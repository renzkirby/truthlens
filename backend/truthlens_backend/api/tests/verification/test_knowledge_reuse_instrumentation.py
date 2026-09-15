import hashlib
import json
from importlib import import_module
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import migrations, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase

from api.knowledge_reuse_service import (
    InvalidKnowledgeReuse,
    build_query_fingerprint,
    record_knowledge_reuse,
)
from api.models import Claim, KnowledgeReuseEvent, OfficialFactCheck, Organization


class KnowledgeReuseInstrumentationTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Knowledge Source Partner", slug="knowledge-source-partner",
        )
        self.other_organization = Organization.objects.create(
            name="Other Knowledge Partner", slug="other-knowledge-partner",
        )
        self.actor = User.objects.create_user(username="knowledge-reuse-user")
        self.source_claim = Claim.objects.create(context_text="Published source claim")
        self.target_claim = Claim.objects.create(context_text="Independent target claim")
        self.fact_check = self.make_publication(claim=self.source_claim)

    def make_publication(self, **overrides):
        values = {
            "claim": self.source_claim,
            "organization": self.organization,
            "canonical_claim": "An authoritative published knowledge fixture.",
            "verdict": "FACT",
            "headline": "Knowledge reuse fixture",
            "summary": "Published knowledge for recorder tests.",
            "publication_status": OfficialFactCheck.PublicationStatus.PUBLISHED,
        }
        values.update(overrides)
        return OfficialFactCheck.objects.create(**values)

    def record(self, **overrides):
        values = {
            "fact_check": self.fact_check,
            "reuse_type": KnowledgeReuseEvent.ReuseType.USER_RESPONSE,
            "match_method": KnowledgeReuseEvent.MatchMethod.EXACT_TEXT,
        }
        values.update(overrides)
        return record_knowledge_reuse(**values)

    def test_user_response_records_exact_source_organization_snapshot(self):
        event = self.record()
        event.refresh_from_db()
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertIsInstance(event.source_organization_id_snapshot, str)
        self.assertEqual(event.fact_check, self.fact_check)

    def test_verification_context_records_exact_source_organization_snapshot(self):
        event = self.record(reuse_type=KnowledgeReuseEvent.ReuseType.VERIFICATION_CONTEXT)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))

    def test_target_claim_records_exact_normalized_string_snapshot(self):
        event = self.record(target_claim=self.target_claim)
        event.refresh_from_db()
        self.assertEqual(event.target_claim_id_snapshot, str(self.target_claim.pk))
        self.assertIsInstance(event.target_claim_id_snapshot, str)
        self.assertEqual(event.target_claim, self.target_claim)

    def test_absent_target_claim_stores_empty_snapshot_without_substituting_source_claim(self):
        event = self.record()
        self.assertIsNone(event.target_claim)
        self.assertEqual(event.target_claim_id_snapshot, "")
        self.assertNotEqual(event.target_claim_id_snapshot, str(self.source_claim.pk))

    def test_central_recorder_strips_snapshot_identifiers_without_relationship_lookups(self):
        organization_id = str(self.organization.pk)
        target_id = str(self.target_claim.pk)
        self.fact_check.organization_id = f" {organization_id} \t"
        self.target_claim.pk = f" {target_id} \t"
        # Mock the insert so transport-independent normalization is tested without
        # requiring padded strings to be valid UUID FK values in the database.
        with self.assertNumQueries(0):
            with patch("api.knowledge_reuse_service.KnowledgeReuseEvent.objects.create") as create:
                self.record(target_claim=self.target_claim)
        self.assertEqual(create.call_args.kwargs["source_organization_id_snapshot"], organization_id)
        self.assertEqual(create.call_args.kwargs["target_claim_id_snapshot"], target_id)

    def test_unsaved_fact_check_with_autoassigned_uuid_is_rejected(self):
        fact_check = OfficialFactCheck(
            organization=self.organization,
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertIsNotNone(fact_check.pk)
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record(fact_check=fact_check)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_fact_check_without_primary_key_is_rejected(self):
        self.fact_check.pk = None
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record()
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_absent_fact_check_is_rejected(self):
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record(fact_check=None)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_published_fact_check_without_organization_is_rejected_without_fallback(self):
        fact_check = self.make_publication(organization=None, claim=None)
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record(
                fact_check=fact_check, target_claim=self.target_claim, triggered_by=self.actor,
                metadata={"source": "TEST", "organization_id": str(self.organization.pk)},
            )
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_blank_source_organization_identifier_is_rejected(self):
        for organization_id in ("", " \t"):
            with self.subTest(organization_id=organization_id):
                self.fact_check.organization_id = organization_id
                with self.assertRaises(InvalidKnowledgeReuse):
                    self.record()
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_nonpublished_fact_checks_remain_rejected(self):
        for status in (OfficialFactCheck.PublicationStatus.DRAFT,
                       OfficialFactCheck.PublicationStatus.IN_REVIEW,
                       OfficialFactCheck.PublicationStatus.ARCHIVED):
            with self.subTest(status=status):
                self.fact_check.publication_status = status
                with self.assertRaises(InvalidKnowledgeReuse):
                    self.record()
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_unsaved_target_claim_with_autoassigned_uuid_is_rejected(self):
        target = Claim(context_text="Unsaved target")
        self.assertIsNotNone(target.pk)
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record(target_claim=target)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_missing_or_blank_target_claim_identifier_is_rejected(self):
        for target_id in (None, "", " \t"):
            with self.subTest(target_id=target_id):
                self.target_claim.pk = target_id
                with self.assertRaises(InvalidKnowledgeReuse):
                    self.record(target_claim=self.target_claim)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_similarity_score_validation_and_conversion_remain_intact(self):
        for score in (-0.01, 1.01):
            with self.subTest(score=score), self.assertRaises(InvalidKnowledgeReuse):
                self.record(similarity_score=score)
        self.assertFalse(KnowledgeReuseEvent.objects.exists())
        for score, expected in ((None, None), (0, 0.0), (1, 1.0), ("0.75", 0.75)):
            with self.subTest(score=score):
                self.assertEqual(self.record(similarity_score=score).similarity_score, expected)

    def test_invalid_reuse_type_remains_rejected(self):
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record(reuse_type="PUBLIC_PAGE_VIEW")
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_invalid_match_method_remains_rejected(self):
        with self.assertRaises(InvalidKnowledgeReuse):
            self.record(match_method="UNSUPPORTED")
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_all_existing_match_methods_remain_recordable(self):
        for method in KnowledgeReuseEvent.MatchMethod.values:
            with self.subTest(method=method):
                self.assertEqual(self.record(match_method=method).match_method, method)

    def test_raw_query_is_not_automatically_stored_in_fields_or_metadata(self):
        query_text = "  Private QUERY material with sensitive phrasing  "
        metadata = {"source": "TEST", "match_stage": "EXISTING"}
        event = self.record(query_text=query_text, metadata=metadata, triggered_by=self.actor)
        row = KnowledgeReuseEvent.objects.values().get(pk=event.pk)
        serialized = json.dumps(row, default=str).casefold()
        self.assertNotIn(query_text.casefold(), serialized)
        self.assertNotIn("private query material with sensitive phrasing", serialized)
        self.assertEqual(event.query_fingerprint, hashlib.sha256(
            b"private query material with sensitive phrasing"
        ).hexdigest())
        self.assertEqual(event.metadata, {"source": "TEST", "match_stage": "EXISTING"})
        self.assertEqual(metadata, event.metadata)

    def test_triggered_by_is_not_copied_into_durable_attribution_or_metadata(self):
        event = self.record(triggered_by=self.actor)
        self.assertEqual(event.triggered_by, self.actor)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertEqual(event.target_claim_id_snapshot, "")
        self.assertEqual(event.metadata, {})
        self.actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.triggered_by)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertEqual(event.target_claim_id_snapshot, "")

    def test_event_save_after_creation_is_rejected(self):
        event = self.record()
        with self.assertRaisesMessage(ValidationError, "immutable"):
            event.save()

    def test_changing_reuse_type_then_saving_is_rejected(self):
        event = self.record()
        event.reuse_type = KnowledgeReuseEvent.ReuseType.VERIFICATION_CONTEXT
        with self.assertRaises(ValidationError):
            event.save(update_fields=["reuse_type"])
        event.refresh_from_db()
        self.assertEqual(event.reuse_type, KnowledgeReuseEvent.ReuseType.USER_RESPONSE)

    def test_changing_fact_check_then_saving_is_rejected(self):
        event = self.record()
        other = self.make_publication(claim=self.target_claim, organization=self.other_organization)
        event.fact_check = other
        with self.assertRaises(ValidationError):
            event.save()
        event.refresh_from_db()
        self.assertEqual(event.fact_check, self.fact_check)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))

    def test_changing_metadata_then_saving_is_rejected(self):
        event = self.record(metadata={"source": "TEST"})
        event.metadata["source"] = "CHANGED"
        with self.assertRaises(ValidationError):
            event.save()
        event.refresh_from_db()
        self.assertEqual(event.metadata, {"source": "TEST"})

    def test_changing_snapshots_then_saving_is_rejected(self):
        event = self.record(target_claim=self.target_claim)
        event.source_organization_id_snapshot = "rewritten-source"
        event.target_claim_id_snapshot = "rewritten-target"
        with self.assertRaises(ValidationError):
            event.save()
        event.refresh_from_db()
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
        self.assertEqual(event.target_claim_id_snapshot, str(self.target_claim.pk))

    def test_event_instance_delete_is_rejected(self):
        event = self.record()
        with self.assertRaisesMessage(ValidationError, "durable"):
            event.delete()
        self.assertTrue(KnowledgeReuseEvent.objects.filter(pk=event.pk).exists())

    def test_target_claim_deletion_nulls_fk_without_erasing_snapshots(self):
        target_id = str(self.target_claim.pk)
        event = self.record(target_claim=self.target_claim)
        self.target_claim.delete()
        event.refresh_from_db()
        self.assertIsNone(event.target_claim)
        self.assertEqual(event.target_claim_id_snapshot, target_id)
        self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))

    def test_changed_source_organization_relationship_does_not_rewrite_event_snapshot(self):
        event = self.record(target_claim=self.target_claim)
        # Deliberately simulate mutable-relationship changes using narrow updates;
        # no production publication mutation rules are relaxed for this test.
        for organization in (self.other_organization, None):
            with self.subTest(organization=organization):
                OfficialFactCheck.objects.filter(pk=self.fact_check.pk).update(organization=organization)
                self.fact_check.refresh_from_db()
                event.refresh_from_db()
                self.assertEqual(self.fact_check.organization, organization)
                self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
                self.assertEqual(event.target_claim_id_snapshot, str(self.target_claim.pk))

    def test_reused_fact_check_fk_protects_exact_publication_row(self):
        event = self.record()
        with self.assertRaises(ProtectedError) as error:
            self.fact_check.delete()
        self.assertIn(event, error.exception.protected_objects)
        self.assertTrue(OfficialFactCheck.objects.filter(pk=self.fact_check.pk).exists())

    def test_transaction_rollback_removes_new_reuse_event(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                event = self.record(target_claim=self.target_claim)
                self.assertEqual(event.source_organization_id_snapshot, str(self.organization.pk))
                raise RuntimeError("force rollback")
        self.assertFalse(KnowledgeReuseEvent.objects.exists())

    def test_historical_blank_snapshots_are_not_reconstructed_from_surviving_relationships(self):
        # Direct insertion represents a pre-4M.2-A row, with current relationships
        # deliberately available but no durable event-local attribution.
        event = KnowledgeReuseEvent.objects.create(
            fact_check=self.fact_check, target_claim=self.target_claim, triggered_by=self.actor,
            reuse_type=KnowledgeReuseEvent.ReuseType.USER_RESPONSE,
            match_method=KnowledgeReuseEvent.MatchMethod.CLAIM_CACHE,
            metadata={"source": "HISTORICAL"},
        )
        event.refresh_from_db()
        self.assertEqual(event.source_organization_id_snapshot, "")
        self.assertEqual(event.target_claim_id_snapshot, "")
        self.record(target_claim=self.target_claim)
        event.refresh_from_db()
        self.assertEqual(event.source_organization_id_snapshot, "")
        self.assertEqual(event.target_claim_id_snapshot, "")


class KnowledgeReuseAttributionContractTests(SimpleTestCase):
    def test_query_fingerprint_normalizes_whitespace_casefolds_and_hashes_with_sha256(self):
        expected = hashlib.sha256(b"strasse private query").hexdigest()
        self.assertEqual(build_query_fingerprint("  Stra\u00dfe\t Private\n QUERY  "), expected)
        self.assertEqual(build_query_fingerprint("STRASSE private query"), expected)
        for query_text in (None, "", " \t\n", 123):
            with self.subTest(query_text=query_text):
                self.assertIsNone(build_query_fingerprint(query_text))

    def test_exact_existing_reuse_choices_exclude_public_page_views(self):
        self.assertEqual(KnowledgeReuseEvent.ReuseType.choices, [
            ("USER_RESPONSE", "User-Facing Reuse"),
            ("VERIFICATION_CONTEXT", "Verification Context Reuse"),
        ])

    def test_exact_existing_match_method_choices(self):
        self.assertEqual(KnowledgeReuseEvent.MatchMethod.choices, [
            ("EXACT_TEXT", "Exact Text Match"), ("SEMANTIC", "Semantic Match"),
            ("FULL_TEXT", "Full-Text Match"), ("CLAIM_CACHE", "Claim Cache Match"),
        ])

    def test_only_two_attribution_snapshots_exist_without_new_person_or_content_fields(self):
        self.assertEqual({field.name for field in KnowledgeReuseEvent._meta.fields}, {
            "id", "fact_check", "target_claim", "triggered_by", "reuse_type", "match_method",
            "similarity_score", "query_fingerprint", "metadata", "created_at",
            "source_organization_id_snapshot", "target_claim_id_snapshot",
        })
        for name, indexed in (("source_organization_id_snapshot", True),
                              ("target_claim_id_snapshot", False)):
            with self.subTest(name=name):
                field = KnowledgeReuseEvent._meta.get_field(name)
                self.assertIsInstance(field, models.CharField)
                self.assertEqual(field.max_length, 255)
                self.assertTrue(field.blank)
                self.assertFalse(field.null)
                self.assertEqual(field.db_index, indexed)
                self.assertFalse(field.has_default())

    def test_existing_foreign_key_deletion_behaviors_are_preserved(self):
        for name, expected in (("fact_check", models.PROTECT),
                               ("target_claim", models.SET_NULL),
                               ("triggered_by", models.SET_NULL)):
            with self.subTest(name=name):
                self.assertIs(KnowledgeReuseEvent._meta.get_field(name).remote_field.on_delete, expected)

    def test_migration_is_only_two_add_fields_with_blank_one_time_historical_values(self):
        migration = import_module("api.migrations.0066_knowledgereuseevent_attribution_snapshots").Migration
        self.assertEqual(migration.dependencies, [("api", "0065_accountabilityevent_actor_id_snapshot")])
        self.assertEqual(len(migration.operations), 2)
        self.assertEqual([operation.name for operation in migration.operations], [
            "source_organization_id_snapshot", "target_claim_id_snapshot",
        ])
        for operation in migration.operations:
            with self.subTest(name=operation.name):
                self.assertIs(type(operation), migrations.AddField)
                self.assertEqual(operation.model_name, "knowledgereuseevent")
                self.assertFalse(operation.preserve_default)
                self.assertEqual(operation.field.default, "")
                self.assertEqual(operation.field.max_length, 255)
                self.assertTrue(operation.field.blank)
                self.assertEqual(operation.field.db_index,
                                 operation.name == "source_organization_id_snapshot")
