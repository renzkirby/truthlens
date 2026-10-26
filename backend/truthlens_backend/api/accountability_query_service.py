"""Capability-scoped, read-only projections of accountability history."""

import re

from django.db.models import Q

from .management_governance_service import MANAGE_PARTNER_ORGANIZATION
from .management_permissions import can_access_management_console
from .models import AccountabilityEvent
from .organization_provisioning_service import PROVISION_PARTNER_ORGANIZATION
from .organization_service import PartnerCapability, has_capability
from .platform_identity_service import can_review_platform_safety
from .platform_staff_service import MANAGE_PLATFORM_STAFF


class AccountabilityDomain:
    VERIFICATION = "VERIFICATION"
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN"
    SAFETY = "SAFETY"
    EVIDENCE = "EVIDENCE"
    ADJUDICATION = "ADJUDICATION"
    PUBLICATION = "PUBLICATION"
    FACTUAL_CORRECTION = "FACTUAL_CORRECTION"
    PLATFORM_GOVERNANCE = "PLATFORM_GOVERNANCE"


DOMAIN_LABELS = {
    AccountabilityDomain.VERIFICATION: "Verification",
    AccountabilityDomain.ORGANIZATION_ADMIN: "Organization Admin",
    AccountabilityDomain.SAFETY: "Safety",
    AccountabilityDomain.EVIDENCE: "Evidence",
    AccountabilityDomain.ADJUDICATION: "Adjudication",
    AccountabilityDomain.PUBLICATION: "Publication",
    AccountabilityDomain.FACTUAL_CORRECTION: "Factual Correction",
    AccountabilityDomain.PLATFORM_GOVERNANCE: "Platform Governance",
}

DOMAIN_ACTIONS = {
    AccountabilityDomain.VERIFICATION: (
        AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CREATED,
        AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED,
        AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_RELEASED,
        AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_COMPLETED,
    ),
    AccountabilityDomain.ORGANIZATION_ADMIN: (
        AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_ROLE_CHANGED,
        AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_SUSPENDED,
        AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_RESTORED,
        AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_REMOVED,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_ACCEPTED,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_EXPIRED,
        AccountabilityEvent.ActionType.ORGANIZATION_PUBLIC_PROFILE_UPDATED,
        AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_REQUESTED,
        AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_ACTIVATED,
        AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED,
        AccountabilityEvent.ActionType.ORGANIZATION_LOGO_UPDATED,
        AccountabilityEvent.ActionType.ORGANIZATION_LOGO_REMOVED,
    ),
    AccountabilityDomain.SAFETY: (
        AccountabilityEvent.ActionType.SAFETY_CASE_CLAIMED,
        AccountabilityEvent.ActionType.SAFETY_CASE_RELEASED,
        AccountabilityEvent.ActionType.SAFETY_CASE_ESCALATED,
        AccountabilityEvent.ActionType.SAFETY_DISMISSED,
        AccountabilityEvent.ActionType.SAFETY_CONTENT_REMOVED,
    ),
    AccountabilityDomain.EVIDENCE: (
        AccountabilityEvent.ActionType.EVIDENCE_REOPENED,
        AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
        AccountabilityEvent.ActionType.EVIDENCE_REJECTED,
    ),
    AccountabilityDomain.ADJUDICATION: (
        AccountabilityEvent.ActionType.ADJUDICATION_STARTED,
        AccountabilityEvent.ActionType.VERDICT_ISSUED,
        AccountabilityEvent.ActionType.VERDICT_REVISED,
    ),
    AccountabilityDomain.PUBLICATION: (
        AccountabilityEvent.ActionType.ARTICLE_DRAFT_CREATED,
        AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
        AccountabilityEvent.ActionType.ARTICLE_SUBMITTED,
        AccountabilityEvent.ActionType.ARTICLE_RETURNED_FOR_REWORK,
        AccountabilityEvent.ActionType.ARTICLE_ABANDONED,
        AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
        AccountabilityEvent.ActionType.ARTICLE_REVISION_DRAFTED,
        AccountabilityEvent.ActionType.ARTICLE_REVISED,
    ),
    AccountabilityDomain.FACTUAL_CORRECTION: (
        AccountabilityEvent.ActionType.FACTUAL_CORRECTION_REQUESTED,
        AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PROPOSAL_SAVED,
        AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PROPOSAL_PREPARED,
        AccountabilityEvent.ActionType.FACTUAL_CORRECTION_CANCELLED,
        AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PUBLISHED,
    ),
    AccountabilityDomain.PLATFORM_GOVERNANCE: (
        AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
        AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        AccountabilityEvent.ActionType.INSTITUTION_CREATED,
        AccountabilityEvent.ActionType.ORGANIZATION_INSTITUTION_AFFILIATION_UPDATED,
        AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_APPROVED,
        AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT,
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
        AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_REVOKED,
        AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CREATED,
        AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_RESENT,
        AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CANCELLED,
    ),
}

ACTION_DOMAINS = {
    action: domain for domain, actions in DOMAIN_ACTIONS.items() for action in actions
}
# Invitation actions remain Organization Admin records in organization-scoped
# projections. Their platform-provisioning variants are projected explicitly as
# Platform Governance below.
ACTION_DOMAINS.update(
    {
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED: (
            AccountabilityDomain.ORGANIZATION_ADMIN
        ),
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT: (
            AccountabilityDomain.ORGANIZATION_ADMIN
        ),
        AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED: (
            AccountabilityDomain.ORGANIZATION_ADMIN
        ),
        AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_ACCEPTED: (
            AccountabilityDomain.PLATFORM_GOVERNANCE
        ),
        AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_EXPIRED: (
            AccountabilityDomain.PLATFORM_GOVERNANCE
        ),
    }
)

ORGANIZATION_DOMAINS = (
    AccountabilityDomain.VERIFICATION,
    AccountabilityDomain.ORGANIZATION_ADMIN,
    AccountabilityDomain.EVIDENCE,
    AccountabilityDomain.ADJUDICATION,
    AccountabilityDomain.PUBLICATION,
    AccountabilityDomain.FACTUAL_CORRECTION,
)

CAPABILITY_DOMAINS = {
    PartnerCapability.CLAIM_VERIFICATION_WORK: {
        AccountabilityDomain.VERIFICATION,
    },
    PartnerCapability.REVIEW_EVIDENCE: {
        AccountabilityDomain.EVIDENCE,
        AccountabilityDomain.FACTUAL_CORRECTION,
    },
    PartnerCapability.ADJUDICATE: {
        AccountabilityDomain.ADJUDICATION,
        AccountabilityDomain.FACTUAL_CORRECTION,
    },
    PartnerCapability.CREATE_FACT_CHECK_DRAFT: {
        AccountabilityDomain.PUBLICATION,
        AccountabilityDomain.FACTUAL_CORRECTION,
    },
    PartnerCapability.PUBLISH_FACT_CHECK: {
        AccountabilityDomain.PUBLICATION,
        AccountabilityDomain.FACTUAL_CORRECTION,
    },
    PartnerCapability.MANAGE_ORGANIZATION: set(ORGANIZATION_DOMAINS),
}

DOMAIN_RESOURCES = {
    AccountabilityDomain.VERIFICATION: {
        AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
    },
    AccountabilityDomain.ORGANIZATION_ADMIN: {
        AccountabilityEvent.ResourceType.ORGANIZATION_MEMBERSHIP,
        AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
        AccountabilityEvent.ResourceType.ORGANIZATION,
    },
    AccountabilityDomain.SAFETY: {
        AccountabilityEvent.ResourceType.MODERATION_CASE,
    },
    AccountabilityDomain.EVIDENCE: {
        AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
    },
    AccountabilityDomain.ADJUDICATION: {
        AccountabilityEvent.ResourceType.MODERATION_CASE,
        AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
    },
    AccountabilityDomain.PUBLICATION: {
        AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
    },
    AccountabilityDomain.FACTUAL_CORRECTION: {
        AccountabilityEvent.ResourceType.FACTUAL_CORRECTION_REQUEST,
        AccountabilityEvent.ResourceType.FACTUAL_CORRECTION_PROPOSAL,
        AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
        AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
    },
    AccountabilityDomain.PLATFORM_GOVERNANCE: {
        AccountabilityEvent.ResourceType.CLAIM,
        AccountabilityEvent.ResourceType.ORGANIZATION,
        AccountabilityEvent.ResourceType.INSTITUTION,
        AccountabilityEvent.ResourceType.ORGANIZATION_INSTITUTION_AFFILIATION,
        AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
        AccountabilityEvent.ResourceType.USER_ACCOUNT,
        AccountabilityEvent.ResourceType.PLATFORM_STAFF_INVITATION,
    },
}

ORGANIZATION_ACTIONS = tuple(
    action for domain in ORGANIZATION_DOMAINS for action in DOMAIN_ACTIONS[domain]
)
SAFETY_ACTIONS = DOMAIN_ACTIONS[AccountabilityDomain.SAFETY]
MANAGEMENT_GOVERNANCE_ACTIONS = DOMAIN_ACTIONS[
    AccountabilityDomain.PLATFORM_GOVERNANCE
]
MANAGEMENT_GOVERNANCE_ACTION_CAPABILITIES = {
    AccountabilityEvent.ActionType.ORGANIZATION_CREATED: (
        MANAGE_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED: (
        MANAGE_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.INSTITUTION_CREATED: (
        MANAGE_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.ORGANIZATION_INSTITUTION_AFFILIATION_UPDATED: (
        MANAGE_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_APPROVED: (
        MANAGE_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED: (
        MANAGE_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED: (
        PROVISION_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT: (
        PROVISION_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED: (
        PROVISION_PARTNER_ORGANIZATION
    ),
    AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_REVOKED: (
        MANAGE_PLATFORM_STAFF
    ),
    AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CREATED: (
        MANAGE_PLATFORM_STAFF
    ),
    AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_RESENT: (
        MANAGE_PLATFORM_STAFF
    ),
    AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CANCELLED: (
        MANAGE_PLATFORM_STAFF
    ),
}

_ACTION_LABELS = dict(AccountabilityEvent.ActionType.choices)
_RESOURCE_LABELS = dict(AccountabilityEvent.ResourceType.choices)
_VALID_DOMAINS = frozenset((*ORGANIZATION_DOMAINS, AccountabilityDomain.SAFETY))
_VALID_ACTIONS = frozenset(ACTION_DOMAINS)
_VALID_RESOURCES = frozenset(_RESOURCE_LABELS)

_SECRET_KEY_PARTS = frozenset(
    {
        "token",
        "digest",
        "password",
        "secret",
        "authorization",
        "cookie",
        "api_key",
        "access_key",
        "private_key",
    }
)
_PRIVATE_CONTENT_KEYS = frozenset(
    {
        "email",
        "article_body",
        "evidence_body",
        "source_payload",
        "ai_analysis",
        "file_body",
        "file_bytes",
        "upload_payload",
    }
)
_EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"
)


class AccountabilityQueryError(Exception):
    pass


class AccountabilityQueryAuthorizationError(AccountabilityQueryError):
    pass


class AccountabilityQueryInputError(AccountabilityQueryError):
    pass


class AccountabilityQueryNotFound(AccountabilityQueryError):
    pass


def _normalized_key(value):
    key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value).strip())
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _is_private_key(key):
    normalized = _normalized_key(key)
    segments = set(normalized.split("_"))
    return (
        normalized in _SECRET_KEY_PARTS
        or normalized in _PRIVATE_CONTENT_KEYS
        or bool(segments.intersection({"token", "digest", "password", "secret", "authorization", "cookie", "email"}))
        or any(part in normalized for part in ("api_key", "access_key", "private_key"))
        or any(part in normalized for part in _PRIVATE_CONTENT_KEYS - {"email"})
    )


def _sanitize_json(value):
    """Return a sanitized copy; never mutate the append-only stored value."""
    if isinstance(value, dict):
        return {
            str(key): _sanitize_json(nested)
            for key, nested in value.items()
            if not _is_private_key(key)
            and not isinstance(nested, (bytes, bytearray, memoryview))
        }
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_json(nested)
            for nested in value
            if not isinstance(nested, (bytes, bytearray, memoryview))
        ]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    if isinstance(value, str):
        return _EMAIL_PATTERN.sub("[redacted email]", value)
    return value


def _visible_organization_domains(actor, organization):
    visible = set()
    for capability, domains in CAPABILITY_DOMAINS.items():
        if has_capability(actor, capability, organization=organization):
            visible.update(domains)
    return tuple(domain for domain in ORGANIZATION_DOMAINS if domain in visible)


def _validate_query_inputs(
    *, domain, action_type, resource_type, created_after, created_before, limit, offset
):
    if domain and domain not in _VALID_DOMAINS:
        raise AccountabilityQueryInputError("Select a valid accountability domain.")
    if action_type and action_type not in _VALID_ACTIONS:
        raise AccountabilityQueryInputError("Select a valid accountability action.")
    if resource_type and resource_type not in _VALID_RESOURCES:
        raise AccountabilityQueryInputError("Select a valid accountability resource.")
    if limit < 1 or limit > 100:
        raise AccountabilityQueryInputError("limit must be between 1 and 100.")
    if offset < 0:
        raise AccountabilityQueryInputError("offset must be zero or greater.")
    if created_after and created_before and created_after > created_before:
        raise AccountabilityQueryInputError(
            "created_after must not be later than created_before."
        )


def _apply_filters(
    queryset,
    *,
    domain,
    action_type,
    resource_type,
    resource_id,
    actor_search,
    created_after,
    created_before,
):
    if domain:
        queryset = queryset.filter(action_type__in=DOMAIN_ACTIONS[domain])
    if action_type:
        queryset = queryset.filter(action_type=action_type)
    if resource_type:
        queryset = queryset.filter(resource_type=resource_type)
    if resource_id:
        queryset = queryset.filter(resource_id=resource_id)
    if actor_search:
        queryset = queryset.filter(actor_username_snapshot__icontains=actor_search)
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)
    return queryset


def _organization_snapshot(foreign_key, name_snapshot):
    if foreign_key is None and not name_snapshot:
        return None
    return {
        "id": str(foreign_key.pk) if foreign_key is not None else None,
        "name": name_snapshot or None,
    }


def _safe_actor_snapshot_id(actor_snapshot):
    if not isinstance(actor_snapshot, dict):
        return None
    value = actor_snapshot.get("id")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    normalized = str(value).strip()
    return normalized or None


def _actor_payload(event, context):
    actor_snapshot = context.pop("actor_snapshot", None)
    durable_id = _safe_actor_snapshot_id(actor_snapshot)
    username = event.actor_username_snapshot or None
    if event.actor_id is None and username is None and durable_id is None:
        return None
    return {
        "id": str(event.actor_id) if event.actor_id is not None else durable_id,
        "username": username,
        "historical": event.actor_id is None and bool(username or durable_id),
    }


def _event_payload(event, *, domain_override=None):
    context = _sanitize_json(event.context or {})
    domain = domain_override or ACTION_DOMAINS[event.action_type]
    return {
        "id": str(event.pk),
        "action_type": event.action_type,
        "action_label": _ACTION_LABELS[event.action_type],
        "domain": domain,
        "domain_label": DOMAIN_LABELS[domain],
        "actor": _actor_payload(event, context),
        "authority": {
            "scope": event.authority_scope,
            "capability": event.capability,
            "organization": _organization_snapshot(
                event.authority_organization,
                event.authority_organization_name_snapshot,
            ),
        },
        "subject_organization": _organization_snapshot(
            event.subject_organization,
            event.subject_organization_name_snapshot,
        ),
        "resource": {
            "type": event.resource_type,
            "label": _RESOURCE_LABELS[event.resource_type],
            "id": event.resource_id,
        },
        "previous_state": _sanitize_json(event.previous_state or {}),
        "new_state": _sanitize_json(event.new_state or {}),
        "reason_code": event.reason_code,
        "notes": _EMAIL_PATTERN.sub("[redacted email]", event.notes),
        "context": context,
        "created_at": event.created_at,
    }


def _filter_options(domains):
    actions = [
        (domain, action)
        for domain in domains
        for action in DOMAIN_ACTIONS[domain]
    ]
    resources = {
        resource for domain in domains for resource in DOMAIN_RESOURCES[domain]
    }
    return {
        "domains": [
            {"value": domain, "label": DOMAIN_LABELS[domain]} for domain in domains
        ],
        "actions": [
            {
                "value": action,
                "label": _ACTION_LABELS[action],
                "domain": domain,
            }
            for domain, action in actions
        ],
        "resources": [
            {"value": value, "label": label}
            for value, label in AccountabilityEvent.ResourceType.choices
            if value in resources
        ],
    }


def _page_payload(
    *, queryset, limit, offset, scope, organization, domains, event_domain=None
):
    count = queryset.count()
    events = queryset.order_by("-created_at", "-id")[offset : offset + limit]
    return {
        "count": count,
        "limit": limit,
        "offset": offset,
        "scope": scope,
        "organization": (
            {"id": str(organization.pk), "name": organization.name}
            if organization is not None
            else None
        ),
        "filter_options": _filter_options(domains),
        "results": [
            _event_payload(event, domain_override=event_domain) for event in events
        ],
    }


def _require_management_governance_authority(actor):
    if not can_access_management_console(actor):
        raise AccountabilityQueryAuthorizationError(
            "Platform management administrator access is required."
        )


def _management_governance_queryset():
    governance_pairs = Q()
    for action_type, capability in MANAGEMENT_GOVERNANCE_ACTION_CAPABILITIES.items():
        if action_type in {
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT,
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
        }:
            resource_type = AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION
        elif action_type == AccountabilityEvent.ActionType.PLATFORM_SAFETY_MODERATOR_REVOKED:
            resource_type = AccountabilityEvent.ResourceType.USER_ACCOUNT
        elif action_type in {
            AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CREATED,
            AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_RESENT,
            AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CANCELLED,
        }:
            resource_type = AccountabilityEvent.ResourceType.PLATFORM_STAFF_INVITATION
        else:
            resource_type = AccountabilityEvent.ResourceType.ORGANIZATION
        governance_pairs |= Q(
            action_type=action_type,
            capability=capability,
            resource_type=resource_type,
        )

    return (
        AccountabilityEvent.objects.filter(
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        .filter(governance_pairs)
        .select_related("actor", "authority_organization", "subject_organization")
    )


def list_management_governance_accountability_events(
    *,
    actor,
    action_type="",
    organization_search="",
    actor_search="",
    created_after=None,
    created_before=None,
    limit=25,
    offset=0,
):
    _require_management_governance_authority(actor)
    _validate_query_inputs(
        domain="",
        action_type=action_type,
        resource_type="",
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    if action_type and action_type not in MANAGEMENT_GOVERNANCE_ACTIONS:
        raise AccountabilityQueryInputError(
            "Select a valid Management Governance action."
        )

    queryset = _management_governance_queryset()
    if action_type:
        queryset = queryset.filter(action_type=action_type)
    if organization_search:
        queryset = queryset.filter(
            Q(subject_organization_name_snapshot__icontains=organization_search)
            | Q(subject_organization__name__icontains=organization_search)
        )
    if actor_search:
        queryset = queryset.filter(
            actor_username_snapshot__icontains=actor_search
        )
    if created_after:
        queryset = queryset.filter(created_at__gte=created_after)
    if created_before:
        queryset = queryset.filter(created_at__lte=created_before)

    return _page_payload(
        queryset=queryset,
        limit=limit,
        offset=offset,
        scope="PLATFORM",
        organization=None,
        domains=(AccountabilityDomain.PLATFORM_GOVERNANCE,),
        event_domain=AccountabilityDomain.PLATFORM_GOVERNANCE,
    )


def get_management_governance_accountability_event(*, actor, event_id):
    _require_management_governance_authority(actor)
    try:
        event = _management_governance_queryset().get(pk=event_id)
    except AccountabilityEvent.DoesNotExist as error:
        raise AccountabilityQueryNotFound(
            "Management governance audit event not found."
        ) from error

    return _event_payload(
        event,
        domain_override=AccountabilityDomain.PLATFORM_GOVERNANCE,
    )


def list_organization_accountability_events(
    *,
    actor,
    organization,
    domain="",
    action_type="",
    resource_type="",
    resource_id="",
    actor_search="",
    created_after=None,
    created_before=None,
    limit=25,
    offset=0,
):
    _validate_query_inputs(
        domain=domain,
        action_type=action_type,
        resource_type=resource_type,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    visible_domains = _visible_organization_domains(actor, organization)
    if not visible_domains:
        raise AccountabilityQueryAuthorizationError(
            "You do not have permission to view this organization's accountability history."
        )

    visible_actions = [
        action for visible_domain in visible_domains for action in DOMAIN_ACTIONS[visible_domain]
    ]
    queryset = AccountabilityEvent.objects.filter(
        subject_organization=organization,
        action_type__in=visible_actions,
    ).exclude(
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
    ).select_related("actor", "authority_organization", "subject_organization")
    queryset = _apply_filters(
        queryset,
        domain=domain,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_search=actor_search,
        created_after=created_after,
        created_before=created_before,
    )
    return _page_payload(
        queryset=queryset,
        limit=limit,
        offset=offset,
        scope="ORGANIZATION",
        organization=organization,
        domains=visible_domains,
    )


def list_platform_accountability_events(
    *,
    actor,
    domain="",
    action_type="",
    resource_type="",
    resource_id="",
    actor_search="",
    created_after=None,
    created_before=None,
    limit=25,
    offset=0,
):
    _validate_query_inputs(
        domain=domain,
        action_type=action_type,
        resource_type=resource_type,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        offset=offset,
    )
    if not can_review_platform_safety(actor):
        raise AccountabilityQueryAuthorizationError(
            "You do not have permission to view Platform Safety accountability history."
        )

    queryset = AccountabilityEvent.objects.filter(
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        action_type__in=SAFETY_ACTIONS,
    ).select_related("actor", "authority_organization", "subject_organization")
    queryset = _apply_filters(
        queryset,
        domain=domain,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_search=actor_search,
        created_after=created_after,
        created_before=created_before,
    )
    return _page_payload(
        queryset=queryset,
        limit=limit,
        offset=offset,
        scope="PLATFORM",
        organization=None,
        domains=(AccountabilityDomain.SAFETY,),
    )
