import uuid
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
    get_organization_verification_metrics,
)
from api.verification_metrics_service import VerificationMetricsIntegrityError


BASELINE_PATCH = (
    "api.verification_metrics_query_service.get_organization_verification_baseline"
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
        with patch(BASELINE_PATCH, return_value=self.baseline) as baseline:
            response = self.request_metrics(actor)
        self.assertEqual(response.status_code, 200)
        self.assertIs(response.data, self.baseline)
        baseline.assert_called_once_with(organization=self.organization)
        return response

    def assert_forbidden(self, actor, *, url=None):
        with patch(BASELINE_PATCH) as baseline:
            response = self.request_metrics(actor, url=url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.data), {"detail"})
        baseline.assert_not_called()

    def test_unauthenticated_request_returns_401(self):
        with patch(BASELINE_PATCH) as baseline:
            response = APIClient().get(self.url)
        self.assertEqual(response.status_code, 401)
        baseline.assert_not_called()

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
        with patch(BASELINE_PATCH) as baseline:
            response = self.request_metrics(
                self.members[OrganizationMembership.Role.OWNER],
                url=self.metrics_url(uuid.uuid4()),
            )
        self.assertEqual(response.status_code, 404)
        baseline.assert_not_called()

    def test_success_preserves_exact_baseline_and_coverage_on_the_wire(self):
        response = self.assert_allowed(self.members[OrganizationMembership.Role.OWNER])
        expected = {
            **self.baseline,
            "measurement_basis": {
                **self.baseline["measurement_basis"],
                "first_observed_claimed_at": "2026-09-15T08:00:00.123456Z",
                "last_observed_claimed_at": "2026-09-15T09:00:00.654321Z",
            },
        }
        self.assertEqual(response.json(), expected)

    def test_empty_baseline_preserves_zero_counts_and_nulls(self):
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
        response = self.assert_allowed(self.members[OrganizationMembership.Role.ADMIN])
        self.assertEqual(response.json(), self.baseline)

    def test_integrity_error_returns_generic_503_without_partial_metrics(self):
        error = VerificationMetricsIntegrityError(
            "Assignment internal-assignment-id has malformed event details."
        )
        with (
            patch(BASELINE_PATCH, side_effect=error) as baseline,
            patch("api.views.logger.exception") as log_exception,
        ):
            response = self.request_metrics(self.members[OrganizationMembership.Role.OWNER])
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "detail": "Verification metrics are temporarily unavailable.",
        })
        self.assertNotIn(str(error), response.content.decode())
        baseline.assert_called_once_with(organization=self.organization)
        log_exception.assert_called_once_with(
            "Organization verification metrics projection failed."
        )


class VerificationMetricsQueryBoundaryTests(SimpleTestCase):
    """No database access is permitted at this delegation boundary."""

    def test_each_qualifying_capability_returns_baseline_by_identity(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        payload = {"organization_id": str(organization.pk)}
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
            ):
                result = get_organization_verification_metrics(
                    actor=actor, organization=organization,
                )
            self.assertIs(result, payload)
            self.assertEqual(capability.call_args_list, [
                call(actor, required, organization=organization)
                for required in capabilities
            ])
            baseline.assert_called_once_with(organization=organization)

    def test_missing_capabilities_raise_without_reading_baseline(self):
        actor = object()
        organization = SimpleNamespace(pk=uuid.uuid4())
        with (
            patch(
                "api.verification_metrics_query_service.has_capability",
                return_value=False,
            ) as capability,
            patch(BASELINE_PATCH) as baseline,
        ):
            with self.assertRaises(VerificationMetricsAuthorizationError):
                get_organization_verification_metrics(actor=actor, organization=organization)
        self.assertEqual(capability.call_args_list, [
            call(actor, PartnerCapability.MANAGE_ORGANIZATION, organization=organization),
            call(actor, PartnerCapability.CLAIM_VERIFICATION_WORK, organization=organization),
        ])
        baseline.assert_not_called()
