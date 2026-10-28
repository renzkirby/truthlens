from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from api.models import (
    Claim,
    ClaimInvestigationClassification,
    InvestigationClassificationAssessment,
    Thread,
    VerificationAssignment,
)


class CommunityClassificationBackfillCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="community-backfill-author")

        self.candidate = self._community_claim(
            "Scientists verified a new laboratory result using repeated trials."
        )
        VerificationAssignment.objects.create(
            claim=self.candidate,
            status=VerificationAssignment.Status.AVAILABLE,
        )

        self.second_candidate = self._community_claim(
            "A technology company announced a new security update for its users."
        )

        self.no_thread = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="A saved claim that never entered the Community feed.",
        )

        self.too_short = self._community_claim("Too short.")

        self.too_long = self._community_claim("A" * 2401)

        self.active = self._community_claim(
            "An active investigation must not be historically reclassified."
        )
        VerificationAssignment.objects.create(
            claim=self.active,
            status=VerificationAssignment.Status.ACTIVE,
        )

        self.completed = self._community_claim(
            "A completed investigation must not be historically reclassified."
        )
        VerificationAssignment.objects.create(
            claim=self.completed,
            status=VerificationAssignment.Status.COMPLETED,
        )

        self.previously_assessed = self._community_claim(
            "A previous classifier assessment requires a separate retry decision."
        )
        InvestigationClassificationAssessment.objects.create(
            claim=self.previously_assessed,
            status=InvestigationClassificationAssessment.Status.FAILED,
            reason_code="PROVIDER_UNAVAILABLE",
            classifier_version="v5-primary-unique-domains",
            input_fingerprint="fixture",
        )

        self.already_classified = self._community_claim(
            "An authoritative technology classification already exists."
        )
        ClaimInvestigationClassification.objects.create(
            claim=self.already_classified,
            domains=["TECHNOLOGY"],
            primary_subject="TECHNOLOGY",
            rationale="Existing authoritative classification.",
            source=ClaimInvestigationClassification.Source.AUTOMATIC,
        )

    def _community_claim(self, context_text):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=context_text,
        )
        Thread.objects.create(claim=claim, author=self.user)
        return claim

    @override_settings(
        INVESTIGATION_CLASSIFICATION_MODE="enforce",
        INVESTIGATION_ROUTING_MODE="off",
    )
    @patch(
        "api.management.commands.backfill_community_classifications."
        "dispatch_classification_task"
    )
    def test_dry_run_reports_backlog_without_dispatching(self, dispatch):
        out = StringIO()

        call_command(
            "backfill_community_classifications",
            limit=25,
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("DRY RUN:", output)
        self.assertIn("unclassified_community=7", output)
        self.assertIn("eligible=2", output)
        self.assertIn("selected=2", output)
        self.assertIn("invalid_context=2", output)
        self.assertIn("blocked_by_assignment=2", output)
        self.assertIn("previous_assessment=1", output)
        dispatch.assert_not_called()

    @override_settings(
        INVESTIGATION_CLASSIFICATION_MODE="enforce",
        INVESTIGATION_ROUTING_MODE="off",
    )
    @patch(
        "api.management.commands.backfill_community_classifications."
        "dispatch_classification_task"
    )
    def test_enqueue_only_dispatches_clean_historical_community_candidates(
        self,
        dispatch,
    ):
        dispatch.return_value = True
        out = StringIO()

        call_command(
            "backfill_community_classifications",
            enqueue=True,
            limit=25,
            stdout=out,
        )

        queued_ids = {call.args[0] for call in dispatch.call_args_list}
        self.assertEqual(
            queued_ids,
            {self.candidate.pk, self.second_candidate.pk},
        )
        self.assertEqual(dispatch.call_count, 2)
        self.assertIn("Queued 2 of 2 selected", out.getvalue())

    @override_settings(
        INVESTIGATION_CLASSIFICATION_MODE="enforce",
        INVESTIGATION_ROUTING_MODE="off",
    )
    @patch(
        "api.management.commands.backfill_community_classifications."
        "dispatch_classification_task"
    )
    def test_limit_caps_only_eligible_claims(self, dispatch):
        dispatch.return_value = True

        call_command(
            "backfill_community_classifications",
            enqueue=True,
            limit=1,
        )

        self.assertEqual(dispatch.call_count, 1)

    @override_settings(
        INVESTIGATION_CLASSIFICATION_MODE="shadow",
        INVESTIGATION_ROUTING_MODE="off",
    )
    def test_enqueue_rejects_non_enforce_classification_mode(self):
        with self.assertRaisesMessage(
            CommandError,
            "INVESTIGATION_CLASSIFICATION_MODE=enforce",
        ):
            call_command(
                "backfill_community_classifications",
                enqueue=True,
            )

    @override_settings(
        INVESTIGATION_CLASSIFICATION_MODE="enforce",
        INVESTIGATION_ROUTING_MODE="enforce",
    )
    def test_enqueue_rejects_routing_enforce(self):
        with self.assertRaisesMessage(
            CommandError,
            "INVESTIGATION_ROUTING_MODE=off",
        ):
            call_command(
                "backfill_community_classifications",
                enqueue=True,
            )

    def test_limit_must_be_small_and_bounded(self):
        for limit in (0, -1, 101):
            with self.subTest(limit=limit), self.assertRaises(CommandError):
                call_command(
                    "backfill_community_classifications",
                    limit=limit,
                )
