from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from api.trust_score_hardening_experiments import (
    BASELINE_DYNAMIC,
    SNAPSHOT_CONTRIBUTOR_GATE,
    SNAPSHOT_EVIDENCE_SHARE,
    SNAPSHOT_ONLY,
    VoterObservation,
    build_hardening_experiment_report,
    effective_vote_weight,
    observed_evidence_share,
)


class TrustScoreHardeningExperimentTests(SimpleTestCase):
    def test_observed_evidence_share_uses_existing_beta_prior_mass(self):
        self.assertEqual(observed_evidence_share(0), 0.0)
        self.assertAlmostEqual(
            observed_evidence_share(3),
            3 / 7,
        )
        self.assertAlmostEqual(
            observed_evidence_share(10),
            10 / 14,
        )
        self.assertAlmostEqual(
            observed_evidence_share(25),
            25 / 29,
        )

    def test_snapshot_evidence_share_removes_fresh_account_influence(self):
        fresh = VoterObservation(
            name="fresh",
            snapshot_score=50.0,
            current_score=50.0,
            resolved_actions=0,
            validated_actions=0,
        )

        self.assertEqual(
            effective_vote_weight(
                fresh,
                SNAPSHOT_EVIDENCE_SHARE,
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
            by_policy[SNAPSHOT_EVIDENCE_SHARE.key]["stable"],
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

    def test_evidence_share_blocks_fresh_attack_but_preserves_established_signal(self):
        report = build_hardening_experiment_report()
        policy = next(
            row
            for row in report["vote_policy_comparison"]["policies"]
            if row["policy"] == SNAPSHOT_EVIDENCE_SHARE.key
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
            "snapshot_evidence_share",
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
