from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import (
    AccountabilityEvent,
    Claim,
    ModerationCase,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    VerificationAssignment,
)
from api.organization_invitation_service import hash_invitation_token
from api.organization_partnership_lifecycle_service import (
    ORGANIZATION_VERIFICATION_REJECTED_REASON,
    ORGANIZATION_VERIFIED_REASON,
    PARTNERSHIP_ACTIVATED_REASON,
    PARTNERSHIP_ENDED_REASON,
    PARTNERSHIP_REINSTATED_REASON,
    PARTNERSHIP_SUSPENDED_REASON,
    OrganizationPartnershipLifecycleAuthorizationError,
    OrganizationPartnershipLifecycleConflict,
    activate_partner_organization_partnership,
    apply_legacy_platform_trust_transition,
    end_partner_organization_partnership,
    reinstate_partner_organization_partnership,
    reject_partner_organization_verification,
    suspend_partner_organization_partnership,
    verify_partner_organization,
)


class OrganizationPartnershipLifecycleServiceTests(TestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="lifecycle-platform-admin",
            email="platform@example.com",
            password="test-password",
        )
        self.ordinary_user = User.objects.create_user(
            username="lifecycle-ordinary-user",
            email="ordinary@example.com",
            password="test-password",
        )
        self.admin = User.objects.create_user(
            username="lifecycle-org-admin",
            email="admin@example.com",
            password="test-password",
        )
        self.lead = User.objects.create_user(
            username="lifecycle-lead",
            email="lead@example.com",
            password="test-password",
        )
        self.former_member = User.objects.create_user(
            username="lifecycle-former-member",
            email="former@example.com",
            password="test-password",
        )

        self.organization = Organization.objects.create(
            name="Lifecycle Partner",
            slug="lifecycle-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
        )

        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.lead_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.SUSPENDED,
        )
        self.historical_membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.former_member,
            role=OrganizationMembership.Role.RESEARCHER,
            status=OrganizationMembership.Status.LEFT,
        )

        now = timezone.now()
        self.invitation = OrganizationInvitation.objects.create(
            organization=self.organization,
            email="pending@example.com",
            invited_role=OrganizationMembership.Role.RESEARCHER,
            invited_by=self.admin,
            token_digest=hash_invitation_token("pending-token"),
            status=OrganizationInvitation.Status.PENDING,
            expires_at=now + timedelta(days=7),
            last_sent_at=now,
        )
        self.original_invitation_digest = self.invitation.token_digest

        self.active_claim = Claim.objects.create(
            context_text="An unfinished lifecycle investigation.",
        )
        self.active_assignment = VerificationAssignment.objects.create(
            claim=self.active_claim,
            organization=self.organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
            claimed_at=now,
        )
        self.active_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            status=ModerationCase.Status.IN_REVIEW,
            claim=self.active_claim,
            organization=self.organization,
            assigned_to=self.lead,
            assigned_at=now,
        )

        self.completed_claim = Claim.objects.create(
            context_text="A completed lifecycle investigation.",
        )
        self.completed_assignment = VerificationAssignment.objects.create(
            claim=self.completed_claim,
            organization=self.organization,
            claimed_by=self.admin,
            status=VerificationAssignment.Status.COMPLETED,
            claimed_at=now,
            completed_at=now,
        )

    def test_end_partnership_relinquishes_current_authority_and_preserves_history(self):
        result = end_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.organization.refresh_from_db()
        self.admin_membership.refresh_from_db()
        self.lead_membership.refresh_from_db()
        self.historical_membership.refresh_from_db()
        self.invitation.refresh_from_db()
        self.active_assignment.refresh_from_db()
        self.active_case.refresh_from_db()
        self.completed_assignment.refresh_from_db()

        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.FORMER,
        )
        self.assertEqual(
            self.organization.verification_status,
            Organization.VerificationStatus.VERIFIED,
        )
        self.assertTrue(self.organization.public_profile_enabled)

        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.LEFT,
        )
        self.assertEqual(
            self.lead_membership.status,
            OrganizationMembership.Status.LEFT,
        )
        self.assertEqual(
            self.historical_membership.status,
            OrganizationMembership.Status.LEFT,
        )

        self.assertEqual(
            self.invitation.status,
            OrganizationInvitation.Status.CANCELLED,
        )
        self.assertEqual(self.invitation.cancelled_by, self.platform_admin)
        self.assertIsNotNone(self.invitation.cancelled_at)
        self.assertNotEqual(
            self.invitation.token_digest,
            self.original_invitation_digest,
        )

        self.assertEqual(
            self.active_assignment.status,
            VerificationAssignment.Status.RELEASED,
        )
        self.assertEqual(
            self.active_assignment.organization_id,
            self.organization.pk,
        )
        self.assertEqual(
            self.active_assignment.claimed_by_id,
            self.lead.pk,
        )
        self.assertIsNotNone(self.active_assignment.released_at)

        replacement = VerificationAssignment.objects.get(
            claim=self.active_claim,
            status=VerificationAssignment.Status.AVAILABLE,
        )
        self.assertIsNone(replacement.organization_id)
        self.assertIsNone(replacement.claimed_by_id)

        self.assertIsNone(self.active_case.organization_id)
        self.assertIsNone(self.active_case.assigned_to_id)
        self.assertIsNone(self.active_case.assigned_at)

        self.assertEqual(
            self.completed_assignment.status,
            VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(
            self.completed_assignment.organization_id,
            self.organization.pk,
        )
        self.assertEqual(
            self.completed_assignment.claimed_by_id,
            self.admin.pk,
        )

        self.assertEqual(result["ended_memberships"], 2)
        self.assertEqual(result["cancelled_invitations"], 1)
        self.assertEqual(result["requeued_investigations"], 1)

        lifecycle_event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
            resource_id=str(self.organization.pk),
            reason_code=PARTNERSHIP_ENDED_REASON,
        )
        self.assertEqual(
            lifecycle_event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        self.assertEqual(lifecycle_event.actor, self.platform_admin)
        self.assertEqual(
            lifecycle_event.previous_state["partner_status"],
            Organization.PartnerStatus.ACTIVE,
        )
        self.assertEqual(
            lifecycle_event.new_state["partner_status"],
            Organization.PartnerStatus.FORMER,
        )
        self.assertEqual(
            lifecycle_event.context,
            {
                "transition": PARTNERSHIP_ENDED_REASON,
                "ended_memberships": 2,
                "cancelled_invitations": 1,
                "requeued_investigations": 1,
            },
        )

        assignment_event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.VERIFICATION_ASSIGNMENT_RELEASED,
            resource_id=str(self.active_assignment.pk),
            reason_code=PARTNERSHIP_ENDED_REASON,
        )
        self.assertEqual(
            assignment_event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )

        membership_events = AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_MEMBERSHIP_REMOVED,
            subject_organization=self.organization,
            reason_code=PARTNERSHIP_ENDED_REASON,
        )
        self.assertEqual(membership_events.count(), 2)

        invitation_event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_INVITATION_CANCELLED,
            resource_id=str(self.invitation.pk),
            reason_code=PARTNERSHIP_ENDED_REASON,
        )
        self.assertEqual(
            invitation_event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )

    def test_non_platform_admin_cannot_end_partnership(self):
        with self.assertRaises(
            OrganizationPartnershipLifecycleAuthorizationError
        ):
            end_partner_organization_partnership(
                organization_id=self.organization.pk,
                actor=self.ordinary_user,
            )

        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )

    def test_legacy_none_partner_with_prior_work_can_be_ended(self):
        self.organization.partner_status = Organization.PartnerStatus.NONE
        self.organization.verification_status = Organization.VerificationStatus.UNVERIFIED
        self.organization.save(
            update_fields=["partner_status", "verification_status"]
        )

        end_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.organization.refresh_from_db()
        self.admin_membership.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.FORMER,
        )
        self.assertEqual(
            self.organization.verification_status,
            Organization.VerificationStatus.UNVERIFIED,
        )
        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.LEFT,
        )

    def test_new_onboarding_organization_without_partner_work_cannot_be_ended(self):
        onboarding = Organization.objects.create(
            name="Lifecycle New Onboarding",
            slug="lifecycle-new-onboarding",
            verification_status=Organization.VerificationStatus.UNVERIFIED,
            partner_status=Organization.PartnerStatus.NONE,
        )

        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            end_partner_organization_partnership(
                organization_id=onboarding.pk,
                actor=self.platform_admin,
            )

    def test_former_partner_cannot_be_ended_again(self):
        self.organization.partner_status = Organization.PartnerStatus.FORMER
        self.organization.save(update_fields=["partner_status"])

        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            end_partner_organization_partnership(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
            )

    def test_suspended_partnership_can_be_ended(self):
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])

        end_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.FORMER,
        )


    def test_verify_transition_is_explicit_and_audited(self):
        onboarding = Organization.objects.create(
            name="Verification Candidate",
            slug="verification-candidate",
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.NONE,
        )

        verify_partner_organization(
            organization_id=onboarding.pk,
            actor=self.platform_admin,
        )

        onboarding.refresh_from_db()
        self.assertEqual(
            onboarding.verification_status,
            Organization.VerificationStatus.VERIFIED,
        )
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED,
            subject_organization=onboarding,
            reason_code=ORGANIZATION_VERIFIED_REASON,
        )
        self.assertEqual(
            event.previous_state["verification_status"],
            Organization.VerificationStatus.PENDING,
        )
        self.assertEqual(
            event.new_state["verification_status"],
            Organization.VerificationStatus.VERIFIED,
        )

    def test_reject_verification_is_limited_to_onboarding_state(self):
        onboarding = Organization.objects.create(
            name="Rejected Candidate",
            slug="rejected-candidate",
            verification_status=Organization.VerificationStatus.UNVERIFIED,
            partner_status=Organization.PartnerStatus.NONE,
        )

        reject_partner_organization_verification(
            organization_id=onboarding.pk,
            actor=self.platform_admin,
        )

        onboarding.refresh_from_db()
        self.assertEqual(
            onboarding.verification_status,
            Organization.VerificationStatus.REJECTED,
        )
        self.assertTrue(
            AccountabilityEvent.objects.filter(
                subject_organization=onboarding,
                reason_code=ORGANIZATION_VERIFICATION_REJECTED_REASON,
            ).exists()
        )

        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            reject_partner_organization_verification(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
            )

    def test_activate_requires_verified_onboarding_without_prior_partner_work(self):
        onboarding = Organization.objects.create(
            name="Activation Candidate",
            slug="activation-candidate",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.NONE,
        )

        activate_partner_organization_partnership(
            organization_id=onboarding.pk,
            actor=self.platform_admin,
        )

        onboarding.refresh_from_db()
        self.assertEqual(
            onboarding.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )
        self.assertTrue(
            AccountabilityEvent.objects.filter(
                subject_organization=onboarding,
                reason_code=PARTNERSHIP_ACTIVATED_REASON,
            ).exists()
        )

        self.organization.partner_status = Organization.PartnerStatus.NONE
        self.organization.save(update_fields=["partner_status"])
        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            activate_partner_organization_partnership(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
            )

    def test_suspend_disables_partnership_without_dropping_current_work(self):
        suspend_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.organization.refresh_from_db()
        self.admin_membership.refresh_from_db()
        self.active_assignment.refresh_from_db()

        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.SUSPENDED,
        )
        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )
        self.assertEqual(
            self.active_assignment.status,
            VerificationAssignment.Status.ACTIVE,
        )
        self.assertEqual(
            self.active_assignment.organization_id,
            self.organization.pk,
        )
        self.assertTrue(
            AccountabilityEvent.objects.filter(
                subject_organization=self.organization,
                reason_code=PARTNERSHIP_SUSPENDED_REASON,
            ).exists()
        )

    def test_reinstate_suspended_partner_preserves_current_memberships(self):
        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])

        reinstate_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.organization.refresh_from_db()
        self.admin_membership.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )
        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.ACTIVE,
        )
        self.assertTrue(
            AccountabilityEvent.objects.filter(
                subject_organization=self.organization,
                reason_code=PARTNERSHIP_REINSTATED_REASON,
            ).exists()
        )

    def test_reinstate_former_partner_never_reactivates_historical_memberships(self):
        end_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.admin_membership.refresh_from_db()
        self.lead_membership.refresh_from_db()
        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.LEFT,
        )

        reinstate_partner_organization_partnership(
            organization_id=self.organization.pk,
            actor=self.platform_admin,
        )

        self.organization.refresh_from_db()
        self.admin_membership.refresh_from_db()
        self.lead_membership.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )
        self.assertEqual(
            self.admin_membership.status,
            OrganizationMembership.Status.LEFT,
        )
        self.assertEqual(
            self.lead_membership.status,
            OrganizationMembership.Status.LEFT,
        )

    def test_non_platform_admin_cannot_use_explicit_governance_transition(self):
        with self.assertRaises(
            OrganizationPartnershipLifecycleAuthorizationError
        ):
            suspend_partner_organization_partnership(
                organization_id=self.organization.pk,
                actor=self.ordinary_user,
            )


    def test_legacy_retirement_state_cannot_bypass_retirement_by_verifying(self):
        self.organization.partner_status = Organization.PartnerStatus.NONE
        self.organization.verification_status = Organization.VerificationStatus.UNVERIFIED
        self.organization.save(
            update_fields=["partner_status", "verification_status"]
        )

        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            verify_partner_organization(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
            )

        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.verification_status,
            Organization.VerificationStatus.UNVERIFIED,
        )


    def test_legacy_trust_adapter_rolls_back_combined_transition_when_second_step_fails(
        self,
    ):
        onboarding = Organization.objects.create(
            name="Legacy Atomic Candidate",
            slug="legacy-atomic-candidate",
            verification_status=Organization.VerificationStatus.PENDING,
            partner_status=Organization.PartnerStatus.NONE,
        )

        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            apply_legacy_platform_trust_transition(
                organization_id=onboarding.pk,
                actor=self.platform_admin,
                verification_status=Organization.VerificationStatus.VERIFIED,
                partner_status=Organization.PartnerStatus.SUSPENDED,
            )

        onboarding.refresh_from_db()
        self.assertEqual(
            onboarding.verification_status,
            Organization.VerificationStatus.PENDING,
        )
        self.assertEqual(
            onboarding.partner_status,
            Organization.PartnerStatus.NONE,
        )
        self.assertFalse(
            AccountabilityEvent.objects.filter(
                subject_organization=onboarding,
                action_type=(
                    AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
                ),
            ).exists()
        )

    def test_legacy_trust_adapter_rejects_direct_former_transition(self):
        with self.assertRaises(OrganizationPartnershipLifecycleConflict):
            apply_legacy_platform_trust_transition(
                organization_id=self.organization.pk,
                actor=self.platform_admin,
                partner_status=Organization.PartnerStatus.FORMER,
            )

        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.partner_status,
            Organization.PartnerStatus.ACTIVE,
        )
