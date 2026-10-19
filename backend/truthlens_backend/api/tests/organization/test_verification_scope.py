from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api.management_governance_service import approve_organization_verification_scope
from api.models import (
    AccountabilityEvent, Organization, OrganizationMembership,
)
from api.organization_scope_service import (
    OrganizationScopeForbidden, OrganizationScopeInvalid,
    configure_active_scope, serialize_organization_scope, submit_scope_request,
)
from api.verification_domain_policy import effective_organization_scope


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
                organization=self.organization,
                user=user,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )
        self.url = reverse(
            "organization_verification_scope", args=[self.organization.pk]
        )

    def test_owner_request_is_audited_but_does_not_self_approve(self):
        scope = submit_scope_request(
            organization=self.organization,
            actor=self.owner,
            domains=["SCIENCE"], jurisdictions=["PH"],
            rationale="Our institution has reviewed scientific research competence.",
        )
        self.assertEqual(scope.requested_verification_domains, ["SCIENCE"])
        self.assertEqual(scope.approved_verification_domains, [])
        self.assertEqual(effective_organization_scope(scope), ([], []))
        self.assertTrue(AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_REQUESTED,
            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
            actor=self.owner,
        ).exists())

    def test_unapproved_scope_cannot_be_activated(self):
        submit_scope_request(
            organization=self.organization,
            actor=self.owner,
            domains=["SCIENCE"], jurisdictions=["PH"],
            rationale="Research expertise requesting appropriate investigation scope.",
        )
        with self.assertRaises(OrganizationScopeInvalid):
            configure_active_scope(
                organization=self.organization,
                actor=self.admin,
                domains=["SCIENCE"], jurisdictions=["PH"],
                rationale="Prematurely enabling specializations before approval.",
            )

    def test_platform_approval_leaves_new_authority_inactive(self):
        submit_scope_request(
            organization=self.organization,
            actor=self.owner,
            domains=["SCIENCE"], jurisdictions=["PH"],
            rationale="Evidence of scientific competence submitted for review.",
        )
        org = approve_organization_verification_scope(
            organization_id=self.organization.pk,
            actor=self.superuser,
            domains=["SCIENCE"], jurisdictions=["PH"],
            rationale="Platform reviewed institutional scientific qualifications.",
        )
        self.assertEqual(org.approved_verification_domains, ["SCIENCE"])
        self.assertEqual(effective_organization_scope(org), ([], []))
        org = configure_active_scope(
            organization=org, actor=self.admin,
            domains=["SCIENCE"], jurisdictions=["PH"],
            rationale="Enable approved scientific investigations for our team.",
        )
        self.assertEqual(effective_organization_scope(org), (["SCIENCE"], ["PH"]))
        self.assertTrue(AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_VERIFICATION_SCOPE_ACTIVATED,
            actor=self.admin,
        ).exists())

    def test_platform_revocation_reduces_active_scope(self):
        submit_scope_request(
            organization=self.organization,
            actor=self.owner,
            domains=["SCIENCE", "TECHNOLOGY"], jurisdictions=["PH"],
            rationale="Review our research and technology team capabilities.",
        )
        org = approve_organization_verification_scope(
            organization_id=self.organization.pk, actor=self.superuser,
            domains=["SCIENCE", "TECHNOLOGY"], jurisdictions=["PH"],
            rationale="Approve evidence-backed science and technology coverage.",
        )
        configure_active_scope(
            organization=org, actor=self.owner,
            domains=["SCIENCE", "TECHNOLOGY"], jurisdictions=["PH"],
            rationale="Enable both reviewed specialist groups for intake.",
        )
        org = approve_organization_verification_scope(
            organization_id=self.organization.pk, actor=self.superuser,
            domains=["SCIENCE"], jurisdictions=["PH"],
            rationale="Technology authorization revoked after platform review.",
        )
        self.assertEqual(org.active_verification_domains, ["SCIENCE"])

    def test_lead_verifier_and_outsiders_cannot_manage_organization_scope(self):
        with self.assertRaises(OrganizationScopeForbidden):
            submit_scope_request(
                organization=self.organization, actor=self.lead,
                domains=["SCIENCE"], jurisdictions=["PH"],
                rationale="Ineligible non-management role attempts scope request.",
            )

    def test_endpoint_rejects_non_manager_and_exposes_distinct_sets(self):
        client = APIClient()
        client.force_authenticate(user=self.lead)
        response = client.get(self.url)
        self.assertEqual(response.status_code, 403)
        client.force_authenticate(user=self.owner)
        response = client.patch(self.url, data={
            "action": "REQUEST",
            "domains": ["SCIENCE"],
            "jurisdictions": ["PH"],
            "rationale": "Our qualified reviewers can handle science coverage.",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["requested_domains"], ["SCIENCE"])
        self.assertEqual(response.data["approved_domains"], [])
        client.force_authenticate(user=self.lead)
        response = client.patch(self.url, data={
            "action": "ACTIVATE",
            "domains": ["SCIENCE"],
            "jurisdictions": ["PH"],
            "rationale": "Unauthorized attempt to activate investigation scope.",
        }, format="json")
        self.assertEqual(response.status_code, 403)
