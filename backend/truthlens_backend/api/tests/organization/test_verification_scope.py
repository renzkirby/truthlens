from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APIClient

from api.models import AccountabilityEvent, Organization, OrganizationMembership
from api.organization_scope_service import (
    OrganizationScopeForbidden, OrganizationScopeInvalid,
    can_manage_specializations, update_organization_specializations,
    serialize_organization_scope,
)
from api.verification_domain_policy import organization_specializations, eligibility_reason


class OrganizationVerificationScopeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="scope-owner")
        self.admin = User.objects.create_user(username="scope-admin")
        self.lead = User.objects.create_user(username="scope-lead")
        self.superuser = User.objects.create_superuser(
            username="scope-platform-admin", email="scope-admin@example.test"
        )
        self.organization = Organization.objects.create(
            name="Scope Research Organization",
            slug="scope-research-organization",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        for user, role in (
            (self.owner, OrganizationMembership.Role.OWNER),
            (self.admin, OrganizationMembership.Role.ADMIN),
            (self.lead, OrganizationMembership.Role.LEAD_VERIFIER),
        ):
            OrganizationMembership.objects.create(
                organization=self.organization, user=user, role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )
        self.url = reverse("organization_verification_scope", args=[self.organization.pk])

    def test_owner_updates_specializations_immediately_with_org_audit(self):
        updated = update_organization_specializations(
            organization=self.organization, actor=self.owner,
            domains=["TECHNOLOGY", "SCIENCE"],
            rationale="We have specialist teams covering science and technology.",
        )
        self.assertEqual(organization_specializations(updated), ["SCIENCE", "TECHNOLOGY"])
        self.assertEqual(updated.approved_verification_domains, [])
        self.assertEqual(updated.active_verification_domains, [])
        self.assertEqual(
            serialize_organization_scope(updated, actor=self.owner)["can_manage"], True,
        )
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED
        )
        self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.ORGANIZATION)
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.previous_state, {"domains": []})
        self.assertEqual(event.new_state, {"domains": ["SCIENCE", "TECHNOLOGY"]})

    def test_org_admin_and_platform_admin_cannot_self_edit(self):
        for user in (self.admin, self.lead, self.superuser):
            with self.subTest(user=user.username), self.assertRaises(OrganizationScopeForbidden):
                update_organization_specializations(
                    organization=self.organization, actor=user,
                    domains=["SCIENCE"], rationale="A restricted actor tries to change scope.",
                )
            self.assertFalse(can_manage_specializations(
                organization=self.organization, actor=user,
            ))

    def test_membership_must_be_active_primary_admin(self):
        membership = OrganizationMembership.objects.get(
            organization=self.organization, user=self.owner,
        )
        membership.status = OrganizationMembership.Status.SUSPENDED
        membership.save(update_fields=["status"])
        with self.assertRaises(OrganizationScopeForbidden):
            update_organization_specializations(
                organization=self.organization, actor=self.owner,
                domains=["SCIENCE"], rationale="Suspended membership must not change scope.",
            )

    def test_invalid_specializations_rejected_without_side_effects(self):
        for domains in (["ALIENS"], ["SCIENCE", "SCIENCE"], "SCIENCE"):
            with self.subTest(domains=domains), self.assertRaises(OrganizationScopeInvalid):
                update_organization_specializations(
                    organization=self.organization, actor=self.owner,
                    domains=domains, rationale="Invalid proposed organization specialization.",
                )
        self.assertEqual(self.organization.verification_specializations, [])
        self.assertFalse(AccountabilityEvent.objects.exists())

    def test_owner_can_downscope_and_unset_without_reapproval(self):
        for domains in (["SCIENCE", "TECHNOLOGY"], ["SCIENCE"], []):
            updated = update_organization_specializations(
                organization=self.organization, actor=self.owner,
                domains=domains, rationale="Updating our current investigation team coverage.",
            )
            self.assertEqual(organization_specializations(updated), sorted(domains))
        self.assertEqual(
            AccountabilityEvent.objects.filter(
                action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED
            ).count(), 3,
        )

    def test_geography_and_historical_approval_never_affect_eligibility(self):
        self.organization.verification_specializations = ["SCIENCE"]
        self.organization.approved_verification_domains = ["SPORTS"]
        self.organization.approved_verification_jurisdictions = ["PH"]
        self.organization.save(update_fields=[
            "verification_specializations", "approved_verification_domains",
            "approved_verification_jurisdictions",
        ])
        class Subject:
            domains = ["SCIENCE"]
            jurisdiction = ""
        self.assertIsNone(eligibility_reason(
            classification=Subject(), specializations=organization_specializations(self.organization)
        ))
        Subject.domains = ["SPORTS"]
        self.assertEqual(eligibility_reason(
            classification=Subject(), specializations=organization_specializations(self.organization)
        ), "OUTSIDE_SPECIALIZATIONS")

    def test_endpoint_primary_admin_updates_admin_reads_others_denied(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.patch(self.url, data={
            "domains": ["SCIENCE"], "rationale": "Qualified for scientific investigations.",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["specializations"], ["SCIENCE"])
        self.assertTrue(response.data["can_manage"])

        client.force_authenticate(user=self.admin)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_manage"])
        response = client.patch(self.url, data={
            "domains": ["SPORTS"], "rationale": "Admin cannot change primary admin settings.",
        }, format="json")
        self.assertEqual(response.status_code, 403)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.verification_specializations, ["SCIENCE"])

        client.force_authenticate(user=self.superuser)
        self.assertEqual(client.patch(self.url, data={
            "domains": ["SPORTS"], "rationale": "Platform cannot change institutional expertise.",
        }, format="json").status_code, 403)
        client.force_authenticate(user=self.lead)
        self.assertEqual(client.get(self.url).status_code, 403)

    def test_platform_governance_and_retry_urls_are_removed(self):
        for legacy_name, args in (
            ("management_organization_verification_scope", [self.organization.pk]),
            ("management_unclassified_intake", []),
            ("management_classification_retry", [self.organization.pk]),
            ("management_investigation_classification", [self.organization.pk]),
        ):
            with self.subTest(legacy_name=legacy_name), self.assertRaises(NoReverseMatch):
                reverse(legacy_name, args=args)

    def test_legacy_request_and_geographic_payload_is_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.patch(self.url, data={
            "action": "REQUEST", "domains": ["SCIENCE"],
            "jurisdictions": ["PH"], "rationale": "Legacy request must not grant scope.",
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.verification_specializations, [])
