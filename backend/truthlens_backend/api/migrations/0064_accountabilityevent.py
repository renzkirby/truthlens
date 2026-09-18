# Generated manually for the TruthLens 4J-A checkpoint.

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api", "0063_officialfactcheck_edit_generation_and_publication_events"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountabilityEvent",
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
                ("actor_username_snapshot", models.CharField(blank=True, max_length=150)),
                (
                    "authority_scope",
                    models.CharField(
                        choices=[
                            ("PERSONAL", "Personal"),
                            ("ORGANIZATION", "Organization"),
                            ("PLATFORM", "Platform"),
                            ("SYSTEM", "System"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "authority_organization_name_snapshot",
                    models.CharField(blank=True, max_length=255),
                ),
                (
                    "subject_organization_name_snapshot",
                    models.CharField(blank=True, max_length=255),
                ),
                ("capability", models.CharField(blank=True, max_length=64)),
                (
                    "action_type",
                    models.CharField(
                        choices=[
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
                (
                    "resource_type",
                    models.CharField(
                        choices=[
                            ("VERIFICATION_ASSIGNMENT", "Verification Assignment"),
                            ("ORGANIZATION_MEMBERSHIP", "Organization Membership"),
                            ("ORGANIZATION_INVITATION", "Organization Invitation"),
                            ("ORGANIZATION", "Organization"),
                            ("MODERATION_CASE", "Moderation Case"),
                            ("THREAD", "Thread"),
                            ("EVIDENCE_SUBMISSION", "Evidence Submission"),
                            ("ADJUDICATION_DECISION", "Adjudication Decision"),
                            ("OFFICIAL_FACT_CHECK", "Official Fact Check"),
                            ("FACTUAL_CORRECTION_REQUEST", "Factual Correction Request"),
                            ("FACTUAL_CORRECTION_PROPOSAL", "Factual Correction Proposal"),
                        ],
                        max_length=64,
                    ),
                ),
                ("resource_id", models.CharField(max_length=255)),
                ("previous_state", models.JSONField(blank=True, default=dict)),
                ("new_state", models.JSONField(blank=True, default=dict)),
                ("reason_code", models.CharField(blank=True, max_length=100)),
                ("notes", models.TextField(blank=True)),
                ("context", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="accountability_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "authority_organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="authority_accountability_events",
                        to="api.organization",
                    ),
                ),
                (
                    "subject_organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="subject_accountability_events",
                        to="api.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["authority_scope", "-created_at"], name="acct_scope_time_idx"),
                    models.Index(fields=["authority_organization", "-created_at"], name="acct_auth_org_time_idx"),
                    models.Index(fields=["subject_organization", "-created_at"], name="acct_subject_org_time_idx"),
                    models.Index(fields=["actor", "-created_at"], name="acct_actor_time_idx"),
                    models.Index(fields=["action_type", "-created_at"], name="acct_action_time_idx"),
                    models.Index(fields=["resource_type", "resource_id", "-created_at"], name="acct_resource_time_idx"),
                ],
            },
        ),
    ]
