"""Preview or apply a deterministic recomputation of Community Trust Scores."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from api.platform_identity_service import is_platform_staff_identity
from api.trust_service import calculate_trust_components


class Command(BaseCommand):
    help = (
        "Preview or apply Trust Score recomputation after scoring-policy changes. "
        "Outputs aggregate counts only and never exposes usernames."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist recalculated Trust Scores. Without this flag, preview only.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Optional maximum number of user rows to inspect, for canary checks.",
        )

    def handle(self, *args, **options):
        users = (
            User.objects.select_related("profile")
            .filter(profile__isnull=False)
            .order_by("id")
        )
        if options["limit"] is not None:
            if options["limit"] < 1:
                self.stderr.write("--limit must be at least 1.")
                return
            users = users[: options["limit"]]

        inspected = 0
        applicable = 0
        platform_staff_skipped = 0
        changed = 0
        unchanged = 0
        maximum_absolute_delta = 0.0
        legacy_zero_to_neutral = 0
        changed_with_resolved_actions = 0
        changed_with_community_votes = 0
        changed_with_moderation_penalty = 0
        delta_at_most_1 = 0
        delta_at_most_5 = 0
        delta_at_most_15 = 0
        delta_over_15 = 0

        for user in users:
            inspected += 1

            if is_platform_staff_identity(user):
                platform_staff_skipped += 1
                continue

            applicable += 1
            components = calculate_trust_components(user)
            target = float(components["trust_score"])
            current = float(user.profile.trust_score)
            delta = target - current
            maximum_absolute_delta = max(
                maximum_absolute_delta,
                abs(delta),
            )

            if abs(delta) < 0.005:
                unchanged += 1
                continue

            changed += 1

            absolute_delta = abs(delta)
            if absolute_delta <= 1.0:
                delta_at_most_1 += 1
            elif absolute_delta <= 5.0:
                delta_at_most_5 += 1
            elif absolute_delta <= 15.0:
                delta_at_most_15 += 1
            else:
                delta_over_15 += 1

            if components["resolved_actions"] > 0:
                changed_with_resolved_actions += 1
            if components["upvotes"] > 0 or components["downvotes"] > 0:
                changed_with_community_votes += 1
            if components["moderation_penalty"] > 0:
                changed_with_moderation_penalty += 1

            if (
                abs(current) < 0.005
                and abs(target - 50.0) < 0.005
                and components["resolved_actions"] == 0
                and components["upvotes"] == 0
                and components["downvotes"] == 0
                and components["moderation_penalty"] == 0
            ):
                legacy_zero_to_neutral += 1

            if options["apply"]:
                user.profile.trust_score = target
                user.profile.save(
                    update_fields=["trust_score"],
                )

        mode = "APPLY" if options["apply"] else "PREVIEW"
        self.stdout.write("TRUTHLENS TRUST SCORE RECOMPUTATION")
        self.stdout.write(f"mode={mode}")
        self.stdout.write(f"inspected_users={inspected}")
        self.stdout.write(f"applicable_users={applicable}")
        self.stdout.write(
            f"platform_staff_skipped={platform_staff_skipped}"
        )
        self.stdout.write(f"changed_users={changed}")
        self.stdout.write(f"unchanged_users={unchanged}")
        self.stdout.write(
            "maximum_absolute_delta="
            f"{maximum_absolute_delta:.2f}"
        )
        self.stdout.write(
            f"legacy_zero_to_neutral={legacy_zero_to_neutral}"
        )
        self.stdout.write(
            "changed_with_resolved_actions="
            f"{changed_with_resolved_actions}"
        )
        self.stdout.write(
            "changed_with_community_votes="
            f"{changed_with_community_votes}"
        )
        self.stdout.write(
            "changed_with_moderation_penalty="
            f"{changed_with_moderation_penalty}"
        )
        self.stdout.write(
            f"delta_at_most_1={delta_at_most_1}"
        )
        self.stdout.write(
            f"delta_1_to_5={delta_at_most_5}"
        )
        self.stdout.write(
            f"delta_5_to_15={delta_at_most_15}"
        )
        self.stdout.write(
            f"delta_over_15={delta_over_15}"
        )

        if options["apply"]:
            self.stdout.write(
                "APPLIED; persisted Community Trust Scores now match the "
                "current deterministic calculation."
            )
        else:
            self.stdout.write(
                "PREVIEW ONLY; NO DATABASE WRITES. Re-run with --apply "
                "after reviewing the aggregate impact."
            )
