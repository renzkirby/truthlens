from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.accountability_query_service import (
    AccountabilityDomain,
    AccountabilityQueryAuthorizationError,
    AccountabilityQueryInputError,
    DOMAIN_ACTIONS,
    ORGANIZATION_DOMAINS,
    _actor_payload,
    list_organization_accountability_events,
    list_platform_accountability_events,
)
from api.models import AccountabilityEvent, Organization, OrganizationMembership, UserProfile
from api.organization_service import PartnerCapability


class AccountabilityQueryServiceTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="Accountability Partner",
            slug="accountability-query-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.other_organization = Organization.objects.create(
            name="Other Accountability Partner",
            slug="other-accountability-query-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.owner = User.objects.create_user(
            username="accountability-owner", email="owner-private@example.com"
        )
        self.lead = User.objects.create_user(username="accountability-lead")
        self.safety_moderator = User.objects.create_user(username="safety-moderator")
        self.event_actor = User.objects.create_user(
            username="historical-actor", email="actor-private@example.com"
        )
        self.owner.profile.trust_score = 99
        self.owner.profile.save(update_fields=["trust_score"])
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])
        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.lead_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def make_event(
        self,
        *,
        action_type,
        organization=None,
        authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
        actor=None,
        resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
        resource_id="resource-1",
        context=None,
        previous_state=None,
        new_state=None,
        notes="",
        capability=PartnerCapability.PUBLISH_FACT_CHECK,
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
            previous_state=previous_state or {},
            new_state=new_state or {},
            notes=notes,
            context=context or {},
        )

    def test_each_current_capability_exposes_only_its_mapped_domains(self):
        for domain, actions in DOMAIN_ACTIONS.items():
            self.make_event(
                action_type=actions[0],
                authority_scope=(
                    AccountabilityEvent.AuthorityScope.PLATFORM
                    if domain == AccountabilityDomain.SAFETY
                    else AccountabilityEvent.AuthorityScope.ORGANIZATION
                ),
            )

        expectations = {
            PartnerCapability.CLAIM_VERIFICATION_WORK: {AccountabilityDomain.VERIFICATION},
            PartnerCapability.REVIEW_EVIDENCE: {
                AccountabilityDomain.EVIDENCE,
                AccountabilityDomain.FACTUAL_CORRECTION,
            },
            PartnerCapability.ADJUDICATE: {
                AccountabilityDomain.ADJUDICATION,
                AccountabilityDomain.FACTUAL_CORRECTION,
            },
            PartnerCapability.CREATE_FACT_CHECK_DRAFT: {
                AccountabilityDomain.PUBLICATION,
                AccountabilityDomain.FACTUAL_CORRECTION,
            },
            PartnerCapability.PUBLISH_FACT_CHECK: {
                AccountabilityDomain.PUBLICATION,
                AccountabilityDomain.FACTUAL_CORRECTION,
            },
            PartnerCapability.MANAGE_ORGANIZATION: set(ORGANIZATION_DOMAINS),
        }

        for capability, expected_domains in expectations.items():
            with self.subTest(capability=capability), patch(
                "api.accountability_query_service.has_capability",
                side_effect=lambda actor, requested, organization=None: requested
                == capability,
            ):
                page = list_organization_accountability_events(
                    actor=self.owner, organization=self.organization
                )
                self.assertEqual(
                    {result["domain"] for result in page["results"]},
                    expected_domains,
                )
                self.assertEqual(
                    {option["value"] for option in page["filter_options"]["domains"]},
                    expected_domains,
                )
                self.assertTrue(
                    all(
                        option["domain"] in expected_domains
                        for option in page["filter_options"]["actions"]
                    )
                )

    def test_review_safety_alone_grants_no_organization_visibility(self):
        with patch(
            "api.accountability_query_service.has_capability",
            side_effect=lambda actor, capability, organization=None: capability
            == PartnerCapability.REVIEW_SAFETY,
        ), self.assertRaises(AccountabilityQueryAuthorizationError):
            list_organization_accountability_events(
                actor=self.safety_moderator,
                organization=self.organization,
            )

    def test_organization_scope_uses_subject_and_includes_personal_and_system(self):
        personal = self.make_event(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_ACCEPTED,
            authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL,
            actor=self.event_actor,
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION,
        )
        system = self.make_event(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_COMPLETED,
            authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
            resource_type=AccountabilityEvent.ResourceType.VERIFICATION_ASSIGNMENT,
        )
        other = self.make_event(
            action_type=AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
            organization=self.other_organization,
        )
        safety = self.make_event(
            action_type=AccountabilityEvent.ActionType.SAFETY_CASE_ESCALATED,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=self.safety_moderator,
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            capability=PartnerCapability.REVIEW_SAFETY,
        )

        page = list_organization_accountability_events(
            actor=self.owner, organization=self.organization
        )
        ids = {result["id"] for result in page["results"]}
        self.assertIn(str(personal.id), ids)
        self.assertIn(str(system.id), ids)
        self.assertNotIn(str(other.id), ids)
        self.assertNotIn(str(safety.id), ids)

    def test_suspended_or_removed_membership_loses_current_access(self):
        for status in (
            OrganizationMembership.Status.SUSPENDED,
            OrganizationMembership.Status.LEFT,
        ):
            with self.subTest(status=status):
                self.owner_membership.status = status
                self.owner_membership.save(update_fields=["status"])
                with self.assertRaises(AccountabilityQueryAuthorizationError):
                    list_organization_accountability_events(
                        actor=self.owner,
                        organization=self.organization,
                    )
                self.owner_membership.status = OrganizationMembership.Status.ACTIVE
                self.owner_membership.save(update_fields=["status"])

    def test_filters_pagination_count_and_deterministic_order(self):
        base = timezone.now() - timedelta(hours=2)
        events = []
        for index in range(4):
            event = self.make_event(
                action_type=AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
                actor=self.event_actor,
                resource_id=f"publication-{index}",
            )
            AccountabilityEvent.objects.filter(pk=event.pk).update(
                created_at=base + timedelta(minutes=index)
            )
            events.append(event)

        filtered = list_organization_accountability_events(
            actor=self.lead,
            organization=self.organization,
            domain=AccountabilityDomain.PUBLICATION,
            action_type=AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
            resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
            resource_id="publication-2",
            actor_search="HISTORICAL",
            created_after=base + timedelta(minutes=1),
            created_before=base + timedelta(minutes=3),
        )
        self.assertEqual(filtered["count"], 1)
        self.assertEqual(filtered["results"][0]["id"], str(events[2].id))

        page = list_organization_accountability_events(
            actor=self.lead,
            organization=self.organization,
            domain=AccountabilityDomain.PUBLICATION,
            limit=2,
            offset=1,
        )
        self.assertEqual(page["count"], 4)
        self.assertEqual(page["limit"], 2)
        self.assertEqual(page["offset"], 1)
        self.assertEqual(
            [result["id"] for result in page["results"]],
            [str(events[2].id), str(events[1].id)],
        )

    def test_invalid_direct_query_inputs_are_rejected(self):
        invalid_values = (
            {"domain": "UNKNOWN"},
            {"action_type": "UNKNOWN"},
            {"resource_type": "UNKNOWN"},
            {"limit": 0},
            {"limit": 101},
            {"offset": -1},
            {
                "created_after": timezone.now(),
                "created_before": timezone.now() - timedelta(days=1),
            },
        )
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(
                AccountabilityQueryInputError
            ):
                list_organization_accountability_events(
                    actor=self.owner,
                    organization=self.organization,
                    **values,
                )

    def test_historical_actor_snapshots_and_private_data_are_projected_safely(self):
        event = self.make_event(
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
            actor=self.event_actor,
            resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            context={
                "safe": {
                    "value": "kept",
                    "token": "remove",
                    "token_digest": "remove",
                    "digest": "remove",
                    "password": "remove",
                    "secret": "remove",
                    "authorization": "remove",
                    "cookie": "remove",
                    "api_key": "remove",
                    "access_key": "remove",
                    "private_key": "remove",
                },
                "actor_snapshot": {
                    "id": str(self.event_actor.pk),
                    "username": "historical-actor",
                },
                "contact_email": "private@example.com",
                "source_payload": {"body": "private source"},
                "article_body": "private article",
                "evidence_body": "private evidence",
                "ai_analysis": "private analysis",
                "file_body": "private file",
                "upload_payload": "private upload",
            },
            previous_state={"password": "remove", "status": "OLD"},
            new_state={"nested": [{"private_key": "remove", "status": "NEW"}]},
            capability=PartnerCapability.ADJUDICATE,
        )
        historical_username = event.actor_username_snapshot
        self.event_actor.username = "current-renamed-actor"
        self.event_actor.save(update_fields=["username"])

        live_result = list_organization_accountability_events(
            actor=self.owner,
            organization=self.organization,
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
        )["results"][0]
        self.assertEqual(live_result["actor"]["id"], str(self.event_actor.pk))
        self.assertEqual(live_result["actor"]["username"], historical_username)
        self.assertFalse(live_result["actor"]["historical"])
        self.assertNotIn("actor_snapshot", live_result["context"])
        self.assertEqual(live_result["context"], {"safe": {"value": "kept"}})
        self.assertEqual(live_result["previous_state"], {"status": "OLD"})
        self.assertEqual(live_result["new_state"], {"nested": [{"status": "NEW"}]})
        self.assertNotIn("email", live_result["actor"])
        self.assertNotIn("trust_score", live_result["actor"])
        self.assertNotIn("role", live_result["actor"])

        actor_id = self.event_actor.pk
        self.event_actor.delete()
        deleted_result = list_organization_accountability_events(
            actor=self.owner,
            organization=self.organization,
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
        )["results"][0]
        self.assertEqual(deleted_result["actor"]["id"], str(actor_id))
        self.assertEqual(deleted_result["actor"]["username"], historical_username)
        self.assertTrue(deleted_result["actor"]["historical"])

    def test_malformed_historical_snapshot_ids_never_project_as_actor_ids(self):
        event = AccountabilityEvent(actor=None, actor_username_snapshot="durable-actor")
        malformed_ids = (
            {"nested": "id"},
            ["id"],
            ("id",),
            {"id"},
            b"id",
            True,
            "",
            "   ",
        )

        for malformed_id in malformed_ids:
            with self.subTest(malformed_id=malformed_id):
                context = {
                    "actor_snapshot": {
                        "id": malformed_id,
                        "username": "durable-actor",
                    }
                }
                actor = _actor_payload(event, context)
                self.assertIsNone(actor["id"])
                self.assertEqual(actor["username"], "durable-actor")
                self.assertTrue(actor["historical"])
                self.assertNotIn("actor_snapshot", context)

    def test_deleted_correction_approver_is_not_replaced_by_publisher(self):
        approver = User.objects.create_user(username="deleted-approver")
        publisher = User.objects.create_user(username="different-publisher")
        approver_id = approver.pk
        approver_username = approver.username
        event = self.make_event(
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
            resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            context={
                "actor_snapshot": {
                    "id": str(approver_id),
                    "username": approver_username,
                },
                "publisher_id": str(publisher.pk),
            },
            capability=PartnerCapability.ADJUDICATE,
        )
        AccountabilityEvent.objects.filter(pk=event.pk).update(
            actor=None,
            actor_username_snapshot=approver_username,
        )
        approver.delete()

        result = list_organization_accountability_events(
            actor=self.owner,
            organization=self.organization,
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
        )["results"][0]
        self.assertEqual(result["actor"]["id"], str(approver_id))
        self.assertEqual(result["actor"]["username"], approver_username)
        self.assertNotEqual(result["actor"]["id"], str(publisher.pk))

    def test_platform_feed_requires_safety_authority_and_is_platform_safety_only(self):
        safety = self.make_event(
            action_type=AccountabilityEvent.ActionType.SAFETY_CONTENT_REMOVED,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=self.safety_moderator,
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            capability=PartnerCapability.REVIEW_SAFETY,
        )
        organization_event = self.make_event(
            action_type=AccountabilityEvent.ActionType.ARTICLE_PUBLISHED,
            actor=self.safety_moderator,
        )

        with self.assertRaises(AccountabilityQueryAuthorizationError):
            list_platform_accountability_events(actor=self.lead)

        page = list_platform_accountability_events(
            actor=self.safety_moderator,
            action_type=AccountabilityEvent.ActionType.SAFETY_CONTENT_REMOVED,
            actor_search="SAFETY",
            limit=1,
            offset=0,
        )
        self.assertEqual(page["scope"], "PLATFORM")
        self.assertIsNone(page["organization"])
        self.assertEqual([item["id"] for item in page["results"]], [str(safety.id)])
        self.assertNotIn(str(organization_event.id), [item["id"] for item in page["results"]])
        self.assertEqual(
            page["filter_options"]["domains"],
            [{"value": AccountabilityDomain.SAFETY, "label": "Safety"}],
        )
        self.assertTrue(
            all(
                item["domain"] == AccountabilityDomain.SAFETY
                for item in page["filter_options"]["actions"]
            )
        )
