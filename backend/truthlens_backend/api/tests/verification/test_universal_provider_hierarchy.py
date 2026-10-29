"""Offline policy checks for the opt-in universal provider hierarchy."""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.verification.cloudflare_pilot import (cloudflare_pilot_enabled, validate_pilot_response)
from api.verification.provider_hierarchy import (
    hierarchy_enabled, requires_strict_stage_contract,
)


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
                "claim_equivalence",
                "fact_check_relevance",
                "gfc_evaluation",
                "tavily_evaluation",
            ):
                with self.subTest(operation=operation):
                    self.assertTrue(cloudflare_pilot_enabled(operation))
            for operation in (
                "claim_gate",
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
