"""Versioned Community Guidelines registry used by Safety review and public UI."""

from copy import deepcopy

from .community_governance_contract import restriction_capabilities_payload


COMMUNITY_POLICY_TITLE = "TruthLens Community Guidelines"

_RULES_V1_0_AND_V1_1 = (
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

_RULES_V1_2 = (
    {
        **_RULES_V1_0_AND_V1_1[0],
        "examples": [
            "Repeated irrelevant promotion or disruptive repeated messages.",
            "Phishing links or offers designed to obtain money or account details.",
        ],
        "boundary": (
            "A single relevant link or good-faith promotion is not automatically spam."
        ),
    },
    {
        **_RULES_V1_0_AND_V1_1[1],
        "examples": [
            "Repeated targeted insults or intimidation.",
            "Encouraging others to repeatedly target one person.",
        ],
        "boundary": (
            "Disagreement, criticism, or challenging a claim is not automatically harassment."
        ),
    },
    {
        **_RULES_V1_0_AND_V1_1[2],
        "examples": [
            "Dehumanizing attacks aimed at people because of a protected or intrinsic characteristic.",
            "Abusive calls to exclude or mistreat people because of such a characteristic.",
        ],
        "boundary": (
            "Discussing identity, public policy, or a group's views is not automatically a violation."
        ),
    },
    {
        **_RULES_V1_0_AND_V1_1[3],
        "examples": [
            "A credible threat of serious physical harm.",
            "Encouraging people to carry out serious violence or dangerous acts.",
        ],
        "boundary": (
            "Reporting on or discussing violent events is not automatically dangerous conduct."
        ),
    },
    {
        **_RULES_V1_0_AND_V1_1[4],
        "examples": [
            "Posting a non-public home address, password, or private personal record.",
            "Sharing sensitive personal details in a way that creates a safety risk.",
        ],
    },
    {
        **_RULES_V1_0_AND_V1_1[5],
        "examples": [
            "Sharing non-consensual intimate material.",
            "Content that sexually exploits or seriously abuses another person.",
        ],
    },
    {
        **_RULES_V1_0_AND_V1_1[6],
        "examples": [
            "Pretending to be another person or organization to deceive people.",
            "Using a false identity or deceptive offer to obtain money or personal information.",
        ],
        "boundary": (
            "Clearly identified parody or commentary is not automatically impersonation."
        ),
    },
)

_BASE_REPORTING_NOTE = (
    "A report reason is an intake signal for Platform Safety. It does not "
    "itself determine whether a Community Guidelines violation occurred."
)

_BASE_VERIFICATION_BOUNDARY = (
    "Disagreement about whether a factual claim is fact, fake, misleading, "
    "satire, or unverified is not by itself a Community Safety violation. "
    "Those questions belong to TruthLens verification and professional "
    "adjudication workflows."
)

_ACCOUNT_ENFORCEMENT_V1_1 = {
    "overview": (
        "After Platform Safety confirms a Community Guidelines violation "
        "and removes the content, it may separately issue an account-level "
        "warning or restrict Community contribution access. Account action "
        "is not automatic and is decided by a qualified human reviewer."
    ),
    "actions": [
        {
            "code": "WARNING",
            "title": "Warning",
            "description": (
                "An educational account action that does not restrict "
                "Community access. A warning remains in Safety history and "
                "may be considered by a human reviewer if later violations "
                "require an account-level decision."
            ),
        },
        {
            "code": "TEMPORARY_RESTRICTION",
            "title": "Temporary Community restriction",
            "description": (
                "Temporarily prevents new or edited Community contributions. "
                "The affected user can still read Community content, report "
                "unsafe content, use TruthLens verification, review the "
                "decision, and withdraw eligible existing contributions."
            ),
        },
        {
            "code": "INDEFINITE_RESTRICTION",
            "title": "Indefinite Community restriction",
            "description": (
                "Restricts Community contribution access without an automatic "
                "end date. It does not disable the TruthLens account, "
                "verification features, reporting, or separately authorized "
                "professional Partner Workspace access."
            ),
        },
    ],
    "decision_factors": (
        "Platform Safety may consider the severity and context of the "
        "confirmed violation and relevant upheld Safety history. There is "
        "no fixed strike count or automatic escalation ladder."
    ),
    "automation_boundary": (
        "Report counts, Trust Score, Community votes, AI verdicts, and AI "
        "recommendations do not automatically issue account restrictions."
    ),
    "review_right": (
        "The affected user can request one review of an account action. "
        "The restriction remains in effect while review is pending. "
        "Warnings and expired temporary restrictions can also be reviewed "
        "to correct the historical record."
    ),
    "reporting_while_restricted": (
        "A Community restriction does not prevent the affected user from "
        "reporting unsafe Community content."
    ),
    "ban_evasion": (
        "Deliberately using another account to evade an active Community "
        "restriction is prohibited. Automated cross-account ban-evasion "
        "detection is not part of this version."
    ),
    "profile_reporting_limitation": (
        "Community Safety reporting in this version covers discussions, "
        "comments, and evidence submissions. Profile-specific reporting is "
        "not yet supported."
    ),
}

_PUBLIC_EXPLANATION_V1_2 = {
    "process_steps": [
        {
            "title": "Report",
            "description": "A Community member sends content to Platform Safety for review.",
        },
        {
            "title": "Human review",
            "description": "Platform Safety checks the content and its context.",
        },
        {
            "title": "Content decision",
            "description": "Platform Safety decides whether a Community rule was broken.",
        },
        {
            "title": "Separate account decision",
            "description": (
                "If content is removed, a human reviewer may separately decide whether "
                "a warning or Community restriction is needed."
            ),
        },
    ],
    "content_reconsideration": (
        "The content owner may request one reconsideration of an eligible content-removal decision."
    ),
    "account_action_review": (
        "The affected user may request one review of an eligible Community account action."
    ),
    "immediate_safety_note": (
        "If someone is in immediate danger, contact local emergency services or appropriate authorities. "
        "TruthLens is not an emergency service."
    ),
    "restriction_capabilities": restriction_capabilities_payload(),
}

COMMUNITY_POLICY_VERSIONS = {
    "1.0": {
        "published_on": "2026-11-14",
        "summary": "Introduced the current Community Safety rules and reporting boundary.",
        "rules": _RULES_V1_0_AND_V1_1,
        "account_enforcement": None,
        "public_explanation": None,
    },
    "1.1": {
        "published_on": "2026-11-15",
        "summary": (
            "Added transparent human-decided Community warnings, contribution "
            "restrictions, Standing, and review rights."
        ),
        "rules": _RULES_V1_0_AND_V1_1,
        "account_enforcement": _ACCOUNT_ENFORCEMENT_V1_1,
        "public_explanation": None,
    },
    "1.2": {
        "published_on": "2026-11-20",
        "summary": (
            "Clarified how reporting, human review, account actions, restrictions, "
            "and review options work, with simple examples and safety guidance."
        ),
        "rules": _RULES_V1_2,
        "account_enforcement": _ACCOUNT_ENFORCEMENT_V1_1,
        "public_explanation": _PUBLIC_EXPLANATION_V1_2,
    },
}

COMMUNITY_POLICY_VERSION = "1.2"
COMMUNITY_VIOLATIONS = COMMUNITY_POLICY_VERSIONS[COMMUNITY_POLICY_VERSION]["rules"]

COMMUNITY_VIOLATION_CHOICES = tuple(
    (item["code"], item["title"]) for item in COMMUNITY_VIOLATIONS
)
_COMMUNITY_VIOLATION_BY_CODE = {
    item["code"]: item for item in COMMUNITY_VIOLATIONS
}


def get_community_violation(code):
    return _COMMUNITY_VIOLATION_BY_CODE.get(code)


def community_policy_supports_account_enforcement(version):
    """Return whether a published Guidelines version authorizes account actions."""

    selected_version = str(version or "").strip()
    version_record = COMMUNITY_POLICY_VERSIONS.get(selected_version)
    return bool(
        version_record
        and version_record.get("account_enforcement") is not None
    )


def community_policy_payload(version=None):
    selected_version = str(version or COMMUNITY_POLICY_VERSION).strip()
    version_record = COMMUNITY_POLICY_VERSIONS.get(selected_version)
    if version_record is None:
        return None

    return {
        "title": COMMUNITY_POLICY_TITLE,
        "version": selected_version,
        "published_on": version_record["published_on"],
        "summary": version_record["summary"],
        "reporting_note": _BASE_REPORTING_NOTE,
        "verification_boundary": _BASE_VERIFICATION_BOUNDARY,
        "rules": [deepcopy(item) for item in version_record["rules"]],
        "account_enforcement": deepcopy(version_record["account_enforcement"]),
        "public_explanation": deepcopy(version_record["public_explanation"]),
        "versions": [
            {
                "version": item_version,
                "published_on": item["published_on"],
                "summary": item["summary"],
                "current": item_version == COMMUNITY_POLICY_VERSION,
            }
            for item_version, item in reversed(
                tuple(COMMUNITY_POLICY_VERSIONS.items())
            )
        ],
    }
