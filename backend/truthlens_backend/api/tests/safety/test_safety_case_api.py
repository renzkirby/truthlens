import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Claim,
    EvidenceSubmission,
    FlagResolutionLog,
    ModerationCase,
    ModerationEvent,
    Organization,
    OrganizationMembership,
    Thread,
    ThreadFlag,
    UserProfile,
)
from api.moderation_service import ModerationCaseError, create_moderation_case


class SafetyCaseApiTests(APITestCase):
    def setUp(self):
        self.author = self._user("safety-author")
        self.contributor = self._user("safety-contributor")
        self.reporter_one = self._user("safety-reporter-one")
        self.reporter_two = self._user("safety-reporter-two")
        self.moderator = self._moderator("safety-moderator")
        self.other_moderator = self._moderator("safety-other-moderator")
        self.ordinary_user = self._user("safety-ordinary")

        self.partner_organization = Organization.objects.create(
            name="Safety API Partner",
            slug="safety-api-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
        )
        self.partner_lead = self._user("safety-partner-lead")
        OrganizationMembership.objects.create(
            organization=self.partner_organization,
            user=self.partner_lead,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        self.thread = self._thread("Primary Safety case")
        self.case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.reporter_one,
            source=ModerationCase.Source.USER_REPORT,
            priority=ModerationCase.Priority.HIGH,
            thread=self.thread,
        )
        self.report_one = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.reporter_one,
            reason=ThreadFlag.Reason.SPAM,
            notes="Repeated promotional links.",
        )
        self.report_two = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.reporter_two,
            reason=ThreadFlag.Reason.HARASSMENT,
            notes="Targeted abusive language.",
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Context supplied by a contributor.",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
            evidence_url="https://example.com/context",
            contributor_trust_snapshot=25.0,
        )

    @staticmethod
    def _user(username):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="test-password",
        )

    def _moderator(self, username):
        user = self._user(username)
        user.profile.role = UserProfile.Role.MOD
        user.profile.save(update_fields=["role"])
        return user

    def _thread(self, caption, *, status_value=Thread.Status.OPEN):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Claim context for {caption}.",
            verified_via=Claim.VerificationSource.PENDING,
        )
        return Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=caption,
            status=status_value,
        )

    def _safety_case(
        self,
        caption,
        *,
        status_value=ModerationCase.Status.OPEN,
        priority=ModerationCase.Priority.NORMAL,
        assigned_to=None,
    ):
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.moderator,
            thread=self._thread(caption),
            priority=priority,
        )
        ModerationCase.objects.filter(pk=case.pk).update(
            status=status_value,
            assigned_to=assigned_to,
        )
        case.refresh_from_db()
        return case

    @staticmethod
    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _url(self, name, case=None):
        if case is None:
            return reverse(name)
        return reverse(name, kwargs={"case_id": case.id})

    def _claim_case(self, case=None, moderator=None):
        case = case or self.case
        moderator = moderator or self.moderator
        return self._client_for(moderator).post(
            self._url("safety_case_claim", case),
            {},
            format="json",
        )

    def test_anonymous_and_ordinary_users_are_denied(self):
        anonymous_response = APIClient().get(self._url("safety_case_queue"))
        ordinary_response = self._client_for(self.ordinary_user).get(
            self._url("safety_case_queue")
        )

        self.assertEqual(anonymous_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(ordinary_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_partner_factual_role_cannot_access_safety_endpoints(self):
        client = self._client_for(self.partner_lead)
        requests = [
            client.get(self._url("safety_case_queue")),
            client.get(self._url("safety_case_detail", self.case)),
            client.post(self._url("safety_case_claim", self.case), {}, format="json"),
            client.post(self._url("safety_case_release", self.case), {}, format="json"),
            client.post(
                self._url("safety_case_action", self.case),
                {"action": "DISMISS"},
                format="json",
            ),
        ]

        self.assertTrue(
            all(response.status_code == status.HTTP_403_FORBIDDEN for response in requests)
        )

    def test_no_organization_role_grants_platform_safety_authority(self):
        roles = [
            OrganizationMembership.Role.OWNER,
            OrganizationMembership.Role.ADMIN,
            OrganizationMembership.Role.LEAD_VERIFIER,
            OrganizationMembership.Role.MODERATOR,
            OrganizationMembership.Role.RESEARCHER,
            OrganizationMembership.Role.CONTRIBUTOR,
        ]

        for index, role in enumerate(roles):
            user = self._user(f"safety-org-role-{index}")
            OrganizationMembership.objects.create(
                organization=self.partner_organization,
                user=user,
                role=role,
                status=OrganizationMembership.Status.ACTIVE,
            )
            response = self._client_for(user).get(self._url("safety_case_queue"))
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_safety_moderator_can_read_queue(self):
        response = self._client_for(self.moderator).get(
            self._url("safety_case_queue")
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.case.id))

    def test_queue_contains_only_active_safety_cases(self):
        active_statuses = [
            ModerationCase.Status.OPEN,
            ModerationCase.Status.IN_REVIEW,
            ModerationCase.Status.ESCALATED,
            ModerationCase.Status.REOPENED,
        ]
        active_cases = [self.case]
        for case_status in active_statuses[1:]:
            active_cases.append(
                self._safety_case(f"Active {case_status}", status_value=case_status)
            )

        self._safety_case("Resolved", status_value=ModerationCase.Status.RESOLVED)
        self._safety_case("Cancelled", status_value=ModerationCase.Status.CANCELLED)

        evidence_case = create_moderation_case(
            case_type=ModerationCase.CaseType.EVIDENCE,
            actor=self.moderator,
            evidence_submission=self.evidence,
        )
        create_moderation_case(
            case_type=ModerationCase.CaseType.ADJUDICATION,
            actor=self.moderator,
            claim=self.thread.claim,
        )

        response = self._client_for(self.moderator).get(
            self._url("safety_case_queue")
        )
        returned_ids = {item["id"] for item in response.data["results"]}

        self.assertEqual(returned_ids, {str(case.id) for case in active_cases})
        self.assertNotIn(str(evidence_case.id), returned_ids)

    def test_queue_filters_case_status_priority_and_assignment(self):
        self.thread.status = Thread.Status.REJECTED
        self.thread.save(update_fields=["status"])
        self._safety_case(
            "Other priority",
            status_value=ModerationCase.Status.ESCALATED,
            priority=ModerationCase.Priority.NORMAL,
            assigned_to=self.other_moderator,
        )
        ModerationCase.objects.filter(pk=self.case.pk).update(
            assigned_to=self.moderator
        )

        response = self._client_for(self.moderator).get(
            self._url("safety_case_queue"),
            {
                "status": ModerationCase.Status.OPEN,
                "priority": ModerationCase.Priority.HIGH,
                "assigned": "me",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.case.id))

        unassigned_case = self._safety_case("Unassigned filter case")
        unassigned_response = self._client_for(self.moderator).get(
            self._url("safety_case_queue"),
            {"assigned": "unassigned"},
        )
        unassigned_ids = {
            item["id"] for item in unassigned_response.data["results"]
        }
        self.assertIn(str(unassigned_case.id), unassigned_ids)
        self.assertNotIn(str(self.case.id), unassigned_ids)

    def test_invalid_queue_filter_is_rejected(self):
        response = self._client_for(self.moderator).get(
            self._url("safety_case_queue"),
            {"status": ModerationCase.Status.RESOLVED},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_queue_report_summary_is_unresolved_and_bounded(self):
        resolved_report = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=self.ordinary_user,
            reason=ThreadFlag.Reason.OTHER,
            resolved_at=self.case.created_at,
            resolution_case=self.case,
        )
        self.assertIsNotNone(resolved_report.resolved_at)

        response = self._client_for(self.moderator).get(
            self._url("safety_case_queue")
        )
        summary = response.data["results"][0]

        self.assertEqual(summary["report_count"], 2)
        self.assertEqual(
            {item["reason"]: item["count"] for item in summary["report_reason_summary"]},
            {ThreadFlag.Reason.HARASSMENT: 1, ThreadFlag.Reason.SPAM: 1},
        )

    def test_detail_uses_explicit_privacy_safe_shape(self):
        response = self._client_for(self.moderator).get(
            self._url("safety_case_detail", self.case)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["thread"]["author"], {
            "id": self.author.id,
            "username": self.author.username,
        })
        self.assertEqual(len(response.data["reports"]), 2)
        for report in response.data["reports"]:
            self.assertNotIn("flagged_by", report)
            self.assertNotIn("reporter", report)
            self.assertNotIn("email", report)
        serialized = str(response.data)
        self.assertNotIn("trust_score", serialized)
        self.assertNotIn("capabilities", serialized)
        self.assertNotIn("metadata", serialized)
        created_event = next(
            event
            for event in response.data["events"]
            if event["event_type"] == ModerationEvent.EventType.CASE_CREATED
        )
        self.assertIsNone(created_event["actor"])

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_case_reports_and_actions_remain_isolated_across_review_cycles(
        self,
        delay,
    ):
        self._claim_case()
        with self.captureOnCommitCallbacks(execute=True):
            resolved_response = self._client_for(self.moderator).post(
                self._url("safety_case_action", self.case),
                {"action": "DISMISS"},
                format="json",
            )

        original_report_ids = {
            str(self.report_one.id),
            str(self.report_two.id),
        }
        self.assertEqual(resolved_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {report["id"] for report in resolved_response.data["reports"]},
            original_report_ids,
        )

        new_reporter = self._user("safety-later-reporter")
        later_report = ThreadFlag.objects.create(
            thread=self.thread,
            flagged_by=new_reporter,
            reason=ThreadFlag.Reason.OTHER,
            notes="A report from the later review cycle.",
        )
        later_case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=new_reporter,
            source=ModerationCase.Source.USER_REPORT,
            thread=self.thread,
        )

        client = self._client_for(self.moderator)
        old_detail = client.get(self._url("safety_case_detail", self.case))
        new_detail = client.get(self._url("safety_case_detail", later_case))

        self.assertEqual(old_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(new_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            {report["id"] for report in old_detail.data["reports"]},
            original_report_ids,
        )
        self.assertNotIn(
            str(later_report.id),
            {report["id"] for report in old_detail.data["reports"]},
        )
        self.assertEqual(
            {report["id"] for report in new_detail.data["reports"]},
            {str(later_report.id)},
        )

        for response in [old_detail, new_detail]:
            for report in response.data["reports"]:
                self.assertEqual(
                    set(report),
                    {"id", "reason", "reason_label", "notes", "flagged_at"},
                )

        stale_action = client.post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS"},
            format="json",
        )

        later_case.refresh_from_db()
        later_report.refresh_from_db()
        self.assertEqual(stale_action.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(later_case.status, ModerationCase.Status.OPEN)
        self.assertIsNone(later_case.assigned_to_id)
        self.assertIsNone(later_report.resolved_at)
        self.assertIsNone(later_report.resolution_case_id)

    def test_detail_returns_404_for_unknown_or_non_safety_case(self):
        evidence_case = create_moderation_case(
            case_type=ModerationCase.CaseType.EVIDENCE,
            actor=self.moderator,
            evidence_submission=self.evidence,
        )
        client = self._client_for(self.moderator)

        unknown_response = client.get(
            reverse("safety_case_detail", kwargs={"case_id": uuid.uuid4()})
        )
        wrong_type_response = client.get(
            self._url("safety_case_detail", evidence_case)
        )

        self.assertEqual(unknown_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(wrong_type_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_claim_is_idempotent_for_same_moderator(self):
        first = self._claim_case()
        second = self._claim_case()
        self.case.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.assigned_to, self.moderator)
        self.assertEqual(
            self.case.events.filter(
                event_type=ModerationEvent.EventType.CASE_CLAIMED
            ).count(),
            1,
        )

    def test_second_moderator_cannot_take_claimed_case(self):
        self._claim_case()
        response = self._claim_case(moderator=self.other_moderator)
        self.case.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.case.assigned_to, self.moderator)

    def test_resolved_case_cannot_be_claimed_or_released(self):
        resolved_case = self._safety_case(
            "Resolved assignment case",
            status_value=ModerationCase.Status.RESOLVED,
            assigned_to=self.moderator,
        )
        client = self._client_for(self.moderator)

        claim_response = client.post(
            self._url("safety_case_claim", resolved_case), {}, format="json"
        )
        release_response = client.post(
            self._url("safety_case_release", resolved_case), {}, format="json"
        )

        self.assertEqual(claim_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(release_response.status_code, status.HTTP_409_CONFLICT)

    def test_only_current_assignee_can_release_case(self):
        self._claim_case()
        other_response = self._client_for(self.other_moderator).post(
            self._url("safety_case_release", self.case), {}, format="json"
        )
        owner_response = self._client_for(self.moderator).post(
            self._url("safety_case_release", self.case), {}, format="json"
        )
        repeated_response = self._client_for(self.moderator).post(
            self._url("safety_case_release", self.case), {}, format="json"
        )

        self.assertEqual(other_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(owner_response.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_response.status_code, status.HTTP_409_CONFLICT)

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_dismiss_resolves_case_and_reports_but_keeps_content_visible(self, delay):
        self._claim_case()
        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.moderator).post(
                self._url("safety_case_action", self.case),
                {"action": "DISMISS"},
                format="json",
            )
        self.case.refresh_from_db()
        self.thread.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(self.thread.status, Thread.Status.OPEN)
        self.assertFalse(
            ThreadFlag.objects.filter(
                thread=self.thread, resolved_at__isnull=True
            ).exists()
        )
        self.assertEqual(FlagResolutionLog.objects.filter(thread=self.thread).count(), 2)
        self.assertTrue(
            self.case.events.filter(
                event_type=ModerationEvent.EventType.SAFETY_DISMISSED
            ).exists()
        )
        self.assertGreaterEqual(delay.call_count, 3)

    def test_remove_and_escalate_require_notes(self):
        self._claim_case()
        client = self._client_for(self.moderator)

        for action in ["REMOVE", "ESCALATE"]:
            response = client.post(
                self._url("safety_case_action", self.case),
                {"action": action, "notes": "   "},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_remove_preserves_legacy_state_audit_and_trust_effects(self, delay):
        self._claim_case()
        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.moderator).post(
                self._url("safety_case_action", self.case),
                {"action": "REMOVE", "notes": "Confirmed targeted abuse."},
                format="json",
            )
        self.case.refresh_from_db()
        self.thread.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(self.thread.status, Thread.Status.REJECTED)
        self.assertEqual(self.thread.moderated_by, self.moderator)
        self.assertEqual(self.thread.moderator_notes, "Confirmed targeted abuse.")
        self.assertTrue(
            self.case.events.filter(
                event_type=ModerationEvent.EventType.CONTENT_REMOVED
            ).exists()
        )
        called_ids = {call.args[0] for call in delay.call_args_list}
        self.assertEqual(
            called_ids,
            {
                self.reporter_one.id,
                self.reporter_two.id,
                self.author.id,
                self.contributor.id,
            },
        )
    def test_escalate_keeps_case_and_reports_active_and_is_idempotent(self):
        self._claim_case()
        client = self._client_for(self.moderator)
        payload = {"action": "ESCALATE", "notes": "Specialist review needed."}

        first = client.post(
            self._url("safety_case_action", self.case), payload, format="json"
        )
        second = client.post(
            self._url("safety_case_action", self.case), payload, format="json"
        )
        self.case.refresh_from_db()

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.status, ModerationCase.Status.ESCALATED)
        self.assertEqual(
            ThreadFlag.objects.filter(
                thread=self.thread, resolved_at__isnull=True
            ).count(),
            2,
        )
        self.assertEqual(
            self.case.events.filter(
                event_type=ModerationEvent.EventType.CASE_ESCALATED
            ).count(),
            1,
        )

    def test_action_requires_assignment_owner(self):
        unassigned_response = self._client_for(self.moderator).post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS"},
            format="json",
        )
        ModerationCase.objects.filter(pk=self.case.pk).update(
            assigned_to=self.other_moderator
        )
        other_owned_response = self._client_for(self.moderator).post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS"},
            format="json",
        )

        self.assertEqual(unassigned_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(other_owned_response.status_code, status.HTTP_409_CONFLICT)

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_stale_second_resolution_is_a_conflict(self, delay):
        self._claim_case()
        client = self._client_for(self.moderator)
        first = client.post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS"},
            format="json",
        )
        second = client.post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS"},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            self.case.events.filter(
                event_type=ModerationEvent.EventType.CASE_RESOLVED
            ).count(),
            1,
        )

    def test_action_rejects_unknown_fields_and_overlong_notes(self):
        self._claim_case()
        client = self._client_for(self.moderator)
        unknown_response = client.post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS", "thread_id": str(self.thread.id)},
            format="json",
        )
        long_response = client.post(
            self._url("safety_case_action", self.case),
            {"action": "DISMISS", "notes": "x" * 2001},
            format="json",
        )

        self.assertEqual(unknown_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(long_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_case_endpoints_reject_unsupported_methods(self):
        client = self._client_for(self.moderator)

        self.assertEqual(
            client.post(self._url("safety_case_queue"), {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.patch(
                self._url("safety_case_detail", self.case), {}, format="json"
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.get(self._url("safety_case_claim", self.case)).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.get(self._url("safety_case_release", self.case)).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            client.get(self._url("safety_case_action", self.case)).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_legacy_safety_action_retains_trust_recomputation(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.moderator).post(
                reverse(
                    "moderation_safety_action",
                    kwargs={"thread_id": self.thread.id},
                ),
                {"action": "REMOVE", "moderator_notes": "Legacy path review."},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        called_ids = {call.args[0] for call in delay.call_args_list}
        self.assertEqual(
            called_ids,
            {
                self.reporter_one.id,
                self.reporter_two.id,
                self.author.id,
                self.contributor.id,
            },
        )

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_dismiss_remains_successful_when_trust_dispatch_fails(self, delay):
        delay.side_effect = ConnectionError("Redis unavailable")
        self._claim_case()

        with self.assertLogs("api.safety_review_service", level="ERROR") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                response = self._client_for(self.moderator).post(
                    self._url("safety_case_action", self.case),
                    {"action": "DISMISS"},
                    format="json",
                )

        self.case.refresh_from_db()
        self.thread.refresh_from_db()
        called_ids = {call.args[0] for call in delay.call_args_list}

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(self.thread.status, Thread.Status.OPEN)
        self.assertFalse(
            ThreadFlag.objects.filter(
                thread=self.thread,
                resolved_at__isnull=True,
            ).exists()
        )
        self.assertEqual(
            called_ids,
            {
                self.reporter_one.id,
                self.reporter_two.id,
                self.contributor.id,
            },
        )
        self.assertTrue(
            any(
                f"case_id={self.case.id}" in message
                and f"thread_id={self.thread.id}" in message
                for message in logs.output
            )
        )

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_remove_remains_successful_when_trust_dispatch_fails(self, delay):
        delay.side_effect = ConnectionError("Redis unavailable")
        self._claim_case()

        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.moderator).post(
                self._url("safety_case_action", self.case),
                {"action": "REMOVE", "notes": "Confirmed violation."},
                format="json",
            )

        self.case.refresh_from_db()
        self.thread.refresh_from_db()
        called_ids = {call.args[0] for call in delay.call_args_list}

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(self.thread.status, Thread.Status.REJECTED)
        self.assertEqual(FlagResolutionLog.objects.filter(thread=self.thread).count(), 2)
        self.assertEqual(
            called_ids,
            {
                self.reporter_one.id,
                self.reporter_two.id,
                self.author.id,
                self.contributor.id,
            },
        )

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    def test_legacy_action_remains_successful_when_trust_dispatch_fails(self, delay):
        delay.side_effect = ConnectionError("Redis unavailable")

        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.moderator).post(
                reverse(
                    "moderation_safety_action",
                    kwargs={"thread_id": self.thread.id},
                ),
                {"action": "REMOVE", "moderator_notes": "Legacy violation."},
                format="json",
            )

        self.case.refresh_from_db()
        self.thread.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(self.thread.status, Thread.Status.REJECTED)
        self.assertEqual(delay.call_count, 4)

    @patch("api.tasks.recompute_user_trust_score_task.delay")
    @patch("api.safety_review_service.resolve_safety_case")
    def test_authoritative_resolution_failure_is_not_swallowed(
        self,
        resolve_case,
        delay,
    ):
        resolve_case.side_effect = ModerationCaseError("Resolution failed.")
        self._claim_case()

        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.moderator).post(
                self._url("safety_case_action", self.case),
                {"action": "DISMISS"},
                format="json",
            )

        self.case.refresh_from_db()
        self.thread.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.case.status, ModerationCase.Status.OPEN)
        self.assertEqual(self.thread.status, Thread.Status.OPEN)
        self.assertEqual(
            ThreadFlag.objects.filter(
                thread=self.thread,
                resolved_at__isnull=True,
            ).count(),
            2,
        )
        delay.assert_not_called()
