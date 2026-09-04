import hashlib
import secrets
import os
from datetime import timedelta
from django.conf import settings
from django.core.mail import (
    EmailMultiAlternatives,
)
from django.template.loader import (
    render_to_string,
)
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


class OrganizationInvitationNotFound(OrganizationInvitationError):
    pass


class OrganizationInvitationDeliveryError(OrganizationInvitationError):
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


def _normalize_invitation_token(
    raw_token,
):
    token = str(raw_token or "").strip()

    if not token:
        raise (
            OrganizationInvitationNotFound(
                "This invitation link is " "invalid or no longer available."
            )
        )

    return token


def _get_invitation_from_token(
    raw_token,
    *,
    for_update=False,
):
    token = _normalize_invitation_token(
        raw_token,
    )

    token_digest = hash_invitation_token(
        token,
    )

    queryset = OrganizationInvitation.objects.select_related(
        "organization",
        "invited_by",
        "accepted_by",
        "cancelled_by",
    )

    if for_update:
        queryset = queryset.select_for_update(
            of=("self",),
        )

    invitation = queryset.filter(
        token_digest=token_digest,
    ).first()

    if not invitation:
        raise (
            OrganizationInvitationNotFound(
                "This invitation link is " "invalid or no longer available."
            )
        )

    return invitation


def get_organization_invitation_by_token(
    raw_token,
):
    with transaction.atomic():
        invitation = _get_invitation_from_token(
            raw_token,
            for_update=True,
        )

        now = timezone.now()

        if (
            invitation.status == OrganizationInvitation.Status.PENDING
            and invitation.expires_at <= now
        ):
            invitation.status = OrganizationInvitation.Status.EXPIRED

            invitation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

        return invitation


def accept_organization_invitation(
    *,
    raw_token,
    actor,
):
    if not actor or not actor.is_authenticated:
        raise (
            OrganizationInvitationAuthorizationError(
                "You must sign in before " "accepting this invitation."
            )
        )

    expired = False

    accepted_invitation = None
    membership = None

    with transaction.atomic():
        invitation = _get_invitation_from_token(
            raw_token,
            for_update=True,
        )

        now = timezone.now()

        if (
            invitation.status == OrganizationInvitation.Status.PENDING
            and invitation.expires_at <= now
        ):
            invitation.status = OrganizationInvitation.Status.EXPIRED

            invitation.save(
                update_fields=[
                    "status",
                    "updated_at",
                ]
            )

            expired = True

        else:
            if invitation.status == OrganizationInvitation.Status.EXPIRED:
                raise (OrganizationInvitationConflict("This invitation has expired."))

            if invitation.status == OrganizationInvitation.Status.ACCEPTED:
                raise (
                    OrganizationInvitationConflict(
                        "This invitation has " "already been accepted."
                    )
                )

            if invitation.status == OrganizationInvitation.Status.CANCELLED:
                raise (
                    OrganizationInvitationConflict(
                        "This invitation is " "no longer available."
                    )
                )

            if invitation.status != OrganizationInvitation.Status.PENDING:
                raise (
                    OrganizationInvitationConflict(
                        "This invitation cannot " "be accepted."
                    )
                )

            actor_email = str(actor.email or "").strip().lower()

            if not actor_email or actor_email != invitation.email:
                raise (
                    OrganizationInvitationAuthorizationError(
                        "This invitation was " "issued to a different " "email address."
                    )
                )

            # Defense in depth. Ordinary
            # invitations must never produce
            # organization ownership.
            if invitation.invited_role not in OWNER_INVITABLE_ROLES:
                raise (
                    InvalidOrganizationInvitationRole(
                        "This invitation contains " "an invalid organization " "role."
                    )
                )

            membership = (
                OrganizationMembership.objects.select_for_update()
                .filter(
                    organization=(invitation.organization),
                    user=actor,
                )
                .first()
            )

            if membership and membership.status != OrganizationMembership.Status.LEFT:
                raise (
                    OrganizationInvitationConflict(
                        "You already have a "
                        "current membership in "
                        "this organization."
                    )
                )

            if membership:
                membership.role = invitation.invited_role

                membership.status = OrganizationMembership.Status.ACTIVE

                membership.approved_at = now

                # The organization authority
                # that originally issued the
                # invitation remains the
                # approving authority.
                membership.approved_by = invitation.invited_by

                membership.save(
                    update_fields=[
                        "role",
                        "status",
                        "approved_at",
                        "approved_by",
                    ]
                )

            else:
                try:
                    with transaction.atomic():
                        membership = OrganizationMembership.objects.create(
                            organization=(invitation.organization),
                            user=actor,
                            role=(invitation.invited_role),
                            status=(OrganizationMembership.Status.ACTIVE),
                            approved_at=now,
                            approved_by=(invitation.invited_by),
                        )

                except IntegrityError as error:
                    raise (
                        OrganizationInvitationConflict(
                            "You already have a "
                            "current membership in "
                            "this organization."
                        )
                    ) from error

            invitation.status = OrganizationInvitation.Status.ACCEPTED

            invitation.accepted_by = actor
            invitation.accepted_at = now

            # Consume the invitation token.
            #
            # This makes acceptance genuinely
            # single-use even if a later caller
            # accidentally looks up the token
            # before checking status.
            invitation.token_digest = hash_invitation_token(generate_invitation_token())

            invitation.save(
                update_fields=[
                    "status",
                    "accepted_by",
                    "accepted_at",
                    "token_digest",
                    "updated_at",
                ]
            )

            accepted_invitation = invitation

    # Raise only AFTER leaving the transaction so
    # the EXPIRED materialization above commits.
    if expired:
        raise (OrganizationInvitationConflict("This invitation has expired."))

    return {
        "invitation": accepted_invitation,
        "membership": membership,
    }


def build_invitation_url(
    raw_token,
):
    frontend_url = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173",
    ).rstrip("/")

    return f"{frontend_url}/" f"organization-invitations/" f"{raw_token}"


def send_organization_invitation_email(
    invitation,
    raw_token,
):
    invitation_url = build_invitation_url(
        raw_token,
    )

    role_label = invitation.get_invited_role_display()

    inviter_name = (
        invitation.invited_by.username
        if invitation.invited_by
        else "An organization administrator"
    )

    subject = (
        f"You're invited to join " f"{invitation.organization.name} " f"on TruthLens"
    )

    text_body = (
        f"{inviter_name} invited you to "
        f"join {invitation.organization.name} "
        f"as {role_label} on TruthLens.\n\n"
        f"Accept the invitation:\n"
        f"{invitation_url}\n\n"
        f"This invitation expires on "
        f"{invitation.expires_at:%Y-%m-%d %H:%M %Z}.\n\n"
        f"If you were not expecting this "
        f"invitation, you can ignore this email."
    )

    html_body = render_to_string(
        "emails/organization_invitation.html",
        {
            "organization_name": (invitation.organization.name),
            "role_label": role_label,
            "inviter_name": inviter_name,
            "invitation_url": invitation_url,
            "expires_at": (invitation.expires_at),
        },
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=(settings.DEFAULT_FROM_EMAIL),
        to=[invitation.email],
    )

    message.attach_alternative(
        html_body,
        "text/html",
    )

    try:
        message.send(
            fail_silently=False,
        )
    except Exception as error:
        raise (
            OrganizationInvitationDeliveryError(
                "The invitation email " "could not be delivered."
            )
        ) from error


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


@transaction.atomic
def create_and_send_organization_invitation(
    *,
    organization,
    email,
    invited_role,
    actor,
):
    invitation, raw_token = create_organization_invitation(
        organization=organization,
        email=email,
        invited_role=invited_role,
        actor=actor,
    )

    send_organization_invitation_email(
        invitation,
        raw_token,
    )

    return invitation


def get_organization_invitations(
    *,
    organization,
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
                "to manage invitations for "
                "this organization."
            )
        )

    expire_stale_invitations(
        organization=organization,
    )

    return (
        OrganizationInvitation.objects.filter(
            organization=organization,
        )
        .select_related(
            "organization",
            "invited_by",
            "accepted_by",
            "cancelled_by",
        )
        .order_by(
            "-created_at",
            "id",
        )
    )


def _get_actor_membership_for_update(
    *,
    organization,
    actor,
):
    return (
        OrganizationMembership.objects.select_for_update()
        .filter(
            organization=organization,
            user=actor,
            status=(OrganizationMembership.Status.ACTIVE),
        )
        .first()
    )


def _require_invitation_role_authority(
    *,
    organization,
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
                "to manage invitations for "
                "this organization."
            )
        )

    actor_membership = _get_actor_membership_for_update(
        organization=organization,
        actor=actor,
    )

    if invited_role not in get_invitable_roles(actor_membership):
        raise (
            InvalidOrganizationInvitationRole(
                "You cannot manage an " "invitation for this " "organization role."
            )
        )

    return actor_membership


def resend_organization_invitation(
    *,
    invitation,
    actor,
):
    organization = invitation.organization

    if not has_capability(
        actor,
        PartnerCapability.MANAGE_ORGANIZATION,
        organization=organization,
    ):
        raise (
            OrganizationInvitationAuthorizationError(
                "You do not have permission " "to resend this invitation."
            )
        )

    expire_stale_invitations(
        organization=organization,
    )

    with transaction.atomic():
        locked = (
            OrganizationInvitation.objects.select_related(
                "organization",
                "invited_by",
            )
            .select_for_update(
                of=("self",),
            )
            .get(
                pk=invitation.pk,
            )
        )

        _require_invitation_role_authority(
            organization=organization,
            invited_role=locked.invited_role,
            actor=actor,
        )

        if locked.status != OrganizationInvitation.Status.PENDING:
            raise (
                OrganizationInvitationConflict(
                    "Only a pending invitation " "can be resent."
                )
            )

        raw_token = generate_invitation_token()

        now = timezone.now()

        locked.token_digest = hash_invitation_token(raw_token)

        locked.expires_at = now + INVITATION_LIFETIME

        locked.last_sent_at = now

        locked.send_count = locked.send_count + 1

        locked.save(
            update_fields=[
                "token_digest",
                "expires_at",
                "last_sent_at",
                "send_count",
                "updated_at",
            ]
        )

        send_organization_invitation_email(
            locked,
            raw_token,
        )

        return locked


def cancel_organization_invitation(
    *,
    invitation,
    actor,
):
    organization = invitation.organization

    if not has_capability(
        actor,
        PartnerCapability.MANAGE_ORGANIZATION,
        organization=organization,
    ):
        raise (
            OrganizationInvitationAuthorizationError(
                "You do not have permission " "to cancel this invitation."
            )
        )

    expire_stale_invitations(
        organization=organization,
    )

    with transaction.atomic():
        locked = (
            OrganizationInvitation.objects.select_related(
                "organization",
            )
            .select_for_update(
                of=("self",),
            )
            .get(
                pk=invitation.pk,
            )
        )

        _require_invitation_role_authority(
            organization=organization,
            invited_role=locked.invited_role,
            actor=actor,
        )

        if locked.status != OrganizationInvitation.Status.PENDING:
            raise (
                OrganizationInvitationConflict(
                    "Only a pending invitation " "can be cancelled."
                )
            )

        locked.status = OrganizationInvitation.Status.CANCELLED

        locked.cancelled_by = actor
        locked.cancelled_at = timezone.now()

        # Invalidate the previously issued
        # invitation URL immediately.
        locked.token_digest = hash_invitation_token(generate_invitation_token())

        locked.save(
            update_fields=[
                "status",
                "cancelled_by",
                "cancelled_at",
                "token_digest",
                "updated_at",
            ]
        )

        return locked
