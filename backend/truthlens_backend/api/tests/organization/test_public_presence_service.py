from django.test import TestCase

from api.models import Organization
from api.organization_public_presence_service import (
    get_public_partner_organizations,
)


class PublicPartnerPresenceServiceTests(TestCase):
    def create_organization(
        self,
        **overrides,
    ):
        values = {
            "name": "Public Presence Partner",
            "slug": "public-presence-partner",
            "verification_status": Organization.VerificationStatus.VERIFIED,
            "partner_status": Organization.PartnerStatus.ACTIVE,
            "public_profile_enabled": True,
        }
        values.update(overrides)

        return Organization.objects.create(**values)

    def assert_is_publicly_eligible(
        self,
        organization,
        expected,
    ):
        self.assertEqual(
            get_public_partner_organizations().filter(
                id=organization.id,
            ).exists(),
            expected,
        )

    def test_verified_active_opted_in_organization_is_eligible(self):
        organization = self.create_organization()

        self.assert_is_publicly_eligible(
            organization,
            True,
        )

    def test_organization_without_public_opt_in_is_excluded(self):
        organization = self.create_organization(
            public_profile_enabled=False,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )

    def test_unverified_organization_is_excluded(self):
        organization = self.create_organization(
            verification_status=Organization.VerificationStatus.UNVERIFIED,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )

    def test_pending_verification_organization_is_excluded(self):
        organization = self.create_organization(
            verification_status=Organization.VerificationStatus.PENDING,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )

    def test_rejected_organization_is_excluded(self):
        organization = self.create_organization(
            verification_status=Organization.VerificationStatus.REJECTED,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )

    def test_non_partner_organization_is_excluded(self):
        organization = self.create_organization(
            partner_status=Organization.PartnerStatus.NONE,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )

    def test_suspended_partner_organization_is_excluded(self):
        organization = self.create_organization(
            partner_status=Organization.PartnerStatus.SUSPENDED,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )

    def test_former_partner_organization_is_excluded(self):
        organization = self.create_organization(
            partner_status=Organization.PartnerStatus.FORMER,
        )

        self.assert_is_publicly_eligible(
            organization,
            False,
        )
