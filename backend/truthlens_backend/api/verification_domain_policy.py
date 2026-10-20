"""Subject-only investigation matching, independent of factual verdicts.

Geographic information may still be used in factual analysis, but is not
organization intake authorization. Legacy jurisdiction utilities are retained
for historical records; new matching only uses subject domains.
"""
import re

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


def eligibility_reason(*, classification, specializations=None, approved_domains=None,
                       approved_jurisdictions=None):
    """Classifications must be validated and entirely within declared subjects.

    Legacy call-argument names are accepted temporarily while old callers are
    migrated; geographic arguments never authorize or restrict assignment.
    """
    if classification is None or not classification.domains:
        return "NEEDS_CLASSIFICATION"
    authorized = specializations if specializations is not None else approved_domains
    if not set(classification.domains).issubset(set(authorized or [])):
        return "OUTSIDE_SPECIALIZATIONS"
    return None
