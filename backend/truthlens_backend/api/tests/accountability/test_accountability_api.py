from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import AccountabilityEvent, Organization, OrganizationMembership, UserProfile
from api.organization_service import PartnerCapability


class AccountabilityApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="API Accountability Partner",
            slug="api-accountability-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other API Accountability Partner",
            slug="other-api-accountability-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.owner = User.objects.create_user(username="api-accountability-owner")
        self.lead = User.objects.create_user(username="api-accountability-lead")
        self.contributor = User.objects.create_user(username="api-accountability-contributor")
        self.outsider = User.objects.create_user(username="api-accountability-outsider")
        self.safety_moderator = User.objects.create_user(username="api-safety-moderator")
        self.dual_role = User.objects.create_user(username="api-dual-role")
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])
        self.dual_role.profile.role = UserProfile.Role.MOD
        self.dual_role.profile.save(update_fields=["role"])

        for user, role in (
            (self.owner, OrganizationMembership.Role.OWNER),
            (self.lead, OrganizationMembership.Role.LEAD_VERIFIER),
            (self.contributor, OrganizationMembership.Role.CONTRIBUTOR),
            (self.dual_role, OrganizationMembership.Role.LEAD_VERIFIER),
        ):
            OrganizationMembership.objects.create(
                organization=self.organization,
                user=user,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )

        self.organization_url = reverse("organization_accountability")
        self.platform_url = reverse("platform_safety_accountability")

    def authenticated_client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_event(
        self,
        *,
        action_type=AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
        organization=None,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=None,
        capability=PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
        resource_id="fact-check-1",
        context=None,
    ):
        organization = self.organization if organization is None else organization
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
            subject_organization_name_snapshot=organization.name if organization else "",
            capability=(
                capability
                if authority_scope
                in {
                    AccountabilityEvent.AuthorityScope.ORGANIZATION,
                    AccountabilityEvent.AuthorityScope.PLATFORM,
                }
                else ""
            ),
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            context=context or {},
        )

    def organization_params(self, **overrides):
        params = {"organization_id": str(self.organization.id)}
        params.update(overrides)
        return params

    def test_organization_endpoint_authentication_and_current_authorization(self):
        self.assertEqual(
            APIClient().get(self.organization_url, self.organization_params()).status_code,
            401,
        )
        for user in (self.outsider, self.contributor, self.safety_moderator):
            with self.subTest(user=user.username):
                response = self.authenticated_client(user).get(
                    self.organization_url,
                    self.organization_params(),
                )
                self.assertEqual(response.status_code, 403)

        membership = OrganizationMembership.objects.get(
            organization=self.organization, user=self.lead
        )
        membership.status = OrganizationMembership.Status.SUSPENDED
        membership.save(update_fields=["status"])
        self.assertEqual(
            self.authenticated_client(self.lead).get(
                self.organization_url, self.organization_params()
            ).status_code,
            403,
        )
        membership.status = OrganizationMembership.Status.LEFT
        membership.save(update_fields=["status"])
        self.assertEqual(
            self.authenticated_client(self.lead).get(
                self.organization_url, self.organization_params()
            ).status_code,
            403,
        )

    def test_unknown_organization_and_invalid_queries_return_client_errors(self):
        client = self.authenticated_client(self.owner)
        self.assertEqual(
            client.get(
                self.organization_url,
                {"organization_id": "00000000-0000-0000-0000-000000000001"},
            ).status_code,
            404,
        )
        invalid_queries = (
            self.organization_params(domain="UNKNOWN"),
            self.organization_params(action_type="UNKNOWN"),
            self.organization_params(resource_type="UNKNOWN"),
            self.organization_params(limit=101),
            self.organization_params(offset=-1),
            self.organization_params(extra="unexpected"),
            self.organization_params(
                created_after="2026-09-15T12:00:00Z",
                created_before="2026-09-14T12:00:00Z",
            ),
        )
        for params in invalid_queries:
            with self.subTest(params=params):
                self.assertEqual(
                    client.get(self.organization_url, params).status_code,
                    400,
                )

    def test_organization_api_filters_pages_and_never_crosses_scope(self):
        now = timezone.now() - timedelta(hours=1)
        events = []
        for index in range(3):
            event = self.make_event(
                actor=self.lead,
                resource_id=f"fact-check-{index}",
            )
            AccountabilityEvent.objects.filter(pk=event.pk).update(
                created_at=now + timedelta(minutes=index)
            )
            events.append(event)
        self.make_event(
            organization=self.other_organization,
            actor=self.lead,
            resource_id="other-tenant",
        )
        personal = self.make_event(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_ACCEPTED,
            authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL,
            actor=self.lead,
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
            resource_id="invitation-1",
        )
        system = self.make_event(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_COMPLETED,
            authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
            actor=None,
            resource_type=AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
            resource_id="assignment-1",
        )
        platform = self.make_event(
            action_type=AccountabilityEvent.ActionType.SAFETY_CASE_ESCALATED,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=self.dual_role,
            capability=PartnerCapability.REVIEW_SAFETY,
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            resource_id="safety-1",
        )

        response = self.authenticated_client(self.dual_role).get(
            self.organization_url,
            self.organization_params(
                domain="PUBLICATION",
                action_type=AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
                resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
                resource_id="fact-check-1",
                actor="ACCOUNTABILITY-LEAD",
                created_after=(now + timedelta(seconds=1)).isoformat(),
                created_before=(now + timedelta(minutes=2, seconds=1)).isoformat(),
                limit=1,
                offset=0,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(events[1].id))

        unfiltered = self.authenticated_client(self.owner).get(
            self.organization_url,
            self.organization_params(limit=2, offset=0),
        )
        returned_ids = {item["id"] for item in unfiltered.data["results"]}
        self.assertEqual(unfiltered.data["limit"], 2)
        self.assertEqual(unfiltered.data["offset"], 0)
        self.assertGreaterEqual(unfiltered.data["count"], 5)
        all_response = self.authenticated_client(self.owner).get(
            self.organization_url,
            self.organization_params(limit=100),
        )
        all_ids = [item["id"] for item in all_response.data["results"]]
        self.assertIn(str(personal.id), all_ids)
        self.assertIn(str(system.id), all_ids)
        self.assertNotIn(str(platform.id), all_ids)
        self.assertNotIn("other-tenant", [item["resource"]["id"] for item in all_response.data["results"]])
        self.assertTrue(returned_ids.issubset(set(all_ids)))

    def test_api_dto_uses_labels_snapshots_and_redacted_context(self):
        actor = User.objects.create_user(
            username="api-original-actor", email="actor-secret@example.com"
        )
        event = self.make_event(
            actor=actor,
            action_type=AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
            capability=PartnerCapability.PUBLISH_FACT_CHECK,
            context={
                "visible": "yes",
                "nested": {"token": "no", "password": "no"},
                "ai_analysis": "not public",
            },
        )
        actor.username = "api-current-actor"
        actor.save(update_fields=["username"])

        response = self.authenticated_client(self.owner).get(
            self.organization_url,
            self.organization_params(
                action_type=AccountabilityEvent.ActionType.ARTICLE_PUBLISHED
            ),
        )
        self.assertEqual(response.status_code, 200)
        result = response.data["results"][0]
        self.assertEqual(result["id"], str(event.id))
        self.assertEqual(result["action_label"], "Article Published")
        self.assertEqual(result["domain_label"], "Publication")
        self.assertEqual(result["resource"]["label"], "Official Fact Check")
        self.assertEqual(result["actor"]["id"], str(actor.pk))
        self.assertEqual(result["actor"]["username"], "api-original-actor")
        self.assertEqual(result["context"], {"visible": "yes", "nested": {}})
        self.assertNotIn("email", result["actor"])
        self.assertNotIn("trust_score", result["actor"])
        self.assertNotIn("role", result["actor"])

    def test_platform_endpoint_is_safety_capability_and_scope_only(self):
        safety_events = []
        for index, action in enumerate(
            (
                AccountabilityEvent.ActionType.SAFETY_CASE_CLAIMED,
                AccountabilityEvent.ActionType.SAFETY_CASE_RELEASED,
            )
        ):
            safety_events.append(
                self.make_event(
                    action_type=action,
                    authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
                    actor=self.safety_moderator,
                    capability=PartnerCapability.REVIEW_SAFETY,
                    resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
                    resource_id=f"safety-{index}",
                )
            )
        organization_event = self.make_event(actor=self.dual_role)

        self.assertEqual(
            self.authenticated_client(self.lead).get(self.platform_url).status_code,
            403,
        )
        response = self.authenticated_client(self.dual_role).get(
            self.platform_url,
            {
                "domain": "SAFETY",
                "resource_type": AccountabilityEvent.ResourceType.MODERATION_CASE,
                "actor": "safety",
                "limit": 1,
                "offset": 0,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scope"], "PLATFORM")
        self.assertIsNone(response.data["organization"])
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertTrue(
            all(item["authority"]["scope"] == "PLATFORM" for item in response.data["results"])
        )
        self.assertTrue(all(item["domain"] == "SAFETY" for item in response.data["results"]))
        self.assertNotIn(
            str(organization_event.id),
            [item["id"] for item in response.data["results"]],
        )
        self.assertEqual(
            {item["domain"] for item in response.data["filter_options"]["actions"]},
            {"SAFETY"},
        )
        self.assertEqual(
            response.data["filter_options"]["resources"],
            [{"value": "MODERATION_CASE", "label": "Moderation Case"}],
        )
