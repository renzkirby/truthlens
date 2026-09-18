from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from api import accountability_service
from api.accountability_service import record_accountability_event
from api.models import AccountabilityEvent, Organization
from api.organization_service import PartnerCapability


class AccountabilityServiceTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="accountability-actor")
        self.authority_organization = Organization.objects.create(
            name="Accountability Authority",
            slug="accountability-authority",
        )
        self.subject_organization = Organization.objects.create(
            name="Accountability Subject",
            slug="accountability-subject",
        )

    def record(self, **overrides):
        values = {
            "action_type": AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
            "resource_type": AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
            "resource_id": 42,
            "authority_scope": AccountabilityEvent.AuthorityScope.SYSTEM,
        }
        values.update(overrides)
        return record_accountability_event(**values)

    def test_organization_requires_actor_organization_and_capability(self):
        base = {"authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION}
        for missing_values in (
            {},
            {"actor": self.actor},
            {
                "actor": self.actor,
                "authority_organization": self.authority_organization,
            },
        ):
            with self.subTest(missing_values=missing_values):
                with self.assertRaises(ValidationError):
                    self.record(**base, **missing_values)

        event = self.record(
            **base,
            actor=self.actor,
            authority_organization=self.authority_organization,
            capability=PartnerCapability.PUBLISH_FACT_CHECK,
        )
        self.assertEqual(event.subject_organization, self.authority_organization)

    def test_organization_allows_historical_snapshot_only_for_verdict_revision(self):
        snapshot = {"id": str(self.actor.pk), "username": self.actor.username}

        event = self.record(
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
            resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
            actor_snapshot=snapshot,
            authority_organization=self.authority_organization,
            capability=PartnerCapability.ADJUDICATE,
        )

        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_username_snapshot, snapshot["username"])
        self.assertEqual(event.context["actor_snapshot"], snapshot)

        for overrides in (
            {"action_type": AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED},
            {"resource_type": AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK},
            {"capability": PartnerCapability.PUBLISH_FACT_CHECK},
        ):
            values = {
                "action_type": AccountabilityEvent.ActionType.VERDICT_REVISED,
                "resource_type": AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
                "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
                "actor_snapshot": snapshot,
                "authority_organization": self.authority_organization,
                "capability": PartnerCapability.ADJUDICATE,
            }
            values.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.record(**values)

    def test_actor_snapshot_must_be_valid_and_identify_live_actor(self):
        for snapshot in (
            {},
            {"id": str(self.actor.pk)},
            {"id": "", "username": self.actor.username},
            {"id": str(self.actor.pk), "username": ""},
            {"id": str(self.actor.pk), "username": self.actor.username, "extra": "x"},
        ):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValidationError):
                self.record(
                    action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
                    resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
                    authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
                    actor_snapshot=snapshot,
                    authority_organization=self.authority_organization,
                    capability=PartnerCapability.ADJUDICATE,
                )

        with self.assertRaises(ValidationError):
            self.record(
                action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
                resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
                authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
                actor=self.actor,
                actor_snapshot={"id": "different", "username": self.actor.username},
                authority_organization=self.authority_organization,
                capability=PartnerCapability.ADJUDICATE,
            )

        historical_username = "accountability-actor-before-rename"
        event = self.record(
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
            resource_type=AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
            actor=self.actor,
            actor_snapshot={
                "id": str(self.actor.pk),
                "username": historical_username,
            },
            authority_organization=self.authority_organization,
            capability=PartnerCapability.ADJUDICATE,
        )
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.actor_username_snapshot, historical_username)

    def test_nonorganization_scopes_reject_actor_snapshot_fallback(self):
        snapshot = {"id": str(self.actor.pk), "username": self.actor.username}
        for scope, values in (
            (
                AccountabilityEvent.AuthorityScope.PLATFORM,
                {"capability": PartnerCapability.REVIEW_SAFETY},
            ),
            (AccountabilityEvent.AuthorityScope.PERSONAL, {}),
            (AccountabilityEvent.AuthorityScope.SYSTEM, {}),
        ):
            with self.subTest(scope=scope), self.assertRaises(ValidationError):
                self.record(
                    authority_scope=scope,
                    actor_snapshot=snapshot,
                    **values,
                )

    def test_platform_requires_actor_and_capability_without_authority_org(self):
        with self.assertRaises(ValidationError):
            self.record(authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM)
        with self.assertRaises(ValidationError):
            self.record(
                authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
                actor=self.actor,
                capability=PartnerCapability.REVIEW_SAFETY,
                authority_organization=self.authority_organization,
            )
        event = self.record(
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=self.actor,
            capability=PartnerCapability.REVIEW_SAFETY,
        )
        self.assertIsNone(event.authority_organization)

    def test_personal_requires_actor_and_forbids_capability_and_authority_org(self):
        with self.assertRaises(ValidationError):
            self.record(authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL)
        for forbidden in (
            {"capability": PartnerCapability.ADJUDICATE},
            {"authority_organization": self.authority_organization},
        ):
            with self.assertRaises(ValidationError):
                self.record(
                    authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL,
                    actor=self.actor,
                    **forbidden,
                )

    def test_system_forbids_actor_capability_and_authority_org(self):
        for forbidden in (
            {"actor": self.actor},
            {"capability": PartnerCapability.ADJUDICATE},
            {"authority_organization": self.authority_organization},
        ):
            with self.assertRaises(ValidationError):
                self.record(**forbidden)

    def test_subject_organization_is_independent_and_snapshots_are_durable(self):
        event = self.record(
            authority_scope=AccountabilityEvent.AuthorityScope.PERSONAL,
            actor=self.actor,
            subject_organization=self.subject_organization,
        )
        self.assertIsNone(event.authority_organization)
        self.assertEqual(event.subject_organization, self.subject_organization)
        self.assertEqual(event.actor_username_snapshot, self.actor.username)
        self.assertEqual(
            event.subject_organization_name_snapshot,
            self.subject_organization.name,
        )

    def test_organization_snapshots_json_defaults_and_resource_normalization(self):
        event = self.record(
            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
            actor=self.actor,
            authority_organization=self.authority_organization,
            subject_organization=self.subject_organization,
            capability=PartnerCapability.ADJUDICATE,
        )
        self.assertEqual(event.resource_id, "42")
        self.assertEqual(event.previous_state, {})
        self.assertEqual(event.new_state, {})
        self.assertEqual(event.context, {})
        self.assertEqual(
            event.authority_organization_name_snapshot,
            self.authority_organization.name,
        )

    def test_sensitive_keys_binary_data_and_non_object_json_are_rejected(self):
        for field, value in (
            ("context", {"raw_token": "secret"}),
            ("previous_state", {"payload": b"bytes"}),
            ("new_state", ["not", "an", "object"]),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    self.record(**{field: value})

    def test_model_is_append_only_and_no_mutation_service_exists(self):
        event = self.record()
        event.notes = "changed"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        self.assertFalse(hasattr(accountability_service, "update_accountability_event"))
        self.assertFalse(hasattr(accountability_service, "delete_accountability_event"))
