import uuid
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import SimpleTestCase, TestCase

from api.accountability_service import record_accountability_event
from api.models import AccountabilityEvent, Organization
from api.organization_service import PartnerCapability
from api.verification_activity_metrics_service import (
    VerificationActivityMetricsIntegrityError,
    get_organization_verification_activity,
    project_organization_verification_activity_events,
)
from api.verification_activity_trends_service import (
    VerificationActivityTrendInputError,
    get_organization_verification_activity_trend,
)
from api.verification_metrics_service import VerificationMetricsIntegrityError


ASSIGNMENT_PATCH = (
    "api.verification_activity_trends_service.project_organization_assignment_lifecycles"
)
ACTIVITY_PATCH = (
    "api.verification_activity_trends_service.project_organization_verification_activity_events"
)


def zero_counts():
    return {
        "assignment": {"claimed": 0, "released": 0, "completed": 0},
        "evidence_review": {"decisions": 0, "verified": 0, "rejected": 0},
        "adjudication": {"started": 0, "verdicts_issued": 0},
        "publication": {"initial_published": 0},
    }


class OrdinaryActivityEventProjectionTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Trend Projection Partner", slug="trend-projection-partner",
        )
        self.other_organization = Organization.objects.create(
            name="Other Trend Partner", slug="other-trend-partner",
        )
        self.actor = User.objects.create_user(username="trend-projection-actor")
        self.claim_id = str(uuid.uuid4())
        self.at = datetime(2026, 9, 15, 10, 0, 0, 123456, tzinfo=timezone.utc)
        actions = AccountabilityEvent.ActionType
        resources = AccountabilityEvent.ResourceType
        self.selected_types = {
            actions.EVIDENCE_VERIFIED: (resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE),
            actions.EVIDENCE_REJECTED: (resources.EVIDENCE_SUBMISSION, PartnerCapability.REVIEW_EVIDENCE),
            actions.ADJUDICATION_STARTED: (resources.MODERATION_CASE, PartnerCapability.ADJUDICATE),
            actions.VERDICT_ISSUED: (resources.ADJUDICATION_DECISION, PartnerCapability.ADJUDICATE),
            actions.ARTICLE_PUBLISHED: (resources.OFFICIAL_FACT_CHECK, PartnerCapability.PUBLISH_FACT_CHECK),
        }

    def record(self, action, *, at=None, **overrides):
        resource_type, capability = self.selected_types.get(action, (
            AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
            PartnerCapability.PUBLISH_FACT_CHECK,
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
            "authority_organization": self.organization,
            "subject_organization": self.organization,
            "capability": capability,
            "context": context,
        }
        values.update(overrides)
        # Supply fixture timestamps at insertion; never update append-only rows.
        with patch("django.utils.timezone.now", return_value=at or self.at):
            return record_accountability_event(**values)

    def project(self):
        with self.assertNumQueries(1):
            return project_organization_verification_activity_events(
                organization=self.organization,
            )

    def test_empty_projection_and_summary_preserve_exact_contract(self):
        self.assertEqual(self.project(), [])
        with self.assertNumQueries(1):
            summary = get_organization_verification_activity(organization=self.organization)
        self.assertEqual(summary, {
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
        })

    def test_projection_exact_fields_and_order_by_timestamp_then_event_id(self):
        actions = AccountabilityEvent.ActionType
        later = self.at + timedelta(seconds=1)
        earlier = self.at - timedelta(seconds=1)
        self.record(actions.ARTICLE_PUBLISHED, at=later)
        # Control UUID defaults at insertion while retaining recorder validation.
        id_field = AccountabilityEvent._meta.get_field("id")
        for identifier, action in (
            (3, actions.EVIDENCE_VERIFIED),
            (1, actions.EVIDENCE_REJECTED),
            (2, actions.EVIDENCE_VERIFIED),
        ):
            with patch.object(id_field, "_get_default", return_value=uuid.UUID(int=identifier)):
                self.record(action)
        self.record(actions.VERDICT_ISSUED, at=earlier)
        self.assertEqual(self.project(), [
            {"action_type": action, "claim_id": self.claim_id, "created_at": at}
            for action, at in (
                (actions.VERDICT_ISSUED, earlier),
                (actions.EVIDENCE_REJECTED, self.at),
                (actions.EVIDENCE_VERIFIED, self.at),
                (actions.EVIDENCE_VERIFIED, self.at),
                (actions.ARTICLE_PUBLISHED, later),
            )
        ])

    def test_summary_delegates_to_projector_and_preserves_nonempty_contract(self):
        actions = AccountabilityEvent.ActionType
        later = self.at + timedelta(seconds=5)
        projected = [
            {"action_type": action, "claim_id": self.claim_id, "created_at": at}
            for action, at in (
                (actions.EVIDENCE_VERIFIED, self.at),
                (actions.EVIDENCE_REJECTED, self.at),
                (actions.EVIDENCE_VERIFIED, self.at),
                (actions.ADJUDICATION_STARTED, self.at),
                (actions.VERDICT_ISSUED, self.at),
                (actions.ARTICLE_PUBLISHED, later),
            )
        ]
        with patch(
            "api.verification_activity_metrics_service.project_organization_verification_activity_events",
            return_value=projected,
        ) as projector, self.assertNumQueries(0):
            summary = get_organization_verification_activity(organization=self.organization)
        projector.assert_called_once_with(organization=self.organization)
        self.assertEqual(summary, {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_activity_at": self.at,
                "last_observed_activity_at": later,
            },
            "evidence_review": {"decisions": 3, "verified": 2, "rejected": 1},
            "adjudication": {"started": 1, "verdicts_issued": 1},
            "publication": {"initial_published": 1},
        })

    def test_correction_evidence_is_excluded_after_integrity_validation(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED):
            for correction_id in (str(uuid.uuid4()), None, "", False):
                self.record(action, context={
                    "claim_id": self.claim_id, "correction_request_id": correction_id,
                })
        self.assertEqual(self.project(), [])
        for overrides in (
            {"context": {"correction_request_id": str(uuid.uuid4())}},
            {"context": {"claim_id": self.claim_id, "correction_request_id": None},
             "resource_type": AccountabilityEvent.ResourceType.THREAD},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(actions.EVIDENCE_VERIFIED, **overrides)
                        self.project()

    def test_repeated_evidence_decisions_are_preserved_as_distinct_events(self):
        actions = AccountabilityEvent.ActionType
        evidence_id = str(uuid.uuid4())
        self.record(actions.EVIDENCE_VERIFIED, resource_id=evidence_id)
        self.record(actions.EVIDENCE_REOPENED, resource_id=evidence_id,
                    resource_type=AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
                    capability=PartnerCapability.REVIEW_EVIDENCE)
        self.record(actions.EVIDENCE_REJECTED, resource_id=evidence_id)
        self.record(actions.EVIDENCE_VERIFIED, resource_id=evidence_id)
        self.assertEqual(len(self.project()), 3)

    def test_selected_resource_and_claim_integrity_rules_remain_fail_closed(self):
        for action in self.selected_types:
            for overrides in (
                {"resource_type": AccountabilityEvent.ResourceType.THREAD},
                *({"context": {"revision_kind": "INITIAL", **identity}} for identity in (
                    {}, {"claim_id": None}, {"claim_id": ""}, {"claim_id": " \t"},
                    {"claim_id": 123}, {"claim_id": False},
                )),
            ):
                with self.subTest(action=action, overrides=overrides):
                    with self.assertRaises(VerificationActivityMetricsIntegrityError):
                        with transaction.atomic():
                            self.record(action, **overrides)
                            self.project()

    def test_initial_publication_requires_exact_revision_kind(self):
        for extra_context in ({}, *({"revision_kind": value} for value in (
            None, "", " \t", "initial", "EDITORIAL_REVISION", "FACTUAL_CORRECTION", 123,
        ))):
            with self.subTest(extra_context=extra_context):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
                                    context={"claim_id": self.claim_id, **extra_context})
                        self.project()

    def test_duplicate_first_activity_histories_fail_even_outside_trend_window(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.ADJUDICATION_STARTED, actions.VERDICT_ISSUED,
                       actions.ARTICLE_PUBLISHED):
            with self.subTest(action=action):
                with self.assertRaises(VerificationActivityMetricsIntegrityError):
                    with transaction.atomic():
                        self.record(action, at=self.at - timedelta(days=100))
                        self.record(action, at=self.at - timedelta(days=99))
                        get_organization_verification_activity_trend(
                            organization=self.organization,
                            created_after=self.at, created_before=self.at + timedelta(hours=1),
                        )

    def test_malformed_assignment_history_outside_window_fails_closed(self):
        with self.assertRaises(VerificationMetricsIntegrityError):
            with transaction.atomic():
                self.record(AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_COMPLETED,
                            at=self.at - timedelta(days=100),
                            resource_type=AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
                            authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
                            actor=None, authority_organization=None, capability="")
                get_organization_verification_activity_trend(
                    organization=self.organization,
                    created_after=self.at, created_before=self.at + timedelta(hours=1),
                )

    def test_nonobject_historical_context_still_raises_projector_integrity_error(self):
        with self.assertRaises(VerificationActivityMetricsIntegrityError):
            with transaction.atomic():
                # The normal recorder rejects non-object context; simulate malformed history.
                AccountabilityEvent.objects.create(
                    action_type=AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
                    resource_type=AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
                    resource_id=str(uuid.uuid4()),
                    authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
                    actor=self.actor, authority_organization=self.organization,
                    subject_organization=self.organization,
                    capability=PartnerCapability.REVIEW_EVIDENCE, context=[],
                )
                self.project()

    def test_excluded_activity_and_other_tenant_history_never_enter_trend(self):
        actions = AccountabilityEvent.ActionType
        for action in (actions.EVIDENCE_VERIFIED, actions.EVIDENCE_REJECTED):
            self.record(action, context={
                "claim_id": self.claim_id, "correction_request_id": str(uuid.uuid4()),
            })
        for action in (actions.ARTICLE_REVISED, actions.FACTUAL_CORRECTION_PUBLISHED,
                       actions.VERDICT_REVISED, actions.ARTICLE_DRAFT_SAVED,
                       actions.ARTICLE_SUBMITTED, actions.ARTICLE_RETURNED_FOR_REWORK,
                       actions.ARTICLE_REVISION_DRAFTED):
            resource_type = (
                AccountabilityEvent.ResourceType.ADJUDICATION_DECISION
                if action == actions.VERDICT_REVISED
                else AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK
            )
            capability = (
                PartnerCapability.ADJUDICATE if action == actions.VERDICT_REVISED
                else PartnerCapability.PUBLISH_FACT_CHECK
            )
            self.record(action, resource_type=resource_type, capability=capability)
        self.record(actions.EVIDENCE_VERIFIED, subject_organization=self.other_organization,
                    resource_type=AccountabilityEvent.ResourceType.THREAD, context={})
        self.assertEqual(self.project(), [])
        with self.assertNumQueries(2):
            result = get_organization_verification_activity_trend(
                organization=self.organization,
                created_after=self.at, created_before=self.at + timedelta(hours=1),
            )
        self.assertEqual(result["totals"], zero_counts())
        self.assertEqual(result["daily"], [{"date": "2026-09-15", **zero_counts()}])


class VerificationActivityTrendTests(SimpleTestCase):
    """All database access is forbidden while testing projection consumption."""

    def setUp(self):
        self.organization = SimpleNamespace(pk=uuid.uuid4())
        self.claim_id = str(uuid.uuid4())
        self.start = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
        self.end = datetime(2026, 9, 17, 12, tzinfo=timezone.utc)

    def attempt(self, *, claimed_at=None, terminal_at=None, status="ACTIVE"):
        claimed_at = self.start if claimed_at is None else claimed_at
        return {
            "assignment_id": str(uuid.uuid4()),
            "claim_id": self.claim_id,
            "organization_id": str(self.organization.pk),
            "status": status,
            "claimed_at": claimed_at,
            "terminal_at": terminal_at,
            "duration_seconds": (
                (terminal_at - claimed_at).total_seconds() if terminal_at is not None else None
            ),
        }

    def event(self, action, *, at=None):
        return {
            "action_type": action, "claim_id": self.claim_id,
            "created_at": self.start if at is None else at,
        }

    def trend(self, *, attempts=(), activity=(), **overrides):
        kwargs = {"created_after": self.start, "created_before": self.end, **overrides}
        original_attempts = deepcopy(attempts)
        original_activity = deepcopy(activity)
        with (
            patch(ASSIGNMENT_PATCH, return_value=attempts) as assignment_projection,
            patch(ACTIVITY_PATCH, return_value=activity) as activity_projection,
        ):
            result = get_organization_verification_activity_trend(
                organization=self.organization, **kwargs,
            )
        assignment_projection.assert_called_once_with(organization=self.organization)
        activity_projection.assert_called_once_with(organization=self.organization)
        self.assertEqual(attempts, original_attempts)
        self.assertEqual(activity, original_activity)
        self.assertEqual(set(result), {"organization_id", "measurement_basis", "totals", "daily"})
        self.assertEqual(set(result["measurement_basis"]), {
            "source", "coverage", "historical_backfill", "granularity",
            "bucket_timezone", "created_after", "created_before",
        })
        for bucket in result["daily"]:
            self.assertEqual(set(bucket), {"date", *zero_counts()})
            for section, fields in zero_counts().items():
                self.assertEqual(set(bucket[section]), set(fields))
            review = bucket["evidence_review"]
            self.assertEqual(review["decisions"], review["verified"] + review["rejected"])
        self.assertEqual(set(result["totals"]), set(zero_counts()))
        for section, fields in zero_counts().items():
            self.assertEqual(set(result["totals"][section]), set(fields))
            for field in fields:
                self.assertEqual(result["totals"][section][field], sum(
                    bucket[section][field] for bucket in result["daily"]
                ))
        review = result["totals"]["evidence_review"]
        self.assertEqual(review["decisions"], review["verified"] + review["rejected"])
        return result

    def assert_input_error(self, **kwargs):
        with patch(ASSIGNMENT_PATCH) as assignments, patch(ACTIVITY_PATCH) as activity:
            with self.assertRaises(VerificationActivityTrendInputError):
                get_organization_verification_activity_trend(
                    organization=self.organization, **kwargs,
                )
        assignments.assert_not_called()
        activity.assert_not_called()

    def test_missing_created_after_is_input_error(self):
        self.assert_input_error(created_before=self.end)

    def test_missing_created_before_is_input_error(self):
        self.assert_input_error(created_after=self.start)

    def test_both_missing_boundaries_are_input_error(self):
        self.assert_input_error()

    def test_non_datetime_boundaries_are_input_errors(self):
        for boundary in ("created_after", "created_before"):
            for value in (None, "2026-09-15T10:00:00Z", date(2026, 9, 15), 123, False):
                with self.subTest(boundary=boundary, value=value):
                    kwargs = {"created_after": self.start, "created_before": self.end}
                    kwargs[boundary] = value
                    self.assert_input_error(**kwargs)

    def test_naive_datetime_boundaries_are_input_errors(self):
        for boundary in ("created_after", "created_before"):
            with self.subTest(boundary=boundary):
                kwargs = {"created_after": self.start, "created_before": self.end}
                kwargs[boundary] = self.start.replace(tzinfo=None)
                self.assert_input_error(**kwargs)

    def test_reversed_window_is_input_error(self):
        self.assert_input_error(created_after=self.end, created_before=self.start)

    def test_reversed_offset_window_is_checked_in_utc(self):
        after = datetime(2026, 9, 15, 10, tzinfo=timezone(timedelta(hours=-5)))
        before = datetime(2026, 9, 15, 11, tzinfo=timezone(timedelta(hours=5)))
        self.assert_input_error(created_after=after, created_before=before)

    def test_empty_valid_window_returns_exact_continuous_zero_contract(self):
        self.assertEqual(self.trend(), {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "granularity": "DAY", "bucket_timezone": "UTC",
                "created_after": self.start, "created_before": self.end,
            },
            "totals": zero_counts(),
            "daily": [
                {"date": value, **zero_counts()}
                for value in ("2026-09-15", "2026-09-16", "2026-09-17")
            ],
        })

    def test_same_day_partial_window_has_exactly_one_bucket(self):
        start = self.start.replace(hour=12)
        result = self.trend(created_after=start, created_before=start + timedelta(hours=1))
        self.assertEqual(result["daily"], [{"date": "2026-09-15", **zero_counts()}])

    def test_equal_boundaries_include_only_events_at_that_instant(self):
        epsilon = timedelta(microseconds=1)
        result = self.trend(
            created_before=self.start,
            attempts=[self.attempt(status="RELEASED", terminal_at=self.start)],
            activity=[self.event("EVIDENCE_VERIFIED", at=at) for at in (
                self.start - epsilon, self.start, self.start + epsilon,
            )],
        )
        self.assertEqual(len(result["daily"]), 1)
        self.assertEqual(result["totals"]["assignment"], {"claimed": 1, "released": 1, "completed": 0})
        self.assertEqual(result["totals"]["evidence_review"], {"decisions": 1, "verified": 1, "rejected": 0})

    def test_both_window_boundaries_are_inclusive(self):
        epsilon = timedelta(microseconds=1)
        timestamps = (self.start - epsilon, self.start, self.end, self.end + epsilon)
        result = self.trend(
            attempts=[self.attempt(claimed_at=at) for at in timestamps],
            activity=[self.event("EVIDENCE_VERIFIED", at=at) for at in timestamps],
        )
        self.assertEqual(result["totals"]["assignment"]["claimed"], 2)
        self.assertEqual(result["totals"]["evidence_review"]["verified"], 2)
        self.assertEqual(result["daily"][0]["assignment"]["claimed"], 1)
        self.assertEqual(result["daily"][2]["assignment"]["claimed"], 1)

    def test_offset_boundaries_and_projected_timestamps_are_bucketed_in_utc(self):
        after = datetime(2026, 9, 16, 0, tzinfo=timezone(timedelta(hours=14)))
        before = datetime(2026, 9, 17, 7, tzinfo=timezone(timedelta(hours=-5)))
        event_at = datetime(2026, 9, 16, 0, 30, tzinfo=timezone(timedelta(hours=2)))
        result = self.trend(
            created_after=after, created_before=before,
            attempts=[self.attempt(claimed_at=event_at)],
            activity=[self.event("EVIDENCE_VERIFIED", at=event_at)],
        )
        self.assertEqual(result["measurement_basis"]["created_after"], self.start)
        self.assertEqual(result["measurement_basis"]["created_before"], self.end)
        self.assertIs(result["measurement_basis"]["created_after"].tzinfo, timezone.utc)
        self.assertIs(result["measurement_basis"]["created_before"].tzinfo, timezone.utc)
        self.assertEqual([bucket["date"] for bucket in result["daily"]], [
            "2026-09-15", "2026-09-16", "2026-09-17",
        ])
        self.assertEqual(result["daily"][0]["assignment"]["claimed"], 1)
        self.assertEqual(result["daily"][0]["evidence_review"]["verified"], 1)
        self.assertEqual(result["daily"][1]["assignment"]["claimed"], 0)

    def test_claimed_and_released_are_bucketed_by_their_own_timestamps(self):
        terminal = self.start + timedelta(days=1)
        result = self.trend(attempts=[self.attempt(status="RELEASED", terminal_at=terminal)])
        self.assertEqual(result["daily"][0]["assignment"], {"claimed": 1, "released": 0, "completed": 0})
        self.assertEqual(result["daily"][1]["assignment"], {"claimed": 0, "released": 1, "completed": 0})

    def test_completion_is_bucketed_by_terminal_time_even_if_claim_precedes_window(self):
        result = self.trend(attempts=[self.attempt(
            claimed_at=self.start - timedelta(days=10), status="COMPLETED", terminal_at=self.end,
        )])
        self.assertEqual(result["totals"]["assignment"], {"claimed": 0, "released": 0, "completed": 1})
        self.assertEqual(result["daily"][2]["assignment"]["completed"], 1)

    def test_terminal_events_outside_window_are_excluded_independently_of_claim(self):
        result = self.trend(attempts=[
            self.attempt(status="RELEASED", terminal_at=self.end + timedelta(microseconds=1)),
            self.attempt(status="COMPLETED", terminal_at=self.end + timedelta(days=1)),
        ])
        self.assertEqual(result["totals"]["assignment"], {"claimed": 2, "released": 0, "completed": 0})

    def test_active_attempts_only_generate_claim_events(self):
        result = self.trend(attempts=[self.attempt()])
        self.assertEqual(result["totals"]["assignment"], {"claimed": 1, "released": 0, "completed": 0})
        self.assertEqual(result["daily"][1]["assignment"], zero_counts()["assignment"])
        self.assertEqual(result["daily"][2]["assignment"], zero_counts()["assignment"])

    def test_released_then_reclaimed_same_claim_remains_distinct_claim_events(self):
        result = self.trend(attempts=[
            self.attempt(status="RELEASED", terminal_at=self.start + timedelta(hours=1)),
            self.attempt(claimed_at=self.start + timedelta(days=1)),
        ])
        self.assertEqual(result["totals"]["assignment"], {"claimed": 2, "released": 1, "completed": 0})
        self.assertEqual(result["daily"][0]["assignment"]["claimed"], 1)
        self.assertEqual(result["daily"][1]["assignment"]["claimed"], 1)

    def test_evidence_decision_mapping_preserves_repeated_events_and_invariant(self):
        result = self.trend(activity=[
            self.event("EVIDENCE_VERIFIED"), self.event("EVIDENCE_REJECTED"),
            self.event("EVIDENCE_VERIFIED", at=self.end),
        ])
        self.assertEqual(result["totals"]["evidence_review"], {"decisions": 3, "verified": 2, "rejected": 1})
        self.assertEqual(result["daily"][0]["evidence_review"], {"decisions": 2, "verified": 1, "rejected": 1})
        self.assertEqual(result["daily"][2]["evidence_review"], {"decisions": 1, "verified": 1, "rejected": 0})

    def test_adjudication_start_and_verdict_mapping_are_independent(self):
        result = self.trend(activity=[
            self.event("ADJUDICATION_STARTED"), self.event("VERDICT_ISSUED", at=self.end),
        ])
        self.assertEqual(result["totals"]["adjudication"], {"started": 1, "verdicts_issued": 1})
        self.assertEqual(result["daily"][0]["adjudication"], {"started": 1, "verdicts_issued": 0})
        self.assertEqual(result["daily"][2]["adjudication"], {"started": 0, "verdicts_issued": 1})

    def test_initial_publication_maps_to_its_daily_event_time(self):
        result = self.trend(activity=[self.event("ARTICLE_PUBLISHED", at=self.end)])
        self.assertEqual(result["totals"]["publication"], {"initial_published": 1})
        self.assertEqual(result["daily"][0]["publication"], {"initial_published": 0})
        self.assertEqual(result["daily"][2]["publication"], {"initial_published": 1})

    def test_empty_in_window_activity_keeps_all_zero_dates(self):
        before = self.start - timedelta(microseconds=1)
        after = self.end + timedelta(microseconds=1)
        result = self.trend(
            attempts=[self.attempt(claimed_at=before, status="COMPLETED", terminal_at=before),
                      self.attempt(claimed_at=after)],
            activity=[self.event("EVIDENCE_REJECTED", at=before),
                      self.event("ARTICLE_PUBLISHED", at=after)],
        )
        self.assertEqual(result["totals"], zero_counts())
        self.assertEqual(result["daily"], [
            {"date": value, **zero_counts()}
            for value in ("2026-09-15", "2026-09-16", "2026-09-17")
        ])

    def test_totals_sum_mixed_daily_activity_with_zero_day_between(self):
        result = self.trend(
            attempts=[self.attempt(status="COMPLETED", terminal_at=self.end)],
            activity=[self.event(action, at=at) for action, at in (
                ("EVIDENCE_VERIFIED", self.start), ("EVIDENCE_REJECTED", self.end),
                ("ADJUDICATION_STARTED", self.start), ("VERDICT_ISSUED", self.end),
                ("ARTICLE_PUBLISHED", self.end),
            )],
        )
        self.assertEqual(result["daily"][1], {"date": "2026-09-16", **zero_counts()})
        self.assertEqual(result["totals"], {
            "assignment": {"claimed": 1, "released": 0, "completed": 1},
            "evidence_review": {"decisions": 2, "verified": 1, "rejected": 1},
            "adjudication": {"started": 1, "verdicts_issued": 1},
            "publication": {"initial_published": 1},
        })

    def test_assignment_integrity_error_propagates_by_identity(self):
        error = VerificationMetricsIntegrityError("Malformed assignment history.")
        with patch(ASSIGNMENT_PATCH, side_effect=error), patch(ACTIVITY_PATCH) as activity:
            with self.assertRaises(VerificationMetricsIntegrityError) as raised:
                get_organization_verification_activity_trend(
                    organization=self.organization,
                    created_after=self.start, created_before=self.end,
                )
        self.assertIs(raised.exception, error)
        activity.assert_not_called()

    def test_activity_integrity_error_propagates_by_identity(self):
        error = VerificationActivityMetricsIntegrityError("Malformed first-decision history.")
        with (
            patch(ASSIGNMENT_PATCH, return_value=[self.attempt()]) as assignments,
            patch(ACTIVITY_PATCH, side_effect=error),
        ):
            with self.assertRaises(VerificationActivityMetricsIntegrityError) as raised:
                get_organization_verification_activity_trend(
                    organization=self.organization,
                    created_after=self.start, created_before=self.end,
                )
        self.assertIs(raised.exception, error)
        assignments.assert_called_once_with(organization=self.organization)

    def test_trend_consumes_only_projections_without_database_or_clock_access(self):
        # SimpleTestCase rejects every database query, including domain-row fallback.
        with patch("django.utils.timezone.now", side_effect=AssertionError("Wall clock used.")):
            result = self.trend(attempts=[self.attempt()], activity=[self.event("EVIDENCE_VERIFIED")])
        self.assertEqual(result["totals"]["assignment"]["claimed"], 1)
        self.assertEqual(result["totals"]["evidence_review"]["verified"], 1)
