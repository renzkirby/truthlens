from django.db.models import (
    Exists,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
)

from .models import (
    AdjudicationDecision,
    ModerationCase,
    Thread,
)


class AdjudicationProvenance:
    """Read-time classification for the Claim verdict compatibility cache."""

    HUMAN_ADJUDICATION = "HUMAN_ADJUDICATION"
    LEGACY_HUMAN_REVIEW = "LEGACY_HUMAN_REVIEW"
    LEGACY_PROVENANCE_UNAVAILABLE = "LEGACY_PROVENANCE_UNAVAILABLE"
    PROVENANCE_UNAVAILABLE = "PROVENANCE_UNAVAILABLE"
    UNATTRIBUTED_CACHE = "UNATTRIBUTED_CACHE"
    NO_ADJUDICATION = "NO_ADJUDICATION"

    ATTRIBUTABLE_STATUSES = {
        HUMAN_ADJUDICATION,
        LEGACY_HUMAN_REVIEW,
    }


def get_current_adjudication_decision(
    claim,
    *,
    lock=False,
):
    prefetched = getattr(
        claim,
        "_current_adjudication_decisions",
        None,
    )

    if prefetched is not None and not lock:
        return prefetched[0] if prefetched else None

    queryset = AdjudicationDecision.objects.filter(
        claim=claim,
        is_current=True,
    )

    if lock:
        queryset = queryset.select_for_update()
    else:
        queryset = queryset.select_related("moderation_case")

    return queryset.first()


def prefetch_claim_adjudication_provenance(
    queryset,
    *,
    claim_path="",
    include_legacy_threads=False,
):
    """Attach the current decision needed by list serializers in one query."""

    decision_lookup = "adjudication_decisions"
    thread_lookup = "threads"

    if claim_path:
        decision_lookup = f"{claim_path}__{decision_lookup}"
        thread_lookup = f"{claim_path}__{thread_lookup}"

    prefetches = [
        Prefetch(
            decision_lookup,
            queryset=(
                AdjudicationDecision.objects.filter(is_current=True).select_related(
                    "moderation_case"
                )
            ),
            to_attr="_current_adjudication_decisions",
        ),
    ]

    if include_legacy_threads:
        prefetches.append(
            Prefetch(
                thread_lookup,
                queryset=(
                    Thread.objects.exclude(moderated_by__isnull=True)
                    .exclude(moderator_verdict__isnull=True)
                    .only(
                        "id",
                        "claim_id",
                        "moderated_by_id",
                        "moderator_verdict",
                    )
                ),
                to_attr="_adjudication_provenance_threads",
            )
        )

    return queryset.prefetch_related(*prefetches)


def annotate_claim_authoritative_verdict(
    queryset,
    *,
    claim_id_field="pk",
):
    """Annotate rows with the attributable verdict for their referenced Claim."""

    matching_legacy_thread = Thread.objects.filter(
        claim_id=OuterRef("claim_id"),
        moderated_by_id=OuterRef("decided_by_id"),
        moderator_verdict=OuterRef("verdict"),
    )

    attributable_decisions = (
        AdjudicationDecision.objects.filter(
            claim_id=OuterRef(claim_id_field),
            is_current=True,
        )
        .annotate(
            has_matching_legacy_thread=Exists(matching_legacy_thread),
        )
        .filter(
            Q(
                decision_source=(
                    AdjudicationDecision.DecisionSource.HUMAN_REVIEW
                ),
                moderation_case__case_type=(
                    ModerationCase.CaseType.ADJUDICATION
                ),
                moderation_case__claim_id=F("claim_id"),
                moderation_case__status=ModerationCase.Status.RESOLVED,
                moderation_case__resolution_code=F("verdict"),
            )
            | Q(
                decision_source=(
                    AdjudicationDecision.DecisionSource.LEGACY_MIGRATION
                ),
                decided_by__isnull=False,
                has_matching_legacy_thread=True,
            )
        )
        .order_by("-decided_at")
    )

    return queryset.annotate(
        authoritative_final_verdict=Subquery(
            attributable_decisions.values("verdict")[:1]
        )
    )


def _legacy_decision_has_historical_review(claim, decision):
    annotated_match = getattr(
        decision,
        "has_matching_legacy_thread",
        None,
    )
    if annotated_match is not None:
        return annotated_match

    provenance_threads = getattr(
        claim,
        "_adjudication_provenance_threads",
        None,
    )

    if provenance_threads is not None:
        return any(
            thread.moderated_by_id == decision.decided_by_id
            and thread.moderator_verdict == decision.verdict
            for thread in provenance_threads
        )

    prefetched_threads = getattr(claim, "_prefetched_objects_cache", {}).get(
        "threads"
    )

    if prefetched_threads is not None:
        return any(
            thread.moderated_by_id == decision.decided_by_id
            and thread.moderator_verdict == decision.verdict
            for thread in prefetched_threads
        )

    return claim.threads.filter(
        moderated_by_id=decision.decided_by_id,
        moderator_verdict=decision.verdict,
    ).exists()


def get_adjudication_decision_provenance(claim, decision):
    """Classify one stored decision from its own historical provenance."""

    if (
        decision.decision_source
        == AdjudicationDecision.DecisionSource.HUMAN_REVIEW
    ):
        case = decision.moderation_case

        if (
            case is not None
            and case.case_type == ModerationCase.CaseType.ADJUDICATION
            and case.claim_id == claim.pk
            and case.status == ModerationCase.Status.RESOLVED
            and case.resolution_code == decision.verdict
        ):
            status = AdjudicationProvenance.HUMAN_ADJUDICATION
        else:
            status = AdjudicationProvenance.PROVENANCE_UNAVAILABLE
    elif (
        decision.decision_source
        == AdjudicationDecision.DecisionSource.LEGACY_MIGRATION
        and decision.decided_by_id is not None
        and _legacy_decision_has_historical_review(claim, decision)
    ):
        status = AdjudicationProvenance.LEGACY_HUMAN_REVIEW
    elif (
        decision.decision_source
        == AdjudicationDecision.DecisionSource.LEGACY_MIGRATION
    ):
        status = AdjudicationProvenance.LEGACY_PROVENANCE_UNAVAILABLE
    else:
        status = AdjudicationProvenance.PROVENANCE_UNAVAILABLE

    return {
        "status": status,
        "decision": decision,
        "is_attributable": (
            status in AdjudicationProvenance.ATTRIBUTABLE_STATUSES
        ),
        "verdict": (
            decision.verdict
            if status in AdjudicationProvenance.ATTRIBUTABLE_STATUSES
            else None
        ),
    }


def get_claim_adjudication_provenance(claim):
    """
    Resolve whether a cached Claim verdict has attributable adjudication
    provenance without rewriting historical data.

    HUMAN_REVIEW records are attributable only when they retain the resolved
    Adjudication case created by the canonical service. A migrated legacy
    decision additionally requires an identifiable historical reviewer and a
    matching moderated Thread record. Cache values and incomplete records are
    never promoted into human adjudications.
    """

    decision = get_current_adjudication_decision(claim)

    if decision is None:
        status = (
            AdjudicationProvenance.UNATTRIBUTED_CACHE
            if claim.final_verdict
            else AdjudicationProvenance.NO_ADJUDICATION
        )
    else:
        return get_adjudication_decision_provenance(claim, decision)

    return {
        "status": status,
        "decision": decision,
        "is_attributable": (
            status in AdjudicationProvenance.ATTRIBUTABLE_STATUSES
        ),
        "verdict": (
            decision.verdict
            if decision is not None
            and status in AdjudicationProvenance.ATTRIBUTABLE_STATUSES
            else None
        ),
    }
