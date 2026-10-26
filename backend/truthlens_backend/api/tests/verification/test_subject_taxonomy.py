"""Pure/offline tests for the *proposed* taxonomy; no AI, network, or DB."""

import ast
import json
from pathlib import Path
from unittest import TestCase

from api.verification.subject_taxonomy import (
    CAMPUS_CONTEXT_CODE,
    CAMPUS_CONTEXT_STATES,
    PUBLIC_CATEGORIES,
    SUBJECT_RULES,
    TAXONOMY_VERSION,
    public_category_for_classification,
    public_category_for_code,
    public_category_for_domains,
    public_category_for_primary_subject,
)


_API_DIR = Path(__file__).resolve().parents[2]
_REPO_DIR = Path(__file__).resolve().parents[5]
_EXAMPLES = _REPO_DIR / "docs" / "claim_taxonomy" / "examples_v1.json"


def current_authoritative_subject_codes():
    """Read current policy vocabulary without importing Django or providers."""
    tree = ast.parse((_API_DIR / "verification_domain_policy.py").read_text(encoding="utf-8"))
    values = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VERIFICATION_DOMAINS" for t in node.targets)
    ]
    if len(values) != 1:
        raise AssertionError("Expected one static authoritative subject list")
    return {code for code, _label in values[0]}


class ProposedSubjectTaxonomyTests(TestCase):
    def test_vocabulary_matches_existing_policy_without_new_authority(self):
        self.assertEqual(TAXONOMY_VERSION, "claim-subject-v1-draft")
        self.assertEqual(len(SUBJECT_RULES), 12)
        self.assertEqual(set(SUBJECT_RULES), current_authoritative_subject_codes())
        self.assertNotIn(CAMPUS_CONTEXT_CODE, SUBJECT_RULES)

    def test_eight_public_groups_cover_each_subject_once(self):
        self.assertEqual(len(PUBLIC_CATEGORIES), 8)
        group_ids = [g.code for g in PUBLIC_CATEGORIES]
        self.assertEqual(len(set(group_ids)), len(group_ids))
        domains = [d for g in PUBLIC_CATEGORIES for d in g.domains]
        self.assertEqual(len(domains), len(set(domains)))
        self.assertEqual(set(domains), set(SUBJECT_RULES))
        self.assertNotIn(CAMPUS_CONTEXT_CODE, group_ids)

    def test_rules_are_readable_and_include_exclusions(self):
        for code, rule in SUBJECT_RULES.items():
            with self.subTest(code=code):
                self.assertGreaterEqual(len(rule.definition), 25)
                self.assertGreaterEqual(len(rule.include), 2)
                self.assertGreaterEqual(len(rule.do_not_infer), 2)
                self.assertTrue(all(bool(s.strip()) for s in (*rule.include, *rule.do_not_infer)))

    def test_primary_subject_must_be_explicit_and_supported(self):
        self.assertEqual(
            public_category_for_primary_subject("ELECTIONS").label,
            "Politics, Governance & Law",
        )
        self.assertEqual(public_category_for_primary_subject("EDUCATION").label, "Education")
        self.assertIsNone(public_category_for_primary_subject(None))
        self.assertIsNone(public_category_for_primary_subject("CAMPUS_AFFAIRS"))
        self.assertIsNone(public_category_for_primary_subject(["EDUCATION", "ELECTIONS"]))
        self.assertIsNone(public_category_for_primary_subject("UNKNOWN"))

    def test_public_category_helpers_do_not_infer_multidomain_primary_subject(self):
        education = public_category_for_domains(["EDUCATION"])
        self.assertEqual(education.code, "EDUCATION")
        self.assertEqual(education.label, "Education")
        self.assertIsNone(public_category_for_domains(["ELECTIONS", "TECHNOLOGY"]))
        self.assertIsNone(public_category_for_domains([]))
        self.assertIsNone(public_category_for_domains(None))

        governance = public_category_for_code("POLITICS_GOVERNMENT_LAW")
        self.assertEqual(governance.label, "Politics, Governance & Law")
        self.assertIsNone(public_category_for_code("CAMPUS_AFFAIRS"))
        self.assertIsNone(public_category_for_code("UNKNOWN"))

    def test_classification_projection_prefers_explicit_primary_subject(self):
        class PersistedClassification:
            domains = ["ELECTIONS", "TECHNOLOGY"]
            primary_subject = "TECHNOLOGY"

        category = public_category_for_classification(PersistedClassification())
        self.assertEqual(category.code, "SCIENCE_TECHNOLOGY")

        class LegacySingleDomain:
            domains = ["EDUCATION"]
            primary_subject = None

        legacy = public_category_for_classification(LegacySingleDomain())
        self.assertEqual(legacy.code, "EDUCATION")

        class LegacyMultiDomain:
            domains = ["ELECTIONS", "TECHNOLOGY"]
            primary_subject = None

        self.assertIsNone(public_category_for_classification(LegacyMultiDomain()))

    def test_examples_cover_every_code_and_campus_boundaries(self):
        rows = json.loads(_EXAMPLES.read_text(encoding="utf-8"))
        self.assertEqual(rows["schema_version"], 1)
        examples = rows["examples"]
        self.assertGreaterEqual(len(examples), 18)
        ids = [x["id"] for x in examples]
        self.assertEqual(len(ids), len(set(ids)))
        observed = set()
        states = set()
        for x in examples:
            with self.subTest(id=x["id"]):
                self.assertEqual(
                    set(x),
                    {"id", "claim_text", "primary_subject", "required_subjects", "campus_state", "institution_hint", "reason"},
                )
                self.assertGreaterEqual(len(x["claim_text"]), 20)
                self.assertTrue(x["reason"].strip())
                self.assertIn(x["campus_state"], CAMPUS_CONTEXT_STATES)
                states.add(x["campus_state"])
                self.assertTrue(isinstance(x["required_subjects"], list))
                self.assertEqual(len(x["required_subjects"]), len(set(x["required_subjects"])))
                self.assertLessEqual(len(x["required_subjects"]), 3)
                self.assertTrue(set(x["required_subjects"]).issubset(SUBJECT_RULES))
                if x["primary_subject"] is None:
                    self.assertEqual(x["required_subjects"], [])
                else:
                    self.assertIn(x["primary_subject"], x["required_subjects"])
                    observed.add(x["primary_subject"])
                if x["campus_state"] == "NOT_APPLICABLE":
                    self.assertIsNone(x["institution_hint"])
                if x["campus_state"] == "UNCERTAIN":
                    self.assertIsNone(x["institution_hint"])
        self.assertEqual(observed, set(SUBJECT_RULES))
        self.assertEqual(states, set(CAMPUS_CONTEXT_STATES))
        self.assertGreaterEqual(sum(x["campus_state"] == "CONFIRMED" for x in examples), 6)

    def test_multidomain_examples_keep_one_explicit_primary_public_category(self):
        examples = json.loads(_EXAMPLES.read_text(encoding="utf-8"))["examples"]
        multi = [x for x in examples if len(x["required_subjects"]) > 1]
        self.assertGreaterEqual(len(multi), 4)
        for item in multi:
            with self.subTest(id=item["id"]):
                self.assertIn(item["primary_subject"], item["required_subjects"])
                category = public_category_for_primary_subject(item["primary_subject"])
                self.assertIsNotNone(category)

        campaign_ai = next(x for x in multi if x["id"] == "cross_campaign_ai")
        self.assertEqual(campaign_ai["required_subjects"], ["ELECTIONS", "TECHNOLOGY"])
        self.assertEqual(
            public_category_for_primary_subject(campaign_ai["primary_subject"]).label,
            "Politics, Governance & Law",
        )

    def test_campus_flood_examples_distinguish_school_decision_from_emergency(self):
        examples = {
            x["id"]: x for x in json.loads(_EXAMPLES.read_text(encoding="utf-8"))["examples"]
        }
        self.assertEqual(examples["campus_flood"]["primary_subject"], "EDUCATION")
        self.assertEqual(examples["campus_flood"]["required_subjects"], ["EDUCATION"])
        self.assertEqual(examples["campus_flood_evacuation"]["primary_subject"], "DISASTERS")
        self.assertEqual(examples["campus_flood_evacuation"]["required_subjects"], ["DISASTERS"])

    def test_campus_context_does_not_imply_education_or_fact_verdict(self):
        examples = json.loads(_EXAMPLES.read_text(encoding="utf-8"))["examples"]
        campus_subjects = {x["primary_subject"] for x in examples if x["campus_state"] == "CONFIRMED"}
        self.assertGreaterEqual(len(campus_subjects), 4)
        self.assertIn("ELECTIONS", campus_subjects)
        self.assertIn("SPORTS", campus_subjects)
        for item in examples:
            self.assertNotIn("truthfulness", item)
            self.assertNotIn("verdict", item)
            self.assertNotIn("institution_id", item)
