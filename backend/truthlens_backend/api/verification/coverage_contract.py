"""Phase 3 coverage-contract precheck. No model calls, database writes, or verdict saves.

This checks structure, citation identity and minimum eligibility requirements,
NOT the semantic truth of a model's coverage assertions. An independently
reviewed evidence-assessment boundary is required before production integration.
"""

from dataclasses import dataclass
from collections.abc import Mapping


_STATUSES = frozenset({"SUPPORTED", "CONTRADICTED", "NOT_ESTABLISHED", "CONFLICTING"})
_VERDICTS = frozenset({"FACT", "FAKE", "MISLEADING", "UNVERIFIED", "SATIRE"})
_ROOT_KEYS = frozenset({
    "assertions", "misleading_basis_evidence_ids", "satire_provenance_evidence_ids",
})
_ASSERTION_KEYS = frozenset({
    "assertion_id", "status", "support_evidence_ids", "contradict_evidence_ids",
})
_MAX_ASSERTIONS = 32
_MAX_REFERENCES = 128


@dataclass(frozen=True)
class CoverageGateResult:
    """Only a precheck outcome; accepted does not certify source semantics."""

    accepted: bool
    verdict: str
    reason_code: str


def _reject(reason_code):
    return CoverageGateResult(False, "UNVERIFIED", reason_code)


def _valid_id(value):
    return type(value) is str and 0 < len(value) <= 128 and value == value.strip()


def _id_collection(value, *, allow_empty=True, max_items=_MAX_REFERENCES):
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("Invalid identifier collection")
    if len(value) > max_items or (not allow_empty and not value):
        raise ValueError("Invalid identifier count")
    if any(not _valid_id(item) for item in value):
        raise ValueError("Invalid identifier")
    ids = set(value)
    if len(ids) != len(value):
        raise ValueError("Duplicate identifier")
    return ids


def check_verdict_coverage(
    proposed_verdict,
    coverage,
    *,
    material_assertion_ids,
    persisted_evidence_link_ids,
):
    """Check a proposed verdict against a separately assessed coverage envelope.

    A caller must provide the COMPLETE material-assertion ID set from a separate
    checked decomposition and actual persisted VerificationEvidence link IDs.
    Stance and provenance semantics are NOT established by this function.
    Invalid or inadequate inputs fail closed to UNVERIFIED, without writing data.

    Coverage shape:
      {"assertions": [{"assertion_id": str,
                       "status": "SUPPORTED|CONTRADICTED|NOT_ESTABLISHED|CONFLICTING",
                       "support_evidence_ids": [str],
                       "contradict_evidence_ids": [str]}],
       "misleading_basis_evidence_ids": [str],
       "satire_provenance_evidence_ids": [str]}
    """
    if type(proposed_verdict) is not str or proposed_verdict not in _VERDICTS:
        return _reject("INVALID_VERDICT")

    try:
        expected = _id_collection(
            material_assertion_ids, allow_empty=False, max_items=_MAX_ASSERTIONS,
        )
        known = _id_collection(persisted_evidence_link_ids)
        if not isinstance(coverage, Mapping) or set(coverage) != _ROOT_KEYS:
            raise ValueError("Invalid coverage envelope")
        rows = coverage["assertions"]
        if not isinstance(rows, (list, tuple)) or not (1 <= len(rows) <= _MAX_ASSERTIONS):
            raise ValueError("Invalid assertion rows")

        misleading_basis = _id_collection(coverage["misleading_basis_evidence_ids"])
        satire_basis = _id_collection(coverage["satire_provenance_evidence_ids"])
        if not (misleading_basis | satire_basis) <= known:
            raise ValueError("Unrecognized basis evidence")

        by_id = {}
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != _ASSERTION_KEYS:
                raise ValueError("Invalid assertion row")
            assertion_id = row["assertion_id"]
            status = row["status"]
            if not _valid_id(assertion_id) or assertion_id in by_id:
                raise ValueError("Unrecognized or duplicate assertion")
            if type(status) is not str or status not in _STATUSES:
                raise ValueError("Invalid coverage state")
            support = _id_collection(row["support_evidence_ids"])
            contradict = _id_collection(row["contradict_evidence_ids"])
            if not (support | contradict) <= known or support & contradict:
                raise ValueError("Invalid or overlapping evidence references")
            if (
                (status == "SUPPORTED" and (not support or contradict))
                or (status == "CONTRADICTED" and (not contradict or support))
                or (status == "CONFLICTING" and (not support or not contradict))
                or (status == "NOT_ESTABLISHED" and (support or contradict))
            ):
                raise ValueError("Evidence references do not match coverage state")
            by_id[assertion_id] = status

        if set(by_id) != expected:
            raise ValueError("Material assertion coverage incomplete")
    except (ValueError, TypeError):
        return _reject("INVALID_COVERAGE_CONTRACT")

    statuses = set(by_id.values())
    if proposed_verdict == "UNVERIFIED":
        return CoverageGateResult(True, "UNVERIFIED", "ABSTENTION_ALLOWED")
    if proposed_verdict == "FACT":
        if statuses != {"SUPPORTED"}:
            return _reject("FACT_REQUIRES_COMPLETE_SUPPORT")
    elif proposed_verdict == "FAKE":
        if "CONTRADICTED" not in statuses:
            return _reject("FAKE_REQUIRES_CONTRADICTION")
        if "CONFLICTING" in statuses:
            return _reject("UNRESOLVED_CONFLICT")
    elif proposed_verdict == "MISLEADING":
        # Conservative first-pass contract: a demonstrable true element,
        # demonstrable false element, and a separately cited framing basis.
        # Other legitimate misleading patterns need semantic review before
        # this gate can be integrated into live verdict decisions.
        if not ({"SUPPORTED", "CONTRADICTED"} <= statuses and misleading_basis):
            return _reject("MISLEADING_REQUIRES_MATERIAL_FALSE_CONTEXT")
        if "CONFLICTING" in statuses:
            return _reject("UNRESOLVED_CONFLICT")
    elif proposed_verdict == "SATIRE":
        if not satire_basis:
            return _reject("SATIRE_REQUIRES_PROVENANCE")

    return CoverageGateResult(True, proposed_verdict, "STRUCTURAL_PRECHECK_PASSED")
