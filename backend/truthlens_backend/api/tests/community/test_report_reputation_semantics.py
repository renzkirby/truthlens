from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Claim, FlagResolutionLog, Thread, ThreadFlag
from api.trust_score_validation import TrustScenario, simulate_trust_score
from api.trust_service import (
    build_vote_reputation_snapshot,
    calculate_trust_components,
    get_reputation_action_counts,
)


class ReportReputationSemanticsTests(TestCase):
    def setUp(self):
        self.reporter = User.objects.create_user(
            username="report-reputation-reporter",
            email="report-reputation-reporter@example.com",
            password="pass1234",
        )
        self.author = User.objects.create_user(
            username="report-reputation-author",
            email="report-reputation-author@example.com",
            password="pass1234",
        )
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/report-reputation-thread",
            verified_via=Claim.VerificationSource.PENDING,
        )
        self.thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption="Report reputation semantics fixture",
        )

    def _resolution_log(self, *, confirmed, index):
        return FlagResolutionLog.objects.create(
            thread=self.thread,
            flagged_by=self.reporter,
            reason=ThreadFlag.Reason.OTHER,
            notes=f"Report {index}",
            flagged_at=timezone.now(),
            resolved_action=(
                FlagResolutionLog.ResolutionAction.REMOVE
                if confirmed
                else FlagResolutionLog.ResolutionAction.DISMISS
            ),
            is_valid_report=confirmed,
        )

    def test_self_report_is_rejected_by_api(self):
        client = APIClient()
        client.force_authenticate(self.author)

        response = client.post(
            reverse("thread-flag-list"),
            {
                "thread_id": str(self.thread.pk),
                "reason": ThreadFlag.Reason.OTHER,
                "notes": "Self-report should not be accepted.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["detail"],
            "You cannot report your own thread.",
        )
        self.assertFalse(
            ThreadFlag.objects.filter(
                thread=self.thread,
                flagged_by=self.author,
            ).exists()
        )

    def test_historical_confirmed_self_report_does_not_build_reputation(self):
        self.thread.status = Thread.Status.REJECTED
        self.thread.save(update_fields=["status"])
        FlagResolutionLog.objects.create(
            thread=self.thread,
            flagged_by=self.author,
            reason=ThreadFlag.Reason.OTHER,
            notes="Historical self-report.",
            flagged_at=timezone.now(),
            resolved_action=FlagResolutionLog.ResolutionAction.REMOVE,
            is_valid_report=True,
        )

        components = calculate_trust_components(self.author)
        counts = get_reputation_action_counts(self.author)
        vote_snapshot = build_vote_reputation_snapshot(self.author)

        self.assertEqual(counts["resolved_actions"], 0)
        self.assertEqual(counts["validated_actions"], 0)
        self.assertEqual(components["resolved_actions"], 0)
        self.assertEqual(components["validated_actions"], 0)
        self.assertEqual(components["history_points"], 0.0)
        self.assertEqual(components["moderation_penalty"], 5.0)
        self.assertEqual(components["trust_score"], 45.0)
        self.assertEqual(vote_snapshot["reputation_weight"], 0.0)

    def test_dismissed_reports_are_neutral_for_trust_score_and_reputation_depth(self):
        before = calculate_trust_components(self.reporter)

        for index in range(10):
            self._resolution_log(confirmed=False, index=index)

        after = calculate_trust_components(self.reporter)
        counts = get_reputation_action_counts(self.reporter)
        vote_snapshot = build_vote_reputation_snapshot(self.reporter)

        self.assertEqual(counts["resolved_actions"], 0)
        self.assertEqual(counts["validated_actions"], 0)
        self.assertEqual(after["resolved_actions"], 0)
        self.assertEqual(after["validated_actions"], 0)
        self.assertEqual(after["contribution_points"], before["contribution_points"])
        self.assertEqual(after["active_contribution_months"], 0)
        self.assertEqual(after["history_points"], 0.0)
        self.assertEqual(after["trust_score"], before["trust_score"])
        self.assertEqual(after["confidence"]["key"], "PROVISIONAL")
        self.assertEqual(vote_snapshot["resolved_actions"], 0)
        self.assertEqual(vote_snapshot["validated_actions"], 0)
        self.assertEqual(vote_snapshot["reputation_weight"], 0.0)

    def test_confirmed_report_remains_a_positive_reputation_action(self):
        self._resolution_log(confirmed=True, index=1)

        components = calculate_trust_components(self.reporter)
        counts = get_reputation_action_counts(self.reporter)

        self.assertEqual(counts["resolved_actions"], 1)
        self.assertEqual(counts["validated_actions"], 1)
        self.assertEqual(components["resolved_actions"], 1)
        self.assertEqual(components["validated_actions"], 1)
        self.assertGreater(components["contribution_points"], 0.0)
        self.assertEqual(components["active_contribution_months"], 1)
        self.assertEqual(components["history_points"], 1.0)
        self.assertGreater(components["trust_score"], 50.0)

    def test_dismissed_reports_do_not_change_existing_confirmed_report_reputation(self):
        self._resolution_log(confirmed=True, index=0)
        confirmed_only = calculate_trust_components(self.reporter)

        for index in range(1, 11):
            self._resolution_log(confirmed=False, index=index)

        with_dismissed = calculate_trust_components(self.reporter)

        for field in (
            "resolved_actions",
            "validated_actions",
            "smoothed_accuracy",
            "contribution_points",
            "active_contribution_months",
            "history_points",
            "trust_score",
        ):
            self.assertEqual(
                with_dismissed[field],
                confirmed_only[field],
                msg=f"Dismissed reports changed reputation field: {field}",
            )

    def test_validation_simulator_models_dismissed_reports_as_neutral(self):
        result = simulate_trust_score(
            TrustScenario(
                name="dismissed_reports_are_neutral",
                dismissed_reports=25,
            )
        )

        self.assertEqual(result["resolved_actions"], 0)
        self.assertEqual(result["validated_actions"], 0)
        self.assertEqual(result["contribution_points"], 0.0)
        self.assertEqual(result["trust_score"], 50.0)
        self.assertEqual(result["confidence"], "Provisional")
