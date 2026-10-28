from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from api.trust_score_hardening_experiments import (
    BASELINE_DYNAMIC,
    SNAPSHOT_CONTRIBUTOR_GATE,
    SNAPSHOT_VALIDATED_HISTORY,
    SNAPSHOT_ONLY,
    VoterObservation,
    build_hardening_experiment_report,
    effective_vote_weight,
    validated_history_factor,
)


class TrustScoreHardeningExperimentTests(SimpleTestCase):
    def test_validated_history_factor_uses_existing_beta_prior_mass(self):
        self.assertEqual(
            validated_history_factor(
                validated_actions=0,
                resolved_actions=0,
            ),
            0.0,
        )
        self.assertAlmostEqual(
            validated_history_factor(
                validated_actions=3,
                resolved_actions=3,
            ),
            3 / 7,
        )
        self.assertAlmostEqual(
            validated_history_factor(
                validated_actions=5,
                resolved_actions=10,
            ),
            5 / 14,
        )
        self.assertAlmostEqual(
            validated_history_factor(
                validated_actions=10,
                resolved_actions=10,
            ),
            10 / 14,
        )
        self.assertEqual(
            validated_history_factor(
                validated_actions=0,
                resolved_actions=25,
            ),
            0.0,
        )

    def test_snapshot_validated_history_removes_fresh_account_influence(self):
        fresh = VoterObservation(
            name="fresh",
            snapshot_score=50.0,
            current_score=50.0,
            snapshot_resolved_actions=0,
            current_resolved_actions=0,
            snapshot_validated_actions=0,
            current_validated_actions=0,
        )

        self.assertEqual(
            effective_vote_weight(
                fresh,
                SNAPSHOT_VALIDATED_HISTORY,
            ),
            0.0,
        )
        self.assertEqual(
            effective_vote_weight(
                fresh,
                SNAPSHOT_CONTRIBUTOR_GATE,
            ),
            0.0,
        )
        self.assertEqual(
            effective_vote_weight(
                fresh,
                SNAPSHOT_ONLY,
            ),
            0.75,
        )

    def test_failed_action_history_cannot_mature_vote_influence(self):
        report = build_hardening_experiment_report()
        policy = next(
            row
            for row in report["vote_policy_comparison"]["policies"]
            if row["policy"] == SNAPSHOT_VALIDATED_HISTORY.key
        )
        failed_history = next(
            row
            for row in policy["archetypes"]
            if row["voter"] == "twenty_five_failures"
        )

        self.assertEqual(
            failed_history["effective_weight"],
            0.0,
        )
        self.assertIsNone(
            failed_history["promotion"]["minimum_votes"],
        )
        self.assertIsNone(
            failed_history["demotion"]["minimum_votes"],
        )

    def test_snapshot_policies_make_historical_vote_weight_stable(self):
        report = build_hardening_experiment_report()
        by_policy = {
            row["policy"]: row
            for row in report["historical_vote_stability"]
        }

        self.assertFalse(
            by_policy[BASELINE_DYNAMIC.key]["stable"],
        )
        self.assertTrue(
            by_policy[SNAPSHOT_ONLY.key]["stable"],
        )
        self.assertTrue(
            by_policy[SNAPSHOT_VALIDATED_HISTORY.key]["stable"],
        )
        self.assertTrue(
            by_policy[SNAPSHOT_CONTRIBUTOR_GATE.key]["stable"],
        )

    def test_snapshot_only_does_not_solve_fresh_account_attack(self):
        report = build_hardening_experiment_report()
        policy = next(
            row
            for row in report["vote_policy_comparison"]["policies"]
            if row["policy"] == SNAPSHOT_ONLY.key
        )
        fresh = next(
            row
            for row in policy["archetypes"]
            if row["voter"] == "fresh"
        )

        self.assertEqual(
            fresh["promotion"]["minimum_votes"],
            5,
        )
        self.assertEqual(
            fresh["demotion"]["minimum_votes"],
            5,
        )

    def test_validated_history_blocks_fresh_attack_but_preserves_established_signal(self):
        report = build_hardening_experiment_report()
        policy = next(
            row
            for row in report["vote_policy_comparison"]["policies"]
            if row["policy"] == SNAPSHOT_VALIDATED_HISTORY.key
        )
        fresh = next(
            row
            for row in policy["archetypes"]
            if row["voter"] == "fresh"
        )
        ten_successes = next(
            row
            for row in policy["archetypes"]
            if row["voter"] == "ten_successes"
        )
        twenty_five = next(
            row
            for row in policy["archetypes"]
            if row["voter"] == "twenty_five_successes"
        )

        self.assertIsNone(
            fresh["promotion"]["minimum_votes"],
        )
        self.assertIsNone(
            fresh["demotion"]["minimum_votes"],
        )
        self.assertEqual(
            ten_successes["promotion"]["minimum_votes"],
            6,
        )
        self.assertEqual(
            twenty_five["promotion"]["minimum_votes"],
            5,
        )

    def test_positive_evidence_gate_keeps_three_failures_provisional(self):
        report = build_hardening_experiment_report()
        rows = {
            row["scenario"]: row
            for row in report["provisional_policy_comparison"]
        }

        self.assertEqual(
            rows["three_failures"]["current_rank"],
            "New Contributor",
        )
        self.assertEqual(
            rows["three_failures"]["positive_evidence_gate_rank"],
            "Provisional",
        )
        self.assertEqual(
            rows["one_success_two_failures"]["positive_evidence_gate_rank"],
            "New Contributor",
        )

    def test_selected_candidate_checks_all_pass(self):
        report = build_hardening_experiment_report()

        self.assertTrue(
            all(
                check["passed"]
                for check in report["selected_candidate_checks"]
            )
        )

    def test_hardening_command_reports_comparison(self):
        output = StringIO()

        call_command(
            "compare_trust_score_hardening",
            stdout=output,
        )

        rendered = output.getvalue()
        self.assertIn(
            "TRUTHLENS TRUST SCORE HARDENING EXPERIMENTS",
            rendered,
        )
        self.assertIn(
            "snapshot_validated_history",
            rendered,
        )
        self.assertIn(
            "SELECTED CANDIDATE CHECKS",
            rendered,
        )
        self.assertIn(
            "PASS H2B",
            rendered,
        )
        self.assertIn(
            "HISTORICAL VOTE STABILITY",
            rendered,
        )
        self.assertIn(
            "NO PRODUCTION SCORE CHANGES",
            rendered,
        )
