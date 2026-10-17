from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase

from api.management_governance_service import (
    MANAGE_PARTNER_ORGANIZATION,
    ManagementGovernanceAuthorizationError,
    ManagementGovernanceConflict,
    create_partner_organization,
    update_organization_platform_trust,
)
from api.models import AccountabilityEvent, Organization


class ManagementGovernanceServiceTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="management-governance-admin",
            email="management-governance@example.com",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="management-governance-staff",
            is_staff=True,
        )
        self.organization = Organization.objects.create(
            name="Governance Partner",
            slug="governance-partner",
            organization_type=Organization.OrganizationType.NEWS,
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.NONE,
            description="Organization-controlled content.",
            public_profile_enabled=True,
        )

    def create_organization(self, **overrides):
        values = {
            "name": "New Governance Partner",
            "slug": "new-governance-partner",
            "organization_type": Organization.OrganizationType.RESEARCH,
            "actor": self.platform_admin,
        }
        values.update(overrides)
        return create_partner_organization(**values)

    def test_creation_uses_safe_defaults_and_records_platform_accountability(self):
        organization = self.create_organization()

        self.assertEqual(
            organization.verification_status,
            Organization.VerificationStatus.UNVERIFIED,
        )
        self.assertEqual(organization.partner_status, Organization.PartnerStatus.NONE)
        self.assertFalse(organization.public_profile_enabled)
        self.assertFalse(organization.public_logo_enabled)
        self.assertIsNone(organization.description)
        self.assertIsNone(organization.website)
        self.assertIsNone(organization.logo_url)
        self.assertEqual(organization.expertise_areas, [])

        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
            resource_id=str(organization.pk),
        )
        self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.PLATFORM)
        self.assertEqual(event.actor, self.platform_admin)
        self.assertIsNone(event.authority_organization)
        self.assertEqual(event.subject_organization, organization)
        self.assertEqual(event.resource_type, AccountabilityEvent.ResourceType.ORGANIZATION)
        self.assertEqual(event.capability, MANAGE_PARTNER_ORGANIZATION)
        self.assertEqual(
            event.new_state,
            {
                "name": "New Governance Partner",
                "slug": "new-governance-partner",
                "organization_type": Organization.OrganizationType.RESEARCH,
                "verification_status": Organization.VerificationStatus.UNVERIFIED,
                "partner_status": Organization.PartnerStatus.NONE,
            },
        )
        self.assertEqual(event.previous_state, {})

    def test_service_rejects_every_non_platform_authority(self):
        inactive_superuser = User.objects.create_superuser(
            username="inactive-management-governance-admin",
            is_active=False,
        )
        for actor in (None, AnonymousUser(), self.staff_user, inactive_superuser):
            with self.subTest(actor=actor), self.assertRaises(
                ManagementGovernanceAuthorizationError
            ):
                self.create_organization(actor=actor)

        self.assertFalse(
            Organization.objects.filter(slug="new-governance-partner").exists()
        )

    def test_creation_rejects_case_insensitive_name_and_duplicate_slug(self):
        for overrides, field in (
            ({"name": "gOvErNaNcE pArTnEr"}, "name"),
            ({"slug": self.organization.slug}, "slug"),
        ):
            with self.subTest(field=field), self.assertRaises(
                ManagementGovernanceConflict
            ) as context:
                self.create_organization(**overrides)
            self.assertEqual(context.exception.field, field)

        self.assertFalse(
            AccountabilityEvent.objects.filter(
                action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED
            ).exists()
        )

    def test_creation_rolls_back_when_accountability_fails(self):
        with patch(
            "api.management_governance_service.record_accountability_event",
            side_effect=RuntimeError("audit unavailable"),
        ), self.assertRaises(RuntimeError):
            self.create_organization()

        self.assertFalse(
            Organization.objects.filter(slug="new-governance-partner").exists()
        )

    def test_platform_trust_update_changes_only_governance_fields_and_audits(self):
        original_description = self.organization.description

        updated = update_organization_platform_trust(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

        self.assertEqual(updated.verification_status, Organization.VerificationStatus.VERIFIED)
        self.assertEqual(updated.partner_status, Organization.PartnerStatus.ACTIVE)
        self.assertEqual(updated.description, original_description)
        event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
            ),
            resource_id=str(self.organization.pk),
        )
        self.assertEqual(
            event.previous_state,
            {
                "verification_status": Organization.VerificationStatus.PENDING,
                "partner_status": Organization.PartnerStatus.NONE,
            },
        )
        self.assertEqual(
            event.new_state,
            {
                "verification_status": Organization.VerificationStatus.VERIFIED,
                "partner_status": Organization.PartnerStatus.ACTIVE,
            },
        )
        self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.PLATFORM)
        self.assertEqual(event.actor, self.platform_admin)
        self.assertEqual(event.subject_organization, self.organization)
        self.assertEqual(event.capability, MANAGE_PARTNER_ORGANIZATION)

    def test_no_op_platform_trust_update_does_not_write_or_audit(self):
        original_updated_at = self.organization.updated_at

        update_organization_platform_trust(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
            verification_status=self.organization.verification_status,
            partner_status=self.organization.partner_status,
        )

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.updated_at, original_updated_at)
        self.assertFalse(
            AccountabilityEvent.objects.filter(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
                )
            ).exists()
        )

    def test_platform_trust_update_rolls_back_when_accountability_fails(self):
        with patch(
            "api.management_governance_service.record_accountability_event",
            side_effect=RuntimeError("audit unavailable"),
        ), self.assertRaises(RuntimeError):
            update_organization_platform_trust(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
                partner_status=Organization.PartnerStatus.SUSPENDED,
            )

        self.organization.refresh_from_db()
        self.assertEqual(self.organization.partner_status, Organization.PartnerStatus.NONE)

