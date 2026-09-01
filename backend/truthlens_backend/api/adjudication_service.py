from django.db import transaction
from django.utils import timezone

from .models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
)

from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    DuplicateActiveModerationCase,
    InvalidModerationTransition,
    create_moderation_case,
    transition_moderation_case,
)


class AdjudicationError(Exception):
    pass


class InvalidAdjudicationDecision(AdjudicationError):
    pass


class AdjudicationConflict(AdjudicationError):
    pass


def get_current_adjudication_decision(
    claim,
    *,
    lock=False,
):
    queryset = AdjudicationDecision.objects.filter(
        claim=claim,
        is_current=True,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.first()


def get_active_adjudication_case(
    claim,
    *,
    lock=False,
):
    queryset = ModerationCase.objects.filter(
        case_type=(ModerationCase.CaseType.ADJUDICATION),
        claim=claim,
        status__in=ACTIVE_CASE_STATUSES,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.order_by("-created_at").first()


def get_latest_adjudication_case(
    claim,
    *,
    lock=False,
):
    queryset = ModerationCase.objects.filter(
        case_type=(ModerationCase.CaseType.ADJUDICATION),
        claim=claim,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.order_by("-created_at").first()


def ensure_adjudication_case(
    *,
    claim,
    actor=None,
    organization=None,
):
    existing_case = get_active_adjudication_case(claim)

    if existing_case:
        return existing_case

    latest_case = get_latest_adjudication_case(claim)

    if latest_case and latest_case.status == ModerationCase.Status.RESOLVED:
        return latest_case

    try:
        return create_moderation_case(
            case_type=(ModerationCase.CaseType.ADJUDICATION),
            actor=actor,
            source=(ModerationCase.Source.COMMUNITY_ESCALATION),
            claim=claim,
            organization=organization,
        )

    except DuplicateActiveModerationCase:
        existing_case = get_active_adjudication_case(claim)

        if existing_case:
            return existing_case

        raise


def _prepare_adjudication_case(
    case,
    *,
    actor,
):
    if case.status == ModerationCase.Status.RESOLVED:
        case = transition_moderation_case(
            case,
            next_status=(ModerationCase.Status.REOPENED),
            actor=actor,
            reason_code="VERDICT_REVIEW",
        )

        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=(ModerationEvent.EventType.VERDICT_REOPENED),
            from_status=(ModerationCase.Status.RESOLVED),
            to_status=(ModerationCase.Status.REOPENED),
            reason_code="VERDICT_REVIEW",
        )

    if case.status in {
        ModerationCase.Status.OPEN,
        ModerationCase.Status.REOPENED,
        ModerationCase.Status.ESCALATED,
    }:
        previous_status = case.status

        case = transition_moderation_case(
            case,
            next_status=(ModerationCase.Status.IN_REVIEW),
            actor=actor,
        )

        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=(ModerationEvent.EventType.ADJUDICATION_STARTED),
            from_status=previous_status,
            to_status=(ModerationCase.Status.IN_REVIEW),
        )

    if case.status != ModerationCase.Status.IN_REVIEW:
        raise InvalidModerationTransition(
            "Claim cannot be adjudicated while " f"its case is {case.status}."
        )

    return case


def has_adjudication_conflict(
    user,
    claim,
):
    if not user or not user.is_authenticated:
        return True

    authored_thread = claim.threads.filter(author=user).exists()

    if authored_thread:
        return True

    contributed_evidence = EvidenceSubmission.objects.filter(
        thread__claim=claim,
        contributor=user,
    ).exists()

    return contributed_evidence


def is_claim_ready_for_adjudication(
    claim,
):
    evidence = EvidenceSubmission.objects.filter(thread__claim=claim)

    # A claim with no community evidence
    # is not automatically adjudication-ready.
    if not evidence.exists():
        return False

    # Every submitted evidence item must
    # have received a human review.
    if evidence.filter(
        evidence_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED)
    ).exists():
        return False

    # Defensive check: no Evidence case
    # may still be operationally active.
    if ModerationCase.objects.filter(
        case_type=(ModerationCase.CaseType.EVIDENCE),
        evidence_submission__thread__claim=claim,
        status__in=ACTIVE_CASE_STATUSES,
    ).exists():
        return False

    return True


def ensure_claim_adjudication_readiness(
    *,
    claim,
    actor=None,
):
    if not is_claim_ready_for_adjudication(claim):
        return None

    # Already has an authoritative human
    # verdict. Revisions are opened explicitly,
    # not automatically by ordinary evidence
    # completion.
    if get_current_adjudication_decision(claim):
        return None

    return ensure_adjudication_case(
        claim=claim,
        actor=actor,
    )


def issue_adjudication_decision(
    *,
    claim,
    actor,
    verdict,
    canonical_claim,
    rationale,
    organization=None,
    verification_run=None,
    expected_revision=None,
):
    valid_verdicts = {value for value, _label in AdjudicationDecision.Verdict.choices}

    if verdict not in valid_verdicts:
        raise InvalidAdjudicationDecision("Invalid adjudication verdict.")

    canonical_claim = (canonical_claim or "").strip()

    rationale = (rationale or "").strip()

    if not canonical_claim:
        raise InvalidAdjudicationDecision("A canonical claim statement " "is required.")

    if not rationale:
        raise InvalidAdjudicationDecision("A decision rationale is required.")

    with transaction.atomic():
        locked_claim = Claim.objects.select_for_update().get(pk=claim.pk)

        current_decision = get_current_adjudication_decision(
            locked_claim,
            lock=True,
        )

        current_revision = current_decision.revision_number if current_decision else 0

        if expected_revision is not None and expected_revision != current_revision:
            raise AdjudicationConflict(
                "This claim's adjudication "
                "changed after the review "
                "was opened. Refresh it "
                "before deciding."
            )

        if (
            verification_run is not None
            and verification_run.claim_id != locked_claim.id
        ):
            raise InvalidAdjudicationDecision(
                "The VerificationRun does not " "belong to this claim."
            )

        case = ensure_adjudication_case(
            claim=locked_claim,
            actor=actor,
            organization=organization,
        )

        if (
            organization is not None
            and case.organization_id is not None
            and case.organization_id != organization.id
        ):
            raise InvalidAdjudicationDecision(
                "The adjudication case belongs " "to a different organization."
            )

        case = _prepare_adjudication_case(
            case,
            actor=actor,
        )

        revision_number = current_revision + 1

        if current_decision:
            current_decision.is_current = False

            current_decision.save(
                update_fields=[
                    "is_current",
                ]
            )

        pipeline_version = (
            verification_run.pipeline_version if verification_run else None
        )

        decision = AdjudicationDecision.objects.create(
            claim=locked_claim,
            moderation_case=case,
            verdict=verdict,
            canonical_claim=canonical_claim,
            rationale=rationale,
            decided_by=actor,
            organization=case.organization,
            verification_run=(verification_run),
            ai_verdict_snapshot=(locked_claim.ai_verdict),
            ai_confidence_snapshot=(locked_claim.consensus_score),
            ai_summary_snapshot=(locked_claim.ai_summary),
            ai_pipeline_version_snapshot=(pipeline_version),
            revision_number=(revision_number),
            supersedes=(current_decision),
            is_current=True,
        )

        locked_claim.final_verdict = verdict
        locked_claim.last_updated = timezone.now()

        locked_claim.save(
            update_fields=[
                "final_verdict",
                "last_updated",
            ]
        )

        event_type = (
            ModerationEvent.EventType.VERDICT_REVISED
            if current_decision
            else (ModerationEvent.EventType.VERDICT_ISSUED)
        )

        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=event_type,
            from_status=case.status,
            to_status=case.status,
            reason_code=verdict,
            notes=rationale,
            metadata={
                "decision_id": str(decision.id),
                "revision_number": revision_number,
                "previous_decision_id": (
                    str(current_decision.id) if current_decision else None
                ),
                "previous_verdict": (
                    current_decision.verdict if current_decision else None
                ),
                "ai_verdict_snapshot": locked_claim.ai_verdict,
                "ai_agreement": (
                    locked_claim.ai_verdict == verdict
                    if locked_claim.ai_verdict
                    else None
                ),
            },
        )

        case = transition_moderation_case(
            case,
            next_status=(ModerationCase.Status.RESOLVED),
            actor=actor,
            reason_code=verdict,
            notes=rationale,
            resolution_code=verdict,
            resolution_summary=rationale,
        )

        return {
            "decision": decision,
            "case": case,
            "claim": locked_claim,
        }
