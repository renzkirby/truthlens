"""Offline policy checks for the opt-in universal provider hierarchy."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_pilot import (cloudflare_pilot_enabled, validate_pilot_response)
from api.services import call_llm_with_fallback
from api.verification.provider_hierarchy import (
    hierarchy_enabled, requires_strict_stage_contract,
)


class UniversalProviderHierarchyPolicyTests(SimpleTestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_hierarchy_can_be_opted_in_outside_development(self):
        with patch.dict("os.environ", {"ENABLE_UNIVERSAL_LLM_HIERARCHY": "1"}):
            self.assertTrue(hierarchy_enabled())

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_hierarchy_remains_off_without_opt_in(self):
        with patch.dict(
            "os.environ",
            {
                "ENABLE_UNIVERSAL_LLM_HIERARCHY": "",
                "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
                "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            },
        ):
            self.assertFalse(hierarchy_enabled())
            self.assertFalse(cloudflare_pilot_enabled("persisted_evidence_evaluation"))

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_mode_enables_only_validated_cloudflare_stages(self):
        with patch.dict("os.environ", {"ENABLE_UNIVERSAL_LLM_HIERARCHY": "1"}):
            for operation in (
                "persisted_evidence_evaluation",
                "evidence_assessment",
                "investigation_classification",
                "claim_equivalence",
                "fact_check_relevance",
                "claim_gate",
                "gfc_evaluation",
                "tavily_evaluation",
            ):
                with self.subTest(operation=operation):
                    self.assertTrue(cloudflare_pilot_enabled(operation))
            for operation in (
                "unsupported_operation",
                None,
            ):
                with self.subTest(operation=operation):
                    self.assertFalse(cloudflare_pilot_enabled(operation))

    def test_equivalence_contract_rejects_inconsistent_or_incomplete_json(self):
        valid = {
            "equivalent": True,
            "reasoning": "Both propositions preserve material details.",
            "material_differences": [],
        }
        self.assertTrue(validate_pilot_response(
            "claim_equivalence", json.dumps(valid), "{}",
        ))
        valid["material_differences"] = ["different date"]
        self.assertFalse(validate_pilot_response(
            "claim_equivalence", json.dumps(valid), "{}",
        ))
        valid["equivalent"] = False
        self.assertTrue(validate_pilot_response(
            "claim_equivalence", json.dumps(valid), "{}",
        ))
        valid["unexpected"] = "field"
        self.assertFalse(validate_pilot_response(
            "claim_equivalence", json.dumps(valid), "{}",
        ))

    def test_relevance_contract_rejects_ambiguous_boolean(self):
        self.assertTrue(validate_pilot_response(
            "fact_check_relevance",
            '{"is_relevant": false, "reasoning": "Different event."}', "",
        ))
        self.assertFalse(validate_pilot_response(
            "fact_check_relevance",
            '{"is_relevant": "false", "reasoning": "Different event."}', "",
        ))

    def test_new_decision_stages_use_strict_contract_when_hierarchy_enabled(self):
        for operation in ("claim_equivalence", "fact_check_relevance"):
            with self.subTest(operation=operation):
                self.assertTrue(requires_strict_stage_contract(
                    operation, pilot_active=True, hierarchy_active=True,
                ))
                self.assertTrue(requires_strict_stage_contract(
                    operation, pilot_active=False, hierarchy_active=True,
                ))

    def test_verdict_stages_require_complete_validated_json(self):
        valid = {
            "reasoning": "The evidence directly addresses the factual statement.",
            "verdict": "FAKE",
            "summary": "The statement is contradicted.",
            "confidence_score": 83,
            "score_context": "Direct evidence contradicts the claim.",
        }
        for operation in ("gfc_evaluation", "tavily_evaluation"):
            with self.subTest(operation=operation):
                self.assertTrue(validate_pilot_response(
                    operation, json.dumps(valid), "Evidence",
                ))
                invalid = {**valid, "confidence_score": "95"}
                self.assertFalse(validate_pilot_response(
                    operation, json.dumps(invalid), "Evidence",
                ))
                self.assertTrue(requires_strict_stage_contract(
                    operation, pilot_active=True, hierarchy_active=True,
                ))

    def test_claim_gate_contract_preserves_out_of_scope_and_query_structure(self):
        example = {
            "cleaned_claim": "A named official announced a new policy.",
            "search_query": "named official announcement new policy",
            "search_queries": ["named official announcement new policy"],
            "article_stance": "REPORTING",
        }
        self.assertTrue(validate_pilot_response(
            "claim_gate", json.dumps(example), "Text: ...",
        ))
        self.assertFalse(validate_pilot_response(
            "claim_gate", json.dumps({**example, "article_stance": []}), "",
        ))
        self.assertFalse(validate_pilot_response(
            "claim_gate", json.dumps({**example, "search_queries": []}), "",
        ))
        self.assertTrue(validate_pilot_response(
            "claim_gate", json.dumps({
                **example, "cleaned_claim": "OUT_OF_SCOPE",
                "search_query": "", "search_queries": [],
            }), "",
        ))
        self.assertFalse(validate_pilot_response(
            "claim_gate", json.dumps({
                **example, "cleaned_claim": "OUT_OF_SCOPE",
            }), "",
        ))

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_three_provider_fallback_order_for_all_stages(self):
        responses = {
            "persisted_evidence_evaluation": {
                "reasoning": "Evidence addresses the claim.",
                "verdict": "FACT", "summary": "Confirmed by evidence.",
                "confidence_score": 86, "score_context": "Direct support.",
            },
            "gfc_evaluation": {
                "reasoning": "Evidence addresses the claim.",
                "verdict": "FACT", "summary": "Confirmed by evidence.",
                "confidence_score": 86, "score_context": "Direct support.",
            },
            "tavily_evaluation": {
                "reasoning": "Evidence addresses the claim.",
                "verdict": "FACT", "summary": "Confirmed by evidence.",
                "confidence_score": 86, "score_context": "Direct support.",
            },
            "claim_equivalence": {
                "equivalent": False, "reasoning": "Different factual events.",
                "material_differences": ["different date"],
            },
            "fact_check_relevance": {
                "reasoning": "Different events.", "is_relevant": False,
            },
            "claim_gate": {
                "cleaned_claim": "An announcement occurred.",
                "search_query": "official announcement details",
                "search_queries": ["official announcement details"],
                "article_stance": "NEUTRAL",
            },
            "investigation_classification": {
                "decision": "ABSTAIN", "primary_subject": None, "domains": [],
            },
            "evidence_assessment": {
                "assessments": [
                    {"key": "item_0", "stance": "SUPPORTS",
                     "relevance_score": 0.9, "directness_score": 0.8},
                ],
            },
        }
        assessment_prompt = (
            'UNTRUSTED ASSESSMENT DATA:\\n'
            + json.dumps({
                "claim_text": "An announcement occurred.",
                "evidence_items": [{"key": "item_0", "evidence_content": "Public record"}],
            })
        ).replace('\\\\n', '\\n')
        with patch.dict("os.environ", {"ENABLE_UNIVERSAL_LLM_HIERARCHY": "1"}):
            for operation, expected in responses.items():
                with self.subTest(operation=operation):
                    prompt = assessment_prompt if operation == "evidence_assessment" else (
                        "The claim subject is undetermined." * 2
                        if operation == "investigation_classification" else "Input"
                    )
                    sequence = []
                    gemini = Mock()
                    def gemini_call(**kwargs):
                        sequence.append("gemini")
                        raise RuntimeError("simulated primary outage")
                    gemini.models.generate_content.side_effect = gemini_call
                    def cloudflare_call(*args, **kwargs):
                        sequence.append("cloudflare")
                        return json.dumps(expected)
                    groq = Mock()
                    def groq_call(**kwargs):
                        sequence.append("groq")
                        return SimpleNamespace(choices=[SimpleNamespace(
                            message=SimpleNamespace(content=json.dumps(expected))
                        )])
                    groq.with_options.return_value.chat.completions.create.side_effect = groq_call
                    with (
                        patch("api.services.gemini_client", gemini),
                        patch("api.services.groq_client", groq),
                        patch("api.services.call_validated_cloudflare_pilot", side_effect=cloudflare_call),
                        patch("api.services.cloudflare_assessment_bypass_reason", return_value=None),
                    ):
                        result = call_llm_with_fallback(
                            "Instructions", prompt, operation=operation,
                        )
                    self.assertEqual(json.loads(result), expected)
                    self.assertEqual(sequence, ["gemini", "cloudflare"])
                    groq.with_options.return_value.chat.completions.create.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_uses_groq_after_cloudflare_failure(self):
        payload = json.dumps({
            "reasoning": "Grounded in evidence.", "verdict": "FACT",
            "summary": "The claim is supported.", "confidence_score": 77,
            "score_context": "Direct supporting evidence.",
        })
        sequence = []
        gemini = Mock()
        gemini.models.generate_content.side_effect = RuntimeError("provider unavailable")
        cloudflare = Mock(side_effect=RuntimeError("provider unavailable"))
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=payload)
            )])
        )
        with (
            patch.dict("os.environ", {"ENABLE_UNIVERSAL_LLM_HIERARCHY": "1"}),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        ):
            result = call_llm_with_fallback(
                "Instructions", "Evidence", operation="gfc_evaluation",
            )
        self.assertEqual(result, payload)
        gemini.models.generate_content.assert_called_once()
        cloudflare.assert_called_once()
        groq.with_options.return_value.chat.completions.create.assert_called_once()
