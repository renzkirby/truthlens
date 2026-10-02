from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import Organization, OrganizationFollow


class OrganizationFollowApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="partner-follower")
        self.other_user = User.objects.create_user(username="other-follower")
        self.organization = self.create_organization(
            name="Followable Partner",
            slug="followable-partner",
        )
        self.other_organization = self.create_organization(
            name="Other Partner",
            slug="other-partner",
        )
        self.url = reverse(
            "public_partner_follow",
            kwargs={"slug": self.organization.slug},
        )
        self.client.force_authenticate(self.user)

    @staticmethod
    def create_organization(**overrides):
        values = {
            "name": "Partner",
            "slug": "partner",
            "verification_status": Organization.VerificationStatus.VERIFIED,
            "partner_status": Organization.PartnerStatus.ACTIVE,
            "public_profile_enabled": True,
        }
        values.update(overrides)
        return Organization.objects.create(**values)

    def test_authenticated_request_toggles_follow_and_unfollow(self):
        first = self.client.post(self.url)
        second = self.client.post(self.url)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(
            first.data,
            {"is_following": True, "followers_count": 1},
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            second.data,
            {"is_following": False, "followers_count": 0},
        )
        self.assertFalse(
            OrganizationFollow.objects.filter(
                organization=self.organization,
                user=self.user,
            ).exists()
        )

    def test_anonymous_follow_is_rejected(self):
        self.client.force_authenticate(None)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_slug_is_safe_not_found(self):
        response = self.client.post(
            reverse(
                "public_partner_follow",
                kwargs={"slug": "missing-partner"},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("detail", response.data)

    def test_ineligible_organizations_are_unavailable(self):
        cases = (
            ("private", {"public_profile_enabled": False}),
            (
                "unverified",
                {"verification_status": Organization.VerificationStatus.UNVERIFIED},
            ),
            (
                "suspended",
                {"partner_status": Organization.PartnerStatus.SUSPENDED},
            ),
            (
                "former",
                {"partner_status": Organization.PartnerStatus.FORMER},
            ),
        )

        for suffix, overrides in cases:
            organization = self.create_organization(
                name=f"Unavailable {suffix}",
                slug=f"unavailable-{suffix}",
                **overrides,
            )
            with self.subTest(suffix=suffix):
                response = self.client.post(
                    reverse(
                        "public_partner_follow",
                        kwargs={"slug": organization.slug},
                    )
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
                self.assertFalse(
                    OrganizationFollow.objects.filter(
                        organization=organization
                    ).exists()
                )

    def test_database_uniqueness_prevents_duplicate_relationships(self):
        OrganizationFollow.objects.create(
            organization=self.organization,
            user=self.user,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            OrganizationFollow.objects.create(
                organization=self.organization,
                user=self.user,
            )

        self.assertEqual(
            OrganizationFollow.objects.filter(
                organization=self.organization,
                user=self.user,
            ).count(),
            1,
        )

    def test_detail_follow_state_and_count_are_organization_scoped(self):
        OrganizationFollow.objects.create(
            organization=self.organization,
            user=self.user,
        )
        OrganizationFollow.objects.create(
            organization=self.organization,
            user=self.other_user,
        )
        OrganizationFollow.objects.create(
            organization=self.other_organization,
            user=self.user,
        )

        authenticated = self.client.get(
            reverse(
                "public_partner_detail",
                kwargs={"slug": self.organization.slug},
            )
        )
        anonymous = APIClient().get(
            reverse(
                "public_partner_detail",
                kwargs={"slug": self.organization.slug},
            )
        )

        self.assertEqual(authenticated.data["followers_count"], 2)
        self.assertTrue(authenticated.data["is_following"])
        self.assertEqual(anonymous.data["followers_count"], 2)
        self.assertFalse(anonymous.data["is_following"])
