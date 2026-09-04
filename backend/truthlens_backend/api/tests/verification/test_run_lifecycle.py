from django.contrib.auth.models import User
from django.test import TestCase

from api.models import Claim, VerificationRun
from api.verification.runs import (
    InvalidVerificationRunTransition,
    abstain_verification_run,
    cancel_verification_run,
    complete_verification_run,
    create_verification_run,
    fail_verification_run,
    start_verification_run,
)


class VerificationRunLifecycleTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Example claim.",
        )

        self.user = User.objects.create_user(
            username="verification-user",
            password="test-password",
        )

    def test_create_verification_run_is_pending(
        self,
    ):
        run = create_verification_run(
            self.claim,
            triggered_by=self.user,
            pipeline_version="test-2.0.0",
        )

        self.assertEqual(
            run.status,
            VerificationRun.Status.PENDING,
        )
        self.assertEqual(
            run.claim,
            self.claim,
        )
        self.assertEqual(
            run.triggered_by,
            self.user,
        )
        self.assertEqual(
            run.pipeline_version,
            "test-2.0.0",
        )
        self.assertIsNone(run.started_at)
        self.assertIsNone(run.completed_at)

    def test_start_transitions_pending_to_running(
        self,
    ):
        run = create_verification_run(self.claim)

        run = start_verification_run(run)

        self.assertEqual(
            run.status,
            VerificationRun.Status.RUNNING,
        )
        self.assertIsNotNone(run.started_at)
        self.assertIsNone(run.completed_at)

    def test_complete_transitions_running_to_completed(
        self,
    ):
        run = start_verification_run(create_verification_run(self.claim))

        run = complete_verification_run(run)

        self.assertEqual(
            run.status,
            VerificationRun.Status.COMPLETED,
        )
        self.assertIsNotNone(run.completed_at)

    def test_abstain_transitions_running_to_abstained(
        self,
    ):
        run = start_verification_run(create_verification_run(self.claim))

        run = abstain_verification_run(run)

        self.assertEqual(
            run.status,
            VerificationRun.Status.ABSTAINED,
        )
        self.assertIsNotNone(run.completed_at)

    def test_fail_records_failure_metadata(
        self,
    ):
        run = start_verification_run(create_verification_run(self.claim))

        run = fail_verification_run(
            run,
            failure_stage="gfc_search",
            failure_code="PROVIDER_ERROR",
            failure_message=("Google Fact Check unavailable."),
        )

        self.assertEqual(
            run.status,
            VerificationRun.Status.FAILED,
        )
        self.assertIsNotNone(run.completed_at)
        self.assertEqual(
            run.failure_stage,
            "gfc_search",
        )
        self.assertEqual(
            run.failure_code,
            "PROVIDER_ERROR",
        )
        self.assertEqual(
            run.failure_message,
            ("Google Fact Check unavailable."),
        )

    def test_pending_run_can_be_cancelled(
        self,
    ):
        run = create_verification_run(self.claim)

        run = cancel_verification_run(run)

        self.assertEqual(
            run.status,
            VerificationRun.Status.CANCELLED,
        )
        self.assertIsNotNone(run.completed_at)

    def test_running_run_can_be_cancelled(
        self,
    ):
        run = start_verification_run(create_verification_run(self.claim))

        run = cancel_verification_run(run)

        self.assertEqual(
            run.status,
            VerificationRun.Status.CANCELLED,
        )
        self.assertIsNotNone(run.completed_at)

    def test_completed_run_cannot_be_started_again(
        self,
    ):
        run = complete_verification_run(
            start_verification_run(create_verification_run(self.claim))
        )

        with self.assertRaises(InvalidVerificationRunTransition):
            start_verification_run(run)

    def test_pending_run_cannot_be_completed(
        self,
    ):
        run = create_verification_run(self.claim)

        with self.assertRaises(InvalidVerificationRunTransition):
            complete_verification_run(run)

    def test_failed_run_is_terminal(
        self,
    ):
        run = fail_verification_run(
            start_verification_run(create_verification_run(self.claim)),
            failure_stage="runtime",
            failure_code="TEST_FAILURE",
        )

        with self.assertRaises(InvalidVerificationRunTransition):
            complete_verification_run(run)

    def test_cancel_clears_failure_metadata(
        self,
    ):
        run = create_verification_run(self.claim)

        run.failure_stage = "old_stage"
        run.failure_code = "OLD_ERROR"
        run.failure_message = "Old failure."
        run.save(
            update_fields=[
                "failure_stage",
                "failure_code",
                "failure_message",
            ]
        )

        run = cancel_verification_run(run)

        self.assertEqual(
            run.status,
            VerificationRun.Status.CANCELLED,
        )
        self.assertIsNone(run.failure_stage)
        self.assertIsNone(run.failure_code)
        self.assertIsNone(run.failure_message)
