"""Offline tests for degraded-path-only Cloudflare assessment budgeting."""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from django.test import SimpleTestCase, override_settings

from api import tasks
from api.models import VerificationEvidence
from api.services import call_llm_with_fallback, llm_provider_scope
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification.cloudflare_pilot import (
    ASSESSMENT_OPERATION,
    cloudflare_assessment_tail_budget_details,
)
from api.verification.evidence_assessment import (
    assess_reasoning_evidence_batch_against_claim,
)
from api.verification.provider_hierarchy import (
    cloudflare_assessment_tail_budget_enabled,
)


SYSTEM = "Assess every passage independently. Preserve each key."


def make_prompt(count=10):
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
        "claim_text": "A verifiable public claim.",
        "evidence_items": [
            {
                "key": f"item_{index}",
                "evidence_content": f"Original passage {index}.",
            }
            for index in range(count)
        ],
    }, ensure_ascii=False)


def subset_prompt(original, indices):
    payload = json.loads(original.split("\n", 1)[1])
    items = payload["evidence_items"]
    return "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps({
        "claim_text": payload["claim_text"],
        "evidence_items": [items[index] for index in indices],
    }, ensure_ascii=False)


def keys(prompt):
    payload = json.loads(prompt.split("\n", 1)[1])
    return [item["key"] for item in payload["evidence_items"]]


def response_for(prompt):
    return json.dumps({
        "assessments": [
            {
                "key": key,
                "stance": "SUPPORTS",
                "relevance_score": 0.9,
                "directness_score": 0.8,
            }
            for key in keys(prompt)
        ]
    })


def evidence_item(*, role=VerificationEvidence.EvidenceRole.SECONDARY):
    return SimpleNamespace(
        evidence_link_id=uuid4(),
        evidence_source_id=uuid4(),
        evidence_role=role,
        stance=VerificationEvidence.Stance.UNKNOWN,
        relevance_score=None,
        directness_score=None,
        content="Persisted evidence content.",
    )


def evidence_group(*items):
    return SimpleNamespace(identity_id=uuid4(), evidence=tuple(items))


class CloudflareAssessmentTailPlannerTests(SimpleTestCase):
    def test_ten_records_across_five_identities_select_eight_and_preserve_each_identity(self):
        groups = [
            evidence_group(evidence_item(), evidence_item())
            for _ in range(5)
        ]
        eligible = tasks._eligible_evidence_assessment_groups(groups)

        selected = tasks._cloudflare_tail_assessment_evidence_link_ids(eligible)

        self.assertEqual(len(selected), 8)
        self.assertTrue(all(
            group.evidence[0].evidence_link_id in selected
            for group in groups
        ))

    def test_nine_distinct_identities_keep_full_behavior(self):
        groups = [evidence_group(evidence_item()) for _ in range(9)]
        eligible = tasks._eligible_evidence_assessment_groups(groups)

        self.assertEqual(
            tasks._cloudflare_tail_assessment_evidence_link_ids(eligible),
            (),
        )

    def test_mixed_fact_check_and_secondary_batch_keeps_full_behavior(self):
        groups = [evidence_group(evidence_item()) for _ in range(8)]
        groups.append(evidence_group(evidence_item(
            role=VerificationEvidence.EvidenceRole.FACT_CHECK,
        )))
        eligible = tasks._eligible_evidence_assessment_groups(groups)

        self.assertEqual(
            tasks._cloudflare_tail_assessment_evidence_link_ids(eligible),
            (),
        )

    def test_batch_outside_nine_to_twelve_keeps_full_behavior(self):
        for count in (8, 13):
            with self.subTest(count=count):
                groups = [evidence_group(evidence_item()) for _ in range(count)]
                eligible = tasks._eligible_evidence_assessment_groups(groups)
                self.assertEqual(
                    tasks._cloudflare_tail_assessment_evidence_link_ids(eligible),
                    (),
                )


class CloudflareAssessmentTailCandidateValidationTests(SimpleTestCase):
    def test_valid_candidate_requires_actual_three_to_two_chunk_reduction(self):
        original = make_prompt(10)
        candidate = subset_prompt(original, range(8))

        details = cloudflare_assessment_tail_budget_details(
            SYSTEM,
            original,
            candidate,
        )

        self.assertEqual(details, {
            "original_items": 10,
            "selected_items": 8,
            "original_chunks": 3,
            "selected_chunks": 2,
        })

    def test_modified_or_reordered_candidate_is_rejected(self):
        original = make_prompt(10)
        reordered = subset_prompt(original, [1, 0, 2, 3, 4, 5, 6, 7])
        tampered_payload = json.loads(
            subset_prompt(original, range(8)).split("\n", 1)[1]
        )
        tampered_payload["evidence_items"][0]["evidence_content"] = "Changed."
        tampered = "UNTRUSTED ASSESSMENT DATA:\n" + json.dumps(tampered_payload)

        self.assertIsNone(cloudflare_assessment_tail_budget_details(
            SYSTEM, original, reordered,
        ))
        self.assertIsNone(cloudflare_assessment_tail_budget_details(
            SYSTEM, original, tampered,
        ))


@override_settings(APP_ENV="development", DEBUG=True)
class CloudflareAssessmentTailRoutingTests(SimpleTestCase):
    def setUp(self):
        self.env = {
            "ENABLE_UNIVERSAL_LLM_HIERARCHY": "0",
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_PROVIDER_RELIABILITY_HARDENING": "1",
            "ENABLE_GEMINI_TRANSIENT_MODEL_FALLBACK": "0",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT": "1",
            "ENABLE_CLOUDFLARE_ASSESSMENT_TAIL_BUDGET": "1",
            "GROQ_MODEL": "openai/gpt-oss-120b",
        }
        self.enterContext(patch.dict(os.environ, self.env, clear=False))
        self.gemini = self.enterContext(
            patch("api.services.gemini_client", Mock())
        )
        quota = RuntimeError("synthetic Gemini unavailable")
        quota.code = 402
        self.gemini.models.generate_content.side_effect = quota

        self.groq = self.enterContext(
            patch("api.services.groq_client", Mock())
        )
        self.groq_call = (
            self.groq.with_options.return_value.chat.completions.create
        )
        self.groq_call.side_effect = self._groq_response

        self.chunk_prompts = []
        self.generate = self.enterContext(patch(
            "api.verification.cloudflare_pilot.generate_evaluation_json",
            side_effect=self._cloudflare_response,
        ))

    def _cloudflare_response(self, system, prompt, **kwargs):
        self.chunk_prompts.append(prompt)
        return response_for(prompt)

    def _groq_response(self, **kwargs):
        prompt = kwargs["messages"][1]["content"]
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=response_for(prompt)),
        )])

    def _call(self, original, candidate):
        return call_llm_with_fallback(
            SYSTEM,
            original,
            operation=ASSESSMENT_OPERATION,
            cloudflare_assessment_user_prompt=candidate,
        )

    def test_flag_is_explicit_and_requires_hardening(self):
        self.assertTrue(cloudflare_assessment_tail_budget_enabled())
        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_ASSESSMENT_TAIL_BUDGET": "0",
        }, clear=False):
            self.assertFalse(cloudflare_assessment_tail_budget_enabled())
        with patch.dict(os.environ, {
            "ENABLE_PROVIDER_RELIABILITY_HARDENING": "0",
        }, clear=False):
            self.assertFalse(cloudflare_assessment_tail_budget_enabled())

    def test_degraded_cloudflare_path_reduces_three_chunks_to_two(self):
        original = make_prompt(10)
        candidate = subset_prompt(original, range(8))

        with llm_provider_scope(), patch(
            "api.services.record_llm_provider_call",
        ) as record:
            result = json.loads(self._call(original, candidate))

        self.assertEqual(len(self.chunk_prompts), 2)
        self.assertEqual([len(keys(prompt)) for prompt in self.chunk_prompts], [4, 4])
        self.assertEqual(
            [row["key"] for row in result["assessments"]],
            [f"item_{index}" for index in range(8)],
        )
        self.groq_call.assert_not_called()
        cloudflare_call = record.call_args_list[-1]
        self.assertEqual(cloudflare_call.args[1], "cloudflare")
        self.assertEqual(cloudflare_call.args[4], "success")
        metadata = cloudflare_call.kwargs["metadata"]
        self.assertTrue(metadata["assessment_tail_budget_applied"])
        self.assertEqual(metadata["assessment_items_original"], 10)
        self.assertEqual(metadata["assessment_items_selected"], 8)
        self.assertEqual(metadata["assessment_chunks_attempted"], 2)

    def test_flag_off_preserves_original_three_chunk_cloudflare_behavior(self):
        original = make_prompt(10)
        candidate = subset_prompt(original, range(8))

        with patch.dict(os.environ, {
            "ENABLE_CLOUDFLARE_ASSESSMENT_TAIL_BUDGET": "0",
        }, clear=False), llm_provider_scope():
            result = json.loads(self._call(original, candidate))

        self.assertEqual(len(self.chunk_prompts), 3)
        self.assertEqual(
            [len(keys(prompt)) for prompt in self.chunk_prompts],
            [4, 4, 2],
        )
        self.assertEqual(len(result["assessments"]), 10)

    def test_healthy_gemini_receives_full_original_batch(self):
        original = make_prompt(10)
        candidate = subset_prompt(original, range(8))
        self.gemini.models.generate_content.side_effect = None
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=response_for(original),
        )

        with llm_provider_scope():
            result = json.loads(self._call(original, candidate))

        self.assertEqual(len(result["assessments"]), 10)
        self.assertEqual(
            self.gemini.models.generate_content.call_args.kwargs["contents"],
            original,
        )
        self.generate.assert_not_called()
        self.groq_call.assert_not_called()

    def test_cloudflare_failure_falls_back_to_full_original_groq_batch(self):
        original = make_prompt(10)
        candidate = subset_prompt(original, range(8))
        self.generate.side_effect = CloudflareEvaluationError(
            "TRANSPORT_ReadTimeout"
        )

        with llm_provider_scope():
            result = json.loads(self._call(original, candidate))

        self.assertEqual(len(result["assessments"]), 10)
        self.groq_call.assert_called_once()
        self.assertEqual(
            self.groq_call.call_args.kwargs["messages"][1]["content"],
            original,
        )


class CloudflareAssessmentTailParsingTests(SimpleTestCase):
    def test_subset_response_leaves_deferred_items_unavailable(self):
        items = [evidence_item() for _ in range(10)]
        selected_ids = tuple(item.evidence_link_id for item in items[:8])
        candidate = subset_prompt(make_prompt(10), range(8))

        with patch(
            "api.verification.evidence_assessment.call_llm_with_fallback",
            return_value=response_for(candidate),
        ) as provider:
            assessments = assess_reasoning_evidence_batch_against_claim(
                "A verifiable public claim.",
                items,
                cloudflare_fallback_evidence_link_ids=selected_ids,
            )

        self.assertEqual(len(assessments), 10)
        self.assertTrue(all(
            assessment.stance == VerificationEvidence.Stance.SUPPORTS
            for assessment in assessments[:8]
        ))
        self.assertTrue(all(
            assessment.stance == VerificationEvidence.Stance.UNKNOWN
            and assessment.relevance_score is None
            and assessment.directness_score is None
            for assessment in assessments[8:]
        ))
        provider_kwargs = provider.call_args.kwargs
        self.assertIn("cloudflare_assessment_user_prompt", provider_kwargs)
        self.assertEqual(
            keys(provider_kwargs["cloudflare_assessment_user_prompt"]),
            [f"item_{index}" for index in range(8)],
        )
