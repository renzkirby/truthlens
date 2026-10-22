"""Forward-only transition from governed domain+jurisdiction scopes to owner-managed subjects.

Historical approval/request/activation fields are retained but cease to authorize
new assignments. This migration does not modify claims or existing assignments.
"""
from django.db import migrations, models


def backfill_specializations(apps, schema_editor):
    Organization = apps.get_model("api", "Organization")
    db = schema_editor.connection.alias
    for organization in Organization.objects.using(db).all().iterator():
        approved = set(organization.approved_verification_domains or [])
        approved_geo = set(organization.approved_verification_jurisdictions or [])
        if organization.active_scope_configured:
            domains = approved & set(organization.active_verification_domains or [])
            geographic_scope = approved_geo & set(
                organization.active_verification_jurisdictions or []
            )
        else:
            domains = approved
            geographic_scope = approved_geo
        # Only grandfather previously effective authorization. An institution
        # without geographic scope never had claimable work under the old policy.
        organization.verification_specializations = sorted(domains) if geographic_scope else []
        organization.save(update_fields=["verification_specializations"], using=db)


class Migration(migrations.Migration):
    dependencies = [("api", "0084_claim_classification_actor_optional")]

    operations = [
        migrations.AddField(
            model_name="organization", name="verification_specializations",
            field=models.JSONField(
                default=list, blank=True,
                help_text="Primary Admin-managed subject specializations for new partner intake.",
            ),
        ),
        migrations.AlterField(
            model_name="claiminvestigationclassification", name="jurisdiction",
            field=models.CharField(max_length=32, blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="accountabilityevent", name="action_type",
            field=models.CharField(max_length=64, choices=[("ORGANIZATION_CREATED", "Organization Created"), ("ORGANIZATION_PLATFORM_TRUST_UPDATED", "Organization Platform Trust Updated"), ("ORGANIZATION_VERIFICATION_SCOPE_APPROVED", "Organization Verification Scope Approved"), ("ORGANIZATION_VERIFICATION_SCOPE_REQUESTED", "Organization Verification Scope Requested"), ("ORGANIZATION_VERIFICATION_SCOPE_ACTIVATED", "Organization Verification Scope Activated"), ("ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED", "Organization Verification Specializations Updated"), ("CLAIM_INVESTIGATION_CLASSIFIED", "Claim Investigation Classified"), ("VERIFICATION_ASSIGNMENT_CREATED", "Verification Assignment Created"), ("VERIFICATION_ASSIGNMENT_CLAIMED", "Verification Assignment Claimed"), ("VERIFICATION_ASSIGNMENT_RELEASED", "Verification Assignment Released"), ("VERIFICATION_ASSIGNMENT_COMPLETED", "Verification Assignment Completed"), ("ORGANIZATION_MEMBERSHIP_ROLE_CHANGED", "Organization Membership Role Changed"), ("ORGANIZATION_MEMBERSHIP_SUSPENDED", "Organization Membership Suspended"), ("ORGANIZATION_MEMBERSHIP_RESTORED", "Organization Membership Restored"), ("ORGANIZATION_MEMBERSHIP_REMOVED", "Organization Membership Removed"), ("ORGANIZATION_INVITATION_CREATED", "Organization Invitation Created"), ("ORGANIZATION_INVITATION_RESENT", "Organization Invitation Resent"), ("ORGANIZATION_INVITATION_CANCELLED", "Organization Invitation Cancelled"), ("ORGANIZATION_INVITATION_ACCEPTED", "Organization Invitation Accepted"), ("ORGANIZATION_INVITATION_EXPIRED", "Organization Invitation Expired"), ("ORGANIZATION_PUBLIC_PROFILE_UPDATED", "Organization Public Profile Updated"), ("ORGANIZATION_LOGO_UPDATED", "Organization Logo Updated"), ("ORGANIZATION_LOGO_REMOVED", "Organization Logo Removed"), ("SAFETY_CASE_CLAIMED", "Safety Case Claimed"), ("SAFETY_CASE_RELEASED", "Safety Case Released"), ("SAFETY_CASE_ESCALATED", "Safety Case Escalated"), ("SAFETY_DISMISSED", "Safety Dismissed"), ("SAFETY_CONTENT_REMOVED", "Safety Content Removed"), ("EVIDENCE_REOPENED", "Evidence Reopened"), ("EVIDENCE_VERIFIED", "Evidence Verified"), ("EVIDENCE_REJECTED", "Evidence Rejected"), ("ADJUDICATION_STARTED", "Adjudication Started"), ("VERDICT_ISSUED", "Verdict Issued"), ("VERDICT_REVISED", "Verdict Revised"), ("ARTICLE_DRAFT_CREATED", "Article Draft Created"), ("ARTICLE_DRAFT_SAVED", "Article Draft Saved"), ("ARTICLE_SUBMITTED", "Article Submitted"), ("ARTICLE_RETURNED_FOR_REWORK", "Article Returned For Rework"), ("ARTICLE_ABANDONED", "Article Abandoned"), ("ARTICLE_PUBLISHED", "Article Published"), ("ARTICLE_REVISION_DRAFTED", "Article Revision Drafted"), ("ARTICLE_REVISED", "Article Revised"), ("FACTUAL_CORRECTION_REQUESTED", "Factual Correction Requested"), ("FACTUAL_CORRECTION_PROPOSAL_SAVED", "Factual Correction Proposal Saved"), ("FACTUAL_CORRECTION_PROPOSAL_PREPARED", "Factual Correction Proposal Prepared"), ("FACTUAL_CORRECTION_CANCELLED", "Factual Correction Cancelled"), ("FACTUAL_CORRECTION_PUBLISHED", "Factual Correction Published")]),
        ),
        migrations.RunPython(backfill_specializations, migrations.RunPython.noop),
    ]
