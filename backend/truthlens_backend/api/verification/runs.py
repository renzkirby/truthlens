from django.db import transaction
from django.utils import timezone

from ..models import Claim, VerificationRun
from ..notification_service import dispatch_after_commit, notify_verification_finished


CURRENT_VERIFICATION_PIPELINE_VERSION = "1.4.18"


class InvalidVerificationRunTransition(
    ValueError
):
    """Raised when a VerificationRun transition is not allowed."""


def create_verification_run(
    claim: Claim,
    *,
    triggered_by=None,
    pipeline_version: str | None = None,
) -> VerificationRun:
    """
    Create a new pending verification run.

    The run is intentionally created as PENDING so creation and
    execution remain separate lifecycle steps.
    """

    values = {
        "claim": claim,
        "triggered_by": triggered_by,
        "status": VerificationRun.Status.PENDING,
        "pipeline_version": (
            pipeline_version or CURRENT_VERIFICATION_PIPELINE_VERSION
        ),
    }

    return VerificationRun.objects.create(
        **values
    )


def has_current_completed_verification_run(claim: Claim) -> bool:
    """Return whether the latest run is a completed result from current code."""
    latest_run = claim.verification_runs.only(
        "status",
        "pipeline_version",
    ).first()
    return bool(
        latest_run is not None
        and latest_run.status == VerificationRun.Status.COMPLETED
        and latest_run.pipeline_version == CURRENT_VERIFICATION_PIPELINE_VERSION
    )


def _locked_run(
    run: VerificationRun,
) -> VerificationRun:
    return VerificationRun.objects.select_for_update().get(
        pk=run.pk
    )


def _require_status(
    run: VerificationRun,
    *allowed_statuses: str,
) -> None:
    if run.status not in allowed_statuses:
        allowed = ", ".join(
            allowed_statuses
        )

        raise InvalidVerificationRunTransition(
            f"VerificationRun {run.pk} "
            f"cannot transition from "
            f"{run.status}. "
            f"Expected status: {allowed}."
        )


@transaction.atomic
def start_verification_run(
    run: VerificationRun,
) -> VerificationRun:
    locked = _locked_run(run)

    _require_status(
        locked,
        VerificationRun.Status.PENDING,
    )

    locked.status = VerificationRun.Status.RUNNING
    locked.started_at = timezone.now()
    locked.completed_at = None
    locked.failure_stage = None
    locked.failure_code = None
    locked.failure_message = None
    locked.abstention_reason = None

    locked.save(
        update_fields=[
            "status",
            "started_at",
            "completed_at",
            "failure_stage",
            "failure_code",
            "failure_message",
            "abstention_reason",
        ]
    )

    return locked


@transaction.atomic
def complete_verification_run(
    run: VerificationRun,
) -> VerificationRun:
    locked = _locked_run(run)

    _require_status(
        locked,
        VerificationRun.Status.RUNNING,
    )

    locked.status = VerificationRun.Status.COMPLETED
    locked.completed_at = timezone.now()
    locked.failure_stage = None
    locked.failure_code = None
    locked.failure_message = None
    locked.abstention_reason = None

    locked.save(
        update_fields=[
            "status",
            "completed_at",
            "failure_stage",
            "failure_code",
            "failure_message",
            "abstention_reason",
        ]
    )

    dispatch_after_commit(notify_verification_finished, locked)
    return locked


@transaction.atomic
def abstain_verification_run(
    run: VerificationRun,
    *,
    abstention_reason: str | None = None,
) -> VerificationRun:
    locked = _locked_run(run)

    _require_status(
        locked,
        VerificationRun.Status.RUNNING,
    )

    locked.status = VerificationRun.Status.ABSTAINED
    locked.completed_at = timezone.now()
    locked.failure_stage = None
    locked.failure_code = None
    locked.failure_message = None
    locked.abstention_reason = abstention_reason

    locked.save(
        update_fields=[
            "status",
            "completed_at",
            "failure_stage",
            "failure_code",
            "failure_message",
            "abstention_reason",
        ]
    )

    dispatch_after_commit(notify_verification_finished, locked)
    return locked


@transaction.atomic
def fail_verification_run(
    run: VerificationRun,
    *,
    failure_stage: str | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> VerificationRun:
    locked = _locked_run(run)

    _require_status(
        locked,
        VerificationRun.Status.RUNNING,
    )

    locked.status = VerificationRun.Status.FAILED
    locked.completed_at = timezone.now()
    locked.failure_stage = failure_stage
    locked.failure_code = failure_code
    locked.failure_message = failure_message
    locked.abstention_reason = None

    locked.save(
        update_fields=[
            "status",
            "completed_at",
            "failure_stage",
            "failure_code",
            "failure_message",
            "abstention_reason",
        ]
    )

    dispatch_after_commit(notify_verification_finished, locked)
    return locked


@transaction.atomic
def cancel_verification_run(
    run: VerificationRun,
) -> VerificationRun:
    locked = _locked_run(run)

    _require_status(
        locked,
        VerificationRun.Status.PENDING,
        VerificationRun.Status.RUNNING,
    )

    locked.status = VerificationRun.Status.CANCELLED
    locked.completed_at = timezone.now()
    locked.failure_stage = None
    locked.failure_code = None
    locked.failure_message = None
    locked.abstention_reason = None

    locked.save(
        update_fields=[
            "status",
            "completed_at",
            "failure_stage",
            "failure_code",
            "failure_message",
            "abstention_reason",
        ]
    )

    return locked
