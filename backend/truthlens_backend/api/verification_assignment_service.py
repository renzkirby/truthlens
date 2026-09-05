from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    OfficialFactCheck,
    VerificationAssignment,
)
from .moderation_service import ACTIVE_CASE_STATUSES
from .organization_service import (
    PartnerCapability,
    has_capability,
)

OPEN_ASSIGNMENT_STATUSES = {
    VerificationAssignment.Status.AVAILABLE,
    VerificationAssignment.Status.ACTIVE,
}


class VerificationAssignmentError(Exception):
    pass


class VerificationAssignmentConflict(VerificationAssignmentError):
    pass


class VerificationAssignmentAuthorizationError(VerificationAssignmentError):
    pass


class VerificationAssignmentReleaseBlocked(VerificationAssignmentError):
    pass


def get_open_verification_assignment(
    claim,
    *,
    lock=False,
):
    queryset = VerificationAssignment.objects.filter(
        claim=claim,
        status__in=OPEN_ASSIGNMENT_STATUSES,
    )

    if lock:
        queryset = queryset.select_for_update()
    else:
        queryset = queryset.select_related(
            "claim",
            "organization",
            "claimed_by",
        )

    return queryset.order_by("-created_at").first()


def get_active_verification_assignment(
    claim,
    *,
    lock=False,
):
    queryset = VerificationAssignment.objects.filter(
        claim=claim,
        status=VerificationAssignment.Status.ACTIVE,
    )

    if lock:
        queryset = queryset.select_for_update()
    else:
        queryset = queryset.select_related(
            "claim",
            "organization",
            "claimed_by",
        )

    return queryset.order_by("-created_at").first()


def get_claim_verification_organization(
    claim,
    *,
    lock=False,
):
    """
    Return the organization currently responsible
    for this claim's verification work.

    When lock=True, lock the open assignment row so
    claiming/releasing cannot race with factual-review
    case creation.
    """

    assignment = get_open_verification_assignment(
        claim,
        lock=lock,
    )

    if not assignment or assignment.status != VerificationAssignment.Status.ACTIVE:
        return None

    return assignment.organization


def get_available_verification_assignments():
    """
    Return the shared verification intake pool.

    AVAILABLE work has not yet been accepted by
    any partner organization.
    """

    return (
        VerificationAssignment.objects.filter(
            status=(VerificationAssignment.Status.AVAILABLE),
            organization__isnull=True,
        )
        .select_related(
            "claim",
            "organization",
            "claimed_by",
        )
        .prefetch_related(
            "claim__threads",
        )
        .order_by("-created_at")
    )


def get_organization_verification_workload(
    organization,
):
    """
    Return active factual-verification work currently
    owned by one partner organization.
    """

    return (
        VerificationAssignment.objects.filter(
            organization=organization,
            status=(VerificationAssignment.Status.ACTIVE),
        )
        .select_related(
            "claim",
            "organization",
            "claimed_by",
        )
        .prefetch_related(
            "claim__threads",
        )
        .order_by(
            "-claimed_at",
            "-created_at",
        )
    )


def ensure_verification_assignment(
    *,
    claim,
):
    """
    Ensure that an unresolved claim has one open
    verification intake assignment.

    AVAILABLE means the claim may be claimed by an
    eligible partner organization.

    Claims that already have an authoritative final
    verdict are not automatically reopened.
    """

    with transaction.atomic():
        locked_claim = Claim.objects.select_for_update().get(pk=claim.pk)

        existing = get_open_verification_assignment(
            locked_claim,
            lock=True,
        )

        if existing:
            return existing

        # Finalized claims require an explicit future
        # revision/reopen workflow rather than silently
        # returning to the public intake queue.
        if locked_claim.final_verdict:
            return None

        try:
            # Inner savepoint lets us safely recover from
            # a concurrent create hitting the partial
            # unique constraint.
            with transaction.atomic():
                assignment = VerificationAssignment.objects.create(
                    claim=locked_claim,
                    status=(VerificationAssignment.Status.AVAILABLE),
                )

        except IntegrityError:
            assignment = get_open_verification_assignment(
                locked_claim,
                lock=True,
            )

            if assignment:
                return assignment

            raise

        return assignment


def _attach_active_cases_to_organization(
    *,
    claim,
    organization,
):
    """
    Attach currently active factual-review cases
    to the organization that accepted responsibility
    for this claim.

    Safety cases are intentionally excluded.
    """

    evidence_cases = list(
        ModerationCase.objects.select_for_update().filter(
            case_type=(ModerationCase.CaseType.EVIDENCE),
            evidence_submission__thread__claim=claim,
            status__in=ACTIVE_CASE_STATUSES,
        )
    )

    adjudication_cases = list(
        ModerationCase.objects.select_for_update().filter(
            case_type=(ModerationCase.CaseType.ADJUDICATION),
            claim=claim,
            status__in=ACTIVE_CASE_STATUSES,
        )
    )

    cases = evidence_cases + adjudication_cases

    for case in cases:
        if case.organization_id and case.organization_id != organization.id:
            raise VerificationAssignmentConflict(
                "An active verification case already "
                "belongs to another organization."
            )

        if case.organization_id is None:
            case.organization = organization

            case.save(
                update_fields=[
                    "organization",
                    "updated_at",
                ]
            )


def claim_verification_assignment(
    *,
    assignment,
    organization,
    actor,
):
    """
    Claim AVAILABLE verification work on behalf of
    a verified partner organization.

    Only a member with CLAIM_VERIFICATION_WORK for
    that specific organization may accept the work.
    """

    if not actor or not actor.is_authenticated:
        raise VerificationAssignmentAuthorizationError("Authentication is required.")

    if not has_capability(
        actor,
        PartnerCapability.CLAIM_VERIFICATION_WORK,
        organization=organization,
    ):
        raise VerificationAssignmentAuthorizationError(
            "You do not have permission to accept "
            "verification work for this organization."
        )

    with transaction.atomic():
        locked_assignment = VerificationAssignment.objects.select_for_update().get(
            pk=assignment.pk
        )

        # Idempotent response when the same organization
        # already owns the work.
        if (
            locked_assignment.status == VerificationAssignment.Status.ACTIVE
            and locked_assignment.organization_id == organization.id
        ):
            return locked_assignment

        if locked_assignment.status != VerificationAssignment.Status.AVAILABLE:
            raise VerificationAssignmentConflict(
                "This verification assignment is no " "longer available."
            )

        if locked_assignment.organization_id is not None:
            raise VerificationAssignmentConflict(
                "Available verification work must not "
                "already belong to an organization."
            )

        locked_assignment.organization = organization
        locked_assignment.claimed_by = actor
        locked_assignment.status = VerificationAssignment.Status.ACTIVE
        locked_assignment.claimed_at = timezone.now()
        locked_assignment.released_at = None

        locked_assignment.full_clean()

        locked_assignment.save(
            update_fields=[
                "organization",
                "claimed_by",
                "status",
                "claimed_at",
                "released_at",
                "updated_at",
            ]
        )

        _attach_active_cases_to_organization(
            claim=locked_assignment.claim,
            organization=organization,
        )

        return locked_assignment


def _claim_has_started_authoritative_work(claim):
    reviewed_evidence_exists = (
        EvidenceSubmission.objects.filter(thread__claim=claim)
        .exclude(evidence_status=(EvidenceSubmission.EvidenceStatus.UNVERIFIED))
        .exists()
    )

    if reviewed_evidence_exists:
        return True

    started_cases_exist = (
        ModerationCase.objects.filter(
            status__in={
                ModerationCase.Status.IN_REVIEW,
                ModerationCase.Status.ESCALATED,
                ModerationCase.Status.REOPENED,
            }
        )
        .filter(
            Q(
                case_type=ModerationCase.CaseType.EVIDENCE,
                evidence_submission__thread__claim=claim,
            )
            | Q(
                case_type=(ModerationCase.CaseType.ADJUDICATION),
                claim=claim,
            )
        )
        .exists()
    )

    if started_cases_exist:
        return True

    if AdjudicationDecision.objects.filter(claim=claim).exists():
        return True

    if OfficialFactCheck.objects.filter(claim=claim).exists():
        return True

    return False


def release_verification_assignment(
    *,
    assignment,
    actor,
):
    """
    Release an ACTIVE assignment back into intake.

    Release is permitted only before authoritative
    factual-review work has begun.
    """

    if not actor or not actor.is_authenticated:
        raise VerificationAssignmentAuthorizationError("Authentication is required.")

    with transaction.atomic():
        locked_assignment = VerificationAssignment.objects.select_for_update().get(
            pk=assignment.pk
        )

        if locked_assignment.status != VerificationAssignment.Status.ACTIVE:
            raise VerificationAssignmentConflict(
                "Only active verification assignments " "can be released."
            )

        organization = locked_assignment.organization

        if organization is None:
            raise VerificationAssignmentConflict(
                "The active assignment has no " "organization."
            )

        if not has_capability(
            actor,
            PartnerCapability.CLAIM_VERIFICATION_WORK,
            organization=organization,
        ):
            raise VerificationAssignmentAuthorizationError(
                "You do not have permission to release "
                "verification work for this organization."
            )

        claim = locked_assignment.claim

        if _claim_has_started_authoritative_work(claim):
            raise VerificationAssignmentReleaseBlocked(
                "This investigation can no longer be "
                "released because authoritative review "
                "work has already begun."
            )

        # Only untouched OPEN factual cases may return
        # to unassigned intake ownership.
        evidence_cases = list(
            ModerationCase.objects.select_for_update().filter(
                case_type=(ModerationCase.CaseType.EVIDENCE),
                evidence_submission__thread__claim=claim,
                organization=organization,
                status=ModerationCase.Status.OPEN,
            )
        )

        adjudication_cases = list(
            ModerationCase.objects.select_for_update().filter(
                case_type=(ModerationCase.CaseType.ADJUDICATION),
                claim=claim,
                organization=organization,
                status=ModerationCase.Status.OPEN,
            )
        )

        cases = evidence_cases + adjudication_cases

        now = timezone.now()

        for case in cases:
            case.organization = None

            case.save(
                update_fields=[
                    "organization",
                    "updated_at",
                ]
            )

        locked_assignment.status = VerificationAssignment.Status.RELEASED
        locked_assignment.released_at = now

        # Keep organization / claimed_by / claimed_at
        # on the released row as historical provenance.
        locked_assignment.save(
            update_fields=[
                "status",
                "released_at",
                "updated_at",
            ]
        )

        replacement = VerificationAssignment.objects.create(
            claim=claim,
            status=(VerificationAssignment.Status.AVAILABLE),
        )

        return {
            "released_assignment": locked_assignment,
            "available_assignment": replacement,
        }


def complete_verification_assignment(
    *,
    claim,
    organization,
):
    """
    Mark the active institutional assignment complete.

    Intended to be called by the publishing workflow
    after successful publication.
    """

    with transaction.atomic():
        assignment = (
            VerificationAssignment.objects.select_for_update()
            .filter(
                claim=claim,
                status=(VerificationAssignment.Status.ACTIVE),
            )
            .first()
        )

        # Legacy fact checks may predate assignment.
        if assignment is None:
            return None

        if assignment.organization_id != organization.id:
            raise VerificationAssignmentConflict(
                "The publishing organization does not "
                "own this verification assignment."
            )

        assignment.status = VerificationAssignment.Status.COMPLETED
        assignment.completed_at = timezone.now()

        assignment.save(
            update_fields=[
                "status",
                "completed_at",
                "updated_at",
            ]
        )

        return assignment
