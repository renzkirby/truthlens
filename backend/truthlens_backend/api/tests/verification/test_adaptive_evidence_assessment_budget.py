from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase

from api import tasks
from api.models import VerificationEvidence


def _item(*, role=VerificationEvidence.EvidenceRole.SECONDARY):
    return SimpleNamespace(
        evidence_link_id=uuid4(),
        evidence_role=role,
        stance=VerificationEvidence.Stance.UNKNOWN,
        relevance_score=None,
        directness_score=None,
    )


def _group(*items):
    return SimpleNamespace(
        identity_id=uuid4(),
        evidence=tuple(items),
    )


def _assessment():
    return SimpleNamespace(
        stance=VerificationEvidence.Stance.SUPPORTS,
        relevance_score=0.95,
        directness_score=0.95,
    )


class AdaptiveEvidenceAssessmentBudgetTests(SimpleTestCase):
    def _run(self, groups, *, enabled=True):
        persisted = []

        def assess(_claim_text, items, **_kwargs):
            return [_assessment() for _item_value in items]

        def persist(items, assessments):
            persisted.extend(items)
            self.assertEqual(len(items), len(assessments))
            return [
                SimpleNamespace(error=None, persisted=True)
                for _item_value in items
            ]

        env = {
            tasks.EVIDENCE_ASSESSMENT_BUDGET_FLAG: "1" if enabled else "0",
        }
        with (
            patch.dict("os.environ", env, clear=False),
            patch(
                "api.tasks.assess_reasoning_evidence_batch_against_claim",
                side_effect=assess,
            ) as assess_batch,
            patch(
                "api.tasks.persist_evidence_assessments_batch",
                side_effect=persist,
            ) as persist_batch,
            patch("api.tasks._log_stage") as log_stage,
        ):
            tasks._assess_and_persist_reasoning_evidence(
                "The submitted claim.",
                groups,
                uuid4(),
                stage_prefix="tavily",
                material_scope_hardening=True,
            )

        batch_calls = [
            call
            for call in log_stage.call_args_list
            if call.args[1] == "tavily_evidence_assessment_batch"
        ]
        self.assertEqual(len(batch_calls), 1)
        return assess_batch, persist_batch, persisted, batch_calls[0]

    def test_flag_off_preserves_existing_single_batch_behavior(self):
        groups = [_group(_item()) for _ in range(6)]

        assess, persist_batch, persisted, batch_call = self._run(
            groups,
            enabled=False,
        )

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 6)
        persist_batch.assert_called_once()
        self.assertEqual(len(persisted), 6)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["assessment_waves"], 1)
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)

    def test_flag_on_does_not_split_batch_when_nothing_is_reduced(self):
        groups = [_group(_item()) for _ in range(7)]

        assess, _persist_batch, persisted, batch_call = self._run(groups)

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 7)
        self.assertEqual(len(persisted), 7)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["selected_items"], 7)
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)
        self.assertEqual(batch_call.kwargs["assessment_waves"], 1)
        self.assertFalse(batch_call.kwargs["early_stopped"])

    def test_duplicate_records_under_ceiling_still_use_one_full_batch(self):
        groups = [
            _group(_item(), _item()),
            _group(_item(), _item()),
            _group(_item()),
            _group(_item()),
        ]

        assess, _persist_batch, persisted, batch_call = self._run(groups)

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 6)
        self.assertEqual(len(persisted), 6)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)

    def test_nine_distinct_identities_fall_back_to_full_assessment(self):
        groups = [_group(_item()) for _ in range(9)]

        assess, _persist_batch, persisted, batch_call = self._run(groups)

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 9)
        self.assertEqual(len(persisted), 9)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)

    def test_non_secondary_evidence_never_uses_adaptive_budget(self):
        groups = [
            _group(_item(role=VerificationEvidence.EvidenceRole.FACT_CHECK))
            for _ in range(9)
        ]

        assess, _persist_batch, persisted, batch_call = self._run(groups)

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 9)
        self.assertEqual(len(persisted), 9)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])

    def test_ninth_duplicate_is_deferred_in_one_call_without_dropping_identity(self):
        groups = [_group(_item()) for _ in range(7)]
        groups.append(_group(_item(), _item()))

        assess, _persist_batch, persisted, batch_call = self._run(groups)

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 8)
        self.assertEqual(len(persisted), 8)
        persisted_ids = {item.evidence_link_id for item in persisted}
        self.assertTrue(all(
            group.evidence[0].evidence_link_id in persisted_ids
            for group in groups
        ))
        self.assertTrue(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["selected_items"], 8)
        self.assertEqual(batch_call.kwargs["deferred_items"], 1)
        self.assertEqual(batch_call.kwargs["assessment_waves"], 1)
        self.assertFalse(batch_call.kwargs["early_stopped"])

    def test_ten_records_across_five_identities_reduce_to_eight_in_one_call(self):
        groups = [_group(_item(), _item()) for _ in range(5)]

        assess, _persist_batch, persisted, batch_call = self._run(groups)

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 8)
        self.assertEqual(len(persisted), 8)
        persisted_ids = {item.evidence_link_id for item in persisted}
        self.assertTrue(all(
            group.evidence[0].evidence_link_id in persisted_ids
            for group in groups
        ))
        self.assertTrue(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["selected_items"], 8)
        self.assertEqual(batch_call.kwargs["deferred_items"], 2)
        self.assertEqual(batch_call.kwargs["assessment_waves"], 1)
