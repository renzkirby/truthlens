from django.core.management.base import BaseCommand
from django.db.models import Q

from api.embedding_service import generate_embedding
from api.knowledge_reuse_service import (
    index_published_fact_check,
)
from api.models import (
    Claim,
    OfficialFactCheck,
)


class Command(BaseCommand):
    help = (
        "Generate embeddings for existing claims "
        "and search indexes for published "
        "OfficialFactCheck records."
    )

    def add_arguments(
        self,
        parser,
    ):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=("Print what would happen " "without modifying the database."),
        )

    def handle(
        self,
        *args,
        **options,
    ):
        dry_run = options.get("dry_run")

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "Running in DRY-RUN mode. " "No changes will be saved."
                )
            )

        # =================================================
        # 1. CLAIM EMBEDDING BACKFILL
        # =================================================

        claims_to_backfill = Claim.objects.filter(
            context_text__isnull=False,
            claim_embedding__isnull=True,
        ).exclude(context_text="")

        total_claims = claims_to_backfill.count()

        self.stdout.write(f"Found {total_claims} " "claims needing embeddings.")

        success_count = 0
        failure_count = 0

        for index, claim in enumerate(
            claims_to_backfill.iterator(),
            start=1,
        ):
            self.stdout.write(
                "Processing claim " f"{index}/{total_claims} " f"(ID: {claim.id})..."
            )

            normalized_text = (claim.context_text or "").strip()

            if len(normalized_text) < 10:
                self.stdout.write(
                    self.style.WARNING(
                        "  -> Skipping claim "
                        f"{claim.id}: text is too "
                        "short for meaningful "
                        "semantic indexing."
                    )
                )
                continue

            try:
                embedding = generate_embedding(normalized_text)

                if embedding:
                    if not dry_run:
                        claim.claim_embedding = embedding

                        claim.save(update_fields=["claim_embedding"])

                    success_count += 1

                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "  -> Generated "
                            "embedding was empty "
                            f"for claim {claim.id}"
                        )
                    )

                    failure_count += 1

            except Exception as error:
                self.stdout.write(
                    self.style.ERROR(
                        "  -> Failed processing " f"claim {claim.id}: " f"{error}"
                    )
                )

                failure_count += 1

        # =================================================
        # 2. PUBLISHED FACT-CHECK KNOWLEDGE INDEXING
        # =================================================

        self.stdout.write("\nChecking published fact-check " "knowledge records...")

        fact_checks_to_backfill = OfficialFactCheck.objects.filter(
            publication_status=(OfficialFactCheck.PublicationStatus.PUBLISHED)
        ).filter(Q(embedding__isnull=True) | Q(search_vector__isnull=True))

        total_fact_checks = fact_checks_to_backfill.count()

        self.stdout.write(
            f"Found {total_fact_checks} "
            "published fact-checks needing "
            "knowledge indexing."
        )

        fact_check_success = 0
        fact_check_failure = 0

        for index, fact_check in enumerate(
            fact_checks_to_backfill.iterator(),
            start=1,
        ):
            self.stdout.write(
                "Processing fact-check "
                f"{index}/{total_fact_checks} "
                f"(ID: {fact_check.id})..."
            )

            try:
                if dry_run:
                    indexed = True

                else:
                    indexed = index_published_fact_check(fact_check)

                if indexed:
                    fact_check_success += 1

                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "  -> Fact-check " f"{fact_check.id} " "was not indexed."
                        )
                    )

                    fact_check_failure += 1

            except Exception as error:
                self.stdout.write(
                    self.style.ERROR(
                        "  -> Failed processing "
                        "fact-check "
                        f"{fact_check.id}: "
                        f"{error}"
                    )
                )

                fact_check_failure += 1

        # =================================================
        # 3. FINAL SUMMARY
        # =================================================

        self.stdout.write(
            self.style.SUCCESS(
                "\nBackfill complete!\n"
                f"Claims embedded: "
                f"{success_count}; "
                f"claim failures: "
                f"{failure_count}.\n"
                f"Published fact-checks indexed: "
                f"{fact_check_success}; "
                f"fact-check failures: "
                f"{fact_check_failure}."
            )
        )
