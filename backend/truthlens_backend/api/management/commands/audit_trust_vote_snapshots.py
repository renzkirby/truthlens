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
        nonstandard = Vote.objects.filter(
            Q(vote_trust_snapshot__isnull=True)
            | Q(vote_trust_snapshot__lt=0)
            | Q(vote_trust_snapshot__gt=100)
        ).count()

        report = {
            "total_votes": total,
            "null_snapshots": null_snapshots,
            "below_zero": below_zero,
            "above_hundred": above_hundred,
            "nonstandard_snapshot_rows": nonstandard,
            "minimum_snapshot": bounds["minimum"],
            "maximum_snapshot": bounds["maximum"],
            "snapshot_coverage_percent": (
                round(
                    ((total - null_snapshots) / total) * 100,
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
            f"below_zero={report['below_zero']}"
        )
        self.stdout.write(
            f"above_hundred={report['above_hundred']}"
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
