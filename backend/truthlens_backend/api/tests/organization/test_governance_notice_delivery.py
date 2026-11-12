from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.accountability_service import record_accountability_event
from api.models import (
    AccountabilityEvent,
    Notification,
    Organization,
    OrganizationGovernanceFallbackDelivery,
    OrganizationGovernanceNoticeRecipient,
    OrganizationMembership,
    UserProfile,
)
from api.notification_service import notification_destination
from api.organization_governance_delivery_service import (
    GovernanceNoticeDeliveryError,
    deliver_governance_fallback_email,
    deliver_governance_notice_channels,
    dispatch_governance_notice_delivery,
)
from api.organization_partnership_lifecycle_service import (
    MANAGE_PARTNER_ORGANIZATION,
    suspend_partner_organization_partnership,
)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="TruthLens <noreply@truthlens.test>",
    FRONTEND_URL="https://truthlens.example",
)
class GovernanceNoticeDeliveryTests(APITestCase):
    def setUp(self):
        self.platform_admin = User.objects.create_superuser(
            username="governance-delivery-platform-admin",
            email="platform@example.com",
            password="test-password",
        )
        self.organization_admin = User.objects.create_user(
            username="governance-delivery-org-admin",
            email="admin@example.com",
            password="test-password",
        )
        self.member = User.objects.create_user(
            username="governance-delivery-member",
            email="member@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Governance Delivery Partner",
            slug="governance-delivery-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.SUSPENDED,
        )
        profile, _created = UserProfile.objects.get_or_create(
            user=self.organization_admin
        )
        profile.is_email_verified = True
        profile.save(update_fields=["is_email_verified"])
        member_profile, _created = UserProfile.objects.get_or_create(user=self.member)
        member_profile.is_email_verified = True
        member_profile.save(update_fields=["is_email_verified"])

    def client_for(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def make_event(self):
        return record_accountability_event(
            action_type=(
                AccountabilityEvent.ActionType.ORGANIZATION_PLATFORM_TRUST_UPDATED
            ),
            resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
            resource_id=self.organization.pk,
            authority_scope=AccountabilityEvent.AuthorityScope.PLATFORM,
            actor=self.platform_admin,
            subject_organization=self.organization,
            capability=MANAGE_PARTNER_ORGANIZATION,
            previous_state={
                "verification_status": Organization.VerificationStatus.VERIFIED,
                "partner_status": Organization.PartnerStatus.ACTIVE,
            },
            new_state={
                "verification_status": Organization.VerificationStatus.VERIFIED,
                "partner_status": Organization.PartnerStatus.SUSPENDED,
            },
            reason_code="PARTNERSHIP_SUSPENDED",
            notes=(
                "A detailed organization-facing rationale that must never be copied "
                "into the governance alert email."
            ),
            context={
                "governance": {
                    "suspension_type": "REMEDIAL",
                    "severity": "HIGH",
                    "policy_basis": "Partnership Governance & Enforcement Policy, Section 8.1 — Remedial Suspension",
                }
            },
        )

    def make_recipient(self, *, user=None, audience="ADMIN"):
        return OrganizationGovernanceNoticeRecipient.objects.create(
            governance_event=self.make_event(),
            user=user or self.organization_admin,
            audience=audience,
        )

    def test_admin_delivery_creates_inbox_notice_and_minimal_email(self):
        recipient = self.make_recipient()

        result = deliver_governance_notice_channels(recipient.pk)

        recipient.refresh_from_db()
        self.assertEqual(
            recipient.in_app_status,
            OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT,
        )
        self.assertEqual(
            recipient.email_status,
            OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT,
        )
        self.assertEqual(recipient.in_app_attempts, 1)
        self.assertEqual(recipient.email_attempts, 1)
        self.assertEqual(result["in_app_status"], "SENT")
        self.assertEqual(result["email_status"], "SENT")

        notification = Notification.objects.get(recipient=self.organization_admin)
        self.assertEqual(
            notification.notification_type,
            Notification.NotificationType.ORGANIZATION_GOVERNANCE_CHANGED,
        )
        self.assertEqual(
            notification.target_type,
            Notification.TargetType.GOVERNANCE_NOTICE,
        )
        self.assertEqual(notification.target_id, recipient.pk)
        self.assertEqual(
            notification_destination(notification),
            f"/governance/{recipient.pk}",
        )

        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.subject, "TruthLens Partner governance notice")
        self.assertIn("Partnership Suspended", email.body)
        self.assertIn(
            f"https://truthlens.example/governance/{recipient.pk}",
            email.body,
        )
        self.assertNotIn("detailed organization-facing rationale", email.body)
        self.assertNotIn("Partnership Enforcement Policy", email.body)

    def test_member_receives_in_app_status_but_email_is_skipped(self):
        recipient = self.make_recipient(
            user=self.member,
            audience=OrganizationGovernanceNoticeRecipient.Audience.MEMBER,
        )

        deliver_governance_notice_channels(recipient.pk)

        recipient.refresh_from_db()
        self.assertEqual(recipient.in_app_status, "SENT")
        self.assertEqual(recipient.email_status, "SKIPPED")
        self.assertEqual(recipient.in_app_attempts, 1)
        self.assertEqual(recipient.email_attempts, 0)
        self.assertEqual(len(mail.outbox), 0)

        notification = Notification.objects.get(recipient=self.member)
        self.assertEqual(notification.title, "Partner status update")
        self.assertNotIn("rationale", notification.message.lower())
        self.assertNotIn("policy", notification.message.lower())

    def test_unverified_admin_email_is_skipped_without_blocking_in_app(self):
        profile = self.organization_admin.profile
        profile.is_email_verified = False
        profile.save(update_fields=["is_email_verified"])
        recipient = self.make_recipient()

        deliver_governance_notice_channels(recipient.pk)

        recipient.refresh_from_db()
        self.assertEqual(recipient.in_app_status, "SENT")
        self.assertEqual(recipient.email_status, "SKIPPED")
        self.assertEqual(recipient.email_attempts, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_failure_does_not_duplicate_successful_in_app_delivery_on_retry(self):
        recipient = self.make_recipient()

        with patch(
            "api.organization_governance_delivery_service.EmailMultiAlternatives.send",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            with self.assertRaises(GovernanceNoticeDeliveryError):
                deliver_governance_notice_channels(recipient.pk)

        recipient.refresh_from_db()
        self.assertEqual(recipient.in_app_status, "SENT")
        self.assertEqual(recipient.email_status, "FAILED")
        self.assertEqual(recipient.in_app_attempts, 1)
        self.assertEqual(recipient.email_attempts, 1)
        self.assertEqual(
            Notification.objects.filter(recipient=self.organization_admin).count(),
            1,
        )

        deliver_governance_notice_channels(recipient.pk)

        recipient.refresh_from_db()
        self.assertEqual(recipient.in_app_status, "SENT")
        self.assertEqual(recipient.email_status, "SENT")
        self.assertEqual(recipient.in_app_attempts, 1)
        self.assertEqual(recipient.email_attempts, 2)
        self.assertEqual(
            Notification.objects.filter(recipient=self.organization_admin).count(),
            1,
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_direct_dispatch_records_smtp_failure_and_keeps_in_app_notice(self):
        recipient = self.make_recipient()

        with patch(
            "api.organization_governance_delivery_service.EmailMultiAlternatives.send",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            result = dispatch_governance_notice_delivery([recipient.pk])

        recipient.refresh_from_db()
        self.assertEqual(
            result,
            {"requested": 1, "delivered": 0, "failed": 1},
        )
        self.assertEqual(recipient.in_app_status, "SENT")
        self.assertEqual(recipient.email_status, "FAILED")

    def test_smtp_failure_after_commit_does_not_rollback_suspension(self):
        organization = Organization.objects.create(
            name="SMTP Failure Partner",
            slug="smtp-failure-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.organization_admin,
            role=OrganizationMembership.Role.ADMIN,
            status=OrganizationMembership.Status.ACTIVE,
        )
        payload = {
            "suspension_type": "REMEDIAL",
            "factors": ["VERIFICATION_STANDARDS"],
            "severity": "HIGH",
            "rationale": (
                "Repeated sourcing failures require temporary remediation before "
                "professional access resumes."
            ),
            "policy_basis": "Partnership Governance & Enforcement Policy, Section 8.1 — Remedial Suspension",
            "supporting_basis": (
                "Internal review of affected investigations and prior corrective "
                "guidance."
            ),
            "supporting_references": ["SMTP-FAILURE-001"],
            "remediation_problem": (
                "Repeated sourcing failures in completed verification work."
            ),
            "remediation_required_action": (
                "Review affected investigations and correct the sourcing process."
            ),
            "remediation_evidence_required": (
                "Updated evidence-review procedure and corrected investigation records."
            ),
            "remediation_deadline": timezone.localdate() + timedelta(days=30),
            "remediation_review_method": (
                "Platform Governance will review the submitted procedure and records."
            ),
            "remediation_failure_consequence": (
                "TruthLens may continue the suspension or consider a stronger "
                "proportionate governance action."
            ),
        }

        with patch(
            "api.organization_governance_delivery_service.EmailMultiAlternatives.send",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                suspend_partner_organization_partnership(
                    organization_id=organization.pk,
                    actor=self.platform_admin,
                    **payload,
                )

        organization.refresh_from_db()
        self.assertEqual(
            organization.partner_status,
            Organization.PartnerStatus.SUSPENDED,
        )
        recipient = OrganizationGovernanceNoticeRecipient.objects.get(
            governance_event__subject_organization=organization,
            governance_event__resource_type=AccountabilityEvent.ResourceType.ORGANIZATION,
            governance_event__resource_id=str(organization.pk),
            user=self.organization_admin,
        )
        self.assertEqual(recipient.in_app_status, "SENT")
        self.assertEqual(recipient.email_status, "FAILED")

    def test_management_detail_exposes_delivery_status_and_retry_endpoint(self):
        recipient = self.make_recipient()
        recipient.in_app_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.SENT
        recipient.email_status = OrganizationGovernanceNoticeRecipient.DeliveryStatus.FAILED
        recipient.in_app_attempts = 1
        recipient.email_attempts = 2
        recipient.last_delivery_error = "Email delivery failed: SMTP unavailable"
        recipient.save(
            update_fields=[
                "in_app_status",
                "email_status",
                "in_app_attempts",
                "email_attempts",
                "last_delivery_error",
            ]
        )

        detail = self.client_for(self.platform_admin).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": self.organization.pk},
            )
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        delivery = detail.data["governance_notice_delivery"]
        self.assertEqual(delivery["total_recipients"], 1)
        self.assertTrue(delivery["retry_available"])
        self.assertEqual(delivery["in_app"]["SENT"], 1)
        self.assertEqual(delivery["email"]["FAILED"], 1)
        self.assertEqual(delivery["recent"][0]["id"], str(recipient.pk))

        retry = self.client_for(self.platform_admin).post(
            reverse(
                "management_organization_governance_notice_retry",
                kwargs={"organization_id": self.organization.pk},
            ),
            {},
            format="json",
        )

        self.assertEqual(retry.status_code, status.HTTP_200_OK)
        self.assertEqual(retry.data["requested"], 1)
        self.assertEqual(retry.data["delivered"], 1)
        self.assertEqual(retry.data["failed"], 0)
        recipient.refresh_from_db()
        self.assertEqual(recipient.email_status, "SENT")
        self.assertEqual(len(mail.outbox), 1)

    def test_no_admin_uses_private_governance_contact_fallback(self):
        organization = Organization.objects.create(
            name="No Admin Fallback Partner",
            slug="no-admin-fallback-partner",
            governance_contact_email="governance-contact@example.com",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        payload = {
            "suspension_type": "ADMINISTRATIVE",
            "factors": ["GOVERNANCE_CAPACITY"],
            "severity": "HIGH",
            "rationale": (
                "The organization currently lacks accountable administration for "
                "continued professional access."
            ),
            "policy_basis": "Partnership Governance & Enforcement Policy, Section 8.3 — Administrative Suspension",
            "supporting_basis": "Internal organization-contact review.",
            "supporting_references": ["NO-ADMIN-001"],
        }

        with self.captureOnCommitCallbacks(execute=True):
            suspend_partner_organization_partnership(
                organization_id=organization.pk,
                actor=self.platform_admin,
                **payload,
            )

        fallback = OrganizationGovernanceFallbackDelivery.objects.get(
            governance_event__subject_organization=organization,
        )
        self.assertEqual(fallback.contact_email, "governance-contact@example.com")
        self.assertEqual(fallback.status, "SENT")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Partnership Suspended", mail.outbox[0].body)
        self.assertNotIn("Internal organization-contact review", mail.outbox[0].body)

    def test_no_admin_without_contact_is_visible_and_can_record_out_of_band_notice(self):
        organization = Organization.objects.create(
            name="Undeliverable Governance Partner",
            slug="undeliverable-governance-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        payload = {
            "suspension_type": "ADMINISTRATIVE",
            "factors": ["GOVERNANCE_CAPACITY"],
            "severity": "HIGH",
            "rationale": (
                "The organization currently lacks accountable administration for "
                "continued professional access."
            ),
            "policy_basis": "Partnership Governance & Enforcement Policy, Section 8.3 — Administrative Suspension",
            "supporting_basis": "Internal organization-contact review.",
            "supporting_references": ["NO-CONTACT-001"],
        }

        with self.captureOnCommitCallbacks(execute=True):
            suspend_partner_organization_partnership(
                organization_id=organization.pk,
                actor=self.platform_admin,
                **payload,
            )

        fallback = OrganizationGovernanceFallbackDelivery.objects.get(
            governance_event__subject_organization=organization,
        )
        self.assertEqual(fallback.status, "NOT_DELIVERABLE")

        detail = self.client_for(self.platform_admin).get(
            reverse(
                "management_organization_detail",
                kwargs={"organization_id": organization.pk},
            )
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertTrue(detail.data["governance_notice_delivery"]["no_active_admin"])
        self.assertEqual(
            detail.data["governance_notice_delivery"]["fallback"]["status"],
            "NOT_DELIVERABLE",
        )

        record = self.client_for(self.platform_admin).post(
            reverse(
                "management_organization_governance_out_of_band_notice",
                kwargs={"organization_id": organization.pk},
            ),
            {
                "fallback_delivery_id": str(fallback.pk),
                "method": "Official organization email",
                "details": (
                    "Platform Governance contacted the designated organization "
                    "representative through the established external channel."
                ),
            },
            format="json",
        )
        self.assertEqual(record.status_code, status.HTTP_200_OK)
        fallback.refresh_from_db()
        self.assertEqual(fallback.status, "OUT_OF_BAND_RECORDED")
        self.assertEqual(fallback.recorded_by, self.platform_admin)

    def test_out_of_band_notice_cannot_overwrite_sent_fallback(self):
        organization = Organization.objects.create(
            name="Sent Fallback Partner",
            slug="sent-fallback-partner",
            governance_contact_email="governance-contact@example.com",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        payload = {
            "suspension_type": "ADMINISTRATIVE",
            "factors": ["GOVERNANCE_CAPACITY"],
            "severity": "HIGH",
            "rationale": (
                "The organization currently lacks accountable administration for "
                "continued professional access."
            ),
            "policy_basis": "Partnership Governance & Enforcement Policy, Section 8.3 — Administrative Suspension",
            "supporting_basis": "Internal organization-contact review.",
            "supporting_references": ["NO-ADMIN-SENT-001"],
        }

        with self.captureOnCommitCallbacks(execute=True):
            suspend_partner_organization_partnership(
                organization_id=organization.pk,
                actor=self.platform_admin,
                **payload,
            )

        fallback = OrganizationGovernanceFallbackDelivery.objects.get(
            governance_event__subject_organization=organization,
        )
        self.assertEqual(fallback.status, "SENT")

        response = self.client_for(self.platform_admin).post(
            reverse(
                "management_organization_governance_out_of_band_notice",
                kwargs={"organization_id": organization.pk},
            ),
            {
                "fallback_delivery_id": str(fallback.pk),
                "method": "Official organization email",
                "details": (
                    "This should not replace a fallback delivery that was already "
                    "recorded as successfully sent."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        fallback.refresh_from_db()
        self.assertEqual(fallback.status, "SENT")
        self.assertEqual(fallback.out_of_band_method, "")

    def test_platform_admin_can_update_private_governance_contact(self):
        response = self.client_for(self.platform_admin).patch(
            reverse(
                "management_organization_governance_contact",
                kwargs={"organization_id": self.organization.pk},
            ),
            {"governance_contact_email": "private-governance@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.organization.refresh_from_db()
        self.assertEqual(
            self.organization.governance_contact_email,
            "private-governance@example.com",
        )
        self.assertEqual(
            response.data["governance_contact_email"],
            "private-governance@example.com",
        )

