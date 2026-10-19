"""Platform-governed verification domain and jurisdiction taxonomy.

These codes classify the *subject matter of claims*, not organization type
or an organization's freely editable public-profile descriptions.
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
    if not isinstance(value, list) or (
        not value and not allow_empty
    ) or len(value) > len(DOMAIN_CODES):
        raise ValidationError("Select one or more supported verification domains.")
    if any(not isinstance(item, str) or item not in DOMAIN_CODES for item in value):
        raise ValidationError("Select only supported verification domain codes.")
    if len(value) != len(set(value)):
        raise ValidationError("Duplicate verification domains are not allowed.")
    return sorted(value)


def validate_jurisdiction(value):
    if not isinstance(value, str) or not JURISDICTION_RE.fullmatch(value):
        raise ValidationError(
            "Use GLOBAL, an ISO-style country code (PH), or a country subdivision (PH-NCR)."
        )
    return value


def validate_jurisdictions(value, *, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty) or len(value) > 50:
        raise ValidationError("Select supported verification jurisdictions.")
    if len(value) != len(set(value)):
        raise ValidationError("Duplicate verification jurisdictions are not allowed.")
    for item in value:
        validate_jurisdiction(item)
    return sorted(value)


def jurisdiction_covers(approved, actual):
    """GLOBAL is an explicit worldwide authorization, never inferred."""
    return any(
        scope == "GLOBAL"
        or scope == actual
        or (scope != "GLOBAL" and actual.startswith(scope + "-"))
        for scope in approved
    )


def eligibility_reason(*, classification, approved_domains, approved_jurisdictions):
    """Return a stable reason or None when all classified topics are covered."""
    if classification is None or not classification.domains or not classification.jurisdiction:
        return "NEEDS_CLASSIFICATION"
    domains = set(classification.domains)
    if not domains.issubset(set(approved_domains)):
        return "OUTSIDE_APPROVED_DOMAINS"
    if not jurisdiction_covers(approved_jurisdictions, classification.jurisdiction):
        return "OUTSIDE_APPROVED_JURISDICTION"
    return None
