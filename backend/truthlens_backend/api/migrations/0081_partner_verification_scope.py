# PARTNER-GOV-1: preserve existing claims, assignments, and published verification history.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone

class Migration(migrations.Migration):
    dependencies = [
        ("api", "0080_verificationtelemetryevent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="approved_verification_domains",
            field=models.JSONField(
                default=list, blank=True,
                help_text="Platform-approved investigation domains, distinct from public expertise_areas.",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="approved_verification_jurisdictions",
            field=models.JSONField(
                default=list, blank=True,
                help_text="Platform-approved ISO-style geographic scopes.",
            ),
        ),
        migrations.CreateModel(
            name="ClaimInvestigationClassification",
            fields=[
                ("claim", models.OneToOneField(
                    to="api.claim", on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True, related_name="investigation_classification",
                    serialize=False,
                )),
                ("domains", models.JSONField(default=list)),
                ("jurisdiction", models.CharField(max_length=32)),
                ("rationale", models.TextField(max_length=2000)),
                ("classified_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("classified_by", models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL,
                    null=True, related_name="investigation_classifications",
                )),
            ],
        ),
        migrations.AlterField(
            model_name="accountabilityevent",
            name="action_type",
            field=models.CharField(max_length=64, choices=[("ORGANIZATION_CREATED", "Organization Created"), ("ORGANIZATION_PLATFORM_TRUST_UPDATED", "Organization Platform Trust Updated"), ("ORGANIZATION_VERIFICATION_SCOPE_APPROVED", "Organization Verification Scope Approved"), ("CLAIM_INVESTIGATION_CLASSIFIED", "Claim Investigation Classified"), ("VERIFICATION_ASSIGNMENT_CREATED", "Verification Assignment Created"), ("VERIFICATION_ASSIGNMENT_CLAIMED", "Verification Assignment Claimed"), ("VERIFICATION_ASSIGNMENT_RELEASED", "Verification Assignment Released"), ("VERIFICATION_ASSIGNMENT_COMPLETED", "Verification Assignment Completed"), ("ORGANIZATION_MEMBERSHIP_ROLE_CHANGED", "Organization Membership Role Changed"), ("ORGANIZATION_MEMBERSHIP_SUSPENDED", "Organization Membership Suspended"), ("ORGANIZATION_MEMBERSHIP_RESTORED", "Organization Membership Restored"), ("ORGANIZATION_MEMBERSHIP_REMOVED", "Organization Membership Removed"), ("ORGANIZATION_INVITATION_CREATED", "Organization Invitation Created"), ("ORGANIZATION_INVITATION_RESENT", "Organization Invitation Resent"), ("ORGANIZATION_INVITATION_CANCELLED", "Organization Invitation Cancelled"), ("ORGANIZATION_INVITATION_ACCEPTED", "Organization Invitation Accepted"), ("ORGANIZATION_INVITATION_EXPIRED", "Organization Invitation Expired"), ("ORGANIZATION_PUBLIC_PROFILE_UPDATED", "Organization Public Profile Updated"), ("ORGANIZATION_LOGO_UPDATED", "Organization Logo Updated"), ("ORGANIZATION_LOGO_REMOVED", "Organization Logo Removed"), ("SAFETY_CASE_CLAIMED", "Safety Case Claimed"), ("SAFETY_CASE_RELEASED", "Safety Case Released"), ("SAFETY_CASE_ESCALATED", "Safety Case Escalated"), ("SAFETY_DISMISSED", "Safety Dismissed"), ("SAFETY_CONTENT_REMOVED", "Safety Content Removed"), ("EVIDENCE_REOPENED", "Evidence Reopened"), ("EVIDENCE_VERIFIED", "Evidence Verified"), ("EVIDENCE_REJECTED", "Evidence Rejected"), ("ADJUDICATION_STARTED", "Adjudication Started"), ("VERDICT_ISSUED", "Verdict Issued"), ("VERDICT_REVISED", "Verdict Revised"), ("ARTICLE_DRAFT_CREATED", "Article Draft Created"), ("ARTICLE_DRAFT_SAVED", "Article Draft Saved"), ("ARTICLE_SUBMITTED", "Article Submitted"), ("ARTICLE_RETURNED_FOR_REWORK", "Article Returned For Rework"), ("ARTICLE_ABANDONED", "Article Abandoned"), ("ARTICLE_PUBLISHED", "Article Published"), ("ARTICLE_REVISION_DRAFTED", "Article Revision Drafted"), ("ARTICLE_REVISED", "Article Revised"), ("FACTUAL_CORRECTION_REQUESTED", "Factual Correction Requested"), ("FACTUAL_CORRECTION_PROPOSAL_SAVED", "Factual Correction Proposal Saved"), ("FACTUAL_CORRECTION_PROPOSAL_PREPARED", "Factual Correction Proposal Prepared"), ("FACTUAL_CORRECTION_CANCELLED", "Factual Correction Cancelled"), ("FACTUAL_CORRECTION_PUBLISHED", "Factual Correction Published")]),
        ),
        migrations.AlterField(
            model_name="accountabilityevent",
            name="resource_type",
            field=models.CharField(max_length=64, choices=[("VERIFICATION_ASSIGNMENT", "Verification Assignment"), ("ORGANIZATION_MEMBERSHIP", "Organization Membership"), ("ORGANIZATION_INVITATION", "Organization Invitation"), ("ORGANIZATION", "Organization"), ("CLAIM", "Claim"), ("MODERATION_CASE", "Moderation Case"), ("THREAD", "Thread"), ("EVIDENCE_SUBMISSION", "Evidence Submission"), ("ADJUDICATION_DECISION", "Adjudication Decision"), ("OFFICIAL_FACT_CHECK", "Official Fact Check"), ("FACTUAL_CORRECTION_REQUEST", "Factual Correction Request"), ("FACTUAL_CORRECTION_PROPOSAL", "Factual Correction Proposal")]),
        ),
    ]
