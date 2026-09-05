import uuid

from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse

from rest_framework import status
from rest_framework.test import (
    APIClient,
    APITestCase,
)

from api.models import (
    Organization,
    OrganizationMembership,
)


class OrganizationPublicProfileAdminApiTests(APITestCase):
    response_fields = {
        "id",
        "name",
        "slug",
        "organization_type",
        "organization_type_label",
        "verification_status",
        "partner_status",
        "description",
        "website",
        "logo_url",
        "expertise_areas",
        "public_profile_enabled",
        "public_logo_enabled",
        "publicly_visible",
    }

    def setUp(self):
        cache.clear()

        self.organization = Organization.objects.create(
            name="Public Profile Admin Partner",
            slug="public-profile-admin-partner",
            description="Original description",
            website="https://example.com/original",
            logo_url="https://example.com/original-logo.png",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            expertise_areas=["Original expertise"],
        )

        self.other_organization = Organization.objects.create(
            name="Other Public Profile Admin Partner",
            slug="other-public-profile-admin-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

        self.owner = self.create_member(
            "public-profile-owner",
            OrganizationMembership.Role.OWNER,
        )
        self.admin = self.create_member(
            "public-profile-admin",
            OrganizationMembership.Role.ADMIN,
        )
        self.lead = self.create_member(
            "public-profile-lead",
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self.other_owner = self.create_member(
            "other-public-profile-owner",
            OrganizationMembership.Role.OWNER,
            organization=self.other_organization,
        )

        self.url = reverse(
            "organization_public_profile",
            kwargs={
                "organization_id": self.organization.id,
            },
        )
        self.public_detail_url = reverse(
            "public_partner_detail",
            kwargs={
                "slug": self.organization.slug,
            },
        )
        self.public_directory_url = reverse("public_partner_directory")

    def create_member(
        self,
        username,
        role,
        *,
        organization=None,
    ):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
        )

        OrganizationMembership.objects.create(
            organization=organization or self.organization,
            user=user,
            role=role,
            status=OrganizationMembership.Status.ACTIVE,
        )

        return user

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)

        return client

    def test_unauthenticated_get_is_rejected(self):
        response = APIClient().get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_owner_can_get_public_profile_configuration(self):
        response = self.client_for(self.owner).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            set(response.data.keys()),
            self.response_fields,
        )
        self.assertFalse(response.data["publicly_visible"])

    def test_admin_can_get_public_profile_configuration(self):
        response = self.client_for(self.admin).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

    def test_member_without_management_capability_cannot_get_configuration(self):
        response = self.client_for(self.lead).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_other_organization_manager_cannot_get_configuration(self):
        response = self.client_for(self.other_owner).get(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_unknown_organization_returns_not_found(self):
        url = reverse(
            "organization_public_profile",
            kwargs={
                "organization_id": uuid.uuid4(),
            },
        )

        response = self.client_for(self.owner).get(url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_owner_can_patch_public_profile_configuration(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "description": "Owner updated description",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["description"],
            "Owner updated description",
        )

    def test_admin_can_patch_public_profile_configuration(self):
        response = self.client_for(self.admin).patch(
            self.url,
            {
                "description": "Admin updated description",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["description"],
            "Admin updated description",
        )

    def test_member_without_management_capability_cannot_patch_configuration(self):
        response = self.client_for(self.lead).patch(
            self.url,
            {
                "description": "Unauthorized update",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_other_organization_manager_cannot_patch_configuration(self):
        response = self.client_for(self.other_owner).patch(
            self.url,
            {
                "description": "Cross-organization update",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_all_administrable_fields_persist(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "description": "Updated public description",
                "website": "https://example.org/updated",
                "logo_url": "https://example.org/updated-logo.png",
                "expertise_areas": ["Elections", "Health"],
                "public_profile_enabled": True,
                "public_logo_enabled": True,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.description, "Updated public description")
        self.assertEqual(self.organization.website, "https://example.org/updated")
        self.assertEqual(
            self.organization.logo_url,
            "https://example.org/updated-logo.png",
        )
        self.assertEqual(self.organization.expertise_areas, ["Elections", "Health"])
        self.assertTrue(self.organization.public_profile_enabled)
        self.assertTrue(self.organization.public_logo_enabled)

    def test_partial_patch_leaves_unspecified_fields_unchanged(self):
        original_website = self.organization.website
        original_logo_url = self.organization.logo_url
        original_expertise = self.organization.expertise_areas

        response = self.client_for(self.owner).patch(
            self.url,
            {
                "description": "Only description changed",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.website, original_website)
        self.assertEqual(self.organization.logo_url, original_logo_url)
        self.assertEqual(self.organization.expertise_areas, original_expertise)
        self.assertFalse(self.organization.public_profile_enabled)
        self.assertFalse(self.organization.public_logo_enabled)

    def test_protected_and_unknown_fields_are_rejected(self):
        protected_values = {
            "name": "Renamed organization",
            "slug": "changed-slug",
            "organization_type": Organization.OrganizationType.NEWS,
            "verification_status": Organization.VerificationStatus.REJECTED,
            "partner_status": Organization.PartnerStatus.SUSPENDED,
            "unexpected_field": "unexpected value",
        }

        for field_name, value in protected_values.items():
            with self.subTest(field_name=field_name):
                response = self.client_for(self.owner).patch(
                    self.url,
                    {
                        field_name: value,
                    },
                    format="json",
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.name, "Public Profile Admin Partner")
        self.assertEqual(self.organization.slug, "public-profile-admin-partner")
        self.assertEqual(
            self.organization.organization_type,
            Organization.OrganizationType.FACT_CHECKING,
        )
        self.assertEqual(
            self.organization.verification_status,
            Organization.VerificationStatus.VERIFIED,
        )
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )

    def test_malformed_website_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "website": "not-a-url",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_string_description_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "description": 123,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_http_website_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "website": "ftp://example.com/profile",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_malformed_logo_url_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "logo_url": "not-a-url",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_list_expertise_areas_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "expertise_areas": "Elections",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_too_many_expertise_areas_are_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "expertise_areas": [f"Area {index}" for index in range(21)],
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_overlong_expertise_area_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "expertise_areas": ["a" * 101],
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_non_string_expertise_area_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "expertise_areas": ["Elections", 123],
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_blank_expertise_area_is_rejected(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "expertise_areas": ["Elections", "   "],
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_expertise_areas_are_trimmed_and_case_insensitively_deduplicated(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "expertise_areas": [
                    "  Elections  ",
                    "elections",
                    "Health",
                    "HEALTH",
                    "Media Literacy",
                ],
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data["expertise_areas"],
            [
                "Elections",
                "Health",
                "Media Literacy",
            ],
        )

    def test_blank_urls_are_normalized_to_null(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "website": "",
                "logo_url": "",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertIsNone(response.data["website"])
        self.assertIsNone(response.data["logo_url"])

    def test_description_is_trimmed_and_may_be_blank(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "description": "  Updated description  ",
            },
            format="json",
        )

        self.assertEqual(response.data["description"], "Updated description")

        response = self.client_for(self.owner).patch(
            self.url,
            {
                "description": "   ",
            },
            format="json",
        )

        self.assertEqual(response.data["description"], "")

    def test_non_boolean_public_flags_are_rejected(self):
        for field_name, value in [
            ("public_profile_enabled", "yes"),
            ("public_logo_enabled", 1),
        ]:
            with self.subTest(field_name=field_name):
                response = self.client_for(self.owner).patch(
                    self.url,
                    {
                        field_name: value,
                    },
                    format="json",
                )

                self.assertEqual(
                    response.status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

    def test_public_profile_and_logo_consent_flags_remain_independent(self):
        self.organization.public_profile_enabled = True
        self.organization.public_logo_enabled = True
        self.organization.save(
            update_fields=[
                "public_profile_enabled",
                "public_logo_enabled",
            ]
        )

        response = self.client_for(self.owner).patch(
            self.url,
            {
                "public_profile_enabled": False,
            },
            format="json",
        )

        self.assertFalse(response.data["public_profile_enabled"])
        self.assertTrue(response.data["public_logo_enabled"])

        self.organization.public_logo_enabled = False
        self.organization.save(update_fields=["public_logo_enabled"])

        response = self.client_for(self.owner).patch(
            self.url,
            {
                "public_logo_enabled": True,
            },
            format="json",
        )

        self.assertFalse(response.data["public_profile_enabled"])
        self.assertTrue(response.data["public_logo_enabled"])
        self.assertFalse(response.data["publicly_visible"])

    def test_enabling_profile_makes_verified_active_partner_public(self):
        response = self.client_for(self.owner).patch(
            self.url,
            {
                "public_profile_enabled": True,
            },
            format="json",
        )

        self.assertTrue(response.data["publicly_visible"])

        public_response = APIClient().get(self.public_directory_url)

        self.assertIn(
            self.organization.slug,
            [item["slug"] for item in public_response.data["results"]],
        )

    def test_disabling_profile_immediately_hides_partner(self):
        self.organization.public_profile_enabled = True
        self.organization.save(update_fields=["public_profile_enabled"])

        response = self.client_for(self.owner).patch(
            self.url,
            {
                "public_profile_enabled": False,
            },
            format="json",
        )

        self.assertFalse(response.data["publicly_visible"])
        self.assertEqual(
            APIClient().get(self.public_detail_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_enabling_logo_immediately_exposes_configured_logo(self):
        self.organization.public_profile_enabled = True
        self.organization.save(update_fields=["public_profile_enabled"])

        self.client_for(self.owner).patch(
            self.url,
            {
                "public_logo_enabled": True,
            },
            format="json",
        )

        public_response = APIClient().get(self.public_detail_url)

        self.assertEqual(
            public_response.data["logo_url"],
            self.organization.logo_url,
        )

    def test_disabling_logo_immediately_hides_configured_logo(self):
        self.organization.public_profile_enabled = True
        self.organization.public_logo_enabled = True
        self.organization.save(
            update_fields=[
                "public_profile_enabled",
                "public_logo_enabled",
            ]
        )

        self.client_for(self.owner).patch(
            self.url,
            {
                "public_logo_enabled": False,
            },
            format="json",
        )

        public_response = APIClient().get(self.public_detail_url)

        self.assertIsNone(public_response.data["logo_url"])

    def test_enabled_unverified_organization_remains_private(self):
        self.organization.verification_status = (
            Organization.VerificationStatus.UNVERIFIED
        )
        self.organization.save(update_fields=["verification_status"])

        response = self.client_for(self.owner).patch(
            self.url,
            {
                "public_profile_enabled": True,
            },
            format="json",
        )

        self.assertFalse(response.data["publicly_visible"])
        self.assertEqual(
            APIClient().get(self.public_detail_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_enabled_non_active_partner_states_remain_private(self):
        for partner_status in [
            Organization.PartnerStatus.NONE,
            Organization.PartnerStatus.SUSPENDED,
            Organization.PartnerStatus.FORMER,
        ]:
            with self.subTest(partner_status=partner_status):
                self.organization.partner_status = partner_status
                self.organization.public_profile_enabled = False
                self.organization.save(
                    update_fields=[
                        "partner_status",
                        "public_profile_enabled",
                    ]
                )

                response = self.client_for(self.owner).patch(
                    self.url,
                    {
                        "public_profile_enabled": True,
                    },
                    format="json",
                )

                self.assertFalse(response.data["publicly_visible"])
                self.assertEqual(
                    APIClient().get(self.public_detail_url).status_code,
                    status.HTTP_404_NOT_FOUND,
                )

    def test_post_is_not_allowed(self):
        response = self.client_for(self.owner).post(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_put_is_not_allowed(self):
        response = self.client_for(self.owner).put(
            self.url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_delete_is_not_allowed(self):
        response = self.client_for(self.owner).delete(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
