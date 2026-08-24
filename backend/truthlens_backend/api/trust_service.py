import math

from django.contrib.auth.models import User
from django.db.models import Count, Q

from .models import (
    EvidenceSubmission,
    FlagResolutionLog,
    Thread,
    Vote,
)


BASE_SCORE = 50.0

# Contribution quality
CONTRIBUTION_POINTS_CAP = 25.0
PRIOR_SUCCESS = 2.0
PRIOR_FAILURE = 2.0

# Community reception
COMMUNITY_POINTS_CAP = 15.0
COMMUNITY_SIGNAL_SCALE = 8.0

# Sustained legitimate history
HISTORY_POINTS_CAP = 5.0

# Moderation penalties
REJECTED_THREAD_PENALTY = 5.0
MODERATION_PENALTY_CAP = 30.0


RANK_REQUIREMENTS = [
    {
        "name": "New Contributor",
        "min_score": 0.0,
        "min_actions": 3,
    },
    {
        "name": "Contributor",
        "min_score": 55.0,
        "min_actions": 10,
    },
    {
        "name": "Trusted Contributor",
        "min_score": 70.0,
        "min_actions": 25,
    },
    {
        "name": "Expert Contributor",
        "min_score": 85.0,
        "min_actions": 50,
    },
]


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _get_confidence_level(resolved_actions):
    if resolved_actions < 3:
        return {
            "key": "PROVISIONAL",
            "label": "Provisional",
        }

    if resolved_actions < 10:
        return {
            "key": "LOW",
            "label": "Low",
        }

    if resolved_actions < 25:
        return {
            "key": "DEVELOPING",
            "label": "Developing",
        }

    if resolved_actions < 50:
        return {
            "key": "ESTABLISHED",
            "label": "Established",
        }

    return {
        "key": "HIGH",
        "label": "High",
    }


def calculate_trust_components(user):
    # ── 1. Resolved contribution quality ──
    #
    # Pending actions are intentionally excluded.
    # We only judge a user once moderation has resolved the action.

    resolved_evidence = EvidenceSubmission.objects.filter(
        contributor=user,
        evidence_status__in=[
            EvidenceSubmission.EvidenceStatus.VERIFIED,
            EvidenceSubmission.EvidenceStatus.REJECTED,
        ],
    )

    evidence_counts = resolved_evidence.aggregate(
        total=Count("id"),
        validated=Count(
            "id",
            filter=Q(
                evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            ),
        ),
    )

    evidence_total = evidence_counts["total"] or 0
    evidence_validated = evidence_counts["validated"] or 0

    resolved_reports = FlagResolutionLog.objects.filter(
        flagged_by=user,
    )

    report_counts = resolved_reports.aggregate(
        total=Count("id"),
        validated=Count(
            "id",
            filter=Q(is_valid_report=True),
        ),
    )

    report_total = report_counts["total"] or 0
    report_validated = report_counts["validated"] or 0

    resolved_actions = evidence_total + report_total
    validated_actions = evidence_validated + report_validated

    # Bayesian smoothing:
    # new users begin with a neutral 50% prior instead of 0% or 100%.
    smoothed_accuracy = (
        validated_actions + PRIOR_SUCCESS
    ) / (
        resolved_actions
        + PRIOR_SUCCESS
        + PRIOR_FAILURE
    )

    quality_signal = (smoothed_accuracy - 0.5) * 2

    contribution_points = _clamp(
        quality_signal * CONTRIBUTION_POINTS_CAP,
        -CONTRIBUTION_POINTS_CAP,
        CONTRIBUTION_POINTS_CAP,
    )

    # ── 2. Community reception ──
    #
    # Only votes on moderator-verified evidence are counted.
    # Users cannot improve their own score by voting on themselves.
    #
    # Voter trust is used as a bounded weight:
    # trust 0   -> 0.50
    # trust 50  -> 0.75
    # trust 100 -> 1.00
    #
    # We use the voter's stored score and do not recursively recompute it.

    votes = (
        Vote.objects.filter(
            evidence__contributor=user,
            evidence__evidence_status=(
                EvidenceSubmission.EvidenceStatus.VERIFIED
            ),
        )
        .exclude(voter=user)
        .select_related("voter__profile")
    )

    weighted_vote_signal = 0.0
    upvotes = 0
    downvotes = 0

    for vote in votes:
        voter_profile = getattr(vote.voter, "profile", None)
        voter_score = (
            voter_profile.trust_score
            if voter_profile
            else BASE_SCORE
        )

        voter_score = _clamp(
            float(voter_score),
            0.0,
            100.0,
        )

        vote_weight = 0.5 + (voter_score / 200.0)

        if vote.vote_value is True:
            weighted_vote_signal += vote_weight
            upvotes += 1
        else:
            weighted_vote_signal -= vote_weight
            downvotes += 1

    community_points = (
        math.tanh(
            weighted_vote_signal / COMMUNITY_SIGNAL_SCALE
        )
        * COMMUNITY_POINTS_CAP
    )

    # ── 3. Positive account history ──
    #
    # Passive account age does not earn trust.
    # Each distinct month containing at least one successful resolved
    # contribution can earn one point, capped at 5.

    successful_dates = []

    successful_dates.extend(
        resolved_evidence.filter(
            evidence_status=(
                EvidenceSubmission.EvidenceStatus.VERIFIED
            ),
            verified_at__isnull=False,
        ).values_list(
            "verified_at",
            flat=True,
        )
    )

    successful_dates.extend(
        resolved_reports.filter(
            is_valid_report=True,
        ).values_list(
            "resolved_at",
            flat=True,
        )
    )

    active_months = {
        (activity_date.year, activity_date.month)
        for activity_date in successful_dates
        if activity_date
    }

    history_points = min(
        HISTORY_POINTS_CAP,
        float(len(active_months)),
    )

    # ── 4. Moderation penalties ──
    #
    # Ordinary rejected evidence already lowers contribution quality.
    # We avoid penalizing it twice.
    #
    # A rejected authored thread is treated separately because it
    # represents a stronger moderation outcome.

    rejected_threads = Thread.objects.filter(
        author=user,
        status=Thread.Status.REJECTED,
    ).count()

    moderation_penalty = min(
        MODERATION_PENALTY_CAP,
        rejected_threads * REJECTED_THREAD_PENALTY,
    )

    # ── Final score ──

    raw_score = (
        BASE_SCORE
        + contribution_points
        + community_points
        + history_points
        - moderation_penalty
    )

    trust_score = _clamp(
        raw_score,
        0.0,
        100.0,
    )

    confidence = _get_confidence_level(
        resolved_actions,
    )

    return {
        "base_score": BASE_SCORE,

        "resolved_actions": resolved_actions,
        "validated_actions": validated_actions,

        "smoothed_accuracy": round(
            smoothed_accuracy,
            4,
        ),
        "contribution_points": round(
            contribution_points,
            2,
        ),

        "upvotes": upvotes,
        "downvotes": downvotes,
        "weighted_vote_signal": round(
            weighted_vote_signal,
            2,
        ),
        "community_points": round(
            community_points,
            2,
        ),

        "active_contribution_months": len(
            active_months,
        ),
        "history_points": round(
            history_points,
            2,
        ),

        "rejected_threads": rejected_threads,
        "moderation_penalty": round(
            float(moderation_penalty),
            2,
        ),

        "confidence": confidence,

        "raw_score": round(
            float(raw_score),
            2,
        ),
        "trust_score": round(
            float(trust_score),
            2,
        ),

        # Temporary compatibility aliases.
        # These prevent older frontend areas from breaking while
        # Dashboard v2 is being introduced.
        "submitted_actions": resolved_actions,
        "contribution_accuracy_rate": round(
            smoothed_accuracy,
            4,
        ),
        "net_votes": upvotes - downvotes,
        "vote_points": round(
            community_points,
            2,
        ),
        "months_active": len(active_months),
        "tenure_points": round(
            history_points,
            2,
        ),
        "removed_threads": rejected_threads,
        "penalties": round(
            float(moderation_penalty),
            2,
        ),
    }


def get_reputation_progression(components):
    score = float(
        components.get(
            "trust_score",
            BASE_SCORE,
        )
    )

    resolved_actions = int(
        components.get(
            "resolved_actions",
            0,
        )
    )

    confidence = components.get(
        "confidence",
        _get_confidence_level(resolved_actions),
    )

    if resolved_actions < 3:
        next_rank = RANK_REQUIREMENTS[0]

        progress_percent = _clamp(
            (
                resolved_actions
                / next_rank["min_actions"]
            )
            * 100,
            0.0,
            100.0,
        )

        return {
            "status": "PROVISIONAL",
            "current_rank": "Provisional",
            "next_rank": next_rank["name"],
            "score_to_next_rank": 0.0,
            "actions_to_next_rank": max(
                0,
                next_rank["min_actions"]
                - resolved_actions,
            ),
            "progress_percent": round(
                progress_percent,
                2,
            ),
            "resolved_actions": resolved_actions,
            "confidence": confidence,
        }

    current_index = 0

    for index, rank in enumerate(
        RANK_REQUIREMENTS
    ):
        if (
            score >= rank["min_score"]
            and resolved_actions
            >= rank["min_actions"]
        ):
            current_index = index

    current_rank = RANK_REQUIREMENTS[
        current_index
    ]

    if current_index == len(
        RANK_REQUIREMENTS
    ) - 1:
        return {
            "status": "ESTABLISHED",
            "current_rank": current_rank["name"],
            "next_rank": None,
            "score_to_next_rank": 0.0,
            "actions_to_next_rank": 0,
            "progress_percent": 100.0,
            "resolved_actions": resolved_actions,
            "confidence": confidence,
        }

    next_rank = RANK_REQUIREMENTS[
        current_index + 1
    ]

    score_progress = (
        1.0
        if next_rank["min_score"] <= 0
        else _clamp(
            score / next_rank["min_score"],
            0.0,
            1.0,
        )
    )

    action_progress = _clamp(
        resolved_actions
        / next_rank["min_actions"],
        0.0,
        1.0,
    )

    progress_percent = (
        min(
            score_progress,
            action_progress,
        )
        * 100
    )

    return {
        "status": "ESTABLISHED",
        "current_rank": current_rank["name"],
        "next_rank": next_rank["name"],
        "score_to_next_rank": round(
            max(
                0.0,
                next_rank["min_score"] - score,
            ),
            2,
        ),
        "actions_to_next_rank": max(
            0,
            next_rank["min_actions"]
            - resolved_actions,
        ),
        "progress_percent": round(
            progress_percent,
            2,
        ),
        "resolved_actions": resolved_actions,
        "confidence": confidence,
    }


def recompute_user_trust_score(user_id):
    user = User.objects.select_related(
        "profile",
    ).get(
        id=user_id,
    )

    components = calculate_trust_components(
        user,
    )

    user.profile.trust_score = components[
        "trust_score"
    ]

    user.profile.save(
        update_fields=["trust_score"],
    )

    return components