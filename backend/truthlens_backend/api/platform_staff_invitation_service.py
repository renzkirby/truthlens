import os

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .accountability_service import record_accountability_event
from .management_permissions import can_access_management_console
from .models import AccountabilityEvent, PlatformStaffInvitation, UserProfile
from .organization_invitation_service import (
    INVITATION_LIFETIME,
    generate_invitation_token,
    hash_invitation_token,
    normalize_invitation_email,
)
from .platform_identity_service import PLATFORM_SAFETY_PROFILE_ROLES
from .platform_staff_service import MANAGE_PLATFORM_STAFF


class PlatformStaffInvitationError(ValueError):
    pass


class PlatformStaffInvitationAuthorizationError(PlatformStaffInvitationError):
    pass


class PlatformStaffInvitationConflict(PlatformStaffInvitationError):
    pass


class PlatformStaffInvitationNotFound(PlatformStaffInvitationError):
    pass


class PlatformStaffInvitationDeliveryError(PlatformStaffInvitationError):
    pass


def _require_platform_admin(actor):
    if not can_access_management_console(actor):
        raise PlatformStaffInvitationAuthorizationError(
            "Platform Admin access is required to manage Platform Staff invitations."
        )


def _normalize_token(raw_token):
    token = str(raw_token or "").strip()
    if not token:
        raise PlatformStaffInvitationNotFound(
            "This invitation link is invalid or no longer available."
        )
    return token


def _get_invitation_from_token(raw_token, *, for_update=False):
    token_digest = hash_invitation_token(_normalize_token(raw_token))
    queryset = PlatformStaffInvitation.objects.select_related(
        "invited_by",
        "accepted_by",
        "cancelled_by",
    )
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    invitation = queryset.filter(token_digest=token_digest).first()
    if invitation is None:
        raise PlatformStaffInvitationNotFound(
            "This invitation link is invalid or no longer available."
        )
    return invitation


def _record_platform_event(*, invitation, actor, action_type, previous_state=None, new_state=None):
    return record_accountability_event(
        action_type=action_type,
        resource_type=AccountabilityEvent.ResourceType.PLATFORM_STAFF_INVITATION,
        resource_id=invitation.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        capability=MANAGE_PLATFORM_STAFF,
        previous_state=previous_state or {},
        new_state=new_state or {},
        context={
            "invited_email": invitation.email,
            "platform_role": invitation.platform_role,
        },
    )


def _record_expired(invitation):
    return record_accountability_event(
        action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_EXPIRED,
        resource_type=AccountabilityEvent.ResourceType.PLATFORM_STAFF_INVITATION,
        resource_id=invitation.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
        previous_state={"status": PlatformStaffInvitation.Status.PENDING},
        new_state={"status": PlatformStaffInvitation.Status.EXPIRED},
        context={
            "invited_email": invitation.email,
            "platform_role": invitation.platform_role,
        },
    )


def _materialize_expired(invitation, *, now=None):
    now = now or timezone.now()
    if (
        invitation.status == PlatformStaffInvitation.Status.PENDING
        and invitation.expires_at <= now
    ):
        invitation.status = PlatformStaffInvitation.Status.EXPIRED
        invitation.save(update_fields=["status", "updated_at"])
        _record_expired(invitation)
        return True
    return False


def expire_stale_platform_staff_invitations(*, email=None):
    with transaction.atomic():
        queryset = PlatformStaffInvitation.objects.select_for_update(of=("self",)).filter(
            status=PlatformStaffInvitation.Status.PENDING,
            expires_at__lte=timezone.now(),
        )
        if email:
            queryset = queryset.filter(email=normalize_invitation_email(email))
        invitations = list(queryset.order_by("created_at", "id"))
        for invitation in invitations:
            _materialize_expired(invitation)
        return len(invitations)


def get_platform_staff_invitations(*, actor):
    _require_platform_admin(actor)
    expire_stale_platform_staff_invitations()
    return PlatformStaffInvitation.objects.select_related(
        "invited_by",
        "accepted_by",
        "cancelled_by",
    ).order_by("-created_at", "-id")


def create_platform_staff_invitation(*, email, actor):
    _require_platform_admin(actor)
    normalized_email = normalize_invitation_email(email)
    expire_stale_platform_staff_invitations(email=normalized_email)

    existing_users = list(
        User.objects.select_related("profile").filter(
            email__iexact=normalized_email,
        )
    )
    for existing_user in existing_users:
        if existing_user.is_superuser:
            raise PlatformStaffInvitationConflict(
                "This email already belongs to a Platform Admin account."
            )
        profile = getattr(existing_user, "profile", None)
        if profile and profile.role in PLATFORM_SAFETY_PROFILE_ROLES:
            raise PlatformStaffInvitationConflict(
                "This email already belongs to a Platform Safety Moderator."
            )

    if existing_users and not any(user.is_active for user in existing_users):
        raise PlatformStaffInvitationConflict(
            "This email belongs to an inactive TruthLens account. "
            "Reactivate the account before issuing a Platform Staff invitation."
        )

    if PlatformStaffInvitation.objects.filter(
        email=normalized_email,
        status=PlatformStaffInvitation.Status.PENDING,
    ).exists():
        raise PlatformStaffInvitationConflict(
            "A pending Platform Staff invitation already exists for this email address."
        )

    raw_token = generate_invitation_token()
    now = timezone.now()
    try:
        invitation = PlatformStaffInvitation.objects.create(
            email=normalized_email,
            platform_role=(
                PlatformStaffInvitation.PlatformRole.PLATFORM_SAFETY_MODERATOR
            ),
            invited_by=actor,
            token_digest=hash_invitation_token(raw_token),
            status=PlatformStaffInvitation.Status.PENDING,
            expires_at=now + INVITATION_LIFETIME,
            last_sent_at=now,
        )
    except IntegrityError as error:
        raise PlatformStaffInvitationConflict(
            "A pending Platform Staff invitation already exists for this email address."
        ) from error

    _record_platform_event(
        invitation=invitation,
        actor=actor,
        action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CREATED,
        new_state={
            "status": invitation.status,
            "platform_role": invitation.platform_role,
            "send_count": invitation.send_count,
        },
    )
    return invitation, raw_token


def build_platform_staff_invitation_url(raw_token):
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    return f"{frontend_url}/platform-staff-invitations/{raw_token}"


def send_platform_staff_invitation_email(invitation, raw_token):
    invitation_url = build_platform_staff_invitation_url(raw_token)
    inviter_name = (
        invitation.invited_by.username
        if invitation.invited_by
        else "A TruthLens Platform Admin"
    )
    role_label = invitation.get_platform_role_display()
    subject = f"You're invited to join TruthLens as {role_label}"
    text_body = (
        f"{inviter_name} invited you to join TruthLens as {role_label}.\n\n"
        f"Accept the invitation:\n{invitation_url}\n\n"
        f"This invitation expires on {invitation.expires_at:%Y-%m-%d %H:%M %Z}.\n\n"
        "Platform Safety staff review policy violations and do not determine factual truth. "
        "While this platform role is active, the staff account does not participate in "
        "Community reputation.\n\n"
        "If you were not expecting this invitation, you can ignore this email."
    )
    html_body = render_to_string(
        "emails/platform_staff_invitation.html",
        {
            "inviter_name": inviter_name,
            "role_label": role_label,
            "invitation_url": invitation_url,
            "expires_at": invitation.expires_at,
        },
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invitation.email],
    )
    message.attach_alternative(html_body, "text/html")
    try:
        message.send(fail_silently=False)
    except Exception as error:
        raise PlatformStaffInvitationDeliveryError(
            "The Platform Staff invitation email could not be delivered."
        ) from error


@transaction.atomic
def create_and_send_platform_staff_invitation(*, email, actor):
    invitation, raw_token = create_platform_staff_invitation(
        email=email,
        actor=actor,
    )
    send_platform_staff_invitation_email(invitation, raw_token)
    return invitation


def resend_platform_staff_invitation(*, invitation, actor):
    _require_platform_admin(actor)
    expired = False
    updated_invitation = None

    with transaction.atomic():
        locked = (
            PlatformStaffInvitation.objects.select_for_update(of=("self",))
            .select_related("invited_by")
            .get(pk=invitation.pk)
        )
        if _materialize_expired(locked):
            expired = True
        else:
            if locked.status != PlatformStaffInvitation.Status.PENDING:
                raise PlatformStaffInvitationConflict(
                    "Only pending Platform Staff invitations can be resent."
                )

            previous_state = {
                "status": locked.status,
                "send_count": locked.send_count,
            }
            raw_token = generate_invitation_token()
            now = timezone.now()
            locked.token_digest = hash_invitation_token(raw_token)
            locked.expires_at = now + INVITATION_LIFETIME
            locked.last_sent_at = now
            locked.send_count += 1
            locked.save(
                update_fields=[
                    "token_digest",
                    "expires_at",
                    "last_sent_at",
                    "send_count",
                    "updated_at",
                ]
            )
            send_platform_staff_invitation_email(locked, raw_token)
            _record_platform_event(
                invitation=locked,
                actor=actor,
                action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_RESENT,
                previous_state=previous_state,
                new_state={
                    "status": locked.status,
                    "send_count": locked.send_count,
                },
            )
            updated_invitation = locked

    if expired:
        raise PlatformStaffInvitationConflict("This invitation has expired.")
    return updated_invitation


def cancel_platform_staff_invitation(*, invitation, actor):
    _require_platform_admin(actor)
    expired = False
    updated_invitation = None

    with transaction.atomic():
        locked = PlatformStaffInvitation.objects.select_for_update(of=("self",)).get(
            pk=invitation.pk
        )
        if _materialize_expired(locked):
            expired = True
        else:
            if locked.status != PlatformStaffInvitation.Status.PENDING:
                raise PlatformStaffInvitationConflict(
                    "Only pending Platform Staff invitations can be cancelled."
                )

            previous_state = {"status": locked.status}
            locked.status = PlatformStaffInvitation.Status.CANCELLED
            locked.cancelled_by = actor
            locked.cancelled_at = timezone.now()
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
            _record_platform_event(
                invitation=locked,
                actor=actor,
                action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_CANCELLED,
                previous_state=previous_state,
                new_state={"status": locked.status},
            )
            updated_invitation = locked

    if expired:
        raise PlatformStaffInvitationConflict("This invitation has expired.")
    return updated_invitation


def get_platform_staff_invitation_by_token(raw_token):
    with transaction.atomic():
        invitation = _get_invitation_from_token(raw_token, for_update=True)
        _materialize_expired(invitation)
        return invitation


def accept_platform_staff_invitation(*, raw_token, actor):
    if not actor or not actor.is_authenticated:
        raise PlatformStaffInvitationAuthorizationError(
            "You must sign in before accepting this invitation."
        )
    if not actor.is_active:
        raise PlatformStaffInvitationAuthorizationError(
            "This TruthLens account is inactive."
        )

    expired = False
    accepted_invitation = None
    with transaction.atomic():
        invitation = _get_invitation_from_token(raw_token, for_update=True)
        now = timezone.now()
        if _materialize_expired(invitation, now=now):
            expired = True
        else:
            if invitation.status == PlatformStaffInvitation.Status.EXPIRED:
                raise PlatformStaffInvitationConflict("This invitation has expired.")
            if invitation.status == PlatformStaffInvitation.Status.ACCEPTED:
                raise PlatformStaffInvitationConflict(
                    "This invitation has already been accepted."
                )
            if invitation.status == PlatformStaffInvitation.Status.CANCELLED:
                raise PlatformStaffInvitationConflict(
                    "This invitation is no longer available."
                )
            if invitation.status != PlatformStaffInvitation.Status.PENDING:
                raise PlatformStaffInvitationConflict(
                    "This invitation cannot be accepted."
                )

            actor_email = str(actor.email or "").strip().lower()
            if not actor_email or actor_email != invitation.email:
                raise PlatformStaffInvitationAuthorizationError(
                    "This invitation was issued to a different email address."
                )

            profile, _created = UserProfile.objects.select_for_update().get_or_create(
                user=actor
            )
            if not profile.is_email_verified:
                raise PlatformStaffInvitationAuthorizationError(
                    "Verify your email address before accepting this Platform Staff invitation."
                )
            if actor.is_superuser:
                raise PlatformStaffInvitationConflict(
                    "Platform Admin accounts already have full Platform Safety access."
                )
            if profile.role in PLATFORM_SAFETY_PROFILE_ROLES:
                raise PlatformStaffInvitationConflict(
                    "This account is already a Platform Safety Moderator."
                )
            if (
                invitation.platform_role
                != PlatformStaffInvitation.PlatformRole.PLATFORM_SAFETY_MODERATOR
            ):
                raise PlatformStaffInvitationConflict(
                    "This invitation contains an unsupported Platform Staff role."
                )

            profile.role = UserProfile.Role.MOD
            profile.save(update_fields=["role"])

            invitation.status = PlatformStaffInvitation.Status.ACCEPTED
            invitation.accepted_by = actor
            invitation.accepted_at = now
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

            record_accountability_event(
                action_type=AccountabilityEvent.ActionType.PLATFORM_STAFF_INVITATION_ACCEPTED,
                resource_type=AccountabilityEvent.ResourceType.PLATFORM_STAFF_INVITATION,
                resource_id=invitation.pk,
                authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL,
                actor=actor,
                previous_state={"status": PlatformStaffInvitation.Status.PENDING},
                new_state={
                    "status": PlatformStaffInvitation.Status.ACCEPTED,
                    "platform_role": invitation.platform_role,
                },
                context={"invited_email": invitation.email},
            )
            accepted_invitation = invitation

    if expired:
        raise PlatformStaffInvitationConflict("This invitation has expired.")
    return accepted_invitation
