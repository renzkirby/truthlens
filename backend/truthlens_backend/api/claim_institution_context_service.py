from django.db import transaction
from django.utils import timezone

from .accountability_service import record_accountability_event
from .management_governance_service import (
    MANAGE_PARTNER_ORGANIZATION,
    ManagementGovernanceAuthorizationError,
    ManagementGovernanceConflict,
    ManagementGovernanceValidationError,
)
from .models import (
    AccountabilityEvent,
    ClaimInvestigationClassification,
    ClaimInstitutionAssociation,
    Institution,
)


def _require_platform_management_authority(actor):
    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise ManagementGovernanceAuthorizationError(
            "Platform management administrator access is required."
        )


def _reviewer_state(user):
    if user is None:
        return None
    return {
        "id": str(user.pk),
        "username": str(user.username),
    }


def _association_state(association):
    return {
        "institution_id": str(association.institution_id),
        "institution_name": association.institution.name,
        "rationale": association.rationale,
        "assigned_by": _reviewer_state(association.assigned_by),
        "assigned_at": association.assigned_at.isoformat(),
    }


def serialize_claim_institution_context(classification):
    associations = list(
        classification.institution_associations.select_related(
            "institution",
            "assigned_by",
        ).order_by("institution__name", "institution_id")
    )
    return {
        "claim_id": str(classification.claim_id),
        "campus_context_state": classification.campus_context_state,
        "campus_context_rationale": classification.campus_context_rationale,
        "campus_context_reviewed_by": _reviewer_state(
            classification.campus_context_reviewed_by
        ),
        "campus_context_reviewed_at": (
            classification.campus_context_reviewed_at.isoformat()
            if classification.campus_context_reviewed_at is not None
            else None
        ),
        "institutions": [
            _association_state(association) for association in associations
        ],
    }


def _normalize_institution_entries(entries):
    normalized = []
    seen = set()

    for entry in entries:
        institution_id = entry.get("institution_id")
        rationale = str(entry.get("rationale") or "").strip()

        key = str(institution_id)
        if key in seen:
            raise ManagementGovernanceValidationError(
                "Duplicate institution IDs are not allowed.",
                field="institutions",
            )
        seen.add(key)

        if not rationale:
            raise ManagementGovernanceValidationError(
                "Each institution association requires a rationale.",
                field="institutions",
            )
        if len(rationale) > 2000:
            raise ManagementGovernanceValidationError(
                "Institution association rationale must be 2000 characters or fewer.",
                field="institutions",
            )

        normalized.append(
            {
                "institution_id": institution_id,
                "rationale": rationale,
            }
        )

    return normalized


@transaction.atomic
def set_claim_institution_context(
    *,
    claim_id,
    campus_context_state,
    campus_context_rationale,
    institutions,
    actor,
):
    _require_platform_management_authority(actor)

    valid_states = {
        value
        for value, _label
        in ClaimInvestigationClassification.CampusContextState.choices
    }
    if campus_context_state is not None and campus_context_state not in valid_states:
        raise ManagementGovernanceValidationError(
            "Select a valid campus context state.",
            field="campus_context_state",
        )

    campus_context_rationale = str(campus_context_rationale or "").strip()
    if campus_context_state is None:
        if campus_context_rationale:
            raise ManagementGovernanceValidationError(
                "Unassessed campus context cannot have a rationale.",
                field="campus_context_rationale",
            )
    else:
        if not campus_context_rationale:
            raise ManagementGovernanceValidationError(
                "Campus context rationale is required.",
                field="campus_context_rationale",
            )
        if len(campus_context_rationale) > 2000:
            raise ManagementGovernanceValidationError(
                "Campus context rationale must be 2000 characters or fewer.",
                field="campus_context_rationale",
            )

    normalized_entries = _normalize_institution_entries(institutions or [])
    if (
        campus_context_state
        != ClaimInvestigationClassification.CampusContextState.CONFIRMED
        and normalized_entries
    ):
        raise ManagementGovernanceValidationError(
            "Institution associations require confirmed campus context.",
            field="institutions",
        )

    classification = (
        ClaimInvestigationClassification.objects.select_for_update()
        .select_related("campus_context_reviewed_by")
        .filter(claim_id=claim_id)
        .first()
    )
    if classification is None:
        raise ManagementGovernanceConflict(
            "Claim has no authoritative investigation classification.",
            field="claim_id",
        )

    current_associations = list(
        ClaimInstitutionAssociation.objects.select_for_update()
        .select_related("institution", "assigned_by")
        .filter(classification=classification)
        .order_by("institution__name", "institution_id")
    )

    previous_state = {
        "claim_id": str(classification.claim_id),
        "campus_context_state": classification.campus_context_state,
        "campus_context_rationale": classification.campus_context_rationale,
        "campus_context_reviewed_by": _reviewer_state(
            classification.campus_context_reviewed_by
        ),
        "campus_context_reviewed_at": (
            classification.campus_context_reviewed_at.isoformat()
            if classification.campus_context_reviewed_at is not None
            else None
        ),
        "institutions": [
            _association_state(association)
            for association in current_associations
        ],
    }

    requested_ids = [entry["institution_id"] for entry in normalized_entries]
    institutions_by_id = {
        str(institution.pk): institution
        for institution in Institution.objects.select_for_update().filter(
            pk__in=requested_ids
        )
    }
    if len(institutions_by_id) != len(requested_ids):
        raise ManagementGovernanceValidationError(
            "One or more institutions do not exist.",
            field="institutions",
        )

    for institution in institutions_by_id.values():
        if not institution.is_active:
            raise ManagementGovernanceValidationError(
                f"Institution '{institution.name}' is inactive.",
                field="institutions",
            )

    desired_pairs = sorted(
        (
            str(entry["institution_id"]),
            entry["rationale"],
        )
        for entry in normalized_entries
    )
    current_pairs = sorted(
        (
            str(association.institution_id),
            association.rationale,
        )
        for association in current_associations
    )
    if (
        classification.campus_context_state == campus_context_state
        and classification.campus_context_rationale == campus_context_rationale
        and desired_pairs == current_pairs
    ):
        return classification

    now = timezone.now()
    classification.campus_context_state = campus_context_state
    classification.campus_context_rationale = campus_context_rationale
    if campus_context_state is None:
        classification.campus_context_reviewed_by = None
        classification.campus_context_reviewed_at = None
    else:
        classification.campus_context_reviewed_by = actor
        classification.campus_context_reviewed_at = now
    classification.save(
        update_fields=[
            "campus_context_state",
            "campus_context_rationale",
            "campus_context_reviewed_by",
            "campus_context_reviewed_at",
            "updated_at",
        ]
    )

    ClaimInstitutionAssociation.objects.filter(
        classification=classification
    ).delete()

    for entry in normalized_entries:
        institution = institutions_by_id[str(entry["institution_id"])]
        ClaimInstitutionAssociation.objects.create(
            classification=classification,
            institution=institution,
            rationale=entry["rationale"],
            assigned_by=actor,
            assigned_at=now,
        )

    classification = (
        ClaimInvestigationClassification.objects.select_related(
            "campus_context_reviewed_by"
        )
        .prefetch_related(
            "institution_associations__institution",
            "institution_associations__assigned_by",
        )
        .get(claim_id=claim_id)
    )
    new_state = serialize_claim_institution_context(classification)

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.CLAIM_INSTITUTION_CONTEXT_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.CLAIM,
        resource_id=classification.claim_id,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        authority_organization=None,
        subject_organization=None,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state,
        new_state=new_state,
    )

    return classification
