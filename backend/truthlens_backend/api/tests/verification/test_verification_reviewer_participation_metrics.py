import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import SimpleTestCase, TestCase

from api.accountability_service import record_accountability_event
from api.models import AccountabilityEvent, Organization
from api.organization_service import PartnerCapability
from api.verification_reviewer_participation_metrics_service import (
    VerificationReviewerParticipationMetricsIntegrityError,
    get_organization_verification_reviewer_participation,
)


class VerificationReviewerParticipationMetricsTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Reviewer Participation Partner", slug="reviewer-participation-partner",
        )
        self.other_organization = Organization.objects.create(
            name="Other Reviewer Partner", slug="other-reviewer-partner",
        )
        self.actor = User.objects.create_user(username="participation-reviewer")
        self.other_actor = User.objects.create_user(username="other-participation-reviewer")
        self.at = datetime(2026, 9, 16, 8, 0, 0, 123456, tzinfo=timezone.utc)

    def event_values(self, action):
        actions = AccountabilityEvent.ActionType
        resources = AccountabilityEvent.ResourceType
        resources_by_action = {
            actions.EVIDENCE_VERIFIED: resources.EVIDENCE_SUBMISSION,
            actions.EVIDENCE_REJECTED: resources.EVIDENCE_SUBMISSION,
            actions.ADJUDICATION_STARTED: resources.MODERATION_CASE,
            actions.VERDICT_ISSUED: resources.ADJUDICATION_DECISION,
            actions.VERDICT_REVISED: resources.ADJUDICATION_DECISION,
        }
        evidence_review = action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED)
        decision_id = str(uuid.uuid4())
        values = {
            "action_type": action,
            "resource_type": resources_by_action[action],
            "resource_id": decision_id,
            "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
            "authority_organization": self.organization,
            "subject_organization": self.organization,
            "capability": (
                PartnerCapability.REVIEW_EVIDENCE if evidence_review else PartnerCapability.ADJUDICATE
            ),
            "context": {"claim_id": str(uuid.uuid4())},
        }
        if action == actions.VERDICT_ISSUED:
            values["previous_state"] = {"verdict": None, "revision_number": 0}
            values["new_state"] = {"verdict": "FACT", "revision_number": 1}
        elif action == actions.VERDICT_REVISED:
            values["previous_state"] = {
                "decision_id": str(uuid.uuid4()), "verdict": "FACT", "revision_number": 1,
            }
            values["new_state"] = {
                "decision_id": decision_id, "verdict": "MISLEADING", "revision_number": 2,
            }
            # Current revision instrumentation need not carry a claim_id.
            values["context"] = {"correction_request_id": str(uuid.uuid4())}
        return values

    def record(self, action=AccountabilityEvent.ActionType.EVIDENCE_VERIFIED, *, at=None, **overrides):
        values = {"actor": self.actor, **self.event_values(action)}
        values.update(overrides)
        with patch("django.utils.timezone.now", return_value=at or self.at):
            return record_accountability_event(**values)

    def historical_or_malformed_event(
        self, action=AccountabilityEvent.ActionType.EVIDENCE_VERIFIED, *, at=None, **overrides,
    ):
        # Direct insertion models pre-G-A blank identity or deliberately corrupt
        # persisted semantics/identity. Existing append-only rows are not rewritten.
        values = {
            **self.event_values(action), "actor": None, "actor_id_snapshot": "",
            "actor_username_snapshot": "historical-reviewer",
        }
        values.update(overrides)
        with patch("django.utils.timezone.now", return_value=at or self.at):
            return AccountabilityEvent.objects.create(**values)

    def participation(self):
        with self.assertNumQueries(1) as queries:
            result = get_organization_verification_reviewer_participation(
                organization=self.organization,
            )
        sql = queries.captured_queries[0]["sql"]
        self.assertIn(f'FROM "{AccountabilityEvent._meta.db_table}"', sql)
        self.assertNotIn(" JOIN ", sql.upper())
        counts = result["reviewer_participation"]
        for stage_count in counts["by_stage"].values():
            self.assertLessEqual(stage_count, counts["unique_reviewers"])
        self.assertEqual(set(result), {"organization_id", "measurement_basis", "reviewer_participation"})
        self.assertEqual(set(counts), {"unique_reviewers", "by_stage"})
        self.assertEqual(set(counts["by_stage"]), {"evidence_review", "adjudication"})
        return result

    def assert_counts(self, *, unique, evidence, adjudication):
        self.assertEqual(self.participation()["reviewer_participation"], {
            "unique_reviewers": unique,
            "by_stage": {"evidence_review": evidence, "adjudication": adjudication},
        })

    def empty_contract(self):
        return {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "identity_source": "ACTOR_ID_SNAPSHOT",
                "coverage": "DURABLE_ACTOR_ID_SNAPSHOT_EVENTS_ONLY",
                "historical_backfill": False,
                "first_observed_participation_at": None,
                "last_observed_participation_at": None,
            },
            "reviewer_participation": {
                "unique_reviewers": 0,
                "by_stage": {"evidence_review": 0, "adjudication": 0},
            },
        }

    def test_exact_empty_contract(self):
        self.assertEqual(self.participation(), self.empty_contract())

    def test_evidence_verified_counts_one_evidence_reviewer(self):
        self.record(AccountabilityEvent.ActionType.EVIDENCE_VERIFIED)
        self.assert_counts(unique=1, evidence=1, adjudication=0)

    def test_evidence_rejected_counts_one_evidence_reviewer(self):
        self.record(AccountabilityEvent.ActionType.EVIDENCE_REJECTED)
        self.assert_counts(unique=1, evidence=1, adjudication=0)

    def test_adjudication_started_counts_one_adjudicator(self):
        self.record(AccountabilityEvent.ActionType.ADJUDICATION_STARTED)
        self.assert_counts(unique=1, evidence=0, adjudication=1)

    def test_verdict_issued_counts_one_adjudicator(self):
        self.record(AccountabilityEvent.ActionType.VERDICT_ISSUED)
        self.assert_counts(unique=1, evidence=0, adjudication=1)

    def test_verdict_revised_without_context_claim_counts_one_adjudicator(self):
        event = self.record(AccountabilityEvent.ActionType.VERDICT_REVISED)
        self.assertNotIn("claim_id", event.context)
        self.assert_counts(unique=1, evidence=0, adjudication=1)

    def test_repeated_review_events_across_claims_and_resources_count_actor_once(self):
        actions = AccountabilityEvent.ActionType
        claim_id = str(uuid.uuid4())
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED, actions.EVIDENCE_VERIFIED):
            self.record(action, resource_id="same-evidence-resource", context={"claim_id": claim_id})
        self.record(actions.EVIDENCE_VERIFIED)
        self.assert_counts(unique=1, evidence=1, adjudication=0)

    def test_one_actor_across_both_stages_counts_once_overall(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED,
                       actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED, actions.VERDICT_REVISED):
            self.record(action)
        self.assert_counts(unique=1, evidence=1, adjudication=1)

    def test_distinct_human_counts_use_union_of_stage_sets_not_sum(self):
        actions = AccountabilityEvent.ActionType
        third_actor = User.objects.create_user(username="third-participation-reviewer")
        self.record(actions.EVIDENCE_VERIFIED)
        self.record(actions.VERDICT_ISSUED)
        self.record(actions.EVIDENCE_REJECTED, actor=self.other_actor)
        self.record(actions.ADJUDICATION_STARTED, actor=third_actor)
        self.record(actions.VERDICT_REVISED, actor=third_actor)
        self.assert_counts(unique=3, evidence=2, adjudication=2)

    def test_different_durable_ids_with_same_username_snapshot_count_independently(self):
        for actor in (self.actor, self.other_actor):
            event = self.record(
                AccountabilityEvent.ActionType.VERDICT_REVISED, actor=actor,
                actor_snapshot={"id": str(actor.pk), "username": "shared-historical-name"},
            )
            self.assertEqual(event.actor_username_snapshot, "shared-historical-name")
        self.assert_counts(unique=2, evidence=0, adjudication=2)

    def test_username_rename_does_not_split_durable_actor_identity(self):
        first = self.record()
        self.actor.username = "renamed-participation-reviewer"
        self.actor.save(update_fields=["username"])
        second = self.record(AccountabilityEvent.ActionType.EVIDENCE_REJECTED)
        self.assertNotEqual(first.actor_username_snapshot, second.actor_username_snapshot)
        self.assertEqual(first.actor_id_snapshot, second.actor_id_snapshot)
        self.assert_counts(unique=1, evidence=1, adjudication=0)

    def test_deleted_live_actor_remains_countable_from_durable_id(self):
        event = self.record()
        actor_id = str(self.actor.pk)
        self.actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_id_snapshot, actor_id)
        self.assert_counts(unique=1, evidence=1, adjudication=0)

    def test_null_actor_revision_with_durable_historical_snapshot_remains_countable(self):
        self.record(
            AccountabilityEvent.ActionType.VERDICT_REVISED, actor=None,
            actor_snapshot={"id": "opaque-deleted-preparer", "username": "deleted-preparer"},
        )
        self.assert_counts(unique=1, evidence=0, adjudication=1)

    def test_surviving_live_actor_fk_without_durable_id_does_not_count(self):
        self.historical_or_malformed_event(actor=self.actor)
        self.assertEqual(self.participation(), self.empty_contract())

    def test_historical_username_without_durable_id_does_not_count(self):
        self.historical_or_malformed_event(actor_username_snapshot="known-historical-name")
        self.assertEqual(self.participation(), self.empty_contract())

    def test_historical_context_actor_snapshot_without_durable_id_does_not_count(self):
        self.historical_or_malformed_event(
            AccountabilityEvent.ActionType.VERDICT_REVISED,
            context={"actor_snapshot": {"id": "historical-id", "username": "historical-name"}},
        )
        self.assertEqual(self.participation(), self.empty_contract())

    def test_valid_blank_identity_history_for_all_selected_actions_is_outside_coverage(self):
        for action in (AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
                       AccountabilityEvent.ActionType.EVIDENCE_REJECTED,
                       AccountabilityEvent.ActionType.ADJUDICATION_STARTED,
                       AccountabilityEvent.ActionType.VERDICT_ISSUED,
                       AccountabilityEvent.ActionType.VERDICT_REVISED):
            self.historical_or_malformed_event(action)
        self.assertEqual(self.participation(), self.empty_contract())

    def test_whitespace_only_and_padded_durable_ids_fail_closed(self):
        for actor_id in (" ", "\t\n", " padded-id", "padded-id ", " padded-id "):
            with self.subTest(actor_id=actor_id):
                with self.assertRaises(VerificationReviewerParticipationMetricsIntegrityError):
                    with transaction.atomic():
                        self.historical_or_malformed_event(actor_id_snapshot=actor_id)
                        self.participation()

    def test_selected_semantics_fail_closed_even_without_durable_identity(self):
        actions = AccountabilityEvent.ActionType
        scopes = AccountabilityEvent.AuthorityScope
        # Validate every selected action before excluding historical blank IDs.
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED,
                       actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED, actions.VERDICT_REVISED):
            for actor_id in ("", "valid-durable-id"):
                wrong_capability = (
                    PartnerCapability.ADJUDICATE
                    if action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED)
                    else PartnerCapability.REVIEW_EVIDENCE
                )
                for overrides in (
                    {"resource_type": AccountabilityEvent.ResourceType.THREAD},
                    *({"authority_scope": scope} for scope in (scopes.PLATFORM, scopes.PERSONAL, scopes.SYSTEM)),
                    {"authority_organization": self.other_organization},
                    {"authority_organization": None},
                    {"capability": wrong_capability},
                    {"capability": ""},
                ):
                    with self.subTest(action=action, actor_id=actor_id, overrides=overrides):
                        with self.assertRaises(VerificationReviewerParticipationMetricsIntegrityError):
                            with transaction.atomic():
                                self.historical_or_malformed_event(
                                    action, actor_id_snapshot=actor_id, **overrides,
                                )
                                self.participation()

    def test_another_subject_organization_is_excluded_even_with_matching_authority(self):
        self.record()
        self.record(actor=self.other_actor, subject_organization=self.other_organization)
        self.historical_or_malformed_event(
            subject_organization=self.other_organization, actor_id_snapshot=" padded ",
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        self.assert_counts(unique=1, evidence=1, adjudication=0)

    def test_nonparticipation_actions_never_count_or_affect_coverage(self):
        actions = AccountabilityEvent.ActionType
        excluded_actions = (
            actions.VERIFICATION_ASSIGNMENT_CREATED, actions.VERIFICATION_ASSIGNMENT_CLAIMED,
            actions.VERIFICATION_ASSIGNMENT_RELEASED, actions.VERIFICATION_ASSIGNMENT_COMPLETED,
            actions.EVIDENCE_REOPENED,
            actions.ARTICLE_DRAFT_CREATED, actions.ARTICLE_DRAFT_SAVED, actions.ARTICLE_SUBMITTED,
            actions.ARTICLE_RETURNED_FOR_REWORK, actions.ARTICLE_ABANDONED,
            actions.ARTICLE_PUBLISHED, actions.ARTICLE_REVISION_DRAFTED, actions.ARTICLE_REVISED,
            actions.FACTUAL_CORRECTION_PUBLISHED,
            actions.ORGANIZATION_INVITATION_ACCEPTED, actions.ORGANIZATION_MEMBERSHIP_ROLE_CHANGED,
            actions.SAFETY_CASE_CLAIMED, actions.SAFETY_DISMISSED,
        )
        for action in excluded_actions:
            # Only action selection matters for excluded events. This fixture is
            # deliberately malformed if treated as selected reviewer history.
            self.historical_or_malformed_event(
                action_type=action, actor_id_snapshot=" padded-nonreviewer ",
                authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
                resource_type=AccountabilityEvent.ResourceType.THREAD,
                at=self.at - timedelta(days=10),
            )
        self.assertEqual(self.participation(), self.empty_contract())
        self.record()
        self.assert_counts(unique=1, evidence=1, adjudication=0)
        basis = self.participation()["measurement_basis"]
        self.assertEqual(basis["first_observed_participation_at"], self.at)
        self.assertEqual(basis["last_observed_participation_at"], self.at)

    def test_correction_evidence_is_included_for_both_review_actions(self):
        for action, actor in (
            (AccountabilityEvent.ActionType.EVIDENCE_VERIFIED, self.actor),
            (AccountabilityEvent.ActionType.EVIDENCE_REJECTED, self.other_actor),
        ):
            self.record(action, actor=actor, context={
                "claim_id": str(uuid.uuid4()),
                "correction_request_id": str(uuid.uuid4()),
                "correction_case_id": str(uuid.uuid4()),
                "evidence_case_id": str(uuid.uuid4()),
            })
        self.assert_counts(unique=2, evidence=2, adjudication=0)

    def test_exact_nonempty_contract_coverage_uses_only_durable_selected_events(self):
        first_at = self.at - timedelta(hours=1)
        last_at = self.at + timedelta(hours=1)
        self.record(AccountabilityEvent.ActionType.VERDICT_REVISED, at=last_at)
        self.record(at=first_at)
        self.historical_or_malformed_event(at=first_at - timedelta(days=100), actor=self.other_actor)
        self.historical_or_malformed_event(
            AccountabilityEvent.ActionType.VERDICT_ISSUED, at=last_at + timedelta(days=100),
        )
        expected = self.empty_contract()
        expected["measurement_basis"]["first_observed_participation_at"] = first_at
        expected["measurement_basis"]["last_observed_participation_at"] = last_at
        expected["reviewer_participation"] = {
            "unique_reviewers": 1, "by_stage": {"evidence_review": 1, "adjudication": 1},
        }
        self.assertEqual(self.participation(), expected)

    def test_output_exposes_only_aggregate_contract_without_individual_identity(self):
        self.record()
        self.record(AccountabilityEvent.ActionType.VERDICT_REVISED, actor=self.other_actor)
        result = self.participation()
        serialized = json.dumps(result, default=str)
        for username in (self.actor.username, self.other_actor.username):
            self.assertNotIn(username, serialized)
        counts = result["reviewer_participation"]
        self.assertEqual(counts, {
            "unique_reviewers": 2, "by_stage": {"evidence_review": 1, "adjudication": 1},
        })
        self.assertEqual(result["measurement_basis"], {
            **self.empty_contract()["measurement_basis"],
            "first_observed_participation_at": self.at,
            "last_observed_participation_at": self.at,
        })


class VerificationReviewerParticipationQueryBoundaryTests(SimpleTestCase):
    """Any database access beyond the mocked accountability read is forbidden."""

    def setUp(self):
        self.organization = SimpleNamespace(pk=uuid.uuid4())
        self.event = {
            "action_type": AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
            "resource_type": AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
            "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
            "authority_organization_id": self.organization.pk,
            "capability": PartnerCapability.REVIEW_EVIDENCE,
            "actor_id_snapshot": "opaque-reviewer-id",
            "created_at": datetime(2026, 9, 16, 8, tzinfo=timezone.utc),
        }

    def test_single_subject_scoped_read_selects_only_needed_fields_and_orders_deterministically(self):
        with patch(
            "api.verification_reviewer_participation_metrics_service.AccountabilityEvent.objects.filter"
        ) as query:
            query.return_value.order_by.return_value.values.return_value = [self.event]
            result = get_organization_verification_reviewer_participation(organization=self.organization)
        actions = AccountabilityEvent.ActionType
        query.assert_called_once_with(
            subject_organization=self.organization,
            action_type__in=(actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED,
                             actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED, actions.VERDICT_REVISED),
        )
        query.return_value.order_by.assert_called_once_with("created_at", "id")
        query.return_value.order_by.return_value.values.assert_called_once_with(
            "action_type", "resource_type", "authority_scope",
            "authority_organization_id", "capability", "actor_id_snapshot", "created_at",
        )
        self.assertEqual(result["reviewer_participation"]["unique_reviewers"], 1)
        self.assertNotIn(self.event["actor_id_snapshot"], json.dumps(result, default=str))

    def test_nonstring_durable_id_fails_without_any_identity_fallback(self):
        # CharField persistence coerces some types to strings; candidate mocks
        # exercise the defensive type check without hiding malformed input.
        for actor_id in (None, 123, False, [], {}):
            with self.subTest(actor_id=actor_id):
                with patch(
                    "api.verification_reviewer_participation_metrics_service.AccountabilityEvent.objects.filter"
                ) as query:
                    query.return_value.order_by.return_value.values.return_value = [
                        {**self.event, "actor_id_snapshot": actor_id},
                    ]
                    with self.assertRaises(VerificationReviewerParticipationMetricsIntegrityError):
                        get_organization_verification_reviewer_participation(organization=self.organization)

    def test_durable_ids_are_opaque_and_are_not_parsed_as_integer_or_uuid(self):
        events = [
            {**self.event, "actor_id_snapshot": actor_id}
            for actor_id in ("42", "043", str(uuid.uuid4()), "opaque:reviewer/identifier")
        ]
        with patch(
            "api.verification_reviewer_participation_metrics_service.AccountabilityEvent.objects.filter"
        ) as query:
            query.return_value.order_by.return_value.values.return_value = events
            result = get_organization_verification_reviewer_participation(organization=self.organization)
        self.assertEqual(result["reviewer_participation"], {
            "unique_reviewers": 4, "by_stage": {"evidence_review": 4, "adjudication": 0},
        })
