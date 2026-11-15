from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .accountability_service import record_accountability_event
from .models import AccountabilityEvent, Organization, PartnershipApplication


MANAGE_PARTNER_ORGANIZATION = "MANAGE_PARTNER_ORGANIZATION"
PARTNERSHIP_APPLICATION_ONBOARDING_REASON = (
    "APPROVED_PARTNERSHIP_APPLICATION_ONBOARDING_COMPLETED"
)


class PartnershipApplicationError(ValueError):
    pass


class PartnershipApplicationAuthorizationError(PartnershipApplicationError):
    pass


class PartnershipApplicationValidationError(PartnershipApplicationError):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


class PartnershipApplicationConflict(PartnershipApplicationError):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


def _require_platform_admin(actor):
    if not (
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_superuser
    ):
        raise PartnershipApplicationAuthorizationError(
            "Platform management administrator access is required."
        )


def _normalize_text(value):
    return str(value or "").strip()


def _normalize_email(value):
    return _normalize_text(value).lower()


def _organization_state(organization):
    return {
        "verification_status": organization.verification_status,
        "partner_status": organization.partner_status,
        "public_profile_enabled": organization.public_profile_enabled,
    }


def _application_state(application):
    return {
        "status": application.status,
        "reviewer_id": (
            str(application.reviewer_id) if application.reviewer_id else None
        ),
        "approved_admin_email": application.approved_admin_email,
        "onboarding_completed_at": (
            application.onboarding_completed_at.isoformat()
            if application.onboarding_completed_at
            else None
        ),
    }


def _available_slug(name):
    base = slugify(name)[:220] or "partner-organization"
    candidate = base
    suffix = 2
    while Organization.objects.filter(slug=candidate).exists():
        suffix_text = f"-{suffix}"
        candidate = f"{base[:255 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    return candidate


def _validate_public_submission(
    *,
    organization_name,
    website,
    authorized_to_represent,
    agrees_to_partner_responsibilities,
):
    if not organization_name:
        raise PartnershipApplicationValidationError(
            "Organization name is required.",
            field="organization_name",
        )

    if not website:
        raise PartnershipApplicationValidationError(
            "Official organization website is required.",
            field="website",
        )

    if Organization.objects.filter(name__iexact=organization_name).exists():
        raise PartnershipApplicationConflict(
            "An organization with this name already exists on TruthLens.",
            field="organization_name",
        )

    if Organization.objects.filter(website__iexact=website).exists():
        raise PartnershipApplicationConflict(
            "An organization with this website already exists on TruthLens.",
            field="website",
        )

    if not authorized_to_represent:
        raise PartnershipApplicationValidationError(
            "Confirm that you are authorized to represent this organization.",
            field="authorized_to_represent",
        )

    if not agrees_to_partner_responsibilities:
        raise PartnershipApplicationValidationError(
            "Agreement to TruthLens Partner responsibilities is required.",
            field="agrees_to_partner_responsibilities",
        )


@transaction.atomic
def submit_partnership_application(
    *,
    organization_name,
    organization_type,
    website,
    official_contact_email,
    applicant_full_name,
    applicant_position,
    applicant_email,
    organization_description,
    partnership_reason,
    supporting_links,
    authorized_to_represent,
    agrees_to_partner_responsibilities,
):
    organization_name = _normalize_text(organization_name)
    website = _normalize_text(website)
    official_contact_email = _normalize_email(official_contact_email)
    applicant_full_name = _normalize_text(applicant_full_name)
    applicant_position = _normalize_text(applicant_position)
    applicant_email = _normalize_email(applicant_email)
    organization_description = _normalize_text(organization_description)
    partnership_reason = _normalize_text(partnership_reason)
    supporting_links = list(supporting_links or [])

    _validate_public_submission(
        organization_name=organization_name,
        website=website,
        authorized_to_represent=authorized_to_represent,
        agrees_to_partner_responsibilities=agrees_to_partner_responsibilities,
    )

    try:
        organization = Organization.objects.create(
            name=organization_name,
            slug=_available_slug(organization_name),
            description=organization_description,
            website=website or None,
            governance_contact_email=official_contact_email,
            organization_type=organization_type,
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.NONE,
            public_profile_enabled=False,
            public_logo_enabled=False,
        )
        application = PartnershipApplication.objects.create(
            organization=organization,
            applicant_full_name=applicant_full_name,
            applicant_position=applicant_position,
            applicant_email=applicant_email,
            official_contact_email=official_contact_email,
            organization_description=organization_description,
            partnership_reason=partnership_reason,
            supporting_links=supporting_links,
            authorized_to_represent=True,
            agrees_to_partner_responsibilities=True,
        )
    except IntegrityError as error:
        raise PartnershipApplicationConflict(
            "An organization with this identity already exists on TruthLens."
        ) from error

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
        subject_organization=organization,
        reason_code="PARTNERSHIP_APPLICATION_SUBMITTED",
        new_state={
            **_organization_state(organization),
            "source": "PUBLIC_PARTNERSHIP_APPLICATION",
        },
    )
    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.PARTNERSHIP_APPLICATION_SUBMITTED,
        resource_type=AccountabilityEvent.ResourceType.PARTNERSHIP_APPLICATION,
        resource_id=application.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
        subject_organization=organization,
        new_state={
            "status": application.status,
            "organization_id": str(organization.pk),
            "applicant_email": application.applicant_email,
            "official_contact_email": application.official_contact_email,
        },
    )

    return application


@transaction.atomic
def start_partnership_application_review(*, application_id, actor):
    _require_platform_admin(actor)
    application = (
        PartnershipApplication.objects.select_for_update()
        .select_related("organization")
        .get(pk=application_id)
    )
    if application.status != PartnershipApplication.Status.SUBMITTED:
        raise PartnershipApplicationConflict(
            "Only a submitted application can enter review."
        )

    previous_state = _application_state(application)
    application.status = PartnershipApplication.Status.UNDER_REVIEW
    application.reviewer = actor
    application.review_started_at = timezone.now()
    application.save(
        update_fields=[
            "status",
            "reviewer",
            "review_started_at",
            "updated_at",
        ]
    )

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.PARTNERSHIP_APPLICATION_REVIEW_STARTED,
        resource_type=AccountabilityEvent.ResourceType.PARTNERSHIP_APPLICATION,
        resource_id=application.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=application.organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state,
        new_state=_application_state(application),
    )
    return application


@transaction.atomic
def approve_partnership_application(
    *,
    application_id,
    actor,
    approved_admin_email,
    decision_notes="",
):
    _require_platform_admin(actor)
    application = (
        PartnershipApplication.objects.select_for_update()
        .select_related("organization")
        .get(pk=application_id)
    )
    if application.status != PartnershipApplication.Status.UNDER_REVIEW:
        raise PartnershipApplicationConflict(
            "Start review before approving this application."
        )

    organization = Organization.objects.select_for_update(of=("self",)).get(
        pk=application.organization_id
    )
    if (
        organization.verification_status != Organization.VerificationStatus.PENDING
        or organization.partner_status != Organization.PartnerStatus.NONE
    ):
        raise PartnershipApplicationConflict(
            "This application's organization is no longer in the pending onboarding state."
        )

    approved_admin_email = _normalize_email(approved_admin_email)
    if not approved_admin_email:
        raise PartnershipApplicationValidationError(
            "An approved Organization Admin email is required.",
            field="approved_admin_email",
        )

    previous_state = _application_state(application)
    application.status = PartnershipApplication.Status.APPROVED
    application.approved_admin_email = approved_admin_email
    application.decision_notes = _normalize_text(decision_notes)
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.save(
        update_fields=[
            "status",
            "approved_admin_email",
            "decision_notes",
            "decided_by",
            "decided_at",
            "updated_at",
        ]
    )

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.PARTNERSHIP_APPLICATION_APPROVED,
        resource_type=AccountabilityEvent.ResourceType.PARTNERSHIP_APPLICATION,
        resource_id=application.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state,
        new_state=_application_state(application),
        notes=application.decision_notes,
    )
    return application


@transaction.atomic
def reject_partnership_application(
    *,
    application_id,
    actor,
    decision_notes,
):
    _require_platform_admin(actor)
    application = (
        PartnershipApplication.objects.select_for_update()
        .select_related("organization")
        .get(pk=application_id)
    )
    if application.status != PartnershipApplication.Status.UNDER_REVIEW:
        raise PartnershipApplicationConflict(
            "Start review before rejecting this application."
        )

    decision_notes = _normalize_text(decision_notes)
    if not decision_notes:
        raise PartnershipApplicationValidationError(
            "A rejection rationale is required.",
            field="decision_notes",
        )

    previous_state = _application_state(application)
    application.status = PartnershipApplication.Status.REJECTED
    application.decision_notes = decision_notes
    application.decided_by = actor
    application.decided_at = timezone.now()
    application.save(
        update_fields=[
            "status",
            "decision_notes",
            "decided_by",
            "decided_at",
            "updated_at",
        ]
    )

    organization = application.organization
    previous_organization_state = _organization_state(organization)
    organization.verification_status = Organization.VerificationStatus.REJECTED
    organization.save(update_fields=["verification_status", "updated_at"])

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_organization_state,
        new_state=_organization_state(organization),
        reason_code="PARTNERSHIP_APPLICATION_REJECTED",
        notes=decision_notes,
    )

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.PARTNERSHIP_APPLICATION_REJECTED,
        resource_type=AccountabilityEvent.ResourceType.PARTNERSHIP_APPLICATION,
        resource_id=application.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        actor=actor,
        subject_organization=organization,
        capability=MANAGE_PARTNER_ORGANIZATION,
        previous_state=previous_state,
        new_state=_application_state(application),
        notes=decision_notes,
    )
    return application


def approved_application_for_admin_onboarding(*, organization, email):
    try:
        application = organization.partnership_application
    except PartnershipApplication.DoesNotExist:
        return None

    if application.status != PartnershipApplication.Status.APPROVED:
        raise PartnershipApplicationConflict(
            "Approve the partnership application before provisioning an Organization Admin."
        )

    normalized_email = _normalize_email(email)
    if normalized_email != _normalize_email(application.approved_admin_email):
        raise PartnershipApplicationConflict(
            "The Organization Admin invitation must be sent to the representative email approved during application review.",
            field="email",
        )

    if application.onboarding_completed_at is not None:
        raise PartnershipApplicationConflict(
            "This partnership application has already completed onboarding."
        )

    return application


def ensure_application_managed_trust_transition_allowed(organization):
    try:
        application = organization.partnership_application
    except PartnershipApplication.DoesNotExist:
        return

    raise PartnershipApplicationConflict(
        "This organization was created from a partnership application. "
        "Use the application review and approved Admin onboarding flow instead of "
        "manual verification or activation."
    )


def finalize_approved_partnership_onboarding(*, organization, accepted_by):
    try:
        application = PartnershipApplication.objects.select_for_update().get(
            organization=organization
        )
    except PartnershipApplication.DoesNotExist:
        return None

    if application.status != PartnershipApplication.Status.APPROVED:
        raise PartnershipApplicationConflict(
            "The partnership application is not approved for onboarding."
        )
    if application.onboarding_completed_at is not None:
        raise PartnershipApplicationConflict(
            "This partnership onboarding has already been completed."
        )
    if _normalize_email(accepted_by.email) != _normalize_email(
        application.approved_admin_email
    ):
        raise PartnershipApplicationConflict(
            "This account is not the approved organization representative."
        )
    if (
        organization.verification_status != Organization.VerificationStatus.PENDING
        or organization.partner_status != Organization.PartnerStatus.NONE
    ):
        raise PartnershipApplicationConflict(
            "The organization is no longer in the pending onboarding state."
        )

    previous_organization_state = _organization_state(organization)
    previous_application_state = _application_state(application)
    now = timezone.now()

    organization.verification_status = Organization.VerificationStatus.VERIFIED
    organization.partner_status = Organization.PartnerStatus.ACTIVE
    organization.save(
        update_fields=[
            "verification_status",
            "partner_status",
            "updated_at",
        ]
    )

    application.onboarding_completed_at = now
    application.save(update_fields=["onboarding_completed_at", "updated_at"])

    completion_context = {
        "accepted_by_user_id": str(accepted_by.pk),
        "accepted_by_username": accepted_by.username,
        "approved_admin_email": application.approved_admin_email,
    }

    record_accountability_event(
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        resource_id=organization.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
        subject_organization=organization,
        previous_state=previous_organization_state,
        new_state=_organization_state(organization),
        reason_code=PARTNERSHIP_APPLICATION_ONBOARDING_REASON,
        context=completion_context,
    )
    record_accountability_event(
        action_type=(
            AccountabilityEvent.ActionType.PARTNERSHIP_APPLICATION_ONBOARDING_COMPLETED
        ),
        resource_type=AccountabilityEvent.ResourceType.PARTNERSHIP_APPLICATION,
        resource_id=application.pk,
        authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
        subject_organization=organization,
        previous_state=previous_application_state,
        new_state=_application_state(application),
        context=completion_context,
    )
    return application
