import logging

from django.db import transaction
from django.utils import timezone

from .adjudication_provenance import get_current_adjudication_decision
from .models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationRun,
)
from .moderation_service import (
    ACTIVE_CASE_STATUSES,
    DuplicateActiveModerationCase,
    create_moderation_case,
    transition_moderation_case,
)
from .organization_service import (
    PartnerCapability,
    get_membership_capabilities,
)
from .verification_assignment_service import get_active_verification_assignment


logger = logging.getLogger(__name__)


class AdjudicationError(Exception):
    pass


class AdjudicationAuthorizationError(AdjudicationError):
    pass


class InvalidAdjudicationDecision(AdjudicationError):
    pass


class AdjudicationConflict(AdjudicationError):
    pass


class AdjudicationNotFound(AdjudicationError):
    pass


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
        queryset = queryset.select_for_update(of=("self",))

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
        queryset = queryset.select_for_update(of=("self",))

    return queryset.order_by("-created_at").first()


def ensure_adjudication_case(
    *,
    claim,
    actor=None,
    organization=None,
):
    existing_case = get_active_adjudication_case(claim)

    if existing_case:
        if organization is not None:
            if (
                existing_case.organization_id
                and existing_case.organization_id != organization.id
            ):
                raise AdjudicationConflict(
                    "This adjudication case belongs " "to another organization."
                )

            if existing_case.organization_id is None:
                existing_case.organization = organization

                existing_case.save(
                    update_fields=[
                        "organization",
                        "updated_at",
                    ]
                )

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
            if organization is not None:
                if (
                    existing_case.organization_id
                    and existing_case.organization_id != organization.id
                ):
                    raise AdjudicationConflict(
                        "This adjudication case belongs " "to another organization."
                    )

                if existing_case.organization_id is None:
                    existing_case.organization = organization

                    existing_case.save(
                        update_fields=[
                            "organization",
                            "updated_at",
                        ]
                    )

            return existing_case

        raise


def _prepare_first_adjudication_case(case, *, actor):
    if case.status == ModerationCase.Status.REOPENED:
        raise AdjudicationConflict(
            "A reopened Adjudication case requires the future correction workflow."
        )

    if case.status in {
        ModerationCase.Status.OPEN,
        ModerationCase.Status.ESCALATED,
    }:
        previous_status = case.status
        case = transition_moderation_case(
            case,
            next_status=ModerationCase.Status.IN_REVIEW,
            actor=actor,
        )
        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=ModerationEvent.EventType.ADJUDICATION_STARTED,
            from_status=previous_status,
            to_status=ModerationCase.Status.IN_REVIEW,
        )

    if case.status != ModerationCase.Status.IN_REVIEW:
        raise AdjudicationConflict(
            f"Claim cannot be adjudicated while its case is {case.status}."
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
    organization=None,
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
        organization=organization,
    )


def _lock_case_claim_identity(case_id):
    identity = (
        ModerationCase.objects.filter(
            pk=case_id,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim__isnull=False,
        )
        .values("claim_id")
        .first()
    )
    if identity is None:
        raise AdjudicationNotFound("Adjudication case not found.")

    try:
        return Claim.objects.select_for_update().get(pk=identity["claim_id"])
    except Claim.DoesNotExist as error:
        raise AdjudicationNotFound("Adjudication case not found.") from error


def _lock_adjudication_context(*, case_id, organization_id, actor):
    """Lock the complete first-decision context in its canonical order."""

    locked_claim = _lock_case_claim_identity(case_id)

    assignment = get_active_verification_assignment(locked_claim, lock=True)
    if assignment is None:
        raise AdjudicationConflict(
            "This claim no longer has an active organization verification assignment."
        )

    try:
        organization = Organization.objects.select_for_update().get(
            pk=organization_id
        )
    except Organization.DoesNotExist as error:
        raise AdjudicationNotFound("Adjudication case not found.") from error

    case = (
        ModerationCase.objects.select_for_update(of=("self",))
        .filter(
            pk=case_id,
            case_type=ModerationCase.CaseType.ADJUDICATION,
            claim=locked_claim,
            organization=organization,
        )
        .first()
    )
    if case is None:
        raise AdjudicationNotFound("Adjudication case not found.")

    if assignment.organization_id != organization.pk:
        raise AdjudicationConflict(
            "The organization responsible for this claim changed after the "
            "review was opened."
        )

    membership = (
        OrganizationMembership.objects.select_related("organization")
        .select_for_update(of=("self",))
        .filter(
            organization=organization,
            user=actor,
        )
        .first()
    )
    capabilities = (
        get_membership_capabilities(membership)
        if membership is not None
        else set()
    )
    if PartnerCapability.ADJUDICATE not in capabilities:
        raise AdjudicationAuthorizationError(
            "You do not have permission to adjudicate this claim."
        )

    # The Claim is the shared parent lock for writer paths. Locking existing
    # children in primary-key order then gives a stable snapshot for conflict
    # and readiness checks while preventing concurrent child updates/deletes.
    threads = list(
        Thread.objects.select_for_update(of=("self",))
        .filter(claim=locked_claim)
        .order_by("pk")
    )
    evidence = list(
        EvidenceSubmission.objects.select_for_update(of=("self",))
        .filter(thread__claim=locked_claim)
        .order_by("pk")
    )
    evidence_cases = list(
        ModerationCase.objects.select_for_update(of=("self",))
        .filter(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission__thread__claim=locked_claim,
            status__in=ACTIVE_CASE_STATUSES,
        )
        .order_by("pk")
    )

    return {
        "claim": locked_claim,
        "assignment": assignment,
        "organization": organization,
        "case": case,
        "threads": threads,
        "evidence": evidence,
        "evidence_cases": evidence_cases,
    }


def _ensure_locked_readiness(context):
    evidence = context["evidence"]
    if not evidence:
        raise AdjudicationConflict(
            "At least one reviewed evidence submission is required before adjudication."
        )
    if any(
        item.evidence_status == EvidenceSubmission.EvidenceStatus.UNVERIFIED
        for item in evidence
    ):
        raise AdjudicationConflict(
            "Every evidence submission must be reviewed before adjudication."
        )
    if context["evidence_cases"]:
        raise AdjudicationConflict("An Evidence case is still active for this claim.")


def _resolve_completed_verification_run(*, verification_run_id, claim):
    if verification_run_id is None:
        return None

    run = (
        VerificationRun.objects.select_for_update(of=("self",))
        .filter(
            pk=verification_run_id,
            claim=claim,
        )
        .first()
    )
    if run is None:
        raise AdjudicationNotFound("Verification run not found.")
    if run.status != VerificationRun.Status.COMPLETED:
        raise AdjudicationConflict("The selected VerificationRun is not complete.")
    return run


def issue_adjudication_decision(
    *,
    case_id,
    organization_id,
    actor,
    verdict,
    canonical_claim,
    rationale,
    expected_revision,
    verification_run_id=None,
):
    valid_verdicts = {
        value for value, _label in AdjudicationDecision.Verdict.choices
    }
    if verdict not in valid_verdicts:
        raise InvalidAdjudicationDecision("Invalid adjudication verdict.")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 0
    ):
        raise InvalidAdjudicationDecision(
            "expected_revision must be a nonnegative integer."
        )

    canonical_claim = (canonical_claim or "").strip()
    rationale = (rationale or "").strip()
    if not canonical_claim:
        raise InvalidAdjudicationDecision("A canonical claim statement is required.")
    if not rationale:
        raise InvalidAdjudicationDecision("A decision rationale is required.")
    if not actor or not actor.is_authenticated:
        raise AdjudicationAuthorizationError(
            "Authentication is required to adjudicate a claim."
        )

    with transaction.atomic():
        context = _lock_adjudication_context(
            case_id=case_id,
            organization_id=organization_id,
            actor=actor,
        )
        locked_claim = context["claim"]
        case = context["case"]

        if case.status not in ACTIVE_CASE_STATUSES:
            raise AdjudicationConflict("This Adjudication case is no longer active.")

        current_decision = get_current_adjudication_decision(
            locked_claim,
            lock=True,
        )
        current_revision = current_decision.revision_number if current_decision else 0
        if expected_revision != current_revision:
            raise AdjudicationConflict(
                "This claim's adjudication changed after the review was opened. "
                "Refresh it before deciding."
            )
        if current_decision is not None:
            raise AdjudicationConflict(
                "This claim already has an authoritative decision. An explicit "
                "correction workflow is required before it can change."
            )

        _ensure_locked_readiness(context)

        if any(thread.author_id == actor.id for thread in context["threads"]):
            raise AdjudicationAuthorizationError(
                "You cannot adjudicate a claim in which you have a direct contribution."
            )
        if any(item.contributor_id == actor.id for item in context["evidence"]):
            raise AdjudicationAuthorizationError(
                "You cannot adjudicate a claim in which you have a direct contribution."
            )

        verification_run = _resolve_completed_verification_run(
            verification_run_id=verification_run_id,
            claim=locked_claim,
        )
        case = _prepare_first_adjudication_case(case, actor=actor)

        decision = AdjudicationDecision.objects.create(
            claim=locked_claim,
            moderation_case=case,
            verdict=verdict,
            canonical_claim=canonical_claim,
            rationale=rationale,
            decided_by=actor,
            organization=context["organization"],
            verification_run=verification_run,
            ai_verdict_snapshot=locked_claim.ai_verdict,
            ai_confidence_snapshot=locked_claim.consensus_score,
            ai_summary_snapshot=locked_claim.ai_summary,
            ai_pipeline_version_snapshot=(
                verification_run.pipeline_version if verification_run else None
            ),
            revision_number=1,
            supersedes=None,
            is_current=True,
        )

        locked_claim.final_verdict = verdict
        locked_claim.last_updated = timezone.now()
        locked_claim.save(update_fields=["final_verdict", "last_updated"])

        ModerationEvent.objects.create(
            case=case,
            actor=actor,
            event_type=ModerationEvent.EventType.VERDICT_ISSUED,
            from_status=case.status,
            to_status=case.status,
            reason_code=verdict,
            notes=rationale,
            metadata={
                "decision_id": str(decision.id),
                "revision_number": 1,
                "previous_decision_id": None,
                "previous_verdict": None,
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
            next_status=ModerationCase.Status.RESOLVED,
            actor=actor,
            reason_code=verdict,
            notes=rationale,
            resolution_code=verdict,
            resolution_summary=rationale,
        )

        thread_ids = [
            thread.pk
            for thread in context["threads"]
            if thread.status != Thread.Status.REJECTED
        ]
        if thread_ids:
            Thread.objects.filter(pk__in=thread_ids).update(
                moderator_verdict=decision.verdict,
                moderator_notes=decision.rationale,
                moderated_by=actor,
                moderated_at=decision.decided_at,
            )

        contributor_ids = tuple(
            sorted({item.contributor_id for item in context["evidence"]})
        )
        return {
            "decision": decision,
            "case": case,
            "claim": locked_claim,
            "contributor_ids": contributor_ids,
        }


def schedule_adjudication_trust_updates(result):
    contributor_ids = tuple(result.get("contributor_ids", ()))
    if not contributor_ids:
        return

    claim_id = getattr(result.get("claim"), "pk", None)
    case_id = getattr(result.get("case"), "pk", None)
    decision_id = getattr(result.get("decision"), "pk", None)

    def dispatch_trust_updates():
        try:
            from .tasks import recompute_user_trust_score_task
        except Exception:
            logger.exception(
                "Failed to load the post-commit Adjudication trust task for "
                "claim_id=%s case_id=%s decision_id=%s.",
                claim_id,
                case_id,
                decision_id,
            )
            return

        for user_id in contributor_ids:
            try:
                recompute_user_trust_score_task.delay(user_id)
            except Exception:
                logger.exception(
                    "Failed to enqueue post-commit Adjudication trust "
                    "recomputation for user_id=%s claim_id=%s case_id=%s "
                    "decision_id=%s.",
                    user_id,
                    claim_id,
                    case_id,
                    decision_id,
                )

    transaction.on_commit(dispatch_trust_updates, robust=True)
