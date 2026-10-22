"""Dry-run-first command to shadow-evaluate previously verified claim text.

Classification belongs to the Claim and is independent of Community threads
or VerificationAssignments. This bulk command may only queue in shadow mode,
so it cannot retroactively grant partner intake authorization.
"""
from django.core.management.base import BaseCommand, CommandError

from api.investigation_classifier import (
    classification_mode,
    dispatch_classification_task,
)
from api.models import Claim, VerificationAssignment


class Command(BaseCommand):
    help = (
        "Preview or queue a bounded batch of claims with stored text, independent "
        "of community threads, for shadow-mode subject classification."
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
        if options["enqueue"] and mode != "shadow":
            raise CommandError(
                "Bulk classification is allowed in shadow mode only. This "
                "command must never grant authoritative classification."
            )

        candidates = list(
            Claim.objects.filter(investigation_classification__isnull=True)
            .exclude(context_text__isnull=True)
            .exclude(context_text="")
            .exclude(
                verification_assignments__status__in=[
                    VerificationAssignment.Status.ACTIVE,
                    VerificationAssignment.Status.COMPLETED,
                ],
            )
            .order_by("pk")
            .values_list("pk", flat=True)[:limit]
        )

        if not options["enqueue"]:
            self.stdout.write(
                f"DRY RUN: {len(candidates)} unclassified claims with stored text "
                f"in this batch (limit={limit}); mode={mode}. "
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
