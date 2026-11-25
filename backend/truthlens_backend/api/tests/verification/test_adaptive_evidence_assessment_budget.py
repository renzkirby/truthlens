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


def _assessment(
    stance=VerificationEvidence.Stance.SUPPORTS,
    relevance=0.95,
    directness=0.95,
):
    return SimpleNamespace(
        stance=stance,
        relevance_score=relevance,
        directness_score=directness,
    )


class AdaptiveEvidenceAssessmentBudgetTests(SimpleTestCase):
    def _run(self, groups, *, side_effect, enabled=True):
        persisted = []

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
                side_effect=side_effect,
            ) as assess,
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
        return assess, persist_batch, persisted, batch_calls[0]

    def test_flag_off_preserves_existing_single_batch_behavior(self):
        groups = [_group(_item()) for _ in range(6)]
        assessments = [_assessment() for _ in range(6)]

        assess, persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[assessments],
            enabled=False,
        )

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 6)
        persist_batch.assert_called_once()
        self.assertEqual(len(persisted), 6)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["assessment_waves"], 1)
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)

    def test_distinct_source_identities_force_second_wave(self):
        groups = [_group(_item()) for _ in range(6)]
        first = [_assessment() for _ in range(4)]
        second = [_assessment() for _ in range(2)]

        assess, _persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[first, second],
        )

        self.assertEqual(assess.call_count, 2)
        self.assertEqual(
            [len(call.args[1]) for call in assess.call_args_list],
            [4, 2],
        )
        self.assertEqual(len(persisted), 6)
        self.assertTrue(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["assessment_waves"], 2)
        self.assertFalse(batch_call.kwargs["early_stopped"])
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)

    def test_strong_first_wave_can_skip_only_same_identity_duplicates(self):
        groups = [
            _group(_item(), _item()),
            _group(_item(), _item()),
            _group(_item()),
            _group(_item()),
        ]
        first = [_assessment() for _ in range(4)]

        assess, _persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[first],
        )

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 4)
        self.assertEqual(len(persisted), 4)
        self.assertTrue(batch_call.kwargs["adaptive_budget"])
        self.assertTrue(batch_call.kwargs["early_stopped"])
        self.assertEqual(batch_call.kwargs["assessment_waves"], 1)
        self.assertEqual(batch_call.kwargs["deferred_items"], 2)

    def test_non_decisive_first_wave_assesses_same_identity_duplicates(self):
        groups = [
            _group(_item(), _item()),
            _group(_item(), _item()),
            _group(_item()),
            _group(_item()),
        ]
        first = [
            _assessment(),
            _assessment(),
            _assessment(VerificationEvidence.Stance.CONTEXT, 0.8, 0.1),
            _assessment(),
        ]
        second = [_assessment(), _assessment()]

        assess, _persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[first, second],
        )

        self.assertEqual(assess.call_count, 2)
        self.assertEqual(
            [len(call.args[1]) for call in assess.call_args_list],
            [4, 2],
        )
        self.assertEqual(len(persisted), 6)
        self.assertFalse(batch_call.kwargs["early_stopped"])
        self.assertEqual(batch_call.kwargs["assessment_waves"], 2)

    def test_nine_distinct_identities_fall_back_to_full_assessment(self):
        groups = [_group(_item()) for _ in range(9)]
        assessments = [_assessment() for _ in range(9)]

        assess, _persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[assessments],
        )

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 9)
        self.assertEqual(len(persisted), 9)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["deferred_items"], 0)

    def test_fact_check_evidence_never_uses_adaptive_budget(self):
        groups = [
            _group(_item(role=VerificationEvidence.EvidenceRole.FACT_CHECK))
            for _ in range(6)
        ]
        assessments = [_assessment() for _ in range(6)]

        assess, _persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[assessments],
        )

        assess.assert_called_once()
        self.assertEqual(len(assess.call_args.args[1]), 6)
        self.assertEqual(len(persisted), 6)
        self.assertFalse(batch_call.kwargs["adaptive_budget"])

    def test_ninth_duplicate_is_deferred_without_dropping_any_identity(self):
        groups = [_group(_item()) for _ in range(7)]
        groups.append(_group(_item(), _item()))
        first = [_assessment() for _ in range(4)]
        second = [_assessment() for _ in range(4)]

        assess, _persist_batch, persisted, batch_call = self._run(
            groups,
            side_effect=[first, second],
        )

        self.assertEqual(assess.call_count, 2)
        self.assertEqual(
            [len(call.args[1]) for call in assess.call_args_list],
            [4, 4],
        )
        self.assertEqual(len(persisted), 8)
        persisted_ids = {item.evidence_link_id for item in persisted}
        self.assertTrue(all(
            group.evidence[0].evidence_link_id in persisted_ids
            for group in groups
        ))
        self.assertTrue(batch_call.kwargs["adaptive_budget"])
        self.assertEqual(batch_call.kwargs["selected_items"], 8)
        self.assertEqual(batch_call.kwargs["deferred_items"], 1)
        self.assertFalse(batch_call.kwargs["early_stopped"])
