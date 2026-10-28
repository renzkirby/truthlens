from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from api.trust_score_validation import (
    DEFAULT_CALIBRATION,
    TrustScenario,
    attack_results,
    build_validation_report,
    invariant_results,
    simulate_trust_score,
)


class TrustScoreValidationTests(SimpleTestCase):
    def test_neutral_user_starts_at_50(self):
        result = simulate_trust_score(
            TrustScenario(name="neutral"),
        )

        self.assertEqual(result["trust_score"], 50.0)
        self.assertEqual(result["current_rank"], "Provisional")

    def test_bayesian_smoothing_limits_one_action_swing(self):
        successful = simulate_trust_score(
            TrustScenario(
                name="success",
                verified_evidence=1,
            )
        )
        failed = simulate_trust_score(
            TrustScenario(
                name="failure",
                rejected_evidence=1,
            )
        )

        self.assertEqual(successful["contribution_points"], 5.0)
        self.assertEqual(failed["contribution_points"], -5.0)

    def test_fresh_vote_cluster_can_cross_current_rank_boundary(self):
        baseline = simulate_trust_score(
            TrustScenario(
                name="baseline",
                verified_evidence=18,
                rejected_evidence=7,
                active_months=5,
            )
        )
        clustered = simulate_trust_score(
            TrustScenario(
                name="clustered",
                verified_evidence=18,
                rejected_evidence=7,
                upvote_trust_scores=(50.0,) * 10,
                active_months=5,
            )
        )

        self.assertEqual(
            baseline["current_rank"],
            "Contributor",
        )
        self.assertEqual(
            clustered["current_rank"],
            "Trusted Contributor",
        )
        self.assertEqual(baseline["trust_score"], 64.48)
        self.assertEqual(clustered["trust_score"], 75.49)

    def test_dynamic_voter_score_changes_historical_vote_result(self):
        original = simulate_trust_score(
            TrustScenario(
                name="original",
                verified_evidence=10,
                upvote_trust_scores=(50.0,) * 5,
                active_months=2,
            )
        )
        reinterpreted = simulate_trust_score(
            TrustScenario(
                name="reinterpreted",
                verified_evidence=10,
                upvote_trust_scores=(90.0,) * 5,
                active_months=2,
            )
        )

        self.assertEqual(original["trust_score"], 76.41)
        self.assertEqual(reinterpreted["trust_score"], 77.85)
        self.assertNotEqual(
            original["trust_score"],
            reinterpreted["trust_score"],
        )

    def test_valid_reports_and_verified_evidence_are_currently_equivalent(self):
        evidence = simulate_trust_score(
            TrustScenario(
                name="evidence",
                verified_evidence=25,
                active_months=5,
            )
        )
        reports = simulate_trust_score(
            TrustScenario(
                name="reports",
                valid_reports=25,
                active_months=5,
            )
        )

        self.assertEqual(
            evidence["trust_score"],
            reports["trust_score"],
        )
        self.assertEqual(
            evidence["current_rank"],
            reports["current_rank"],
        )

    def test_current_invariant_baseline_has_two_known_failures(self):
        checks = invariant_results()["checks"]
        failed = {
            check["id"]
            for check in checks
            if not check["passed"]
        }

        self.assertEqual(
            failed,
            {"I8", "I9"},
        )

    def test_current_attack_threshold_is_five_fresh_account_votes(self):
        attacks = attack_results()

        promotion = next(
            row
            for row in attacks["promotion_probe"]["thresholds"]
            if row["voter_trust_score"] == 50.0
        )
        demotion = next(
            row
            for row in attacks["demotion_probe"]["thresholds"]
            if row["voter_trust_score"] == 50.0
        )

        self.assertEqual(promotion["minimum_votes"], 5)
        self.assertEqual(
            promotion["to_rank"],
            "Trusted Contributor",
        )
        self.assertEqual(demotion["minimum_votes"], 5)
        self.assertEqual(
            demotion["to_rank"],
            "Contributor",
        )

    def test_validation_report_includes_sensitivity_rows(self):
        report = build_validation_report()

        self.assertEqual(
            report["calibration"]["prior_success"],
            DEFAULT_CALIBRATION.prior_success,
        )
        self.assertGreaterEqual(
            len(report["sensitivity"]),
            18,
        )

    def test_management_command_is_offline_and_reports_failures(self):
        output = StringIO()

        call_command(
            "analyze_trust_score_model",
            stdout=output,
        )

        rendered = output.getvalue()
        self.assertIn(
            "TRUTHLENS TRUST SCORE PRE-HARDENING BASELINE",
            rendered,
        )
        self.assertIn(
            "FAIL I8",
            rendered,
        )
        self.assertIn(
            "FAIL I9",
            rendered,
        )
        self.assertIn(
            "NO DATABASE READS",
            rendered,
        )
