from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone

from .models import EvidenceSubmission, FlagResolutionLog, Thread, ThreadFlag, Vote


BASE_SCORE = 50.0
ACCURACY_MAX_POINTS = 30.0
VOTE_POINTS_CAP = 15.0
TENURE_POINTS_CAP = 5.0
TENURE_POINTS_PER_MONTH = 1.0
THREAD_REMOVAL_PENALTY = 15.0


def _months_since(start_dt, end_dt):
    years = end_dt.year - start_dt.year
    months = end_dt.month - start_dt.month
    total = years * 12 + months
    if end_dt.day < start_dt.day:
        total -= 1
    return max(0, total)


def calculate_trust_components(user):
    evidence_counts = EvidenceSubmission.objects.filter(contributor=user).aggregate(
        total=Count("id"),
        verified=Count("id", filter=Q(evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED)),
    )
    evidence_total = evidence_counts["total"] or 0
    evidence_validated = evidence_counts["verified"] or 0

    active_report_total = ThreadFlag.objects.filter(flagged_by=user).count()
    resolved_report_counts = FlagResolutionLog.objects.filter(flagged_by=user).aggregate(
        total=Count("id"),
        validated=Count("id", filter=Q(is_valid_report=True)),
    )
    resolved_report_total = resolved_report_counts["total"] or 0
    report_validated = resolved_report_counts["validated"] or 0
    report_total = active_report_total + resolved_report_total

    submitted_actions = evidence_total + report_total
    validated_actions = evidence_validated + report_validated
    contribution_accuracy_rate = (
        validated_actions / submitted_actions if submitted_actions > 0 else 0.0
    )
    contribution_points = contribution_accuracy_rate * ACCURACY_MAX_POINTS

    upvotes = Vote.objects.filter(evidence__contributor=user, vote_value=True).count()
    downvotes = Vote.objects.filter(evidence__contributor=user, vote_value=False).count()
    net_votes = upvotes - downvotes
    vote_points = max(-VOTE_POINTS_CAP, min(VOTE_POINTS_CAP, float(net_votes)))

    months_active = _months_since(user.date_joined, timezone.now())
    tenure_points = min(TENURE_POINTS_CAP, months_active * TENURE_POINTS_PER_MONTH)

    removed_threads = Thread.objects.filter(author=user, status=Thread.Status.REJECTED).count()
    penalties = removed_threads * THREAD_REMOVAL_PENALTY

    # UI composition shares: each factor's absolute influence as a percentage of total influence.
    influence_total = (
        abs(BASE_SCORE)
        + abs(contribution_points)
        + abs(vote_points)
        + abs(tenure_points)
        + abs(penalties)
    )
    if influence_total <= 0:
        influence_total = 1.0

    base_share_pct = (abs(BASE_SCORE) / influence_total) * 100
    contribution_share_pct = (abs(contribution_points) / influence_total) * 100
    vote_share_pct = (abs(vote_points) / influence_total) * 100
    tenure_share_pct = (abs(tenure_points) / influence_total) * 100
    penalties_share_pct = (abs(penalties) / influence_total) * 100

    raw_score = BASE_SCORE + contribution_points + vote_points + tenure_points - penalties
    trust_score = max(0.0, min(100.0, raw_score))

    return {
        "base_score": BASE_SCORE,
        "submitted_actions": submitted_actions,
        "validated_actions": validated_actions,
        "contribution_accuracy_rate": round(contribution_accuracy_rate, 4),
        "contribution_points": round(contribution_points, 2),
        "net_votes": net_votes,
        "vote_points": round(vote_points, 2),
        "months_active": months_active,
        "tenure_points": round(float(tenure_points), 2),
        "removed_threads": removed_threads,
        "penalties": round(float(penalties), 2),
        "base_share_pct": round(base_share_pct, 2),
        "contribution_share_pct": round(contribution_share_pct, 2),
        "vote_share_pct": round(vote_share_pct, 2),
        "tenure_share_pct": round(tenure_share_pct, 2),
        "penalties_share_pct": round(penalties_share_pct, 2),
        "raw_score": round(float(raw_score), 2),
        "trust_score": round(float(trust_score), 2),
    }


def recompute_user_trust_score(user_id):
    user = User.objects.select_related("profile").get(id=user_id)
    components = calculate_trust_components(user)
    user.profile.trust_score = components["trust_score"]
    user.profile.save(update_fields=["trust_score"])
    return components
