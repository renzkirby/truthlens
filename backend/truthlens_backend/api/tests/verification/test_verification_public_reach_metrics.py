import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from api.models import (
    AccountabilityEvent, Claim, ClaimFactCheckReference, KnowledgeReuseEvent,
    OfficialFactCheck, Organization, PublicReachEvent,
)
from api.public_reach_service import VALID_EVENT_SURFACE_PAIRS
from api.verification_public_reach_metrics_service import (
    VerificationPublicReachMetricsIntegrityError,
    get_organization_public_reach_metrics,
    project_organization_public_reach_events,
)


E = PublicReachEvent.EventType
S = PublicReachEvent.SourceSurface
SELECT_PATCH = "api.verification_public_reach_metrics_service.PublicReachEvent.objects.filter"
PAIRS = (
    (E.PARTNER_PROFILE_VIEW, S.PUBLIC_PARTNER_PROFILE),
    (E.PUBLICATION_VIEW, S.PUBLIC_FACT_CHECK_PAGE),
    (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_OFFICIAL_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_RELATED_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_OFFICIAL_FACT_CHECK),
    (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_RELATED_FACT_CHECK),
)


class VerificationPublicReachMetricsTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Reach Partner", slug="reach-partner", public_profile_enabled=True,
            verification_status="VERIFIED", partner_status="ACTIVE",
        )
        self.other = Organization.objects.create(name="Other Reach Partner", slug="other-reach-partner")
        self.publication = OfficialFactCheck.objects.create(
            organization=self.organization, claim=Claim.objects.create(),
            canonical_claim="A published proposition", headline="Reach fixture", verdict="FACT",
            summary="Published summary", publication_status="PUBLISHED",
        )

    def event(self, event_type=E.PUBLICATION_VIEW, surface=S.PUBLIC_FACT_CHECK_PAGE, **overrides):
        is_profile = event_type == E.PARTNER_PROFILE_VIEW
        values = {
            "client_event_id": uuid.uuid4(), "event_type": event_type, "source_surface": surface,
            "source_organization_id_snapshot": str(self.organization.pk),
            "fact_check_id_snapshot": "" if is_profile else str(self.publication.pk),
            "organization": self.organization, "fact_check": None if is_profile else self.publication,
        }
        values.update(overrides)
        # Direct, valid durable fixtures keep projection tests separate from recording eligibility.
        return PublicReachEvent.objects.create(**values)

    def metrics(self, organization=None):
        return get_organization_public_reach_metrics(organization=organization or self.organization)

    def selected_row(self):
        return PublicReachEvent.objects.values(
            "id", "client_event_id", "event_type", "source_surface",
            "source_organization_id_snapshot", "fact_check_id_snapshot", "created_at",
        ).get(pk=self.event().pk)

    def test_empty_organization_returns_exact_zero_structure(self):
        self.assertEqual(self.metrics(), {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "PUBLIC_REACH_EVENT",
                "attribution_source": "SOURCE_ORGANIZATION_ID_SNAPSHOT",
                "publication_identity_source": "FACT_CHECK_ID_SNAPSHOT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "unique_audience_measurement": False,
                "first_observed_interaction_at": None,
                "last_observed_interaction_at": None,
            },
            "observed_interactions": {
                "events": 0,
                "by_type": {"PUBLICATION_VIEW": 0, "PARTNER_PROFILE_VIEW": 0,
                            "EXTENSION_PUBLICATION_IMPRESSION": 0, "EXTENSION_PUBLICATION_CLICK": 0},
                "by_surface": {"PUBLIC_FACT_CHECK_PAGE": 0, "PUBLIC_PARTNER_PROFILE": 0,
                               "EXTENSION_OFFICIAL_FACT_CHECK": 0, "EXTENSION_RELATED_FACT_CHECK": 0},
                "distinct_publications": 0,
            },
            "extension_publications": {
                "impressions": {"official": 0, "related": 0, "total": 0},
                "clicks": {"official": 0, "related": 0, "total": 0},
            },
        })
        self.assertEqual(project_organization_public_reach_events(organization=self.organization), [])

    def test_each_of_six_locked_pairs_counts_individually(self):
        self.assertEqual(set(PAIRS), VALID_EVENT_SURFACE_PAIRS)
        for event_type, surface in PAIRS:
            with self.subTest(event_type=event_type, surface=surface):
                before = self.metrics()
                self.event(event_type, surface)
                after = self.metrics()
                self.assertEqual(after["observed_interactions"]["events"], before["observed_interactions"]["events"] + 1)
                self.assertEqual(after["observed_interactions"]["by_type"][event_type], before["observed_interactions"]["by_type"][event_type] + 1)
                self.assertEqual(after["observed_interactions"]["by_surface"][surface], before["observed_interactions"]["by_surface"][surface] + 1)
        result = self.metrics()
        self.assertEqual(result["observed_interactions"], {
            "events": 6,
            "by_type": {"PUBLICATION_VIEW": 1, "PARTNER_PROFILE_VIEW": 1,
                        "EXTENSION_PUBLICATION_IMPRESSION": 2, "EXTENSION_PUBLICATION_CLICK": 2},
            "by_surface": {"PUBLIC_FACT_CHECK_PAGE": 1, "PUBLIC_PARTNER_PROFILE": 1,
                           "EXTENSION_OFFICIAL_FACT_CHECK": 2, "EXTENSION_RELATED_FACT_CHECK": 2},
            "distinct_publications": 1,
        })
        self.assertEqual(result["extension_publications"], {
            "impressions": {"official": 1, "related": 1, "total": 2},
            "clicks": {"official": 1, "related": 1, "total": 2},
        })

    def test_repeated_interactions_are_not_deduplicated_by_publication_surface_or_time(self):
        timestamp = timezone.now()
        for _ in range(3):
            event = self.event()
            PublicReachEvent.objects.filter(pk=event.pk).update(created_at=timestamp)
        counts = self.metrics()["observed_interactions"]
        self.assertEqual(counts["events"], 3)
        self.assertEqual(counts["by_type"]["PUBLICATION_VIEW"], 3)
        self.assertEqual(counts["distinct_publications"], 1)

    def test_different_publication_snapshots_count_without_current_publication_identity(self):
        self.event()
        self.event(fact_check_id_snapshot="historical-archived-publication", fact_check=None)
        self.assertEqual(self.metrics()["observed_interactions"]["distinct_publications"], 2)

    def test_profile_views_do_not_add_publication_identity(self):
        for _ in range(2):
            self.event(E.PARTNER_PROFILE_VIEW, S.PUBLIC_PARTNER_PROFILE)
        counts = self.metrics()["observed_interactions"]
        self.assertEqual(counts["events"], 2)
        self.assertEqual(counts["distinct_publications"], 0)

    def test_archiving_publication_does_not_change_historical_counts(self):
        self.event()
        before = self.metrics()
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(publication_status="ARCHIVED")
        self.assertEqual(self.metrics(), before)

    def test_source_snapshot_exclusively_controls_attribution(self):
        self.event(source_organization_id_snapshot=str(self.other.pk))
        self.assertEqual(self.metrics()["observed_interactions"]["events"], 0)
        self.assertEqual(self.metrics(self.other)["observed_interactions"]["events"], 1)

    def test_current_organization_fk_change_and_null_do_not_move_attribution(self):
        event = self.event()
        before = self.metrics()
        for organization in (self.other, None):
            PublicReachEvent.objects.filter(pk=event.pk).update(organization=organization)
            self.assertEqual(self.metrics(), before)
            self.assertEqual(self.metrics(self.other)["observed_interactions"]["events"], 0)

    def test_current_fact_check_fk_change_and_null_preserve_publication_snapshot(self):
        event = self.event()
        other_publication = OfficialFactCheck.objects.create(
            claim=Claim.objects.create(), organization=self.other, canonical_claim="Other proposition",
            headline="Other publication", verdict="FACT", summary="Other summary", publication_status="PUBLISHED",
        )
        before = self.metrics()
        for publication in (other_publication, None):
            PublicReachEvent.objects.filter(pk=event.pk).update(fact_check=publication)
            self.assertEqual(self.metrics(), before)
        self.assertEqual(self.metrics()["observed_interactions"]["distinct_publications"], 1)

    def test_eligibility_and_publication_organization_changes_do_not_change_history(self):
        self.event()
        before = self.metrics()
        Organization.objects.filter(pk=self.organization.pk).update(
            public_profile_enabled=False, verification_status="UNVERIFIED", partner_status="SUSPENDED",
        )
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(organization=self.other)
        self.assertEqual(self.metrics(), before)

    def test_malformed_selected_fields_fail_closed_without_repair(self):
        valid = self.selected_row()
        # Pair, snapshot and NOT NULL constraints prevent storing most corrupt rows.
        for field, value in (
            ("event_type", "INVALID"), ("source_surface", "INVALID"),
            ("source_surface", S.PUBLIC_PARTNER_PROFILE),
            ("fact_check_id_snapshot", ""), ("fact_check_id_snapshot", " "),
            ("fact_check_id_snapshot", " padded"), ("fact_check_id_snapshot", "padded "),
            ("fact_check_id_snapshot", None), ("fact_check_id_snapshot", 123),
            ("id", None), ("client_event_id", None), ("created_at", None),
            ("source_organization_id_snapshot", str(self.other.pk)),
        ):
            with self.subTest(field=field, value=value):
                row = {**valid, field: value}
                original = dict(row)
                with patch(SELECT_PATCH) as select:
                    select.return_value.order_by.return_value.values.return_value = [row]
                    with self.assertRaises(VerificationPublicReachMetricsIntegrityError):
                        self.metrics()
                self.assertEqual(row, original)

    def test_profile_with_nonblank_publication_snapshot_fails_closed(self):
        row = self.selected_row()
        row.update(event_type=E.PARTNER_PROFILE_VIEW, source_surface=S.PUBLIC_PARTNER_PROFILE)
        with patch(SELECT_PATCH) as select:
            select.return_value.order_by.return_value.values.return_value = [row]
            with self.assertRaises(VerificationPublicReachMetricsIntegrityError):
                self.metrics()

    def test_stored_padded_publication_snapshot_fails_closed(self):
        event = self.event()
        PublicReachEvent.objects.filter(pk=event.pk).update(fact_check_id_snapshot=" padded ")
        with self.assertRaises(VerificationPublicReachMetricsIntegrityError):
            self.metrics()

    def test_unselected_malformed_history_does_not_poison_requested_organization(self):
        self.event()
        self.event(source_organization_id_snapshot=str(self.other.pk), fact_check_id_snapshot=" padded ")
        self.assertEqual(self.metrics()["observed_interactions"]["events"], 1)

    def test_padded_source_snapshot_is_not_exact_attribution(self):
        self.event(source_organization_id_snapshot=f" {self.organization.pk} ")
        self.assertEqual(self.metrics()["observed_interactions"]["events"], 0)

    def test_first_and_last_times_use_only_selected_events(self):
        middle = timezone.now()
        earliest = middle - timedelta(days=2)
        latest = middle + timedelta(days=2)
        for timestamp in (latest, earliest, middle):
            event = self.event()
            PublicReachEvent.objects.filter(pk=event.pk).update(created_at=timestamp)
        event = self.event(source_organization_id_snapshot=str(self.other.pk))
        PublicReachEvent.objects.filter(pk=event.pk).update(created_at=earliest - timedelta(days=10))
        basis = self.metrics()["measurement_basis"]
        self.assertEqual(basis["first_observed_interaction_at"], earliest)
        self.assertEqual(basis["last_observed_interaction_at"], latest)

    def test_projection_and_metrics_exclude_client_person_and_current_fk_identity(self):
        event = self.event()
        projected = project_organization_public_reach_events(organization=self.organization)
        self.assertEqual(set(projected[0]), {"event_type", "source_surface", "fact_check_id_snapshot", "created_at"})
        result = self.metrics()
        serialized = json.dumps({"projected": projected, "metrics": result}, default=str)
        self.assertNotIn(str(event.client_event_id), serialized)
        for key in (
            "client_event_id", "user_id", "actor_id", "visitor_id", "ip", "ip_address",
            "user_agent", "referrer", "page_url", "fact_check_id", "unique_users",
            "unique_visitors", "unique_viewers", "unique_clickers", "sessions", "audience_size",
        ):
            self.assertNotIn(f'"{key}"', serialized)
        self.assertIs(result["measurement_basis"]["unique_audience_measurement"], False)

    def test_only_public_reach_measurement_fields_are_queried(self):
        self.event()
        with CaptureQueriesContext(connection) as queries:
            self.metrics()
        self.assertEqual(len(queries), 1)
        sql = queries[0]["sql"].lower()
        for field in ("id", "client_event_id", "event_type", "source_surface",
                      "source_organization_id_snapshot", "fact_check_id_snapshot", "created_at"):
            self.assertIn(f'"{field}"', sql)
        for field in ("organization_id", "fact_check_id"):
            self.assertNotIn(f'"{field}"', sql)
        for model in (KnowledgeReuseEvent, ClaimFactCheckReference, AccountabilityEvent, Organization, OfficialFactCheck, Claim, User):
            self.assertNotIn(f'"{model._meta.db_table.lower()}"', sql)

    def test_projection_does_not_call_current_eligibility_or_provider_services(self):
        self.event()
        with (
            patch("api.public_reach_service.get_public_partner_fact_check_detail") as publication,
            patch("api.public_reach_service.is_public_partner_eligible") as eligible,
            patch("api.services.call_llm_with_fallback") as provider,
        ):
            self.metrics()
        publication.assert_not_called()
        eligible.assert_not_called()
        provider.assert_not_called()

    def test_extension_totals_equal_official_plus_related_for_uneven_counts(self):
        for event_type, surface, count in (
            (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_OFFICIAL_FACT_CHECK, 3),
            (E.EXTENSION_PUBLICATION_IMPRESSION, S.EXTENSION_RELATED_FACT_CHECK, 2),
            (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_OFFICIAL_FACT_CHECK, 1),
            (E.EXTENSION_PUBLICATION_CLICK, S.EXTENSION_RELATED_FACT_CHECK, 4),
        ):
            for _ in range(count):
                self.event(event_type, surface)
        extension = self.metrics()["extension_publications"]
        self.assertEqual(extension, {
            "impressions": {"official": 3, "related": 2, "total": 5},
            "clicks": {"official": 1, "related": 4, "total": 5},
        })
        for counts in extension.values():
            self.assertEqual(counts["total"], counts["official"] + counts["related"])
