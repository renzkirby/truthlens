"""Offline safeguards for bounded, lossless Cloudflare assessment chunking."""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from api.services import call_llm_with_fallback, llm_provider_scope
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import (
    ASSESSMENT_MAX_CHUNKS,
    ASSESSMENT_MAX_ITEMS,
    ASSESSMENT_OPERATION,
    cloudflare_assessment_chunking_enabled,
    cloudflare_assessment_chunking_bypass_reason,
)
from api.verification.telemetry import (
    get_current_collector,
    verification_telemetry_scope,
)
from uuid import uuid4


def make_prompt(count=12, item_length=24):
    passages = [
        f"Original passage {index}: " + ("A" * item_length)
        for index in range(count)
    ]
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
        "claim_text": "The spacecraft launched on October 14, 2024.",
        "evidence_items": [
            {"key": f"item_{index}", "evidence_content": passage}
            for index, passage in enumerate(passages)
        ],
    }, ensure_ascii=False)


def keys_and_contents(prompt):
    data = json.loads(prompt.split("\n", 1)[1])
    return [(item["key"], item["evidence_content"])
            for item in data["evidence_items"]]


def response_for(prompt):
    return json.dumps({"assessments": [
        {
            "key": key,
            "stance": "SUPPORTS" if int(key[5:]) % 2 == 0 else "REFUTES",
            "relevance_score": 0.85,
            "directness_score": 0.75,
        }
        for key, _ in keys_and_contents(prompt)
    ]})


class GeminiQuotaError(RuntimeError):
    code = 402


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareAssessmentChunkingTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
            "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING": "1",
            "CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY": "0",
        }))
        self.gemini = self.enterContext(
            patch("api.services.gemini_client", Mock())
        )
        self.gemini.models.generate_content.side_effect = GeminiQuotaError(
            "capacity exhausted",
        )
        self.groq = self.enterContext(
            patch("api.services.groq_client", Mock())
        )
        self.chunk_calls = []
        self.generate = self.enterContext(patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            side_effect=self._generate_chunk,
        ))
        self.groq_fallback = self.groq.with_options.return_value.chat.completions.create
        self.groq_fallback.side_effect = self._groq_response

    def _generate_chunk(self, system, prompt, **kwargs):
        self.chunk_calls.append((system, prompt, kwargs))
        audit = kwargs.get("audit_metadata")
        if isinstance(audit, dict):
            audit.update({
                "prompt_tokens": 100,
                "completion_tokens": 75,
                "total_tokens": 175,
                "reasoning_tokens": 30,
                "reasoning_present": True,
                "finish_reason": "stop",
                "private_token": "DO_NOT_PERSIST",
            })
        return response_for(prompt)

    def _groq_response(self, **kwargs):
        prompt = kwargs["messages"][1]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=response_for(prompt)),
        )])

    def _call(self, prompt):
        return call_llm_with_fallback(
            "Assess every passage independently. Preserve each key.",
            prompt, operation=ASSESSMENT_OPERATION,
        )

    def test_twelve_items_are_three_validated_calls_without_groq(self):
        prompt = make_prompt(12)
        self.assertTrue(cloudflare_assessment_chunking_enabled())
        self.assertIsNone(cloudflare_assessment_chunking_bypass_reason(
            "Assess every passage independently. Preserve each key.", prompt,
        ))
        with llm_provider_scope(), patch(
            "api.services.record_llm_provider_call",
        ) as record:
            actual = json.loads(self._call(prompt))
        self.assertEqual(len(self.chunk_calls), 3)
        self.assertEqual(ASSESSMENT_MAX_ITEMS, 4)
        self.assertEqual(ASSESSMENT_MAX_CHUNKS, 3)
        self.assertEqual(
            [len(keys_and_contents(prompt)) for _, prompt, _ in self.chunk_calls],
            [4, 4, 4],
        )
        original = keys_and_contents(prompt)
        assembled = [
            item
            for _, chunk_prompt, _ in self.chunk_calls
            for item in keys_and_contents(chunk_prompt)
        ]
        self.assertEqual(assembled, original)
        self.assertEqual(
            [x["key"] for x in actual["assessments"]],
            [key for key, _ in original],
        )
        self.assertEqual(
            [x["stance"] for x in actual["assessments"]],
            ["SUPPORTS", "REFUTES"] * 6,
        )
        self.groq_fallback.assert_not_called()
        self.assertEqual(
            [(call.args[1], call.args[4]) for call in record.call_args_list],
            [("gemini", "failed"), ("cloudflare", "success")],
        )
        self.assertEqual(
            record.call_args.kwargs["metadata"]["assessment_chunks_attempted"], 3,
        )

    def test_oversized_original_prompt_can_split_without_trimming(self):
        prompt = make_prompt(12, item_length=3000)
        self.assertGreater(
            len(prompt) + len("Assess every passage independently. Preserve each key."),
            28000,
        )
        actual = json.loads(self._call(prompt))
        self.assertEqual(len(actual["assessments"]), 12)
        self.assertEqual(len(self.chunk_calls), 3)
        self.assertEqual(
            [item for _, p, _ in self.chunk_calls for item in keys_and_contents(p)],
            keys_and_contents(prompt),
        )
        self.assertTrue(all(
            len(system) + len(chunk_prompt) <= 28000
            for system, chunk_prompt, _ in self.chunk_calls
        ))
        self.groq_fallback.assert_not_called()

    def test_thirteen_items_skip_cloudflare_and_preserve_original_groq_batch(self):
        original = make_prompt(13)
        with patch("api.services.record_llm_provider_call") as record:
            result = self._call(original)
        self.assertEqual(
            len(json.loads(result)["assessments"]), 13,
        )
        self.generate.assert_not_called()
        self.groq_fallback.assert_called_once()
        self.assertEqual(
            self.groq_fallback.call_args.kwargs["messages"][1]["content"],
            original,
        )
        self.assertEqual(
            [(call.args[1], call.args[4]) for call in record.call_args_list],
            [("gemini", "failed"), ("cloudflare", "skipped"), ("groq", "success")],
        )

    def test_failing_second_chunk_discards_partial_and_uses_full_groq_batch(self):
        original = make_prompt(12)
        call_count = 0

        def second_chunk_timeout(system, prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise CloudflareEvaluationError("TRANSPORT_ReadTimeout")
            return self._generate_chunk(system, prompt, **kwargs)

        self.generate.side_effect = second_chunk_timeout

        @verification_telemetry_scope()
        def verification(claim_id):
            with llm_provider_scope():
                result = self._call(original)
                return result, [event for event in get_current_collector().events
                                if event["provider"] == "cloudflare"]

        result, events = verification(str(uuid4()))
        self.assertEqual(call_count, 2)
        self.assertEqual(
            [item["key"] for item in json.loads(result)["assessments"]],
            [f"item_{i}" for i in range(12)],
        )
        self.groq_fallback.assert_called_once()
        self.assertEqual(
            self.groq_fallback.call_args.kwargs["messages"][1]["content"],
            original,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "failed")
        self.assertEqual(
            events[0]["error_label"],
            "CloudflareEvaluationError code=TRANSPORT_ReadTimeout",
        )
        self.assertEqual(
            events[0]["metadata"]["assessment_chunks_attempted"], 2,
        )
        self.assertNotIn("private_token", str(events[0]))

    def test_a_malformed_single_chunk_never_gets_partially_accepted(self):
        original = make_prompt(12)
        def invalid_second(system, prompt, **kwargs):
            if len(self.chunk_calls) == 1:
                self.chunk_calls.append((system, prompt, kwargs))
                return json.dumps({"assessments": []})
            return self._generate_chunk(system, prompt, **kwargs)

        self.generate.side_effect = invalid_second
        result = self._call(original)
        self.assertEqual(len(json.loads(result)["assessments"]), 12)
        self.assertEqual(self.generate.call_count, 2)
        self.groq_fallback.assert_called_once()
        self.assertEqual(
            self.groq_fallback.call_args.kwargs["messages"][1]["content"],
            original,
        )

    def test_indivisible_oversize_source_bypasses_without_any_cloudflare_call(self):
        original = make_prompt(1, item_length=29000)
        self.assertEqual(
            cloudflare_assessment_chunking_bypass_reason("System", original),
            "PROMPT_TOO_LONG",
        )
        self.assertEqual(
            len(json.loads(self._call(original))["assessments"]), 1,
        )
        self.generate.assert_not_called()
        self.assertEqual(
            self.groq_fallback.call_args.kwargs["messages"][1]["content"],
            original,
        )

    def test_without_opt_in_original_twelve_item_skip_is_preserved(self):
        with patch.dict(os.environ, {
            "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING": "0",
        }):
            self.assertFalse(cloudflare_assessment_chunking_enabled())
            prompt = make_prompt(12)
            self.assertEqual(
                len(json.loads(self._call(prompt))["assessments"]), 12,
            )
            self.generate.assert_not_called()
            self.groq_fallback.assert_called_once()

    def test_worker_flags_must_all_be_present(self):
        for flag in (
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT",
            "CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING",
        ):
            with self.subTest(flag=flag), patch.dict(os.environ, {flag: "0"}):
                self.assertFalse(cloudflare_assessment_chunking_enabled())
        with override_settings(APP_ENV="production", DEBUG=False):
            self.assertFalse(cloudflare_assessment_chunking_enabled())
        with override_settings(APP_ENV="staging"):
            self.assertFalse(cloudflare_assessment_chunking_enabled())

    def test_chunk_telemetry_reports_only_bounded_aggregates(self):
        @verification_telemetry_scope()
        def verification(claim_id):
            with llm_provider_scope():
                self._call(make_prompt(12))
            return [event for event in get_current_collector().events
                    if event["provider"] == "cloudflare"]

        events = verification(str(uuid4()))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["outcome"], "success")
        self.assertEqual(events[0]["metadata"], {
            "prompt_tokens": 300,
            "completion_tokens": 225,
            "total_tokens": 525,
            "reasoning_tokens": 90,
            "reasoning_present": True,
            "finish_reason": "stop",
            "assessment_chunks_attempted": 3,
        })
        self.assertNotIn("DO_NOT_PERSIST", str(events))
