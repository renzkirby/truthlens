import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


def _item(
    evidence_id,
    *,
    title="",
    content="",
    stance="CONTEXT",
    relevance=0.99,
    directness=0.99,
):
    return SimpleNamespace(
        evidence_link_id=evidence_id,
        title=title,
        content=content,
        stance=stance,
        relevance_score=relevance,
        directness_score=directness,
    )


def _group(*items):
    return SimpleNamespace(evidence=tuple(items))


class VerificationAuditRemediationV1419Tests(SimpleTestCase):
    def test_v1419_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.19")

    def test_attributed_speech_fact_rule_is_explicit_in_primary_prompt(self):
        system_prompt, _ = services.build_persisted_evidence_prompt(
            "A named official said a specific statement.",
            "Persisted evidence.",
        )

        self.assertIn("ATTRIBUTED SPEECH/ACTION ENTAILMENT", system_prompt)
        self.assertIn(
            "Evidence proving only that the underlying technology",
            system_prompt,
        )
        self.assertIn(
            "do not return FACT",
            system_prompt,
        )

    def test_attribution_correction_is_centered_in_relationship_excerpt(self):
        prefix = "Background material. " * 120
        correction = (
            "While there are no reports of Gatchalian saying the exact quote, "
            "he made several related statements about the same air-to-water project."
        )
        text = prefix + correction + (" More background." * 120)

        excerpt = services._relationship_audit_excerpt(text, max_chars=900)

        self.assertIn("no reports of Gatchalian saying the exact quote", excerpt)
        self.assertLess(len(excerpt), 1000)

    def test_structured_context_signal_can_correct_primary_fact_to_misleading(self):
        evidence_id = "91919191-9191-9191-9191-919191919191"
        groups = [_group(_item(
            evidence_id,
            content=(
                "Claim reviewed: Rex Gatchalian said air can now be turned into "
                "water to help address El Niño. Rating: Needs Context. "
                "While there are no reports of Gatchalian saying the exact quote "
                "in the circulating graphic, he made several statements about the "
                "same air-to-water project and demonstrated the generator."
            ),
            stance="CONTEXT",
        ))]
        initial_fact = {
            "reasoning": (
                "The first evaluator incorrectly treated the real technology "
                "as support for the attributed statement."
            ),
            "verdict": "FACT",
            "summary": "The underlying technology is real.",
            "confidence_score": 97,
            "score_context": "Related evidence supports the technology.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "MISSING_CONTEXT",
            "basis_evidence_ids": [evidence_id],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(initial_fact), json.dumps(audited)],
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                (
                    "Rex Gatchalian said air can now be turned into water as "
                    "a solution to Super El Niño."
                ),
                "Persisted evidence.",
                official_misleading_evidence_ids=(evidence_id,),
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_kind"], "MISSING_CONTEXT")
        self.assertEqual(
            result["contextual_basis_evidence_ids"],
            [evidence_id],
        )

    def test_context_signal_does_not_force_misleading_when_exact_claim_is_supported(self):
        evidence_id = "92929292-9292-9292-9292-929292929292"
        groups = [_group(_item(
            evidence_id,
            content=(
                "Claim reviewed: The official said the program launched on May 5. "
                "Rating: Needs Context. A transcript explicitly records the official "
                "saying the program launched on May 5."
            ),
            stance="SUPPORTS",
        ))]
        initial_fact = {
            "reasoning": "The exact attributed statement is explicitly supported.",
            "verdict": "FACT",
            "summary": "The exact attributed statement is supported.",
            "confidence_score": 95,
            "score_context": "Direct transcript support.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }
        audited = {
            "relationship": "FULLY_SUPPORTED",
            "basis_kind": "NONE",
            "basis_evidence_ids": [],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(initial_fact), json.dumps(audited)],
        ):
            result = services.evaluate_claim_with_persisted_evidence(
                "The official said the program launched on May 5.",
                "Persisted evidence.",
                official_misleading_evidence_ids=(evidence_id,),
                evidence_groups=groups,
            )

        self.assertEqual(result["verdict"], "FACT")
        self.assertEqual(result["contextual_basis_kind"], "NONE")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])
