import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase

from api.accountability_service import record_accountability_event
from api.models import AccountabilityEvent, Organization
from api.organization_service import PartnerCapability
from api.verification_activity_metrics_service import (
    VerificationActivityMetricsIntegrityError,
    get_organization_verification_activity,
)


class VerificationActivityMetricsTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="activity-metrics-actor")
        self.organization = Organization.objects.create(
            name="Activity Partner", slug="activity-partner",
        )
        self.other_organization = Organization.objects.create(
            name="Other Activity Partner", slug="other-activity-partner",
        )
        self.claim_id = str(uuid.uuid4())
        self.observed_at = datetime(2026, 9, 15, 8, 0, 0, 123456, tzinfo=timezone.utc)
        actions = AccountabilityEvent.ActionType
        resources = AccountabilityEvent.ResourceType
        self.event_types = {
            actions.EVIDENCE_VERIFIED: (resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE),
            actions.EVIDENCE_REJECTED: (resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE),
            actions.EVIDENCE_REOPENED: (resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE),
            actions.ADJUDICATION_STARTED: (resources.MODERATION_CASE, PartnerCapability.ADJUDICATE),
            actions.VERDICT_ISSUED: (resources.ADJUDICATION_DECISION, PartnerCapability.ADJUDICATE),
            actions.VERDICT_REVISED: (resources.ADJUDICATION_DECISION, PartnerCapability.ADJUDICATE),
            actions.ARTICLE_PUBLISHED: (resources.OFFICIAL_FACT_CHECK, PartnerCapability.PUBLISH_FACT_CHECK),
            actions.ARTICLE_REVISED: (resources.OFFICIAL_FACT_CHECK, PartnerCapability.PUBLISH_FACT_CHECK),
            actions.FACTUAL_CORRECTION_PUBLISHED: (resources.OFFICIAL_FACT_CHECK, PartnerCapability.PUBLISH_FACT_CHECK),
        }

    def record(self, action, *, organization=None, at=None, **overrides):
        organization = self.organization if organization is None else organization
        resource_type, capability = self.event_types.get(action, (
            AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
            PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        ))
        context = {"claim_id": self.claim_id}
        if action == AccountabilityEvent.ActionType.ARTICLE_PUBLISHED:
            context["revision_kind"] = "INITIAL"
        values = {
            "actor": self.actor,
            "action_type": action,
            "resource_type": resource_type,
            "resource_id": str(uuid.uuid4()),
            "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
            "authority_organization": organization,
            "subject_organization": organization,
            "capability": capability,
            "context": context,
        }
        values.update(overrides)
        # Insert timestamps once, preserving append-only event history.
        with patch("django.utils.timezone.now", return_value=at or self.observed_at):
            return record_accountability_event(**values)

    def activity(self):
        # One event-only query; no mutable domain rows are needed by these fixtures.
        with self.assertNumQueries(1):
            result = get_organization_verification_activity(organization=self.organization)
        review = result["evidence_review"]
        self.assertEqual(review["decisions"], review["verified"] + review["rejected"])
        return result

    def empty_contract(self):
        return {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_activity_at": None,
                "last_observed_activity_at": None,
            },
            "evidence_review": {"decisions": 0, "verified": 0, "rejected": 0},
            "adjudication": {"started": 0, "verdicts_issued": 0},
            "publication": {"initial_published": 0},
        }

    def test_empty_organization_returns_exact_zero_and_none_contract(self):
        self.assertEqual(self.activity(), self.empty_contract())

    def test_ordinary_verified_event_increments_decisions_and_verified(self):
        self.record(AccountabilityEvent.ActionType.EVIDENCE_VERIFIED)
        self.assertEqual(self.activity()["evidence_review"], {
            "decisions": 1, "verified": 1, "rejected": 0,
        })

    def test_ordinary_rejected_event_increments_decisions_and_rejected(self):
        self.record(AccountabilityEvent.ActionType.EVIDENCE_REJECTED)
        self.assertEqual(self.activity()["evidence_review"], {
            "decisions": 1, "verified": 0, "rejected": 1,
        })

    def test_repeated_ordinary_decisions_on_same_resource_and_claim_are_counted(self):
        actions = AccountabilityEvent.ActionType
        evidence_id = str(uuid.uuid4())
        for offset, action in enumerate((
            actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REOPENED,
            actions.EVIDENCE_REJECTED, actions.EVIDENCE_REOPENED,
            actions.EVIDENCE_VERIFIED,
        )):
            self.record(action, resource_id=evidence_id,
                        at=self.observed_at + timedelta(seconds=offset))
        self.assertEqual(self.activity()["evidence_review"], {
            "decisions": 3, "verified": 2, "rejected": 1,
        })

    def test_correction_evidence_is_excluded_by_presence_of_context_key(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED):
            for correction_id in (str(uuid.uuid4()), None, "", False):
                self.record(action, context={"correction_request_id": correction_id})
        self.assertEqual(self.activity(), self.empty_contract())

    def test_excluded_correction_evidence_does_not_extend_activity_timestamps(self):
        actions = AccountabilityEvent.ActionType
        for action, offset in ((actions.EVIDENCE_VERIFIED, -100),
                               (actions.EVIDENCE_REJECTED, 100)):
            self.record(action, at=self.observed_at + timedelta(seconds=offset), context={
                "correction_request_id": str(uuid.uuid4()),
            })
        self.record(actions.EVIDENCE_VERIFIED)
        result = self.activity()
        self.assertEqual(result["evidence_review"], {"decisions": 1, "verified": 1, "rejected": 0})
        self.assertEqual(result["measurement_basis"]["first_observed_activity_at"], self.observed_at)
        self.assertEqual(result["measurement_basis"]["last_observed_activity_at"], self.observed_at)

    def test_adjudication_started_counts_without_requiring_verdict(self):
        self.record(AccountabilityEvent.ActionType.ADJUDICATION_STARTED)
        self.assertEqual(self.activity()["adjudication"], {"started": 1, "verdicts_issued": 0})

    def test_verdict_issued_counts_without_requiring_started(self):
        self.record(AccountabilityEvent.ActionType.VERDICT_ISSUED)
        self.assertEqual(self.activity()["adjudication"], {"started": 0, "verdicts_issued": 1})

    def assert_duplicate_claim_fails(self, action):
        for same_resource in (True, False):
            with self.subTest(same_resource=same_resource):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    # Roll back each malformed fixture without deleting audit history.
                    with transaction.atomic():
                        first = self.record(action)
                        self.record(action, resource_id=(
                            first.resource_id if same_resource else str(uuid.uuid4())
                        ))
                        self.activity()

    def test_duplicate_adjudication_started_for_claim_fails_closed(self):
        self.assert_duplicate_claim_fails(AccountabilityEvent.ActionType.ADJUDICATION_STARTED)

    def test_duplicate_verdict_issued_for_claim_fails_closed(self):
        self.assert_duplicate_claim_fails(AccountabilityEvent.ActionType.VERDICT_ISSUED)

    def test_explicit_initial_publication_increments_initial_published(self):
        self.record(AccountabilityEvent.ActionType.ARTICLE_PUBLISHED)
        self.assertEqual(self.activity()["publication"], {"initial_published": 1})

    def test_publication_requires_exact_initial_revision_kind(self):
        for context in (
            {"claim_id": self.claim_id},
            *({"claim_id": self.claim_id, "revision_kind": kind} for kind in (
                None, "", " \t", "initial", "EDITORIAL_REVISION", "FACTUAL_CORRECTION", 1,
            )),
        ):
            with self.subTest(context=context):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(AccountabilityEvent.ActionType.ARTICLE_PUBLISHED, context=context)
                        self.activity()

    def test_duplicate_initial_publication_for_claim_fails_closed(self):
        self.assert_duplicate_claim_fails(AccountabilityEvent.ActionType.ARTICLE_PUBLISHED)

    def test_revision_and_correction_publications_are_excluded(self):
        actions = AccountabilityEvent.ActionType
        self.record(actions.ARTICLE_REVISED, context={
            "claim_id": self.claim_id, "revision_kind": "EDITORIAL_REVISION",
        })
        self.record(actions.FACTUAL_CORRECTION_PUBLISHED, context={
            "claim_id": self.claim_id, "revision_kind": "FACTUAL_CORRECTION",
        })
        self.assertEqual(self.activity(), self.empty_contract())

    def test_other_organization_events_are_excluded_by_subject_not_authority(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED,
                       actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED,
                       actions.ARTICLE_PUBLISHED):
            self.record(action)
            self.record(action, organization=self.other_organization,
                        authority_organization=self.organization)
        result = self.activity()
        self.assertEqual(result["evidence_review"], {"decisions": 2, "verified": 1, "rejected": 1})
        self.assertEqual(result["adjudication"], {"started": 1, "verdicts_issued": 1})
        self.assertEqual(result["publication"], {"initial_published": 1})

    def test_all_selected_actions_with_wrong_resource_type_fail_closed(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED,
                       actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED,
                       actions.ARTICLE_PUBLISHED):
            with self.subTest(action=action):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(action, resource_type=AccountabilityEvent.ResourceType.THREAD)
                        self.activity()

    def test_correction_evidence_with_wrong_resource_type_still_fails_closed(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED):
            with self.subTest(action=action):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(
                            action,
                            resource_type=AccountabilityEvent.ResourceType.THREAD,
                            context={"correction_request_id": str(uuid.uuid4())},
                        )
                        self.activity()

    def test_all_selected_actions_require_nonblank_string_claim_identity(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED,
                       actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED,
                       actions.ARTICLE_PUBLISHED):
            for identity in ({}, *({"claim_id": value} for value in (
                None, "", " \t\n", 123, False, [], {},
            ))):
                context = {**identity, "revision_kind": "INITIAL"}
                with self.subTest(action=action, context=context):
                    with self.assertRaises(VerificationActivityMetricsIntegrityError):
                        with transaction.atomic():
                            self.record(action, context=context)
                            self.activity()

    def test_timestamps_and_exact_nonempty_contract_use_only_ordinary_activity(self):
        actions = AccountabilityEvent.ActionType
        later = self.observed_at + timedelta(seconds=100)
        # Reverse insertion order; event time determines the bounds.
        self.record(actions.ARTICLE_PUBLISHED, at=later)
        self.record(actions.VERDICT_ISSUED, at=self.observed_at + timedelta(seconds=40))
        self.record(actions.EVIDENCE_VERIFIED, at=self.observed_at + timedelta(seconds=20))
        self.record(actions.EVIDENCE_REJECTED, at=self.observed_at + timedelta(seconds=30))
        self.record(actions.ADJUDICATION_STARTED)
        self.record(actions.VERDICT_REVISED, at=later + timedelta(days=1))
        self.record(actions.EVIDENCE_REOPENED, at=self.observed_at - timedelta(days=1))
        self.record(actions.ARTICLE_REVISED, at=later + timedelta(days=2))
        self.record(actions.FACTUAL_CORRECTION_PUBLISHED, at=later + timedelta(days=3))
        for offset in (-1000, 1000):
            self.record(actions.EVIDENCE_REJECTED,
                        at=self.observed_at + timedelta(seconds=offset), context={
                            "correction_request_id": str(uuid.uuid4()),
                        })
        self.record(actions.ARTICLE_PUBLISHED, organization=self.other_organization,
                    at=later + timedelta(days=4))
        expected = self.empty_contract()
        expected["measurement_basis"].update(
            first_observed_activity_at=self.observed_at, last_observed_activity_at=later,
        )
        expected["evidence_review"] = {"decisions": 2, "verified": 1, "rejected": 1}
        expected["adjudication"] = {"started": 1, "verdicts_issued": 1}
        expected["publication"] = {"initial_published": 1}
        self.assertEqual(self.activity(), expected)

    def test_draft_and_correction_proposal_actions_are_excluded(self):
        actions = AccountabilityEvent.ActionType
        for action in (
            actions.ARTICLE_DRAFT_CREATED, actions.ARTICLE_DRAFT_SAVED,
            actions.ARTICLE_SUBMITTED, actions.ARTICLE_RETURNED_FOR_REWORK,
            actions.ARTICLE_ABANDONED, actions.ARTICLE_REVISION_DRAFTED,
        ):
            self.record(action)
        for action in (actions.FACTUAL_CORRECTION_PROPOSAL_SAVED,
                       actions.FACTUAL_CORRECTION_PROPOSAL_PREPARED):
            self.record(action, resource_type=AccountabilityEvent.ResourceType.FACTUAL_CORRECTION_PROPOSAL)
        self.assertEqual(self.activity(), self.empty_contract())

    def test_distinct_claims_can_have_each_first_decision_action(self):
        actions = AccountabilityEvent.ActionType
        for claim_id in (self.claim_id, str(uuid.uuid4())):
            for action in (actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED,
                           actions.ARTICLE_PUBLISHED):
                self.record(action, context={"claim_id": claim_id, "revision_kind": "INITIAL"})
        result = self.activity()
        self.assertEqual(result["adjudication"], {"started": 2, "verdicts_issued": 2})
        self.assertEqual(result["publication"], {"initial_published": 2})

    def test_nonobject_historical_context_fails_closed(self):
        for context in ([], "malformed context", 123):
            with self.subTest(context=context):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        # Normal recording rejects non-object context; simulate malformed history only.
                        AccountabilityEvent.objects.create(
                            action_type=AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
                            resource_type=AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
                            resource_id=str(uuid.uuid4()),
                            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
                            actor=self.actor,
                            authority_organization=self.organization,
                            subject_organization=self.organization,
                            capability=PartnerCapability.REVIEW_EVIDENCE,
                            context=context,
                        )
                        self.activity()
