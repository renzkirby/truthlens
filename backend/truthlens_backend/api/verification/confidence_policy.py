import math
import re
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
}
_CONTEXTUAL_VERDICTS = frozenset({"MISLEADING", "SATIRE"})
_MISLEADING_BASIS_KINDS = frozenset({
    "MISSING_CONTEXT",
    "PARTIAL_TRUTH",
    "FALSE_CONTEXT",
    "SATIRE_ORIGIN_OF_MISINFORMATION",
})
_SATIRE_BASIS_KINDS = frozenset({"SATIRE_PROVENANCE"})
_CONTEXTUAL_BASIS_STANCES = frozenset({
    VerificationEvidence.Stance.SUPPORTS,
    VerificationEvidence.Stance.REFUTES,
    VerificationEvidence.Stance.CONTEXT,
})
_CONTEXTUAL_INCOMPLETE_MAX = 60.0
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

    contextual_verdict = verdict in {"MISLEADING", "SATIRE"}
    if supporting_group_count == 0:
        if contextual_verdict:
            return (
                "No usable assessed evidence contributes to this verdict; "
                f"final confidence is {score}%."
            )
        return (
            "No usable assessed evidence supports this verdict; "
            f"final confidence is {score}%."
        )
    if supporting_group_count == 1:
        if contextual_verdict:
            return (
                "One distinct source identity contributes assessed evidence "
                f"to this verdict; final confidence is {score}%."
            )
        return (
            "One distinct source identity supports this verdict; "
            f"final confidence is {score}%."
        )
    if supporting_group_count == 2:
        if contextual_verdict:
            return (
                "Two distinct source identities contribute assessed evidence "
                f"to this verdict; final confidence is {score}%."
            )
        return (
            "Two distinct source identities support this verdict; "
            f"final confidence is {score}%."
        )
    if contextual_verdict:
        return (
            f"{supporting_group_count} distinct source identities contribute "
            f"assessed evidence to this verdict; final confidence is {score}%."
        )
    return (
        f"{supporting_group_count} distinct source identities support this verdict; "
        f"final confidence is {score}%."
    )


def _contextual_basis_score_context(
    verdict,
    final_score,
    source_identity_count,
    *,
    complete,
):
    score = _score_text(final_score)
    if not complete:
        if verdict == "MISLEADING":
            return (
                "Required misleading-context basis is not tied to usable persisted "
                f"evidence; final confidence is {score}%."
            )
        return (
            "Satirical provenance is not tied to usable persisted evidence; "
            f"final confidence is {score}%."
        )

    if verdict == "MISLEADING":
        label = "Validated misleading-context basis"
    else:
        label = "Validated satire provenance"

    if source_identity_count == 1:
        identities = "one distinct source identity"
    elif source_identity_count == 2:
        identities = "two distinct source identities"
    else:
        identities = f"{source_identity_count} distinct source identities"
    return (
        f"{label} spans {identities}; final confidence is {score}%."
    )


def _contextual_basis_qualities(verdict_result, verdict, evidence_groups):
    basis_kind = verdict_result.get("contextual_basis_kind")
    basis_ids = verdict_result.get("contextual_basis_evidence_ids")

    if (
        not isinstance(basis_ids, list)
        or not basis_ids
        or len(basis_ids) > 128
        or any(type(value) is not str or not value for value in basis_ids)
        or len(set(basis_ids)) != len(basis_ids)
    ):
        return None

    allowed_kinds = (
        _MISLEADING_BASIS_KINDS
        if verdict == "MISLEADING"
        else _SATIRE_BASIS_KINDS
    )
    if type(basis_kind) is not str or basis_kind not in allowed_kinds:
        return None

    requested_ids = set(basis_ids)
    matched_ids = set()
    basis_qualities = []

    for group in evidence_groups:
        best_quality = None
        for item in group.evidence:
            evidence_link_id = str(item.evidence_link_id)
            if evidence_link_id not in requested_ids:
                continue

            matched_ids.add(evidence_link_id)
            quality = _item_quality(item)
            if (
                quality is None
                or quality < _USABLE_SCORE_FLOOR
                or item.stance not in _CONTEXTUAL_BASIS_STANCES
            ):
                return None
            best_quality = (
                quality if best_quality is None else max(best_quality, quality)
            )

        if best_quality is not None:
            basis_qualities.append(best_quality)

    if matched_ids != requested_ids or not basis_qualities:
        return None
    return basis_qualities


def _calibrate_contextual_verdict(verdict_result, verdict, confidence, evidence_groups):
    basis_qualities = _contextual_basis_qualities(
        verdict_result,
        verdict,
        evidence_groups,
    )
    if basis_qualities is None:
        final_score = min(
            confidence,
            _ABSOLUTE_AI_MAX,
            _CONTEXTUAL_INCOMPLETE_MAX,
        )
        result = dict(verdict_result)
        result["confidence_score"] = final_score
        result["score_context"] = _contextual_basis_score_context(
            verdict,
            final_score,
            0,
            complete=False,
        )
        return result

    source_identity_count = len(basis_qualities)
    ceiling = min(
        _ABSOLUTE_AI_MAX,
        _topology_cap(source_identity_count),
        _quality_cap(basis_qualities),
    )
    final_score = min(confidence, ceiling)
    result = dict(verdict_result)
    result["confidence_score"] = final_score
    result["score_context"] = _contextual_basis_score_context(
        verdict,
        final_score,
        source_identity_count,
        complete=True,
    )
    return result


def enforce_noneditable_fallback_evidence_support(
    verdict_result: dict,
    evidence_groups: Iterable[ReasoningEvidenceGroup],
    *,
    required_anchor_tokens=(),
) -> dict:
    """Fail closed when an ambiguity fallback lacks assessed verdict evidence.

    IMAGE/URL submissions that only proceed after a strict insufficient-context
    gate are allowed broader recall, but not weaker conclusion standards. A
    decisive verdict must be tied to usable current-run assessed evidence.
    """
    if not isinstance(verdict_result, dict):
        raise TypeError("verdict_result must be a dictionary")

    result = dict(verdict_result)
    verdict = result.get("verdict")
    evidence_groups = tuple(evidence_groups)

    if verdict == "UNVERIFIED":
        return result

    anchors = {
        str(token).strip().casefold()
        for token in required_anchor_tokens
        if str(token).strip()
    }

    def evidence_has_anchor(item):
        content = getattr(item, "content", None)
        if not isinstance(content, str):
            return False
        evidence_tokens = {
            token.casefold()
            for token in re.findall(r"\b[\w'’.-]+\b", content, flags=re.UNICODE)
        }
        return bool(anchors & evidence_tokens)

    # A fallback that still has no explicit actor/entity anchor may retrieve
    # potentially useful context, but must never turn an amount/action match
    # into a factual attribution.
    supported = False
    if anchors:
        consistent_stances = _CONSISTENT_STANCES.get(verdict)
        if consistent_stances is not None:
            for group in evidence_groups:
                for item in group.evidence:
                    quality = _item_quality(item)
                    if (
                        quality is not None
                        and quality >= _USABLE_SCORE_FLOOR
                        and item.stance in consistent_stances
                        and evidence_has_anchor(item)
                    ):
                        supported = True
                        break
                if supported:
                    break
        elif verdict in _CONTEXTUAL_VERDICTS:
            basis_qualities = _contextual_basis_qualities(
                result,
                verdict,
                evidence_groups,
            )
            basis_ids = {
                str(value)
                for value in result.get("contextual_basis_evidence_ids", [])
                if value
            }
            supported = basis_qualities is not None and any(
                str(item.evidence_link_id) in basis_ids and evidence_has_anchor(item)
                for group in evidence_groups
                for item in group.evidence
            )

    if supported:
        return result

    result.update({
        "verdict": "UNVERIFIED",
        "summary": (
            "The available evidence did not directly support a decisive conclusion "
            "for the context-limited submitted claim."
        ),
        "confidence_score": 0,
        "score_context": (
            "No usable assessed evidence both supports the verdict and preserves an explicit submitted identity anchor."
        ),
        "contextual_basis_kind": "NONE",
        "contextual_basis_evidence_ids": [],
    })
    return result


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
    evidence_groups = tuple(evidence_groups)

    if verdict == "UNVERIFIED":
        final_score = min(confidence, _UNVERIFIED_MAX)
        result["confidence_score"] = final_score
        result["score_context"] = _score_context(
            verdict, final_score, 0, None,
        )
        return result

    if verdict in _CONTEXTUAL_VERDICTS:
        return _calibrate_contextual_verdict(
            result,
            verdict,
            confidence,
            evidence_groups,
        )

    consistent_stances = _CONSISTENT_STANCES.get(verdict)
    if consistent_stances is None:
        # Unknown/non-user-facing verdicts are validated elsewhere. Do not
        # silently invent confidence semantics for them.
        return result

    opposing_stances = _OPPOSING_STANCES.get(verdict, frozenset())
    supporting_qualities = []
    conflict_qualities = []

    for group in evidence_groups:
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
