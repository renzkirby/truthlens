import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.verification import evidence_assessment
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


class VerificationAuditRemediationTests(SimpleTestCase):
    def test_claim_gate_prompt_separates_nonfactual_speech_from_ambiguity(self):
        payload = {
            "cleaned_claim": "OUT_OF_SCOPE",
            "search_query": "",
            "search_queries": [],
            "article_stance": "NEUTRAL",
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(payload),
        ) as call_llm:
            result = services.clean_ocr_text(
                "School cafeterias should offer healthier food."
            )

        self.assertEqual(result["cleaned_claim"], "OUT_OF_SCOPE")
        prompt = call_llm.call_args.args[0]
        for required in (
            "Un-attributed recommendations",
            "subjective preferences",
            "School cafeterias should offer healthier food.",
            "Chocolate ice cream tastes better than every other flavor.",
            "Do NOT use INSUFFICIENT_CONTEXT for a statement that is non-factual",
            "WHO said schools should offer healthier food.",
        ):
            with self.subTest(required=required):
                self.assertIn(required, prompt)

    def test_media_claims_open_fake_vs_misleading_relationship_audit(self):
        for claim in (
            "A July 2025 video showed flood relief.",
            "The footage showed damage from the storm.",
            "This photo was taken during the protest.",
            "The image shows the current event.",
            "An audio recording captured the statement.",
        ):
            with self.subTest(claim=claim):
                self.assertTrue(
                    services._claim_needs_fake_false_context_audit(claim)
                )

        self.assertFalse(
            services._claim_needs_fake_false_context_audit(
                "The government signed a nationwide import ban."
            )
        )

    def test_plain_video_fake_result_reaches_relationship_audit(self):
        first_result = {
            "reasoning": "Evidence contradicts the submitted claim.",
            "verdict": "FAKE",
            "summary": "The submitted claim is contradicted.",
            "confidence_score": 90,
            "score_context": "Direct refutation.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }
        audited_result = {
            **first_result,
            "verdict": "MISLEADING",
            "contextual_basis_kind": "FALSE_CONTEXT",
            "contextual_basis_evidence_ids": ["evidence-1"],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(first_result),
        ), patch(
            "api.services._audit_fake_false_context_signal",
            return_value=audited_result,
        ) as relationship_audit:
            result = services.evaluate_claim_with_persisted_evidence(
                "A video showed flooding from this month's storm.",
                "Persisted assessed evidence.",
                evidence_groups=(),
            )

        relationship_audit.assert_called_once()
        self.assertEqual(result["verdict"], "MISLEADING")

    def test_structured_misleading_compact_context_keeps_context_diversity(self):
        signal = SimpleNamespace(
            evidence_link_id="signal",
            title="Exact ClaimReview",
            content="Claim reviewed: same proposition. Rating: Misleading.",
            stance="REFUTES",
            relevance_score=1.0,
            directness_score=1.0,
        )
        refutations = [
            SimpleNamespace(
                evidence_link_id=f"refute-{index}",
                title=f"Refutation {index}",
                content="The current asserted event did not occur.",
                stance="REFUTES",
                relevance_score=1.0,
                directness_score=0.95,
            )
            for index in range(6)
        ]
        context = SimpleNamespace(
            evidence_link_id="context-1",
            title="Earlier genuine event",
            content=(
                "An earlier related ruling really occurred, but it concerned a "
                "different proceeding and materially different context."
            ),
            stance="CONTEXT",
            relevance_score=0.8,
            directness_score=0.6,
        )
        groups = [SimpleNamespace(
            evidence=tuple([signal, *refutations, context])
        )]

        rendered = json.loads(
            services._bounded_structured_misleading_context(
                ["signal"],
                groups,
                max_items=6,
            )
        )
        ids = [row["evidence_id"] for row in rendered]

        self.assertEqual(ids[0], "signal")
        self.assertIn("context-1", ids)
        self.assertLessEqual(len(rendered), 6)

    def test_material_scope_prompt_rejects_headline_only_direct_support(self):
        prompt = evidence_assessment._MATERIAL_SCOPE_INSTRUCTIONS
        for required in (
            "isolated headline",
            "related-story link",
            "archive/listing entry",
            "recommendation-card fragment",
            "must not receive",
            "decisive SUPPORTS/REFUTES",
        ):
            with self.subTest(required=required):
                self.assertIn(required, prompt)

    def test_verdict_affecting_remediation_has_new_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.11")
