import hashlib
import secrets

from datetime import timedelta

from django.contrib.auth.models import User
from django.db import (
    IntegrityError,
    transaction,
)
from django.utils import timezone

from .models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from .organization_service import (
    PartnerCapability,
    has_capability,
)
from django.core.exceptions import (
    ValidationError,
)
from django.core.validators import (
    validate_email,
)

INVITATION_LIFETIME = timedelta(
    days=7,
)


class OrganizationInvitationError(ValueError):
    pass


class OrganizationInvitationAuthorizationError(OrganizationInvitationError):
    pass


class OrganizationInvitationConflict(OrganizationInvitationError):
    pass


class InvalidOrganizationInvitationRole(OrganizationInvitationError):
    pass


OWNER_INVITABLE_ROLES = {
    OrganizationMembership.Role.ADMIN,
    OrganizationMembership.Role.LEAD_VERIFIER,
    OrganizationMembership.Role.MODERATOR,
    OrganizationMembership.Role.RESEARCHER,
    OrganizationMembership.Role.CONTRIBUTOR,
}


ADMIN_INVITABLE_ROLES = {
    OrganizationMembership.Role.LEAD_VERIFIER,
    OrganizationMembership.Role.MODERATOR,
    OrganizationMembership.Role.RESEARCHER,
    OrganizationMembership.Role.CONTRIBUTOR,
}


def normalize_invitation_email(
    email,
):
    normalized = str(email or "").strip().lower()

    if not normalized:
        raise OrganizationInvitationError("An email address is required.")

    try:
        validate_email(
            normalized,
        )
    except ValidationError as error:
        raise OrganizationInvitationError("Enter a valid email address.") from error

    return normalized


def hash_invitation_token(
    token,
):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_invitation_token():
    return secrets.token_urlsafe(32)


def get_invitable_roles(
    membership,
):
    if not membership or membership.status != OrganizationMembership.Status.ACTIVE:
        return set()

    if membership.role == OrganizationMembership.Role.OWNER:
        return set(OWNER_INVITABLE_ROLES)

    if membership.role == OrganizationMembership.Role.ADMIN:
        return set(ADMIN_INVITABLE_ROLES)

    return set()


def expire_stale_invitations(
    *,
    organization=None,
    email=None,
):
    queryset = OrganizationInvitation.objects.filter(
        status=(OrganizationInvitation.Status.PENDING),
        expires_at__lte=timezone.now(),
    )

    if organization is not None:
        queryset = queryset.filter(
            organization=organization,
        )

    if email is not None:
        queryset = queryset.filter(
            email=normalize_invitation_email(email),
        )

    return queryset.update(
        status=(OrganizationInvitation.Status.EXPIRED),
        updated_at=timezone.now(),
    )


@transaction.atomic
def create_organization_invitation(
    *,
    organization,
    email,
    invited_role,
    actor,
):
    if not has_capability(
        actor,
        PartnerCapability.MANAGE_ORGANIZATION,
        organization=organization,
    ):
        raise (
            OrganizationInvitationAuthorizationError(
                "You do not have permission "
                "to invite members to this "
                "organization."
            )
        )

    normalized_email = normalize_invitation_email(email)

    actor_membership = (
        OrganizationMembership.objects.select_for_update()
        .filter(
            organization=organization,
            user=actor,
            status=(OrganizationMembership.Status.ACTIVE),
        )
        .first()
    )

    if invited_role not in get_invitable_roles(actor_membership):
        raise InvalidOrganizationInvitationRole(
            "You cannot invite a member " "with this organization role."
        )

    # Ownership changes need their own explicit
    # transfer workflow and must never happen
    # through an ordinary invitation.
    if invited_role == OrganizationMembership.Role.OWNER:
        raise InvalidOrganizationInvitationRole(
            "Organization ownership cannot " "be assigned through an invitation."
        )

    # Materialize stale PENDING records as EXPIRED
    # before checking for a live invitation.
    expire_stale_invitations(
        organization=organization,
        email=normalized_email,
    )

    existing_user = User.objects.filter(
        email__iexact=normalized_email,
    ).first()

    if existing_user:
        existing_membership = OrganizationMembership.objects.filter(
            organization=organization,
            user=existing_user,
        ).first()

        if (
            existing_membership
            and existing_membership.status != OrganizationMembership.Status.LEFT
        ):
            raise (
                OrganizationInvitationConflict(
                    "This user already has a " "current organization " "membership."
                )
            )

    if OrganizationInvitation.objects.filter(
        organization=organization,
        email=normalized_email,
        status=(OrganizationInvitation.Status.PENDING),
    ).exists():
        raise OrganizationInvitationConflict(
            "A pending invitation already " "exists for this email address."
        )

    raw_token = generate_invitation_token()

    now = timezone.now()

    try:
        invitation = OrganizationInvitation.objects.create(
            organization=organization,
            email=normalized_email,
            invited_role=invited_role,
            invited_by=actor,
            token_digest=(hash_invitation_token(raw_token)),
            status=(OrganizationInvitation.Status.PENDING),
            expires_at=(now + INVITATION_LIFETIME),
            last_sent_at=now,
        )

    except IntegrityError as error:
        raise OrganizationInvitationConflict(
            "A pending invitation already " "exists for this email address."
        ) from error

    return invitation, raw_token
