"""Offline policy checks for the opt-in universal provider hierarchy."""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_pilot import (cloudflare_pilot_enabled, validate_pilot_response)
from api.services import (
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    llm_provider_scope,
)
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.provider_hierarchy import (
    hierarchy_enabled,
    requires_strict_stage_contract,
)


class UniversalProviderHierarchyPolicyTests(SimpleTestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_hierarchy_can_be_opted_in_outside_development(self):
        with patch.dict("os.environ", {"ENABLE_UNIVERSAL_LLM_HIERARCHY": "1"}):
            self.assertTrue(hierarchy_enabled())

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_hierarchy_auto_enables_with_cloudflare_credentials(self):
        with patch.dict(
            "os.environ",
            {
                "ENABLE_UNIVERSAL_LLM_HIERARCHY": "",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                "CLOUDFLARE_API_TOKEN": "configured-token",
            },
        ):
            self.assertTrue(hierarchy_enabled())
            self.assertTrue(cloudflare_pilot_enabled(
                "persisted_evidence_evaluation",
            ))

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_explicit_zero_disables_automatic_hierarchy(self):
        with patch.dict(
            "os.environ",
            {
                "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
                "CLOUDFLARE_ACCOUNT_ID": "a" * 32,
                "CLOUDFLARE_API_TOKEN": "configured-token",
            },
        ):
            self.assertFalse(hierarchy_enabled())
            self.assertFalse(cloudflare_pilot_enabled(
                "persisted_evidence_evaluation",
            ))

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_hierarchy_remains_off_without_cloudflare_credentials(self):
        with patch.dict(
            "os.environ",
            {
                "ENABLE_UNIVERSAL_LLM_HIERARCHY": "",
                "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
                "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
                "CLOUDFLARE_ACCOUNT_ID": "",
                "CLOUDFLARE_API_TOKEN": "",
            },
        ):
            self.assertFalse(hierarchy_enabled())
            self.assertFalse(cloudflare_pilot_enabled(
                "persisted_evidence_evaluation",
            ))

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

    def test_persisted_verdict_contract_accepts_contextual_basis_without_widening_legacy_stages(self):
        contextual = {
            "reasoning": "The evidence establishes missing context.",
            "verdict": "MISLEADING",
            "summary": "The claim omits material context.",
            "confidence_score": 90,
            "score_context": "Missing context is explicit in persisted evidence.",
            "contextual_basis_kind": "MISSING_CONTEXT",
            "contextual_basis_evidence_ids": [
                "11111111-1111-1111-1111-111111111111",
            ],
        }
        self.assertTrue(validate_pilot_response(
            "persisted_evidence_evaluation",
            json.dumps(contextual),
            "Evidence",
        ))
        for operation in ("gfc_evaluation", "tavily_evaluation"):
            with self.subTest(operation=operation):
                self.assertFalse(validate_pilot_response(
                    operation,
                    json.dumps(contextual),
                    "Evidence",
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
        )
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
    def test_legacy_persisted_evidence_retries_gemini_after_groq_413(self):
        payload = json.dumps({
            "reasoning": "Grounded in the complete persisted dossier.",
            "verdict": "FACT",
            "summary": "The claim is supported.",
            "confidence_score": 84,
            "score_context": "Direct persisted evidence supports the claim.",
        })

        class ProviderError(RuntimeError):
            pass

        gemini_503 = ProviderError("service unavailable")
        gemini_503.code = 503
        groq_413 = ProviderError("request too large")
        groq_413.status_code = 413

        gemini = Mock()
        gemini.models.generate_content.side_effect = [
            gemini_503,
            SimpleNamespace(text=payload),
        ]
        groq = Mock()
        groq.chat.completions.create.side_effect = groq_413

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
                    "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
                    "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.time.sleep") as sleep,
        ):
            result = call_llm_with_fallback(
                "Instructions",
                "Complete persisted evidence dossier.",
                operation="persisted_evidence_evaluation",
            )

        self.assertEqual(result, payload)
        self.assertEqual(gemini.models.generate_content.call_count, 2)
        groq.chat.completions.create.assert_called_once()
        sleep.assert_called_once_with(1.0)

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_groq_413_does_not_retry_job_blocking_gemini_error(self):
        class ProviderError(RuntimeError):
            pass

        gemini_429 = ProviderError("quota unavailable")
        gemini_429.code = 429
        groq_413 = ProviderError("request too large")
        groq_413.status_code = 413

        gemini = Mock()
        gemini.models.generate_content.side_effect = gemini_429
        groq = Mock()
        groq.chat.completions.create.side_effect = groq_413

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
                    "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
                    "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.time.sleep") as sleep,
        ):
            with self.assertRaises(LLMProviderUnavailableError):
                call_llm_with_fallback(
                    "Instructions",
                    "Complete persisted evidence dossier.",
                    operation="persisted_evidence_evaluation",
                )

        gemini.models.generate_content.assert_called_once()
        groq.chat.completions.create.assert_called_once()
        sleep.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_uses_groq_after_cloudflare_failure(self):
        payload = json.dumps({
            "reasoning": "Grounded in evidence.", "verdict": "FACT",
            "summary": "The claim is supported.", "confidence_score": 77,
            "score_context": "Direct supporting evidence.",
        })
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

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_universal_skips_oversize_cloudflare_request_and_preserves_groq_fallback(self):
        payload = json.dumps({
            "reasoning": "Grounded in the complete evidence dossier.",
            "verdict": "FACT",
            "summary": "The claim is supported.",
            "confidence_score": 82,
            "score_context": "Direct supporting evidence.",
        })
        gemini = Mock()
        gemini.models.generate_content.side_effect = RuntimeError("provider unavailable")
        cloudflare = Mock()
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=payload)
            )])
        )
        oversized_evidence = "E" * 30000

        with (
            patch.dict("os.environ", {"ENABLE_UNIVERSAL_LLM_HIERARCHY": "1"}),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        ):
            result = call_llm_with_fallback(
                "Instructions",
                oversized_evidence,
                operation="persisted_evidence_evaluation",
            )

        self.assertEqual(result, payload)
        gemini.models.generate_content.assert_called_once()
        cloudflare.assert_not_called()
        groq.with_options.return_value.chat.completions.create.assert_called_once()
        sent_messages = (
            groq.with_options.return_value.chat.completions.create
            .call_args.kwargs["messages"]
        )
        self.assertEqual(sent_messages[1]["content"], oversized_evidence)

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_reliability_hardening_keeps_successful_gemini_path_unchanged(self):
        payload = json.dumps({
            "cleaned_claim": "An announcement occurred.",
            "search_query": "official announcement details",
            "search_queries": ["official announcement details"],
            "article_stance": "NEUTRAL",
        })
        full_prompt = "FULL ORIGINAL PROMPT"
        fallback_prompt = "BOUNDED FALLBACK PROMPT"
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(text=payload)
        cloudflare = Mock()
        groq = Mock()

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        ):
            result = call_llm_with_fallback(
                "Instructions",
                full_prompt,
                operation="claim_gate",
                fallback_user_prompt=fallback_prompt,
            )

        self.assertEqual(result, payload)
        self.assertEqual(
            gemini.models.generate_content.call_args.kwargs["contents"],
            full_prompt,
        )
        cloudflare.assert_not_called()
        groq.with_options.return_value.chat.completions.create.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_transient_gemini_503_is_suppressed_for_later_calls_in_same_scope(self):
        payload = json.dumps({
            "cleaned_claim": "An announcement occurred.",
            "search_query": "official announcement details",
            "search_queries": ["official announcement details"],
            "article_stance": "NEUTRAL",
        })

        class ProviderError(RuntimeError):
            pass

        gemini_503 = ProviderError("service unavailable")
        gemini_503.code = 503

        gemini = Mock()
        gemini.models.generate_content.side_effect = gemini_503
        cloudflare = Mock(return_value=payload)
        groq = Mock()

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        ):
            with llm_provider_scope():
                self.assertEqual(
                    call_llm_with_fallback(
                        "Instructions",
                        "Prompt one",
                        operation="claim_gate",
                    ),
                    payload,
                )
                self.assertEqual(
                    call_llm_with_fallback(
                        "Instructions",
                        "Prompt two",
                        operation="claim_gate",
                    ),
                    payload,
                )

        gemini.models.generate_content.assert_called_once()
        self.assertEqual(cloudflare.call_count, 2)
        groq.with_options.return_value.chat.completions.create.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_all_fallback_failures_get_one_forced_gemini_recovery_after_503(self):
        payload = json.dumps({
            "cleaned_claim": "An announcement occurred.",
            "search_query": "official announcement details",
            "search_queries": ["official announcement details"],
            "article_stance": "NEUTRAL",
        })

        class ProviderError(RuntimeError):
            pass

        gemini_503 = ProviderError("service unavailable")
        gemini_503.code = 503
        gemini = Mock()
        gemini.models.generate_content.side_effect = [
            gemini_503,
            SimpleNamespace(text=payload),
        ]
        cloudflare = Mock(side_effect=RuntimeError("cloudflare unavailable"))
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.side_effect = (
            RuntimeError("groq unavailable")
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
            patch("api.services.time.sleep") as sleep,
        ):
            with llm_provider_scope():
                result = call_llm_with_fallback(
                    "Instructions",
                    "FULL ORIGINAL PROMPT",
                    operation="claim_gate",
                )

        self.assertEqual(result, payload)
        self.assertEqual(gemini.models.generate_content.call_count, 2)
        self.assertEqual(
            gemini.models.generate_content.call_args_list[1].kwargs["contents"],
            "FULL ORIGINAL PROMPT",
        )
        cloudflare.assert_called_once()
        groq.with_options.return_value.chat.completions.create.assert_called_once()
        sleep.assert_called_once_with(1.0)

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_oversize_persisted_fallback_uses_bounded_prompt_for_cloudflare_and_groq(self):
        payload = json.dumps({
            "reasoning": "Grounded in the bounded persisted dossier.",
            "verdict": "FACT",
            "summary": "The claim is supported.",
            "confidence_score": 82,
            "score_context": "Direct supporting evidence.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        })

        class ProviderError(RuntimeError):
            pass

        gemini_503 = ProviderError("service unavailable")
        gemini_503.code = 503
        gemini = Mock()
        gemini.models.generate_content.side_effect = gemini_503
        cloudflare = Mock(side_effect=RuntimeError("cloudflare unavailable"))
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=payload)
            )])
        )
        full_prompt = "FULL EVIDENCE " * 5000
        bounded_prompt = "BOUNDED EVIDENCE " * 200

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        ):
            with llm_provider_scope():
                result = call_llm_with_fallback(
                    "Instructions",
                    full_prompt,
                    operation="persisted_evidence_evaluation",
                    fallback_user_prompt=bounded_prompt,
                )

        self.assertEqual(result, payload)
        self.assertEqual(
            gemini.models.generate_content.call_args.kwargs["contents"],
            full_prompt,
        )
        self.assertEqual(cloudflare.call_args.args[1], bounded_prompt)
        sent_messages = (
            groq.with_options.return_value.chat.completions.create
            .call_args.kwargs["messages"]
        )
        self.assertEqual(sent_messages[1]["content"], bounded_prompt)

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_groq_413_retries_once_with_bounded_prompt_when_preflight_used_full(self):
        payload = json.dumps({
            "reasoning": "Grounded in evidence.",
            "verdict": "FACT",
            "summary": "The claim is supported.",
            "confidence_score": 82,
            "score_context": "Direct supporting evidence.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        })

        class ProviderError(RuntimeError):
            pass

        gemini_503 = ProviderError("service unavailable")
        gemini_503.code = 503
        groq_413 = ProviderError("request too large")
        groq_413.status_code = 413

        gemini = Mock()
        gemini.models.generate_content.side_effect = gemini_503
        cloudflare = Mock(side_effect=RuntimeError("cloudflare unavailable"))
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.side_effect = [
            groq_413,
            SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=payload)
            )]),
        ]

        def estimate(_system, prompt):
            return 3000 if prompt == "FULL PROMPT" else 1000

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
            patch("api.services.estimate_prompt_tokens", side_effect=estimate),
        ):
            with llm_provider_scope():
                result = call_llm_with_fallback(
                    "Instructions",
                    "FULL PROMPT",
                    operation="persisted_evidence_evaluation",
                    fallback_user_prompt="BOUNDED PROMPT",
                )

        self.assertEqual(result, payload)
        calls = groq.with_options.return_value.chat.completions.create.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].kwargs["messages"][1]["content"], "FULL PROMPT")
        self.assertEqual(calls[1].kwargs["messages"][1]["content"], "BOUNDED PROMPT")

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_cloudflare_413_does_not_poison_later_stage_in_same_scope(self):
        payload = json.dumps({
            "cleaned_claim": "An announcement occurred.",
            "search_query": "official announcement details",
            "search_queries": ["official announcement details"],
            "article_stance": "NEUTRAL",
        })

        class ProviderError(RuntimeError):
            pass

        gemini_503 = ProviderError("service unavailable")
        gemini_503.code = 503
        gemini = Mock()
        gemini.models.generate_content.side_effect = gemini_503
        cloudflare = Mock(side_effect=[
            CloudflareEvaluationError("HTTP_413"),
            payload,
        ])
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content=payload)
            )])
        )

        with (
            patch.dict(
                "os.environ",
                {
                    "ENABLE_UNIVERSAL_LLM_HIERARCHY": "1",
                    "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
                },
            ),
            patch("api.services.gemini_client", gemini),
            patch("api.services.groq_client", groq),
            patch("api.services.call_validated_cloudflare_pilot", cloudflare),
        ):
            with llm_provider_scope():
                self.assertEqual(
                    call_llm_with_fallback(
                        "Instructions",
                        "Prompt one",
                        operation="claim_gate",
                    ),
                    payload,
                )
                self.assertEqual(
                    call_llm_with_fallback(
                        "Instructions",
                        "Prompt two",
                        operation="claim_gate",
                    ),
                    payload,
                )

        gemini.models.generate_content.assert_called_once()
        self.assertEqual(cloudflare.call_count, 2)
        groq.with_options.return_value.chat.completions.create.assert_called_once()

