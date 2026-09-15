import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import call, patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from api.models import Organization, OrganizationMembership, UserProfile
from api.organization_service import PartnerCapability
from api.verification_metrics_query_service import (
    VerificationMetricsAuthorizationError,
    VerificationMetricsCompositionError,
    get_organization_verification_metrics,
)
from api.verification_metrics_service import VerificationMetricsIntegrityError
from api.verification_activity_metrics_service import VerificationActivityMetricsIntegrityError
from api.verification_activity_trends_service import VerificationActivityTrendInputError


BASELINE_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_baseline"
)
ACTIVITY_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_activity"
)
TREND_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_activity_trend"
)


class VerificationMetricsApiTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Metrics Partner",
            slug="metrics-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other Metrics Partner",
            slug="other-metrics-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.members = {}
        for role in (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
            OrganizationMembership.Role.CONTRIBUTOR,
            OrganizationMembership.Role.RESEARCHER,
            OrganizationMembership.Role.MODERATOR,
        ):
            actor = User.objects.create_user(username=f"metrics-{role.lower()}")
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=actor,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )
            self.members[role] = actor
        self.outsider = User.objects.create_user(username="metrics-outsider")
        self.safety_moderator = User.objects.create_user(username="metrics-safety-mod")
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])
        self.url = self.metrics_url(self.organization.pk)
        self.baseline = {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_claimed_at": datetime(
                    2026, 9, 15, 8, 0, 0, 123456, tzinfo=timezone.utc,
                ),
                "last_observed_claimed_at": datetime(
                    2026, 9, 15, 9, 0, 0, 654321, tzinfo=timezone.utc,
                ),
            },
            "attempts": {
                "claimed": 5, "active": 2, "released": 1, "completed": 2, "terminal": 3,
            },
            "reliability": {
                "terminal_completion_rate": 2 / 3,
                "terminal_release_rate": 1 / 3,
            },
            "completed_turnaround": {
                "count": 2,
                "average_seconds": 5.9375,
                "median_seconds": 5.9375,
                "minimum_seconds": 1.625,
                "maximum_seconds": 10.25,
            },
        }
        self.activity_payload = {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_activity_at": datetime(
                    2026, 9, 15, 10, 0, 0, 234567, tzinfo=timezone.utc,
                ),
                "last_observed_activity_at": datetime(
                    2026, 9, 15, 11, 0, 0, 765432, tzinfo=timezone.utc,
                ),
            },
            "evidence_review": {"decisions": 7, "verified": 3, "rejected": 4},
            "adjudication": {"started": 2, "verdicts_issued": 1},
            "publication": {"initial_published": 1},
        }
        # Windowed fixture activity differs from the earlier full-history summaries.
        self.created_after = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
        self.created_before = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
        self.window = {
            "created_after": "2026-09-20T10:00:00Z",
            "created_before": "2026-09-22T12:00:00Z",
        }
        totals = {
            "assignment": {"claimed": 1, "released": 0, "completed": 0},
            "evidence_review": {"decisions": 1, "verified": 1, "rejected": 0},
            "adjudication": {"started": 0, "verdicts_issued": 0},
            "publication": {"initial_published": 0},
        }
        zeros = {section: dict.fromkeys(fields, 0) for section, fields in totals.items()}
        self.trend_payload = {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "granularity": "DAY",
                "bucket_timezone": "UTC",
                "created_after": self.created_after,
                "created_before": self.created_before,
            },
            "totals": totals,
            "daily": [
                {"date": "2026-09-20", **deepcopy(totals)},
                {"date": "2026-09-21", **deepcopy(zeros)},
                {"date": "2026-09-22", **deepcopy(zeros)},
            ],
        }

    def expected_payload(self):
        return {
            **self.baseline,
            "activity": {
                "measurement_basis": self.activity_payload["measurement_basis"],
                "evidence_review": self.activity_payload["evidence_review"],
                "adjudication": self.activity_payload["adjudication"],
                "publication": self.activity_payload["publication"],
            },
        }

    def metrics_url(self, organization_id):
        return reverse(
            "organization_verification_metrics",
            kwargs={"organization_id": organization_id},
        )

    def request_metrics(self, actor, *, url=None, params=None):
        client = APIClient()
        client.force_authenticate(user=actor)
        return client.get(self.url if url is None else url, data=params or {})

    def assert_allowed(self, actor):
        original_baseline = deepcopy(self.baseline)
        original_activity = deepcopy(self.activity_payload)
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(actor)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.expected_payload())
        self.assertIsNot(response.data, self.baseline)
        self.assertIsNot(response.data["activity"], self.activity_payload)
        self.assertEqual(self.baseline, original_baseline)
        self.assertEqual(self.activity_payload, original_activity)
        self.assertEqual(set(response.data), {
            "organization_id", "measurement_basis", "attempts", "reliability",
            "completed_turnaround", "activity",
        })
        self.assertEqual(set(response.data["activity"]), {
            "measurement_basis", "evidence_review", "adjudication", "publication",
        })
        for key, value in self.baseline.items():
            self.assertEqual(response.data[key], value)
        self.assertEqual(response.data["activity"]["measurement_basis"],
                         original_activity["measurement_basis"])
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_called_once_with(organization=self.organization)
        trend.assert_not_called()
        return response

    def assert_forbidden(self, actor, *, url=None, params=None):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(actor, url=url, params=params)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.data), {"detail"})
        baseline.assert_not_called()
        activity.assert_not_called()
        trend.assert_not_called()

    def test_unauthenticated_request_returns_401(self):
        for params in ({}, self.window):
            with (
                self.subTest(params=params),
                patch(BASELINE_PATCH) as baseline,
                patch(ACTIVITY_PATCH) as activity,
                patch(TREND_PATCH) as trend,
            ):
                response = APIClient().get(self.url, data=params)
                self.assertEqual(response.status_code, 401)
                baseline.assert_not_called()
                activity.assert_not_called()
                trend.assert_not_called()

    def test_owner_can_read_metrics(self):
        self.assert_allowed(self.members[OrganizationMembership.Role.OWNER])

    def test_admin_can_read_metrics(self):
        self.assert_allowed(self.members[OrganizationMembership.Role.ADMIN])

    def test_lead_verifier_can_read_metrics(self):
        self.assert_allowed(self.members[OrganizationMembership.Role.LEAD_VERIFIER])

    def test_contributor_is_forbidden(self):
        self.assert_forbidden(self.members[OrganizationMembership.Role.CONTRIBUTOR])

    def test_researcher_is_forbidden(self):
        self.assert_forbidden(self.members[OrganizationMembership.Role.RESEARCHER])

    def test_organization_moderator_is_forbidden(self):
        self.assert_forbidden(self.members[OrganizationMembership.Role.MODERATOR])

    def test_platform_safety_moderator_is_forbidden(self):
        self.assert_forbidden(self.safety_moderator)

    def test_outsider_is_forbidden(self):
        self.assert_forbidden(self.outsider)

    def assert_inactive_memberships_forbidden(self, membership_status, *, params=None):
        for role in (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
        ):
            with self.subTest(role=role):
                actor = self.members[role]
                membership = OrganizationMembership.objects.get(
                    organization=self.organization, user=actor,
                )
                membership.status = membership_status
                membership.save(update_fields=["status"])
                self.assert_forbidden(actor, params=params)

    def test_suspended_membership_is_forbidden(self):
        self.assert_inactive_memberships_forbidden(OrganizationMembership.Status.SUSPENDED)

    def test_left_membership_is_forbidden(self):
        self.assert_inactive_memberships_forbidden(OrganizationMembership.Status.LEFT)

    def test_qualifying_capabilities_do_not_cross_organizations(self):
        for role in (
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
        ):
            with self.subTest(role=role):
                actor = self.members[role]
                OrganizationMembership.objects.create(
                    organization=self.other_organization,
                    user=actor,
                    role=OrganizationMembership.Role.CONTRIBUTOR,
                    status=OrganizationMembership.Status.ACTIVE,
                )
                self.assert_allowed(actor)
                self.assert_forbidden(
                    actor, url=self.metrics_url(self.other_organization.pk),
                )

    def test_unknown_organization_returns_404(self):
        with patch(BASELINE_PATCH) as baseline, patch(ACTIVITY_PATCH) as activity:
            response = self.request_metrics(
                self.members[OrganizationMembership.Role.OWNER],
                url=self.metrics_url(uuid.uuid4()),
            )
        self.assertEqual(response.status_code, 404)
        baseline.assert_not_called()
        activity.assert_not_called()

    def test_success_preserves_baseline_and_activity_coverage_on_the_wire(self):
        response = self.assert_allowed(self.members[OrganizationMembership.Role.OWNER])
        expected = {
            **self.expected_payload(),
            "measurement_basis": {
                **self.baseline["measurement_basis"],
                "first_observed_claimed_at": "2026-09-15T08:00:00.123456Z",
                "last_observed_claimed_at": "2026-09-15T09:00:00.654321Z",
            },
            "activity": {
                **self.expected_payload()["activity"],
                "measurement_basis": {
                    **self.activity_payload["measurement_basis"],
                    "first_observed_activity_at": "2026-09-15T10:00:00.234567Z",
                    "last_observed_activity_at": "2026-09-15T11:00:00.765432Z",
                },
            },
        }
        self.assertEqual(response.json(), expected)

    def test_empty_baseline_and_activity_preserve_zero_counts_and_nulls(self):
        self.baseline["measurement_basis"]["first_observed_claimed_at"] = None
        self.baseline["measurement_basis"]["last_observed_claimed_at"] = None
        self.baseline["attempts"] = dict.fromkeys(self.baseline["attempts"], 0)
        self.baseline["reliability"] = dict.fromkeys(self.baseline["reliability"])
        self.baseline["completed_turnaround"] = {
            "count": 0,
            "average_seconds": None,
            "median_seconds": None,
            "minimum_seconds": None,
            "maximum_seconds": None,
        }
        self.activity_payload["measurement_basis"]["first_observed_activity_at"] = None
        self.activity_payload["measurement_basis"]["last_observed_activity_at"] = None
        self.activity_payload["evidence_review"] = {"decisions": 0, "verified": 0, "rejected": 0}
        self.activity_payload["adjudication"] = {"started": 0, "verdicts_issued": 0}
        self.activity_payload["publication"] = {"initial_published": 0}
        response = self.assert_allowed(self.members[OrganizationMembership.Role.ADMIN])
        self.assertEqual(response.json(), self.expected_payload())

    def test_integrity_error_returns_generic_503_without_partial_metrics(self):
        error = VerificationMetricsIntegrityError(
            "Assignment internal-assignment-id has malformed event details."
        )
        with (
            patch(BASELINE_PATCH, side_effect=error) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "detail": "Verification metrics are temporarily unavailable.",
        })
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_not_called()
        log_exception.assert_called_once_with(
            "Organization verification metrics projection failed."
        )

    def assert_generic_unavailable(self, response, log_exception):
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "detail": "Verification metrics are temporarily unavailable.",
        })
        log_exception.assert_called_once_with(
            "Organization verification metrics projection failed."
        )

    def test_activity_integrity_error_returns_503_without_valid_baseline(self):
        error = VerificationActivityMetricsIntegrityError(
            "Claim internal-claim-id has duplicate history at internal-event-id."
        )
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, side_effect=error) as activity,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assert_generic_unavailable(response, log_exception)
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_called_once_with(organization=self.organization)

    def test_composition_error_returns_generic_503_without_partial_metrics(self):
        error = VerificationMetricsCompositionError("Internal identity details.")
        with (
            patch("api.views.get_organization_verification_metrics", side_effect=error),
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assert_generic_unavailable(response, log_exception)
        self.assertNotIn(str(error), response.content.decode())

    def test_missing_or_mismatched_service_identities_return_generic_503(self):
        for service in ("baseline", "activity"):
            for identity in (None, str(self.other_organization.pk)):
                with self.subTest(service=service, identity=identity):
                    baseline_payload = deepcopy(self.baseline)
                    activity_payload = deepcopy(self.activity_payload)
                    malformed = baseline_payload if service == "baseline" else activity_payload
                    if identity is None:
                        del malformed["organization_id"]
                    else:
                        malformed["organization_id"] = identity
                    with (
                        patch(BASELINE_PATCH, return_value=baseline_payload) as baseline,
                        patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                        patch("api.views.logger.exception") as log_exception,
                    ):
                        response = self.request_metrics(
                            self.members[OrganizationMembership.Role.OWNER],
                        )
                    self.assert_generic_unavailable(response, log_exception)
                    baseline.assert_called_once_with(organization=self.organization)
                    activity.assert_called_once_with(organization=self.organization)


    def assert_window_allowed(self, actor, *, params=None, after=None, before=None):
        after = self.created_after if after is None else after
        before = self.created_before if before is None else before
        payload = deepcopy(self.trend_payload)
        payload["measurement_basis"].update(created_after=after, created_before=before)
        original_trend = deepcopy(payload)
        original_baseline = deepcopy(self.baseline)
        original_activity = deepcopy(self.activity_payload)
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
            patch(TREND_PATCH, return_value=payload) as trend,
        ):
            response = self.request_metrics(actor, params=self.window if params is None else params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), set(self.expected_payload()) | {"trend"})
        for key, value in self.expected_payload().items():
            self.assertEqual(response.data[key], value)
        self.assertEqual(response.data["trend"], {
            "measurement_basis": original_trend["measurement_basis"],
            "totals": original_trend["totals"],
            "daily": original_trend["daily"],
        })
        self.assertEqual(set(response.data["trend"]), {"measurement_basis", "totals", "daily"})
        self.assertIsNot(response.data["trend"], payload)
        self.assertEqual(payload, original_trend)
        self.assertEqual(self.baseline, original_baseline)
        self.assertEqual(self.activity_payload, original_activity)
        baseline.assert_called_once_with(organization=self.organization)
        activity.assert_called_once_with(organization=self.organization)
        trend.assert_called_once_with(
            organization=self.organization, created_after=after, created_before=before,
        )
        self.assertIs(trend.call_args.kwargs["created_after"].tzinfo, timezone.utc)
        self.assertIs(trend.call_args.kwargs["created_before"].tzinfo, timezone.utc)
        return response

    def assert_invalid_query(self, params):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=params)
        self.assertEqual(response.status_code, 400)
        baseline.assert_not_called()
        activity.assert_not_called()
        trend.assert_not_called()
        return response

    def test_owner_window_adds_only_trend_and_preserves_full_history_summaries(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER])

    def test_admin_with_valid_window_is_allowed(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.ADMIN])

    def test_lead_verifier_with_valid_window_is_allowed(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.LEAD_VERIFIER])

    def test_explicit_offsets_are_accepted_and_passed_downstream_as_utc(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER], params={
            "created_after": "2026-09-20T18:00:00+08:00",
            "created_before": "2026-09-22T07:00:00-05:00",
        })

    def test_each_timezone_naive_boundary_is_rejected(self):
        for boundary, value in (
            ("created_after", "2026-09-20T10:00:00"),
            ("created_before", "2026-09-22T12:00:00"),
        ):
            with self.subTest(boundary=boundary):
                self.assert_invalid_query({**self.window, boundary: value})

    def test_invalid_datetime_syntax_and_blank_boundaries_are_rejected(self):
        for boundary in self.window:
            for value in ("not-a-datetime", "2026-13-20T10:00:00Z",
                          "2026-09-20T10:00:00+25:00", ""):
                with self.subTest(boundary=boundary, value=value):
                    self.assert_invalid_query({**self.window, boundary: value})

    def test_partial_query_windows_are_rejected(self):
        for boundary in self.window:
            with self.subTest(boundary=boundary):
                self.assert_invalid_query({boundary: self.window[boundary]})

    def test_two_blank_boundaries_are_not_treated_as_no_window(self):
        self.assert_invalid_query({"created_after": "", "created_before": ""})

    def test_reversed_window_after_utc_normalization_is_rejected(self):
        self.assert_invalid_query({
            "created_after": "2026-09-20T10:00:00-05:00",
            "created_before": "2026-09-20T11:00:00+05:00",
        })

    def test_equal_boundaries_are_accepted(self):
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER],
                                   params={"created_after": self.window["created_after"],
                                           "created_before": self.window["created_after"]},
                                   before=self.created_after)

    def test_exactly_90_intersected_utc_dates_are_accepted(self):
        after = self.created_after.replace(hour=23, minute=59)
        before = (after + timedelta(days=89)).replace(hour=0, minute=0)
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER],
                                   params={"created_after": after.isoformat(),
                                           "created_before": before.isoformat()},
                                   after=after, before=before)

    def test_91_intersected_utc_dates_are_rejected_even_with_duration_under_90_days(self):
        after = self.created_after.replace(hour=23, minute=59)
        before = (after + timedelta(days=90)).replace(hour=0, minute=0)
        self.assertLess(before - after, timedelta(days=90))
        self.assert_invalid_query({"created_after": after.isoformat(), "created_before": before.isoformat()})

    def test_90_utc_dates_are_accepted_even_when_local_boundary_dates_span_92(self):
        after = self.created_after.replace(hour=0, minute=30)
        before = (after + timedelta(days=89)).replace(hour=23, minute=30)
        local_after = after.astimezone(timezone(timedelta(hours=-2)))
        local_before = before.astimezone(timezone(timedelta(hours=8)))
        self.assertEqual((local_before.date() - local_after.date()).days + 1, 92)
        self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER],
                                   params={"created_after": local_after.isoformat(),
                                           "created_before": local_before.isoformat()},
                                   after=after, before=before)

    def test_91_utc_dates_are_rejected_even_when_local_boundary_dates_span_89(self):
        after = self.created_after.replace(hour=23, minute=30)
        before = (after + timedelta(days=90)).replace(hour=0, minute=30)
        local_after = after.astimezone(timezone(timedelta(hours=8)))
        local_before = before.astimezone(timezone(timedelta(hours=-2)))
        self.assertEqual((local_before.date() - local_after.date()).days + 1, 89)
        self.assert_invalid_query({"created_after": local_after.isoformat(),
                                   "created_before": local_before.isoformat()})

    def test_unknown_query_parameters_are_rejected_in_both_modes(self):
        for params in ({"created_aftr": self.window["created_after"]},
                       {**self.window, "limit": "90"}):
            with self.subTest(params=params):
                response = self.assert_invalid_query(params)
                unknown = "limit" if "limit" in params else "created_aftr"
                self.assertEqual(response.json(), {unknown: ["Unknown query parameter."]})

    def test_forbidden_windowed_actors_execute_no_measurement_services(self):
        for actor in (
            self.members[OrganizationMembership.Role.CONTRIBUTOR],
            self.members[OrganizationMembership.Role.RESEARCHER],
            self.members[OrganizationMembership.Role.MODERATOR],
            self.safety_moderator, self.outsider,
        ):
            with self.subTest(actor=actor.username):
                self.assert_forbidden(actor, params=self.window)

    def test_suspended_and_left_memberships_are_forbidden_with_window(self):
        for membership_status in (OrganizationMembership.Status.SUSPENDED,
                                  OrganizationMembership.Status.LEFT):
            with self.subTest(status=membership_status):
                self.assert_inactive_memberships_forbidden(membership_status, params=self.window)

    def test_windowed_capabilities_do_not_cross_organizations(self):
        for role in (OrganizationMembership.Role.OWNER, OrganizationMembership.Role.ADMIN,
                     OrganizationMembership.Role.LEAD_VERIFIER):
            with self.subTest(role=role):
                actor = self.members[role]
                OrganizationMembership.objects.create(
                    organization=self.other_organization, user=actor,
                    role=OrganizationMembership.Role.CONTRIBUTOR,
                    status=OrganizationMembership.Status.ACTIVE,
                )
                self.assert_window_allowed(actor)
                self.assert_forbidden(actor, params=self.window,
                                      url=self.metrics_url(self.other_organization.pk))

    def test_unknown_organization_with_window_remains_404(self):
        with (
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER],
                                            params=self.window, url=self.metrics_url(uuid.uuid4()))
        self.assertEqual(response.status_code, 404)
        baseline.assert_not_called()
        activity.assert_not_called()
        trend.assert_not_called()

    def assert_windowed_integrity_failure(self, source, error):
        with (
            patch(BASELINE_PATCH, return_value=self.baseline,
                  side_effect=error if source == "baseline" else None) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload,
                  side_effect=error if source == "activity" else None) as activity,
            patch(TREND_PATCH, return_value=self.trend_payload,
                  side_effect=error if source == "trend" else None) as trend,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=self.window)
        self.assert_generic_unavailable(response, log_exception)
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        if source == "baseline":
            activity.assert_not_called()
        else:
            activity.assert_called_once_with(organization=self.organization)
        if source == "trend":
            trend.assert_called_once_with(organization=self.organization,
                                          created_after=self.created_after, created_before=self.created_before)
        else:
            trend.assert_not_called()

    def test_windowed_baseline_and_activity_integrity_failures_remain_generic_503(self):
        for source, error in (
            ("baseline", VerificationMetricsIntegrityError("Internal assignment-id details.")),
            ("activity", VerificationActivityMetricsIntegrityError("Internal claim-id details.")),
        ):
            with self.subTest(source=source):
                self.assert_windowed_integrity_failure(source, error)

    def test_each_trend_projection_integrity_failure_is_generic_503(self):
        for error in (
            VerificationMetricsIntegrityError("Internal trend assignment-id details."),
            VerificationActivityMetricsIntegrityError("Internal trend event-id details."),
        ):
            with self.subTest(error=type(error).__name__):
                self.assert_windowed_integrity_failure("trend", error)

    def test_missing_or_mismatched_trend_identity_returns_generic_503(self):
        for identity in (None, str(self.other_organization.pk)):
            with self.subTest(identity=identity):
                payload = deepcopy(self.trend_payload)
                if identity is None:
                    del payload["organization_id"]
                else:
                    payload["organization_id"] = identity
                original = deepcopy(payload)
                with (
                    patch(BASELINE_PATCH, return_value=self.baseline),
                    patch(ACTIVITY_PATCH, return_value=self.activity_payload),
                    patch(TREND_PATCH, return_value=payload),
                    patch("api.views.logger.exception") as log_exception,
                ):
                    response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=self.window)
                self.assert_generic_unavailable(response, log_exception)
                self.assertEqual(payload, original)

    def test_defensive_trend_input_error_returns_generic_400(self):
        error = VerificationActivityTrendInputError("Internal invalid-window details.")
        with (
            patch(BASELINE_PATCH, return_value=self.baseline),
            patch(ACTIVITY_PATCH, return_value=self.activity_payload),
            patch(TREND_PATCH, side_effect=error),
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER], params=self.window)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Invalid verification analytics time window."})
        log_exception.assert_not_called()

    def test_trend_datetimes_serialize_as_utc_over_http(self):
        response = self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.json()["trend"], {
            "measurement_basis": {
                **self.trend_payload["measurement_basis"],
                "created_after": "2026-09-20T10:00:00Z",
                "created_before": "2026-09-22T12:00:00Z",
            },
            "totals": self.trend_payload["totals"],
            "daily": self.trend_payload["daily"],
        })

    def test_empty_trend_counts_and_daily_buckets_are_preserved_exactly(self):
        zeros = {section: dict.fromkeys(fields, 0)
                 for section, fields in self.trend_payload["totals"].items()}
        self.trend_payload["totals"] = deepcopy(zeros)
        self.trend_payload["daily"] = [
            {"date": value, **deepcopy(zeros)}
            for value in ("2026-09-20", "2026-09-21", "2026-09-22")
        ]
        response = self.assert_window_allowed(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.json()["trend"]["totals"], zeros)
        self.assertEqual(response.json()["trend"]["daily"], self.trend_payload["daily"])


class VerificationMetricsQueryBoundaryTests(SimpleTestCase):
    """No database access is permitted at this delegation boundary."""

    def test_each_qualifying_capability_delegates_and_composes_without_mutation(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        payload = {"organization_id": str(organization.pk), "attempts": {"claimed": 2}}
        activity_payload = {
            "organization_id": str(organization.pk),
            "measurement_basis": {"first_observed_activity_at": None},
            "evidence_review": {"decisions": 1, "verified": 1, "rejected": 0},
            "adjudication": {"started": 0, "verdicts_issued": 0},
            "publication": {"initial_published": 0},
        }
        original_baseline = deepcopy(payload)
        original_activity = deepcopy(activity_payload)
        for results, capabilities in (
            ([True], [PartnerCapability.MANAGE_ORGANIZATION]),
            ([False, True], [
                PartnerCapability.MANAGE_ORGANIZATION,
                PartnerCapability.CLAIM_VERIFICATION_WORK,
            ]),
        ):
            with (
                self.subTest(results=results),
                patch(
                    "api.verification_metrics_query_service.has_capability",
                    side_effect=results,
                ) as capability,
                patch(BASELINE_PATCH, return_value=payload) as baseline,
                patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                patch(TREND_PATCH) as trend,
            ):
                result = get_organization_verification_metrics(
                    actor=actor, organization=organization,
                )
            self.assertEqual(result, {
                "organization_id": str(organization.pk),
                "attempts": {"claimed": 2},
                "activity": {
                    "measurement_basis": {"first_observed_activity_at": None},
                    "evidence_review": {"decisions": 1, "verified": 1, "rejected": 0},
                    "adjudication": {"started": 0, "verdicts_issued": 0},
                    "publication": {"initial_published": 0},
                },
            })
            self.assertIsNot(result, payload)
            self.assertIsNot(result["activity"], activity_payload)
            self.assertEqual(payload, original_baseline)
            self.assertEqual(activity_payload, original_activity)
            self.assertEqual(capability.call_args_list, [
                call(actor, required, organization=organization)
                for required in capabilities
            ])
            baseline.assert_called_once_with(organization=organization)
            activity.assert_called_once_with(organization=organization)
            trend.assert_not_called()

    def test_missing_capabilities_raise_without_reading_either_service(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        with (
            patch(
                "api.verification_metrics_query_service.has_capability",
                return_value=False,
            ) as capability,
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            with self.assertRaises(VerificationMetricsAuthorizationError):
                get_organization_verification_metrics(actor=actor, organization=organization)
        self.assertEqual(capability.call_args_list, [
            call(actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization),
            call(actor, PartnerCapability.CLAIM_VERIFICATION_WORK, organization=organization),
        ])
        baseline.assert_not_called()
        activity.assert_not_called()
        trend.assert_not_called()

    def test_missing_or_mismatched_service_identity_raises_composition_error(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        for service in ("baseline", "activity"):
            for identity in (None, str(uuid.uuid4())):
                with self.subTest(service=service, identity=identity):
                    baseline_payload = {"organization_id": str(organization.pk)}
                    activity_payload = {"organization_id": str(organization.pk)}
                    malformed = baseline_payload if service == "baseline" else activity_payload
                    if identity is None:
                        del malformed["organization_id"]
                    else:
                        malformed["organization_id"] = identity
                    original_baseline = deepcopy(baseline_payload)
                    original_activity = deepcopy(activity_payload)
                    with (
                        patch(
                            "api.verification_metrics_query_service.has_capability",
                            return_value=True,
                        ),
                        patch(BASELINE_PATCH, return_value=baseline_payload) as baseline,
                        patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                    ):
                        with self.assertRaises(VerificationMetricsCompositionError):
                            get_organization_verification_metrics(
                                actor=actor, organization=organization,
                            )
                    baseline.assert_called_once_with(organization=organization)
                    activity.assert_called_once_with(organization=organization)
                    self.assertEqual(baseline_payload, original_baseline)
                    self.assertEqual(activity_payload, original_activity)

    def test_direct_partial_window_fails_after_authorization_before_all_measurements(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        boundary = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
        for kwargs in ({"created_after": boundary}, {"created_before": boundary}):
            with self.subTest(kwargs=kwargs):
                with (
                    patch("api.verification_metrics_query_service.has_capability",
                          return_value=True) as capability,
                    patch(BASELINE_PATCH) as baseline,
                    patch(ACTIVITY_PATCH) as activity,
                    patch(TREND_PATCH) as trend,
                ):
                    with self.assertRaises(VerificationActivityTrendInputError):
                        get_organization_verification_metrics(
                            actor=actor, organization=organization, **kwargs,
                        )
                capability.assert_called_once_with(
                    actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization,
                )
                baseline.assert_not_called()
                activity.assert_not_called()
                trend.assert_not_called()

    def test_direct_partial_window_does_not_bypass_authorization(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        with (
            patch("api.verification_metrics_query_service.has_capability",
                  return_value=False) as capability,
            patch(BASELINE_PATCH) as baseline,
            patch(ACTIVITY_PATCH) as activity,
            patch(TREND_PATCH) as trend,
        ):
            with self.assertRaises(VerificationMetricsAuthorizationError):
                get_organization_verification_metrics(
                    actor=actor, organization=organization,
                    created_after=datetime(2026, 9, 20, 10, tzinfo=timezone.utc),
                )
        self.assertEqual(capability.call_args_list, [
            call(actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization),
            call(actor, PartnerCapability.CLAIM_VERIFICATION_WORK, organization=organization),
        ])
        baseline.assert_not_called()
        activity.assert_not_called()
        trend.assert_not_called()

    def test_direct_missing_or_mismatched_trend_identity_raises_composition_error(self):
        organization = SimpleNamespace(pk=uuid.uuid4())
        after = datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
        before = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)
        for identity in (None, str(uuid.uuid4())):
            with self.subTest(identity=identity):
                baseline_payload = {"organization_id": str(organization.pk)}
                activity_payload = {
                    "organization_id": str(organization.pk),
                    "measurement_basis": {}, "evidence_review": {},
                    "adjudication": {}, "publication": {},
                }
                trend_payload = {} if identity is None else {"organization_id": identity}
                original = deepcopy(trend_payload)
                with (
                    patch("api.verification_metrics_query_service.has_capability", return_value=True),
                    patch(BASELINE_PATCH, return_value=baseline_payload) as baseline,
                    patch(ACTIVITY_PATCH, return_value=activity_payload) as activity,
                    patch(TREND_PATCH, return_value=trend_payload) as trend,
                ):
                    with self.assertRaises(VerificationMetricsCompositionError):
                        get_organization_verification_metrics(
                            actor=object(), organization=organization,
                            created_after=after, created_before=before,
                        )
                baseline.assert_called_once_with(organization=organization)
                activity.assert_called_once_with(organization=organization)
                trend.assert_called_once_with(
                    organization=organization, created_after=after, created_before=before,
                )
                self.assertEqual(trend_payload, original)
