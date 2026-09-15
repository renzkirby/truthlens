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
from api.verification_resolution_metrics_service import (
    VerificationResolutionMetricsIntegrityError,
    get_organization_verification_resolution_distribution,
)


class VerificationResolutionMetricsTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Resolution Partner", slug="resolution-partner",
        )
        self.other_organization = Organization.objects.create(
            name="Other Resolution Partner", slug="other-resolution-partner",
        )
        self.actor = User.objects.create_user(username="resolution-metrics-actor")
        self.decision_id = str(uuid.uuid4())
        self.claim_id = str(uuid.uuid4())
        self.at = datetime(2026, 9, 16, 8, 0, 0, 123456, tzinfo=timezone.utc)

    def record(self, action, *, at=None, **overrides):
        values = {
            "actor": self.actor,
            "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
            "authority_organization": self.organization,
            "subject_organization": self.organization,
            "capability": PartnerCapability.ADJUDICATE,
            "action_type": action,
            "resource_type": AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
        }
        values.update(overrides)
        # Fixture time is supplied at insertion; append-only rows are never rewritten.
        with patch("django.utils.timezone.now", return_value=at or self.at):
            return record_accountability_event(**values)

    def issue(self, *, decision_id=None, claim_id=None, verdict="FACT", **overrides):
        values = {
            "resource_id": decision_id if decision_id is not None else str(uuid.uuid4()),
            "context": {"claim_id": claim_id if claim_id is not None else str(uuid.uuid4())},
            "previous_state": {"verdict": None, "revision_number": 0},
            "new_state": {"verdict": verdict, "revision_number": 1},
        }
        values.update(overrides)
        return self.record(AccountabilityEvent.ActionType.VERDICT_ISSUED, **values)

    def revise(self, *, predecessor_id=None, decision_id=None,
               previous_verdict="FACT", verdict="FAKE", previous_revision=1,
               revision=2, **overrides):
        decision_id = decision_id if decision_id is not None else str(uuid.uuid4())
        values = {
            "resource_id": decision_id,
            # Match current correction instrumentation: no context claim_id required.
            "context": {"correction_request_id": str(uuid.uuid4()),
                        "prepared_proposal_id": str(uuid.uuid4()),
                        "fact_check_id": str(uuid.uuid4())},
            "previous_state": {
                "decision_id": predecessor_id if predecessor_id is not None else self.decision_id,
                "verdict": previous_verdict,
                "revision_number": previous_revision,
            },
            "new_state": {"decision_id": decision_id, "verdict": verdict,
                          "revision_number": revision},
        }
        values.update(overrides)
        return self.record(AccountabilityEvent.ActionType.VERDICT_REVISED, **values)

    def malformed_history(self, **overrides):
        # Only for data that normal recording rejects: non-object JSON or blank IDs.
        values = {
            "actor": self.actor,
            "actor_username_snapshot": self.actor.username,
            "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
            "authority_organization": self.organization,
            "subject_organization": self.organization,
            "capability": PartnerCapability.ADJUDICATE,
            "action_type": AccountabilityEvent.ActionType.VERDICT_ISSUED,
            "resource_type": AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            "resource_id": str(uuid.uuid4()),
            "context": {"claim_id": self.claim_id},
            "previous_state": {"verdict": None, "revision_number": 0},
            "new_state": {"verdict": "FACT", "revision_number": 1},
        }
        values.update(overrides)
        return AccountabilityEvent.objects.create(**values)

    def distribution(self):
        with self.assertNumQueries(1) as queries:
            result = get_organization_verification_resolution_distribution(
                organization=self.organization,
            )
        sql = queries.captured_queries[0]["sql"]
        self.assertIn(f'FROM "{AccountabilityEvent._meta.db_table}"', sql)
        self.assertNotIn(" JOIN ", sql.upper())
        latest = result["latest_observed_resolutions"]
        self.assertEqual(latest["count"], sum(latest["by_verdict"].values()))
        self.assertEqual(set(latest["by_verdict"]), {"FACT", "FAKE", "MISLEADING", "SATIRE"})
        return result

    def assert_buckets(self, **expected):
        buckets = {"FACT": 0, "FAKE": 0, "MISLEADING": 0, "SATIRE": 0, **expected}
        self.assertEqual(self.distribution()["latest_observed_resolutions"], {
            "count": sum(buckets.values()), "by_verdict": buckets,
        })

    def test_empty_returns_exact_contract(self):
        self.assertEqual(self.distribution(), {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "OBSERVED_AUTHORITATIVE_RESOLUTION_EVENTS_ONLY",
                "historical_backfill": False,
                "first_observed_resolution_at": None,
                "last_observed_resolution_at": None,
            },
            "latest_observed_resolutions": {
                "count": 0, "by_verdict": {"FACT": 0, "FAKE": 0, "MISLEADING": 0, "SATIRE": 0},
            },
        })

    def test_one_issued_fact_counts_one_fact(self):
        self.issue()
        self.assert_buckets(FACT=1)

    def test_supported_verdicts_and_independent_claims_count_in_each_bucket(self):
        for verdict in ("FACT", "FAKE", "MISLEADING", "SATIRE"):
            self.issue(verdict=verdict)
        self.assert_buckets(FACT=1, FAKE=1, MISLEADING=1, SATIRE=1)

    def test_independent_issued_decisions_with_same_verdict_count_independently(self):
        self.issue()
        self.issue()
        self.assert_buckets(FACT=2)

    def test_other_subject_organization_history_is_excluded_even_with_matching_authority(self):
        self.issue(decision_id=self.decision_id, claim_id=self.claim_id)
        self.issue(decision_id=self.decision_id, claim_id=self.claim_id,
                   subject_organization=self.other_organization)
        self.revise(predecessor_id=self.decision_id,
                    subject_organization=self.other_organization)
        self.issue(context={}, subject_organization=self.other_organization,
                   resource_type=AccountabilityEvent.ResourceType.THREAD)
        self.assert_buckets(FACT=1)

    def test_wrong_resource_type_for_either_selected_action_fails_closed(self):
        for recorder in (self.issue, self.revise):
            with self.subTest(action=recorder.__name__):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        recorder(resource_type=AccountabilityEvent.ResourceType.THREAD)
                        self.distribution()

    def test_blank_resource_identity_in_historical_events_fails_closed(self):
        for action in (AccountabilityEvent.ActionType.VERDICT_ISSUED,
                       AccountabilityEvent.ActionType.VERDICT_REVISED):
            for value in ("", " \t"):
                with self.subTest(action=action, value=value):
                    with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                        with transaction.atomic():
                            self.malformed_history(action_type=action, resource_id=value)
                            self.distribution()

    def test_previous_and_new_states_must_be_objects_for_each_action(self):
        for action in (AccountabilityEvent.ActionType.VERDICT_ISSUED,
                       AccountabilityEvent.ActionType.VERDICT_REVISED):
            for field in ("previous_state", "new_state"):
                for value in ([], "malformed", 123, False):
                    with self.subTest(action=action, field=field, value=value):
                        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                            with transaction.atomic():
                                self.malformed_history(action_type=action, **{field: value})
                                self.distribution()

    def test_issued_context_must_be_an_object(self):
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.malformed_history(context=[])
                self.distribution()

    def test_issued_claim_identity_must_be_nonblank_string(self):
        for context in ({}, *({"claim_id": value} for value in (
            None, "", " \t", 123, False, [], {},
        ))):
            with self.subTest(context=context):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        self.issue(context=context)
                        self.distribution()

    def test_issued_revision_must_be_integer_exactly_one(self):
        for state in ({"verdict": "FACT"}, *(
            {"verdict": "FACT", "revision_number": value}
            for value in (None, 0, -1, 2, True, False, 1.0, "1")
        )):
            with self.subTest(state=state):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        self.issue(new_state=state)
                        self.distribution()

    def test_issued_previous_revision_must_be_integer_exactly_zero(self):
        for state in ({"verdict": None}, *(
            {"verdict": None, "revision_number": value}
            for value in (None, -1, 1, True, False, 0.0, "0")
        )):
            with self.subTest(state=state):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        self.issue(previous_state=state)
                        self.distribution()

    def test_issued_previous_verdict_must_be_explicitly_none(self):
        for state in ({"revision_number": 0}, *(
            {"revision_number": 0, "verdict": value}
            for value in ("FACT", "FAKE", "", False, 0)
        )):
            with self.subTest(state=state):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        self.issue(previous_state=state)
                        self.distribution()

    def test_issued_verdict_must_be_authoritative(self):
        for state in ({"revision_number": 1}, *(
            {"revision_number": 1, "verdict": value}
            for value in (None, "UNVERIFIED", "UNKNOWN", "fact", "", 123, [], {})
        )):
            with self.subTest(state=state):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        self.issue(new_state=state)
                        self.distribution()

    def test_duplicate_issued_claim_fails_closed(self):
        self.issue(claim_id=self.claim_id)
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.issue(claim_id=self.claim_id)
                self.distribution()

    def test_duplicate_issued_decision_identity_fails_closed(self):
        self.issue(decision_id=self.decision_id)
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.issue(decision_id=self.decision_id)
                self.distribution()

    def test_revision_without_context_claim_replaces_observed_predecessor(self):
        self.issue(decision_id=self.decision_id)
        self.revise()
        self.assert_buckets(FAKE=1)

    def test_multiple_revisions_leave_only_terminal_verdict(self):
        self.issue(decision_id=self.decision_id)
        successor = self.revise(verdict="MISLEADING")
        self.revise(predecessor_id=successor.resource_id, previous_verdict="MISLEADING",
                    previous_revision=2, revision=3)
        self.assert_buckets(FAKE=1)

    def test_revision_from_unobserved_preinstrumentation_root_counts_only_successor(self):
        self.revise(previous_revision=7, revision=8, previous_verdict="MISLEADING", verdict="SATIRE")
        self.assert_buckets(SATIRE=1)

    def test_independent_external_and_observed_root_lineages_count_once_each(self):
        self.issue(decision_id=self.decision_id)
        self.revise()
        other = self.revise(predecessor_id=str(uuid.uuid4()), verdict="MISLEADING",
                            previous_revision=4, revision=5)
        self.revise(predecessor_id=other.resource_id, previous_verdict="MISLEADING",
                    previous_revision=5, revision=6, verdict="SATIRE")
        self.assert_buckets(FAKE=1, SATIRE=1)

    def test_revision_predecessor_and_successor_ids_are_required_nonblank_strings(self):
        for field in ("previous_state", "new_state"):
            for identity in (None, "", " \t", 123, False, [], {}):
                state = {"verdict": "FACT" if field == "previous_state" else "FAKE",
                         "revision_number": 1 if field == "previous_state" else 2}
                if identity is not None:
                    state["decision_id"] = identity
                with self.subTest(field=field, identity=identity):
                    with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                        with transaction.atomic():
                            self.revise(**{field: state})
                            self.distribution()

    def test_revision_resource_identity_must_match_new_decision(self):
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(resource_id=str(uuid.uuid4()))
                self.distribution()

    def test_revision_numbers_must_be_positive_integers_not_booleans(self):
        for field in ("previous_state", "new_state"):
            for value in (None, 0, -1, True, False, 1.0, 2.0, "2"):
                state = {"verdict": "FACT" if field == "previous_state" else "FAKE",
                         "decision_id": str(uuid.uuid4())}
                if value is not None:
                    state["revision_number"] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                        with transaction.atomic():
                            self.revise(**{field: state})
                            self.distribution()

    def test_revision_must_increment_previous_number_by_one(self):
        for revision in (1, 2, 4, 10):
            with self.subTest(revision=revision):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        self.revise(previous_revision=2, revision=revision)
                        self.distribution()

    def test_previous_and_new_revision_verdicts_must_be_authoritative(self):
        for argument in ("previous_verdict", "verdict"):
            for value in (None, "UNVERIFIED", "UNKNOWN", "fake", "", False, [], {}):
                with self.subTest(argument=argument, value=value):
                    with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                        with transaction.atomic():
                            self.revise(**{argument: value})
                            self.distribution()

    def test_observed_predecessor_verdict_mismatch_fails_closed(self):
        self.issue(decision_id=self.decision_id)
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(previous_verdict="SATIRE")
                self.distribution()

    def test_observed_predecessor_revision_mismatch_fails_closed(self):
        self.issue(decision_id=self.decision_id)
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(previous_revision=2, revision=3)
                self.distribution()

    def test_predecessor_fork_fails_for_observed_and_external_roots(self):
        for observed in (False, True):
            with self.subTest(observed=observed):
                with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                    with transaction.atomic():
                        if observed:
                            self.issue(decision_id=self.decision_id)
                        self.revise()
                        self.revise(verdict="SATIRE")
                        self.distribution()

    def test_new_decision_merge_or_duplicate_identity_fails_closed(self):
        first = self.revise()
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(predecessor_id=str(uuid.uuid4()), decision_id=first.resource_id)
                self.distribution()

    def test_duplicate_revision_event_fails_closed(self):
        first = self.revise()
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(decision_id=first.resource_id)
                self.distribution()

    def test_issued_identity_cannot_be_reintroduced_by_revision(self):
        self.issue(decision_id=self.decision_id)
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(predecessor_id=str(uuid.uuid4()), decision_id=self.decision_id)
                self.distribution()

    def test_self_loop_and_multi_node_cycle_fail_closed(self):
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.revise(decision_id=self.decision_id)
                self.distribution()
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                successor = self.revise()
                self.revise(predecessor_id=successor.resource_id, decision_id=self.decision_id,
                            previous_verdict="FAKE", previous_revision=2, revision=3)
                self.distribution()

    def test_predecessor_consistency_uses_complete_history_regardless_of_event_order(self):
        self.revise(at=self.at)
        self.issue(decision_id=self.decision_id, at=self.at + timedelta(seconds=1))
        self.assert_buckets(FAKE=1)

    def test_later_observed_predecessor_cannot_be_treated_as_external_to_hide_mismatch(self):
        self.revise(at=self.at)
        with self.assertRaises(VerificationResolutionMetricsIntegrityError):
            with transaction.atomic():
                self.issue(decision_id=self.decision_id, verdict="SATIRE",
                           at=self.at + timedelta(seconds=1))
                self.distribution()

    def test_exact_nonempty_contract_and_coverage_include_issue_and_revision_events(self):
        first_at = self.at - timedelta(days=1)
        last_at = self.at + timedelta(days=1)
        # Reverse insertion order exercises explicit event-time coverage ordering.
        self.revise(at=last_at)
        self.issue(decision_id=self.decision_id, at=first_at)
        self.issue(verdict="SATIRE", at=self.at)
        self.record(AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
                    resource_id=str(uuid.uuid4()),
                    resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
                    previous_state={}, new_state={}, context={}, at=last_at + timedelta(days=10))
        self.assertEqual(self.distribution(), {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "OBSERVED_AUTHORITATIVE_RESOLUTION_EVENTS_ONLY",
                "historical_backfill": False,
                "first_observed_resolution_at": first_at,
                "last_observed_resolution_at": last_at,
            },
            "latest_observed_resolutions": {
                "count": 2, "by_verdict": {"FACT": 0, "FAKE": 1, "MISLEADING": 0, "SATIRE": 1},
            },
        })

    def test_revision_only_coverage_begins_at_first_observed_revision(self):
        first = self.revise(previous_revision=3, revision=4, at=self.at)
        later = self.at + timedelta(seconds=10)
        self.revise(predecessor_id=first.resource_id, previous_verdict="FAKE",
                    previous_revision=4, revision=5, verdict="SATIRE", at=later)
        basis = self.distribution()["measurement_basis"]
        self.assertEqual(basis["first_observed_resolution_at"], self.at)
        self.assertEqual(basis["last_observed_resolution_at"], later)


class VerificationResolutionQueryBoundaryTests(SimpleTestCase):
    """No database access is allowed outside the mocked event-read boundary."""

    def setUp(self):
        self.organization = SimpleNamespace(pk=uuid.uuid4())
        self.at = datetime(2026, 9, 16, 8, tzinfo=timezone.utc)
        self.event = {
            "action_type": "VERDICT_ISSUED",
            "resource_type": "ADJUDICATION_DECISION",
            "resource_id": "observed-decision",
            "context": {"claim_id": "observed-claim"},
            "previous_state": {"verdict": None, "revision_number": 0},
            "new_state": {"verdict": "FACT", "revision_number": 1},
            "created_at": self.at,
        }

    def test_only_subject_scoped_ordered_accountability_events_are_queried(self):
        with patch("api.verification_resolution_metrics_service.AccountabilityEvent.objects.filter") as query:
            query.return_value.order_by.return_value.values.return_value = [self.event]
            result = get_organization_verification_resolution_distribution(organization=self.organization)
        query.assert_called_once_with(
            subject_organization=self.organization,
            action_type__in=(AccountabilityEvent.ActionType.VERDICT_ISSUED,
                             AccountabilityEvent.ActionType.VERDICT_REVISED),
        )
        query.return_value.order_by.assert_called_once_with("created_at", "id")
        self.assertEqual(result["latest_observed_resolutions"]["count"], 1)

    def test_nonstring_resource_identity_fails_without_mutable_fallback(self):
        # CharField storage normally yields strings; mock malformed candidate rows
        # to exercise the defensive type check without persisting coerced values.
        for identity in (None, 123, False, [], {}):
            with self.subTest(identity=identity):
                with patch("api.verification_resolution_metrics_service.AccountabilityEvent.objects.filter") as query:
                    query.return_value.order_by.return_value.values.return_value = [
                        {**self.event, "resource_id": identity},
                    ]
                    with self.assertRaises(VerificationResolutionMetricsIntegrityError):
                        get_organization_verification_resolution_distribution(organization=self.organization)
