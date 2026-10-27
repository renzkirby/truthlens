from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import (
    Claim,
    EvidenceReviewDecision,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
    Organization,
    Thread,
    VerificationAssignment,
)


migration_module = import_module(
    "api.migrations.0096_institutional_evidence_review_provenance"
)
handoff_migration_module = import_module(
    "api.migrations.0097_reconcile_active_successor_evidence_handoffs"
)


class InstitutionalEvidenceReviewMigrationTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="migration-review-contributor",
        )
        self.reviewer = User.objects.create_user(
            username="migration-reviewer",
        )
        self.organization = Organization.objects.create(
            name="Migration Review Partner",
            slug="migration-review-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.claim = Claim.objects.create(
            context_text="Historical institutional review migration claim.",
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Historical review discussion",
        )

    def test_backfills_resolved_review_with_original_provenance(self):
        reviewed_at = timezone.now() - timedelta(days=30)
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            verified_by=self.reviewer,
            verified_at=reviewed_at,
        )
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=EvidenceSubmission.EvidenceStatus.VERIFIED,
            resolution_summary="Historical evidence review.",
            resolved_by=self.reviewer,
            resolved_at=reviewed_at,
        )
        event = ModerationEvent.objects.create(
            case=case,
            actor=self.reviewer,
            event_type=ModerationEvent.EventType.EVIDENCE_VERIFIED,
            reason_code=EvidenceSubmission.EvidenceStatus.VERIFIED,
            notes="Historical evidence review.",
        )
        ModerationEvent.objects.filter(pk=event.pk).update(created_at=reviewed_at)

        migration_module.backfill_institutional_evidence_reviews(apps, None)

        decision = EvidenceReviewDecision.objects.get(moderation_case=case)
        self.assertEqual(decision.evidence_submission_id, evidence.pk)
        self.assertEqual(decision.organization_id, self.organization.pk)
        self.assertEqual(decision.reviewed_by_id, self.reviewer.pk)
        self.assertEqual(
            decision.decision_type,
            EvidenceReviewDecision.DecisionType.INDEPENDENT_REVIEW,
        )
        self.assertEqual(
            decision.disposition,
            EvidenceReviewDecision.Disposition.VERIFIED,
        )
        self.assertEqual(decision.notes, "Historical evidence review.")
        self.assertEqual(decision.organization_name_snapshot, self.organization.name)
        self.assertEqual(
            decision.reviewer_username_snapshot,
            self.reviewer.username,
        )
        self.assertEqual(decision.reviewed_at, reviewed_at)

        migration_module.backfill_institutional_evidence_reviews(apps, None)
        self.assertEqual(
            EvidenceReviewDecision.objects.filter(moderation_case=case).count(),
            1,
        )

    def test_ignores_nonresolved_and_unowned_cases(self):
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        active = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            status=ModerationCase.Status.OPEN,
        )

        migration_module.backfill_institutional_evidence_reviews(apps, None)

        self.assertFalse(
            EvidenceReviewDecision.objects.filter(moderation_case=active).exists()
        )


    def test_does_not_recast_factual_correction_review_as_ordinary_basis(self):
        reviewed_at = timezone.now() - timedelta(days=10)
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
            verified_by=self.reviewer,
            verified_at=reviewed_at,
            rejection_reason=EvidenceSubmission.RejectionReason.OTHER,
        )
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=EvidenceSubmission.EvidenceStatus.REJECTED,
            resolution_summary="Correction-specific evidence review.",
            resolved_by=self.reviewer,
            resolved_at=reviewed_at,
        )
        ModerationEvent.objects.create(
            case=case,
            actor=self.reviewer,
            event_type=ModerationEvent.EventType.EVIDENCE_REJECTED,
            reason_code=EvidenceSubmission.RejectionReason.OTHER,
            notes="Correction-specific evidence review.",
            metadata={
                "correction_request_id": "00000000-0000-0000-0000-000000000001",
                "correction_case_id": "00000000-0000-0000-0000-000000000002",
            },
        )

        migration_module.backfill_institutional_evidence_reviews(apps, None)

        self.assertFalse(
            EvidenceReviewDecision.objects.filter(
                moderation_case=case,
            ).exists()
        )


class ActiveSuccessorEvidenceHandoffMigrationTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="handoff-migration-contributor",
        )
        self.reviewer_a = User.objects.create_user(
            username="handoff-migration-reviewer-a",
        )
        self.reviewer_b = User.objects.create_user(
            username="handoff-migration-reviewer-b",
        )
        self.org_a = Organization.objects.create(
            name="Handoff Migration Partner A",
            slug="handoff-migration-partner-a",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ENDED,
        )
        self.org_b = Organization.objects.create(
            name="Handoff Migration Partner B",
            slug="handoff-migration-partner-b",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.claim = Claim.objects.create(
            context_text="Pre-feature successor assignment claim.",
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Historical successor handoff discussion",
        )
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim,
            organization=self.org_b,
            claimed_by=self.reviewer_b,
            status=VerificationAssignment.Status.ACTIVE,
        )

    def _reviewed_evidence(self, *, organization, reviewer, status="VERIFIED"):
        reviewed_at = timezone.now() - timedelta(days=2)
        evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_status=status,
            verified_by=reviewer,
            verified_at=reviewed_at,
            rejection_reason=(
                EvidenceSubmission.RejectionReason.OTHER
                if status == EvidenceSubmission.EvidenceStatus.REJECTED
                else None
            ),
        )
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
            status=ModerationCase.Status.RESOLVED,
            resolution_code=status,
            resolved_by=reviewer,
            resolved_at=reviewed_at,
        )
        EvidenceReviewDecision.objects.create(
            evidence_submission=evidence,
            organization=organization,
            moderation_case=case,
            reviewed_by=reviewer,
            disposition=status,
            rejection_reason=(
                EvidenceSubmission.RejectionReason.OTHER
                if status == EvidenceSubmission.EvidenceStatus.REJECTED
                else None
            ),
            reviewed_at=reviewed_at,
        )
        return evidence

    def test_repairs_preexisting_active_successor_assignment(self):
        evidence = self._reviewed_evidence(
            organization=self.org_a,
            reviewer=self.reviewer_a,
        )

        handoff_migration_module.reconcile_active_successor_evidence_handoffs(
            apps,
            None,
        )

        handoff = ModerationCase.objects.get(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.org_b,
            status=ModerationCase.Status.OPEN,
        )
        event = ModerationEvent.objects.get(
            case=handoff,
            event_type=ModerationEvent.EventType.CASE_CREATED,
        )
        self.assertEqual(
            event.metadata["legacy_repair"],
            "0097_reconcile_active_successor_evidence_handoffs",
        )

        handoff_migration_module.reconcile_active_successor_evidence_handoffs(
            apps,
            None,
        )
        self.assertEqual(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
                status__in=[
                    ModerationCase.Status.OPEN,
                    ModerationCase.Status.IN_REVIEW,
                    ModerationCase.Status.ESCALATED,
                    ModerationCase.Status.REOPENED,
                ],
            ).count(),
            1,
        )

    def test_does_not_create_handoff_when_current_basis_matches(self):
        evidence = self._reviewed_evidence(
            organization=self.org_b,
            reviewer=self.reviewer_b,
        )

        handoff_migration_module.reconcile_active_successor_evidence_handoffs(
            apps,
            None,
        )

        self.assertFalse(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
                status__in=[
                    ModerationCase.Status.OPEN,
                    ModerationCase.Status.IN_REVIEW,
                    ModerationCase.Status.ESCALATED,
                    ModerationCase.Status.REOPENED,
                ],
            ).exists()
        )
