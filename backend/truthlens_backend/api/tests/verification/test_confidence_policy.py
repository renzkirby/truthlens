import uuid

from django.test import SimpleTestCase

from api.models import VerificationEvidence
from api.verification.confidence_policy import (
    calibrate_verdict_confidence,
    enforce_noneditable_fallback_evidence_support,
    has_claim_scoped_misleading_support,
)
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
    content="Evidence text.",
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
        content=content,
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


def _verdict(
    verdict="FACT",
    confidence=100,
    *,
    contextual_basis_kind=None,
    contextual_basis_evidence_ids=None,
):
    result = {
        "reasoning": "Evidence-bound reasoning.",
        "verdict": verdict,
        "summary": "Summary.",
        "confidence_score": confidence,
        "score_context": "Provider supplied context.",
    }
    if contextual_basis_kind is not None:
        result["contextual_basis_kind"] = contextual_basis_kind
    if contextual_basis_evidence_ids is not None:
        result["contextual_basis_evidence_ids"] = contextual_basis_evidence_ids
    return result


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

    def test_misleading_uses_only_validated_contextual_basis_evidence(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind="MISSING_CONTEXT",
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 90)
        self.assertIn(
            "Validated misleading-context basis spans one distinct source identity",
            result["score_context"],
        )

    def test_misleading_without_basis_is_limited_even_with_mixed_assessed_evidence(self):
        result = calibrate_verdict_confidence(
            _verdict(verdict="MISLEADING"),
            [
                _group(_item(stance=VerificationEvidence.Stance.SUPPORTS)),
                _group(_item(stance=VerificationEvidence.Stance.REFUTES)),
                _group(_item(stance=VerificationEvidence.Stance.CONTEXT)),
            ],
        )

        self.assertEqual(result["confidence_score"], 60)
        self.assertIn(
            "Required misleading-context basis is not tied to usable persisted evidence",
            result["score_context"],
        )

    def test_two_contextual_basis_identities_allow_95_ceiling(self):
        first = _item(stance=VerificationEvidence.Stance.SUPPORTS)
        second = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind="PARTIAL_TRUTH",
                contextual_basis_evidence_ids=[
                    str(first.evidence_link_id),
                    str(second.evidence_link_id),
                ],
            ),
            [_group(first), _group(second)],
        )

        self.assertEqual(result["confidence_score"], 95)
        self.assertIn("two distinct source identities", result["score_context"])

    def test_multiple_basis_records_in_one_identity_count_once(self):
        first = _item(stance=VerificationEvidence.Stance.SUPPORTS)
        second = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind="FALSE_CONTEXT",
                contextual_basis_evidence_ids=[
                    str(first.evidence_link_id),
                    str(second.evidence_link_id),
                ],
            ),
            [_group(first, second)],
        )

        self.assertEqual(result["confidence_score"], 90)
        self.assertIn("one distinct source identity", result["score_context"])

    def test_unknown_contextual_basis_id_fails_closed_to_60(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind="MISSING_CONTEXT",
                contextual_basis_evidence_ids=[str(uuid.uuid4())],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 60)

    def test_duplicate_contextual_basis_id_fails_closed_to_60(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        evidence_id = str(item.evidence_link_id)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind="MISSING_CONTEXT",
                contextual_basis_evidence_ids=[evidence_id, evidence_id],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 60)

    def test_malformed_contextual_basis_kind_fails_closed_without_crashing(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind=[],
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["confidence_score"], 60)

    def test_contextual_basis_quality_still_limits_confidence(self):
        item = _item(
            stance=VerificationEvidence.Stance.CONTEXT,
            relevance=0.95,
            directness=0.55,
        )
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                contextual_basis_kind="MISSING_CONTEXT",
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 70)

    def test_contextual_calibration_never_raises_lower_model_score(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="MISLEADING",
                confidence=55,
                contextual_basis_kind="MISSING_CONTEXT",
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 55)

    def test_fact_and_fake_score_context_still_says_supports_verdict(self):
        fact = calibrate_verdict_confidence(
            _verdict(verdict="FACT"),
            [_group(_item(stance=VerificationEvidence.Stance.SUPPORTS))],
        )
        fake = calibrate_verdict_confidence(
            _verdict(verdict="FAKE"),
            [_group(_item(stance=VerificationEvidence.Stance.REFUTES))],
        )

        self.assertIn("supports this verdict", fact["score_context"])
        self.assertIn("supports this verdict", fake["score_context"])
        self.assertNotIn("contributes assessed evidence", fact["score_context"])
        self.assertNotIn("contributes assessed evidence", fake["score_context"])

    def test_claim_scoped_misleading_backstop_requires_support_and_refutation(self):
        support = _item(stance=VerificationEvidence.Stance.SUPPORTS)
        refute = _item(stance=VerificationEvidence.Stance.REFUTES)
        result = _verdict(
            verdict="MISLEADING",
            contextual_basis_kind="FALSE_CONTEXT",
            contextual_basis_evidence_ids=[str(refute.evidence_link_id)],
        )

        self.assertTrue(
            has_claim_scoped_misleading_support(
                result,
                [_group(support), _group(refute)],
            )
        )

    def test_claim_scoped_misleading_backstop_rejects_context_only_nuance(self):
        support = _item(stance=VerificationEvidence.Stance.SUPPORTS)
        context = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = _verdict(
            verdict="MISLEADING",
            contextual_basis_kind="MISSING_CONTEXT",
            contextual_basis_evidence_ids=[str(context.evidence_link_id)],
        )

        self.assertFalse(
            has_claim_scoped_misleading_support(
                result,
                [_group(support), _group(context)],
            )
        )

    def test_claim_scoped_misleading_backstop_requires_real_basis_evidence(self):
        support = _item(stance=VerificationEvidence.Stance.SUPPORTS)
        refute = _item(stance=VerificationEvidence.Stance.REFUTES)
        result = _verdict(
            verdict="MISLEADING",
            contextual_basis_kind="FALSE_CONTEXT",
            contextual_basis_evidence_ids=[str(uuid.uuid4())],
        )

        self.assertFalse(
            has_claim_scoped_misleading_support(
                result,
                [_group(support), _group(refute)],
            )
        )

    def test_satire_uses_only_validated_satire_provenance(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="SATIRE",
                contextual_basis_kind="SATIRE_PROVENANCE",
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 90)
        self.assertIn(
            "Validated satire provenance spans one distinct source identity",
            result["score_context"],
        )

    def test_satire_origin_of_misinformation_does_not_count_as_satire_provenance(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="SATIRE",
                contextual_basis_kind="SATIRE_ORIGIN_OF_MISINFORMATION",
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 60)
        self.assertIn(
            "Satirical provenance is not tied to usable persisted evidence",
            result["score_context"],
        )

    def test_contextual_basis_does_not_change_fact_confidence_semantics(self):
        item = _item(stance=VerificationEvidence.Stance.SUPPORTS)
        result = calibrate_verdict_confidence(
            _verdict(
                verdict="FACT",
                contextual_basis_kind="SATIRE_PROVENANCE",
                contextual_basis_evidence_ids=[str(item.evidence_link_id)],
            ),
            [_group(item)],
        )

        self.assertEqual(result["confidence_score"], 90)
        self.assertIn("supports this verdict", result["score_context"])
        self.assertNotIn("satire provenance", result["score_context"].lower())

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



class NoneditableFallbackEvidencePolicyTests(SimpleTestCase):
    def test_fact_without_usable_support_is_downgraded_to_unverified(self):
        result = enforce_noneditable_fallback_evidence_support(
            _verdict("FACT", 90),
            [_group(_item(stance=VerificationEvidence.Stance.CONTEXT))],
        )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

    def test_anchored_topic_fragment_cannot_become_fact(self):
        result = enforce_noneditable_fallback_evidence_support(
            _verdict("FACT", 93),
            [_group(_item(
                stance=VerificationEvidence.Stance.SUPPORTS,
                content="PBBM led work on the Metro Manila Subway underground project.",
            ))],
            required_anchor_tokens=["pbbm"],
            assertion_complete=False,
        )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertIn("complete factual proposition", result["summary"])
        self.assertIn("will not use that evidence to invent", result["reasoning"])

    def test_actorless_amount_match_cannot_become_fact(self):
        result = enforce_noneditable_fallback_evidence_support(
            _verdict("FACT", 90),
            [_group(_item(
                stance=VerificationEvidence.Stance.SUPPORTS,
                content="Lakambini Chiu posted P5.8 million bail.",
            ))],
            required_anchor_tokens=[],
        )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertIn(
            "abstains rather than attaching unrelated evidence",
            result["reasoning"],
        )

    def test_support_without_submitted_anchor_cannot_become_fact(self):
        result = enforce_noneditable_fallback_evidence_support(
            _verdict("FACT", 90),
            [_group(_item(
                stance=VerificationEvidence.Stance.SUPPORTS,
                content="Ferdinand Marcos Jr. led an underground railway project.",
            ))],
            required_anchor_tokens=["pbbm"],
        )

        self.assertEqual(result["verdict"], "UNVERIFIED")

    def test_fact_with_usable_support_is_preserved(self):
        verdict = _verdict("FACT", 88)
        result = enforce_noneditable_fallback_evidence_support(
            verdict,
            [_group(_item(
                stance=VerificationEvidence.Stance.SUPPORTS,
                content="PBBM led the subway excavation.",
            ))],
            required_anchor_tokens=["pbbm"],
        )

        self.assertEqual(result, verdict)

    def test_fake_with_usable_refutation_is_preserved(self):
        verdict = _verdict("FAKE", 88)
        result = enforce_noneditable_fallback_evidence_support(
            verdict,
            [_group(_item(
                stance=VerificationEvidence.Stance.REFUTES,
                content="PBBM did not make the claimed statement.",
            ))],
            required_anchor_tokens=["pbbm"],
        )

        self.assertEqual(result, verdict)

    def test_misleading_requires_evidence_tied_contextual_basis(self):
        item = _item(stance=VerificationEvidence.Stance.CONTEXT)
        verdict = _verdict(
            "MISLEADING",
            80,
            contextual_basis_kind="MISSING_CONTEXT",
            contextual_basis_evidence_ids=[],
        )

        result = enforce_noneditable_fallback_evidence_support(
            verdict,
            [_group(item)],
        )

        self.assertEqual(result["verdict"], "UNVERIFIED")

    def test_misleading_with_usable_tied_basis_is_preserved(self):
        item = _item(
            stance=VerificationEvidence.Stance.CONTEXT,
            content="PBBM context materially changes the subway claim.",
        )
        verdict = _verdict(
            "MISLEADING",
            80,
            contextual_basis_kind="MISSING_CONTEXT",
            contextual_basis_evidence_ids=[str(item.evidence_link_id)],
        )

        result = enforce_noneditable_fallback_evidence_support(
            verdict,
            [_group(item)],
            required_anchor_tokens=["pbbm"],
        )

        self.assertEqual(result, verdict)
