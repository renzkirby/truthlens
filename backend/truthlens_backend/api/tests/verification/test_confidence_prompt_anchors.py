"""Regression checks for fixed-confidence anchoring in verdict prompts."""

import ast
from pathlib import Path

from django.test import SimpleTestCase


SERVICES_PATH = Path(__file__).resolve().parents[2] / "services.py"


class VerdictConfidencePromptAnchorTests(SimpleTestCase):
    PROMPT_FUNCTIONS = {
        "evaluate_image_claim_with_gfc",
        "evaluate_image_claim_with_tavily",
        "build_persisted_evidence_prompt",
        "evaluate_url_claim_with_gfc",
        "evaluate_url_claim_with_tavily",
    }

    def _verdict_prompt_source(self):
        source = SERVICES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        segments = [
            ast.get_source_segment(source, node) or ""
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in self.PROMPT_FUNCTIONS
        ]
        self.assertEqual(len(segments), len(self.PROMPT_FUNCTIONS))
        return "\n".join(segments)

    def test_verdict_templates_do_not_anchor_at_95_percent(self):
        source = self._verdict_prompt_source()
        self.assertNotIn('"confidence_score": 95', source)
        self.assertEqual(
            source.count(
                '"confidence_score": <evidence_based_numeric_percentage_0_to_100>'
            ),
            5,
        )

    def test_verdict_templates_require_numeric_evidence_based_confidence(self):
        source = self._verdict_prompt_source()
        self.assertEqual(
            source.count(
                "The confidence_score placeholder in the field template "
                "must be replaced with a JSON number."
            ),
            5,
        )
        self.assertEqual(
            source.count(
                "unresolved material assertions or conflicts must reduce "
                "confidence."
            ),
            5,
        )

    def test_all_primary_verdict_prompts_apply_fake_misleading_precedence(self):
        source = self._verdict_prompt_source()
        self.assertEqual(
            source.count("_with_fake_misleading_precedence_rules("),
            5,
        )

    def test_fake_misleading_precedence_has_overfilter_and_abstention_guards(self):
        source = SERVICES_PATH.read_text(encoding="utf-8")
        required_rules = (
            "Do not choose MISLEADING merely because a real person",
            "a substantial genuine factual component of the same submitted proposition",
            "must both be established by the supplied evidence",
            "does not convert a separate invented quotation",
            "choose UNVERIFIED rather than guessing",
        )
        for rule in required_rules:
            with self.subTest(rule=rule):
                self.assertIn(rule, source)

    def test_materiality_audit_does_not_receive_fake_misleading_precedence_block(self):
        source = SERVICES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        audit_source = next(
            ast.get_source_segment(source, node) or ""
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_audit_misleading_materiality"
        )
        self.assertNotIn(
            "_with_fake_misleading_precedence_rules(",
            audit_source,
        )
