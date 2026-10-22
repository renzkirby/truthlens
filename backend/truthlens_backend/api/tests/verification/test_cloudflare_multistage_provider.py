"""Offline Cloudflare assessment pilot contracts, fallback and metrics."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from api.services import call_llm_with_fallback, llm_provider_scope
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import (
    ASSESSMENT_OPERATION,
    ASSESSMENT_COMPLETION_TOKENS,
    PILOT_OPERATION,
    cloudflare_pilot_enabled,
    call_validated_cloudflare_pilot,
    validate_pilot_response,
)
from api.verification.telemetry import (
    get_current_collector,
    record_llm_provider_call,
    verification_telemetry_scope,
)


def assessment_prompt(*keys):
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
        "claim_text": "The city reopened the bridge in 2024.",
        "evidence_items": [
            {"key": key, "evidence_content": f"Evidence {key}."}
            for key in keys
        ],
    })


def result_for(*keys):
    return json.dumps({"assessments": [
        {
            "key": key,
            "stance": "REFUTES" if index % 2 else "SUPPORTS",
            "relevance_score": 0.95,
            "directness_score": 0.85,
        }
        for index, key in enumerate(keys)
    ]})


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareAssessmentRoutingTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "0",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "0",
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
            "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING": "0",
        }))
        self.prompt = assessment_prompt("item_0", "item_2")
        self.good = result_for("item_0", "item_2")
        self.provider = self.enterContext(patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            return_value=self.good,
        ))
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(
            text=self.good,
        )
        self.gemini = self.enterContext(patch(
            "api.services.gemini_client", gemini,
        ))
        groq = Mock()
        groq.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=self.good),
            )],
        )
        self.groq = self.enterContext(patch(
            "api.services.groq_client", groq,
        ))

    def _enable(self):
        os.environ["ENABLE_CLOUDFLARE_VERIFICATION_PILOT"] = "1"
        os.environ["ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"] = "1"

    def _call(self, prompt=None):
        return call_llm_with_fallback(
            "Independent source assessment only.",
            prompt if prompt is not None else self.prompt,
            operation=ASSESSMENT_OPERATION,
        )

    def test_assessment_off_when_only_verdict_flag_enabled(self):
        os.environ["ENABLE_CLOUDFLARE_VERIFICATION_PILOT"] = "1"
        self.assertFalse(cloudflare_pilot_enabled(ASSESSMENT_OPERATION))
        self.assertTrue(cloudflare_pilot_enabled(PILOT_OPERATION))
        self.assertEqual(self._call(), self.good)
        self.provider.assert_not_called()
        self.gemini.models.generate_content.assert_called_once()

    def test_assessment_flag_alone_cannot_enable_pilot(self):
        os.environ["ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"] = "1"
        self.assertFalse(cloudflare_pilot_enabled(ASSESSMENT_OPERATION))
        self.assertEqual(self._call(), self.good)
        self.provider.assert_not_called()

    @override_settings(APP_ENV="production", DEBUG=True)
    def test_production_never_routes_to_cloudflare(self):
        self._enable()
        self.assertFalse(cloudflare_pilot_enabled(ASSESSMENT_OPERATION))
        self.assertEqual(self._call(), self.good)
        self.provider.assert_not_called()

    @override_settings(APP_ENV="staging", DEBUG=True)
    def test_staging_never_routes_to_cloudflare(self):
        self._enable()
        self.assertFalse(cloudflare_pilot_enabled(ASSESSMENT_OPERATION))
        self.assertEqual(self._call(), self.good)
        self.provider.assert_not_called()

    @override_settings(APP_ENV="development", DEBUG=False)
    def test_debug_false_never_routes_to_cloudflare(self):
        self._enable()
        self.assertFalse(cloudflare_pilot_enabled(ASSESSMENT_OPERATION))
        self.assertEqual(self._call(), self.good)
        self.provider.assert_not_called()

    def test_valid_keyed_cloudflare_batch_is_accepted_without_fallback(self):
        self._enable()
        with patch("api.services.record_llm_provider_call") as record:
            result = self._call()
        self.assertEqual(result, self.good)
        self.gemini.models.generate_content.assert_not_called()
        self.groq.chat.completions.create.assert_not_called()
        self.assertEqual(
            self.provider.call_args.kwargs["max_completion_tokens"],
            ASSESSMENT_COMPLETION_TOKENS,
        )
        self.assertEqual(
            record.call_args.args[:2], (ASSESSMENT_OPERATION, "cloudflare"),
        )
        self.assertEqual(record.call_args.args[4], "success")

    def test_invalid_cloudflare_batch_uses_gemini_fallback(self):
        self._enable()
        self.provider.return_value = result_for("item_0")
        self.assertEqual(self._call(), self.good)
        self.provider.assert_called_once()
        self.gemini.models.generate_content.assert_called_once()
        self.groq.chat.completions.create.assert_not_called()

    def test_cloudflare_and_gemini_invalid_use_groq_fallback(self):
        self._enable()
        self.provider.return_value = "{}"
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=result_for("item_0"),
        )
        self.assertEqual(self._call(), self.good)
        self.provider.assert_called_once()
        self.gemini.models.generate_content.assert_called_once()
        self.groq.chat.completions.create.assert_called_once()

    def test_prompt_too_long_falls_back_without_dropping_items(self):
        self._enable()
        self.provider.side_effect = CloudflareEvaluationError(
            "PROMPT_TOO_LONG",
        )
        self.assertEqual(self._call(), self.good)
        self.gemini.models.generate_content.assert_called_once()
        self.assertIn("item_2", self.gemini.models.generate_content.call_args.kwargs["contents"])

    def test_failed_assessment_cloudflare_not_retried_on_same_job(self):
        self._enable()
        self.provider.side_effect = [
            CloudflareEvaluationError("HTTP_429"),
            self.good,
        ]
        with llm_provider_scope():
            self.assertEqual(self._call(), self.good)
            self.assertEqual(self._call(), self.good)
        self.assertEqual(self.provider.call_count, 1)
        with llm_provider_scope():
            self.assertEqual(self._call(), self.good)
        self.assertEqual(self.provider.call_count, 2)

    def test_other_operation_preserves_legacy_order(self):
        self._enable()
        self.assertEqual(
            call_llm_with_fallback("System", "Test",
                                   operation="claim_equivalence"),
            self.good,
        )
        self.provider.assert_not_called()


class CloudflareAssessmentContractTests(SimpleTestCase):
    def setUp(self):
        self.prompt = assessment_prompt("item_0", "item_2")
        self.good = result_for("item_0", "item_2")

    def test_valid_reordered_results_and_contradictory_stances(self):
        obj = json.loads(self.good)
        obj["assessments"].reverse()
        self.assertTrue(validate_pilot_response(
            ASSESSMENT_OPERATION, json.dumps(obj), self.prompt,
        ))

    def test_invalid_assessment_cannot_be_treated_as_success(self):
        for invalid in (
            "{}",
            "not json",
            "[]",
            result_for("item_0"),
            result_for("item_0", "item_0"),
            result_for("item_0", "item_99"),
        ):
            with self.subTest(invalid=invalid[:30]):
                self.assertFalse(validate_pilot_response(
                    ASSESSMENT_OPERATION, invalid, self.prompt,
                ))

    def test_invalid_score_stance_and_extra_fields_rejected(self):
        for key, value in (
            ("stance", "FACT"),
            ("stance", ["SUPPORTS"]),
            ("relevance_score", 1.5),
            ("directness_score", -0.1),
            ("directness_score", True),
            ("directness_score", "0.85"),
            ("relevance_score", None),
            ("relevance_score", float("inf")),
        ):
            with self.subTest(key=key, value=value):
                obj = json.loads(self.good)
                obj["assessments"][0][key] = value
                self.assertFalse(validate_pilot_response(
                    ASSESSMENT_OPERATION, json.dumps(obj), self.prompt,
                ))
        obj = json.loads(self.good)
        obj["assessments"][0]["publisher"] = "untrusted data"
        self.assertFalse(validate_pilot_response(
            ASSESSMENT_OPERATION, json.dumps(obj), self.prompt,
        ))

    def test_untrusted_unknown_or_duplicate_inputs_fail_before_http(self):
        for prompt in (
            "not assessment JSON",
            assessment_prompt("item_0", "item_0"),
            assessment_prompt("item_0", "unknown"),
            "UNTRUSTED ASSESSMENT DATA:\n{}",
        ):
            with self.subTest(prompt=prompt[:30]), patch(
                "api.verification.cloudflare_pilot.generate_evaluation_json"
            ) as http:
                with self.assertRaises(CloudflareEvaluationError):
                    call_validated_cloudflare_pilot(
                        "System", prompt, operation=ASSESSMENT_OPERATION,
                    )
                http.assert_not_called()

    def test_validated_wrapper_uses_stage_specific_budget(self):
        with patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            return_value=self.good,
        ) as provider:
            raw = call_validated_cloudflare_pilot(
                "System", self.prompt, operation=ASSESSMENT_OPERATION,
            )
        self.assertEqual(raw, self.good)
        self.assertEqual(
            provider.call_args.kwargs["max_completion_tokens"],
            ASSESSMENT_COMPLETION_TOKENS,
        )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_final_budget_default_and_opt_in_development_only(self):
        from api.verification.cloudflare_pilot import PILOT_COMPLETION_TOKENS
        evaluation = json.dumps({
            "reasoning": "Documented support.",
            "verdict": "FACT",
            "summary": "The claim is supported.",
            "confidence_score": 91,
            "score_context": "One direct public source.",
        })
        with patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            return_value=evaluation,
        ) as provider:
            call_validated_cloudflare_pilot("System", "Dossier")
            self.assertEqual(
                provider.call_args.kwargs["max_completion_tokens"],
                PILOT_COMPLETION_TOKENS,
            )
            with patch.dict(os.environ, {
                "CLOUDFLARE_PILOT_FINAL_MAX_TOKENS": "1536",
            }):
                call_validated_cloudflare_pilot("System", "Dossier")
                self.assertEqual(
                    provider.call_args.kwargs["max_completion_tokens"], 1536,
                )
            with patch.dict(os.environ, {
                "CLOUDFLARE_PILOT_FINAL_MAX_TOKENS": "20",
            }):
                call_validated_cloudflare_pilot("System", "Dossier")
                self.assertEqual(
                    provider.call_args.kwargs["max_completion_tokens"],
                    PILOT_COMPLETION_TOKENS,
                )
            with patch.dict(os.environ, {
                "CLOUDFLARE_PILOT_FINAL_MAX_TOKENS": "1536",
            }), override_settings(APP_ENV="production", DEBUG=False):
                call_validated_cloudflare_pilot("System", "Dossier")
                self.assertEqual(
                    provider.call_args.kwargs["max_completion_tokens"],
                    PILOT_COMPLETION_TOKENS,
                )

    def test_operation_whitelist_blocks_unknown_stage(self):
        with patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json"
        ) as provider, self.assertRaises(CloudflareEvaluationError):
            call_validated_cloudflare_pilot(
                "System", "Dossier", operation="claim_equivalence",
            )
        provider.assert_not_called()

    def test_sanitized_token_telemetry_excludes_prompts_and_secrets(self):
        @verification_telemetry_scope()
        def invoke(claim_id):
            record_llm_provider_call(
                ASSESSMENT_OPERATION, "cloudflare", uuid4(), 20001, "success",
                metadata={
                    "finish_reason": "stop",
                    "prompt_tokens": 1250,
                    "completion_tokens": 220,
                    "reasoning_tokens": 120,
                    "total_tokens": 1470,
                    "reasoning_present": True,
                    "secret": "do-not-persist",
                    "user_prompt": "private evidence data",
                },
            )
            return get_current_collector().events[0]["metadata"]

        recorded = invoke(str(uuid4()))
        self.assertEqual(recorded, {
            "finish_reason": "stop",
            "prompt_tokens": 1250,
            "completion_tokens": 220,
            "reasoning_tokens": 120,
            "total_tokens": 1470,
            "reasoning_present": True,
        })
        self.assertNotIn("private evidence data", str(recorded))

    def test_invalid_usage_counters_are_not_persisted(self):
        @verification_telemetry_scope()
        def invoke(claim_id):
            record_llm_provider_call(
                PILOT_OPERATION, "cloudflare", uuid4(), 5000, "success",
                metadata={
                    "finish_reason": "unexpected vendor detail",
                    "prompt_tokens": -1,
                    "completion_tokens": True,
                    "total_tokens": "100",
                    "reasoning_present": "yes",
                },
            )
            return get_current_collector().events[0]["metadata"]
        self.assertEqual(invoke(str(uuid4())), {})
