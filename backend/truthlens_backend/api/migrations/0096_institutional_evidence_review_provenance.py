from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


def backfill_institutional_evidence_reviews(apps, schema_editor):
    EvidenceReviewDecision = apps.get_model("api", "EvidenceReviewDecision")
    ModerationCase = apps.get_model("api", "ModerationCase")
    ModerationEvent = apps.get_model("api", "ModerationEvent")

    cases = (
        ModerationCase.objects.filter(
            case_type="EVIDENCE",
            status="RESOLVED",
            organization_id__isnull=False,
            evidence_submission_id__isnull=False,
            resolution_code__in=["VERIFIED", "REJECTED"],
        )
        .select_related("organization", "resolved_by")
        .order_by("created_at", "id")
    )

    valid_rejection_reasons = {
        "IRRELEVANT",
        "UNRELIABLE_SOURCE",
        "INACCESSIBLE_SOURCE",
        "DUPLICATE",
        "OUTDATED",
        "MISREPRESENTS_SOURCE",
        "INSUFFICIENT_CONTEXT",
        "FABRICATED",
        "OTHER",
    }

    for case in cases.iterator():
        if EvidenceReviewDecision.objects.filter(
            moderation_case_id=case.id
        ).exists():
            continue

        review_event = (
            ModerationEvent.objects.filter(
                case_id=case.id,
                event_type__in=["EVIDENCE_VERIFIED", "EVIDENCE_REJECTED"],
            )
            .order_by("-created_at", "-id")
            .first()
        )
        rejection_reason = None
        if (
            case.resolution_code == "REJECTED"
            and review_event is not None
            and review_event.reason_code in valid_rejection_reasons
        ):
            rejection_reason = review_event.reason_code

        reviewer = case.resolved_by or (
            review_event.actor if review_event is not None else None
        )
        notes = (
            review_event.notes
            if review_event is not None and review_event.notes is not None
            else (case.resolution_summary or "")
        )

        EvidenceReviewDecision.objects.create(
            id=uuid.uuid4(),
            evidence_submission_id=case.evidence_submission_id,
            organization_id=case.organization_id,
            moderation_case_id=case.id,
            reviewed_by_id=(reviewer.id if reviewer is not None else None),
            decision_type="INDEPENDENT_REVIEW",
            disposition=case.resolution_code,
            source_review_id=None,
            notes=notes,
            rejection_reason=rejection_reason,
            organization_name_snapshot=case.organization.name,
            reviewer_username_snapshot=(
                reviewer.username if reviewer is not None else ""
            ),
            reviewed_at=(
                case.resolved_at
                or (
                    review_event.created_at
                    if review_event is not None
                    else case.updated_at
                )
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0095_reconcile_missing_evidence_cases"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EvidenceReviewDecision",
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
                    "decision_type",
                    models.CharField(
                        choices=[
                            ("INDEPENDENT_REVIEW", "Independent Review"),
                            ("PRIOR_REVIEW_ACCEPTED", "Prior Review Accepted"),
                        ],
                        default="INDEPENDENT_REVIEW",
                        max_length=32,
                    ),
                ),
                (
                    "disposition",
                    models.CharField(
                        choices=[
                            ("VERIFIED", "Verified"),
                            ("REJECTED", "Rejected"),
                        ],
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "rejection_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("IRRELEVANT", "Irrelevant"),
                            ("UNRELIABLE_SOURCE", "Unreliable Source"),
                            ("INACCESSIBLE_SOURCE", "Inaccessible Source"),
                            ("DUPLICATE", "Duplicate"),
                            ("OUTDATED", "Outdated"),
                            ("MISREPRESENTS_SOURCE", "Misrepresents Source"),
                            ("INSUFFICIENT_CONTEXT", "Insufficient Context"),
                            ("FABRICATED", "Fabricated"),
                            ("OTHER", "Other"),
                        ],
                        max_length=30,
                        null=True,
                    ),
                ),
                (
                    "organization_name_snapshot",
                    models.CharField(editable=False, max_length=255),
                ),
                (
                    "reviewer_username_snapshot",
                    models.CharField(blank=True, editable=False, max_length=150),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                        editable=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, editable=False),
                ),
                (
                    "evidence_submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="review_decisions",
                        to="api.evidencesubmission",
                    ),
                ),
                (
                    "moderation_case",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="evidence_review_decision",
                        to="api.moderationcase",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="evidence_review_decisions",
                        to="api.organization",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="institutional_evidence_review_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_review",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="accepted_by_decisions",
                        to="api.evidencereviewdecision",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["evidence_submission", "organization", "-reviewed_at"],
                        name="evrev_evid_org_time_idx",
                    ),
                    models.Index(
                        fields=["organization", "-reviewed_at"],
                        name="evrev_org_time_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("moderation_case",),
                        name="uniq_evidence_review_decision_case",
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
                    ("CLAIM_INSTITUTION_CONTEXT_UPDATED", "Claim Institution Context Updated"),
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
                    ("EVIDENCE_PRIOR_REVIEW_ACCEPTED", "Prior Evidence Review Accepted"),
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
        migrations.CreateModel(
            name="AdjudicationDecisionEvidenceReviewBasis",
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
                    "captured_at",
                    models.DateTimeField(auto_now_add=True, editable=False),
                ),
                (
                    "decision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="evidence_review_basis",
                        to="api.adjudicationdecision",
                    ),
                ),
                (
                    "evidence_submission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="adjudication_review_basis",
                        to="api.evidencesubmission",
                    ),
                ),
                (
                    "review_decision",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="adjudication_basis_records",
                        to="api.evidencereviewdecision",
                    ),
                ),
            ],
            options={
                "ordering": ["captured_at", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("decision", "evidence_submission"),
                        name="uniq_adj_dec_evidence_review_basis",
                    )
                ],
            },
        ),
        migrations.RunPython(
            backfill_institutional_evidence_reviews,
            migrations.RunPython.noop,
        ),
    ]
