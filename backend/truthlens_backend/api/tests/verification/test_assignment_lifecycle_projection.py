import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase

from api.accountability_service import record_accountability_event
from api.models import AccountabilityEvent, Organization
from api.organization_service import PartnerCapability
from api.verification_metrics_service import (
    VerificationMetricsIntegrityError,
    project_organization_assignment_lifecycles,
)


class AssignmentLifecycleProjectionTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="lifecycle-projection-actor")
        self.organization = Organization.objects.create(
            name="Lifecycle Partner", slug="lifecycle-partner",
        )
        self.other_organization = Organization.objects.create(
            name="Other Lifecycle Partner", slug="other-lifecycle-partner",
        )
        self.assignment_id = str(uuid.uuid4())
        self.claim_id = str(uuid.uuid4())
        self.claimed_at = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)
        self.terminal_at = self.claimed_at + timedelta(seconds=90.5)

    def record(self, action_type, *, assignment_id=None, at=None, organization=None,
               **overrides):
        organization = organization if organization is not None else self.organization
        system_action = action_type in {
            AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CREATED,
            AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_COMPLETED,
        }
        values = {
            "action_type": action_type,
            "resource_type": AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
            "resource_id": assignment_id or self.assignment_id,
            "authority_scope": (
                AccountabilityEvent.AuthorityScope.SYSTEM if system_action
                else AccountabilityEvent.AuthorityScope.ORGANIZATION
            ),
            "subject_organization": organization,
            "context": {"claim_id": self.claim_id},
        }
        if not system_action:
            values.update(
                actor=self.actor,
                authority_organization=organization,
                capability=PartnerCapability.CLAIM_VERIFICATION_WORK,
            )
        values.update(overrides)
        # Supply fixture timestamps at insertion; never rewrite append-only rows.
        with patch("django.utils.timezone.now", return_value=at or self.claimed_at):
            return record_accountability_event(**values)

    def project(self):
        return project_organization_assignment_lifecycles(organization=self.organization)

    def test_claimed_without_terminal_projects_exact_active_shape(self):
        self.record(AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED)

        self.assertEqual(self.project(), [{
            "assignment_id": self.assignment_id,
            "claim_id": self.claim_id,
            "organization_id": str(self.organization.pk),
            "status": "ACTIVE",
            "claimed_at": self.claimed_at,
            "terminal_at": None,
            "duration_seconds": None,
        }])

    def test_completion_and_release_project_event_timestamps_and_duration(self):
        actions = AccountabilityEvent.ActionType
        for action, status in (
            (actions.VERIFICATION_ASSIGNMENT_COMPLETED, "COMPLETED"),
            (actions.VERIFICATION_ASSIGNMENT_RELEASED, "RELEASED"),
        ):
            with self.subTest(status=status):
                assignment_id = str(uuid.uuid4())
                self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED,
                            assignment_id=assignment_id)
                terminal = self.record(action, assignment_id=assignment_id,
                                       at=self.terminal_at)
                if status == "COMPLETED":
                    self.assertEqual(terminal.authority_scope,
                                     AccountabilityEvent.AuthorityScope.SYSTEM)
                    self.assertIsNone(terminal.authority_organization)
                attempt = next(item for item in self.project()
                               if item["assignment_id"] == assignment_id)
                self.assertEqual(attempt, {
                    "assignment_id": assignment_id,
                    "claim_id": self.claim_id,
                    "organization_id": str(self.organization.pk),
                    "status": status,
                    "claimed_at": self.claimed_at,
                    "terminal_at": self.terminal_at,
                    "duration_seconds": 90.5,
                })
                self.assertIsInstance(attempt["duration_seconds"], float)

    def test_release_then_reclaim_same_claim_remains_two_attempts(self):
        actions = AccountabilityEvent.ActionType
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
        self.record(actions.VERIFICATION_ASSIGNMENT_RELEASED, at=self.terminal_at)
        replacement_id = str(uuid.uuid4())
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED,
                    assignment_id=replacement_id,
                    at=self.terminal_at + timedelta(seconds=1))

        attempts = self.project()
        self.assertEqual([item["assignment_id"] for item in attempts],
                         [self.assignment_id, replacement_id])
        self.assertEqual([item["claim_id"] for item in attempts],
                         [self.claim_id, self.claim_id])
        self.assertEqual([item["status"] for item in attempts], ["RELEASED", "ACTIVE"])

    def test_created_only_history_is_excluded_even_with_organization_subject(self):
        self.record(AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CREATED,
                    context={})
        self.assertEqual(self.project(), [])

    def test_created_does_not_supply_or_conflict_with_lifecycle_claim_identity(self):
        actions = AccountabilityEvent.ActionType
        self.record(actions.VERIFICATION_ASSIGNMENT_CREATED,
                    context={"claim_id": str(uuid.uuid4())})
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
        self.assertEqual(self.project()[0]["claim_id"], self.claim_id)

    def test_other_organization_history_is_excluded_including_system_completion(self):
        actions = AccountabilityEvent.ActionType
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED,
                    organization=self.other_organization)
        self.record(actions.VERIFICATION_ASSIGNMENT_COMPLETED,
                    organization=self.other_organization, at=self.terminal_at)
        self.assertEqual(len(self.project()), 1)
        self.assertEqual(self.project()[0]["status"], "ACTIVE")

    def test_other_resource_type_is_excluded(self):
        self.record(AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED,
                    resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE)
        self.assertEqual(self.project(), [])

    def test_output_orders_by_claimed_at_then_assignment_id(self):
        actions = AccountabilityEvent.ActionType
        # Reverse insertion order exercises both ordering keys independently.
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED,
                    assignment_id="a-later", at=self.terminal_at)
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED, assignment_id="b-earlier")
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED, assignment_id="a-earlier")
        self.assertEqual([item["assignment_id"] for item in self.project()],
                         ["a-earlier", "b-earlier", "a-later"])

    def test_missing_blank_or_nonstring_claim_identity_fails_closed(self):
        actions = AccountabilityEvent.ActionType
        for context in ({}, {"claim_id": None}, {"claim_id": ""},
                        {"claim_id": " \t"}, {"claim_id": 123}):
            with self.subTest(context=context):
                # Roll back each rejected fixture without deleting event history.
                with self.assertRaises(VerificationMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED,
                                    context=context)
                        self.project()

    def test_terminal_missing_or_inconsistent_claim_identity_fails_closed(self):
        actions = AccountabilityEvent.ActionType
        for context in ({}, {"claim_id": str(uuid.uuid4())}):
            with self.subTest(context=context):
                with self.assertRaises(VerificationMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
                        self.record(actions.VERIFICATION_ASSIGNMENT_RELEASED,
                                    at=self.terminal_at, context=context)
                        self.project()

    def test_terminal_without_claimed_event_fails_closed(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.VERIFICATION_ASSIGNMENT_RELEASED,
                       actions.VERIFICATION_ASSIGNMENT_COMPLETED):
            with self.subTest(action=action):
                with self.assertRaises(VerificationMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(action, at=self.terminal_at)
                        self.project()

    def test_duplicate_claimed_or_terminal_events_fail_closed(self):
        actions = AccountabilityEvent.ActionType
        for duplicate in (actions.VERIFICATION_ASSIGNMENT_CLAIMED,
                          actions.VERIFICATION_ASSIGNMENT_RELEASED,
                          actions.VERIFICATION_ASSIGNMENT_COMPLETED):
            with self.subTest(duplicate=duplicate):
                with self.assertRaises(VerificationMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
                        self.record(duplicate, at=self.terminal_at)
                        if duplicate != actions.VERIFICATION_ASSIGNMENT_CLAIMED:
                            self.record(duplicate, at=self.terminal_at)
                        self.project()

    def test_contradictory_terminal_events_fail_closed(self):
        actions = AccountabilityEvent.ActionType
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
        self.record(actions.VERIFICATION_ASSIGNMENT_RELEASED, at=self.terminal_at)
        self.record(actions.VERIFICATION_ASSIGNMENT_COMPLETED, at=self.terminal_at)
        with self.assertRaises(VerificationMetricsIntegrityError):
            self.project()

    def test_terminal_before_claim_fails_closed_but_equal_timestamp_is_valid(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.VERIFICATION_ASSIGNMENT_RELEASED,
                       actions.VERIFICATION_ASSIGNMENT_COMPLETED):
            with self.subTest(action=action):
                with self.assertRaises(VerificationMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
                        self.record(action, at=self.claimed_at - timedelta(seconds=1))
                        self.project()
        self.record(actions.VERIFICATION_ASSIGNMENT_CLAIMED)
        self.record(actions.VERIFICATION_ASSIGNMENT_COMPLETED)
        self.assertEqual(self.project()[0]["duration_seconds"], 0.0)
