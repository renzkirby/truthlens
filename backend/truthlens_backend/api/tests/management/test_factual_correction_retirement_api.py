from copy import deepcopy

from django.contrib.auth.models import User
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    FactualCorrectionRequest,
    ModerationCase,
    OfficialFactCheck,
    Organization,
)
from api.tests.workspace.test_factual_correction_proposal import (
    FactualCorrectionProposalFixtures,
)


class PlatformFactualCorrectionRetirementApiTests(
    FactualCorrectionProposalFixtures,
    TestCase,
):
    def setUp(self):
        super().setUp()
        self.platform_admin = User.objects.create_superuser(
            username="retirement-api-platform-admin",
            email="retirement-api-platform-admin@example.com",
            password="test-password",
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def cancellation_url(self, correction_request, organization=None):
        return reverse(
            "management_organization_factual_correction_retirement_cancel",
            kwargs={
                "organization_id": (organization or self.organization).pk,
                "correction_request_id": correction_request.pk,
            },
        )

    def detail_url(self):
        return reverse(
            "management_organization_detail",
            kwargs={"organization_id": self.organization.pk},
        )

    def correction_context(self, *, suffix, prepared=False):
        context = self.make_proposal_context(
            suffix=suffix,
            review=prepared,
        )
        if prepared:
            context["proposal"] = self.save_proposal(context)
            self.prepare_proposal(context, context["proposal"])
            context["proposal"].refresh_from_db()
        return context

    def test_legacy_retirement_blocker_can_be_cancelled_then_end_partnership_becomes_available(
        self,
    ):
        context = self.correction_context(
            suffix="retirement-api-legacy",
            prepared=True,
        )
        publication_payload = deepcopy(context["seal"].payload)

        # Reproduce the legacy CSG shape after real Partner work already exists.
        self.organization.verification_status = (
            Organization.VerificationStatus.UNVERIFIED
        )
        self.organization.partner_status = Organization.PartnerStatus.NONE
        self.organization.save(
            update_fields=["verification_status", "partner_status"]
        )

        before = self.client_for(self.platform_admin).get(self.detail_url())
        self.assertEqual(before.status_code, status.HTTP_200_OK)
        lifecycle = before.data["lifecycle"]
        self.assertEqual(lifecycle["state"], "RETIREMENT_REQUIRED")
        self.assertFalse(lifecycle["actions"]["can_end_partnership"])
        self.assertEqual(lifecycle["impact"]["active_factual_corrections"], 1)
        self.assertEqual(
            lifecycle["active_factual_corrections"],
            [
                {
                    "id": str(context["correction_request"].pk),
                    "predecessor_fact_check_id": str(context["published"].pk),
                    "predecessor_headline": context["published"].headline,
                    "correction_reason": context["correction_request"].correction_reason,
                    "requested_at": context[
                        "correction_request"
                    ].requested_at.isoformat(),
                }
            ],
        )

        response = self.client_for(self.platform_admin).post(
            self.cancellation_url(context["correction_request"]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["correction"],
            {
                "id": str(context["correction_request"].pk),
                "status": FactualCorrectionRequest.Status.CANCELLED,
                "case_status": ModerationCase.Status.CANCELLED,
                "proposal_preserved": True,
            },
        )
        refreshed = response.data["organization"]["lifecycle"]
        self.assertEqual(refreshed["state"], "RETIREMENT_REQUIRED")
        self.assertEqual(refreshed["active_factual_corrections"], [])
        self.assertEqual(refreshed["impact"]["active_factual_corrections"], 0)
        self.assertTrue(refreshed["actions"]["can_end_partnership"])
        self.assertTrue(refreshed["can_end_partnership"])
        self.assertEqual(refreshed["end_partnership_blockers"], [])

        context["published"].refresh_from_db()
        context["seal"].refresh_from_db()
        self.assertEqual(
            context["published"].publication_status,
            OfficialFactCheck.PublicationStatus.PUBLISHED,
        )
        self.assertEqual(context["seal"].payload, publication_payload)

    def test_endpoint_rejects_unexpected_fields(self):
        context = self.correction_context(suffix="retirement-api-strict")

        response = self.client_for(self.platform_admin).post(
            self.cancellation_url(context["correction_request"]),
            {"reason": "arbitrary"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        context["correction_request"].refresh_from_db()
        self.assertEqual(
            context["correction_request"].status,
            FactualCorrectionRequest.Status.ACTIVE,
        )

    def test_endpoint_is_platform_admin_only(self):
        context = self.correction_context(suffix="retirement-api-permission")

        response = self.client_for(self.lead).post(
            self.cancellation_url(context["correction_request"]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        context["correction_request"].refresh_from_db()
        self.assertEqual(
            context["correction_request"].status,
            FactualCorrectionRequest.Status.ACTIVE,
        )

    def test_unknown_organization_and_wrong_request_organization_fail_closed(self):
        context = self.correction_context(suffix="retirement-api-scope")

        missing = self.client_for(self.platform_admin).post(
            self.cancellation_url(
                context["correction_request"],
                organization=self.other_organization,
            ),
            {},
            format="json",
        )
        self.assertEqual(missing.status_code, status.HTTP_409_CONFLICT)

        unknown = self.client_for(self.platform_admin).post(
            reverse(
                "management_organization_factual_correction_retirement_cancel",
                kwargs={
                    "organization_id": "00000000-0000-0000-0000-000000000001",
                    "correction_request_id": context["correction_request"].pk,
                },
            ),
            {},
            format="json",
        )
        self.assertEqual(unknown.status_code, status.HTTP_404_NOT_FOUND)
