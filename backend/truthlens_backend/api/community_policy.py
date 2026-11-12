"""Versioned Community Guidelines registry used by Safety review and public UI."""

COMMUNITY_POLICY_VERSION = "1.0"
COMMUNITY_POLICY_TITLE = "TruthLens Community Guidelines"

COMMUNITY_VIOLATIONS = (
    {
        "code": "SPAM_DECEPTIVE_CONDUCT",
        "title": "Spam and Deceptive Conduct",
        "description": (
            "Repetitive or disruptive spam, scams, deceptive promotion, phishing, "
            "or conduct intended to manipulate participation on TruthLens."
        ),
    },
    {
        "code": "HARASSMENT_TARGETED_ABUSE",
        "title": "Harassment and Targeted Abuse",
        "description": (
            "Bullying, sustained personal attacks, targeted abuse, or coordinated "
            "harassment directed at an identifiable person or group."
        ),
    },
    {
        "code": "HATEFUL_DISCRIMINATORY_CONDUCT",
        "title": "Hateful or Discriminatory Conduct",
        "description": (
            "Dehumanizing, degrading, or abusive attacks based on protected or "
            "intrinsic characteristics."
        ),
    },
    {
        "code": "THREATS_DANGEROUS_CONDUCT",
        "title": "Threats and Dangerous Conduct",
        "description": (
            "Credible threats, incitement, or encouragement of serious physical "
            "harm or dangerous conduct."
        ),
    },
    {
        "code": "PRIVACY_PERSONAL_INFORMATION",
        "title": "Privacy and Personal Information",
        "description": (
            "Sharing non-public personal information, credentials, or other "
            "sensitive information in a way that creates a privacy or safety risk."
        ),
    },
    {
        "code": "SEXUAL_EXPLOITATIVE_CONTENT",
        "title": "Sexual or Exploitative Content",
        "description": (
            "Non-consensual intimate material, sexual exploitation, or other "
            "serious sexually abusive content."
        ),
    },
    {
        "code": "IMPERSONATION_FRAUD",
        "title": "Impersonation and Fraud",
        "description": (
            "Malicious impersonation, identity deception, scams, or fraudulent "
            "conduct intended to mislead or harm others."
        ),
    },
)

COMMUNITY_VIOLATION_CHOICES = tuple(
    (item["code"], item["title"]) for item in COMMUNITY_VIOLATIONS
)
_COMMUNITY_VIOLATION_BY_CODE = {
    item["code"]: item for item in COMMUNITY_VIOLATIONS
}


def get_community_violation(code):
    return _COMMUNITY_VIOLATION_BY_CODE.get(code)


def community_policy_payload():
    return {
        "title": COMMUNITY_POLICY_TITLE,
        "version": COMMUNITY_POLICY_VERSION,
        "reporting_note": (
            "A report reason is an intake signal for Platform Safety. It does not "
            "itself determine whether a Community Guidelines violation occurred."
        ),
        "verification_boundary": (
            "Disagreement about whether a factual claim is fact, fake, misleading, "
            "satire, or unverified is not by itself a Community Safety violation. "
            "Those questions belong to TruthLens verification and professional "
            "adjudication workflows."
        ),
        "rules": [dict(item) for item in COMMUNITY_VIOLATIONS],
    }
