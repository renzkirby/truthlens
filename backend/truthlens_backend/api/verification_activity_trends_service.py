"""Explicit UTC daily event-volume trends from trusted organization projections."""

from datetime import datetime, timedelta, timezone

from .verification_activity_metrics_service import (
    project_organization_verification_activity_events,
)
from .verification_metrics_service import project_organization_assignment_lifecycles


class VerificationActivityTrendInputError(Exception):
    pass


# Detect omitted required inputs without supplying a time-window default.
_MISSING = object()


def _utc_boundary(value, name):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise VerificationActivityTrendInputError(
            f"{name} is required and must be a timezone-aware datetime."
        )
    return value.astimezone(timezone.utc)


def _empty_counts():
    return {
        "assignment": {"claimed": 0, "released": 0, "completed": 0},
        "evidence_review": {"decisions": 0, "verified": 0, "rejected": 0},
        "adjudication": {"started": 0, "verdicts_issued": 0},
        "publication": {"initial_published": 0},
    }


def get_organization_verification_activity_trend(
    *, organization, created_after=_MISSING, created_before=_MISSING,
):
    """Bucket observed events in a required, inclusive window using UTC dates.

    The first and last dates may represent partial days. Both trusted projections
    validate complete organization history before any window filtering occurs.
    """
    created_after = _utc_boundary(created_after, "created_after")
    created_before = _utc_boundary(created_before, "created_before")
    if created_after > created_before:
        raise VerificationActivityTrendInputError(
            "created_after must not be later than created_before."
        )

    attempts = project_organization_assignment_lifecycles(organization=organization)
    activity = project_organization_verification_activity_events(organization=organization)

    first_date = created_after.date()
    buckets = {}
    for offset in range((created_before.date() - first_date).days + 1):
        date = (first_date + timedelta(days=offset)).isoformat()
        buckets[date] = {"date": date, **_empty_counts()}

    def include(timestamp, section, field):
        timestamp = timestamp.astimezone(timezone.utc)
        if created_after <= timestamp <= created_before:
            counts = buckets[timestamp.date().isoformat()][section]
            counts[field] += 1
            if section == "evidence_review":
                counts["decisions"] += 1

    for attempt in attempts:
        include(attempt["claimed_at"], "assignment", "claimed")
        if attempt["status"] == "RELEASED":
            include(attempt["terminal_at"], "assignment", "released")
        elif attempt["status"] == "COMPLETED":
            include(attempt["terminal_at"], "assignment", "completed")

    activity_fields = {
        "EVIDENCE_VERIFIED": ("evidence_review", "verified"),
        "EVIDENCE_REJECTED": ("evidence_review", "rejected"),
        "ADJUDICATION_STARTED": ("adjudication", "started"),
        "VERDICT_ISSUED": ("adjudication", "verdicts_issued"),
        "ARTICLE_PUBLISHED": ("publication", "initial_published"),
    }
    for event in activity:
        section, field = activity_fields[event["action_type"]]
        include(event["created_at"], section, field)

    daily = list(buckets.values())
    totals = _empty_counts()
    for bucket in daily:
        for section, fields in totals.items():
            for field in fields:
                fields[field] += bucket[section][field]

    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "coverage": "INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "granularity": "DAY",
            "bucket_timezone": "UTC",
            "created_after": created_after,
            "created_before": created_before,
        },
        "totals": totals,
        "daily": daily,
    }
