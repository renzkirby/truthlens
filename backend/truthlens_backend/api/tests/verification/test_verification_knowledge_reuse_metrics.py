import base64
import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.claim_matching import get_match_result
from api.knowledge_reuse_service import record_knowledge_reuse
from api.models import (
    AccountabilityEvent,
    Claim,
    ClaimFactCheckReference,
    KnowledgeReuseEvent,
    OfficialFactCheck,
    Organization,
    PublicReachEvent,
)
from api.verification_knowledge_reuse_metrics_service import (
    VerificationKnowledgeReuseMetricsIntegrityError,
    get_organization_knowledge_reuse_metrics,
    project_organization_knowledge_reuse_events,
)


class KnowledgeReuseMetricsFixture(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Reuse Partner", slug="reuse-partner")
        self.other_organization = Organization.objects.create(name="Other Partner", slug="other-partner")
        self.actor = User.objects.create_user(username="reuse-metrics-actor")
        self.source_claim = Claim.objects.create(context_text="Published source proposition")
        self.target_claim = Claim.objects.create(context_text="Private target proposition")
        self.publication = self.make_publication()

    def make_publication(self, **overrides):
        values = {
            "claim": self.source_claim,
            "organization": self.organization,
            "canonical_claim": "Published source proposition",
            "verdict": "FACT",
            "headline": "Published reuse fixture",
            "summary": "Published summary",
            "publication_status": OfficialFactCheck.PublicationStatus.PUBLISHED,
        }
        values.update(overrides)
        return OfficialFactCheck.objects.create(**values)

    def record(self, **overrides):
        values = {
            "fact_check": self.publication,
            "reuse_type": KnowledgeReuseEvent.ReuseType.USER_RESPONSE,
            "match_method": KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
            "target_claim": self.target_claim,
        }
        values.update(overrides)
        return record_knowledge_reuse(**values)

    def metrics(self, organization=None):
        return get_organization_knowledge_reuse_metrics(organization=organization or self.organization)


class VerificationKnowledgeReuseMetricsTests(KnowledgeReuseMetricsFixture):
    def test_empty_organization_returns_exact_zero_structure(self):
        self.assertEqual(self.metrics(), {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "KNOWLEDGE_REUSE_EVENT",
                "attribution_source": "SOURCE_ORGANIZATION_ID_SNAPSHOT",
                "target_identity_source": "TARGET_CLAIM_ID_SNAPSHOT",
                "coverage": "ATTRIBUTED_INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "historical_unattributed_rows_excluded": True,
                "first_observed_reuse_at": None,
                "last_observed_reuse_at": None,
            },
            "material_reuse": {
                "events": 0,
                "by_type": {"USER_RESPONSE": 0, "VERIFICATION_CONTEXT": 0},
                "by_match_method": {"EXACT_TEXT": 0, "SEMANTIC": 0, "FULL_TEXT": 0, "CLAIM_CACHE": 0},
                "distinct_publications": 0,
                "distinct_target_claims": 0,
            },
            "repeat_claim_reuse": {"cached_published_responses": 0, "distinct_cached_claims": 0},
        })
        self.assertEqual(project_organization_knowledge_reuse_events(organization=self.organization), [])

    def test_both_reuse_types_and_all_match_methods_count_individually(self):
        for reuse_type in KnowledgeReuseEvent.ReuseType.values:
            for method in KnowledgeReuseEvent.MatchMethod.values:
                self.record(reuse_type=reuse_type, match_method=method)
        result = self.metrics()
        self.assertEqual(result["material_reuse"]["events"], 8)
        self.assertEqual(result["material_reuse"]["by_type"], {"USER_RESPONSE": 4, "VERIFICATION_CONTEXT": 4})
        self.assertEqual(result["material_reuse"]["by_match_method"], {
            "EXACT_TEXT": 2, "SEMANTIC": 2, "FULL_TEXT": 2, "CLAIM_CACHE": 2,
        })
        self.assertEqual(result["repeat_claim_reuse"]["cached_published_responses"], 1)

    def test_repeated_publication_and_target_do_not_deduplicate_events(self):
        timestamp = timezone.now()
        for _ in range(3):
            event = self.record(triggered_by=self.actor, query_text="Same private query")
            KnowledgeReuseEvent.objects.filter(pk=event.pk).update(created_at=timestamp)
        material = self.metrics()["material_reuse"]
        self.assertEqual(material["events"], 3)
        self.assertEqual(material["distinct_publications"], 1)
        self.assertEqual(material["distinct_target_claims"], 1)

    def test_different_publications_count_distinctly(self):
        self.record()
        publication = self.make_publication(claim=Claim.objects.create())
        self.record(fact_check=publication)
        self.assertEqual(self.metrics()["material_reuse"]["distinct_publications"], 2)

    def test_different_nonblank_target_snapshots_count_distinctly(self):
        self.record()
        event = self.record()
        # Historical identity is the snapshot even when the surviving FK is identical.
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(target_claim_id_snapshot="historical-target")
        self.assertEqual(self.metrics()["material_reuse"]["distinct_target_claims"], 2)

    def test_blank_target_snapshot_counts_event_without_reconstruction(self):
        event = self.record()
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(target_claim_id_snapshot="")
        self.record(target_claim=None)
        material = self.metrics()["material_reuse"]
        self.assertEqual(material["events"], 2)
        self.assertEqual(material["distinct_target_claims"], 0)

    def test_only_user_response_claim_cache_is_repeat_claim_reuse(self):
        for reuse_type, method, expected_repeat in (
            ("USER_RESPONSE", "CLAIM_CACHE", 1),
            ("USER_RESPONSE", "EXACT_TEXT", 0),
            ("USER_RESPONSE", "SEMANTIC", 0),
            ("USER_RESPONSE", "FULL_TEXT", 0),
            ("VERIFICATION_CONTEXT", "CLAIM_CACHE", 0),
        ):
            with self.subTest(reuse_type=reuse_type, method=method):
                before = self.metrics()
                self.record(reuse_type=reuse_type, match_method=method)
                after = self.metrics()
                self.assertEqual(after["material_reuse"]["events"], before["material_reuse"]["events"] + 1)
                self.assertEqual(
                    after["repeat_claim_reuse"]["cached_published_responses"],
                    before["repeat_claim_reuse"]["cached_published_responses"] + expected_repeat,
                )

    def test_distinct_cached_claims_use_only_nonblank_snapshots_in_repeat_subset(self):
        for _ in range(2):
            self.record(match_method="CLAIM_CACHE")
        event = self.record(match_method="CLAIM_CACHE")
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(target_claim_id_snapshot="historical-cache-target")
        event = self.record(match_method="CLAIM_CACHE")
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(target_claim_id_snapshot="")
        other_target = Claim.objects.create()
        self.record(target_claim=other_target)
        self.record(target_claim=other_target, reuse_type="VERIFICATION_CONTEXT", match_method="CLAIM_CACHE")
        result = self.metrics()
        self.assertEqual(result["repeat_claim_reuse"], {"cached_published_responses": 4, "distinct_cached_claims": 2})
        self.assertEqual(result["material_reuse"]["distinct_target_claims"], 3)

    def test_other_source_snapshot_is_excluded_even_with_current_organization_match(self):
        event = self.record()
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(
            source_organization_id_snapshot=str(self.other_organization.pk),
        )
        self.assertEqual(self.metrics()["material_reuse"]["events"], 0)
        self.assertEqual(self.metrics(self.other_organization)["material_reuse"]["events"], 1)

    def test_current_publication_organization_change_does_not_move_attribution(self):
        self.record()
        before = self.metrics()
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(organization=self.other_organization)
        self.assertEqual(self.metrics(), before)
        self.assertEqual(self.metrics(self.other_organization)["material_reuse"]["events"], 0)

    def test_target_deletion_preserves_distinct_target_and_cached_counts(self):
        event = self.record(match_method="CLAIM_CACHE")
        before = self.metrics()
        target_id = str(self.target_claim.pk)
        self.target_claim.delete()
        event.refresh_from_db()
        self.assertIsNone(event.target_claim_id)
        self.assertEqual(event.target_claim_id_snapshot, target_id)
        self.assertEqual(self.metrics(), before)

    def test_triggered_by_deletion_does_not_change_metrics(self):
        event = self.record(triggered_by=self.actor)
        before = self.metrics()
        self.actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.triggered_by_id)
        self.assertEqual(self.metrics(), before)

    def test_blank_historical_source_is_excluded_without_relationship_backfill(self):
        event = self.record()
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(source_organization_id_snapshot="")
        before = self.metrics()
        self.assertEqual(before["material_reuse"]["events"], 0)
        self.assertIsNone(before["measurement_basis"]["first_observed_reuse_at"])
        OfficialFactCheck.objects.filter(pk=self.publication.pk).update(organization=self.other_organization)
        self.assertEqual(self.metrics(), before)
        self.assertEqual(self.metrics(self.other_organization)["material_reuse"]["events"], 0)

    def test_padded_source_snapshot_is_not_exact_attribution(self):
        event = self.record()
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(
            source_organization_id_snapshot=f" {self.organization.pk} ",
        )
        self.assertEqual(self.metrics()["material_reuse"]["events"], 0)

    def test_malformed_selected_reuse_type_fails_closed(self):
        self.assert_invalid_database_field("reuse_type", "INVALID")

    def test_malformed_selected_match_method_fails_closed(self):
        self.assert_invalid_database_field("match_method", "INVALID")

    def test_malformed_selected_target_snapshot_fails_closed(self):
        for value in (" ", " padded", "padded ", "\ttarget\n"):
            with self.subTest(value=value):
                self.assert_invalid_database_field("target_claim_id_snapshot", value)

    def test_out_of_range_selected_similarity_score_fails_closed(self):
        for score in (-0.01, 1.01):
            with self.subTest(score=score):
                self.assert_invalid_database_field("similarity_score", score)

    def assert_invalid_database_field(self, field, value):
        event = self.record()
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(**{field: value})
        with self.assertRaises(VerificationKnowledgeReuseMetricsIntegrityError):
            self.metrics()
        # Restore through the narrow fixture bypass before another subtest.
        original = getattr(event, field)
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(**{field: original})

    def test_unrepresentable_missing_identities_and_invalid_fields_fail_closed(self):
        self.record()
        valid_row = project_organization_knowledge_reuse_events(organization=self.organization)[0]
        # NOT NULL columns cannot hold these missing identities. NaN handling also
        # varies by database, so corrupt only the selected measurement row fixture.
        for field, value in (
            ("id", None),
            ("fact_check_id", None),
            ("created_at", None),
            ("target_claim_id_snapshot", None),
            ("target_claim_id_snapshot", 123),
            ("source_organization_id_snapshot", str(self.other_organization.pk)),
            ("similarity_score", float("nan")),
            ("similarity_score", float("inf")),
            ("similarity_score", float("-inf")),
            ("similarity_score", "invalid"),
        ):
            with self.subTest(field=field, value=value):
                row = {**valid_row, field: value}
                with patch("api.verification_knowledge_reuse_metrics_service.KnowledgeReuseEvent.objects.filter") as select:
                    select.return_value.order_by.return_value.values.return_value = [row]
                    with self.assertRaises(VerificationKnowledgeReuseMetricsIntegrityError):
                        self.metrics()

    def test_similarity_score_boundaries_and_absence_are_valid(self):
        for score in (None, 0, 1, 0.5):
            self.record(similarity_score=score)
        self.assertEqual(self.metrics()["material_reuse"]["events"], 4)

    def test_malformed_unselected_history_does_not_poison_selected_metrics(self):
        self.record()
        for source in ("", str(self.other_organization.pk)):
            event = self.record()
            KnowledgeReuseEvent.objects.filter(pk=event.pk).update(
                source_organization_id_snapshot=source, reuse_type="INVALID",
                match_method="INVALID", target_claim_id_snapshot=" padded ",
            )
        self.assertEqual(self.metrics()["material_reuse"]["events"], 1)

    def test_first_and_last_observed_times_use_only_selected_events(self):
        middle = timezone.now()
        earliest = middle - timedelta(days=2)
        latest = middle + timedelta(days=2)
        for timestamp in (latest, earliest, middle):
            event = self.record()
            KnowledgeReuseEvent.objects.filter(pk=event.pk).update(created_at=timestamp)
        event = self.record()
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(
            source_organization_id_snapshot="", created_at=earliest - timedelta(days=10),
        )
        basis = self.metrics()["measurement_basis"]
        self.assertEqual(basis["first_observed_reuse_at"], earliest)
        self.assertEqual(basis["last_observed_reuse_at"], latest)

    def test_result_excludes_actor_fingerprint_metadata_and_raw_text(self):
        event = self.record(triggered_by=self.actor, query_text="Private query contents", metadata={
            "organization_id": str(self.other_organization.pk), "source": "untrusted",
            "raw_claim_text": "Sensitive metadata contents",
        })
        result = self.metrics()
        serialized = json.dumps(result, default=str)
        for private_value in (
            self.actor.username, event.query_fingerprint, "Private query contents",
            self.target_claim.context_text, "Sensitive metadata contents",
        ):
            self.assertNotIn(private_value, serialized)
        def check_keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    self.assertNotIn(key, {
                        "actor", "actor_id", "user", "user_id", "triggered_by", "triggered_by_id",
                        "query_fingerprint", "metadata", "query_text", "claim_text", "context_text",
                    })
                    check_keys(child)
        check_keys(result)
        before = result
        KnowledgeReuseEvent.objects.filter(pk=event.pk).update(metadata=["Arbitrary legacy metadata"])
        self.assertEqual(self.metrics(), before)

    def test_projection_queries_only_reuse_event_measurement_fields(self):
        self.record()
        with CaptureQueriesContext(connection) as queries:
            self.metrics()
        self.assertEqual(len(queries), 1)
        sql = queries[0]["sql"].lower()
        self.assertIn(KnowledgeReuseEvent._meta.db_table.lower(), sql)
        for model in (ClaimFactCheckReference, PublicReachEvent, AccountabilityEvent, OfficialFactCheck, Claim, User):
            self.assertNotIn(f'"{model._meta.db_table.lower()}"', sql)
        for field in ("query_fingerprint", "metadata", "triggered_by_id", "target_claim_id"):
            self.assertNotIn(f'"{field}"', sql)


class FileCacheKnowledgeReuseTests(KnowledgeReuseMetricsFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.actor)
        self.enterContext(patch("api.views.FactCheckRateThrottle.allow_request", return_value=True))
        self.enterContext(patch("api.views.ClaimPollingRateThrottle.allow_request", return_value=True))

    def submit(self, text="Published source proposition", file_name="claim.txt"):
        return self.client.post(reverse("verify_file"), {
            "file_data": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "file_name": file_name,
        }, format="json")

    def test_file_cache_hit_records_exactly_one_event_and_preserves_response(self):
        expected_match = get_match_result(self.source_claim)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        with patch("api.views.find_matching_claim", return_value=self.source_claim), patch(
            "api.views.get_match_result", wraps=get_match_result,
        ) as match:
            response = self.submit(text="  Published source proposition  ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "claim_id": str(self.source_claim.pk), "cached": True, "match": expected_match,
        })
        match.assert_called_once_with(
            self.source_claim, triggered_by=self.actor, record_reuse=True,
            query_text="Published source proposition",
        )
        event = KnowledgeReuseEvent.objects.get()
        self.assertEqual(event.reuse_type, "USER_RESPONSE")
        self.assertEqual(event.match_method, "CLAIM_CACHE")
        self.assertEqual(event.fact_check_id, self.publication.pk)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertEqual(event.target_claim_id_snapshot, str(self.source_claim.pk))
        self.assertEqual(event.triggered_by_id, self.actor.pk)

    def test_anonymous_file_cache_hit_records_without_actor(self):
        self.client.force_authenticate(user=None)
        with patch("api.views.find_matching_claim", return_value=self.source_claim):
            response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cached"])
        self.assertIsNone(KnowledgeReuseEvent.objects.get().triggered_by_id)

    def test_file_cache_without_publication_does_not_fabricate_event(self):
        expected_match = get_match_result(self.target_claim)
        with patch("api.views.find_matching_claim", return_value=self.target_claim):
            response = self.submit()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "claim_id": str(self.target_claim.pk), "cached": True, "match": expected_match,
        })
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_non_cached_file_does_not_record_user_response(self):
        with patch("api.views.find_matching_claim", return_value=None), patch(
            "api.views.text_fact_check_process.delay",
        ) as task, patch("api.views.get_match_result", wraps=get_match_result) as match:
            response = self.submit()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload), {"claim_id", "cached"})
        self.assertFalse(payload["cached"])
        claim = Claim.objects.get(pk=payload["claim_id"])
        self.assertEqual(claim.claim_type, Claim.ClaimType.FILE)
        task.assert_called_once_with(
            "Published source proposition", claim.pk, triggered_by_id=self.actor.pk,
        )
        match.assert_not_called()
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_failed_extraction_and_unsupported_file_do_not_record(self):
        for text, file_name in ((" ", "claim.txt"), ("content", "claim.exe")):
            with self.subTest(file_name=file_name), patch("api.views.find_matching_claim") as lookup:
                response = self.submit(text=text, file_name=file_name)
                self.assertEqual(response.status_code, 400)
                lookup.assert_not_called()
                self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_claim_polling_remains_read_only_for_reuse(self):
        # Existing material reuse history must also remain unchanged by polling.
        self.record(target_claim=self.source_claim, match_method="CLAIM_CACHE")
        before = self.metrics()
        with patch("api.views.get_match_result", wraps=get_match_result) as match:
            for _ in range(3):
                response = self.client.get(reverse("claim_status", kwargs={"claim_id": self.source_claim.pk}))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["resolution_source"], "OFFICIAL_FACT_CHECK")
        self.assertEqual(match.call_count, 3)
        for call in match.call_args_list:
            self.assertEqual(call.kwargs, {})
        self.assertEqual(KnowledgeReuseEvent.objects.count(), 1)
        self.assertEqual(self.metrics(), before)
