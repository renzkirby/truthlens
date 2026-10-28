"""Audit stored vote reputation snapshots without modifying data."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Max, Min, Q

from api.models import Vote


class Command(BaseCommand):
    help = (
        "Read-only audit of Vote.vote_trust_snapshot coverage and range. "
        "Does not expose individual votes or users."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the aggregate audit as JSON.",
        )

    def handle(self, *args, **options):
        total = Vote.objects.count()
        null_snapshots = Vote.objects.filter(
            vote_trust_snapshot__isnull=True,
        ).count()
        below_zero = Vote.objects.filter(
            vote_trust_snapshot__lt=0,
        ).count()
        above_hundred = Vote.objects.filter(
            vote_trust_snapshot__gt=100,
        ).count()
        bounds = Vote.objects.filter(
            vote_trust_snapshot__isnull=False,
        ).aggregate(
            minimum=Min("vote_trust_snapshot"),
            maximum=Max("vote_trust_snapshot"),
        )
        weight_null = Vote.objects.filter(
            vote_reputation_weight_snapshot__isnull=True,
        ).count()
        weight_below_zero = Vote.objects.filter(
            vote_reputation_weight_snapshot__lt=0,
        ).count()
        weight_above_one = Vote.objects.filter(
            vote_reputation_weight_snapshot__gt=1,
        ).count()
        resolved_history_null = Vote.objects.filter(
            vote_resolved_actions_snapshot__isnull=True,
        ).count()
        validated_history_null = Vote.objects.filter(
            vote_validated_actions_snapshot__isnull=True,
        ).count()
        complete_history = Vote.objects.filter(
            vote_resolved_actions_snapshot__isnull=False,
            vote_validated_actions_snapshot__isnull=False,
        ).count()
        partial_history = Vote.objects.filter(
            Q(
                vote_resolved_actions_snapshot__isnull=False,
                vote_validated_actions_snapshot__isnull=True,
            )
            | Q(
                vote_resolved_actions_snapshot__isnull=True,
                vote_validated_actions_snapshot__isnull=False,
            )
        ).count()
        legacy_preserved = Vote.objects.filter(
            vote_reputation_weight_snapshot__isnull=False,
            vote_resolved_actions_snapshot__isnull=True,
            vote_validated_actions_snapshot__isnull=True,
        ).count()
        hardened = Vote.objects.filter(
            vote_reputation_weight_snapshot__isnull=False,
            vote_resolved_actions_snapshot__isnull=False,
            vote_validated_actions_snapshot__isnull=False,
        ).count()

        nonstandard = Vote.objects.filter(
            Q(vote_trust_snapshot__isnull=True)
            | Q(vote_trust_snapshot__lt=0)
            | Q(vote_trust_snapshot__gt=100)
            | Q(vote_reputation_weight_snapshot__isnull=True)
            | Q(vote_reputation_weight_snapshot__lt=0)
            | Q(vote_reputation_weight_snapshot__gt=1)
        ).count()

        report = {
            "total_votes": total,
            "null_snapshots": null_snapshots,
            "below_zero": below_zero,
            "above_hundred": above_hundred,
            "nonstandard_snapshot_rows": nonstandard,
            "minimum_snapshot": bounds["minimum"],
            "maximum_snapshot": bounds["maximum"],
            "weight_null": weight_null,
            "weight_below_zero": weight_below_zero,
            "weight_above_one": weight_above_one,
            "resolved_history_snapshot_null": resolved_history_null,
            "validated_history_snapshot_null": validated_history_null,
            "complete_history_snapshots": complete_history,
            "partial_history_snapshots": partial_history,
            "legacy_preserved_votes": legacy_preserved,
            "hardened_votes": hardened,
            "snapshot_coverage_percent": (
                round(
                    ((total - null_snapshots) / total) * 100,
                    2,
                )
                if total
                else 100.0
            ),
            "weight_coverage_percent": (
                round(
                    ((total - weight_null) / total) * 100,
                    2,
                )
                if total
                else 100.0
            ),
            "history_snapshot_coverage_percent": (
                round(
                    (complete_history / total) * 100,
                    2,
                )
                if total
                else 100.0
            ),
            "read_only": True,
        }

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    report,
                    sort_keys=True,
                )
            )
            return

        self.stdout.write("TRUTHLENS VOTE SNAPSHOT AUDIT")
        self.stdout.write(f"total_votes={report['total_votes']}")
        self.stdout.write(
            f"snapshot_coverage_percent="
            f"{report['snapshot_coverage_percent']:.2f}"
        )
        self.stdout.write(
            f"null_snapshots={report['null_snapshots']}"
        )
        self.stdout.write(
            f"weight_coverage_percent="
            f"{report['weight_coverage_percent']:.2f}"
        )
        self.stdout.write(
            f"history_snapshot_coverage_percent="
            f"{report['history_snapshot_coverage_percent']:.2f}"
        )
        self.stdout.write(
            f"weight_null={report['weight_null']}"
        )
        self.stdout.write(
            f"resolved_history_snapshot_null="
            f"{report['resolved_history_snapshot_null']}"
        )
        self.stdout.write(
            f"validated_history_snapshot_null="
            f"{report['validated_history_snapshot_null']}"
        )
        self.stdout.write(
            f"partial_history_snapshots="
            f"{report['partial_history_snapshots']}"
        )
        self.stdout.write(
            f"legacy_preserved_votes={report['legacy_preserved_votes']}"
        )
        self.stdout.write(
            f"hardened_votes={report['hardened_votes']}"
        )
        self.stdout.write(
            f"below_zero={report['below_zero']}"
        )
        self.stdout.write(
            f"above_hundred={report['above_hundred']}"
        )
        self.stdout.write(
            f"weight_below_zero={report['weight_below_zero']}"
        )
        self.stdout.write(
            f"weight_above_one={report['weight_above_one']}"
        )
        self.stdout.write(
            f"nonstandard_snapshot_rows="
            f"{report['nonstandard_snapshot_rows']}"
        )
        self.stdout.write(
            "snapshot_range="
            f"{report['minimum_snapshot']}..{report['maximum_snapshot']}"
        )
        self.stdout.write(
            "READ ONLY; NO DATABASE WRITES; NO VOTE OR USER DETAILS EXPOSED."
        )
