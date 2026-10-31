import math
from collections.abc import Iterable
from numbers import Real

from ..models import VerificationEvidence
from .evidence_dossier import ReasoningEvidenceGroup


_UNVERIFIED_MAX = 49.0
_ABSOLUTE_AI_MAX = 99.0

_TOPOLOGY_CAPS = {
    0: 60.0,
    1: 90.0,
    2: 95.0,
}
_THREE_PLUS_CAP = 97.0

_USABLE_SCORE_FLOOR = 0.50
_MODERATE_CONFLICT_FLOOR = 0.60
_STRONG_CONFLICT_FLOOR = 0.80

_CONSISTENT_STANCES = {
    "FACT": frozenset({VerificationEvidence.Stance.SUPPORTS}),
    "FAKE": frozenset({VerificationEvidence.Stance.REFUTES}),
    # MISLEADING and SATIRE often require contextual or mixed evidence rather
    # than one simple supporting/refuting stance. Count any materially assessed
    # non-UNKNOWN item, but still only once per source identity.
    "MISLEADING": frozenset({
        VerificationEvidence.Stance.SUPPORTS,
        VerificationEvidence.Stance.REFUTES,
        VerificationEvidence.Stance.CONTEXT,
    }),
    "SATIRE": frozenset({
        VerificationEvidence.Stance.SUPPORTS,
        VerificationEvidence.Stance.REFUTES,
        VerificationEvidence.Stance.CONTEXT,
    }),
}
_OPPOSING_STANCES = {
    "FACT": frozenset({VerificationEvidence.Stance.REFUTES}),
    "FAKE": frozenset({VerificationEvidence.Stance.SUPPORTS}),
}


def _valid_unit_score(value):
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _item_quality(item):
    if not (
        _valid_unit_score(item.relevance_score)
        and _valid_unit_score(item.directness_score)
    ):
        return None
    return min(float(item.relevance_score), float(item.directness_score))


def _normalized_confidence(value):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("confidence_score must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
        raise ValueError("confidence_score must be between 0 and 100")
    return value


def _quality_cap(qualities):
    if not qualities:
        return 60.0
    average_quality = sum(qualities) / len(qualities)
    if average_quality < 0.60:
        return 70.0
    if average_quality < 0.75:
        return 85.0
    if average_quality < 0.90:
        return 93.0
    return 97.0


def _topology_cap(group_count):
    if group_count >= 3:
        return _THREE_PLUS_CAP
    return _TOPOLOGY_CAPS[group_count]


def _score_text(value):
    return f"{value:g}"


def _score_context(verdict, final_score, supporting_group_count, conflict_level):
    score = _score_text(final_score)
    if verdict == "UNVERIFIED":
        return (
            "Evidence remains insufficient for a decisive verdict; "
            f"final confidence is {score}%."
        )
    if conflict_level == "strong":
        return (
            "Strong conflicting assessed source identities limit automated "
            f"evidence confidence to {score}%."
        )
    if conflict_level == "moderate":
        return (
            "Conflicting assessed source identities limit automated evidence "
            f"confidence to {score}%."
        )
    if supporting_group_count == 0:
        return (
            "No usable assessed evidence supports this verdict; "
            f"final confidence is {score}%."
        )
    if supporting_group_count == 1:
        return (
            "One distinct source identity supports this verdict; "
            f"final confidence is {score}%."
        )
    if supporting_group_count == 2:
        return (
            "Two distinct source identities support this verdict; "
            f"final confidence is {score}%."
        )
    return (
        f"{supporting_group_count} distinct source identities support this verdict; "
        f"final confidence is {score}%."
    )


def calibrate_verdict_confidence(
    verdict_result: dict,
    evidence_groups: Iterable[ReasoningEvidenceGroup],
) -> dict:
    """Apply deterministic evidence-topology ceilings to an AI verdict score.

    Source identity is deliberately weaker than editorial independence. The
    function never infers ownership, syndication, authority, or credibility.
    Multiple records inside one source identity contribute at most once.
    """
    if not isinstance(verdict_result, dict):
        raise TypeError("verdict_result must be a dictionary")

    verdict = verdict_result.get("verdict")
    confidence = _normalized_confidence(
        verdict_result.get("confidence_score", 0)
    )
    result = dict(verdict_result)

    if verdict == "UNVERIFIED":
        final_score = min(confidence, _UNVERIFIED_MAX)
        result["confidence_score"] = final_score
        result["score_context"] = _score_context(
            verdict, final_score, 0, None,
        )
        return result

    consistent_stances = _CONSISTENT_STANCES.get(verdict)
    if consistent_stances is None:
        # Unknown/non-user-facing verdicts are validated elsewhere. Do not
        # silently invent confidence semantics for them.
        return result

    opposing_stances = _OPPOSING_STANCES.get(verdict, frozenset())
    supporting_qualities = []
    conflict_qualities = []

    for group in tuple(evidence_groups):
        best_support = None
        best_conflict = None
        for item in group.evidence:
            quality = _item_quality(item)
            if quality is None or quality < _USABLE_SCORE_FLOOR:
                continue
            if item.stance in consistent_stances:
                best_support = (
                    quality if best_support is None else max(best_support, quality)
                )
            if item.stance in opposing_stances:
                best_conflict = (
                    quality if best_conflict is None else max(best_conflict, quality)
                )
        if best_support is not None:
            supporting_qualities.append(best_support)
        if best_conflict is not None:
            conflict_qualities.append(best_conflict)

    supporting_group_count = len(supporting_qualities)
    ceiling = min(
        _ABSOLUTE_AI_MAX,
        _topology_cap(supporting_group_count),
        _quality_cap(supporting_qualities),
    )

    conflict_level = None
    if any(q >= _STRONG_CONFLICT_FLOOR for q in conflict_qualities):
        ceiling = min(ceiling, 75.0)
        conflict_level = "strong"
    elif any(q >= _MODERATE_CONFLICT_FLOOR for q in conflict_qualities):
        ceiling = min(ceiling, 85.0)
        conflict_level = "moderate"

    final_score = min(confidence, ceiling)
    result["confidence_score"] = final_score
    result["score_context"] = _score_context(
        verdict,
        final_score,
        supporting_group_count,
        conflict_level,
    )
    return result
