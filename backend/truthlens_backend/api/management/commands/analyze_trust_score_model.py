"""Analyze the current Trust Score model without database reads or writes."""

import json

from django.core.management.base import BaseCommand

from api.trust_score_validation import build_validation_report


class Command(BaseCommand):
    help = (
        "Offline analysis of the current Trust Score calibration. "
        "No database reads/writes and no external calls."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the complete validation report as JSON.",
        )
        parser.add_argument(
            "--sensitivity",
            action="store_true",
            help="Include parameter sensitivity rows in human-readable output.",
        )

    def handle(self, *args, **options):
        report = build_validation_report()

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    report,
                    indent=2,
                    sort_keys=True,
                )
            )
            return

        calibration = report["calibration"]
        self.stdout.write("TRUTHLENS TRUST SCORE VALIDATION")
        self.stdout.write(
            "CALIBRATION "
            f"base={calibration['base_score']:.0f} "
            f"quality_cap=±{calibration['contribution_points_cap']:.0f} "
            f"community_cap=±{calibration['community_points_cap']:.0f} "
            f"history_cap=+{calibration['history_points_cap']:.0f} "
            f"thread_penalty=-{calibration['rejected_thread_penalty']:.0f}"
        )
        self.stdout.write("")

        self.stdout.write("BASELINE SCENARIOS")
        header = (
            f"{'scenario':38} {'score':>7} {'rank':22} "
            f"{'quality':>8} {'community':>10} {'history':>8} {'penalty':>8}"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for row in report["baseline_scenarios"]:
            self.stdout.write(
                f"{row['name'][:38]:38} "
                f"{row['trust_score']:7.2f} "
                f"{row['current_rank'][:22]:22} "
                f"{row['contribution_points']:8.2f} "
                f"{row['community_points']:10.2f} "
                f"{row['history_points']:8.2f} "
                f"{row['moderation_penalty']:8.2f}"
            )

        self.stdout.write("")
        self.stdout.write("INVARIANTS")
        passed = 0
        failed = 0
        for check in report["invariants"]["checks"]:
            status = "PASS" if check["passed"] else "FAIL"
            if check["passed"]:
                passed += 1
            else:
                failed += 1
            self.stdout.write(
                f"{status:4} {check['id']} {check['name']}: {check['detail']}"
            )

        architectural = report["invariants"]["non_numeric_invariant"]
        self.stdout.write(
            f"INFO {architectural['id']} {architectural['name']}: "
            f"{architectural['detail']}"
        )
        self.stdout.write(
            f"NUMERIC_INVARIANTS passed={passed} failed={failed}"
        )

        self.stdout.write("")
        self.stdout.write("ATTACK PROBES")
        promotion = report["attacks"]["promotion_probe"]
        demotion = report["attacks"]["demotion_probe"]
        self.stdout.write(
            "Promotion baseline: "
            f"{promotion['baseline']['trust_score']:.2f} "
            f"{promotion['baseline']['current_rank']}"
        )
        for row in promotion["thresholds"]:
            self.stdout.write(
                "  fresh/upvote voter_trust="
                f"{row['voter_trust_score']:.0f} "
                f"minimum_votes={row['minimum_votes']} "
                f"result={row['score']:.2f}/{row['to_rank']}"
            )
        self.stdout.write(
            "Demotion baseline: "
            f"{demotion['baseline']['trust_score']:.2f} "
            f"{demotion['baseline']['current_rank']}"
        )
        for row in demotion["thresholds"]:
            self.stdout.write(
                "  downvote voter_trust="
                f"{row['voter_trust_score']:.0f} "
                f"minimum_votes={row['minimum_votes']} "
                f"result={row['score']:.2f}/{row['to_rank']}"
            )

        self.stdout.write("")
        self.stdout.write("DIAGNOSTICS")
        for name, diagnostic in report["diagnostics"].items():
            self.stdout.write(
                f"{name}: {diagnostic['finding']}"
            )

        if options["sensitivity"]:
            self.stdout.write("")
            self.stdout.write("SENSITIVITY PROBES")
            for row in report["sensitivity"]:
                rendered = ", ".join(
                    (
                        f"{name}={result['trust_score']:.2f}"
                        f"/{result['current_rank']}"
                    )
                    for name, result in row["results"].items()
                )
                self.stdout.write(f"{row['variant']}: {rendered}")

        self.stdout.write("")
        self.stdout.write(
            "OFFLINE ONLY; NO DATABASE READS; NO DATABASE WRITES; "
            "NO EXTERNAL CALLS; NO PRODUCTION SCORE CHANGES."
        )
