"""Compare candidate Trust Score hardening policies offline."""

import json

from django.core.management.base import BaseCommand

from api.trust_score_hardening_experiments import (
    build_hardening_experiment_report,
)


class Command(BaseCommand):
    help = (
        "Offline comparison of Trust Score hardening candidates. "
        "No database reads/writes and no production behavior changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the complete hardening comparison as JSON.",
        )

    def handle(self, *args, **options):
        report = build_hardening_experiment_report()

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    report,
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        comparison = report["vote_policy_comparison"]
        self.stdout.write("TRUTHLENS TRUST SCORE HARDENING EXPERIMENTS")
        self.stdout.write(
            "Promotion baseline: "
            f"{comparison['promotion_baseline']['trust_score']:.2f} "
            f"{comparison['promotion_baseline']['current_rank']}"
        )
        self.stdout.write(
            "Demotion baseline: "
            f"{comparison['demotion_baseline']['trust_score']:.2f} "
            f"{comparison['demotion_baseline']['current_rank']}"
        )
        self.stdout.write("")

        for policy in comparison["policies"]:
            self.stdout.write(
                f"POLICY {policy['policy']} — {policy['label']}"
            )
            for row in policy["archetypes"]:
                promotion = row["promotion"]["minimum_votes"]
                demotion = row["demotion"]["minimum_votes"]
                self.stdout.write(
                    f"  {row['voter']:24} "
                    f"weight={row['effective_weight']:.4f} "
                    f"promote={promotion if promotion is not None else '>100'} "
                    f"demote={demotion if demotion is not None else '>100'}"
                )
            self.stdout.write("")

        self.stdout.write("HISTORICAL VOTE STABILITY")
        for row in report["historical_vote_stability"]:
            status = "PASS" if row["stable"] else "FAIL"
            self.stdout.write(
                f"{status:4} {row['policy']}: "
                f"before={row['before_points']:.4f} "
                f"after={row['after_points']:.4f}"
            )

        self.stdout.write("")
        self.stdout.write("PROVISIONAL POLICY")
        for row in report["provisional_policy_comparison"]:
            self.stdout.write(
                f"{row['scenario']:28} "
                f"score={row['score']:.2f} "
                f"current={row['current_rank']} "
                f"positive_gate={row['positive_evidence_gate_rank']}"
            )

        self.stdout.write("")
        self.stdout.write("LEGITIMATE INFLUENCE")
        for row in report["legitimate_influence_comparison"]:
            self.stdout.write(
                f"{row['policy']:28} "
                f"{row['voter']:24} "
                f"weight={row['effective_weight']:.4f} "
                f"five_upvote_points={row['five_upvote_points']:.2f}"
            )

        self.stdout.write("")
        self.stdout.write(
            "OFFLINE ONLY; NO DATABASE READS; NO DATABASE WRITES; "
            "NO PRODUCTION SCORE CHANGES."
        )
