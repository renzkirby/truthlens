import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.accountability_query_service import AccountabilityDomain, ORGANIZATION_DOMAINS
from api.management_governance_service import MANAGE_PARTNER_ORGANIZATION
from api.models import (
    AccountabilityEvent,
    Organization,
    OrganizationMembership,
)
from api.organization_provisioning_service import PROVISION_PARTNER_ORGANIZATION


class ManagementGovernanceAuditApiTests(APITestCase):
    def setUp(self):
        # DRF's default user throttle uses Django's shared cache. Database
        # isolation can recycle user IDs between tests, so isolate this class
        # from throttle state accumulated by earlier API tests.
        cache.clear()
        self.addCleanup(cache.clear)

        self.superuser = User.objects.create_superuser(
            username="governance-audit-admin",
            email="audit-admin@example.com",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            username="governance-audit-staff",
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="governance-audit-user",
        )
        self.primary_admin = User.objects.create_user(
            username="governance-primary-admin",
        )
        self.organization_admin = User.objects.create_user(
            username="governance-organization-admin",
        )
        self.inactive_superuser = User.objects.create_superuser(
            username="inactive-governance-audit-admin",
            is_active=False,
        )
        self.organization = Organization.objects.create(
            name="Audit Newsroom",
            slug="audit-newsroom",
        )
        self.other_organization = Organization.objects.create(
            name="Civic Research Lab",
            slug="civic-research-lab",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.primary_admin,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.collection_url = reverse("management_governance_audit")

    def client_for(self, user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def make_event(
        self,
        *,
        action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
        capability=MANAGE_PARTNER_ORGANIZATION,
        authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
        organization=None,
        actor=None,
        resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
        previous_state=None,
        new_state=None,
        context=None,
        notes="",
    ):
        organization = organization or self.organization
        actor = self.superuser if actor is None else actor
        authority_organization = (
            organization
            if authority_scope == AccountabilityEvent.AuthorityScope.ORGANIZATION
            else None
        )
        return AccountabilityEvent.objects.create(
            actor=actor,
            actor_username_snapshot=actor.username if actor else "",
            authority_scope=authority_scope,
            authority_organization=authority_organization,
            authority_organization_name_snapshot=(
                authority_organization.name if authority_organization else ""
            ),
            subject_organization=organization,
            subject_organization_name_snapshot=organization.name,
            capability=capability,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=str(organization.pk),
            previous_state=previous_state or {},
            new_state=new_state or {},
            context=context or {},
            notes=notes,
        )

    def detail_url(self, event):
        return reverse(
            "management_governance_audit_detail",
            kwargs={"event_id": event.pk},
        )

    def test_only_active_superuser_can_access_collection_and_detail(self):
        event = self.make_event()
        allowed_client = self.client_for(self.superuser)
        self.assertEqual(
            allowed_client.get(self.collection_url).status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            allowed_client.get(self.detail_url(event)).status_code,
            status.HTTP_200_OK,
        )

        for user, expected_status in (
            (self.staff_user, status.HTTP_403_FORBIDDEN),
            (self.ordinary_user, status.HTTP_403_FORBIDDEN),
            (self.primary_admin, status.HTTP_403_FORBIDDEN),
            (self.organization_admin, status.HTTP_403_FORBIDDEN),
            (self.inactive_superuser, status.HTTP_403_FORBIDDEN),
            (None, status.HTTP_401_UNAUTHORIZED),
        ):
            with self.subTest(user=user):
                client = self.client_for(user)
                self.assertEqual(client.get(self.collection_url).status_code, expected_status)
                self.assertEqual(client.get(self.detail_url(event)).status_code, expected_status)

    def test_projection_includes_only_allowed_action_capability_pairs(self):
        allowed = [
            self.make_event(),
            self.make_event(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
                ),
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
                capability=PROVISION_PARTNER_ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_RESENT,
                capability=PROVISION_PARTNER_ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            ),
            self.make_event(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED
                ),
                capability=PROVISION_PARTNER_ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
                previous_state={"status": "PENDING"},
                new_state={"status": "CANCELLED"},
            ),
        ]
        excluded = [
            self.make_event(
                action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
                capability="MANAGE_ORGANIZATION",
                authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.SAFETY_DISMISSED,
                capability="REVIEW_SAFETY",
                resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
                capability="REVIEW_EVIDENCE",
                resource_type=AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.VERDICT_ISSUED,
                capability="ADJUDICATE",
                resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
                capability="PUBLISH_FACT_CHECK",
                resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
            ),
            self.make_event(
                action_type=AccountabilityEvent.ActionType.ORGANIZATION_CREATED,
                capability=PROVISION_PARTNER_ORGANIZATION,
            ),
            self.make_event(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED
                ),
                capability="MANAGE_ORGANIZATION",
                authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            ),
            self.make_event(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED
                ),
                capability=MANAGE_PARTNER_ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            ),
            self.make_event(
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED
                ),
                capability=PROVISION_PARTNER_ORGANIZATION,
                resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
            ),
        ]

        response = self.client_for(self.superuser).get(self.collection_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {result["id"] for result in response.data["results"]},
            {str(event.pk) for event in allowed},
        )
        self.assertTrue(
            all(
                result["domain"] == AccountabilityDomain.PLATFORM_GOVERNANCE
                for result in response.data["results"]
            )
        )
        self.assertIn(
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
            {
                option["value"]
                for option in response.data["filter_options"]["actions"]
            },
        )
        for event in excluded:
            with self.subTest(event=event.action_type):
                self.assertEqual(
                    self.client_for(self.superuser).get(self.detail_url(event)).status_code,
                    status.HTTP_404_NOT_FOUND,
                )

    def test_filters_and_stable_pagination(self):
        now = timezone.now()
        first = self.make_event(actor=self.superuser)
        second_actor = User.objects.create_superuser(username="secondary-auditor")
        second = self.make_event(
            action_type=(
                AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
            ),
            organization=self.other_organization,
            actor=second_actor,
        )
        AccountabilityEvent.objects.filter(pk=first.pk).update(
            created_at=now - timedelta(days=2)
        )
        AccountabilityEvent.objects.filter(pk=second.pk).update(created_at=now)
        client = self.client_for(self.superuser)

        cases = (
            ({"action_type": second.action_type}, second),
            ({"organization": "civic research"}, second),
            ({"actor": "secondary"}, second),
            ({"created_after": (now - timedelta(hours=1)).isoformat()}, second),
            ({"created_before": (now - timedelta(days=1)).isoformat()}, first),
        )
        for params, expected in cases:
            with self.subTest(params=params):
                response = client.get(self.collection_url, params)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["count"], 1)
                self.assertEqual(response.data["results"][0]["id"], str(expected.pk))

        first_page = client.get(self.collection_url, {"limit": 1, "offset": 0})
        second_page = client.get(self.collection_url, {"limit": 1, "offset": 1})
        repeated_first_page = client.get(
            self.collection_url,
            {"limit": 1, "offset": 0},
        )
        self.assertEqual(first_page.data["results"], repeated_first_page.data["results"])
        self.assertNotEqual(
            first_page.data["results"][0]["id"],
            second_page.data["results"][0]["id"],
        )

    def test_rejects_inverted_dates_and_unsupported_parameters(self):
        client = self.client_for(self.superuser)
        now = timezone.now()
        inverted = client.get(
            self.collection_url,
            {
                "created_after": now.isoformat(),
                "created_before": (now - timedelta(days=1)).isoformat(),
            },
        )
        unsupported = client.get(self.collection_url, {"email": "private@example.com"})
        unsupported_detail = client.get(
            self.detail_url(self.make_event()),
            {"include_private": "true"},
        )

        self.assertEqual(inverted.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unsupported.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unsupported_detail.status_code, status.HTTP_400_BAD_REQUEST)

    def test_detail_uses_safe_projection_without_email_or_secrets(self):
        event = self.make_event(
            previous_state={
                "token": "old-token",
                "nested": {
                    "token_digest": "old-digest",
                    "status": "PENDING",
                },
            },
            new_state={
                "raw_token": "new-token",
                "invitation_email": "invitee@example.com",
                "status": "PENDING",
            },
            context={
                "authorization": "Bearer secret",
                "safe_note": "Contact private.person@example.com if needed",
                "nested": {"password": "secret", "count": 2},
            },
            notes="Requested by private.person@example.com",
        )

        response = self.client_for(self.superuser).get(self.detail_url(event))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = response.data
        serialized = json.dumps(payload).lower()
        self.assertNotIn(self.superuser.email, serialized)
        self.assertNotIn("invitee@example.com", serialized)
        self.assertNotIn("old-token", serialized)
        self.assertNotIn("old-digest", serialized)
        self.assertNotIn("new-token", serialized)
        self.assertNotIn("bearer secret", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("token_digest", serialized)
        self.assertNotIn("raw_token", serialized)
        self.assertIn("[redacted email]", serialized)
        self.assertEqual(payload["previous_state"]["nested"], {"status": "PENDING"})
        self.assertEqual(payload["context"]["nested"], {"count": 2})

    def test_platform_governance_is_not_an_organization_visible_domain(self):
        self.assertNotIn(AccountabilityDomain.PLATFORM_GOVERNANCE, ORGANIZATION_DOMAINS)

