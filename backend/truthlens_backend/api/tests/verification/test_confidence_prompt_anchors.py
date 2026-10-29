"""Regression checks for fixed-confidence anchoring in verdict prompts."""

from pathlib import Path

from django.test import SimpleTestCase


SERVICES_PATH = Path(__file__).resolve().parents[2] / "services.py"


class VerdictConfidencePromptAnchorTests(SimpleTestCase):
    def test_verdict_templates_do_not_anchor_at_95_percent(self):
        source = SERVICES_PATH.read_text(encoding="utf-8")
        self.assertNotIn('"confidence_score": 95', source)
        self.assertEqual(
            source.count(
                '"confidence_score": <evidence_based_numeric_percentage_0_to_100>'
            ),
            5,
        )

    def test_verdict_templates_require_numeric_evidence_based_confidence(self):
        source = SERVICES_PATH.read_text(encoding="utf-8")
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
