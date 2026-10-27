"""Investigation matching policy, independent of factual verdicts.

Ordinary partners are authorized by required subject domains. Verified Student
Publications use their reviewed institution-wide affiliation instead of subject
specializations, but only for claims with confirmed canonical institution
identity. Geographic information remains non-authoritative for intake.
"""
import re

from django.conf import settings
from django.core.exceptions import ValidationError

VERIFICATION_DOMAINS = (
    ("CIVICS", "Civics & Governance"),
    ("ELECTIONS", "Elections"),
    ("LAW", "Law & Justice"),
    ("HEALTH", "Health & Medicine"),
    ("SCIENCE", "Science"),
    ("TECHNOLOGY", "Technology"),
    ("EDUCATION", "Education"),
    ("ECONOMY", "Economy & Business"),
    ("ENVIRONMENT", "Environment"),
    ("DISASTERS", "Disasters & Public Safety"),
    ("SPORTS", "Sports"),
    ("CULTURE", "Culture & Entertainment"),
)
DOMAIN_CODES = frozenset(code for code, _ in VERIFICATION_DOMAINS)
JURISDICTION_RE = re.compile(r"^(?:GLOBAL|[A-Z]{2}(?:-[A-Z0-9]{1,8})?)$")


def validate_domains(value, *, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > len(DOMAIN_CODES):
        raise ValidationError("Select supported investigation specializations.")
    if any(not isinstance(item, str) or item not in DOMAIN_CODES for item in value):
        raise ValidationError("Select only supported specialization codes.")
    if len(value) != len(set(value)):
        raise ValidationError("Duplicate specializations are not allowed.")
    return sorted(value)


def validate_jurisdiction(value):
    """Compatibility validator for preserved historical classifications."""
    if not isinstance(value, str) or not JURISDICTION_RE.fullmatch(value):
        raise ValidationError("Use GLOBAL or a country/subdivision code.")
    return value


def validate_jurisdictions(value, *, allow_empty=False):
    """Compatibility validator for preserved historical scope records."""
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > 50:
        raise ValidationError("Select supported jurisdictions.")
    if len(value) != len(set(value)):
        raise ValidationError("Duplicate jurisdictions are not allowed.")
    for item in value:
        validate_jurisdiction(item)
    return sorted(value)


def jurisdiction_covers(approved, actual):
    """Legacy helper; MUST NOT gate new investigation assignments."""
    return any(
        scope == "GLOBAL" or scope == actual
        or (scope != "GLOBAL" and actual.startswith(scope + "-"))
        for scope in approved
    )


def organization_specializations(organization):
    """Single authoritative specialization set declared by the organization."""
    return sorted(set(organization.verification_specializations or []) & DOMAIN_CODES)


def effective_organization_scope(organization):
    """Compatibility projection for older read surfaces (no geographic authority)."""
    return organization_specializations(organization), []


def subject_eligibility_enforced():
    """Return whether authoritative classification may gate partner intake.

    Subject classification and Community topic projection are independent from
    this routing rollout. Routing remains backward-compatible until explicitly
    enabled even when automatic classification itself is in enforce mode.
    """
    return (
        str(getattr(settings, "INVESTIGATION_ROUTING_MODE", "off"))
        .strip()
        .lower()
        == "enforce"
    )


NEEDS_CLASSIFICATION = "NEEDS_CLASSIFICATION"
NEEDS_INSTITUTION_IDENTITY = "NEEDS_INSTITUTION_IDENTITY"
INSTITUTION_AFFILIATION_NOT_VERIFIED = "INSTITUTION_AFFILIATION_NOT_VERIFIED"
OUTSIDE_INSTITUTION_SCOPE = "OUTSIDE_INSTITUTION_SCOPE"
OUTSIDE_SPECIALIZATIONS = "OUTSIDE_SPECIALIZATIONS"


def eligibility_reason(*, classification, specializations):
    """Return the ordinary subject-specialization refusal reason, if any."""
    if classification is None or not classification.domains:
        return NEEDS_CLASSIFICATION
    if not set(classification.domains).issubset(set(specializations or [])):
        return OUTSIDE_SPECIALIZATIONS
    return None


def is_student_publication(organization):
    """Student Publication is an organization identity, not a self-declared scope."""
    return (
        getattr(organization, "organization_subtype", None)
        == "STUDENT_PUBLICATION"
    )


def student_publication_institution_eligibility_reason(
    *,
    classification,
    organization,
):
    """Authorize a Student Publication only inside its verified institution.

    Subject specializations intentionally do not expand Student Publication
    intake beyond this reviewed institutional scope.
    """
    if classification is None or not getattr(classification, "domains", None):
        return NEEDS_CLASSIFICATION

    affiliation = getattr(organization, "institution_affiliation", None)
    institution = (
        getattr(affiliation, "institution", None)
        if affiliation is not None
        else None
    )
    if (
        getattr(organization, "organization_type", None) != "NEWS"
        or affiliation is None
        or getattr(affiliation, "verification_status", None) != "VERIFIED"
        or getattr(affiliation, "coverage_scope", None) != "INSTITUTION_WIDE"
        or institution is None
        or not getattr(institution, "is_active", False)
    ):
        return INSTITUTION_AFFILIATION_NOT_VERIFIED

    campus_state = getattr(classification, "campus_context_state", None)
    if campus_state == "NOT_APPLICABLE":
        return OUTSIDE_INSTITUTION_SCOPE
    if campus_state != "CONFIRMED":
        return NEEDS_INSTITUTION_IDENTITY

    association_manager = getattr(
        classification,
        "institution_associations",
        None,
    )
    if association_manager is None:
        return NEEDS_INSTITUTION_IDENTITY

    institution_ids = {
        association.institution_id
        for association in association_manager.all()
    }
    if not institution_ids:
        return NEEDS_INSTITUTION_IDENTITY
    if affiliation.institution_id not in institution_ids:
        return OUTSIDE_INSTITUTION_SCOPE
    return None


def organization_claim_eligibility_reason(*, classification, organization):
    """Return the authoritative intake refusal reason for one organization."""
    if classification is None or not getattr(classification, "domains", None):
        return NEEDS_CLASSIFICATION

    if is_student_publication(organization):
        return student_publication_institution_eligibility_reason(
            classification=classification,
            organization=organization,
        )

    return eligibility_reason(
        classification=classification,
        specializations=organization_specializations(organization),
    )
