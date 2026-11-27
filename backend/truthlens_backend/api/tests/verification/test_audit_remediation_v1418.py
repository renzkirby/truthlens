import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import services
from api.verification.cloudflare_pilot import validate_pilot_response
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


def _item(
    evidence_id,
    *,
    title="",
    content="",
    stance="REFUTES",
    relevance=0.95,
    directness=0.95,
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


class VerificationAuditRemediationV1418Tests(SimpleTestCase):
    def setUp(self):
        self.initial_fake = {
            "reasoning": "Assessed evidence contradicts the submitted proposition.",
            "verdict": "FAKE",
            "summary": "The submitted proposition is contradicted by the evidence.",
            "confidence_score": 90,
            "score_context": "Direct assessed evidence contradicts the claim.",
            "contextual_basis_kind": "NONE",
            "contextual_basis_evidence_ids": [],
        }

    def test_v1418_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.18")

    def test_nonmedia_claim_shape_gate_accepts_only_targeted_relationships(self):
        self.assertTrue(services._claim_has_nonmedia_relationship_shape(
            "Divorce was legalized after the House passed an absolute divorce bill."
        ))
        self.assertTrue(services._claim_has_nonmedia_relationship_shape(
            "₱4.1 trillion of the national budget was released to the president."
        ))
        self.assertFalse(services._claim_has_nonmedia_relationship_shape(
            "The House did not approve the bill."
        ))
        self.assertFalse(services._claim_has_nonmedia_relationship_shape(
            "The president was released to police custody."
        ))
        self.assertFalse(services._claim_has_nonmedia_relationship_shape(
            "The attributed quotation was fabricated."
        ))

    def test_legal_status_correction_can_prequalify_one_strong_refutation(self):
        evidence_id = "11111111-1111-1111-1111-111111111111"
        groups = [_group(_item(
            evidence_id,
            content=(
                "Divorce remains illegal in the country. The House approved "
                "House Bill No. 9349 on third reading, but the Senate failed "
                "to act before the Congress ended."
            ),
            relevance=0.97,
            directness=0.94,
        ))]

        self.assertEqual(
            services._qualified_nonmedia_relationship_basis_ids(groups),
            (evidence_id,),
        )

    def test_transfer_recipient_correction_can_prequalify_one_strong_refutation(self):
        evidence_id = "22222222-2222-2222-2222-222222222222"
        groups = [_group(_item(
            evidence_id,
            content=(
                "The Department released 64.9% of the 2025 budget, but these "
                "funds went to various government agencies, not the president."
            ),
            relevance=1.0,
            directness=1.0,
        ))]

        self.assertEqual(
            services._qualified_nonmedia_relationship_basis_ids(groups),
            (evidence_id,),
        )

    def test_nonmedia_qualifier_is_body_only_refutes_only_and_quality_gated(self):
        title_only = _item(
            "33333333-3333-3333-3333-333333333333",
            title="MISLEADING: Bill approval did not legalize divorce",
            content="The alleged legal change was fabricated.",
        )
        context_only = _item(
            "44444444-4444-4444-4444-444444444444",
            content=(
                "Divorce remains illegal. The House approved the bill on "
                "third reading."
            ),
            stance="CONTEXT",
        )
        weak = _item(
            "55555555-5555-5555-5555-555555555555",
            content=(
                "The Department released part of the budget, but the funds "
                "went to government agencies, not the named person."
            ),
            relevance=0.84,
            directness=0.99,
        )

        self.assertEqual(
            services._qualified_nonmedia_relationship_basis_ids(
                [_group(title_only, context_only, weak)]
            ),
            (),
        )

    def test_generic_misleading_false_or_context_words_do_not_prequalify(self):
        item = _item(
            "66666666-6666-6666-6666-666666666666",
            content=(
                "The post is misleading and false because important context "
                "was omitted. The attributed quotation was fabricated."
            ),
            relevance=1.0,
            directness=1.0,
        )

        self.assertFalse(
            services._text_has_qualified_nonmedia_relationship_correction(
                item.content
            )
        )
        self.assertEqual(
            services._qualified_nonmedia_relationship_basis_ids([_group(item)]),
            (),
        )

    def test_valid_nonmedia_partial_truth_uses_only_prequalified_basis(self):
        evidence_id = "77777777-7777-7777-7777-777777777777"
        groups = [_group(_item(
            evidence_id,
            content=(
                "Divorce remains illegal. The House approved House Bill No. "
                "9349, but the remaining legislative steps were not completed."
            ),
            relevance=0.97,
            directness=0.94,
        ))]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "PARTIAL_TRUTH",
            "basis_evidence_ids": [evidence_id],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "Divorce became legal after the House passed the bill.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_kind"], "PARTIAL_TRUTH")
        self.assertEqual(result["contextual_basis_evidence_ids"], [evidence_id])
        audit_prompt = provider.call_args_list[1].args[1]
        self.assertIn("<eligible_relationship_basis_ids>", audit_prompt)
        self.assertIn(evidence_id, audit_prompt)

    def test_nonmedia_audit_rejects_freeform_extra_fields(self):
        evidence_id = "7f7f7f7f-7777-7777-7777-777777777777"
        groups = [_group(_item(
            evidence_id,
            content=(
                "Divorce remains illegal. The House approved House Bill No. "
                "9349, but the remaining legislative steps were not completed."
            ),
            relevance=0.97,
            directness=0.94,
        ))]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "PARTIAL_TRUTH",
            "basis_evidence_ids": [evidence_id],
            "reasoning": "Provider-authored factual prose must not be accepted here.",
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ):
            result = services.evaluate_claim_with_persisted_evidence(
                "Divorce became legal after the House passed the bill.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)

    def test_nonmedia_audit_rejects_unqualified_visible_basis_id(self):
        qualified_id = "88888888-8888-8888-8888-888888888888"
        unrelated_id = "99999999-9999-9999-9999-999999999999"
        groups = [_group(
            _item(
                qualified_id,
                content=(
                    "The Department released 64.9% of the budget, but these "
                    "funds went to government agencies, not the president."
                ),
                relevance=1.0,
                directness=1.0,
            ),
            _item(
                unrelated_id,
                content="The attributed quotation was fabricated and never said.",
                relevance=1.0,
                directness=1.0,
            ),
        )]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "PARTIAL_TRUTH",
            "basis_evidence_ids": [unrelated_id],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ):
            result = services.evaluate_claim_with_persisted_evidence(
                "The released funds went to the president.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

    def test_nonmedia_audit_rejects_false_context_basis_kind(self):
        evidence_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        groups = [_group(_item(
            evidence_id,
            content=(
                "The Department released 64.9% of the budget, but these funds "
                "went to government agencies, not the president."
            ),
            relevance=1.0,
            directness=1.0,
        ))]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "FALSE_CONTEXT",
            "basis_evidence_ids": [evidence_id],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ):
            result = services.evaluate_claim_with_persisted_evidence(
                "The released funds went to the president.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["confidence_score"], 0)

    def test_fabricated_core_remains_fake_after_nonmedia_audit(self):
        evidence_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        groups = [_group(_item(
            evidence_id,
            content=(
                "The House approved the bill, but the claimed separate policy "
                "remains illegal."
            ),
            relevance=0.95,
            directness=0.95,
        ))]
        audited = {
            "relationship": "FABRICATED_CORE",
            "basis_kind": "NONE",
            "basis_evidence_ids": [],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "The official invented action occurred.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["verdict"], "FAKE")
        self.assertEqual(result["contextual_basis_kind"], "NONE")

    def test_legal_background_does_not_open_audit_for_simple_polarity_reversal(self):
        groups = [_group(_item(
            "bcbcbcbc-bcbc-bcbc-bcbc-bcbcbcbcbcbc",
            content=(
                "Divorce remains illegal. The House approved House Bill No. "
                "9349 on third reading."
            ),
            relevance=1.0,
            directness=1.0,
        ))]

        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.initial_fake),
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "The House did not approve the bill.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 1)
        self.assertEqual(result["verdict"], "FAKE")

    def test_ordinary_fabricated_claim_keeps_single_main_evaluator_call(self):
        groups = [_group(_item(
            "cccccccc-cccc-cccc-cccc-cccccccccccc",
            content="The attributed quotation was fabricated and never said.",
            relevance=1.0,
            directness=1.0,
        ))]

        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.initial_fake),
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "The official said the invented quotation.",
                "Persisted assessed evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 1)
        self.assertEqual(result["verdict"], "FAKE")

    def test_cloudflare_contract_restricts_nonmedia_basis_to_prequalified_ids(self):
        qualified_id = "dddddddd-dddd-dddd-dddd-dddddddddddd"
        visible_but_unqualified_id = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
        prompt = (
            "<eligible_relationship_basis_ids>"
            f"{json.dumps([qualified_id])}"
            "</eligible_relationship_basis_ids>"
            "<assessed_candidates>"
            f"{json.dumps([{'evidence_id': qualified_id}, {'evidence_id': visible_but_unqualified_id}])}"
            "</assessed_candidates>"
        )
        accepted = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "PARTIAL_TRUTH",
            "basis_evidence_ids": [qualified_id],
        }
        rejected = {
            **accepted,
            "basis_evidence_ids": [visible_but_unqualified_id],
        }

        self.assertTrue(validate_pilot_response(
            "structured_misleading_audit",
            json.dumps(accepted),
            prompt,
        ))
        self.assertFalse(validate_pilot_response(
            "structured_misleading_audit",
            json.dumps(rejected),
            prompt,
        ))
        wrong_kind = {
            **accepted,
            "basis_kind": "FALSE_CONTEXT",
        }
        extra_field = {
            **accepted,
            "reasoning": "Provider-authored prose is not part of this contract.",
        }
        self.assertFalse(validate_pilot_response(
            "structured_misleading_audit",
            json.dumps(wrong_kind),
            prompt,
        ))
        self.assertFalse(validate_pilot_response(
            "structured_misleading_audit",
            json.dumps(extra_field),
            prompt,
        ))
