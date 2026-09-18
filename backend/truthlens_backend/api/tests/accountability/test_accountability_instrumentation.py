import json
import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from api.accountability_service import record_accountability_event
from api.adjudication_service import issue_adjudication_decision
from api.evidence_review_service import review_evidence_submission
from api.factual_correction_service import cancel_factual_correction
from api.models import (
    AccountabilityEvent,
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    OfficialFactCheck,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    Thread,
    UserProfile,
    VerificationAssignment,
)
from api.organization_invitation_service import (
    OrganizationInvitationConflict,
    accept_organization_invitation,
    cancel_organization_invitation,
    create_organization_invitation,
    expire_stale_invitations,
)
from api.organization_membership_service import (
    OrganizationMembershipConflict,
    change_organization_membership_role,
    remove_organization_membership,
    restore_organization_membership,
    suspend_organization_membership,
)
from api.organization_public_profile_service import (
    update_organization_public_profile,
)
from api.organization_service import PartnerCapability
from api.publishing_service import (
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
    update_fact_check_draft,
)
from api.safety_review_service import (
    claim_safety_case,
    perform_safety_case_action,
    release_safety_case,
)
from api.tests.workspace.test_factual_correction_handoff import (
    FactualCorrectionHandoffFixtures,
)
from api.verification_assignment_service import (
    VerificationAssignmentAuthorizationError,
    VerificationAssignmentConflict,
    claim_verification_assignment,
    ensure_verification_assignment,
    release_verification_assignment,
)


class AccountabilityInstrumentationTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="accountability-dual-role")
        self.contributor = User.objects.create_user(
            username="accountability-contributor"
        )
        self.outsider = User.objects.create_user(username="accountability-outsider")
        self.manager = User.objects.create_user(username="accountability-manager")
        self.actor.profile.role = UserProfile.Role.MOD
        self.actor.profile.save(update_fields=["role"])
        self.organization = Organization.objects.create(
            name="Accountability Partner",
            slug="accountability-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.actor,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.manager,
            role=OrganizationMembership.Role.OWNER,
            status=OrganizationMembership.Status.ACTIVE,
        )

    def test_assignment_evidence_adjudication_and_publication_are_attributed(self):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Accountability workflow claim",
            ai_verdict="FAKE",
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.contributor,
            caption="Accountability workflow thread",
        )
        assignment = ensure_verification_assignment(claim=claim)
        assignment = claim_verification_assignment(
            assignment=assignment,
            organization=self.organization,
            actor=self.actor,
        )
        claimed_count = AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED,
            resource_id=str(assignment.pk),
        ).count()
        claim_verification_assignment(
            assignment=assignment,
            organization=self.organization,
            actor=self.actor,
        )
        self.assertEqual(
            AccountabilityEvent.objects.filter(
                action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED,
                resource_id=str(assignment.pk),
            ).count(),
            claimed_count,
        )

        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption="Public evidence caption",
            evidence_url="https://example.com/accountability-evidence",
        )
        evidence_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )
        review = review_evidence_submission(
            evidence=evidence,
            actor=self.actor,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            expected_status=EvidenceSubmission.EvidenceStatus.UNVERIFIED,
            expected_case_id=evidence_case.pk,
            expected_organization_id=self.organization.pk,
            allow_reopen=False,
        )
        decision_result = issue_adjudication_decision(
            case_id=review["adjudication_case"].pk,
            organization_id=self.organization.pk,
            actor=self.actor,
            verdict=AdjudicationDecision.Verdict.FAKE,
            canonical_claim="The reviewed claim is false.",
            rationale="The reviewed evidence contradicts the claim.",
            expected_revision=0,
        )
        decision = decision_result["decision"]
        draft = create_fact_check_draft(
            decision=decision,
            actor=self.actor,
            organization_id=self.organization.pk,
            expected_decision_revision=decision.revision_number,
            headline="Accountability fact-check",
            summary="The evidence contradicts the claim.",
            article_body="A concise public analysis.",
            source_urls=["https://example.com/accountability-evidence"],
        )
        draft = update_fact_check_draft(
            fact_check=draft,
            actor=self.actor,
            organization_id=self.organization.pk,
            expected_edit_generation=draft.edit_generation,
            expected_decision_revision=decision.revision_number,
            summary="The reviewed evidence directly contradicts the claim.",
        )
        submitted = submit_fact_check_for_review(
            fact_check=draft,
            actor=self.actor,
            organization_id=self.organization.pk,
            expected_edit_generation=draft.edit_generation,
            expected_decision_revision=decision.revision_number,
        )
        result = publish_fact_check(
            fact_check=submitted,
            actor=self.actor,
            organization_id=self.organization.pk,
            expected_edit_generation=submitted.edit_generation,
            expected_decision_revision=decision.revision_number,
        )

        organization_events = AccountabilityEvent.objects.filter(
            actor=self.actor,
            authority_scope=AccountabilityEvent.AuthorityScope.ORGANIZATION,
            authority_organization=self.organization,
        )
        expected_capabilities = {
            AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED: (
                PartnerCapability.CLAIM_VERIFICATION_WORK
            ),
            AccountabilityEvent.ActionType.EVIDENCE_VERIFIED: (
                PartnerCapability.REVIEW_EVIDENCE
            ),
            AccountabilityEvent.ActionType.ADJUDICATION_STARTED: (
                PartnerCapability.ADJUDICATE
            ),
            AccountabilityEvent.ActionType.VERDICT_ISSUED: (
                PartnerCapability.ADJUDICATE
            ),
            AccountabilityEvent.ActionType.ARTICLE_DRAFT_CREATED: (
                PartnerCapability.CREATE_FACT_CHECK_DRAFT
            ),
            AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED: (
                PartnerCapability.CREATE_FACT_CHECK_DRAFT
            ),
            AccountabilityEvent.ActionType.ARTICLE_SUBMITTED: (
                PartnerCapability.CREATE_FACT_CHECK_DRAFT
            ),
            AccountabilityEvent.ActionType.ARTICLE_PUBLISHED: (
                PartnerCapability.PUBLISH_FACT_CHECK
            ),
        }
        for action_type, capability in expected_capabilities.items():
            with self.subTest(action_type=action_type):
                events = organization_events.filter(
                    action_type=action_type,
                    capability=capability,
                )
                self.assertTrue(events.exists())
                for event in events:
                    self.assertEqual(event.actor_id_snapshot, str(self.actor.pk))
                    self.assertEqual(event.actor_username_snapshot, self.actor.username)
                    self.assertNotIn("actor_snapshot", event.context)

        completed = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_COMPLETED,
            resource_id=str(assignment.pk),
        )
        self.assertEqual(completed.authority_scope, AccountabilityEvent.AuthorityScope.SYSTEM)
        self.assertIsNone(completed.actor)
        self.assertEqual(completed.actor_id_snapshot, "")
        self.assertEqual(completed.context["claim_id"], str(claim.pk))

    def test_evidence_decisions_and_reopen_are_correlated_to_claim(self):
        claim = Claim.objects.create(context_text="Evidence correlation claim")
        thread = Thread.objects.create(
            claim=claim,
            author=self.contributor,
            caption="Evidence correlation thread",
        )
        assignment = ensure_verification_assignment(claim=claim)
        claim_verification_assignment(
            assignment=assignment,
            organization=self.organization,
            actor=self.actor,
        )
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption="Evidence correlation source",
            evidence_url="https://example.com/evidence-correlation",
        )
        for status, action, reason in (
            (
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
                None,
            ),
            (
                EvidenceSubmission.EvidenceStatus.REJECTED,
                AccountabilityEvent.ActionType.EVIDENCE_REJECTED,
                EvidenceSubmission.RejectionReason.OUTDATED,
            ),
        ):
            with self.subTest(status=status):
                result = review_evidence_submission(
                    evidence=evidence,
                    actor=self.actor,
                    evidence_status=status,
                    rejection_reason=reason,
                )
                event = AccountabilityEvent.objects.get(
                    action_type=action,
                    resource_id=str(evidence.pk),
                )
                self.assertEqual(event.actor_id_snapshot, str(self.actor.pk))
                self.assertEqual(event.actor_username_snapshot, self.actor.username)
                self.assertEqual(
                    event.context,
                    {
                        "evidence_case_id": str(result["case"].pk),
                        "claim_id": str(claim.pk),
                    },
                )

        reopened = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.EVIDENCE_REOPENED,
            resource_id=str(evidence.pk),
        )
        self.assertEqual(
            reopened.context,
            {
                "moderation_case_id": str(result["case"].pk),
                "claim_id": str(claim.pk),
            },
        )

    def test_release_conflict_unauthorized_action_and_rollback_leave_no_extra_event(self):
        claim = Claim.objects.create(context_text="Assignment release audit")
        assignment = ensure_verification_assignment(claim=claim)
        with self.assertRaises(VerificationAssignmentAuthorizationError):
            claim_verification_assignment(
                assignment=assignment,
                organization=self.organization,
                actor=self.outsider,
            )
        self.assertFalse(
            AccountabilityEvent.objects.filter(
                action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_CLAIMED,
                resource_id=str(assignment.pk),
            ).exists()
        )

        assignment = claim_verification_assignment(
            assignment=assignment,
            organization=self.organization,
            actor=self.actor,
        )
        released = release_verification_assignment(
            assignment=assignment,
            actor=self.actor,
        )["released_assignment"]
        release_count = AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_RELEASED,
            resource_id=str(released.pk),
        ).count()
        with self.assertRaises(VerificationAssignmentConflict):
            release_verification_assignment(assignment=released, actor=self.actor)
        self.assertEqual(
            AccountabilityEvent.objects.filter(
                action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_RELEASED,
                resource_id=str(released.pk),
            ).count(),
            release_count,
        )

        before = AccountabilityEvent.objects.count()
        try:
            with transaction.atomic():
                record_accountability_event(
                    action_type=AccountabilityEvent.ActionType.ARTICLE_DRAFT_SAVED,
                    resource_type=AccountabilityEvent.ResourceType.OFFICIAL_FACT_CHECK,
                    resource_id="rolled-back",
                    authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        self.assertEqual(AccountabilityEvent.objects.count(), before)

    def test_membership_invitation_profile_and_expiry_instrumentation(self):
        target = User.objects.create_user(username="accountability-member")
        target_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=target,
            role=OrganizationMembership.Role.CONTRIBUTOR,
            status=OrganizationMembership.Status.ACTIVE,
        )
        target_membership = change_organization_membership_role(
            organization=self.organization,
            membership_id=target_membership.pk,
            role=OrganizationMembership.Role.RESEARCHER,
            actor=self.manager,
        )
        suspend_organization_membership(
            organization=self.organization,
            membership_id=target_membership.pk,
            actor=self.manager,
        )
        restore_organization_membership(
            organization=self.organization,
            membership_id=target_membership.pk,
            actor=self.manager,
        )
        remove_organization_membership(
            organization=self.organization,
            membership_id=target_membership.pk,
            actor=self.manager,
        )
        with self.assertRaises(OrganizationMembershipConflict):
            remove_organization_membership(
                organization=self.organization,
                membership_id=target_membership.pk,
                actor=self.manager,
            )

        invitee = User.objects.create_user(
            username="accountability-invitee",
            email="invitee@example.com",
        )
        invitee.profile.is_email_verified = True
        invitee.profile.save(update_fields=["is_email_verified"])
        accepted_invitation, accepted_token = create_organization_invitation(
            organization=self.organization,
            email=invitee.email,
            invited_role=OrganizationMembership.Role.CONTRIBUTOR,
            actor=self.manager,
        )
        accept_organization_invitation(raw_token=accepted_token, actor=invitee)

        cancelled_invitation, _cancelled_token = create_organization_invitation(
            organization=self.organization,
            email="cancelled@example.com",
            invited_role=OrganizationMembership.Role.CONTRIBUTOR,
            actor=self.manager,
        )
        cancel_organization_invitation(
            invitation=cancelled_invitation,
            actor=self.manager,
        )
        with self.assertRaises(OrganizationInvitationConflict):
            cancel_organization_invitation(
                invitation=cancelled_invitation,
                actor=self.manager,
            )

        expired_invitation, _expired_token = create_organization_invitation(
            organization=self.organization,
            email="expired@example.com",
            invited_role=OrganizationMembership.Role.CONTRIBUTOR,
            actor=self.manager,
        )
        expired_invitation.expires_at = timezone.now() - timedelta(seconds=1)
        expired_invitation.save(update_fields=["expires_at", "updated_at"])
        self.assertEqual(expire_stale_invitations(organization=self.organization), 1)
        self.assertEqual(expire_stale_invitations(organization=self.organization), 0)

        update_organization_public_profile(
            organization=self.organization,
            actor=self.manager,
            changes={
                "website": "https://example.com/accountability-partner",
                "public_profile_enabled": True,
                "description": "Public organization description.",
            },
        )

        expected_actions = {
            AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_ROLE_CHANGED,
            AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_SUSPENDED,
            AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_RESTORED,
            AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_REMOVED,
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CREATED,
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_ACCEPTED,
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
            AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_EXPIRED,
            AccountabilityEvent.ActionType.ORGANIZATION_PUBLIC_PROFILE_UPDATED,
        }
        self.assertTrue(
            expected_actions.issubset(
                set(AccountabilityEvent.objects.values_list("action_type", flat=True))
            )
        )
        acceptance = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_ACCEPTED,
            resource_id=str(accepted_invitation.pk),
        )
        self.assertEqual(acceptance.authority_scope, AccountabilityEvent.AuthorityScope.PERSONAL)
        self.assertEqual(acceptance.actor_id_snapshot, str(invitee.pk))
        self.assertEqual(acceptance.actor_username_snapshot, invitee.username)
        self.assertNotIn("actor_snapshot", acceptance.context)
        self.assertIsNone(acceptance.authority_organization)
        self.assertEqual(acceptance.subject_organization, self.organization)
        invite_events = AccountabilityEvent.objects.filter(
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION_INVITATION
        )
        serialized = json.dumps(
            list(invite_events.values("previous_state", "new_state", "context", "notes"))
        ).lower()
        self.assertNotIn("token", serialized)
        self.assertNotIn("digest", serialized)

    def test_dual_role_safety_events_remain_platform_scoped(self):
        claim = Claim.objects.create(context_text="Safety accountability claim")
        thread = Thread.objects.create(
            claim=claim,
            author=self.contributor,
            caption="Safety accountability thread",
        )
        case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.SAFETY,
            thread=thread,
            source=ModerationCase.Source.USER_REPORT,
        )
        claimed = claim_safety_case(case=case, actor=self.actor)
        claim_safety_case(case=claimed, actor=self.actor)
        released = release_safety_case(case=claimed, actor=self.actor)
        claimed = claim_safety_case(case=released, actor=self.actor)
        perform_safety_case_action(
            case=claimed,
            actor=self.actor,
            action="ESCALATE",
            notes="Needs a platform policy decision.",
        )
        perform_safety_case_action(
            case=claimed,
            actor=self.actor,
            action="ESCALATE",
            notes="Repeated idempotent request.",
        )
        perform_safety_case_action(
            case=claimed,
            actor=self.actor,
            action="DISMISS",
            notes="No policy violation.",
        )
        events = AccountabilityEvent.objects.filter(
            resource_type=AccountabilityEvent.ResourceType.MODERATION_CASE,
            resource_id=str(case.pk),
        )
        self.assertEqual(
            events.filter(
                action_type=AccountabilityEvent.ActionType.SAFETY_CASE_ESCALATED
            ).count(),
            1,
        )
        self.assertTrue(events.exists())
        for event in events:
            self.assertEqual(event.actor_id_snapshot, str(self.actor.pk))
            self.assertEqual(event.actor_username_snapshot, self.actor.username)
            self.assertNotIn("actor_snapshot", event.context)
            self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.PLATFORM)
            self.assertEqual(event.capability, PartnerCapability.REVIEW_SAFETY)
            self.assertIsNone(event.authority_organization)


class DurableActorIdentityInstrumentationTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="durable-actor")
        self.organization = Organization.objects.create(
            name="Durable Actor Partner", slug="durable-actor-partner",
        )

    def record(self, **overrides):
        values = {
            "action_type": AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
            "resource_type": AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION,
            "resource_id": "durable-evidence",
            "authority_scope": AccountabilityEvent.AuthorityScope.ORGANIZATION,
            "actor": self.actor,
            "authority_organization": self.organization,
            "capability": PartnerCapability.REVIEW_EVIDENCE,
        }
        values.update(overrides)
        return record_accountability_event(**values)

    def revision(self, **overrides):
        values = {
            "action_type": AccountabilityEvent.ActionType.VERDICT_REVISED,
            "resource_type": AccountabilityEvent.ResourceType.ADJUDICATION_DECISION,
            "capability": PartnerCapability.ADJUDICATE,
        }
        values.update(overrides)
        return self.record(**values)

    def test_live_actor_snapshots_preserve_exact_ordinary_context(self):
        context = {"evidence_case_id": "case-id", "claim_id": "claim-id"}
        event = self.record(context=context)
        event.refresh_from_db()
        self.assertEqual(event.actor_id_snapshot, str(self.actor.pk))
        self.assertEqual(event.actor_username_snapshot, self.actor.username)
        self.assertEqual(event.context, {
            "evidence_case_id": "case-id", "claim_id": "claim-id",
        })
        self.assertEqual(context, event.context)
        self.assertNotIn("actor_snapshot", event.context)

    def test_username_rename_preserves_both_recorded_snapshots(self):
        actor_id = str(self.actor.pk)
        username = self.actor.username
        event = self.record()
        self.actor.username = "durable-actor-renamed"
        self.actor.save(update_fields=["username"])
        event.refresh_from_db()
        self.assertEqual(event.actor.username, "durable-actor-renamed")
        self.assertEqual(event.actor_id_snapshot, actor_id)
        self.assertEqual(event.actor_username_snapshot, username)

    def test_actor_deletion_nulls_fk_and_preserves_both_snapshots(self):
        actor_id = str(self.actor.pk)
        username = self.actor.username
        event = self.record()
        self.actor.delete()
        event.refresh_from_db()
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_id_snapshot, actor_id)
        self.assertEqual(event.actor_username_snapshot, username)

    def test_live_historical_preparer_uses_supplied_id_and_username(self):
        snapshot = {"id": str(self.actor.pk), "username": "preparer-before-rename"}
        context = {"correction_request_id": "correction-id"}
        event = self.revision(actor_snapshot=snapshot, context=context)
        event.refresh_from_db()
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.actor_id_snapshot, snapshot["id"])
        self.assertEqual(event.actor_username_snapshot, snapshot["username"])
        self.assertEqual(event.context, {
            "correction_request_id": "correction-id", "actor_snapshot": snapshot,
        })
        self.assertEqual(context, {"correction_request_id": "correction-id"})

    def test_deleted_historical_preparer_retains_recorded_id_and_username(self):
        snapshot = {"id": str(self.actor.pk), "username": self.actor.username}
        self.actor.delete()
        event = self.revision(actor=None, actor_snapshot=snapshot)
        event.refresh_from_db()
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_id_snapshot, snapshot["id"])
        self.assertEqual(event.actor_username_snapshot, snapshot["username"])
        self.assertEqual(event.context, {"actor_snapshot": snapshot})

    def test_historical_id_normalization_preserves_existing_context_behavior(self):
        snapshot = {"id": f" {self.actor.pk} ", "username": self.actor.username}
        event = self.revision(actor_snapshot=snapshot)
        normalized = {"id": str(self.actor.pk), "username": self.actor.username}
        self.assertEqual(event.actor_id_snapshot, normalized["id"])
        self.assertEqual(event.context, {"actor_snapshot": normalized})
        self.assertEqual(snapshot["id"], f" {self.actor.pk} ")

    def test_historical_snapshot_remains_restricted_to_revision_resource_and_capability(self):
        snapshot = {"id": str(self.actor.pk), "username": self.actor.username}
        before = AccountabilityEvent.objects.count()
        for overrides in (
            {"action_type": AccountabilityEvent.ActionType.EVIDENCE_VERIFIED},
            {"resource_type": AccountabilityEvent.ResourceType.EVIDENCE_SUBMISSION},
            {"capability": PartnerCapability.REVIEW_EVIDENCE},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.revision(actor_snapshot=snapshot, **overrides)
        self.assertEqual(AccountabilityEvent.objects.count(), before)

    def test_historical_snapshot_must_identify_same_live_actor(self):
        with self.assertRaises(ValidationError):
            self.revision(actor_snapshot={"id": "another-person", "username": "past-name"})
        self.assertFalse(AccountabilityEvent.objects.exists())

    def test_malformed_historical_snapshot_remains_rejected(self):
        for snapshot in (
            [], {}, {"username": "past-name"}, {"id": "past-id"},
            *({"id": value, "username": "past-name"}
              for value in (None, "", " \t", 123, False, [], {})),
            *({"id": "past-id", "username": value}
              for value in (None, "", " \t", 123, "x" * 151)),
            {"id": "past-id", "username": "past-name", "extra": "not-permitted"},
        ):
            with self.subTest(snapshot=snapshot), self.assertRaises(ValidationError):
                self.revision(actor=None, actor_snapshot=snapshot)
        self.assertFalse(AccountabilityEvent.objects.exists())

    def test_authenticated_unsaved_actor_is_rejected_with_validation_error(self):
        for actor in (User(username="unsaved"), User(pk=123456, username="unsaved-with-id")):
            with self.subTest(pk=actor.pk):
                self.assertTrue(actor.is_authenticated)
                with self.assertRaises(ValidationError):
                    self.record(actor=actor)
        self.assertFalse(AccountabilityEvent.objects.exists())

    def test_blank_live_actor_identity_is_rejected(self):
        self.actor.pk = " \t"
        with self.assertRaises(ValidationError):
            self.record()
        self.assertFalse(AccountabilityEvent.objects.exists())

    def test_live_identifier_is_normalized_without_assuming_uuid_or_integer_type(self):
        for actor_pk in (123, uuid.uuid4(), " stable-identifier "):
            actor = SimpleNamespace(
                pk=actor_pk, is_authenticated=True, username="observed-name",
                _state=SimpleNamespace(adding=False),
            )
            with self.subTest(pk=actor_pk):
                with patch("api.accountability_service.AccountabilityEvent.objects.create") as create:
                    self.record(actor=actor)
                self.assertEqual(create.call_args.kwargs["actor_id_snapshot"], str(actor_pk).strip())
                self.assertEqual(create.call_args.kwargs["actor_username_snapshot"], "observed-name")

    def test_system_event_has_empty_actor_snapshots_and_unchanged_context(self):
        event = self.record(
            actor=None, authority_scope=AccountabilityEvent.AuthorityScope.SYSTEM,
            authority_organization=None, capability="", context={"claim_id": "claim-id"},
        )
        self.assertIsNone(event.actor)
        self.assertEqual(event.actor_id_snapshot, "")
        self.assertEqual(event.actor_username_snapshot, "")
        self.assertEqual(event.context, {"claim_id": "claim-id"})

    def test_rollback_removes_live_actor_event_with_identity_snapshot(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                event = self.record()
                self.assertEqual(event.actor_id_snapshot, str(self.actor.pk))
                raise RuntimeError("force rollback")
        self.assertFalse(AccountabilityEvent.objects.exists())

    def test_authority_scope_validations_remain_unchanged(self):
        scopes = AccountabilityEvent.AuthorityScope
        snapshot = {"id": str(self.actor.pk), "username": self.actor.username}
        for scope, overrides in (
            (scopes.ORGANIZATION, {"actor": None}),
            (scopes.ORGANIZATION, {"authority_organization": None}),
            (scopes.ORGANIZATION, {"capability": ""}),
            (scopes.PLATFORM, {"actor": None, "authority_organization": None}),
            (scopes.PLATFORM, {}),
            (scopes.PLATFORM, {"authority_organization": None, "capability": ""}),
            (scopes.PERSONAL, {"actor": None, "authority_organization": None, "capability": ""}),
            (scopes.PERSONAL, {"capability": ""}),
            (scopes.PERSONAL, {"authority_organization": None}),
            (scopes.SYSTEM, {"authority_organization": None, "capability": ""}),
            (scopes.SYSTEM, {"actor": None, "capability": ""}),
            (scopes.SYSTEM, {"actor": None, "authority_organization": None}),
            *(
                (scope, {"actor": None if scope == scopes.SYSTEM else self.actor,
                         "actor_snapshot": snapshot, "authority_organization": None,
                         "capability": PartnerCapability.ADJUDICATE if scope == scopes.PLATFORM else ""})
                for scope in (scopes.PLATFORM, scopes.PERSONAL, scopes.SYSTEM)
            ),
        ):
            with self.subTest(scope=scope, overrides=overrides), self.assertRaises(ValidationError):
                self.revision(authority_scope=scope, **overrides)
        self.assertFalse(AccountabilityEvent.objects.exists())


class FactualCorrectionAccountabilityInstrumentationTests(
    FactualCorrectionHandoffFixtures,
    TestCase,
):
    def test_correction_evidence_decisions_and_reopen_are_correlated_to_claim(self):
        for status, action, reason in (
            (
                EvidenceSubmission.EvidenceStatus.VERIFIED,
                AccountabilityEvent.ActionType.EVIDENCE_VERIFIED,
                None,
            ),
            (
                EvidenceSubmission.EvidenceStatus.REJECTED,
                AccountabilityEvent.ActionType.EVIDENCE_REJECTED,
                EvidenceSubmission.RejectionReason.OUTDATED,
            ),
        ):
            with self.subTest(status=status):
                context = self.make_correction_review_context(
                    suffix=f"accountability-correlation-{status}",
                )
                result = self.review_correction(
                    context,
                    evidence_status=status,
                    rejection_reason=reason,
                )
                event = AccountabilityEvent.objects.get(
                    action_type=action,
                    resource_id=str(result["evidence"].pk),
                    context__correction_request_id=str(context["correction_request"].pk),
                )
                self.assertEqual(
                    event.context,
                    {
                        "correction_request_id": str(context["correction_request"].pk),
                        "correction_case_id": str(context["correction_case"].pk),
                        "evidence_case_id": str(result["case"].pk),
                        "is_reaffirmation": (
                            status == EvidenceSubmission.EvidenceStatus.VERIFIED
                        ),
                        "claim_id": str(context["claim"].pk),
                    },
                )
                reopened = AccountabilityEvent.objects.get(
                    action_type=AccountabilityEvent.ActionType.EVIDENCE_REOPENED,
                    resource_id=str(result["evidence"].pk),
                )
                self.assertEqual(
                    reopened.context,
                    {
                        "moderation_case_id": str(result["case"].pk),
                        "claim_id": str(context["claim"].pk),
                    },
                )

    def test_preparation_and_handoff_keep_decision_and_publication_authority_distinct(self):
        context = self.make_prepared_context(suffix="accountability-handoff")
        result = self.handoff(context)
        saved = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PROPOSAL_SAVED,
            resource_id=str(context["prepared_proposal"].pk),
        )
        prepared = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PROPOSAL_PREPARED,
            resource_id=str(context["prepared_proposal"].pk),
        )
        verdict = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
            resource_id=str(result["decision"].pk),
        )
        publication = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PUBLISHED,
            resource_id=str(result["fact_check"].pk),
        )
        self.assertEqual(
            saved.capability,
            PartnerCapability.CREATE_FACT_CHECK_DRAFT,
        )
        self.assertEqual(prepared.capability, PartnerCapability.ADJUDICATE)
        self.assertEqual(verdict.actor, context["prepared_proposal"].prepared_by)
        self.assertEqual(
            verdict.actor_id_snapshot,
            context["prepared_proposal"].prepared_by_snapshot["id"],
        )
        self.assertEqual(
            verdict.actor_username_snapshot,
            context["prepared_proposal"].prepared_by_snapshot["username"],
        )
        self.assertEqual(verdict.capability, PartnerCapability.ADJUDICATE)
        self.assertEqual(publication.actor, self.publisher)
        self.assertEqual(publication.capability, PartnerCapability.PUBLISH_FACT_CHECK)

    def test_deleted_preparer_remains_factual_actor_without_publisher_substitution(self):
        context = self.make_prepared_context(suffix="accountability-deleted-preparer")
        approver_snapshot = dict(context["prepared_proposal"].prepared_by_snapshot)

        User.objects.filter(pk=self.lead.id).delete()
        context["prepared_proposal"].refresh_from_db()
        context["correction_request"].refresh_from_db()
        self.assertIsNone(context["prepared_proposal"].prepared_by)

        result = self.handoff(context)

        verdict = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.VERDICT_REVISED,
            resource_id=str(result["decision"].pk),
        )
        publication = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.FACTUAL_CORRECTION_PUBLISHED,
            resource_id=str(result["fact_check"].pk),
        )

        self.assertIsNone(verdict.actor)
        self.assertEqual(verdict.actor_id_snapshot, approver_snapshot["id"])
        self.assertEqual(
            verdict.authority_scope,
            AccountabilityEvent.AuthorityScope.ORGANIZATION,
        )
        self.assertEqual(verdict.capability, PartnerCapability.ADJUDICATE)
        self.assertEqual(
            verdict.actor_username_snapshot,
            approver_snapshot["username"],
        )
        self.assertEqual(verdict.context["actor_snapshot"], approver_snapshot)
        self.assertNotEqual(
            verdict.actor_username_snapshot,
            self.publisher.username,
        )

        self.assertEqual(publication.actor, self.publisher)
        self.assertEqual(
            publication.capability,
            PartnerCapability.PUBLISH_FACT_CHECK,
        )

    def test_cancellation_records_only_the_successful_terminal_transition(self):
        context = self.make_prepared_context(suffix="accountability-cancel")
        result = cancel_factual_correction(
            correction_request_id=context["correction_request"].pk,
            actor=self.lead,
            organization_id=self.organization.pk,
            expected_proposal_version=context["prepared_proposal"].version,
            expected_predecessor_version=context["published"].version,
            expected_decision_revision=context["decision"].revision_number,
            cancellation_reason="The correction request is no longer needed.",
        )
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.FACTUAL_CORRECTION_CANCELLED,
            resource_id=str(result["request"].pk),
        )
        self.assertEqual(event.capability, PartnerCapability.ADJUDICATE)
        self.assertEqual(event.new_state["status"], result["request"].status)
