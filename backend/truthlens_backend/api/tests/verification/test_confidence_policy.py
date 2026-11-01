import uuid

from django.test import SimpleTestCase

from api.models import VerificationEvidence
from api.verification.confidence_policy import calibrate_verdict_confidence
from api.verification.evidence_dossier import (
    ReasoningEvidenceGroup,
    ReasoningEvidenceItem,
)


def _item(
    *,
    stance,
    relevance=0.95,
    directness=0.95,
    provider="TAVILY",
):
    return ReasoningEvidenceItem(
        evidence_link_id=uuid.uuid4(),
        evidence_source_id=uuid.uuid4(),
        provider=provider,
        url="https://example.com/article",
        canonical_url="https://example.com/article",
        title="Example",
        publisher="Example",
        source_type="NEWS",
        content="Evidence text.",
        published_at=None,
        retrieved_at=None,
        evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        stance=stance,
        relevance_score=relevance,
        directness_score=directness,
        recency_score=None,
    )


def _group(*items):
    return ReasoningEvidenceGroup(
        identity_kind="CANONICAL_SOURCE",
        identity_id=uuid.uuid4(),
        evidence=tuple(items),
    )


def _verdict(verdict="FACT", confidence=100):
    return {
        "reasoning": "Evidence-bound reasoning.",
        "verdict": verdict,
        "summary": "Summary.",
        "confidence_score": confidence,
        "score_context": "Provider supplied context.",
    }


class ConfidencePolicyTests(SimpleTestCase):
    def test_multiple_records_in_one_source_identity_count_once(self):
        group = _group(
            _item(
                stance=VerificationEvidence.Stance.SUPPORTS,
                provider="GOOGLE_FACT_CHECK",
            ),
            _item(
                stance=VerificationEvidence.Stance.SUPPORTS,
                provider="TAVILY",
            ),
            _item(stance=VerificationEvidence.Stance.SUPPORTS),
            _item(stance=VerificationEvidence.Stance.SUPPORTS),
            _item(stance=VerificationEvidence.Stance.SUPPORTS),
        )

        result = calibrate_verdict_confidence(_verdict(), [group])

        self.assertEqual(result["confidence_score"], 90)
        self.assertIn("One distinct source identity", result["score_context"])

    def test_two_strong_distinct_source_identities_allow_95_ceiling(self):
        result = calibrate_verdict_confidence(
            _verdict(),
            [
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
            ],
        )

        self.assertEqual(result["confidence_score"], 95)
        self.assertIn("Two distinct source identities", result["score_context"])

    def test_three_strong_distinct_source_identities_allow_97_ceiling(self):
        result = calibrate_verdict_confidence(
            _verdict(),
            [
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
            ],
        )

        self.assertEqual(result["confidence_score"], 97)
        self.assertIn("3 distinct source identities", result["score_context"])

    def test_weak_relevance_or_directness_lowers_ceiling(self):
        result = calibrate_verdict_confidence(
            _verdict(),
            [
                _group(_item(
                    stance=VerificationEvidence.Stance.SUPPORTS,
                    relevance=0.95,
                    directness=0.55,
                )),
            ],
        )

        self.assertEqual(result["confidence_score"], 70)

    def test_context_and_unknown_do_not_corroborate_fact(self):
        result = calibrate_verdict_confidence(
            _verdict(),
            [
                _group(_item(stance=VerificationEvidence.Stance.CONTEXT)),
                _group(_item(stance=VerificationEvidence.Stance.UNKNOWN)),
            ],
        )

        self.assertEqual(result["confidence_score"], 60)
        self.assertIn("No usable assessed evidence", result["score_context"])

    def test_strong_conflict_reduces_fact_ceiling(self):
        result = calibrate_verdict_confidence(
            _verdict(),
            [
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(
                    stance=VerificationEvidence.Stance.REFUTES,
                    relevance=0.90,
                    directness=0.85,
                )),
            ],
        )

        self.assertEqual(result["confidence_score"], 75)
        self.assertIn("Strong conflicting", result["score_context"])

    def test_strong_conflict_reduces_fake_ceiling_symmetrically(self):
        result = calibrate_verdict_confidence(
            _verdict(verdict="FAKE"),
            [
                _group(_item(stance=VerificationEvidence.Stance.REFUTES)),
                _group(_item(stance=VerificationEvidence.Stance.REFUTES)),
                _group(_item(
                    stance=VerificationEvidence.Stance.SUPPORTS,
                    relevance=0.90,
                    directness=0.85,
                )),
            ],
        )

        self.assertEqual(result["confidence_score"], 75)

    def test_unverified_high_confidence_is_capped_below_decisive_range(self):
        result = calibrate_verdict_confidence(
            _verdict(verdict="UNVERIFIED", confidence=98),
            [],
        )

        self.assertEqual(result["confidence_score"], 49)
        self.assertIn("insufficient for a decisive verdict", result["score_context"])

    def test_unverified_zero_confidence_stays_zero(self):
        result = calibrate_verdict_confidence(
            _verdict(verdict="UNVERIFIED", confidence=0),
            [],
        )

        self.assertEqual(result["confidence_score"], 0)

    def test_model_score_below_ceiling_is_not_raised(self):
        result = calibrate_verdict_confidence(
            _verdict(confidence=82),
            [_group(_item(stance=VerificationEvidence.Stance.SUPPORTS))],
        )

        self.assertEqual(result["confidence_score"], 82)

    def test_misleading_can_use_mixed_material_evidence_without_false_conflict(self):
        result = calibrate_verdict_confidence(
            _verdict(verdict="MISLEADING"),
            [
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.CONTEXT)),
            ],
        )

        self.assertEqual(result["confidence_score"], 95)

    def test_score_context_never_claims_editorial_independence(self):
        result = calibrate_verdict_confidence(
            _verdict(),
            [
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
            ],
        )

        context = result["score_context"].lower()
        self.assertNotIn("independent", context)
        self.assertNotIn("editorial", context)
