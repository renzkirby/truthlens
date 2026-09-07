from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    ModerationCase,
    ModerationEvent,
    Organization,
    OrganizationMembership,
    Thread,
    UserProfile,
    VerificationAssignment,
)


class EvidenceCaseApiTests(APITestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="evidence-contributor",
            password="test-password",
        )
        self.lead = User.objects.create_user(
            username="evidence-lead",
            password="test-password",
        )
        self.partner_moderator = User.objects.create_user(
            username="evidence-moderator",
            password="test-password",
        )
        self.ordinary_user = User.objects.create_user(
            username="ordinary-user",
            password="test-password",
        )
        self.safety_moderator = User.objects.create_user(
            username="safety-only",
            password="test-password",
        )
        self.safety_moderator.profile.role = UserProfile.Role.MOD
        self.safety_moderator.profile.save(update_fields=["role"])

        self.organization = self._create_organization("primary")
        self.other_organization = self._create_organization("other")
        self._add_member(
            self.lead,
            self.organization,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self._add_member(
            self.partner_moderator,
            self.organization,
            OrganizationMembership.Role.MODERATOR,
        )

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="A claim requiring professional evidence review.",
            url_link="https://example.com/claim",
            source_link="https://example.com/source",
            media_url="https://example.com/media.png",
            ai_verdict="FAKE",
            consensus_score=91.0,
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.contributor,
            caption="Community evidence discussion",
        )
        self.assignment = VerificationAssignment.objects.create(
            claim=self.claim,
            organization=self.organization,
            claimed_by=self.lead,
            status=VerificationAssignment.Status.ACTIVE,
            claimed_at=timezone.now(),
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Primary source document",
            evidence_url="https://example.com/evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_verdict="SUPPORTS",
            contributor_trust_snapshot=87.0,
        )
        self.case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=self.evidence,
            organization=self.organization,
            source=ModerationCase.Source.EVIDENCE_SUBMISSION,
        )

    @staticmethod
    def _create_organization(suffix):
        return Organization.objects.create(
            name=f"Evidence Partner {suffix}",
            slug=f"evidence-partner-{suffix}",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )

    @staticmethod
    def _add_member(user, organization, role, *, membership_status=None):
        return OrganizationMembership.objects.create(
            organization=organization,
            user=user,
            role=role,
            status=membership_status or OrganizationMembership.Status.ACTIVE,
        )

    def _queue_url(self, **params):
        values = {"organization_id": self.organization.id, **params}
        query = "&".join(f"{key}={value}" for key, value in values.items())
        return f"{reverse('evidence_case_queue')}?{query}"

    def _detail_url(self, case=None, organization=None):
        case = case or self.case
        organization = organization or self.organization
        return (
            f"{reverse('evidence_case_detail', args=[case.id])}"
            f"?organization_id={organization.id}"
        )

    def _action_url(self, case=None, organization=None):
        case = case or self.case
        organization = organization or self.organization
        return (
            f"{reverse('evidence_case_action', args=[case.id])}"
            f"?organization_id={organization.id}"
        )

    def _authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_authentication_and_capability_are_organization_scoped(self):
        self.assertEqual(
            self.client.get(self._queue_url()).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        for denied_user in (self.ordinary_user, self.safety_moderator):
            with self.subTest(user=denied_user.username):
                self._authenticate(denied_user)
                response = self.client.get(self._queue_url())
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        other_lead = User.objects.create_user(
            username="other-org-lead",
            password="test-password",
        )
        self._add_member(
            other_lead,
            self.other_organization,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self._authenticate(other_lead)
        self.assertEqual(
            self.client.get(self._queue_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.organization.partner_status = Organization.PartnerStatus.SUSPENDED
        self.organization.save(update_fields=["partner_status"])
        self._authenticate(self.lead)
        self.assertEqual(
            self.client.get(self._queue_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.organization.partner_status = Organization.PartnerStatus.ACTIVE
        self.organization.save(update_fields=["partner_status"])

        for allowed_user in (self.lead, self.partner_moderator):
            with self.subTest(user=allowed_user.username):
                self._authenticate(allowed_user)
                response = self.client.get(self._queue_url())
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_review_partner_roles_and_inactive_memberships_are_denied(self):
        denied_roles = [
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.RESEARCHER,
            OrganizationMembership.Role.CONTRIBUTOR,
        ]
        for index, role in enumerate(denied_roles):
            user = User.objects.create_user(
                username=f"denied-role-{index}",
                password="test-password",
            )
            self._add_member(user, self.organization, role)
            self._authenticate(user)
            with self.subTest(role=role):
                self.assertEqual(
                    self.client.get(self._queue_url()).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

        suspended = User.objects.create_user(
            username="suspended-reviewer",
            password="test-password",
        )
        self._add_member(
            suspended,
            self.organization,
            OrganizationMembership.Role.MODERATOR,
            membership_status=OrganizationMembership.Status.SUSPENDED,
        )
        self._authenticate(suspended)
        self.assertEqual(
            self.client.get(self._queue_url()).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_queue_requires_and_validates_allowlisted_query_parameters(self):
        self._authenticate(self.lead)
        base_url = reverse("evidence_case_queue")
        for url in (
            base_url,
            f"{base_url}?organization_id=not-a-uuid",
            self._queue_url(limit=0),
            self._queue_url(limit=101),
            self._queue_url(offset=-1),
            self._queue_url(search="unsupported"),
            self._queue_url(evidence_status="UNKNOWN"),
        ):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )

        unknown_organization_url = (
            f"{base_url}?organization_id=00000000-0000-0000-0000-000000000001"
        )
        self.assertEqual(
            self.client.get(unknown_organization_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_default_queue_is_active_unverified_and_organization_isolated(self):
        other_evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Other organization evidence",
        )
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=other_evidence,
            organization=self.other_organization,
        )
        cancelled_evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Cancelled evidence",
        )
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=cancelled_evidence,
            organization=self.organization,
            status=ModerationCase.Status.CANCELLED,
        )

        self._authenticate(self.lead)
        response = self.client.get(self._queue_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["limit"], 20)
        self.assertEqual(response.data["offset"], 0)
        self.assertEqual(response.data["organization"]["id"], str(self.organization.id))
        self.assertEqual(response.data["results"][0]["id"], str(self.case.id))

    def test_reviewed_history_is_status_specific_and_excludes_cancelled_cases(self):
        self.evidence.evidence_status = EvidenceSubmission.EvidenceStatus.VERIFIED
        self.evidence.save(update_fields=["evidence_status"])
        self.case.status = ModerationCase.Status.RESOLVED
        self.case.save(update_fields=["status"])

        rejected = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        rejected_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=rejected,
            organization=self.organization,
            status=ModerationCase.Status.RESOLVED,
        )
        cancelled = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
        )
        ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=cancelled,
            organization=self.organization,
            status=ModerationCase.Status.CANCELLED,
        )

        self._authenticate(self.lead)
        verified_response = self.client.get(
            self._queue_url(evidence_status="VERIFIED")
        )
        rejected_response = self.client.get(
            self._queue_url(evidence_status="REJECTED")
        )

        self.assertEqual(
            [item["id"] for item in verified_response.data["results"]],
            [str(self.case.id)],
        )
        self.assertEqual(
            [item["id"] for item in rejected_response.data["results"]],
            [str(rejected_case.id)],
        )

    def test_queue_pagination_is_deterministic(self):
        second_evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Second item",
        )
        second_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.EVIDENCE,
            evidence_submission=second_evidence,
            organization=self.organization,
        )

        self._authenticate(self.lead)
        first_page = self.client.get(self._queue_url(limit=1, offset=0))
        second_page = self.client.get(self._queue_url(limit=1, offset=1))

        self.assertEqual(first_page.data["count"], 2)
        self.assertNotEqual(
            first_page.data["results"][0]["id"],
            second_page.data["results"][0]["id"],
        )
        self.assertEqual(
            {first_page.data["results"][0]["id"], second_page.data["results"][0]["id"]},
            {str(self.case.id), str(second_case.id)},
        )

    def test_summary_and_detail_use_explicit_privacy_safe_shapes(self):
        ModerationEvent.objects.create(
            case=self.case,
            actor=self.lead,
            event_type=ModerationEvent.EventType.REVIEW_STARTED,
            metadata={"private": "must-not-leak"},
        )
        self._authenticate(self.lead)

        summary = self.client.get(self._queue_url()).data["results"][0]
        detail = self.client.get(self._detail_url()).data
        serialized = repr({"summary": summary, "detail": detail})

        self.assertEqual(summary["status"], ModerationCase.Status.OPEN)
        self.assertEqual(
            summary["evidence"]["evidence_status"],
            EvidenceSubmission.EvidenceStatus.UNVERIFIED,
        )
        self.assertEqual(
            summary["evidence"]["contributor"],
            {"id": self.contributor.id, "username": self.contributor.username},
        )
        self.assertFalse(summary["evidence"]["is_self_submission"])
        for forbidden in (
            "trust_score",
            "contributor_trust_snapshot",
            "email",
            "ai_verdict",
            "consensus_score",
            "metadata",
            "private",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(len(detail["events"]), 1)

    def test_detail_is_scoped_to_requested_organization(self):
        other_lead = User.objects.create_user(
            username="other-detail-lead",
            password="test-password",
        )
        self._add_member(
            other_lead,
            self.other_organization,
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self._authenticate(other_lead)
        response = self.client.get(
            self._detail_url(organization=self.other_organization)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unknown_and_non_evidence_case_are_unavailable(self):
        safety_case = ModerationCase.objects.create(
            case_type=ModerationCase.CaseType.SAFETY,
            thread=self.thread,
            source=ModerationCase.Source.USER_REPORT,
        )
        self._authenticate(self.lead)
        unknown_url = (
            f"{reverse('evidence_case_detail', args=['00000000-0000-0000-0000-000000000001'])}"
            f"?organization_id={self.organization.id}"
        )
        non_evidence_url = (
            f"{reverse('evidence_case_detail', args=[safety_case.id])}"
            f"?organization_id={self.organization.id}"
        )
        self.assertEqual(
            self.client.get(unknown_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(non_evidence_url).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_detail_event_history_is_bounded_to_fifty(self):
        ModerationEvent.objects.bulk_create(
            [
                ModerationEvent(
                    case=self.case,
                    actor=self.lead,
                    event_type=ModerationEvent.EventType.REVIEW_STARTED,
                    notes=f"Event {index}",
                )
                for index in range(55)
            ]
        )
        self._authenticate(self.lead)
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["events"]), 50)

    @patch("api.trust_service.recompute_user_trust_score")
    def test_verified_action_resolves_case_without_setting_claim_verdict(
        self,
        immediate_recompute,
    ):
        self._authenticate(self.lead)
        with patch(
            "api.tasks.recompute_user_trust_score_task.delay"
        ) as async_recompute:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self._action_url(),
                    {
                        "decision": "VERIFIED",
                        "expected_status": "UNVERIFIED",
                        "moderator_notes": "Source is accessible and supports review.",
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.evidence.refresh_from_db()
        self.case.refresh_from_db()
        self.claim.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "VERIFIED")
        self.assertEqual(self.evidence.verified_by_id, self.lead.id)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertIsNone(self.claim.final_verdict)
        self.assertFalse(AdjudicationDecision.objects.filter(claim=self.claim).exists())
        self.assertTrue(
            self.case.events.filter(
                event_type=ModerationEvent.EventType.EVIDENCE_VERIFIED
            ).exists()
        )
        immediate_recompute.assert_called_once_with(self.contributor.id)
        async_recompute.assert_called_once_with(self.contributor.id)

    def test_rejected_action_requires_valid_reason_and_records_audit(self):
        self._authenticate(self.partner_moderator)
        missing_reason = self.client.post(
            self._action_url(),
            {"decision": "REJECTED", "expected_status": "UNVERIFIED"},
            format="json",
        )
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)

        with patch("api.views.schedule_evidence_review_trust_updates"):
            response = self.client.post(
                self._action_url(),
                {
                    "decision": "REJECTED",
                    "expected_status": "UNVERIFIED",
                    "rejection_reason": "UNRELIABLE_SOURCE",
                    "moderator_notes": "Publisher provenance could not be verified.",
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "REJECTED")
        self.assertEqual(self.evidence.rejection_reason, "UNRELIABLE_SOURCE")

    def test_action_payload_is_strict_and_requires_unverified_expected_status(self):
        self._authenticate(self.lead)
        payloads = [
            {"decision": "VERIFIED"},
            {"decision": "VERIFIED", "expected_status": "VERIFIED"},
            {
                "decision": "VERIFIED",
                "expected_status": "UNVERIFIED",
                "rejection_reason": "IRRELEVANT",
            },
            {
                "decision": "VERIFIED",
                "expected_status": "UNVERIFIED",
                "unknown": True,
            },
            {
                "decision": "REJECTED",
                "expected_status": "UNVERIFIED",
                "rejection_reason": "NOT_A_REASON",
            },
            {
                "decision": "VERIFIED",
                "expected_status": "UNVERIFIED",
                "moderator_notes": "x" * 2001,
            },
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    self._action_url(), payload, format="json"
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_self_submission_is_visible_but_cannot_be_reviewed(self):
        self.evidence.contributor = self.lead
        self.evidence.save(update_fields=["contributor"])
        self._authenticate(self.lead)

        queue_item = self.client.get(self._queue_url()).data["results"][0]
        response = self.client.post(
            self._action_url(),
            {"decision": "VERIFIED", "expected_status": "UNVERIFIED"},
            format="json",
        )

        self.assertTrue(queue_item["evidence"]["is_self_submission"])
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self._authenticate(self.partner_moderator)
        with patch("api.views.schedule_evidence_review_trust_updates"):
            other_reviewer_response = self.client.post(
                self._action_url(),
                {"decision": "VERIFIED", "expected_status": "UNVERIFIED"},
                format="json",
            )
        self.assertEqual(other_reviewer_response.status_code, status.HTTP_200_OK)

    def test_stale_second_decision_and_resolved_case_action_return_conflict(self):
        self._authenticate(self.lead)
        with patch(
            "api.views.schedule_evidence_review_trust_updates"
        ):
            first = self.client.post(
                self._action_url(),
                {"decision": "VERIFIED", "expected_status": "UNVERIFIED"},
                format="json",
            )
            second = self.client.post(
                self._action_url(),
                {
                    "decision": "REJECTED",
                    "expected_status": "UNVERIFIED",
                    "rejection_reason": "IRRELEVANT",
                },
                format="json",
            )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "VERIFIED")

    def test_post_commit_reputation_failures_do_not_change_success_response(self):
        self._authenticate(self.lead)
        with patch(
            "api.trust_service.recompute_user_trust_score",
            side_effect=RuntimeError("trust unavailable"),
        ), patch(
            "api.tasks.recompute_user_trust_score_task.delay",
            side_effect=RuntimeError("broker unavailable"),
        ) as async_recompute:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self._action_url(),
                    {"decision": "VERIFIED", "expected_status": "UNVERIFIED"},
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.evidence.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "VERIFIED")
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        async_recompute.assert_called_once_with(self.contributor.id)

    def test_legacy_verify_also_contains_reputation_dispatch_failure(self):
        self._authenticate(self.lead)
        legacy_url = reverse("evidence-verify", args=[self.evidence.id])
        with patch(
            "api.trust_service.recompute_user_trust_score",
            side_effect=RuntimeError("trust unavailable"),
        ), patch(
            "api.tasks.recompute_user_trust_score_task.delay",
            side_effect=RuntimeError("broker unavailable"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.patch(
                    legacy_url,
                    {
                        "evidence_status": "VERIFIED",
                        "expected_status": "UNVERIFIED",
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.evidence_status, "VERIFIED")

    def test_legacy_evidence_queue_remains_available(self):
        self._authenticate(self.lead)
        url = (
            f"{reverse('moderation_evidence_queue')}"
            f"?organization_id={self.organization.id}"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_methods_are_read_or_action_only(self):
        self._authenticate(self.lead)
        self.assertEqual(
            self.client.post(self._queue_url(), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(self._detail_url(), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.get(self._action_url()).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
