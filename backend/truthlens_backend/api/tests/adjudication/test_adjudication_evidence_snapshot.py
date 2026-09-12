from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from api.adjudication_service import (
    AdjudicationConflict,
    InvalidAdjudicationDecision,
)
from api.models import (
    AdjudicationDecision,
    AdjudicationDecisionEvidenceSnapshot,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
)
from api.tests.adjudication.test_adjudication_transaction_contract import (
    AdjudicationContractFixtures,
)


class AdjudicationEvidenceSnapshotTests(
    AdjudicationContractFixtures,
    TestCase,
):
    def make_mixed_context(self):
        context = self.make_context(
            evidence_statuses=[
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                EvidenceSubmission.EvidenceStatus.REJECTED,
            ]
        )
        reviewed_at = timezone.now()
        verified, rejected = context["evidence"]

        verified.evidence_caption = None
        verified.evidence_url = None
        verified.verified_by = self.moderator
        verified.verified_at = reviewed_at
        verified.moderator_notes = "Source and claim context were reviewed."
        verified.save(
            update_fields=[
                "evidence_caption",
                "evidence_url",
                "verified_by",
                "verified_at",
                "moderator_notes",
            ]
        )

        rejected.verified_by = self.moderator
        rejected.verified_at = reviewed_at
        rejected.moderator_notes = "The source does not address the claim."
        rejected.rejection_reason = EvidenceSubmission.RejectionReason.IRRELEVANT
        rejected.save(
            update_fields=[
                "verified_by",
                "verified_at",
                "moderator_notes",
                "rejection_reason",
            ]
        )
        return context, reviewed_at

    def test_first_decision_atomically_captures_mixed_evidence_basis(self):
        context, reviewed_at = self.make_mixed_context()

        result = self.issue(
            context,
            verdict=AdjudicationDecision.Verdict.UNVERIFIED,
        )

        decision = result["decision"]
        snapshot = AdjudicationDecisionEvidenceSnapshot.objects.get(
            decision=decision
        )
        records = {record["id"]: record for record in snapshot.evidence_records}
        verified, rejected = context["evidence"]

        self.assertEqual(snapshot.schema_version, 1)
        self.assertIsNotNone(snapshot.captured_at)
        self.assertEqual(snapshot.decision_id, decision.id)
        self.assertEqual(snapshot.claim_id, context["claim"].id)
        self.assertEqual(set(records), {str(verified.id), str(rejected.id)})
        self.assertEqual(
            set(records[str(verified.id)]),
            {
                "id",
                "thread_id",
                "evidence_status",
                "evidence_type",
                "evidence_caption",
                "evidence_url",
                "contributor_id",
                "reviewer_id",
                "submitted_at",
                "reviewed_at",
                "moderator_notes",
                "rejection_reason",
            },
        )

        verified_record = records[str(verified.id)]
        self.assertEqual(
            verified_record["evidence_status"],
            EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        self.assertEqual(verified_record["thread_id"], str(context["thread"].id))
        self.assertEqual(
            verified_record["contributor_id"],
            str(self.contributor.id),
        )
        self.assertEqual(verified_record["reviewer_id"], str(self.moderator.id))
        self.assertEqual(verified_record["reviewed_at"], reviewed_at.isoformat())
        self.assertIsNone(verified_record["evidence_caption"])
        self.assertIsNone(verified_record["evidence_url"])
        self.assertIsNone(verified_record["rejection_reason"])

        rejected_record = records[str(rejected.id)]
        self.assertEqual(
            rejected_record["evidence_status"],
            EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        self.assertEqual(
            rejected_record["rejection_reason"],
            EvidenceSubmission.RejectionReason.IRRELEVANT,
        )
        self.assertEqual(
            rejected_record["moderator_notes"],
            "The source does not address the claim.",
        )

        context["claim"].refresh_from_db()
        self.assertEqual(decision.revision_number, 1)
        self.assertTrue(decision.is_current)
        self.assertEqual(
            context["claim"].final_verdict,
            AdjudicationDecision.Verdict.UNVERIFIED,
        )

    def test_snapshot_does_not_follow_later_live_evidence_changes(self):
        context, _reviewed_at = self.make_mixed_context()
        result = self.issue(context)
        snapshot = result["decision"].evidence_snapshot
        captured_records = snapshot.evidence_records
        evidence = context["evidence"][0]

        EvidenceSubmission.objects.filter(pk=evidence.pk).update(
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
            evidence_caption="Later mutable caption.",
            evidence_url="https://example.com/later-source",
            verified_by_id=self.lead.id,
            verified_at=timezone.now(),
            moderator_notes="Later mutable notes.",
            rejection_reason=EvidenceSubmission.RejectionReason.OTHER,
        )

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.evidence_records, captured_records)

    def test_failed_and_conflicting_decisions_do_not_create_snapshots(self):
        invalid = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        conflict = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.UNVERIFIED]
        )

        with self.assertRaises(InvalidAdjudicationDecision):
            self.issue(invalid, verdict="NOT_A_VERDICT")
        with self.assertRaises(AdjudicationConflict):
            self.issue(conflict)

        self.assertFalse(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision__claim__in=[invalid["claim"], conflict["claim"]]
            ).exists()
        )
        self.assertFalse(
            AdjudicationDecision.objects.filter(
                claim__in=[invalid["claim"], conflict["claim"]]
            ).exists()
        )

    def test_snapshot_failure_rolls_back_the_authoritative_transaction(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        original_event_count = ModerationEvent.objects.filter(
            case=context["case"]
        ).count()

        with patch(
            "api.adjudication_service."
            "AdjudicationDecisionEvidenceSnapshot.objects.create",
            side_effect=RuntimeError("snapshot storage unavailable"),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "snapshot storage unavailable",
            ):
                self.issue(context)

        context["claim"].refresh_from_db()
        context["case"].refresh_from_db()
        context["thread"].refresh_from_db()
        self.assertIsNone(context["claim"].final_verdict)
        self.assertEqual(context["case"].status, ModerationCase.Status.OPEN)
        self.assertIsNone(context["thread"].moderator_verdict)
        self.assertFalse(
            AdjudicationDecision.objects.filter(claim=context["claim"]).exists()
        )
        self.assertFalse(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                claim_id=context["claim"].id
            ).exists()
        )
        self.assertEqual(
            ModerationEvent.objects.filter(case=context["case"]).count(),
            original_event_count,
        )

    def test_legacy_decision_without_snapshot_remains_explicitly_absent(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        legacy = AdjudicationDecision.objects.create(
            claim=context["claim"],
            moderation_case=context["case"],
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="Legacy canonical wording.",
            rationale="Legacy rationale.",
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
            revision_number=1,
            is_current=True,
        )

        self.assertFalse(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision=legacy
            ).exists()
        )
        self.assertFalse(hasattr(legacy, "evidence_snapshot"))

    def test_snapshot_rejects_claim_identity_from_another_decision(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        other_context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        legacy = AdjudicationDecision.objects.create(
            claim=context["claim"],
            moderation_case=context["case"],
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim="Legacy canonical wording.",
            rationale="Legacy rationale.",
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
            revision_number=1,
            is_current=True,
        )

        with self.assertRaisesMessage(
            ValidationError,
            "Snapshot claim identity must match its adjudication decision.",
        ):
            AdjudicationDecisionEvidenceSnapshot.objects.create(
                decision=legacy,
                claim_id=other_context["claim"].id,
                evidence_records=[],
            )

        self.assertFalse(
            AdjudicationDecisionEvidenceSnapshot.objects.filter(
                decision=legacy
            ).exists()
        )

    def test_snapshot_rejects_direct_edits_and_deletion(self):
        context = self.make_context(
            evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED]
        )
        decision = self.issue(context)["decision"]
        snapshot = decision.evidence_snapshot
        snapshot.evidence_records = []

        with self.assertRaises(ValidationError):
            snapshot.save()
        with self.assertRaises(ValidationError):
            snapshot.delete()
        with self.assertRaises(ProtectedError):
            decision.delete()

        snapshot.refresh_from_db()
        self.assertEqual(len(snapshot.evidence_records), 1)
