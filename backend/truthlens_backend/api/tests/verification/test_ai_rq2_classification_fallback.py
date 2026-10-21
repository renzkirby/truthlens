"""No-network, contract-bound Cloudflare classification routing acceptance.

Classification is independent of truth/verdict determination and cannot grant
partner scope or claimability merely because a model output is parseable.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from api.investigation_classifier import validate_model_suggestion
from api.services import (
    LLMProviderUnavailableError,
    call_llm_with_fallback,
    llm_provider_scope,
)
from api.verification.classification_contract import (
    CLASSIFICATION_OPERATION, validate_classification_response,
)
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import (
    CLASSIFICATION_COMPLETION_TOKENS, CLASSIFICATION_HTTP_TIMEOUT,
    cloudflare_classification_http_timeout,
    cloudflare_classification_reject_if_busy_enabled,
    call_validated_cloudflare_pilot, cloudflare_pilot_enabled,
)
from api.verification.telemetry import (
    get_current_collector, verification_telemetry_scope,
)


CLAIM = "Researchers reported that a science experiment achieved reproducible results."
VALID = json.dumps({
    "decision": "CLASSIFY",
    "domains": [{"code": "SCIENCE", "evidence": "science experiment"}],
})
ABSTAIN = json.dumps({"decision": "ABSTAIN", "domains": []})


class GeminiBillingError(RuntimeError):
    code = 402


class GroqLimited(RuntimeError):
    status_code = 429


class StrictClassificationContractTests(SimpleTestCase):
    def test_accepts_quoted_subject_and_explicit_abstention(self):
        self.assertTrue(validate_classification_response(VALID, CLAIM))
        self.assertTrue(validate_classification_response(ABSTAIN, CLAIM))
        self.assertEqual(
            validate_model_suggestion(CLAIM, json.loads(VALID)),
            ["SCIENCE"],
        )

    def test_rejects_unsupported_domain_and_invented_quote(self):
        for payload in (
            {"decision": "CLASSIFY", "domains": [
                {"code": "NOT_A_DOMAIN", "evidence": "science experiment"}]},
            {"decision": "CLASSIFY", "domains": [
                {"code": "SCIENCE", "evidence": "fabricated wording"}]},
            {"decision": "CLASSIFY", "domains": [
                {"code": "SCIENCE", "evidence": "sc"}]},
            {"decision": "CLASSIFY", "domains": [
                {"code": "SCIENCE", "evidence": "science experiment"},
                {"code": "SCIENCE", "evidence": "Researchers reported"}]},
            {"decision": "ABSTAIN", "domains": [
                {"code": "SCIENCE", "evidence": "science experiment"}]},
            {"decision": "ABSTAIN", "domains": [], "jurisdiction": "PH"},
            {"decision": "CLASSIFY", "domains": [
                {"code": "SCIENCE", "evidence": "science experiment",
                 "confidence": 1.0}]},
            {"decision": "CLASSIFY", "domains": [
                {"code": "SCIENCE", "evidence": "science experiment"}],
             "verdict": "FACT"},
            {"decision": "UNKNOWN", "domains": []},
            {"decision": "CLASSIFY", "domains": []},
            {"decision": "CLASSIFY", "domains": [
                {"code": "SCIENCE", "evidence": "science experiment"}] * 4},
        ):
            with self.subTest(payload=payload):
                self.assertFalse(validate_classification_response(
                    json.dumps(payload), CLAIM,
                ))

    def test_malformed_non_object_and_nonstring_are_rejected(self):
        for raw in ('', 'not-json', '[]', 'null', '{"decision":true}',
                    '{"decision":"ABSTAIN","domains":null}', None, 22):
            with self.subTest(raw=raw):
                self.assertFalse(validate_classification_response(raw, CLAIM))
        self.assertFalse(validate_classification_response(VALID, None))


@override_settings(APP_ENV="development", DEBUG=True)
class ClassificationProviderHierarchyTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "0",
            "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING": "0",
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "0",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "",
        }))
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(text=VALID)
        self.gemini = self.enterContext(patch("api.services.gemini_client", gemini))
        self.cloud = self.enterContext(patch(
            "api.services.call_validated_cloudflare_pilot",
            return_value=VALID,
        ))
        groq = Mock()
        self.groq = self.enterContext(patch("api.services.groq_client", groq))
        self.groq_lane = groq.with_options.return_value.chat.completions.create
        self.groq_lane.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=VALID)),
        ])

    def _request(self, claim=CLAIM):
        return call_llm_with_fallback(
            "Classify the claim subject using exact quotations.",
            claim, operation=CLASSIFICATION_OPERATION,
        )

    def test_valid_gemini_response_uses_no_secondary_provider(self):
        self.assertTrue(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
        self.assertEqual(self._request(), VALID)
        self.cloud.assert_not_called()
        self.groq_lane.assert_not_called()

    def test_gemini_billing_failure_falls_to_cloudflare_not_groq(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        with patch("api.services.record_llm_provider_call") as record:
            self.assertEqual(self._request(), VALID)
        self.cloud.assert_called_once()
        self.assertEqual(
            self.cloud.call_args.kwargs["operation"],
            CLASSIFICATION_OPERATION,
        )
        self.groq_lane.assert_not_called()
        self.assertEqual(
            [(call.args[1], call.args[4]) for call in record.call_args_list],
            [("gemini", "failed"), ("cloudflare", "success")],
        )

    def test_valid_abstention_is_accepted_without_forced_classification(self):
        self.gemini.models.generate_content.return_value = SimpleNamespace(text=ABSTAIN)
        self.assertEqual(self._request(), ABSTAIN)
        self.cloud.assert_not_called()
        self.groq_lane.assert_not_called()

    def test_hallucinated_gemini_classification_falls_to_cloudflare(self):
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps({
                "decision": "CLASSIFY",
                "domains": [{"code": "SCIENCE", "evidence": "imaginary quote"}],
            }),
        )
        self.assertEqual(self._request(), VALID)
        self.cloud.assert_called_once()
        self.groq_lane.assert_not_called()

    def test_invalid_cloudflare_output_falls_to_validated_groq(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.cloud.side_effect = CloudflareEvaluationError(
            "INVALID_CLASSIFICATION_JSON",
        )
        self.assertEqual(self._request(), VALID)
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_lane.assert_called_once()

    def test_invalid_groq_response_exhausts_without_granting_authority(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.cloud.side_effect = CloudflareEvaluationError("HTTP_429_CAPACITY")
        self.groq_lane.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content='{"decision":"CLASSIFY","domains":[]}')),
        ])
        with self.assertRaises(LLMProviderUnavailableError):
            self._request()
        self.groq_lane.assert_called_once()

    def test_all_three_unavailable_raises_and_does_not_model_hop(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.cloud.side_effect = CloudflareEvaluationError("TRANSPORT_ReadTimeout")
        self.groq_lane.side_effect = GroqLimited("429 synthetic")
        with self.assertRaises(LLMProviderUnavailableError):
            self._request()
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_lane.assert_called_once()

    def test_classification_route_independent_of_assessment_pilot(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.assertEqual(
            os.environ["ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT"], "0",
        )
        self.assertEqual(self._request(), VALID)
        self.cloud.assert_called_once()

    def test_without_classification_flag_never_calls_cloudflare(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "0",
        }):
            self.assertFalse(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
            self.assertEqual(self._request(), VALID)
        self.cloud.assert_not_called()
        self.groq_lane.assert_called_once()

    def test_flag_off_invalid_groq_still_enforces_contract_when_hierarchy_active(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.groq_lane.return_value = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content='{"decision":"CLASSIFY","domains":[]}')),
        ])
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "0",
        }), self.assertRaises(LLMProviderUnavailableError):
            self._request()
        self.cloud.assert_not_called()

    def test_cloudflare_provider_job_breaker_prevents_repeat_after_transport_failure(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)
        self.cloud.side_effect = CloudflareEvaluationError("TRANSPORT_ReadTimeout")
        with llm_provider_scope():
            self.assertEqual(self._request(), VALID)
            self.assertEqual(self._request(), VALID)
        self.gemini.models.generate_content.assert_called_once()
        self.cloud.assert_called_once()
        self.assertEqual(self.groq_lane.call_count, 2)

    def test_safe_classification_provider_telemetry_label(self):
        self.gemini.models.generate_content.side_effect = GeminiBillingError(402)

        @verification_telemetry_scope()
        def run(claim_id):
            with llm_provider_scope():
                self._request()
            return get_current_collector().events

        events = run(str(uuid4()))
        self.assertEqual([event["name"] for event in events],
                         [CLASSIFICATION_OPERATION] * 2)
        self.assertEqual([event["provider"] for event in events],
                         ["gemini", "cloudflare"])
        self.assertNotIn(CLAIM, str(events))

    @override_settings(APP_ENV="production", DEBUG=False)
    def test_production_disables_cloudflare_route_even_when_opted_in(self):
        self.assertFalse(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
        self.assertEqual(self._request(), VALID)
        self.cloud.assert_not_called()
        self.groq.with_options.assert_not_called()

    @override_settings(APP_ENV="staging", DEBUG=True)
    def test_staging_disables_cloudflare_route_even_when_opted_in(self):
        self.assertFalse(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
        self.assertEqual(self._request(), VALID)
        self.cloud.assert_not_called()
        self.groq.with_options.assert_not_called()


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareClassificationAdapterTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "1",
            "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY": "0",
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "0",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "",
        }))
        self.generate = self.enterContext(patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            return_value=VALID,
        ))

    def test_classification_adapter_preserves_input_and_bounded_settings(self):
        metadata = {}
        self.assertEqual(
            call_validated_cloudflare_pilot(
                "Classify subjects", CLAIM,
                operation=CLASSIFICATION_OPERATION, audit_metadata=metadata,
            ), VALID,
        )
        self.generate.assert_called_once()
        self.assertEqual(self.generate.call_args.args, ("Classify subjects", CLAIM))
        self.assertEqual(
            self.generate.call_args.kwargs["max_completion_tokens"],
            CLASSIFICATION_COMPLETION_TOKENS,
        )
        self.assertEqual(self.generate.call_args.kwargs["http_timeout"],
                         CLASSIFICATION_HTTP_TIMEOUT)
        self.assertNotIn("reject_if_busy", self.generate.call_args.kwargs)


    def test_default_classification_policy_is_unchanged(self):
        self.assertFalse(cloudflare_classification_reject_if_busy_enabled())
        self.assertEqual(
            cloudflare_classification_http_timeout(),
            CLASSIFICATION_HTTP_TIMEOUT,
        )
        call_validated_cloudflare_pilot(
            "Classify subjects", CLAIM, operation=CLASSIFICATION_OPERATION,
        )
        self.assertNotIn("reject_if_busy", self.generate.call_args.kwargs)
        self.assertEqual(
            self.generate.call_args.kwargs["http_timeout"],
            (3, 15),
        )

    def test_explicit_classification_capacity_fast_fail_only_in_classification(self):
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "1",
        }):
            self.assertTrue(cloudflare_classification_reject_if_busy_enabled())
            call_validated_cloudflare_pilot(
                "Classify subjects", CLAIM, operation=CLASSIFICATION_OPERATION,
            )
            self.assertIs(self.generate.call_args.kwargs["reject_if_busy"], True)
            self.assertEqual(
                self.generate.call_args.kwargs["max_completion_tokens"],
                CLASSIFICATION_COMPLETION_TOKENS,
            )
            # No opt-in was given to the separate factual-verdict stage.
            self.generate.reset_mock()
            self.generate.return_value = json.dumps({
                "reasoning": "The supplied source corroborates the statement.",
                "verdict": "FACT",
                "summary": "Supported by the supplied evidence.",
                "confidence_score": 85,
                "score_context": "The evidence directly supports the claim.",
            })
            call_validated_cloudflare_pilot(
                "Evaluate evidence", "Grounded evidence context.",
            )
            self.assertNotIn("reject_if_busy", self.generate.call_args.kwargs)

    def test_bounded_30_second_diagnostic_is_off_by_default(self):
        for invalid in ("", "0", "15", "29", "31", "60", "30.0", " 30 "):
            with self.subTest(value=invalid), patch.dict(os.environ, {
                "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": invalid,
            }):
                self.assertEqual(
                    cloudflare_classification_http_timeout(), (3, 15),
                )
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "30",
        }):
            self.assertEqual(
                cloudflare_classification_http_timeout(), (3, 30),
            )
            call_validated_cloudflare_pilot(
                "Classify subjects", CLAIM, operation=CLASSIFICATION_OPERATION,
            )
        self.assertEqual(
            self.generate.call_args.kwargs["http_timeout"], (3, 30),
        )
        self.assertEqual(
            self.generate.call_args.kwargs["max_completion_tokens"], 1024,
        )

    def test_capacity_fast_fail_and_timeout_profile_require_dev_gates(self):
        for key in (
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT",
        ):
            with self.subTest(flag=key), patch.dict(os.environ, {
                key: "0",
                "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "1",
                "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "30",
            }):
                self.assertFalse(
                    cloudflare_classification_reject_if_busy_enabled(),
                )
                self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "1",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "30",
        }):
            with override_settings(APP_ENV="production", DEBUG=False):
                self.assertFalse(
                    cloudflare_classification_reject_if_busy_enabled(),
                )
                self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))
            with override_settings(APP_ENV="staging", DEBUG=True):
                self.assertFalse(
                    cloudflare_classification_reject_if_busy_enabled(),
                )
                self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))
            with override_settings(DEBUG=False):
                self.assertFalse(
                    cloudflare_classification_reject_if_busy_enabled(),
                )
                self.assertEqual(cloudflare_classification_http_timeout(), (3, 15))

    def test_short_assessment_and_final_timeout_are_not_changed(self):
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY": "1",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "30",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
        }):
            self.generate.return_value = json.dumps({
                "assessments": [{
                    "key": "item_0", "stance": "SUPPORTS",
                    "relevance_score": 0.9, "directness_score": 0.8,
                }],
            })
            call_validated_cloudflare_pilot(
                "Assess evidence",
                "UNTRUSTED ASSESSMENT DATA:\\n" + json.dumps({
                    "claim_text": CLAIM,
                    "evidence_items": [{
                        "key": "item_0",
                        "evidence_content": "The original evidence passage.",
                    }],
                }),
                operation="evidence_assessment",
            )
            self.assertEqual(
                self.generate.call_args.kwargs["http_timeout"], (3, 15),
            )
            self.assertNotIn("reject_if_busy", self.generate.call_args.kwargs)

    def test_invalid_classification_adaptor_json_rejected(self):
        self.generate.return_value = '{"decision":"CLASSIFY","domains":[]}'
        with self.assertRaisesRegex(CloudflareEvaluationError,
                                    "^INVALID_CLASSIFICATION_JSON$"):
            call_validated_cloudflare_pilot(
                "System", CLAIM, operation=CLASSIFICATION_OPERATION,
            )

    def test_empty_abstention_is_valid_classification_outcome(self):
        self.generate.return_value = ABSTAIN
        self.assertEqual(call_validated_cloudflare_pilot(
            "System", CLAIM, operation=CLASSIFICATION_OPERATION,
        ), ABSTAIN)

    def test_invalid_or_oversized_input_blocks_network(self):
        for text in ("", "No", "x" * 2401, 10, None):
            with self.subTest(text=str(text)[:20]):
                with self.assertRaisesRegex(CloudflareEvaluationError,
                                            "INVALID_CLASSIFICATION_INPUT"):
                    call_validated_cloudflare_pilot(
                        "System", text, operation=CLASSIFICATION_OPERATION,
                    )
        self.generate.assert_not_called()

    def test_no_classification_flag_or_non_dev_cannot_enable_routing(self):
        for name in (
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT",
        ):
            with self.subTest(name=name), patch.dict(os.environ, {name: "0"}):
                self.assertFalse(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
        with override_settings(APP_ENV="production", DEBUG=False):
            self.assertFalse(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
        with override_settings(DEBUG=False):
            self.assertFalse(cloudflare_pilot_enabled(CLASSIFICATION_OPERATION))
