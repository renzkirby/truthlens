"""Latest observed authoritative human resolutions from accountability history."""

from .models import AccountabilityEvent, AdjudicationDecision


class VerificationResolutionMetricsIntegrityError(Exception):
    pass


AUTHORITATIVE_VERDICTS = (
    AdjudicationDecision.Verdict.FACT,
    AdjudicationDecision.Verdict.FAKE,
    AdjudicationDecision.Verdict.MISLEADING,
    AdjudicationDecision.Verdict.SATIRE,
)


def _nonblank_identity(value):
    if not isinstance(value, str) or not value.strip():
        raise VerificationResolutionMetricsIntegrityError(
            "Selected resolution history has a missing or invalid identity."
        )
    return value


def _revision_number(value, *, minimum):
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise VerificationResolutionMetricsIntegrityError(
            "Selected resolution history has an invalid revision number."
        )
    return value


def _verdict(value):
    if not isinstance(value, str) or value not in AUTHORITATIVE_VERDICTS:
        raise VerificationResolutionMetricsIntegrityError(
            "Selected resolution history has an invalid authoritative verdict."
        )
    return value


def _validate_acyclic_successors(successors):
    checked = set()
    for decision_id in successors:
        path = set()
        while decision_id in successors and decision_id not in checked:
            if decision_id in path:
                raise VerificationResolutionMetricsIntegrityError(
                    "Selected resolution history contains a cyclic decision lineage."
                )
            path.add(decision_id)
            decision_id = successors[decision_id]
        checked.update(path)


def get_organization_verification_resolution_distribution(*, organization):
    """Validate observed issue/revision lineages and count their terminal states.

    Missing historical predecessors remain external roots, without fabricated
    issues or mutable-row recovery. Event timestamps describe observed coverage;
    decision edges, rather than event recency alone, determine effective state.
    """
    actions = AccountabilityEvent.ActionType
    events = AccountabilityEvent.objects.filter(
        subject_organization=organization,
        action_type__in=(actions.VERDICT_ISSUED, actions.VERDICT_REVISED),
    ).order_by("created_at", "id").values(
        "action_type", "resource_type", "resource_id", "context",
        "previous_state", "new_state", "created_at",
    )

    observed_states = {}
    issued_claims = set()
    successors = {}
    revision_predecessors = []
    first_observed_at = None
    last_observed_at = None
    for event in events:
        if event["resource_type"] != AccountabilityEvent.ResourceType.ADJUDICATION_DECISION:
            raise VerificationResolutionMetricsIntegrityError(
                "Selected resolution history has an incorrect resource type."
            )
        decision_id = _nonblank_identity(event["resource_id"])
        previous = event["previous_state"]
        new = event["new_state"]
        if not isinstance(previous, dict) or not isinstance(new, dict):
            raise VerificationResolutionMetricsIntegrityError(
                "Selected resolution history requires object decision states."
            )
        verdict = _verdict(new.get("verdict"))
        revision = _revision_number(new.get("revision_number"), minimum=1)

        if event["action_type"] == actions.VERDICT_ISSUED:
            context = event["context"]
            claim_id = _nonblank_identity(
                context.get("claim_id") if isinstance(context, dict) else None
            )
            previous_revision = _revision_number(previous.get("revision_number"), minimum=0)
            if (
                revision != 1
                or previous_revision != 0
                or "verdict" not in previous
                or previous["verdict"] is not None
            ):
                raise VerificationResolutionMetricsIntegrityError(
                    "Selected resolution history has an invalid initial issue state."
                )
            if claim_id in issued_claims:
                raise VerificationResolutionMetricsIntegrityError(
                    "Selected resolution history contains duplicate initial issues for a claim."
                )
            issued_claims.add(claim_id)
        else:
            # Revised events do not guarantee context claim identity.
            predecessor_id = _nonblank_identity(previous.get("decision_id"))
            successor_id = _nonblank_identity(new.get("decision_id"))
            previous_verdict = _verdict(previous.get("verdict"))
            previous_revision = _revision_number(previous.get("revision_number"), minimum=1)
            if (
                decision_id != successor_id
                or predecessor_id == successor_id
                or revision != previous_revision + 1
            ):
                raise VerificationResolutionMetricsIntegrityError(
                    "Selected resolution history has an invalid revision edge."
                )
            if predecessor_id in successors:
                raise VerificationResolutionMetricsIntegrityError(
                    "Selected resolution history contains a fork or duplicate revision edge."
                )
            successors[predecessor_id] = successor_id
            revision_predecessors.append((
                predecessor_id, (previous_verdict, previous_revision),
            ))

        # Every issue/revision introduces one observed decision, exactly once.
        # This also rejects merged lineages and an issued decision reused as a successor.
        if decision_id in observed_states:
            raise VerificationResolutionMetricsIntegrityError(
                "Selected resolution history introduces a decision identity more than once."
            )
        observed_states[decision_id] = (verdict, revision)
        created_at = event["created_at"]
        first_observed_at = (
            min(first_observed_at, created_at)
            if first_observed_at is not None else created_at
        )
        last_observed_at = (
            max(last_observed_at, created_at)
            if last_observed_at is not None else created_at
        )

    _validate_acyclic_successors(successors)
    # Resolve against the complete selected history, including predecessor events
    # encountered later in deterministic timestamp order. No chronology is inferred.
    for predecessor_id, previous_state in revision_predecessors:
        if predecessor_id in observed_states and observed_states[predecessor_id] != previous_state:
            raise VerificationResolutionMetricsIntegrityError(
                "Selected resolution history contradicts an observed predecessor state."
            )

    by_verdict = dict.fromkeys(AUTHORITATIVE_VERDICTS, 0)
    for decision_id, (verdict, _revision) in observed_states.items():
        if decision_id not in successors:
            by_verdict[verdict] += 1

    return {
        "organization_id": str(organization.pk),
        "measurement_basis": {
            "source": "ACCOUNTABILITY_EVENT",
            "coverage": "OBSERVED_AUTHORITATIVE_RESOLUTION_EVENTS_ONLY",
            "historical_backfill": False,
            "first_observed_resolution_at": first_observed_at,
            "last_observed_resolution_at": last_observed_at,
        },
        "latest_observed_resolutions": {
            "count": sum(by_verdict.values()),
            "by_verdict": by_verdict,
        },
    }
