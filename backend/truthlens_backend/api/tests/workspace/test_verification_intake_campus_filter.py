from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Claim,
    ClaimInvestigationClassification,
    Organization,
    OrganizationMembership,
    Thread,
)
from api.verification_assignment_service import ensure_verification_assignment


class VerificationIntakeCampusFilterTests(APITestCase):
    def setUp(self):
        self.community_user = User.objects.create_user(
            username="campus-filter-community-user",
            password="test-password",
        )
        self.lead = User.objects.create_user(
            username="campus-filter-lead",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Campus Filter Partner",
            slug="campus-filter-partner",
            organization_type=Organization.OrganizationType.NEWS,
            organization_subtype=Organization.OrganizationSubtype.STUDENT_PUBLICATION,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.lead)

    def _assignment(self, *, suffix, campus_state):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Campus intake filter fixture {suffix}.",
            ai_verdict="UNVERIFIED",
        )
        ClaimInvestigationClassification.objects.create(
            claim=claim,
            domains=["EDUCATION"],
            primary_subject="EDUCATION",
            campus_context_state=campus_state,
            campus_context_rationale=(
                "Reviewed campus context fixture."
                if campus_state
                else ""
            ),
            rationale="Reviewed subject classification fixture.",
            source=ClaimInvestigationClassification.Source.MANUAL,
        )
        Thread.objects.create(
            claim=claim,
            author=self.community_user,
            caption=f"Campus filter thread {suffix}.",
            status=Thread.Status.OPEN,
        )
        return ensure_verification_assignment(claim=claim)

    @override_settings(INVESTIGATION_ROUTING_MODE="off")
    def test_campus_affairs_filter_returns_only_confirmed_campus_claims(self):
        confirmed = self._assignment(
            suffix="confirmed",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )
        self._assignment(
            suffix="not-applicable",
            campus_state=ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE,
        )
        self._assignment(
            suffix="uncertain",
            campus_state=ClaimInvestigationClassification.CampusContextState.UNCERTAIN,
        )
        self._assignment(
            suffix="unassessed",
            campus_state=None,
        )

        response = self.client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization.id),
                "classification": "CAMPUS_AFFAIRS",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            str(confirmed.id),
        )

    @override_settings(INVESTIGATION_ROUTING_MODE="off")
    def test_campus_affairs_filter_is_browsing_only(self):
        confirmed = self._assignment(
            suffix="browsing-only",
            campus_state=ClaimInvestigationClassification.CampusContextState.CONFIRMED,
        )

        response = self.client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization.id),
                "classification": "CAMPUS_AFFAIRS",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(confirmed.id))

    def test_unknown_intake_filter_remains_invalid(self):
        response = self.client.get(
            reverse("verification_intake"),
            {
                "organization_id": str(self.organization.id),
                "classification": "NOT_A_SUPPORTED_FILTER",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
