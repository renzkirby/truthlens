import math
from numbers import Real

from django.db import transaction

from ..models import VerificationEvidence
from .evidence_assessment import EvidenceAssessment
from .evidence_dossier import ReasoningEvidenceItem


def _is_valid_score(value):
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0.0 <= value <= 1.0
    )


def _is_unavailable_assessment(assessment):
    return (
        assessment.stance == VerificationEvidence.Stance.UNKNOWN
        and assessment.relevance_score is None
        and assessment.directness_score is None
    )


def _validate_assessment(assessment):
    if not isinstance(assessment, EvidenceAssessment):
        raise ValueError("assessment must be an EvidenceAssessment.")
    if assessment.stance not in VerificationEvidence.Stance.values:
        raise ValueError("assessment stance is invalid.")
    if not _is_valid_score(assessment.relevance_score):
        raise ValueError("assessment relevance_score is invalid.")
    if not _is_valid_score(assessment.directness_score):
        raise ValueError("assessment directness_score is invalid.")


def persist_evidence_assessment(
    evidence_item: ReasoningEvidenceItem,
    assessment: EvidenceAssessment,
) -> bool:
    """Persist a valid assessment without overwriting existing assessment data."""
    if not isinstance(assessment, EvidenceAssessment):
        raise ValueError("assessment must be an EvidenceAssessment.")
    if _is_unavailable_assessment(assessment):
        return False
    _validate_assessment(assessment)

    with transaction.atomic():
        target = VerificationEvidence.objects.select_for_update().get(
            pk=evidence_item.evidence_link_id
        )
        if target.evidence_source_id != evidence_item.evidence_source_id:
            raise ValueError(
                "ReasoningEvidenceItem evidence_source_id does not match its "
                "VerificationEvidence target."
            )
        if (
            target.stance != VerificationEvidence.Stance.UNKNOWN
            or target.relevance_score is not None
            or target.directness_score is not None
        ):
            return False

        target.stance = assessment.stance
        target.relevance_score = float(assessment.relevance_score)
        target.directness_score = float(assessment.directness_score)
        target.save(
            update_fields=["stance", "relevance_score", "directness_score"]
        )

    return True
