import uuid
from copy import deepcopy
from datetime import datetime, timezone
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


BASELINE_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_baseline"
)
ACTIVITY_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_activity"
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

    def request_metrics(self, actor, *, url=None):
        client = APIClient()
        client.force_authenticate(user=actor)
        return client.get(self.url if url is None else url)

    def assert_allowed(self, actor):
        original_baseline = deepcopy(self.baseline)
        original_activity = deepcopy(self.activity_payload)
        with (
            patch(BASELINE_PATCH, return_value=self.baseline) as baseline,
            patch(ACTIVITY_PATCH, return_value=self.activity_payload) as activity,
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
        return response

    def assert_forbidden(self, actor, *, url=None):
        with patch(BASELINE_PATCH) as baseline, patch(ACTIVITY_PATCH) as activity:
            response = self.request_metrics(actor, url=url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.data), {"detail"})
        baseline.assert_not_called()
        activity.assert_not_called()

    def test_unauthenticated_request_returns_401(self):
        with patch(BASELINE_PATCH) as baseline, patch(ACTIVITY_PATCH) as activity:
            response = APIClient().get(self.url)
        self.assertEqual(response.status_code, 401)
        baseline.assert_not_called()
        activity.assert_not_called()

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

    def assert_inactive_memberships_forbidden(self, membership_status):
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
                self.assert_forbidden(actor)

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
        ):
            with self.assertRaises(VerificationMetricsAuthorizationError):
                get_organization_verification_metrics(actor=actor, organization=organization)
        self.assertEqual(capability.call_args_list, [
            call(actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization),
            call(actor, PartnerCapability.CLAIM_VERIFICATION_WORK, organization=organization),
        ])
        baseline.assert_not_called()
        activity.assert_not_called()

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
