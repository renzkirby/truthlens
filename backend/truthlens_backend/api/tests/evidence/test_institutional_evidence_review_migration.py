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
)


migration_module = import_module(
    "api.migrations.0096_institutional_evidence_review_provenance"
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
        reviewed_at = timezone.now() - timezone.timedelta(days=30)
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
