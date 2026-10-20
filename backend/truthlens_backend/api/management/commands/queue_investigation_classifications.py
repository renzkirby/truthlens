"""Safely seed existing available community claims into the classifier queue.

Dry-run by default. Never retroactively authorizes claims: shadow mode only
records suggestions; enforce requires separate accuracy/rollout approval.
"""
from django.core.management.base import BaseCommand, CommandError

from api.investigation_classifier import (
    classification_mode,
    dispatch_classification_task,
)
from api.models import Claim, VerificationAssignment


class Command(BaseCommand):
    help = (
        "Preview or enqueue a bounded batch of existing unclassified community "
        "investigations for asynchronous subject classification."
    )

    def add_arguments(self, parser):
        parser.add_argument("--enqueue", action="store_true", help="Actually queue jobs.")
        parser.add_argument(
            "--limit", type=int, default=100,
            help="Maximum claims to inspect (1-1000; default 100).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("--limit must be between 1 and 1000.")
        mode = classification_mode()
        if options["enqueue"] and mode == "off":
            raise CommandError(
                "Classifier mode is off. Configure shadow first; do not enable "
                "enforce without a separate accuracy review."
            )

        candidates = list(
            Claim.objects.filter(
                verification_assignments__status=VerificationAssignment.Status.AVAILABLE,
                threads__isnull=False,
                investigation_classification__isnull=True,
            )
            .exclude(context_text__isnull=True)
            .exclude(context_text="")
            .distinct()
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )

        if not options["enqueue"]:
            self.stdout.write(
                f"DRY RUN: {len(candidates)} eligible unclassified community "
                f"claims in this batch (limit={limit}); mode={mode}. "
                "No tasks dispatched."
            )
            return

        queued = sum(bool(dispatch_classification_task(claim_id)) for claim_id in candidates)
        self.stdout.write(
            self.style.SUCCESS(
                f"Queued {queued} of {len(candidates)} eligible claims "
                f"(mode={mode}); check worker logs and assessment records."
            )
        )
