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
        self.standalone = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="A saved claim without a thread or assignment.",
        )
        self.active = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="An already assigned claim must not be reclassified.",
        )
        Thread.objects.create(claim=self.active, author=user)
        VerificationAssignment.objects.create(
            claim=self.active,
            status=VerificationAssignment.Status.ACTIVE,
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
        self.assertIn("DRY RUN: 3 unclassified claims with stored text", out.getvalue())
        dispatch.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.management.commands.queue_investigation_classifications.dispatch_classification_task")
    def test_enqueue_includes_standalone_claims_but_excludes_claimed_and_classified(
        self, dispatch,
    ):
        dispatch.return_value = True
        out = StringIO()
        call_command("queue_investigation_classifications", enqueue=True, stdout=out)
        self.assertEqual(dispatch.call_count, 3)
        queued_ids = {call.args[0] for call in dispatch.call_args_list}
        self.assertEqual(
            queued_ids, {self.candidate.pk, self.no_thread.pk, self.standalone.pk}
        )
        self.assertIn("Queued 3 of 3", out.getvalue())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    def test_off_mode_cannot_enqueue(self):
        with self.assertRaises(CommandError):
            call_command("queue_investigation_classifications", enqueue=True)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    def test_backlog_enqueue_rejects_enforce_mode(self):
        with self.assertRaises(CommandError):
            call_command("queue_investigation_classifications", enqueue=True)

    def test_limit_must_be_bounded(self):
        for limit in (0, -1, 1001):
            with self.subTest(limit=limit), self.assertRaises(CommandError):
                call_command("queue_investigation_classifications", limit=limit)
