from datetime import timedelta

from django.core.cache import cache
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from api.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)


class PublicPartnerApiTests(APITestCase):
    public_fields = {
        "id",
        "name",
        "slug",
        "description",
        "website",
        "logo_url",
        "organization_type",
        "organization_type_label",
        "expertise_areas",
    }

    def setUp(self):
        cache.clear()

        self.alpha = self.create_organization(
            name="Alpha Verification",
            slug="alpha-verification",
            description="Election integrity reporting.",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            logo_url="https://example.com/alpha-logo.png",
            public_logo_enabled=False,
        )

        self.beta = self.create_organization(
            name="Beta Newsroom",
            slug="beta-newsroom",
            description="Regional accountability journalism.",
            organization_type=Organization.OrganizationType.NEWS,
            logo_url="https://example.com/beta-logo.png",
            public_logo_enabled=True,
        )

        self.climate = self.create_organization(
            name="Climate Research Lab",
            slug="climate-research-lab",
            description="Independent climate science investigations.",
            organization_type=Organization.OrganizationType.RESEARCH,
        )

        self.private = self.create_organization(
            name="Private Partner",
            slug="private-partner",
            description="Climate science kept private.",
            organization_type=Organization.OrganizationType.RESEARCH,
            public_profile_enabled=False,
        )

        self.directory_url = reverse("public_partner_directory")

    def create_organization(
        self,
        *,
        name,
        slug,
        description="",
        organization_type=Organization.OrganizationType.OTHER,
        verification_status=Organization.VerificationStatus.VERIFIED,
        partner_status=Organization.PartnerStatus.ACTIVE,
        public_profile_enabled=True,
        logo_url=None,
        public_logo_enabled=False,
    ):
        return Organization.objects.create(
            name=name,
            slug=slug,
            description=description,
            website=f"https://example.com/{slug}",
            logo_url=logo_url,
            organization_type=organization_type,
            verification_status=verification_status,
            partner_status=partner_status,
            expertise_areas=["media literacy"],
            public_profile_enabled=public_profile_enabled,
            public_logo_enabled=public_logo_enabled,
        )

    def detail_url(
        self,
        organization,
    ):
        return reverse(
            "public_partner_detail",
            kwargs={
                "slug": organization.slug,
            },
        )

    def test_directory_exposes_only_publicly_eligible_organizations(self):
        response = APIClient().get(self.directory_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["count"],
            3,
        )
        self.assertEqual(
            [item["slug"] for item in response.data["results"]],
            [
                self.alpha.slug,
                self.beta.slug,
                self.climate.slug,
            ],
        )

    def test_eligible_slug_returns_public_profile(self):
        response = APIClient().get(
            self.detail_url(self.alpha),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["slug"],
            self.alpha.slug,
        )

    def test_non_public_slug_returns_not_found(self):
        response = APIClient().get(
            self.detail_url(self.private),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_unknown_slug_returns_not_found(self):
        response = APIClient().get(
            reverse(
                "public_partner_detail",
                kwargs={
                    "slug": "unknown-partner",
                },
            ),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_logo_is_exposed_when_public_logo_is_enabled(self):
        response = APIClient().get(
            self.detail_url(self.beta),
        )

        self.assertEqual(
            response.data["logo_url"],
            self.beta.logo_url,
        )

    def test_logo_is_hidden_when_public_logo_is_disabled(self):
        response = APIClient().get(
            self.detail_url(self.alpha),
        )

        self.assertIsNone(response.data["logo_url"])

    def test_public_response_exposes_only_explicit_profile_fields(self):
        member = User.objects.create_user(
            username="private-partner-member",
            email="private-member@example.com",
            password="test-password",
        )

        OrganizationMembership.objects.create(
            organization=self.alpha,
            user=member,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        now = timezone.now()

        OrganizationInvitation.objects.create(
            organization=self.alpha,
            email="private-invitation@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            invited_by=member,
            token_digest="a" * 64,
            expires_at=now + timedelta(days=7),
            last_sent_at=now,
        )

        response = APIClient().get(
            self.detail_url(self.alpha),
        )

        self.assertEqual(
            set(response.data.keys()),
            self.public_fields,
        )

        serialized_response = str(response.data)

        for private_value in [
            member.username,
            member.email,
            "private-invitation@example.com",
            "memberships",
            "invitations",
            "capabilities",
            "trust_score",
            "verification_status",
            "partner_status",
        ]:
            self.assertNotIn(
                private_value,
                serialized_response,
            )

    def test_directory_is_deterministically_ordered_by_name(self):
        response = APIClient().get(self.directory_url)

        self.assertEqual(
            [item["name"] for item in response.data["results"]],
            sorted(item["name"] for item in response.data["results"]),
        )

    def test_search_matches_name_case_insensitively(self):
        response = APIClient().get(
            self.directory_url,
            {
                "search": "bEtA nEwS",
            },
        )

        self.assertEqual(
            [item["slug"] for item in response.data["results"]],
            [self.beta.slug],
        )

    def test_search_matches_description_case_insensitively(self):
        response = APIClient().get(
            self.directory_url,
            {
                "search": "CLIMATE SCIENCE",
            },
        )

        self.assertEqual(
            [item["slug"] for item in response.data["results"]],
            [self.climate.slug],
        )

    def test_valid_type_filters_directory(self):
        response = APIClient().get(
            self.directory_url,
            {
                "type": Organization.OrganizationType.NEWS,
            },
        )

        self.assertEqual(
            [item["slug"] for item in response.data["results"]],
            [self.beta.slug],
        )

    def test_blank_type_does_not_filter_directory(self):
        response = APIClient().get(
            self.directory_url,
            {
                "type": "",
            },
        )

        self.assertEqual(
            response.data["count"],
            3,
        )

    def test_invalid_type_returns_bad_request(self):
        response = APIClient().get(
            self.directory_url,
            {
                "type": "INVALID_TYPE",
            },
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_combined_filters_cannot_bypass_public_eligibility(self):
        response = APIClient().get(
            self.directory_url,
            {
                "search": "climate science",
                "type": Organization.OrganizationType.RESEARCH,
            },
        )

        self.assertEqual(
            [item["slug"] for item in response.data["results"]],
            [self.climate.slug],
        )
        self.assertNotIn(
            self.private.slug,
            [item["slug"] for item in response.data["results"]],
        )

    def test_directory_rejects_post(self):
        response = APIClient().post(
            self.directory_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_detail_rejects_patch(self):
        response = APIClient().patch(
            self.detail_url(self.alpha),
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_detail_rejects_delete(self):
        response = APIClient().delete(
            self.detail_url(self.alpha),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_anonymous_user_can_read_directory(self):
        response = APIClient().get(self.directory_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_anonymous_user_can_read_eligible_detail(self):
        response = APIClient().get(
            self.detail_url(self.alpha),
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
