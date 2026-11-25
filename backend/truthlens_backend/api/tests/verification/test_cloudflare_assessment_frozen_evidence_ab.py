import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from api.management.commands.compare_cloudflare_assessment_frozen_evidence import (
    _compare_frozen_arms,
)
from api.models import Claim, VerificationEvidence
from api.verification.evidence_assessment import EvidenceAssessment


def _assessment(stance, relevance=0.9, directness=0.8):
    if stance == VerificationEvidence.Stance.UNKNOWN:
        return EvidenceAssessment(
            stance=stance,
            relevance_score=None,
            directness_score=None,
        )
    return EvidenceAssessment(
        stance=stance,
        relevance_score=relevance,
        directness_score=directness,
    )


def _item(role=VerificationEvidence.EvidenceRole.SECONDARY):
    return SimpleNamespace(
        evidence_link_id=uuid4(),
        evidence_source_id=uuid4(),
        evidence_role=role,
        stance=VerificationEvidence.Stance.UNKNOWN,
        relevance_score=None,
        directness_score=None,
        content="Frozen evidence passage.",
    )


def _groups(item_counts=(2, 2, 2, 2, 2)):
    return [
        (uuid4(), tuple(_item() for _ in range(count)))
        for count in item_counts
    ]


def _arm(assessments, *, budgeted=False, chunks=3, applied=False):
    return {
        "budgeted": budgeted,
        "duration_ms": 1000 if not budgeted else 700,
        "assessments": assessments,
        "provider_events": [],
        "cloudflare_success": True,
        "cloudflare_chunks": chunks,
        "tail_budget_applied": applied,
        "assessment_items_original": 10 if applied else None,
        "assessment_items_selected": 8 if applied else None,
        "groq_attempts": 0,
    }


class FrozenEvidenceComparisonTests(SimpleTestCase):
    def test_redundant_context_loss_can_pass_when_decisive_topology_is_preserved(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        selected_ids = tuple(item.evidence_link_id for item in items[:8])

        baseline_assessments = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        baseline_assessments[1] = _assessment(
            VerificationEvidence.Stance.CONTEXT
        )

        budgeted_assessments = list(baseline_assessments)
        budgeted_assessments[1] = _assessment(
            VerificationEvidence.Stance.UNKNOWN
        )

        baseline = _arm(baseline_assessments)
        budgeted = _arm(
            budgeted_assessments,
            budgeted=True,
            chunks=2,
            applied=True,
        )

        result = _compare_frozen_arms(
            groups,
            baseline,
            budgeted,
            selected_ids,
        )

        self.assertEqual(result["quality_gate"], "PASS")
        self.assertTrue(result["identity_coverage_preserved"])
        self.assertTrue(result["decisive_identity_topology_match"])
        self.assertTrue(result["context_topology_changed"])

    def test_losing_unique_refutation_requires_review(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        selected_ids = tuple(item.evidence_link_id for item in items[:8])

        baseline_assessments = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        baseline_assessments[9] = _assessment(
            VerificationEvidence.Stance.REFUTES
        )

        budgeted_assessments = list(baseline_assessments)
        budgeted_assessments[9] = _assessment(
            VerificationEvidence.Stance.UNKNOWN
        )

        result = _compare_frozen_arms(
            groups,
            _arm(baseline_assessments),
            _arm(
                budgeted_assessments,
                budgeted=True,
                chunks=2,
                applied=True,
            ),
            selected_ids,
        )

        self.assertEqual(result["quality_gate"], "REVIEW")
        self.assertIn(
            "DECISIVE_IDENTITY_TOPOLOGY_CHANGED",
            result["review_reasons"],
        )

    def test_selected_item_stance_change_requires_review(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        selected_ids = tuple(item.evidence_link_id for item in items[:8])

        baseline_assessments = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        budgeted_assessments = list(baseline_assessments)
        budgeted_assessments[0] = _assessment(
            VerificationEvidence.Stance.CONTEXT
        )

        result = _compare_frozen_arms(
            groups,
            _arm(baseline_assessments),
            _arm(
                budgeted_assessments,
                budgeted=True,
                chunks=2,
                applied=True,
            ),
            selected_ids,
        )

        self.assertEqual(result["quality_gate"], "REVIEW")
        self.assertIn(
            "SELECTED_ITEM_STANCE_CHANGED",
            result["review_reasons"],
        )

    def test_provider_or_chunk_contamination_is_invalid(self):
        groups = _groups()
        items = [item for _identity_id, members in groups for item in members]
        selected_ids = tuple(item.evidence_link_id for item in items[:8])
        assessments = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in items
        ]
        baseline = _arm(assessments, chunks=2)
        baseline["groq_attempts"] = 1

        result = _compare_frozen_arms(
            groups,
            baseline,
            _arm(
                assessments,
                budgeted=True,
                chunks=2,
                applied=True,
            ),
            selected_ids,
        )

        self.assertEqual(result["quality_gate"], "INVALID")
        self.assertIn(
            "BASELINE_NOT_THREE_CHUNKS",
            result["review_reasons"],
        )
        self.assertIn(
            "BASELINE_GROQ_REACHED",
            result["review_reasons"],
        )


class FrozenEvidenceABCommandTests(TestCase):
    @override_settings(APP_ENV="production", DEBUG=False)
    def test_command_is_development_only(self):
        with self.assertRaises(CommandError):
            call_command(
                "compare_cloudflare_assessment_frozen_evidence",
                claims=["A test claim."],
            )

    @override_settings(APP_ENV="development", DEBUG=True)
    def test_retrieval_runs_once_and_both_arms_share_frozen_snapshot(self):
        groups = [
            SimpleNamespace(
                identity_kind="URL",
                identity_id=uuid4(),
                evidence=tuple(_item() for _ in range(2)),
            )
            for _ in range(5)
        ]
        eligible_items = [
            item for group in groups for item in group.evidence
        ]
        baseline_assessments = [
            _assessment(VerificationEvidence.Stance.SUPPORTS)
            for _ in eligible_items
        ]
        budgeted_assessments = list(baseline_assessments)
        # The production selector chooses eight of ten across these five
        # identities, so the two deferred records remain unavailable.
        for index in (8, 9):
            budgeted_assessments[index] = _assessment(
                VerificationEvidence.Stance.UNKNOWN
            )

        seen_item_ids = []

        def fake_arm(
            claim_text,
            evidence_items,
            *,
            budgeted,
            selected_ids,
            material_scope_hardening=True,
        ):
            seen_item_ids.append(
                tuple(item.evidence_link_id for item in evidence_items)
            )
            assessments = (
                budgeted_assessments if budgeted else baseline_assessments
            )
            return {
                "budgeted": budgeted,
                "duration_ms": 700 if budgeted else 1000,
                "assessments": assessments,
                "provider_events": [],
                "cloudflare_success": True,
                "cloudflare_chunks": 2 if budgeted else 3,
                "tail_budget_applied": budgeted,
                "assessment_items_original": 10 if budgeted else None,
                "assessment_items_selected": 8 if budgeted else None,
                "groq_attempts": 0,
            }

        before_claims = Claim.objects.count()
        output = io.StringIO()

        with (
            patch(
                "api.management.commands.compare_cloudflare_assessment_frozen_evidence."
                "tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": "A test claim.",
                    "search_query": "A test claim.",
                    "search_queries": ["A test claim."],
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_frozen_evidence."
                "tasks._retrieve_and_ingest_tavily_queries",
                return_value={"results": []},
            ) as retrieval,
            patch(
                "api.management.commands.compare_cloudflare_assessment_frozen_evidence."
                "load_reasoning_evidence_dossier_for_run",
                return_value=groups,
            ),
            patch(
                "api.management.commands.compare_cloudflare_assessment_frozen_evidence."
                "_run_assessment_arm",
                side_effect=fake_arm,
            ),
        ):
            call_command(
                "compare_cloudflare_assessment_frozen_evidence",
                claims=["A test claim."],
                json=True,
                stdout=output,
            )

        report = json.loads(output.getvalue())[0]
        retrieval.assert_called_once()
        self.assertEqual(len(seen_item_ids), 2)
        self.assertEqual(seen_item_ids[0], seen_item_ids[1])
        self.assertEqual(Claim.objects.count(), before_claims)
        self.assertTrue(report["database_isolated"])
        self.assertEqual(report["frozen_evidence"]["item_count"], 10)
        self.assertEqual(report["frozen_evidence"]["identity_count"], 5)
        self.assertEqual(report["quality_gate"], "PASS")
