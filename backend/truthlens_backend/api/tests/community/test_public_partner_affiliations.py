from django.contrib.auth.models import User
from django.test import TestCase

from api.models import Organization, OrganizationMembership
from api.organization_public_affiliation_service import (
    get_public_partner_affiliations,
    prefetch_public_partner_affiliations,
)


class PublicPartnerAffiliationProjectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="affiliated-member",
            email="private-affiliation@example.com",
        )

    @staticmethod
    def create_organization(**overrides):
        values = {
            "name": "Eligible Partner",
            "slug": "eligible-partner",
            "verification_status": Organization.VerificationStatus.VERIFIED,
            "partner_status": Organization.PartnerStatus.ACTIVE,
            "public_profile_enabled": True,
            "public_logo_enabled": True,
            "logo_url": "https://example.com/partner-logo.png",
        }
        values.update(overrides)
        return Organization.objects.create(**values)

    def membership(self, organization, *, status_value=OrganizationMembership.Status.ACTIVE):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=self.user,
            role=OrganizationMembership.Role.OWNER,
            status=status_value,
        )

    def affiliations(self):
        user = prefetch_public_partner_affiliations(
            User.objects.filter(pk=self.user.pk)
        ).get()
        return get_public_partner_affiliations(user)

    def test_active_membership_in_verified_active_public_partner_appears(self):
        organization = self.create_organization()
        self.membership(organization)

        self.assertEqual(
            self.affiliations(),
            [
                {
                    "id": str(organization.pk),
                    "name": organization.name,
                    "slug": organization.slug,
                    "logo_url": organization.logo_url,
                }
            ],
        )

    def test_non_active_membership_statuses_are_excluded_individually(self):
        for membership_status in (
            OrganizationMembership.Status.PENDING,
            OrganizationMembership.Status.SUSPENDED,
            OrganizationMembership.Status.LEFT,
        ):
            organization = self.create_organization(
                name=f"{membership_status} Partner",
                slug=f"{membership_status.lower()}-partner",
            )
            self.membership(organization, status_value=membership_status)

        self.assertEqual(self.affiliations(), [])

    def test_ineligible_organization_states_are_excluded_individually(self):
        cases = (
            ("unverified", {"verification_status": Organization.VerificationStatus.UNVERIFIED}),
            ("pending", {"verification_status": Organization.VerificationStatus.PENDING}),
            ("rejected", {"verification_status": Organization.VerificationStatus.REJECTED}),
            ("none", {"partner_status": Organization.PartnerStatus.NONE}),
            ("suspended", {"partner_status": Organization.PartnerStatus.SUSPENDED}),
            ("former", {"partner_status": Organization.PartnerStatus.FORMER}),
            ("private", {"public_profile_enabled": False}),
        )
        for suffix, overrides in cases:
            organization = self.create_organization(
                name=f"{suffix.title()} Partner",
                slug=f"{suffix}-partner",
                **overrides,
            )
            self.membership(organization)

        self.assertEqual(self.affiliations(), [])

    def test_logo_permission_multiple_memberships_and_ordering(self):
        zebra = self.create_organization(
            name="Zebra Verification",
            slug="zebra-verification",
            public_logo_enabled=False,
        )
        alpha = self.create_organization(
            name="Alpha Verification",
            slug="alpha-verification",
        )
        self.membership(zebra)
        self.membership(alpha)

        affiliations = self.affiliations()

        self.assertEqual(
            [item["name"] for item in affiliations],
            ["Alpha Verification", "Zebra Verification"],
        )
        self.assertEqual(affiliations[0]["logo_url"], alpha.logo_url)
        self.assertIsNone(affiliations[1]["logo_url"])
        serialized = str(affiliations)
        for private_value in (
            self.user.email,
            OrganizationMembership.Role.OWNER,
            "capabilities",
        ):
            self.assertNotIn(private_value, serialized)

    def test_list_projection_prefetches_affiliations_in_bounded_queries(self):
        organization = self.create_organization()
        second_user = User.objects.create_user(username="second-affiliated-member")
        self.membership(organization)
        OrganizationMembership.objects.create(
            organization=organization,
            user=second_user,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        with self.assertNumQueries(2):
            users = list(
                prefetch_public_partner_affiliations(
                    User.objects.filter(pk__in=(self.user.pk, second_user.pk))
                ).order_by("username")
            )
            projections = [
                get_public_partner_affiliations(user)
                for user in users
            ]

        self.assertEqual(len(projections), 2)
        self.assertTrue(all(items[0]["slug"] == organization.slug for items in projections))
