import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.verification import evidence_assessment
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


class VerificationAuditRemediationV1414Tests(SimpleTestCase):
    def test_claim_gate_prompts_protect_stable_factual_propositions(self):
        payload = {
            "cleaned_claim": "The agency announced the decision during the review.",
            "search_query": "agency announced decision review",
            "search_queries": ["agency announced decision review"],
            "article_stance": "NEUTRAL",
        }
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(payload),
        ) as provider:
            services.clean_ocr_text(
                "The agency announced the decision during the named 2026 review."
            )
            services.extract_search_query(
                "The agency announced the decision during the named 2026 review.",
                "https://example.com/article",
            )

        prompts = [call.args[0] for call in provider.call_args_list]
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertIn(
                "the asserted action or relationship, and the material event",
                prompt,
            )
            self.assertIn(
                "Do not demand extra background merely because more detail could "
                "make retrieval easier.",
                prompt,
            )
            self.assertIn(
                "do not require an additional date, location, source name, or "
                "quotation",
                prompt,
            )
            # Existing fail-closed protection must remain intact.
            self.assertIn(
                "proceeding would require inventing or assuming a material detail",
                prompt,
            )

    def test_evidence_assessment_preserves_modal_entailment(self):
        prompt = evidence_assessment._SYSTEM_INSTRUCTIONS
        for required in (
            "Modal or hypothetical evidence does not establish categorical actuality.",
            '"may", "might", "could"',
            "can SUPPORT a claim about possibility or candidacy",
            "does not SUPPORT a stronger categorical claim",
            "classify evidence that establishes only possibility",
        ):
            with self.subTest(required=required):
                self.assertIn(required, prompt)

    def test_persisted_evaluator_preserves_modal_entailment(self):
        system_prompt, _user_prompt = services.build_persisted_evidence_prompt(
            "Particle X makes up most dark matter.",
            "Persisted evidence.",
            "NEUTRAL",
        )
        for required in (
            "FACT also requires modal and epistemic entailment.",
            "may, might, or could be true",
            "does NOT establish a categorical submitted claim",
            "If the dossier establishes only possibility, candidacy, or theory",
            "return UNVERIFIED",
        ):
            with self.subTest(required=required):
                self.assertIn(required, system_prompt)

    def test_structured_misleading_audit_recognizes_status_reframing(self):
        signal_id = "11111111-2222-3333-4444-555555555555"
        context_id = "66666666-7777-8888-9999-aaaaaaaaaaaa"
        groups = [
            SimpleNamespace(
                evidence=(
                    SimpleNamespace(
                        evidence_link_id=signal_id,
                        title="Structured fact check",
                        content=(
                            "Claim reviewed: An agency promised a special benefit. "
                            "Rating: Misleading."
                        ),
                        stance="REFUTES",
                        relevance_score=0.98,
                        directness_score=0.95,
                    ),
                    SimpleNamespace(
                        evidence_link_id=context_id,
                        title="Official process description",
                        content=(
                            "The person was placed in mandatory administrative "
                            "custody and rehabilitation under the applicable law."
                        ),
                        stance="CONTEXT",
                        relevance_score=0.93,
                        directness_score=0.90,
                    ),
                )
            )
        ]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "MISSING_CONTEXT",
        }

        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(audited),
        ) as provider:
            result = services._audit_structured_misleading_signal(
                "The agency promised a special benefit so the person could recover.",
                "Persisted evidence.",
                {
                    "verdict": "UNVERIFIED",
                    "reasoning": "Initial evaluator abstained.",
                    "summary": "Evidence was inconclusive.",
                    "confidence_score": 0,
                    "score_context": "Insufficient.",
                    "contextual_basis_kind": "NONE",
                    "contextual_basis_evidence_ids": [],
                },
                [signal_id],
                groups,
            )

        system_prompt = " ".join(provider.call_args.args[0].split())
        self.assertIn(
            "the reviewed proposition establishes that this audit concerns the "
            "same submitted proposition",
            system_prompt,
        )
        self.assertIn(
            "required custody, rehabilitation, compliance",
            system_prompt,
        )
        self.assertIn(
            "Do not choose INSUFFICIENT_OR_CONFLICTING merely because corrective "
            "evidence",
            system_prompt,
        )
        self.assertIn(
            "rating does not decide the verdict",
            system_prompt,
        )
        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_kind"], "MISSING_CONTEXT")
        self.assertEqual(
            result["contextual_basis_evidence_ids"],
            [signal_id],
        )

    def test_final_validation_hardening_has_new_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.14")
