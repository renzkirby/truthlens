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


class VerificationAuditRemediationV1417Tests(SimpleTestCase):
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

    def test_v1417_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.17")

    def test_evidence_context_trigger_is_narrow_and_quality_gated(self):
        contextual = _group(_item(
            "11111111-1111-1111-1111-111111111111",
            title="Circulating video of ceremony MISLEADS",
            content="The full video shows the earlier handshake before the shortened clip.",
        ))
        ordinary_false = _group(_item(
            "22222222-2222-2222-2222-222222222222",
            title="Fact check",
            content="The attributed statement was fabricated and did not occur.",
        ))
        weak_context = _group(_item(
            "33333333-3333-3333-3333-333333333333",
            title="Circulating video MISLEADS",
            content="The full video supplies additional context.",
            relevance=0.3,
            directness=0.3,
        ))

        self.assertTrue(
            services._evidence_needs_fake_false_context_audit([contextual])
        )
        self.assertFalse(
            services._evidence_needs_fake_false_context_audit([ordinary_false])
        )
        self.assertFalse(
            services._evidence_needs_fake_false_context_audit([weak_context])
        )

    def test_fake_can_open_relationship_audit_from_evidence_not_claim_words(self):
        evidence_id = "44444444-4444-4444-4444-444444444444"
        groups = [_group(_item(
            evidence_id,
            title="Circulating clip of commencement ceremony MISLEADS",
            content=(
                "The full video shows that the cadet had already greeted and "
                "shaken hands with the official before the shortened clip."
            ),
        ))]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "FALSE_CONTEXT",
            "basis_evidence_ids": [evidence_id],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "A cadet ignored the president during the commencement ceremony.",
                "Persisted evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_kind"], "FALSE_CONTEXT")
        self.assertEqual(result["contextual_basis_evidence_ids"], [evidence_id])

    def test_equivalent_false_signal_blocks_incidental_satire_provenance_override(self):
        false_id = "55555555-5555-5555-5555-555555555555"
        groups = [_group(_item(
            false_id,
            title="Fact check",
            content=(
                "Rating: False. The debunk discusses a related satire or parody "
                "storytelling element, but the submitted factual event did not occur."
            ),
        ))]

        with (
            patch(
                "api.services.call_llm_with_fallback",
                return_value=json.dumps(self.initial_fake),
            ) as provider,
            patch(
                "api.services._audit_persisted_satire_provenance",
            ) as satire_audit,
        ):
            result = services.evaluate_claim_with_persisted_evidence(
                "The athlete met the head of state after the tournament final.",
                "Persisted evidence.",
                official_false_evidence_ids=[false_id],
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 1)
        satire_audit.assert_not_called()
        self.assertEqual(result["verdict"], "FAKE")

    def test_false_and_misleading_taxonomies_share_one_relationship_audit(self):
        misleading_id = "66666666-6666-6666-6666-666666666666"
        false_id = "77777777-7777-7777-7777-777777777777"
        correction_id = "88888888-8888-8888-8888-888888888888"
        groups = [_group(
            _item(
                misleading_id,
                title="Structured fact check",
                content="Rating: Misleading. The claim overstates the legal effect.",
            ),
            _item(
                false_id,
                title="Second structured fact check",
                content="Rating: False. The claimed legal conclusion did not follow.",
            ),
            _item(
                correction_id,
                title="Legislative status",
                content=(
                    "The chamber passed the bill, but the proposal had not completed "
                    "the remaining steps required to become law."
                ),
                stance="CONTEXT",
            ),
        )]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "PARTIAL_TRUTH",
            "basis_evidence_ids": [correction_id],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            side_effect=[json.dumps(self.initial_fake), json.dumps(audited)],
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "The measure became law after one chamber passed the bill.",
                "Persisted evidence.",
                official_misleading_evidence_ids=[misleading_id],
                official_false_evidence_ids=[false_id],
                evidence_groups=groups,
            )

        self.assertEqual(result["verdict"], "MISLEADING")
        self.assertEqual(result["contextual_basis_evidence_ids"], [correction_id])
        second_prompt = provider.call_args_list[1].args[1]
        self.assertIn(misleading_id, second_prompt)
        self.assertIn(false_id, second_prompt)

    def test_structured_relationship_audit_rejects_unshown_basis_id(self):
        misleading_id = "99999999-9999-9999-9999-999999999999"
        context_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        groups = [_group(
            _item(
                misleading_id,
                title="Structured fact check",
                content="Rating: Misleading.",
            ),
            _item(
                context_id,
                title="Corrective report",
                content="The funds went to agencies and were not released to the named person.",
                stance="CONTEXT",
            ),
        )]
        audited = {
            "relationship": "MATERIAL_MISDESCRIPTION",
            "basis_kind": "FALSE_CONTEXT",
            "basis_evidence_ids": ["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"],
        }

        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(audited),
        ):
            result = services._audit_structured_misleading_signal(
                "The funds were released to the named person.",
                "Persisted evidence.",
                self.initial_fake,
                [misleading_id],
                groups,
            )

        self.assertEqual(result["verdict"], "UNVERIFIED")
        self.assertEqual(result["contextual_basis_evidence_ids"], [])

    def test_relationship_excerpt_keeps_late_corrective_passage(self):
        content = (
            ("Background information. " * 80)
            + "The funds went to government agencies and were not released to the president. "
            + ("Additional background. " * 80)
        )
        excerpt = services._relationship_audit_excerpt(content, max_chars=500)

        self.assertIn("not released to the president", excerpt)
        self.assertLessEqual(len(excerpt), 506)

    def test_ordinary_fake_does_not_gain_relationship_audit_call(self):
        evidence_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        groups = [_group(_item(
            evidence_id,
            title="Direct contradiction",
            content="The attributed quotation was fabricated and the speaker never said it.",
        ))]

        with patch(
            "api.services.call_llm_with_fallback",
            return_value=json.dumps(self.initial_fake),
        ) as provider:
            result = services.evaluate_claim_with_persisted_evidence(
                "The official said the invented quotation.",
                "Persisted evidence.",
                evidence_groups=groups,
            )

        self.assertEqual(provider.call_count, 1)
        self.assertEqual(result["verdict"], "FAKE")
