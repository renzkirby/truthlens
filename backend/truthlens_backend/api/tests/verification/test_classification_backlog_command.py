from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from api.models import (
    Claim, ClaimInvestigationClassification, Thread, VerificationAssignment,
)


class ClassificationBacklogCommandTests(TestCase):
    def setUp(self):
        user = User.objects.create_user(username="classifier-backlog-author")
        self.candidate = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Scientists verified laboratory experiments using independent trials.",
        )
        Thread.objects.create(claim=self.candidate, author=user)
        VerificationAssignment.objects.create(
            claim=self.candidate,
            status=VerificationAssignment.Status.AVAILABLE,
        )
        self.no_thread = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT, context_text="Other data from a science lab."
        )
        VerificationAssignment.objects.create(
            claim=self.no_thread,
            status=VerificationAssignment.Status.AVAILABLE,
        )
        self.already_classified = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Technology products require careful assessment.",
        )
        Thread.objects.create(claim=self.already_classified, author=user)
        VerificationAssignment.objects.create(
            claim=self.already_classified,
            status=VerificationAssignment.Status.AVAILABLE,
        )
        ClaimInvestigationClassification.objects.create(
            claim=self.already_classified,
            domains=["TECHNOLOGY"],
            rationale="Pre-existing authoritative classification.",
        )

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.management.commands.queue_investigation_classifications.dispatch_classification_task")
    def test_dry_run_never_dispatches(self, dispatch):
        out = StringIO()
        call_command("queue_investigation_classifications", stdout=out)
        self.assertIn("DRY RUN: 1 eligible", out.getvalue())
        dispatch.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.management.commands.queue_investigation_classifications.dispatch_classification_task")
    def test_enqueue_only_open_unclassified_community_claim(self, dispatch):
        dispatch.return_value = True
        out = StringIO()
        call_command("queue_investigation_classifications", enqueue=True, stdout=out)
        dispatch.assert_called_once_with(self.candidate.pk)
        self.assertIn("Queued 1 of 1", out.getvalue())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    def test_off_mode_cannot_enqueue(self):
        with self.assertRaises(CommandError):
            call_command("queue_investigation_classifications", enqueue=True)

    def test_limit_must_be_bounded(self):
        for limit in (0, -1, 1001):
            with self.subTest(limit=limit), self.assertRaises(CommandError):
                call_command("queue_investigation_classifications", limit=limit)
