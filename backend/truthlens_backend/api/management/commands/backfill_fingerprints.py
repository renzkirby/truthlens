"""
Management command to backfill claim_fingerprint for all existing claims.

Usage:
    python manage.py backfill_fingerprints
    python manage.py backfill_fingerprints --dry-run   # Preview without saving
"""

from django.core.management.base import BaseCommand
from api.models import Claim
from api.claim_matching import compute_fingerprint


class Command(BaseCommand):
    help = "Backfill claim_fingerprint for all existing claims that don't have one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be updated without saving to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        claims_without_fingerprint = Claim.objects.filter(claim_fingerprint__isnull=True)
        total = claims_without_fingerprint.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("All claims already have fingerprints. Nothing to do."))
            return

        self.stdout.write(f"Found {total} claims without fingerprints. Processing...")

        updated = 0
        skipped = 0
        errors = 0

        for claim in claims_without_fingerprint.iterator():
            try:
                # Determine fingerprint data based on claim type
                if claim.claim_type == "IMAGE":
                    data = claim.media_hash
                elif claim.claim_type == "URL":
                    data = claim.url_link
                else:
                    # TEXT or other types — use context_text
                    data = claim.context_text

                fingerprint = compute_fingerprint(claim.claim_type, data)

                if fingerprint:
                    if dry_run:
                        self.stdout.write(
                            f"  [DRY RUN] Claim {claim.id} ({claim.claim_type}): "
                            f"would set fingerprint = {fingerprint[:30]}..."
                        )
                    else:
                        claim.claim_fingerprint = fingerprint
                        claim.save(update_fields=["claim_fingerprint"])
                    updated += 1
                else:
                    skipped += 1
                    if dry_run:
                        self.stdout.write(
                            f"  [SKIP] Claim {claim.id} ({claim.claim_type}): "
                            f"insufficient data for fingerprint"
                        )
            except Exception as e:
                errors += 1
                self.stderr.write(f"  [ERROR] Claim {claim.id}: {str(e)}")

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Backfill complete: "
                f"{updated} updated, {skipped} skipped (no data), {errors} errors"
            )
        )
