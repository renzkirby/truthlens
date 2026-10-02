import math
from dataclasses import dataclass
from numbers import Real

from django.db import transaction

from ..models import VerificationEvidence
from .evidence_assessment import EvidenceAssessment
from .evidence_dossier import ReasoningEvidenceItem


@dataclass(frozen=True)
class EvidenceAssessmentPersistenceOutcome:
    persisted: bool
    error: Exception | None = None


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
    outcome = persist_evidence_assessments_batch([evidence_item], [assessment])[0]
    if outcome.error is not None:
        raise outcome.error
    return outcome.persisted


def persist_evidence_assessments_batch(
    evidence_items: list[ReasoningEvidenceItem],
    assessments: list[EvidenceAssessment],
) -> list[EvidenceAssessmentPersistenceOutcome]:
    """Persist independently valid assessments in one locked database batch."""
    evidence_items = list(evidence_items)
    assessments = list(assessments)
    outcomes = [None] * len(evidence_items)
    candidates = []

    for index, evidence_item in enumerate(evidence_items):
        try:
            assessment = assessments[index]
        except IndexError:
            outcomes[index] = EvidenceAssessmentPersistenceOutcome(
                persisted=False,
                error=ValueError("assessment is missing for evidence item."),
            )
            continue

        try:
            if not isinstance(assessment, EvidenceAssessment):
                raise ValueError("assessment must be an EvidenceAssessment.")
            if _is_unavailable_assessment(assessment):
                outcomes[index] = EvidenceAssessmentPersistenceOutcome(
                    persisted=False
                )
                continue
            _validate_assessment(assessment)
            evidence_link_id = evidence_item.evidence_link_id
            evidence_source_id = evidence_item.evidence_source_id
        except Exception as exc:
            outcomes[index] = EvidenceAssessmentPersistenceOutcome(
                persisted=False,
                error=exc,
            )
            continue

        candidates.append(
            (
                index,
                evidence_link_id,
                evidence_source_id,
                assessment,
            )
        )

    if not candidates:
        return outcomes

    with transaction.atomic():
        targets_by_id = {
            target.pk: target
            for target in VerificationEvidence.objects.select_for_update().filter(
                pk__in={candidate[1] for candidate in candidates}
            )
        }
        targets_to_update = []

        for index, evidence_link_id, evidence_source_id, assessment in candidates:
            target = targets_by_id.get(evidence_link_id)
            if target is None:
                outcomes[index] = EvidenceAssessmentPersistenceOutcome(
                    persisted=False,
                    error=VerificationEvidence.DoesNotExist(
                        "VerificationEvidence matching query does not exist."
                    ),
                )
                continue
            if target.evidence_source_id != evidence_source_id:
                outcomes[index] = EvidenceAssessmentPersistenceOutcome(
                    persisted=False,
                    error=ValueError(
                        "ReasoningEvidenceItem evidence_source_id does not match its "
                        "VerificationEvidence target."
                    ),
                )
                continue
            if (
                target.stance != VerificationEvidence.Stance.UNKNOWN
                or target.relevance_score is not None
                or target.directness_score is not None
            ):
                outcomes[index] = EvidenceAssessmentPersistenceOutcome(
                    persisted=False
                )
                continue

            target.stance = assessment.stance
            target.relevance_score = float(assessment.relevance_score)
            target.directness_score = float(assessment.directness_score)
            targets_to_update.append(target)
            outcomes[index] = EvidenceAssessmentPersistenceOutcome(persisted=True)

        VerificationEvidence.objects.bulk_update(
            targets_to_update,
            fields=["stance", "relevance_score", "directness_score"],
        )

    return outcomes
