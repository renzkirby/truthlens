import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from importlib import import_module
from unittest.mock import patch

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, connections, migrations, models, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from api.models import AccountabilityEvent, KnowledgeReuseEvent, OfficialFactCheck, Organization, PublicReachEvent
from api.public_publication_query_service import get_public_partner_fact_check_detail
from api.public_reach_service import (
    InvalidPublicReach,
    PublicReachConflict,
    PublicReachTargetNotFound,
    VALID_EVENT_SURFACE_PAIRS,
    record_public_reach_event,
)
from api.tests.workspace.test_editorial_revision_publication import EditorialReplacementFixtures
from api.throttles import PublicPartnerRateThrottle, PublicReachRateThrottle
from api.views import public_reach_events


E = PublicReachEvent.EventType
S = PublicReachEvent.SourceSurface
EXPECTED_PAIRS = {
    (E.PARTNER_PROFILE_VIEW, S.PUBLIC_PARTNER_PROFILE),
    (E.PUBLICATION_VIEW, S.PUBLIC_FACT_CHECK_PAGE),
    (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_OFFICIAL_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_RELATED_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_OFFICIAL_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_RELATED_FACT_CHECK),
}


class PublicReachInstrumentationTests(EditorialReplacementFixtures, TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        Organization.objects.filter(pk=self.organization.pk).update(public_profile_enabled=True)
        self.organization.refresh_from_db()
        self.client = APIClient()
        self.url = reverse("public_reach_events")

    def record(self, **overrides):
        values = {
            "client_event_id": uuid.uuid4(),
            "event_type": E.PARTNER_PROFILE_VIEW,
            "source_surface": S.PUBLIC_PARTNER_PROFILE,
            "organization": self.organization,
        }
        values.update(overrides)
        return record_public_reach_event(**values)

    def payload(self, **overrides):
        values = {
            "client_event_id": str(uuid.uuid4()),
            "event_type": E.PARTNER_PROFILE_VIEW,
            "source_surface": S.PUBLIC_PARTNER_PROFILE,
            "organization_slug": self.organization.slug,
            "publication_id": None,
        }
        values.update(overrides)
        return values

    def publication(self):
        return self.make_published_context(suffix="reach")["published"]

    def test_profile_view_exact_snapshots(self):
        event, created = self.record()
        event.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(event.organization, self.organization)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertEqual(event.fact_check_id_snapshot, "")
        self.assertIsNone(event.fact_check)

    def test_all_publication_pairs_persist_exact_publication_snapshot(self):
        publication = self.publication()
        for event_type, surface in EXPECTED_PAIRS - {(E.PARTNER_PROFILE_VIEW, S.PUBLIC_PARTNER_PROFILE)}:
            with self.subTest(event_type=event_type, surface=surface):
                event, created = self.record(event_type=event_type, source_surface=surface, fact_check=publication)
                self.assertTrue(created)
                self.assertEqual(event.fact_check, publication)
                self.assertEqual(event.fact_check_id_snapshot, str(publication.pk))
                self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))

    def test_archived_public_history_is_recorded_as_selected_version(self):
        context = self.make_published_context(suffix="historical-reach")
        predecessor = context["published"]
        successor = self.replace(context, self.make_submitted_revision(context))["fact_check"]
        predecessor.refresh_from_db()
        self.assertEqual(predecessor.publication_status, OfficialFactCheck.PublicationStatus.ARCHIVED)
        with patch("api.public_reach_service.get_public_partner_fact_check_detail", wraps=get_public_partner_fact_check_detail) as detail:
            event, _ = self.record(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE, fact_check=predecessor)
        detail.assert_called_once()
        self.assertEqual(detail.call_args.kwargs["publication_id"], predecessor.pk)
        self.assertEqual(event.fact_check_id_snapshot, str(predecessor.pk))
        self.assertNotEqual(event.fact_check_id_snapshot, str(successor.pk))
        response = self.client.post(self.url, self.payload(
            event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE,
            publication_id=str(predecessor.pk),
        ), format="json")
        self.assertEqual(response.status_code, 201)

    def test_every_invalid_pair_fails_closed_in_service_and_api(self):
        publication = self.publication()
        for event_type in E.values + ["UNKNOWN"]:
            for surface in S.values + ["UNKNOWN"]:
                if (event_type, surface) in EXPECTED_PAIRS:
                    continue
                with self.subTest(event_type=event_type, surface=surface):
                    with self.assertRaises(InvalidPublicReach):
                        self.record(event_type=event_type, source_surface=surface, fact_check=publication)
                    response = self.client.post(self.url, self.payload(
                        event_type=event_type, source_surface=surface, publication_id=str(publication.pk),
                    ), format="json")
                    self.assertEqual(response.status_code, 400)
        self.assertFalse(PublicReachEvent.objects.exists())

    def test_profile_with_publication_and_publication_without_target_are_invalid(self):
        publication = self.publication()
        with self.assertRaises(InvalidPublicReach):
            self.record(fact_check=publication)
        with self.assertRaises(InvalidPublicReach):
            self.record(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE)
        for payload in (
            self.payload(publication_id=str(publication.pk)),
            self.payload(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE),
        ):
            self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    def test_uuid_validation(self):
        for value in (None, "", "not-a-uuid", 123, {}, []):
            with self.subTest(value=value), self.assertRaises(InvalidPublicReach):
                self.record(client_event_id=value)
        self.assertFalse(PublicReachEvent.objects.exists())

    def test_unknown_and_unsaved_organizations_fail_closed(self):
        for organization in (None, Organization(name="Unsaved", slug="unsaved")):
            with self.subTest(organization=organization), self.assertRaises(PublicReachTargetNotFound):
                self.record(organization=organization)
        self.assertEqual(self.client.post(self.url, self.payload(organization_slug="missing-partner"), format="json").status_code, 404)
        deleted = Organization.objects.create(name="Deleted", slug="deleted-reach")
        deleted_id = deleted.pk
        Organization.objects.filter(pk=deleted_id).delete()
        with self.assertRaises(PublicReachTargetNotFound):
            self.record(organization=deleted)

    def test_ineligible_organization_is_revalidated_even_with_stale_instance(self):
        for changes in (
            {"public_profile_enabled": False},
            {"verification_status": Organization.VerificationStatus.UNVERIFIED},
            {"partner_status": Organization.PartnerStatus.SUSPENDED},
        ):
            with self.subTest(changes=changes):
                Organization.objects.filter(pk=self.organization.pk).update(**changes)
                with self.assertRaises(PublicReachTargetNotFound):
                    self.record()
                self.assertEqual(self.client.post(self.url, self.payload(), format="json").status_code, 404)
                Organization.objects.filter(pk=self.organization.pk).update(
                    public_profile_enabled=True,
                    verification_status=Organization.VerificationStatus.VERIFIED,
                    partner_status=Organization.PartnerStatus.ACTIVE,
                )

    def test_inaccessible_and_broken_publication_lineage_rejected(self):
        context = self.make_published_context(suffix="broken-reach")
        publication = context["published"]
        revision = self.make_submitted_revision(context)
        with self.assertRaises(PublicReachTargetNotFound):
            self.record(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE, fact_check=revision)
        # Deliberate corruption verifies the existing public contract is reused.
        type(context["seal"]).objects.filter(pk=context["seal"].pk).update(payload={})
        with self.assertRaises(PublicReachTargetNotFound):
            self.record(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE, fact_check=publication)
        response = self.client.post(self.url, self.payload(event_type=E.PUBLICATION_VIEW,
            source_surface=S.PUBLIC_FACT_CHECK_PAGE, publication_id=str(publication.pk)), format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(PublicReachEvent.objects.exists())

    def test_wrong_organization_and_unsaved_publication_fail_closed(self):
        publication = self.publication()
        other = Organization.objects.create(name="Other reach", slug="other-reach",
            public_profile_enabled=True, verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE)
        for target in (publication, OfficialFactCheck(organization=other)):
            with self.subTest(target=target), self.assertRaises(PublicReachTargetNotFound):
                self.record(organization=other, event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE, fact_check=target)
        response = self.client.post(self.url, self.payload(organization_slug=other.slug,
            event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE,
            publication_id=str(publication.pk)), format="json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.post(self.url, self.payload(event_type=E.PUBLICATION_VIEW,
            source_surface=S.PUBLIC_FACT_CHECK_PAGE, publication_id=str(uuid.uuid4())), format="json").status_code, 404)

    def test_identical_client_event_id_returns_existing_row(self):
        key = uuid.uuid4()
        first, created = self.record(client_event_id=key)
        repeat, repeated_create = self.record(client_event_id=str(key))
        self.assertTrue(created)
        self.assertFalse(repeated_create)
        self.assertEqual(first.pk, repeat.pk)
        self.assertEqual(PublicReachEvent.objects.count(), 1)

    def test_conflicting_client_event_id_rejects_every_semantic_dimension(self):
        publication = self.publication()
        other_publication = self.make_published_context(suffix="other-target")["published"]
        other_org = Organization.objects.create(name="Another reach", slug="another-reach",
            public_profile_enabled=True, verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE)
        profile_key = uuid.uuid4()
        self.record(client_event_id=profile_key)
        with self.assertRaises(PublicReachConflict):
            self.record(client_event_id=profile_key, organization=other_org)
        key = uuid.uuid4()
        original = dict(client_event_id=key, event_type=E.EXTENSION_PUBLICATION_IMPRESSION,
            source_surface=S.EXTENSION_OFFICIAL_FACT_CHECK, fact_check=publication)
        self.record(**original)
        for changes in (
            {"event_type": E.EXTENSION_PUBLICATION_CLICK},
            {"source_surface": S.EXTENSION_RELATED_FACT_CHECK},
            {"fact_check": other_publication},
            {"event_type": E.PUBLICATION_VIEW, "source_surface": S.PUBLIC_FACT_CHECK_PAGE},
        ):
            with self.subTest(changes=changes), self.assertRaises(PublicReachConflict):
                self.record(**{**original, **changes})
        self.assertEqual(PublicReachEvent.objects.count(), 2)

    def test_repeated_genuine_views_use_distinct_keys_and_are_allowed(self):
        self.record()
        self.record()
        self.assertEqual(PublicReachEvent.objects.count(), 2)

    def test_unique_constraint_rejects_duplicate_inserts(self):
        event, _ = self.record()
        values = {field: getattr(event, field) for field in (
            "client_event_id", "event_type", "source_surface", "organization",
            "source_organization_id_snapshot", "fact_check_id_snapshot",
        )}
        with self.assertRaises(IntegrityError), transaction.atomic():
            PublicReachEvent.objects.create(**values)
        self.assertEqual(PublicReachEvent.objects.count(), 1)

    def test_event_update_delete_and_reconstructed_pk_update_rejected(self):
        event, _ = self.record()
        event.client_event_id = uuid.uuid4()
        event.source_organization_id_snapshot = "changed"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            PublicReachEvent(pk=event.pk).save()
        event.refresh_from_db()
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))

    def test_organization_deletion_nulls_relationship_preserves_snapshot(self):
        organization = Organization.objects.create(name="Ephemeral", slug="ephemeral-reach",
            public_profile_enabled=True, verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE)
        event, _ = self.record(organization=organization)
        snapshot = str(organization.pk)
        organization.delete()
        event.refresh_from_db()
        self.assertIsNone(event.organization_id)
        self.assertEqual(event.source_organization_id_snapshot, snapshot)

    def test_publication_relationship_changes_preserve_snapshots(self):
        publication = self.publication()
        event, _ = self.record(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE, fact_check=publication)
        OfficialFactCheck.objects.filter(pk=publication.pk).update(organization=None)
        # Simulate a later relationship removal without rewriting the event.
        PublicReachEvent.objects.filter(pk=event.pk).update(organization=None, fact_check=None)
        event.refresh_from_db()
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertEqual(event.fact_check_id_snapshot, str(publication.pk))

    def test_publication_deletion_nulls_fk_without_erasing_snapshot(self):
        # A minimal unsealed row isolates SET_NULL from unrelated publication
        # protection rules. No production public-validity rules are relaxed.
        publication = OfficialFactCheck.objects.create(organization=self.organization)
        snapshot = str(publication.pk)
        event = PublicReachEvent.objects.create(client_event_id=uuid.uuid4(),
            event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE,
            organization=self.organization, fact_check=publication,
            source_organization_id_snapshot=str(self.organization.pk), fact_check_id_snapshot=snapshot)
        OfficialFactCheck.objects.filter(pk=publication.pk).delete()
        event.refresh_from_db()
        self.assertIsNone(event.fact_check_id)
        self.assertEqual(event.fact_check_id_snapshot, snapshot)

    def test_api_allow_any_new_repeat_and_conflict_statuses_with_tiny_response(self):
        payload = self.payload()
        new = self.client.post(self.url, payload, format="json")
        repeat = self.client.post(self.url, payload, format="json")
        self.assertEqual(new.status_code, 201)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(new.data, {"recorded": True})
        self.assertEqual(repeat.data, {"recorded": True})
        publication = self.publication()
        conflicting = self.client.post(self.url, {**payload, "event_type": E.PUBLICATION_VIEW,
            "source_surface": S.PUBLIC_FACT_CHECK_PAGE, "publication_id": str(publication.pk)}, format="json")
        self.assertEqual(conflicting.status_code, 409)
        self.assertEqual(PublicReachEvent.objects.count(), 1)

    def test_api_publication_pairs_have_created_and_idempotent_statuses(self):
        publication = self.publication()
        for event_type, surface in EXPECTED_PAIRS - {(E.PARTNER_PROFILE_VIEW, S.PUBLIC_PARTNER_PROFILE)}:
            with self.subTest(event_type=event_type, surface=surface):
                payload = self.payload(event_type=event_type, source_surface=surface, publication_id=str(publication.pk))
                self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 201)
                self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 200)

    def test_api_rejects_unknown_fields_and_malformed_payloads(self):
        for payload in ({}, [], "text", self.payload(client_event_id="invalid"),
            self.payload(client_event_id=123), self.payload(publication_id=123),
            self.payload(organization_slug=123),
            self.payload(publication_id="invalid"), self.payload(organization_slug="../invalid"),
            *[self.payload(**{field: "private"}) for field in (
                "user", "email", "ip_address", "user_agent", "referrer", "page_url",
                "source_url", "query", "claim_text", "metadata", "endpoint",
            )]):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)
        self.assertFalse(PublicReachEvent.objects.exists())
        absent_publication = self.payload()
        absent_publication.pop("publication_id")
        self.assertEqual(self.client.post(self.url, absent_publication, format="json").status_code, 201)

    def test_authenticated_api_caller_records_no_durable_identity(self):
        self.client.force_authenticate(user=self.lead)
        response = self.client.post(self.url, self.payload(), format="json",
            HTTP_REFERER="https://private.example/page", HTTP_USER_AGENT="private-agent", REMOTE_ADDR="192.0.2.1")
        self.assertEqual(response.status_code, 201)
        event = PublicReachEvent.objects.get()
        self.assertEqual({field.name for field in event._meta.fields}, EXPECTED_FIELDS)
        self.assertNotIn(self.lead.username, str(event.__dict__))
        for value in ("private.example", "private-agent", "192.0.2.1"):
            self.assertNotIn(value, str(event.__dict__))

    def test_recording_creates_no_other_events_and_invokes_no_providers(self):
        publication = self.publication()
        counts = (KnowledgeReuseEvent.objects.count(), AccountabilityEvent.objects.count())
        # Fail loudly if recording unexpectedly calls provider entry points.
        provider_paths = [
            "api.embedding_service.generate_embedding",
            "api.claim_matching.generate_embedding",
            "api.services.evaluate_claim_with_persisted_evidence",
            "api.services.search_official_vault",
            "api.services.groq_client.chat.completions.create",
            "api.services.gemini_client.models.generate_content",
            "api.verification.providers.tavily.TavilyProvider.search_with_payload",
            "api.verification.providers.google_fact_check.GoogleFactCheckProvider.search_with_payload",
            "requests.sessions.Session.request",
        ]
        with ExitStack() as stack:
            providers = [stack.enter_context(patch(path, side_effect=AssertionError("Unexpected provider call"))) for path in provider_paths]
            self.record()
            self.record(event_type=E.PUBLICATION_VIEW, source_surface=S.PUBLIC_FACT_CHECK_PAGE, fact_check=publication)
            response = self.client.post(self.url, self.payload(event_type=E.EXTENSION_PUBLICATION_CLICK,
                source_surface=S.EXTENSION_RELATED_FACT_CHECK, publication_id=str(publication.pk)), format="json")
            self.assertEqual(response.status_code, 201)
            for provider in providers:
                provider.assert_not_called()
        self.assertEqual(counts, (KnowledgeReuseEvent.objects.count(), AccountabilityEvent.objects.count()))

    def test_existing_public_get_endpoints_record_zero_reach_events(self):
        publication = self.publication()
        for url in (
            reverse("public_partner_detail", kwargs={"slug": self.organization.slug}),
            reverse("public_partner_fact_check_detail", kwargs={"slug": self.organization.slug, "publication_id": publication.pk}),
        ):
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertFalse(PublicReachEvent.objects.exists())

    def test_database_constraints_reject_bad_pair_and_snapshots(self):
        defaults = dict(client_event_id=uuid.uuid4(), event_type=E.PARTNER_PROFILE_VIEW,
            source_surface=S.PUBLIC_PARTNER_PROFILE, source_organization_id_snapshot=str(self.organization.pk),
            fact_check_id_snapshot="")
        for changes in (
            {"source_surface": S.PUBLIC_FACT_CHECK_PAGE},
            {"event_type": "UNKNOWN"},
            {"fact_check_id_snapshot": str(uuid.uuid4())},
            {"source_organization_id_snapshot": ""},
            {"event_type": E.PUBLICATION_VIEW, "source_surface": S.PUBLIC_FACT_CHECK_PAGE},
        ):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), transaction.atomic():
                PublicReachEvent.objects.create(**{**defaults, **changes})
        self.assertFalse(PublicReachEvent.objects.exists())


EXPECTED_FIELDS = {
    "id", "client_event_id", "event_type", "source_surface", "organization", "fact_check",
    "source_organization_id_snapshot", "fact_check_id_snapshot", "created_at",
}


class PublicReachContractTests(SimpleTestCase):
    def test_exact_schema_excludes_all_identity_and_metadata(self):
        self.assertEqual({field.name for field in PublicReachEvent._meta.fields}, EXPECTED_FIELDS)
        for name in ("id", "client_event_id"):
            self.assertIsInstance(PublicReachEvent._meta.get_field(name), models.UUIDField)
        self.assertTrue(PublicReachEvent._meta.get_field("id").primary_key)
        self.assertTrue(PublicReachEvent._meta.get_field("client_event_id").unique)
        self.assertFalse(PublicReachEvent._meta.get_field("client_event_id").editable)
        for name in ("organization", "fact_check"):
            field = PublicReachEvent._meta.get_field(name)
            self.assertTrue(field.null)
            self.assertTrue(field.blank)
            self.assertIs(field.remote_field.on_delete, models.SET_NULL)
            self.assertEqual(field.remote_field.related_name, "public_reach_events")
        for name in ("source_organization_id_snapshot", "fact_check_id_snapshot"):
            field = PublicReachEvent._meta.get_field(name)
            self.assertEqual(field.max_length, 255)
            self.assertTrue(field.db_index)
            self.assertFalse(field.null)
        self.assertFalse(PublicReachEvent._meta.get_field("source_organization_id_snapshot").blank)
        self.assertTrue(PublicReachEvent._meta.get_field("fact_check_id_snapshot").blank)
        self.assertTrue(PublicReachEvent._meta.get_field("created_at").auto_now_add)
        for name in ("event_type", "source_surface"):
            self.assertTrue(PublicReachEvent._meta.get_field(name).db_index)

    def test_exact_choices_and_pair_contract(self):
        self.assertEqual(set(E.values), {"PUBLICATION_VIEW", "PARTNER_PROFILE_VIEW", "EXTENSION_PUBLICATION_IMPRESSION", "EXTENSION_PUBLICATION_CLICK"})
        self.assertEqual(set(S.values), {"PUBLIC_FACT_CHECK_PAGE", "PUBLIC_PARTNER_PROFILE", "EXTENSION_OFFICIAL_FACT_CHECK", "EXTENSION_RELATED_FACT_CHECK"})
        self.assertEqual(VALID_EVENT_SURFACE_PAIRS, EXPECTED_PAIRS)

    def test_permission_throttle_and_independent_scope(self):
        self.assertEqual(public_reach_events.cls.permission_classes, [AllowAny])
        self.assertEqual(public_reach_events.cls.throttle_classes, [PublicReachRateThrottle])
        self.assertEqual(PublicReachRateThrottle.scope, "public_reach")
        self.assertNotEqual(PublicReachRateThrottle.scope, PublicPartnerRateThrottle.scope)
        from rest_framework.test import APIRequestFactory
        request = APIRequestFactory().post("/api/public-reach/events/")
        reach_key = PublicReachRateThrottle().get_cache_key(request, None)
        self.assertIn("public_reach", reach_key)

    def test_migration_has_exact_dependency_and_only_create_model_without_backfill(self):
        migration = import_module("api.migrations.0070_public_reach_event").Migration
        self.assertEqual(migration.dependencies, [("api", "0069_claim_fact_check_relationship_unique")])
        self.assertEqual(len(migration.operations), 1)
        operation = migration.operations[0]
        self.assertIs(type(operation), migrations.CreateModel)
        self.assertEqual(operation.name, "PublicReachEvent")
        self.assertEqual({name for name, _ in operation.fields}, EXPECTED_FIELDS)
        for name, field in operation.fields:
            with self.subTest(name=name):
                self.assertEqual(field.deconstruct()[1:], PublicReachEvent._meta.get_field(name).deconstruct()[1:])
        self.assertEqual(operation.options["ordering"], PublicReachEvent._meta.ordering)
        for option in ("indexes", "constraints"):
            self.assertEqual([item.deconstruct() for item in operation.options[option]],
                [item.deconstruct() for item in getattr(PublicReachEvent._meta, option)])
        self.assertEqual([index.fields for index in PublicReachEvent._meta.indexes], [
            ["event_type", "-created_at"], ["source_surface", "-created_at"],
            ["source_organization_id_snapshot", "-created_at"], ["fact_check_id_snapshot", "-created_at"],
        ])
        self.assertEqual({constraint.name for constraint in PublicReachEvent._meta.constraints}, {
            "reach_valid_event_surface", "reach_publication_snapshot", "reach_organization_snapshot",
        })


class PublicReachConcurrencyTests(TransactionTestCase):
    def test_simultaneous_identical_events_produce_one_row(self):
        if connection.vendor != "postgresql":
            self.skipTest("Concurrent insert contract requires PostgreSQL.")
        organization = Organization.objects.create(name="Concurrent reach", slug="concurrent-reach",
            public_profile_enabled=True, verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE)
        event_id = uuid.uuid4()
        barrier = threading.Barrier(2)
        original_create = models.QuerySet.create

        def competing_insert(queryset, **kwargs):
            if queryset.model is PublicReachEvent:
                # Both get_or_create callers must observe the missing key before
                # either insert wins, exercising unique-key race recovery.
                barrier.wait(timeout=10)
            return original_create(queryset, **kwargs)

        def record():
            close_old_connections()
            try:
                target = Organization.objects.get(pk=organization.pk)
                event, created = record_public_reach_event(client_event_id=event_id,
                    event_type=E.PARTNER_PROFILE_VIEW, source_surface=S.PUBLIC_PARTNER_PROFILE,
                    organization=target)
                return event.pk, created
            finally:
                connections.close_all()

        with patch.object(models.QuerySet, "create", competing_insert), ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(record) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(len({event_id for event_id, _ in results}), 1)
        self.assertEqual(sorted(created for _, created in results), [False, True])
        self.assertEqual(PublicReachEvent.objects.filter(client_event_id=event_id).count(), 1)
