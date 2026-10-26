from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from api.models import (
    AccountabilityEvent,
    Institution,
    Organization,
    OrganizationInstitutionAffiliation,
)
from api.verification_domain_policy import (
    eligibility_reason,
    organization_specializations,
)


class InstitutionAffiliationFoundationTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="institution-platform-admin",
            email="institution-admin@example.test",
            password="test-password",
        )
        self.ordinary_user = User.objects.create_user(
            username="institution-ordinary-user",
            password="test-password",
        )
        self.newsroom = Organization.objects.create(
            name="Campus Chronicle",
            slug="campus-chronicle",
            organization_type=Organization.OrganizationType.NEWS,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.research_org = Organization.objects.create(
            name="Campus Research Lab",
            slug="campus-research-lab",
            organization_type=Organization.OrganizationType.RESEARCH,
        )
        self.institution = Institution.objects.create(
            name="Example University",
            slug="example-university",
            website="https://university.example.test",
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_student_publication_subtype_requires_news_organization(self):
        organization = Organization(
            name="Invalid Student Publication",
            slug="invalid-student-publication",
            organization_type=Organization.OrganizationType.RESEARCH,
            organization_subtype=(
                Organization.OrganizationSubtype.STUDENT_PUBLICATION
            ),
        )

        with self.assertRaises(ValidationError) as raised:
            organization.full_clean()

        self.assertIn("organization_subtype", raised.exception.message_dict)

    def test_platform_admin_can_create_canonical_institution_with_audit(self):
        response = self.client_for(self.platform_admin).post(
            reverse("management_institutions"),
            {
                "name": "Second University",
                "slug": "second-university",
                "website": "https://second.example.test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        institution = Institution.objects.get(slug="second-university")
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.INSTITUTION_CREATED,
            resource_id=str(institution.id),
        )
        self.assertEqual(
            event.resource_type,
            AccountabilityEvent.ResourceType.INSTITUTION,
        )
        self.assertEqual(event.actor, self.platform_admin)

    def test_non_platform_user_cannot_manage_institutions(self):
        response = self.client_for(self.ordinary_user).post(
            reverse("management_institutions"),
            {
                "name": "Unauthorized University",
                "slug": "unauthorized-university",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            Institution.objects.filter(slug="unauthorized-university").exists()
        )

    def test_verified_affiliation_sets_student_publication_identity_and_scope(self):
        response = self.client_for(self.platform_admin).put(
            reverse(
                "management_organization_institution_affiliation",
                kwargs={"organization_id": self.newsroom.id},
            ),
            {
                "institution_id": str(self.institution.id),
                "verification_status": (
                    OrganizationInstitutionAffiliation.VerificationStatus.VERIFIED
                ),
                "rationale": (
                    "Platform review confirmed this publication belongs to "
                    "Example University."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.newsroom.refresh_from_db()
        self.assertEqual(
            self.newsroom.organization_subtype,
            Organization.OrganizationSubtype.STUDENT_PUBLICATION,
        )

        affiliation = OrganizationInstitutionAffiliation.objects.get(
            organization=self.newsroom
        )
        self.assertEqual(affiliation.institution, self.institution)
        self.assertEqual(
            affiliation.coverage_scope,
            OrganizationInstitutionAffiliation.CoverageScope.INSTITUTION_WIDE,
        )
        self.assertEqual(
            affiliation.verification_status,
            OrganizationInstitutionAffiliation.VerificationStatus.VERIFIED,
        )
        self.assertEqual(affiliation.reviewed_by, self.platform_admin)
        self.assertIsNotNone(affiliation.reviewed_at)

        event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.ORGANIZATION_INSTITUTION_AFFILIATION_UPDATED
            ),
            resource_id=str(affiliation.id),
        )
        self.assertEqual(event.subject_organization, self.newsroom)

        detail = self.client_for(self.platform_admin).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.newsroom.id},
            )
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail.data["organization_subtype"],
            Organization.OrganizationSubtype.STUDENT_PUBLICATION,
        )
        self.assertEqual(
            detail.data["institution_affiliation"]["institution"]["id"],
            str(self.institution.id),
        )

    def test_non_news_organization_cannot_receive_student_publication_affiliation(self):
        response = self.client_for(self.platform_admin).put(
            reverse(
                "management_organization_institution_affiliation",
                kwargs={"organization_id": self.research_org.id},
            ),
            {
                "institution_id": str(self.institution.id),
                "verification_status": (
                    OrganizationInstitutionAffiliation.VerificationStatus.PENDING
                ),
                "rationale": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.research_org.refresh_from_db()
        self.assertIsNone(self.research_org.organization_subtype)
        self.assertFalse(
            OrganizationInstitutionAffiliation.objects.filter(
                organization=self.research_org
            ).exists()
        )

    def test_reviewed_affiliation_requires_rationale(self):
        response = self.client_for(self.platform_admin).put(
            reverse(
                "management_organization_institution_affiliation",
                kwargs={"organization_id": self.newsroom.id},
            ),
            {
                "institution_id": str(self.institution.id),
                "verification_status": (
                    OrganizationInstitutionAffiliation.VerificationStatus.VERIFIED
                ),
                "rationale": "",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            OrganizationInstitutionAffiliation.objects.filter(
                organization=self.newsroom
            ).exists()
        )

    def test_verified_affiliation_does_not_change_current_subject_eligibility(self):
        self.newsroom.organization_subtype = (
            Organization.OrganizationSubtype.STUDENT_PUBLICATION
        )
        self.newsroom.save(update_fields=["organization_subtype"])
        OrganizationInstitutionAffiliation.objects.create(
            organization=self.newsroom,
            institution=self.institution,
            verification_status=(
                OrganizationInstitutionAffiliation.VerificationStatus.VERIFIED
            ),
            rationale="Verified for persistence-only test.",
            reviewed_by=self.platform_admin,
            reviewed_at=self.platform_admin.date_joined,
        )

        classification = SimpleNamespace(domains=["HEALTH"])
        self.assertEqual(
            eligibility_reason(
                classification=classification,
                specializations=organization_specializations(self.newsroom),
            ),
            "OUTSIDE_SPECIALIZATIONS",
        )
