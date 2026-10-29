"""Offline policy checks for the opt-in universal provider hierarchy."""

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_pilot import cloudflare_pilot_enabled
from api.verification.provider_hierarchy import hierarchy_enabled


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
            ):
                with self.subTest(operation=operation):
                    self.assertTrue(cloudflare_pilot_enabled(operation))
            for operation in (
                "claim_gate",
                "claim_equivalence",
                "fact_check_relevance",
                "gfc_evaluation",
                "tavily_evaluation",
                None,
            ):
                with self.subTest(operation=operation):
                    self.assertFalse(cloudflare_pilot_enabled(operation))
