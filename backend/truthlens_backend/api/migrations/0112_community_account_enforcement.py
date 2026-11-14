import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0111_multitarget_community_safety"),
    ]

    operations = [
        migrations.AlterField(
            model_name="accountabilityevent",
            name="action_type",
            field=models.CharField(
                choices=[("ORGANIZATION_CREATED", "Organization Created"), ("ORGANIZATION_PLATFORM_TRUST_UPDATED", "Organization Platform Trust Updated"), ("INSTITUTION_CREATED", "Institution Created"), ("ORGANIZATION_INSTITUTION_AFFILIATION_UPDATED", "Organization Institution Affiliation Updated"), ("ORGANIZATION_VERIFICATION_SCOPE_APPROVED", "Organization Verification Scope Approved"), ("ORGANIZATION_VERIFICATION_SCOPE_REQUESTED", "Organization Verification Scope Requested"), ("ORGANIZATION_VERIFICATION_SCOPE_ACTIVATED", "Organization Verification Scope Activated"), ("ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED", "Organization Verification Specializations Updated"), ("CLAIM_INVESTIGATION_CLASSIFIED", "Claim Investigation Classified"), ("CLAIM_INSTITUTION_CONTEXT_UPDATED", "Claim Institution Context Updated"), ("VERIFICATION_ASSIGNMENT_CREATED", "Verification Assignment Created"), ("VERIFICATION_ASSIGNMENT_CLAIMED", "Verification Assignment Claimed"), ("VERIFICATION_ASSIGNMENT_RELEASED", "Verification Assignment Released"), ("VERIFICATION_ASSIGNMENT_COMPLETED", "Verification Assignment Completed"), ("ORGANIZATION_MEMBERSHIP_ROLE_CHANGED", "Organization Membership Role Changed"), ("ORGANIZATION_MEMBERSHIP_SUSPENDED", "Organization Membership Suspended"), ("ORGANIZATION_MEMBERSHIP_RESTORED", "Organization Membership Restored"), ("ORGANIZATION_MEMBERSHIP_REMOVED", "Organization Membership Removed"), ("ORGANIZATION_INVITATION_CREATED", "Organization Invitation Created"), ("ORGANIZATION_INVITATION_RESENT", "Organization Invitation Resent"), ("ORGANIZATION_INVITATION_CANCELLED", "Organization Invitation Cancelled"), ("ORGANIZATION_INVITATION_ACCEPTED", "Organization Invitation Accepted"), ("ORGANIZATION_INVITATION_EXPIRED", "Organization Invitation Expired"), ("ORGANIZATION_PUBLIC_PROFILE_UPDATED", "Organization Public Profile Updated"), ("ORGANIZATION_LOGO_UPDATED", "Organization Logo Updated"), ("ORGANIZATION_LOGO_REMOVED", "Organization Logo Removed"), ("SAFETY_CASE_CLAIMED", "Safety Case Claimed"), ("SAFETY_CASE_RELEASED", "Safety Case Released"), ("SAFETY_CASE_ESCALATED", "Safety Case Escalated"), ("SAFETY_DISMISSED", "Safety Dismissed"), ("SAFETY_CONTENT_REMOVED", "Safety Content Removed"), ("COMMUNITY_WARNING_ISSUED", "Community Warning Issued"), ("COMMUNITY_RESTRICTION_ISSUED", "Community Restriction Issued"), ("COMMUNITY_ENFORCEMENT_REVIEW_SUBMITTED", "Community Enforcement Review Submitted"), ("COMMUNITY_ENFORCEMENT_REVIEW_STARTED", "Community Enforcement Review Started"), ("COMMUNITY_ENFORCEMENT_UPHELD", "Community Enforcement Upheld"), ("COMMUNITY_ENFORCEMENT_REVERSED", "Community Enforcement Reversed"), ("COMMUNITY_ENFORCEMENT_BASIS_REVERSED", "Community Enforcement Basis Reversed"), ("COMMUNITY_RESTRICTION_LIFTED", "Community Restriction Lifted"), ("COMMUNITY_RESTRICTION_SUPERSEDED", "Community Restriction Superseded"), ("PLATFORM_SAFETY_MODERATOR_REVOKED", "Platform Safety Moderator Revoked"), ("PLATFORM_STAFF_INVITATION_CREATED", "Platform Staff Invitation Created"), ("PLATFORM_STAFF_INVITATION_RESENT", "Platform Staff Invitation Resent"), ("PLATFORM_STAFF_INVITATION_CANCELLED", "Platform Staff Invitation Cancelled"), ("PLATFORM_STAFF_INVITATION_ACCEPTED", "Platform Staff Invitation Accepted"), ("PLATFORM_STAFF_INVITATION_EXPIRED", "Platform Staff Invitation Expired"), ("EVIDENCE_REOPENED", "Evidence Reopened"), ("EVIDENCE_PRIOR_REVIEW_ACCEPTED", "Prior Evidence Review Accepted"), ("EVIDENCE_VERIFIED", "Evidence Verified"), ("EVIDENCE_REJECTED", "Evidence Rejected"), ("ADJUDICATION_STARTED", "Adjudication Started"), ("VERDICT_ISSUED", "Verdict Issued"), ("VERDICT_REVISED", "Verdict Revised"), ("ARTICLE_DRAFT_CREATED", "Article Draft Created"), ("ARTICLE_DRAFT_SAVED", "Article Draft Saved"), ("ARTICLE_SUBMITTED", "Article Submitted"), ("ARTICLE_RETURNED_FOR_REWORK", "Article Returned For Rework"), ("ARTICLE_ABANDONED", "Article Abandoned"), ("ARTICLE_PUBLISHED", "Article Published"), ("ARTICLE_REVISION_DRAFTED", "Article Revision Drafted"), ("ARTICLE_REVISED", "Article Revised"), ("FACTUAL_CORRECTION_REQUESTED", "Factual Correction Requested"), ("FACTUAL_CORRECTION_PROPOSAL_SAVED", "Factual Correction Proposal Saved"), ("FACTUAL_CORRECTION_PROPOSAL_PREPARED", "Factual Correction Proposal Prepared"), ("FACTUAL_CORRECTION_CANCELLED", "Factual Correction Cancelled"), ("FACTUAL_CORRECTION_PUBLISHED", "Factual Correction Published")],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[("AUTOMATED_VERIFICATION_COMPLETED", "Analysis completed"), ("AUTOMATED_VERIFICATION_FAILED", "Analysis failed"), ("PARTNER_FACT_CHECK_PUBLISHED", "Partner fact-check published"), ("PARTNER_FACT_CHECK_CORRECTED", "Partner fact-check corrected"), ("ARTICLE_RETURNED_FOR_REWORK", "Article returned for rework"), ("FACT_CHECK_PUBLISHED", "Fact-check published"), ("FACTUAL_CORRECTION_PUBLISHED", "Factual correction published"), ("ORGANIZATION_MEMBERSHIP_CHANGED", "Membership changed"), ("ORGANIZATION_GOVERNANCE_CHANGED", "Organization governance changed"), ("THREAD_COMMENTED", "Thread commented"), ("EVIDENCE_REVIEWED", "Evidence reviewed"), ("USER_FOLLOWED", "User followed"), ("COMMUNITY_MODERATION_OUTCOME", "Community moderation outcome"), ("COMMUNITY_ACCOUNT_ENFORCEMENT", "Community account enforcement")],
                max_length=40,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="notification",
            name="notification_type_valid",
        ),
        migrations.AddConstraint(
            model_name="notification",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    notification_type__in=["AUTOMATED_VERIFICATION_COMPLETED","AUTOMATED_VERIFICATION_FAILED","PARTNER_FACT_CHECK_PUBLISHED","PARTNER_FACT_CHECK_CORRECTED","ARTICLE_RETURNED_FOR_REWORK","FACT_CHECK_PUBLISHED","FACTUAL_CORRECTION_PUBLISHED","ORGANIZATION_MEMBERSHIP_CHANGED","ORGANIZATION_GOVERNANCE_CHANGED","THREAD_COMMENTED","EVIDENCE_REVIEWED","USER_FOLLOWED","COMMUNITY_MODERATION_OUTCOME","COMMUNITY_ACCOUNT_ENFORCEMENT"]
                ),
                name="notification_type_valid",
            ),
        ),
        migrations.CreateModel(
            name="CommunityAccountEnforcement",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("username_snapshot", models.CharField(max_length=150)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("WARNING", "Warning"),
                            (
                                "TEMPORARY_RESTRICTION",
                                "Temporary Community restriction",
                            ),
                            (
                                "INDEFINITE_RESTRICTION",
                                "Indefinite Community restriction",
                            ),
                        ],
                        max_length=32,
                    ),
                ),
                ("user_rationale", models.TextField()),
                ("internal_note", models.TextField(blank=True, default="")),
                ("policy_title_snapshot", models.CharField(max_length=160)),
                ("policy_version", models.CharField(max_length=20)),
                ("violation_code_snapshot", models.CharField(max_length=64)),
                ("violation_label_snapshot", models.CharField(max_length=160)),
                (
                    "restriction_ends_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "issued_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                    ),
                ),
                ("user_seen_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "revocation_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("REVIEW_REVERSED", "Review reversed"),
                            (
                                "BASIS_REVERSED",
                                "Underlying content decision reversed",
                            ),
                            ("LIFTED_EARLY", "Restriction lifted early"),
                            (
                                "SUPERSEDED",
                                "Superseded by stronger restriction",
                            ),
                        ],
                        default="",
                        max_length=32,
                    ),
                ),
                (
                    "revocation_rationale",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "issued_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_account_enforcements_issued",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_account_enforcements_revoked",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "safety_decision",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="account_enforcement",
                        to="api.communitysafetydecision",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_account_enforcements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-issued_at", "-id"],
                "indexes": [
                    models.Index(
                        fields=["user", "-issued_at"],
                        name="comm_enforce_user_time_idx",
                    ),
                    models.Index(
                        fields=["user", "restriction_ends_at"],
                        name="comm_enforce_user_end_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                action="TEMPORARY_RESTRICTION",
                                restriction_ends_at__isnull=False,
                            )
                            | models.Q(
                                action__in=[
                                    "WARNING",
                                    "INDEFINITE_RESTRICTION",
                                ],
                                restriction_ends_at__isnull=True,
                            )
                        ),
                        name="comm_enforce_action_expiry_ck",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                revoked_at__isnull=True,
                                revoked_by__isnull=True,
                                revocation_reason="",
                                revocation_rationale="",
                            )
                            | (
                                models.Q(revoked_at__isnull=False)
                                & ~models.Q(revocation_reason="")
                                & ~models.Q(revocation_rationale="")
                            )
                        ),
                        name="comm_enforce_revocation_state_ck",
                    ),
                    models.UniqueConstraint(
                        fields=("user",),
                        condition=models.Q(
                            action="INDEFINITE_RESTRICTION",
                            revoked_at__isnull=True,
                            user__isnull=False,
                        ),
                        name="comm_enforce_one_active_indef",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CommunityAccountEnforcementReview",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("request_statement", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SUBMITTED", "Submitted"),
                            ("UNDER_REVIEW", "Under review"),
                            ("RESOLVED", "Resolved"),
                            ("MOOT", "Moot"),
                        ],
                        default="SUBMITTED",
                        max_length=20,
                    ),
                ),
                (
                    "reviewer_independence_note",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "independence_override_rationale",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "review_started_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "outcome",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("UPHELD", "Account action upheld"),
                            ("REVERSED", "Account action reversed"),
                        ],
                        default="",
                        max_length=20,
                    ),
                ),
                (
                    "resolution_rationale",
                    models.TextField(blank=True, default=""),
                ),
                ("internal_note", models.TextField(blank=True, default="")),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "enforcement",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="review",
                        to="api.communityaccountenforcement",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_account_enforcement_reviews_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="community_account_enforcement_reviews",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-submitted_at", "-id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                status="SUBMITTED",
                                reviewer__isnull=True,
                                review_started_at__isnull=True,
                                outcome="",
                                resolved_at__isnull=True,
                            )
                            | models.Q(
                                status="UNDER_REVIEW",
                                reviewer__isnull=False,
                                review_started_at__isnull=False,
                                outcome="",
                                resolved_at__isnull=True,
                            )
                            | (
                                models.Q(
                                    status="RESOLVED",
                                    reviewer__isnull=False,
                                    review_started_at__isnull=False,
                                    outcome__in=["UPHELD", "REVERSED"],
                                    resolved_at__isnull=False,
                                )
                                & ~models.Q(resolution_rationale="")
                            )
                            | (
                                models.Q(
                                    status="MOOT",
                                    outcome="",
                                    resolved_at__isnull=False,
                                )
                                & ~models.Q(resolution_rationale="")
                            )
                        ),
                        name="comm_enforce_review_state_ck",
                    ),
                ],
            },
        ),
    ]
