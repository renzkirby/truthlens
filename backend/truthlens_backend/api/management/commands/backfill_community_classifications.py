"""Dry-run-first backfill for historical Community claim classifications.

This command only targets claims already represented by a Community Thread.
It never writes classifications directly; enqueue mode dispatches the same
validated asynchronous classifier used for newly analyzed claims.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef

from api.investigation_classifier import (
    MAX_CLAIM_LENGTH,
    MIN_CLAIM_LENGTH,
    classification_mode,
    dispatch_classification_task,
)
from api.models import (
    Claim,
    InvestigationClassificationAssessment,
    VerificationAssignment,
)
from api.verification_domain_policy import subject_eligibility_enforced


DEFAULT_LIMIT = 25
MAX_LIMIT = 100


class Command(BaseCommand):
    help = (
        "Preview or queue a bounded authoritative classification backfill for "
        "historical unclassified Community claims."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--enqueue",
            action="store_true",
            help="Actually queue eligible claims through the normal classifier.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_LIMIT,
            help=(
                "Maximum eligible claims to queue in this batch "
                f"(1-{MAX_LIMIT}; default {DEFAULT_LIMIT})."
            ),
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= MAX_LIMIT:
            raise CommandError(f"--limit must be between 1 and {MAX_LIMIT}.")

        mode = classification_mode()
        if options["enqueue"]:
            if mode != "enforce":
                raise CommandError(
                    "Community classification backfill requires "
                    "INVESTIGATION_CLASSIFICATION_MODE=enforce."
                )
            if subject_eligibility_enforced():
                raise CommandError(
                    "Community classification backfill requires "
                    "INVESTIGATION_ROUTING_MODE=off so historical classification "
                    "cannot change partner intake authorization."
                )

        active_or_completed = VerificationAssignment.objects.filter(
            claim_id=OuterRef("pk"),
            status__in=[
                VerificationAssignment.Status.ACTIVE,
                VerificationAssignment.Status.COMPLETED,
            ],
        )
        previous_assessment = InvestigationClassificationAssessment.objects.filter(
            claim_id=OuterRef("pk"),
        )

        claims = (
            Claim.objects.filter(
                threads__isnull=False,
                investigation_classification__isnull=True,
            )
            .annotate(
                has_active_or_completed_assignment=Exists(active_or_completed),
                has_previous_assessment=Exists(previous_assessment),
            )
            .distinct()
            .order_by("pk")
        )

        total_unclassified = 0
        invalid_context = 0
        blocked_by_assignment = 0
        previous_assessment_count = 0
        eligible_total = 0
        selected_ids = []

        for claim in claims.iterator():
            total_unclassified += 1
            context_text = (
                claim.context_text.strip()
                if isinstance(claim.context_text, str)
                else ""
            )

            if not (
                MIN_CLAIM_LENGTH
                <= len(context_text)
                <= MAX_CLAIM_LENGTH
            ):
                invalid_context += 1
                continue

            if claim.has_active_or_completed_assignment:
                blocked_by_assignment += 1
                continue

            if claim.has_previous_assessment:
                previous_assessment_count += 1
                continue

            eligible_total += 1
            if len(selected_ids) < limit:
                selected_ids.append(claim.pk)

        summary = (
            f"unclassified_community={total_unclassified} "
            f"eligible={eligible_total} "
            f"selected={len(selected_ids)} "
            f"invalid_context={invalid_context} "
            f"blocked_by_assignment={blocked_by_assignment} "
            f"previous_assessment={previous_assessment_count} "
            f"limit={limit} mode={mode}"
        )

        if not options["enqueue"]:
            self.stdout.write(
                f"DRY RUN: {summary}. No tasks dispatched."
            )
            return

        queued = sum(
            bool(dispatch_classification_task(claim_id))
            for claim_id in selected_ids
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Queued {queued} of {len(selected_ids)} selected historical "
                f"Community claims. {summary}. "
                "Check Celery logs plus assessment/classification records."
            )
        )
