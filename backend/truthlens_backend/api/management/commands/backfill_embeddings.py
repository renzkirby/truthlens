from django.core.management.base import BaseCommand
from api.models import Claim
from api.embedding_service import generate_embedding
import sys


class Command(BaseCommand):
    help = "Generate embeddings for existing claims that have context_text but lack a claim_embedding."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would happen without actually modifying the database.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run")

        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode. No changes will be saved."))

        # We only want to process TEXT and URL claims where context_text exists
        # IMAGE claims are deduplicated via pHash, but if they have context_text,
        # they can still technically be embedded. The query excludes those that already have an embedding.
        claims_to_backfill = Claim.objects.filter(
            context_text__isnull=False,
            claim_embedding__isnull=True
        ).exclude(context_text="")

        total_claims = claims_to_backfill.count()
        self.stdout.write(f"Found {total_claims} claims needing embeddings.")

        if total_claims == 0:
            self.stdout.write(self.style.SUCCESS("All claims are properly embedded. Nothing to do."))
            return

        success_count = 0
        failure_count = 0

        # Process in batches to avoid eating up memory
        for i, claim in enumerate(claims_to_backfill):
            self.stdout.write(f"Processing claim {i+1}/{total_claims} (ID: {claim.id})...")
            
            try:
                embedding = generate_embedding(claim.context_text)
                
                if embedding:
                    if not dry_run:
                        claim.claim_embedding = embedding
                        claim.save(update_fields=['claim_embedding'])
                    success_count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  -> Generated embedding was empty for claim {claim.id}"))
                    failure_count += 1
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  -> Failed processing claim {claim.id}: {e}"))
                failure_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nBackfill complete! "
            f"Successfully embedded: {success_count}. "
            f"Failed: {failure_count}."
        ))
