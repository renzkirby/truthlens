"""Community account enforcement, Standing, review, and revocation services."""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .accountability_service import record_accountability_event
from .community_policy import community_policy_supports_account_enforcement
from .models import (
    AccountabilityEvent,
    CommunityAccountEnforcement,
    CommunityAccountEnforcementReview,
    CommunitySafetyDecision,
    CommunitySafetyReconsideration,
    UserProfile,
)
from .organization_service import PartnerCapability
from .platform_identity_service import (
    PLATFORM_SAFETY_PROFILE_ROLES,
    can_review_platform_safety,
)


logger = logging.getLogger(__name__)


TEMPORARY_DURATION_MAP = {
    "24_HOURS": timedelta(hours=24),
    "7_DAYS": timedelta(days=7),
    "30_DAYS": timedelta(days=30),
}


class CommunityAccountEnforcementError(Exception):
    pass


class CommunityAccountEnforcementAuthorizationError(CommunityAccountEnforcementError):
    pass


class CommunityAccountEnforcementConflict(CommunityAccountEnforcementError):
    pass


class CommunityAccountEnforcementValidationError(CommunityAccountEnforcementError):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


class CommunityAccountEnforcementNotFound(CommunityAccountEnforcementError):
    pass


def _require_safety_reviewer(actor):
    if not can_review_platform_safety(actor):
        raise CommunityAccountEnforcementAuthorizationError(
            "Platform Safety review authority is required."
        )


def _active_restrictions_queryset(user, *, now=None, lock=False):
    now = now or timezone.now()
    queryset = CommunityAccountEnforcement.objects.filter(
        user=user,
        revoked_at__isnull=True,
    ).filter(
        Q(action=CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION)
        | Q(
            action=CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION,
            restriction_ends_at__gt=now,
        )
    )
    if lock:
        queryset = queryset.select_for_update()
    return queryset.select_related("safety_decision").order_by(
        "-restriction_ends_at",
        "-issued_at",
        "-id",
    )


def _effective_restriction(user, *, now=None, lock=False):
    now = now or timezone.now()
    restrictions = list(
        _active_restrictions_queryset(
            user,
            now=now,
            lock=lock,
        )
    )
    if not restrictions:
        return None

    indefinite = next(
        (
            item
            for item in restrictions
            if item.action
            == CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION
        ),
        None,
    )
    if indefinite is not None:
        return indefinite

    return max(
        restrictions,
        key=lambda item: item.restriction_ends_at,
    )


def serialize_enforcement(enforcement, *, actor=None, now=None, include_internal=False):
    now = now or timezone.now()
    review = getattr(enforcement, "review", None)
    if enforcement.revoked_at is not None:
        state = "REVOKED"
    elif (
        enforcement.action
        == CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION
        and enforcement.restriction_ends_at <= now
    ):
        state = "EXPIRED"
    elif enforcement.action == CommunityAccountEnforcement.Action.WARNING:
        state = "WARNING"
    else:
        state = "ACTIVE"

    can_request_review = bool(
        actor
        and actor.is_authenticated
        and enforcement.user_id == actor.pk
        and review is None
        and enforcement.revocation_reason
        not in {
            CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED,
            CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED,
        }
    )

    payload = {
        "id": str(enforcement.pk),
        "safety_decision_id": str(enforcement.safety_decision_id),
        "action": enforcement.action,
        "state": state,
        "user_rationale": enforcement.user_rationale,
        "policy": {
            "title": enforcement.policy_title_snapshot,
            "version": enforcement.policy_version,
        },
        "violation": {
            "code": enforcement.violation_code_snapshot,
            "title": enforcement.violation_label_snapshot,
        },
        "restriction_ends_at": enforcement.restriction_ends_at,
        "issued_at": enforcement.issued_at,
        "seen": enforcement.user_seen_at is not None,
        "revoked_at": enforcement.revoked_at,
        "revocation_reason": enforcement.revocation_reason or None,
        "revocation_rationale": (
            enforcement.revocation_rationale if enforcement.revoked_at else ""
        ),
        "can_request_review": can_request_review,
        "review": (
            {
                "id": str(review.pk),
                "status": review.status,
                "request_statement": review.request_statement,
                "submitted_at": review.submitted_at,
                "review_started_at": review.review_started_at,
                "outcome": review.outcome or None,
                "resolution_rationale": review.resolution_rationale,
                "resolved_at": review.resolved_at,
            }
            if review is not None
            else None
        ),
    }

    if include_internal:
        payload.update(
            {
                "user": (
                    {
                        "id": enforcement.user_id,
                        "username": (
                            enforcement.user.username
                            if enforcement.user_id
                            else enforcement.username_snapshot
                        ),
                    }
                    if enforcement.user_id
                    else {
                        "id": None,
                        "username": enforcement.username_snapshot,
                    }
                ),
                "internal_note": enforcement.internal_note,
                "issued_by": (
                    {
                        "id": enforcement.issued_by_id,
                        "username": enforcement.issued_by.username,
                    }
                    if enforcement.issued_by_id
                    else None
                ),
                "safety_decision_id": str(enforcement.safety_decision_id),
                "review_internal": (
                    {
                        "reviewer": (
                            {
                                "id": review.reviewer_id,
                                "username": review.reviewer.username,
                            }
                            if review and review.reviewer_id
                            else None
                        ),
                        "reviewer_independence_note": (
                            review.reviewer_independence_note if review else ""
                        ),
                        "independence_override_rationale": (
                            review.independence_override_rationale if review else ""
                        ),
                        "internal_note": review.internal_note if review else "",
                        "independence_requirement": (
                            (
                                "OVERRIDE_RATIONALE"
                                if _another_safety_reviewer_exists(actor)
                                else "UNAVAILABLE_NOTE"
                            )
                            if (
                                actor
                                and actor.is_authenticated
                                and enforcement.issued_by_id == actor.pk
                                and review.status
                                == CommunityAccountEnforcementReview.Status.SUBMITTED
                            )
                            else "INDEPENDENT_REVIEW"
                        ),
                    }
                    if review is not None
                    else None
                ),
            }
        )

    return payload


def get_user_community_access(user, *, now=None):
    """Project Community contribution access without changing identity eligibility."""

    if not user or not user.is_authenticated:
        return {
            "status": "FULL_ACCESS",
            "can_contribute": True,
            "restriction_ends_at": None,
            "active_enforcement_id": None,
            "has_unseen_action": False,
        }

    now = now or timezone.now()
    restriction = _effective_restriction(user, now=now)
    unseen = CommunityAccountEnforcement.objects.filter(
        user=user,
        user_seen_at__isnull=True,
    ).exists()

    if restriction is None:
        return {
            "status": "FULL_ACCESS",
            "can_contribute": True,
            "restriction_ends_at": None,
            "active_enforcement_id": None,
            "has_unseen_action": unseen,
        }

    if (
        restriction.action
        == CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION
    ):
        status = "INDEFINITELY_RESTRICTED"
        ends_at = None
    else:
        status = "TEMPORARILY_RESTRICTED"
        ends_at = restriction.restriction_ends_at

    return {
        "status": status,
        "can_contribute": False,
        "restriction_ends_at": ends_at,
        "active_enforcement_id": str(restriction.pk),
        "has_unseen_action": unseen,
    }


def get_community_standing(user, *, history_limit=20):
    now = timezone.now()
    history = (
        CommunityAccountEnforcement.objects.filter(user=user)
        .select_related(
            "issued_by",
            "safety_decision",
            "review",
            "review__reviewer",
        )
        .order_by("-issued_at", "-id")[:history_limit]
    )
    return {
        "access": get_user_community_access(user, now=now),
        "history": [
            serialize_enforcement(item, actor=user, now=now)
            for item in history
        ],
    }


def _record_enforcement_event(
    *,
    enforcement,
    actor,
    action_type,
    reason_code,
    notes,
    previous_state=None,
    new_state=None,
    authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
    capability=PartnerCapability.REVIEW_SAFETY,
):
    return record_accountability_event(
        action_type=action_type,
        resource_type=AccountabilityEvent.ResourceType.USER_ACCOUNT,
        resource_id=enforcement.user_id or enforcement.username_snapshot,
        authority_scope=authority_scope,
        actor=actor,
        capability=capability,
        previous_state=previous_state or {},
        new_state=new_state or {},
        reason_code=reason_code,
        notes=notes,
        context={
            "enforcement_id": str(enforcement.pk),
            "safety_decision_id": str(enforcement.safety_decision_id),
            "action": enforcement.action,
            "policy_version": enforcement.policy_version,
            "violation_code": enforcement.violation_code_snapshot,
        },
    )


def _another_safety_reviewer_exists(actor):
    return (
        User.objects.filter(is_active=True)
        .filter(
            Q(is_superuser=True)
            | Q(profile__role__in=tuple(PLATFORM_SAFETY_PROFILE_ROLES))
        )
        .exclude(pk=actor.pk)
        .exists()
    )


def _mark_superseded(enforcement, *, actor, rationale, when):
    if enforcement.revoked_at is not None:
        return enforcement
    previous_state = serialize_enforcement(
        enforcement,
        now=when,
        include_internal=True,
    )
    enforcement.revoked_at = when
    enforcement.revoked_by = actor
    enforcement.revocation_reason = (
        CommunityAccountEnforcement.RevocationReason.SUPERSEDED
    )
    enforcement.revocation_rationale = rationale
    enforcement.save(
        update_fields=[
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "revocation_rationale",
        ]
    )
    _record_enforcement_event(
        enforcement=enforcement,
        actor=actor,
        action_type=AccountabilityEvent.ActionType.COMMUNITY_RESTRICTION_SUPERSEDED,
        reason_code="SUPERSEDED",
        notes=rationale,
        previous_state=previous_state,
        new_state=serialize_enforcement(
            enforcement,
            now=when,
            include_internal=True,
        ),
    )
    return enforcement


@transaction.atomic
def issue_account_enforcement(
    *,
    safety_decision,
    actor,
    action,
    user_rationale,
    internal_note="",
    duration_code="",
):
    _require_safety_reviewer(actor)

    if not getattr(
        settings,
        "COMMUNITY_ACCOUNT_ENFORCEMENT_ISSUANCE_ENABLED",
        False,
    ):
        raise CommunityAccountEnforcementConflict(
            "Community account enforcement issuance is currently disabled."
        )

    decision = (
        CommunitySafetyDecision.objects.select_for_update()
        .select_related("content_owner")
        .get(pk=safety_decision.pk)
    )
    if decision.action != CommunitySafetyDecision.Action.REMOVE:
        raise CommunityAccountEnforcementConflict(
            "Only a confirmed removed-content decision can support account enforcement."
        )
    if not community_policy_supports_account_enforcement(decision.policy_version):
        raise CommunityAccountEnforcementConflict(
            "This historical Safety decision predates Community account enforcement "
            "and cannot be used to issue a new account action."
        )
    reconsideration = getattr(decision, "reconsideration", None)
    if reconsideration is not None and not reconsideration.outcome:
        raise CommunityAccountEnforcementConflict(
            "Resolve the pending content reconsideration before issuing an account-level action."
        )
    if (
        reconsideration is not None
        and reconsideration.outcome
        == CommunitySafetyReconsideration.Outcome.REVERSED
    ):
        raise CommunityAccountEnforcementConflict(
            "The underlying content removal was reversed."
        )
    if decision.content_owner_id is None:
        raise CommunityAccountEnforcementConflict(
            "The affected Community account is no longer available."
        )
    if CommunityAccountEnforcement.objects.filter(
        safety_decision=decision
    ).exists():
        raise CommunityAccountEnforcementConflict(
            "This Safety decision already has an account-level action."
        )

    user_rationale = str(user_rationale or "").strip()
    internal_note = str(internal_note or "").strip()
    if len(user_rationale) < 20:
        raise CommunityAccountEnforcementValidationError(
            "Explain the account action to the affected user.",
            field="user_rationale",
        )

    valid_actions = set(CommunityAccountEnforcement.Action.values)
    if action not in valid_actions:
        raise CommunityAccountEnforcementValidationError(
            "Select a supported Community account action.",
            field="action",
        )

    now = timezone.now()
    user = User.objects.select_for_update().get(pk=decision.content_owner_id)
    active = list(_active_restrictions_queryset(user, now=now, lock=True))
    indefinite = next(
        (
            item
            for item in active
            if item.action
            == CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION
        ),
        None,
    )
    active_temporaries = [
        item
        for item in active
        if item.action
        == CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION
    ]

    restriction_ends_at = None
    if action == CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION:
        duration = TEMPORARY_DURATION_MAP.get(duration_code)
        if duration is None:
            raise CommunityAccountEnforcementValidationError(
                "Choose 24 hours, 7 days, or 30 days.",
                field="duration_code",
            )
        if indefinite is not None:
            raise CommunityAccountEnforcementConflict(
                "This account already has an active indefinite Community restriction."
            )
        restriction_ends_at = now + duration
        if active_temporaries:
            current_end = max(
                item.restriction_ends_at for item in active_temporaries
            )
            if restriction_ends_at <= current_end:
                raise CommunityAccountEnforcementConflict(
                    "The new temporary restriction must end later than the active restriction."
                )
            for existing in active_temporaries:
                _mark_superseded(
                    existing,
                    actor=actor,
                    rationale="Superseded by a longer Community restriction.",
                    when=now,
                )
    elif action == CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION:
        if indefinite is not None:
            raise CommunityAccountEnforcementConflict(
                "This account already has an active indefinite Community restriction."
            )
        for existing in active_temporaries:
            _mark_superseded(
                existing,
                actor=actor,
                rationale="Superseded by an indefinite Community restriction.",
                when=now,
            )
    elif duration_code:
        raise CommunityAccountEnforcementValidationError(
            "Only temporary restrictions use a duration.",
            field="duration_code",
        )

    try:
        enforcement = CommunityAccountEnforcement.objects.create(
            user=user,
            username_snapshot=user.username,
            safety_decision=decision,
            action=action,
            user_rationale=user_rationale,
            internal_note=internal_note,
            policy_title_snapshot=decision.policy_title_snapshot,
            policy_version=decision.policy_version,
            violation_code_snapshot=decision.violation_code,
            violation_label_snapshot=decision.violation_label_snapshot,
            restriction_ends_at=restriction_ends_at,
            issued_by=actor,
        )
    except IntegrityError as error:
        raise CommunityAccountEnforcementConflict(
            "This account action conflicts with an enforcement action already on record."
        ) from error

    _record_enforcement_event(
        enforcement=enforcement,
        actor=actor,
        action_type=(
            AccountabilityEvent.ActionType.COMMUNITY_WARNING_ISSUED
            if action == CommunityAccountEnforcement.Action.WARNING
            else AccountabilityEvent.ActionType.COMMUNITY_RESTRICTION_ISSUED
        ),
        reason_code=action,
        notes=user_rationale,
        new_state=serialize_enforcement(
            enforcement,
            now=now,
            include_internal=True,
        ),
    )
    schedule_enforcement_notification(
        enforcement,
        event="ISSUED",
    )
    return enforcement


@transaction.atomic
def mark_enforcement_seen(*, enforcement_id, actor):
    enforcement = (
        CommunityAccountEnforcement.objects.select_for_update()
        .filter(pk=enforcement_id, user=actor)
        .first()
    )
    if enforcement is None:
        raise CommunityAccountEnforcementNotFound
    if enforcement.user_seen_at is None:
        enforcement.user_seen_at = timezone.now()
        enforcement.save(update_fields=["user_seen_at"])
    return enforcement


@transaction.atomic
def submit_enforcement_review(*, enforcement_id, actor, request_statement):
    enforcement = (
        CommunityAccountEnforcement.objects.select_for_update()
        .select_related("review")
        .filter(pk=enforcement_id, user=actor)
        .first()
    )
    if enforcement is None:
        raise CommunityAccountEnforcementNotFound
    if hasattr(enforcement, "review"):
        raise CommunityAccountEnforcementConflict(
            "This account action already has a review request."
        )
    if enforcement.revocation_reason in {
        CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED,
        CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED,
    }:
        raise CommunityAccountEnforcementConflict(
            "This account action has already been reversed."
        )

    statement = str(request_statement or "").strip()
    if len(statement) < 20:
        raise CommunityAccountEnforcementValidationError(
            "Explain why this account action should be reviewed.",
            field="request_statement",
        )

    review = CommunityAccountEnforcementReview.objects.create(
        enforcement=enforcement,
        requested_by=actor,
        request_statement=statement,
    )
    _record_enforcement_event(
        enforcement=enforcement,
        actor=actor,
        action_type=(
            AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_REVIEW_SUBMITTED
        ),
        reason_code="REVIEW_SUBMITTED",
        notes=statement,
        new_state={
            "review_id": str(review.pk),
            "status": review.status,
        },
        authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL,
        capability="",
    )
    return review


@transaction.atomic
def start_enforcement_review(
    *,
    review_id,
    actor,
    reviewer_independence_note="",
    independence_override_rationale="",
):
    _require_safety_reviewer(actor)
    review = (
        CommunityAccountEnforcementReview.objects.select_for_update()
        .select_related("enforcement", "enforcement__issued_by")
        .get(pk=review_id)
    )
    if review.status != CommunityAccountEnforcementReview.Status.SUBMITTED:
        raise CommunityAccountEnforcementConflict(
            "Only a submitted account-action review can enter review."
        )

    original_actor_id = review.enforcement.issued_by_id
    independence_note = str(reviewer_independence_note or "").strip()
    override_rationale = str(independence_override_rationale or "").strip()
    if original_actor_id == actor.pk:
        if _another_safety_reviewer_exists(actor):
            if len(override_rationale) < 20:
                raise CommunityAccountEnforcementValidationError(
                    "Another qualified Safety reviewer is available. Self-review requires an independence override rationale.",
                    field="independence_override_rationale",
                )
        elif len(independence_note) < 20:
            raise CommunityAccountEnforcementValidationError(
                "Record why independent review is unavailable.",
                field="reviewer_independence_note",
            )

    review.status = CommunityAccountEnforcementReview.Status.UNDER_REVIEW
    review.reviewer = actor
    review.reviewer_independence_note = independence_note
    review.independence_override_rationale = override_rationale
    review.review_started_at = timezone.now()
    review.save(
        update_fields=[
            "status",
            "reviewer",
            "reviewer_independence_note",
            "independence_override_rationale",
            "review_started_at",
        ]
    )
    _record_enforcement_event(
        enforcement=review.enforcement,
        actor=actor,
        action_type=(
            AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_REVIEW_STARTED
        ),
        reason_code="REVIEW_STARTED",
        notes=independence_note or override_rationale,
        new_state={
            "review_id": str(review.pk),
            "status": review.status,
        },
    )
    return review


def _revoke_locked_enforcement(
    *,
    enforcement,
    actor,
    reason,
    rationale,
    action_type,
    when=None,
):
    when = when or timezone.now()
    if enforcement.revoked_at is not None:
        return enforcement

    previous_state = serialize_enforcement(
        enforcement,
        now=when,
        include_internal=True,
    )
    enforcement.revoked_at = when
    enforcement.revoked_by = actor
    enforcement.revocation_reason = reason
    enforcement.revocation_rationale = str(rationale or "").strip()
    enforcement.user_seen_at = None
    enforcement.save(
        update_fields=[
            "revoked_at",
            "revoked_by",
            "revocation_reason",
            "revocation_rationale",
            "user_seen_at",
        ]
    )
    _record_enforcement_event(
        enforcement=enforcement,
        actor=actor,
        action_type=action_type,
        reason_code=reason,
        notes=enforcement.revocation_rationale,
        previous_state=previous_state,
        new_state=serialize_enforcement(
            enforcement,
            now=when,
            include_internal=True,
        ),
    )
    return enforcement


@transaction.atomic
def resolve_enforcement_review(
    *,
    review_id,
    actor,
    outcome,
    resolution_rationale,
    internal_note="",
):
    _require_safety_reviewer(actor)
    review = (
        CommunityAccountEnforcementReview.objects.select_for_update()
        .select_related("enforcement", "reviewer")
        .get(pk=review_id)
    )
    if review.status != CommunityAccountEnforcementReview.Status.UNDER_REVIEW:
        raise CommunityAccountEnforcementConflict(
            "Only an account-action review under review can be resolved."
        )
    if review.reviewer_id != actor.pk:
        raise CommunityAccountEnforcementAuthorizationError(
            "The Safety reviewer who started this review must resolve it."
        )
    if outcome not in CommunityAccountEnforcementReview.Outcome.values:
        raise CommunityAccountEnforcementValidationError(
            "Select Uphold or Reverse.",
            field="outcome",
        )

    rationale = str(resolution_rationale or "").strip()
    if len(rationale) < 20:
        raise CommunityAccountEnforcementValidationError(
            "Explain the review outcome.",
            field="resolution_rationale",
        )
    enforcement = CommunityAccountEnforcement.objects.select_for_update().get(
        pk=review.enforcement_id
    )
    if (
        enforcement.revocation_reason
        == CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED
    ):
        raise CommunityAccountEnforcementConflict(
            "The underlying content decision was already reversed."
        )

    if outcome == CommunityAccountEnforcementReview.Outcome.REVERSED:
        if enforcement.revoked_at is None:
            _revoke_locked_enforcement(
                enforcement=enforcement,
                actor=actor,
                reason=(
                    CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED
                ),
                rationale=rationale,
                action_type=(
                    AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_REVERSED
                ),
            )
        elif (
            enforcement.revocation_reason
            != CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED
        ):
            previous_state = serialize_enforcement(
                enforcement,
                include_internal=True,
            )
            enforcement.revoked_by = actor
            enforcement.revocation_reason = (
                CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED
            )
            enforcement.revocation_rationale = rationale
            enforcement.user_seen_at = None
            enforcement.save(
                update_fields=[
                    "revoked_by",
                    "revocation_reason",
                    "revocation_rationale",
                    "user_seen_at",
                ]
            )
            _record_enforcement_event(
                enforcement=enforcement,
                actor=actor,
                action_type=(
                    AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_REVERSED
                ),
                reason_code=(
                    CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED
                ),
                notes=rationale,
                previous_state=previous_state,
                new_state=serialize_enforcement(
                    enforcement,
                    include_internal=True,
                ),
            )

    review.status = CommunityAccountEnforcementReview.Status.RESOLVED
    review.outcome = outcome
    review.resolution_rationale = rationale
    review.internal_note = str(internal_note or "").strip()
    review.resolved_at = timezone.now()
    review.save(
        update_fields=[
            "status",
            "outcome",
            "resolution_rationale",
            "internal_note",
            "resolved_at",
        ]
    )

    if outcome == CommunityAccountEnforcementReview.Outcome.UPHELD:
        enforcement.user_seen_at = None
        enforcement.save(update_fields=["user_seen_at"])
        _record_enforcement_event(
            enforcement=enforcement,
            actor=actor,
            action_type=(
                AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_UPHELD
            ),
            reason_code="UPHELD",
            notes=rationale,
            new_state={
                "review_id": str(review.pk),
                "status": review.status,
                "outcome": review.outcome,
            },
        )

    schedule_enforcement_notification(
        enforcement,
        event="REVIEW_RESOLVED",
        review=review,
    )
    return review


@transaction.atomic
def lift_enforcement_early(*, enforcement_id, actor, rationale):
    _require_safety_reviewer(actor)
    enforcement = (
        CommunityAccountEnforcement.objects.select_for_update()
        .select_related("safety_decision")
        .get(pk=enforcement_id)
    )
    if enforcement.action == CommunityAccountEnforcement.Action.WARNING:
        raise CommunityAccountEnforcementConflict(
            "Warnings are corrected through review, not lifted."
        )
    if enforcement.revoked_at is not None:
        raise CommunityAccountEnforcementConflict(
            "This Community restriction is already inactive."
        )
    if (
        enforcement.action
        == CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION
        and enforcement.restriction_ends_at <= timezone.now()
    ):
        raise CommunityAccountEnforcementConflict(
            "This temporary restriction has already expired."
        )

    rationale = str(rationale or "").strip()
    if len(rationale) < 20:
        raise CommunityAccountEnforcementValidationError(
            "Explain why this restriction is being lifted early.",
            field="rationale",
        )
    _revoke_locked_enforcement(
        enforcement=enforcement,
        actor=actor,
        reason=CommunityAccountEnforcement.RevocationReason.LIFTED_EARLY,
        rationale=rationale,
        action_type=AccountabilityEvent.ActionType.COMMUNITY_RESTRICTION_LIFTED,
    )
    schedule_enforcement_notification(
        enforcement,
        event="LIFTED",
    )
    return enforcement


def revoke_enforcement_for_basis_reversal(*, safety_decision, actor, rationale):
    """Revoke dependent account action inside the caller's Phase C transaction."""

    enforcement = (
        CommunityAccountEnforcement.objects.select_for_update()
        .select_related("review")
        .filter(safety_decision=safety_decision)
        .first()
    )
    if enforcement is None:
        return None

    if enforcement.revocation_reason not in {
        CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED,
        CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED,
    }:
        previous_state = serialize_enforcement(
            enforcement,
            include_internal=True,
        )
        enforcement.revoked_at = timezone.now()
        enforcement.revoked_by = actor
        enforcement.revocation_reason = (
            CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED
        )
        enforcement.revocation_rationale = str(rationale or "").strip()
        enforcement.user_seen_at = None
        enforcement.save(
            update_fields=[
                "revoked_at",
                "revoked_by",
                "revocation_reason",
                "revocation_rationale",
                "user_seen_at",
            ]
        )
        _record_enforcement_event(
            enforcement=enforcement,
            actor=actor,
            action_type=(
                AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_BASIS_REVERSED
            ),
            reason_code=(
                CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED
            ),
            notes=enforcement.revocation_rationale,
            previous_state=previous_state,
            new_state=serialize_enforcement(
                enforcement,
                include_internal=True,
            ),
        )

    review = getattr(enforcement, "review", None)
    if (
        review is not None
        and review.status
        in {
            CommunityAccountEnforcementReview.Status.SUBMITTED,
            CommunityAccountEnforcementReview.Status.UNDER_REVIEW,
        }
    ):
        review.status = CommunityAccountEnforcementReview.Status.MOOT
        review.outcome = ""
        review.resolution_rationale = (
            "The underlying Community Safety removal was reversed, so this "
            "account-action review no longer requires a separate decision."
        )
        review.resolved_at = timezone.now()
        review.save(
            update_fields=[
                "status",
                "outcome",
                "resolution_rationale",
                "resolved_at",
            ]
        )

    schedule_enforcement_notification(
        enforcement,
        event="BASIS_REVERSED",
        review=review,
    )
    return enforcement


def list_safety_account_enforcements(*, actor, status_filter="", limit=50):
    _require_safety_reviewer(actor)
    queryset = CommunityAccountEnforcement.objects.select_related(
        "user",
        "issued_by",
        "safety_decision",
        "review",
        "review__reviewer",
    ).order_by("-issued_at", "-id")

    now = timezone.now()
    if status_filter == "ACTIVE":
        queryset = queryset.filter(revoked_at__isnull=True).filter(
            Q(action=CommunityAccountEnforcement.Action.INDEFINITE_RESTRICTION)
            | Q(
                action=CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION,
                restriction_ends_at__gt=now,
            )
        )
    elif status_filter == "PENDING_REVIEW":
        queryset = queryset.filter(
            review__status__in=[
                CommunityAccountEnforcementReview.Status.SUBMITTED,
                CommunityAccountEnforcementReview.Status.UNDER_REVIEW,
            ]
        )
    elif status_filter == "WARNING":
        queryset = queryset.filter(
            action=CommunityAccountEnforcement.Action.WARNING
        )

    return [
        serialize_enforcement(
            item,
            actor=actor,
            now=now,
            include_internal=True,
        )
        for item in queryset[: max(1, min(int(limit), 100))]
    ]


def schedule_enforcement_notification(enforcement, *, event, review=None):
    """Best-effort derived inbox delivery; Standing remains authoritative."""

    enforcement_id = enforcement.pk
    recipient_id = enforcement.user_id
    decision_id = enforcement.safety_decision_id

    def deliver():
        if recipient_id is None:
            return
        try:
            from .notification_service import Target, Type, create_notification_once

            current = CommunityAccountEnforcement.objects.select_related(
                "safety_decision"
            ).get(pk=enforcement_id)

            if event == "ISSUED":
                if current.action == CommunityAccountEnforcement.Action.WARNING:
                    title = "You received a Community warning"
                    message = (
                        "Your Community access is unchanged. Open Community Standing "
                        "to review the reason and policy."
                    )
                elif (
                    current.action
                    == CommunityAccountEnforcement.Action.TEMPORARY_RESTRICTION
                ):
                    title = "Your Community access is temporarily restricted"
                    message = (
                        "You can still read Community content, report unsafe content, "
                        "and use TruthLens verification. Open Community Standing for details."
                    )
                else:
                    title = "Your Community access is indefinitely restricted"
                    message = (
                        "Your contribution access has no automatic end date. Open "
                        "Community Standing to review the reason and your review options."
                    )
                dedupe = f"community-enforcement:{current.pk}:issued"
            elif event == "REVIEW_RESOLVED":
                title = "Your Community account-action review was resolved"
                outcome = review.outcome if review is not None else ""
                message = (
                    "Platform Safety reversed the account action. Open Community Standing "
                    "to review the outcome."
                    if outcome == CommunityAccountEnforcementReview.Outcome.REVERSED
                    else "Platform Safety upheld the account action. Open Community Standing to review the outcome."
                )
                dedupe = f"community-enforcement:{current.pk}:review-resolved"
            elif event == "BASIS_REVERSED":
                title = "Your Community account action was reversed"
                message = (
                    "The underlying content-removal decision was reversed, so the "
                    "dependent account action no longer applies."
                )
                dedupe = f"community-enforcement:{current.pk}:basis-reversed"
            else:
                title = "Your Community restriction was lifted"
                message = (
                    "Platform Safety ended this Community restriction early. Open "
                    "Community Standing to review the update."
                )
                dedupe = f"community-enforcement:{current.pk}:lifted"

            create_notification_once(
                recipient_id=recipient_id,
                notification_type=Type.COMMUNITY_ACCOUNT_ENFORCEMENT,
                target_type=Target.MODERATION_OUTCOME,
                target_id=decision_id,
                dedupe_key=dedupe,
                title=title,
                message=message,
            )
        except Exception:
            logger.exception(
                "Community account-enforcement notification failed for enforcement_id=%s event=%s.",
                enforcement_id,
                event,
            )

    transaction.on_commit(deliver, robust=True)
