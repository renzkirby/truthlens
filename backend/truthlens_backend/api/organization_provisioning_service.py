from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from .accountability_service import record_accountability_event
from .models import (
    AccountabilityEvent,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from .organization_invitation_service import (
    INVITATION_LIFETIME,
    OrganizationInvitationDeliveryError,
    OrganizationInvitationError,
    expire_stale_invitations,
    generate_invitation_token,
    hash_invitation_token,
    normalize_invitation_email,
    send_organization_invitation_email,
)


PROVISION_PARTNER_ORGANIZATION = "PROVISION_PARTNER_ORGANIZATION"


class OrganizationProvisioningError(ValueError):
    pass


class OrganizationProvisioningAuthorizationError(OrganizationProvisioningError):
    pass


class OrganizationProvisioningConflict(OrganizationProvisioningError):
    pass


class OrganizationProvisioningDeliveryError(OrganizationProvisioningError):
    pass


def _require_developer_authority(actor):
    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise OrganizationProvisioningAuthorizationError(
            "An active TruthLens developer superuser is required."
        )


def _lock_organization(organization):
    return Organization.objects.select_for_update(
        of=("self",),
    ).get(
        pk=organization.pk,
    )


def _get_current_owner(organization):
    return (
        OrganizationMembership.objects.select_for_update(
            of=("self",),
        )
        .select_related("user")
        .filter(
            organization=organization,
            role=OrganizationMembership.Role.OWNER,
        )
        .exclude(
            status=OrganizationMembership.Status.LEFT,
        )
        .first()
    )


def _ensure_no_current_owner(organization):
    current_owner = _get_current_owner(organization)

    if current_owner:
        raise OrganizationProvisioningConflict(
            "This organization already has a current Primary Admin."
        )


def _normalize_email(email):
    try:
        return normalize_invitation_email(email)
    except OrganizationInvitationError as error:
        raise OrganizationProvisioningError(str(error)) from error


def _ensure_recipient_has_no_current_membership(
    *,
    organization,
    email,
):
    existing_user_ids = User.objects.filter(
        email__iexact=email,
    ).values_list("pk", flat=True)

    if not existing_user_ids.exists():
        return

    current_membership = (
        OrganizationMembership.objects.select_for_update(
            of=("self",),
        )
        .filter(
            organization=organization,
            user_id__in=existing_user_ids,
        )
        .exclude(
            status=OrganizationMembership.Status.LEFT,
        )
        .first()
    )

    if current_membership:
        raise OrganizationProvisioningConflict(
            "This account already has a current membership in the organization. "
            "Primary Admin transfer is not supported by this workflow."
        )


def _create_primary_admin_invitation(
    *,
    organization,
    email,
    actor,
):
    _require_developer_authority(actor)

    locked_organization = _lock_organization(organization)
    normalized_email = _normalize_email(email)

    expire_stale_invitations(
        organization=locked_organization,
    )
    _ensure_no_current_owner(locked_organization)

    pending_onboarding = (
        OrganizationInvitation.objects.select_for_update(
            of=("self",),
        )
        .filter(
            organization=locked_organization,
            purpose=(
                OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
            ),
            status=OrganizationInvitation.Status.PENDING,
        )
        .first()
    )

    if pending_onboarding:
        raise OrganizationProvisioningConflict(
            "A Primary Admin onboarding invitation is already pending."
        )

    _ensure_recipient_has_no_current_membership(
        organization=locked_organization,
        email=normalized_email,
    )

    if OrganizationInvitation.objects.filter(
        organization=locked_organization,
        email=normalized_email,
        status=OrganizationInvitation.Status.PENDING,
    ).exists():
        raise OrganizationProvisioningConflict(
            "A pending invitation already exists for this email address."
        )

    raw_token = generate_invitation_token()
    now = timezone.now()

    try:
        invitation = OrganizationInvitation.objects.create(
            organization=locked_organization,
            email=normalized_email,
            invited_role=OrganizationMembership.Role.OWNER,
            purpose=(
                OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
            ),
            invited_by=actor,
            token_digest=hash_invitation_token(raw_token),
            status=OrganizationInvitation.Status.PENDING,
            expires_at=now + INVITATION_LIFETIME,
            last_sent_at=now,
        )
    except IntegrityError as error:
        raise OrganizationProvisioningConflict(
            "A Primary Admin onboarding invitation is already pending."
        ) from error

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
        resource_id=invitation.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=locked_organization,
        capability=PROVISION_PARTNER_ORGANIZATION,
        new_state={
            "status": invitation.status,
            "invitation_purpose": invitation.purpose,
            "invited_role": invitation.invited_role,
            "send_count": invitation.send_count,
        },
    )

    return invitation, raw_token


@transaction.atomic
def create_and_send_primary_admin_invitation(
    *,
    organization,
    email,
    actor,
):
    invitation, raw_token = _create_primary_admin_invitation(
        organization=organization,
        email=email,
        actor=actor,
    )

    try:
        send_organization_invitation_email(
            invitation,
            raw_token,
        )
    except OrganizationInvitationDeliveryError as error:
        raise OrganizationProvisioningDeliveryError(
            "The Primary Admin invitation email could not be delivered."
        ) from error

    return invitation


@transaction.atomic
def resend_primary_admin_invitation(
    *,
    invitation,
    actor,
):
    _require_developer_authority(actor)

    locked_organization = _lock_organization(invitation.organization)
    _ensure_no_current_owner(locked_organization)

    locked_invitation = (
        OrganizationInvitation.objects.select_for_update(
            of=("self",),
        )
        .select_related("organization", "invited_by")
        .get(
            pk=invitation.pk,
            organization=locked_organization,
        )
    )

    if (
        locked_invitation.purpose
        != OrganizationInvitation.InvitationPurpose.PRIMARY_ADMIN_ONBOARDING
        or locked_invitation.invited_role != OrganizationMembership.Role.OWNER
    ):
        raise OrganizationProvisioningConflict(
            "Only a Primary Admin onboarding invitation can be resent here."
        )

    if (
        locked_invitation.status != OrganizationInvitation.Status.PENDING
        or locked_invitation.expires_at <= timezone.now()
    ):
        raise OrganizationProvisioningConflict(
            "This invitation is no longer active. Issue a replacement invitation."
        )

    raw_token = generate_invitation_token()
    now = timezone.now()
    previous_send_count = locked_invitation.send_count

    locked_invitation.token_digest = hash_invitation_token(raw_token)
    locked_invitation.expires_at = now + INVITATION_LIFETIME
    locked_invitation.last_sent_at = now
    locked_invitation.send_count = previous_send_count + 1
    locked_invitation.save(
        update_fields=[
            "token_digest",
            "expires_at",
            "last_sent_at",
            "send_count",
            "updated_at",
        ]
    )

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
        resource_id=locked_invitation.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=locked_organization,
        capability=PROVISION_PARTNER_ORGANIZATION,
        previous_state={
            "status": locked_invitation.status,
            "invitation_purpose": locked_invitation.purpose,
            "send_count": previous_send_count,
        },
        new_state={
            "status": locked_invitation.status,
            "invitation_purpose": locked_invitation.purpose,
            "invited_role": locked_invitation.invited_role,
            "send_count": locked_invitation.send_count,
        },
    )

    try:
        send_organization_invitation_email(
            locked_invitation,
            raw_token,
        )
    except OrganizationInvitationDeliveryError as error:
        raise OrganizationProvisioningDeliveryError(
            "The Primary Admin invitation email could not be delivered."
        ) from error

    return locked_invitation
