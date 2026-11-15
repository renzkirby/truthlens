from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    Organization,
    OrganizationMembership,
    PartnershipApplication,
)
from api.organization_invitation_service import accept_organization_invitation
from api.organization_provisioning_service import _create_organization_admin_invitation


APPLICATION_PAYLOAD = {
    "organization_name": "Example Verification Network",
    "organization_type": "FACT_CHECKING",
    "website": "https://example-verification.org",
    "official_contact_email": "office@example-verification.org",
    "applicant_full_name": "Maria Santos",
    "applicant_position": "Executive Director",
    "applicant_email": "maria@example-verification.org",
    "organization_description": (
        "Example Verification Network is an independent organization that "
        "publishes evidence-based public-interest fact checks."
    ),
    "partnership_reason": (
        "We want to contribute professional verification capacity and publish "
        "institutional fact checks through TruthLens."
    ),
    "supporting_links": [
        "https://example-verification.org/about",
    ],
    "authorized_to_represent": True,
    "agrees_to_partner_responsibilities": True,
}


class PartnershipApplicationWorkflowTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.platform_admin = User.objects.create_superuser(
            username="platform-admin",
            email="admin@truthlens.test",
            password="test-password",
        )

    def submit_application(self, **overrides):
        payload = {**APPLICATION_PAYLOAD, **overrides}
        return self.client.post(
            reverse("public_partnership_application_create"),
            payload,
            format="json",
        )

    def application(self):
        return PartnershipApplication.objects.select_related("organization").get()

    def start_review(self, application):
        self.client.force_authenticate(self.platform_admin)
        return self.client.post(
            reverse(
                "management_partnership_application_review",
                args=[application.pk],
            ),
            {},
            format="json",
        )

    def approve(self, application, email="maria@example-verification.org"):
        return self.client.post(
            reverse(
                "management_partnership_application_approve",
                args=[application.pk],
            ),
            {
                "approved_admin_email": email,
                "decision_notes": "Institutional identity and representative were reviewed.",
            },
            format="json",
        )

    def test_public_submission_creates_private_pending_organization(self):
        response = self.submit_application()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        application = self.application()
        organization = application.organization

        self.assertEqual(application.status, PartnershipApplication.Status.SUBMITTED)
        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.PENDING,
        )
        self.assertEqual(
            organization.partner_status,
            Organization.PartnerStatus.NONE,
        )
        self.assertFalse(organization.public_profile_enabled)
        self.assertFalse(organization.public_logo_enabled)
        self.assertEqual(
            organization.governance_contact_email,
            APPLICATION_PAYLOAD["official_contact_email"],
        )

    def test_duplicate_organization_name_is_rejected(self):
        first = self.submit_application()
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.submit_application(
            website="https://another-example.org",
            applicant_email="other@another-example.org",
            official_contact_email="office@another-example.org",
        )

        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Organization.objects.count(), 1)
        self.assertEqual(PartnershipApplication.objects.count(), 1)

    def test_application_requires_representation_and_partner_acknowledgement(self):
        response = self.submit_application(
            authorized_to_represent=False,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Organization.objects.count(), 0)

        response = self.submit_application(
            agrees_to_partner_responsibilities=False,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Organization.objects.count(), 0)

    def test_review_and_approval_preserve_pending_organization_until_acceptance(self):
        self.submit_application()
        application = self.application()

        review = self.start_review(application)
        self.assertEqual(review.status_code, status.HTTP_200_OK)

        approved = self.approve(application)
        self.assertEqual(approved.status_code, status.HTTP_200_OK)

        application.refresh_from_db()
        application.organization.refresh_from_db()
        self.assertEqual(application.status, PartnershipApplication.Status.APPROVED)
        self.assertEqual(
            application.organization.verification_status,
            Organization.VerificationStatus.PENDING,
        )
        self.assertEqual(
            application.organization.partner_status,
            Organization.PartnerStatus.NONE,
        )

    def test_manual_verify_shortcut_is_blocked_for_application_organization(self):
        self.submit_application()
        application = self.application()
        self.start_review(application)
        self.approve(application)

        response = self.client.post(
            reverse(
                "management_organization_verify",
                args=[application.organization_id],
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        application.organization.refresh_from_db()
        self.assertEqual(
            application.organization.verification_status,
            Organization.VerificationStatus.PENDING,
        )

    def test_admin_provisioning_is_blocked_before_application_approval(self):
        self.submit_application()
        application = self.application()
        self.client.force_authenticate(self.platform_admin)

        response = self.client.post(
            reverse(
                "management_primary_admin_provision",
                args=[application.organization_id],
            ),
            {"email": application.applicant_email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(application.organization.invitations.exists())

    def test_admin_provisioning_requires_approved_representative_email(self):
        self.submit_application()
        application = self.application()
        self.start_review(application)
        self.approve(application)

        wrong = self.client.post(
            reverse(
                "management_primary_admin_provision",
                args=[application.organization_id],
            ),
            {"email": "different@example-verification.org"},
            format="json",
        )
        self.assertEqual(wrong.status_code, status.HTTP_409_CONFLICT)

    def test_approved_admin_acceptance_finalizes_verification_and_partnership(self):
        self.submit_application()
        application = self.application()
        self.start_review(application)
        self.approve(application)

        invitation, raw_token = _create_organization_admin_invitation(
            organization=application.organization,
            email="maria@example-verification.org",
            actor=self.platform_admin,
        )

        representative = User.objects.create_user(
            username="maria",
            email="maria@example-verification.org",
            password="test-password",
        )
        representative.profile.is_email_verified = True
        representative.profile.save(update_fields=["is_email_verified"])

        result = accept_organization_invitation(
            raw_token=raw_token,
            actor=representative,
        )

        application.refresh_from_db()
        application.organization.refresh_from_db()
        self.assertIsNotNone(application.onboarding_completed_at)
        self.assertEqual(
            application.organization.verification_status,
            Organization.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            application.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )
        self.assertEqual(
            result["membership"].role,
            OrganizationMembership.Role.ADMIN,
        )
        self.assertEqual(
            result["membership"].status,
            OrganizationMembership.Status.ACTIVE,
        )
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, invitation.Status.ACCEPTED)

    def test_legacy_organization_without_application_keeps_manual_lifecycle(self):
        organization = Organization.objects.create(
            name="Legacy Internal Partner",
            slug="legacy-internal-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.NONE,
        )
        self.client.force_authenticate(self.platform_admin)

        verify_response = self.client.post(
            reverse("management_organization_verify", args=[organization.pk]),
            {},
            format="json",
        )
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)

        activate_response = self.client.post(
            reverse(
                "management_organization_activate_partnership",
                args=[organization.pk],
            ),
            {},
            format="json",
        )
        self.assertEqual(activate_response.status_code, status.HTTP_200_OK)

        organization.refresh_from_db()
        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )

    def test_management_governance_history_includes_application_review_events(self):
        self.submit_application()
        application = self.application()
        self.start_review(application)
        self.approve(application)

        response = self.client.get(
            reverse("management_governance_audit"),
            {"organization": application.organization.name},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        actions = {
            row["action_type"]
            for row in response.data["results"]
        }
        self.assertIn(
            "PARTNERSHIP_APPLICATION_SUBMITTED",
            actions,
        )
        self.assertIn(
            "PARTNERSHIP_APPLICATION_REVIEW_STARTED",
            actions,
        )
        self.assertIn(
            "PARTNERSHIP_APPLICATION_APPROVED",
            actions,
        )

    def test_rejection_marks_application_and_organization_rejected(self):
        self.submit_application()
        application = self.application()
        self.start_review(application)

        response = self.client.post(
            reverse(
                "management_partnership_application_reject",
                args=[application.pk],
            ),
            {"decision_notes": "The submitted institutional identity could not be established."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        application.refresh_from_db()
        application.organization.refresh_from_db()
        self.assertEqual(application.status, PartnershipApplication.Status.REJECTED)
        self.assertEqual(
            application.organization.verification_status,
            Organization.VerificationStatus.REJECTED,
        )
        self.assertEqual(
            application.organization.partner_status,
            Organization.PartnerStatus.NONE,
        )
