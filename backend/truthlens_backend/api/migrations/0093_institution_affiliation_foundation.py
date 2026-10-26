import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0092_platform_staff_invitations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Institution",
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
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                (
                    "website",
                    models.URLField(blank=True, max_length=2000, null=True),
                ),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        Lower("name"),
                        name="unique_institution_name_ci",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="organization",
            name="organization_subtype",
            field=models.CharField(
                blank=True,
                choices=[
                    ("STUDENT_PUBLICATION", "Student Publication"),
                ],
                help_text=(
                    "Platform-managed organization subtype. Student Publication is "
                    "valid only for News Organizations."
                ),
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="organization",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("organization_subtype__isnull", True))
                    | models.Q(
                        ("organization_subtype", "STUDENT_PUBLICATION"),
                        ("organization_type", "NEWS"),
                    )
                ),
                name="student_publication_requires_news_org",
            ),
        ),
        migrations.CreateModel(
            name="OrganizationInstitutionAffiliation",
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
                (
                    "coverage_scope",
                    models.CharField(
                        choices=[
                            ("INSTITUTION_WIDE", "Institution-wide"),
                        ],
                        default="INSTITUTION_WIDE",
                        max_length=32,
                    ),
                ),
                (
                    "verification_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("VERIFIED", "Verified"),
                            ("REJECTED", "Rejected"),
                        ],
                        db_index=True,
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                (
                    "rationale",
                    models.TextField(blank=True, default="", max_length=2000),
                ),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "institution",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="student_publication_affiliations",
                        to="api.institution",
                    ),
                ),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="institution_affiliation",
                        to="api.organization",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_institution_affiliations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["organization_id"],
                "constraints": [
                    models.CheckConstraint(
                        condition=(
                            models.Q(
                                ("reviewed_at__isnull", True),
                                ("reviewed_by__isnull", True),
                                ("verification_status", "PENDING"),
                            )
                            | models.Q(
                                ("reviewed_at__isnull", False),
                                ("reviewed_by__isnull", False),
                                ("verification_status__in", ["VERIFIED", "REJECTED"]),
                            )
                        ),
                        name="institution_affiliation_review_state_valid",
                    ),
                ],
            },
        ),
        migrations.AlterField(
            model_name="accountabilityevent",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("ORGANIZATION_CREATED", "Organization Created"),
                    ("ORGANIZATION_PLATFORM_TRUST_UPDATED", "Organization Platform Trust Updated"),
                    ("INSTITUTION_CREATED", "Institution Created"),
                    ("ORGANIZATION_INSTITUTION_AFFILIATION_UPDATED", "Organization Institution Affiliation Updated"),
                    ("ORGANIZATION_VERIFICATION_SCOPE_APPROVED", "Organization Verification Scope Approved"),
                    ("ORGANIZATION_VERIFICATION_SCOPE_REQUESTED", "Organization Verification Scope Requested"),
                    ("ORGANIZATION_VERIFICATION_SCOPE_ACTIVATED", "Organization Verification Scope Activated"),
                    ("ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED", "Organization Verification Specializations Updated"),
                    ("CLAIM_INVESTIGATION_CLASSIFIED", "Claim Investigation Classified"),
                    ("VERIFICATION_ASSIGNMENT_CREATED", "Verification Assignment Created"),
                    ("VERIFICATION_ASSIGNMENT_CLAIMED", "Verification Assignment Claimed"),
                    ("VERIFICATION_ASSIGNMENT_RELEASED", "Verification Assignment Released"),
                    ("VERIFICATION_ASSIGNMENT_COMPLETED", "Verification Assignment Completed"),
                    ("ORGANIZATION_MEMBERSHIP_ROLE_CHANGED", "Organization Membership Role Changed"),
                    ("ORGANIZATION_MEMBERSHIP_SUSPENDED", "Organization Membership Suspended"),
                    ("ORGANIZATION_MEMBERSHIP_RESTORED", "Organization Membership Restored"),
                    ("ORGANIZATION_MEMBERSHIP_REMOVED", "Organization Membership Removed"),
                    ("ORGANIZATION_INVITATION_CREATED", "Organization Invitation Created"),
                    ("ORGANIZATION_INVITATION_RESENT", "Organization Invitation Resent"),
                    ("ORGANIZATION_INVITATION_CANCELLED", "Organization Invitation Cancelled"),
                    ("ORGANIZATION_INVITATION_ACCEPTED", "Organization Invitation Accepted"),
                    ("ORGANIZATION_INVITATION_EXPIRED", "Organization Invitation Expired"),
                    ("ORGANIZATION_PUBLIC_PROFILE_UPDATED", "Organization Public Profile Updated"),
                    ("ORGANIZATION_LOGO_UPDATED", "Organization Logo Updated"),
                    ("ORGANIZATION_LOGO_REMOVED", "Organization Logo Removed"),
                    ("SAFETY_CASE_CLAIMED", "Safety Case Claimed"),
                    ("SAFETY_CASE_RELEASED", "Safety Case Released"),
                    ("SAFETY_CASE_ESCALATED", "Safety Case Escalated"),
                    ("SAFETY_DISMISSED", "Safety Dismissed"),
                    ("SAFETY_CONTENT_REMOVED", "Safety Content Removed"),
                    ("PLATFORM_SAFETY_MODERATOR_REVOKED", "Platform Safety Moderator Revoked"),
                    ("PLATFORM_STAFF_INVITATION_CREATED", "Platform Staff Invitation Created"),
                    ("PLATFORM_STAFF_INVITATION_RESENT", "Platform Staff Invitation Resent"),
                    ("PLATFORM_STAFF_INVITATION_CANCELLED", "Platform Staff Invitation Cancelled"),
                    ("PLATFORM_STAFF_INVITATION_ACCEPTED", "Platform Staff Invitation Accepted"),
                    ("PLATFORM_STAFF_INVITATION_EXPIRED", "Platform Staff Invitation Expired"),
                    ("EVIDENCE_REOPENED", "Evidence Reopened"),
                    ("EVIDENCE_VERIFIED", "Evidence Verified"),
                    ("EVIDENCE_REJECTED", "Evidence Rejected"),
                    ("ADJUDICATION_STARTED", "Adjudication Started"),
                    ("VERDICT_ISSUED", "Verdict Issued"),
                    ("VERDICT_REVISED", "Verdict Revised"),
                    ("ARTICLE_DRAFT_CREATED", "Article Draft Created"),
                    ("ARTICLE_DRAFT_SAVED", "Article Draft Saved"),
                    ("ARTICLE_SUBMITTED", "Article Submitted"),
                    ("ARTICLE_RETURNED_FOR_REWORK", "Article Returned For Rework"),
                    ("ARTICLE_ABANDONED", "Article Abandoned"),
                    ("ARTICLE_PUBLISHED", "Article Published"),
                    ("ARTICLE_REVISION_DRAFTED", "Article Revision Drafted"),
                    ("ARTICLE_REVISED", "Article Revised"),
                    ("FACTUAL_CORRECTION_REQUESTED", "Factual Correction Requested"),
                    ("FACTUAL_CORRECTION_PROPOSAL_SAVED", "Factual Correction Proposal Saved"),
                    ("FACTUAL_CORRECTION_PROPOSAL_PREPARED", "Factual Correction Proposal Prepared"),
                    ("FACTUAL_CORRECTION_CANCELLED", "Factual Correction Cancelled"),
                    ("FACTUAL_CORRECTION_PUBLISHED", "Factual Correction Published"),
                ],
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name="accountabilityevent",
            name="resource_type",
            field=models.CharField(
                choices=[
                    ("VERIFICATION_ASSIGNMENT", "Verification Assignment"),
                    ("ORGANIZATION_MEMBERSHIP", "Organization Membership"),
                    ("ORGANIZATION_INVITATION", "Organization Invitation"),
                    ("ORGANIZATION", "Organization"),
                    ("INSTITUTION", "Institution"),
                    ("ORGANIZATION_INSTITUTION_AFFILIATION", "Organization Institution Affiliation"),
                    ("CLAIM", "Claim"),
                    ("MODERATION_CASE", "Moderation Case"),
                    ("THREAD", "Thread"),
                    ("USER_ACCOUNT", "User Account"),
                    ("PLATFORM_STAFF_INVITATION", "Platform Staff Invitation"),
                    ("EVIDENCE_SUBMISSION", "Evidence Submission"),
                    ("ADJUDICATION_DECISION", "Adjudication Decision"),
                    ("OFFICIAL_FACT_CHECK", "Official Fact Check"),
                    ("FACTUAL_CORRECTION_REQUEST", "Factual Correction Request"),
                    ("FACTUAL_CORRECTION_PROPOSAL", "Factual Correction Proposal"),
                ],
                max_length=64,
            ),
        ),
    ]
