"""Shared public description of Community restriction capabilities.

Authorization still lives in the real Community endpoints. This module is only the
single public description used by Standing and the Community Guidelines.
"""


COMMUNITY_RESTRICTION_CAPABILITIES = {
    "available": (
        ("READ_COMMUNITY", "Read Community discussions"),
        ("USE_VERIFY", "Use TruthLens verification"),
        ("REPORT_SAFETY", "Report unsafe Community content"),
        ("VIEW_STANDING", "View Community Standing"),
        ("REQUEST_ELIGIBLE_REVIEW", "Request an eligible review"),
        ("DELETE_ELIGIBLE_OWN_CONTENT", "Delete eligible content you posted"),
        ("WITHDRAW_EXISTING_PARTICIPATION", "Remove an existing like or vote"),
        ("UNFOLLOW", "Unfollow users or Partners"),
    ),
    "unavailable": (
        ("CREATE_DISCUSSION", "Create a discussion"),
        ("COMMENT_REPLY", "Comment or reply"),
        ("SUBMIT_EVIDENCE", "Submit evidence"),
        ("EDIT_CONTRIBUTION", "Edit Community contributions"),
        ("ADD_OR_CHANGE_VOTE", "Add or change a vote"),
        ("LIKE", "Add a like"),
        ("FOLLOW", "Follow users or Partners"),
    ),
}


def restriction_capabilities_payload():
    return {
        group: [
            {"code": code, "label": label}
            for code, label in entries
        ]
        for group, entries in COMMUNITY_RESTRICTION_CAPABILITIES.items()
    }
