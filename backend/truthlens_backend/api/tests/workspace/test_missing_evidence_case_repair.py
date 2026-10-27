from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import (
    Claim,
    EvidenceSubmission,
    ModerationCase,
    Organization,
    Thread,
    VerificationAssignment,
)


repair_migration = import_module(
    "api.migrations.0095_reconcile_missing_evidence_cases"
)


class MissingEvidenceCaseRepairTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="legacy-evidence-repair-user",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Legacy Evidence Repair Partner",
            slug="legacy-evidence-repair-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    def make_evidence(self, *, active_assignment, status="UNVERIFIED"):
        claim = Claim.objects.create(
            context_text=f"Legacy evidence repair claim {Claim.objects.count()}",
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.user,
            caption="Legacy evidence repair thread",
        )
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.user,
            evidence_caption="Legacy evidence without a review case",
            evidence_status=status,
        )
        VerificationAssignment.objects.create(
            claim=claim,
            organization=self.organization if active_assignment else None,
            claimed_by=self.user if active_assignment else None,
            status=(
                VerificationAssignment.Status.ACTIVE
                if active_assignment
                else VerificationAssignment.Status.AVAILABLE
            ),
            claimed_at=timezone.now() if active_assignment else None,
        )
        return evidence

    def run_repair(self):
        repair_migration.reconcile_missing_evidence_cases(apps, None)

    def test_repairs_unverified_evidence_for_active_owned_investigation(self):
        evidence = self.make_evidence(active_assignment=True)

        self.run_repair()

        case = ModerationCase.objects.get(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
        )
        self.assertEqual(case.status, ModerationCase.Status.OPEN)
        self.assertEqual(case.organization_id, self.organization.id)
        event = case.events.get(event_type="CASE_CREATED")
        self.assertEqual(
            event.metadata["legacy_repair"],
            "0095_reconcile_missing_evidence_cases",
        )

    def test_does_not_assign_unclaimed_community_evidence(self):
        evidence = self.make_evidence(active_assignment=False)

        self.run_repair()

        self.assertFalse(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
            ).exists()
        )

    def test_does_not_recreate_existing_terminal_review_history(self):
        evidence = self.make_evidence(active_assignment=True)
        terminal = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            status=ModerationCase.Status.CANCELLED,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )

        self.run_repair()

        self.assertEqual(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
            ).count(),
            1,
        )
        terminal.refresh_from_db()
        self.assertEqual(terminal.status, ModerationCase.Status.CANCELLED)
        self.assertIsNone(terminal.organization_id)

    def test_does_not_create_case_for_already_reviewed_evidence(self):
        evidence = self.make_evidence(
            active_assignment=True,
            status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )

        self.run_repair()

        self.assertFalse(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission=evidence,
            ).exists()
        )
