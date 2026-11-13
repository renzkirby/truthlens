from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Claim,
    CommunityReport,
    CommunityReportOutcome,
    CommunitySafetyDecision,
    CommunitySafetyReconsideration,
    EvidenceSubmission,
    ModerationCase,
    Thread,
    ThreadComment,
    UserProfile,
)
from api.trust_service import calculate_trust_components


class MultiTargetCommunitySafetyTests(APITestCase):
    def setUp(self):
        self.thread_author = self._user("multitarget-thread-author")
        self.comment_owner = self._user("multitarget-comment-owner")
        self.evidence_owner = self._user("multitarget-evidence-owner")
        self.reporter_one = self._user("multitarget-reporter-one")
        self.reporter_two = self._user("multitarget-reporter-two")
        self.unrelated = self._user("multitarget-unrelated")
        self.moderator = self._moderator("multitarget-moderator")
        self.second_moderator = self._moderator("multitarget-second-moderator")

        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Multi-target Safety test claim.",
            verified_via=Claim.VerificationSource.PENDING,
        )
        self.thread = Thread.objects.create(
            claim=self.claim,
            author=self.thread_author,
            caption="Multi-target Safety discussion.",
            status=Thread.Status.OPEN,
        )
        self.comment = ThreadComment.objects.create(
            thread=self.thread,
            commenter=self.comment_owner,
            comment_text="A comment that can be reviewed independently.",
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.evidence_owner,
            evidence_caption="Evidence explanation for Safety testing.",
            evidence_url="https://example.com/multitarget-evidence",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
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

    @staticmethod
    def _client(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _report(self, *, reporter, target_type, reason="HARASSMENT", notes="Target-specific concern."):
        payload = {
            "target_type": target_type,
            "thread_id": str(self.thread.pk),
            "reason": reason,
            "notes": notes,
        }
        if target_type == CommunityReport.TargetType.COMMENT:
            payload["comment_id"] = str(self.comment.pk)
        elif target_type == CommunityReport.TargetType.EVIDENCE:
            payload["evidence_submission_id"] = str(self.evidence.pk)

        return self._client(reporter).post(
            reverse("community-report-list"),
            payload,
            format="json",
        )

    def _case(self, target_type):
        filters = {
            "case_type": ModerationCase.CaseType.SAFETY,
            "safety_target_type": target_type,
            "thread": self.thread,
        }
        if target_type == ModerationCase.SafetyTargetType.COMMENT:
            filters["thread_comment"] = self.comment
        elif target_type == ModerationCase.SafetyTargetType.EVIDENCE:
            filters["evidence_submission"] = self.evidence
        return ModerationCase.objects.get(**filters)

    def _claim(self, case, moderator=None):
        moderator = moderator or self.moderator
        response = self._client(moderator).post(
            reverse("safety_case_claim", kwargs={"case_id": case.pk}),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response

    def _remove(self, *, case, confirmed_report_ids, moderator=None):
        moderator = moderator or self.moderator
        self._claim(case, moderator)
        with self.captureOnCommitCallbacks(execute=True):
            response = self._client(moderator).post(
                reverse("safety_case_action", kwargs={"case_id": case.pk}),
                {
                    "action": "REMOVE",
                    "notes": "The reported content meets the targeted abuse rule.",
                    "violation_code": "HARASSMENT_TARGETED_ABUSE",
                    "confirmed_report_ids": [
                        str(report_id) for report_id in confirmed_report_ids
                    ],
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return CommunitySafetyDecision.objects.get(moderation_case=case)

    def test_comment_and_evidence_reports_create_independent_safety_cases(self):
        comment_response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
        )
        evidence_response = self._report(
            reporter=self.reporter_two,
            target_type=CommunityReport.TargetType.EVIDENCE,
        )

        self.assertEqual(comment_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(evidence_response.status_code, status.HTTP_201_CREATED)

        comment_case = self._case(ModerationCase.SafetyTargetType.COMMENT)
        evidence_case = self._case(ModerationCase.SafetyTargetType.EVIDENCE)

        self.assertNotEqual(comment_case.pk, evidence_case.pk)
        self.assertEqual(comment_case.thread_comment, self.comment)
        self.assertEqual(evidence_case.evidence_submission, self.evidence)
        self.assertEqual(
            ModerationCase.objects.filter(
                case_type=ModerationCase.CaseType.SAFETY,
                thread=self.thread,
                status__in=[
                    ModerationCase.Status.OPEN,
                    ModerationCase.Status.IN_REVIEW,
                    ModerationCase.Status.ESCALATED,
                    ModerationCase.Status.REOPENED,
                ],
            ).count(),
            2,
        )

    def test_report_target_must_belong_to_declared_thread(self):
        other_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Other discussion.",
            verified_via=Claim.VerificationSource.PENDING,
        )
        other_thread = Thread.objects.create(
            claim=other_claim,
            author=self.thread_author,
            caption="Other thread.",
        )

        response = self._client(self.reporter_one).post(
            reverse("community-report-list"),
            {
                "target_type": "COMMENT",
                "thread_id": str(other_thread.pk),
                "comment_id": str(self.comment.pk),
                "reason": "HARASSMENT",
                "notes": "Mismatched target.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(CommunityReport.objects.exists())

    def test_other_report_reason_requires_explanation(self):
        response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
            reason=CommunityReport.Reason.OTHER,
            notes="",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("notes", response.data)

    def test_owner_cannot_report_own_comment_or_evidence(self):
        comment_response = self._report(
            reporter=self.comment_owner,
            target_type=CommunityReport.TargetType.COMMENT,
        )
        evidence_response = self._report(
            reporter=self.evidence_owner,
            target_type=CommunityReport.TargetType.EVIDENCE,
        )

        self.assertEqual(comment_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(evidence_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CommunityReport.objects.exists())

    def test_comment_removal_uses_tombstone_and_mixed_report_semantics(self):
        spam = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
            reason=CommunityReport.Reason.SPAM,
            notes="I think this is spam.",
        )
        harassment = self._report(
            reporter=self.reporter_two,
            target_type=CommunityReport.TargetType.COMMENT,
            reason=CommunityReport.Reason.HARASSMENT,
            notes="This is targeted abuse.",
        )
        self.assertEqual(spam.status_code, status.HTTP_201_CREATED)
        self.assertEqual(harassment.status_code, status.HTTP_201_CREATED)

        spam_report = CommunityReport.objects.get(pk=spam.data["id"])
        harassment_report = CommunityReport.objects.get(pk=harassment.data["id"])
        decision = self._remove(
            case=self._case(ModerationCase.SafetyTargetType.COMMENT),
            confirmed_report_ids=[harassment_report.pk],
        )

        self.comment.refresh_from_db()
        self.assertIsNotNone(self.comment.safety_removed_at)
        self.assertEqual(decision.target_type, CommunitySafetyDecision.TargetType.COMMENT)
        self.assertEqual(decision.target_id_snapshot, self.comment.pk)

        spam_outcome = CommunityReportOutcome.objects.get(
            safety_decision=decision,
            reporter=self.reporter_one,
        )
        harassment_outcome = CommunityReportOutcome.objects.get(
            safety_decision=decision,
            reporter=self.reporter_two,
        )
        self.assertEqual(
            spam_outcome.report_outcome,
            CommunityReportOutcome.ReportOutcome.NOT_CONFIRMED,
        )
        self.assertEqual(
            harassment_outcome.report_outcome,
            CommunityReportOutcome.ReportOutcome.CONFIRMED,
        )

        detail = self._client(self.unrelated).get(
            reverse("thread-detail", kwargs={"pk": self.thread.pk})
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        rendered_comment = next(
            item
            for item in detail.data["comments"]
            if str(item["id"]) == str(self.comment.pk)
        )
        self.assertTrue(rendered_comment["safety_removed"])
        self.assertEqual(rendered_comment["comment_text"], "")
        self.assertIsNone(rendered_comment["comment_rich"])

        reporter_one_components = calculate_trust_components(self.reporter_one)
        reporter_two_components = calculate_trust_components(self.reporter_two)
        owner_components = calculate_trust_components(self.comment_owner)
        self.assertEqual(reporter_one_components["validated_actions"], 0)
        self.assertEqual(reporter_two_components["validated_actions"], 1)
        self.assertEqual(owner_components["moderation_penalty"], 5.0)

    def test_evidence_removal_does_not_change_evidence_review_status(self):
        report_response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.EVIDENCE,
        )
        report = CommunityReport.objects.get(pk=report_response.data["id"])
        original_status = self.evidence.evidence_status

        decision = self._remove(
            case=self._case(ModerationCase.SafetyTargetType.EVIDENCE),
            confirmed_report_ids=[report.pk],
        )

        self.evidence.refresh_from_db()
        self.assertIsNotNone(self.evidence.safety_removed_at)
        self.assertEqual(self.evidence.evidence_status, original_status)
        self.assertEqual(decision.target_type, CommunitySafetyDecision.TargetType.EVIDENCE)

        detail = self._client(self.unrelated).get(
            reverse("thread-detail", kwargs={"pk": self.thread.pk})
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        ids = {str(item["id"]) for item in detail.data["evidence_submissions"]}
        self.assertNotIn(str(self.evidence.pk), ids)

        direct = self._client(self.unrelated).get(
            reverse("evidence-detail", kwargs={"pk": self.evidence.pk})
        )
        self.assertEqual(direct.status_code, status.HTTP_404_NOT_FOUND)

    def test_exact_target_and_parent_thread_mutations_are_frozen_during_review(self):
        response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        comment_delete = self._client(self.comment_owner).delete(
            reverse("comment-detail", kwargs={"pk": self.comment.pk})
        )
        thread_delete = self._client(self.thread_author).delete(
            reverse("thread-detail", kwargs={"pk": self.thread.pk})
        )

        self.assertEqual(comment_delete.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(thread_delete.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(ThreadComment.objects.filter(pk=self.comment.pk).exists())
        self.assertTrue(Thread.objects.filter(pk=self.thread.pk).exists())

    def test_dismissed_comment_case_keeps_comment_visible_and_reports_neutral(self):
        response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
        )
        report = CommunityReport.objects.get(pk=response.data["id"])
        case = self._case(ModerationCase.SafetyTargetType.COMMENT)
        self._claim(case)

        with self.captureOnCommitCallbacks(execute=True):
            resolution = self._client(self.moderator).post(
                reverse("safety_case_action", kwargs={"case_id": case.pk}),
                {"action": "DISMISS", "notes": ""},
                format="json",
            )

        self.assertEqual(resolution.status_code, status.HTTP_200_OK)
        self.comment.refresh_from_db()
        self.assertIsNone(self.comment.safety_removed_at)

        outcome = CommunityReportOutcome.objects.get(
            reporter=self.reporter_one,
            target_id_snapshot=self.comment.pk,
        )
        self.assertEqual(
            outcome.report_outcome,
            CommunityReportOutcome.ReportOutcome.NO_VIOLATION,
        )
        self.assertFalse(outcome.is_valid_report)
        self.assertEqual(
            calculate_trust_components(self.reporter_one)["validated_actions"],
            0,
        )

    def test_comment_reconsideration_reversal_restores_content_and_trust(self):
        response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
        )
        report = CommunityReport.objects.get(pk=response.data["id"])
        decision = self._remove(
            case=self._case(ModerationCase.SafetyTargetType.COMMENT),
            confirmed_report_ids=[report.pk],
        )

        self.assertEqual(
            calculate_trust_components(self.comment_owner)["moderation_penalty"],
            5.0,
        )
        self.assertEqual(
            calculate_trust_components(self.reporter_one)["validated_actions"],
            1,
        )

        request_response = self._client(self.comment_owner).post(
            reverse(
                "community_moderation_reconsideration",
                kwargs={"decision_id": decision.pk},
            ),
            {
                "request_statement": (
                    "The comment context was misunderstood and should be reviewed again."
                )
            },
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)

        case = self._case(ModerationCase.SafetyTargetType.COMMENT)
        self._claim(case, self.second_moderator)
        with self.captureOnCommitCallbacks(execute=True):
            reverse_response = self._client(self.second_moderator).post(
                reverse(
                    "safety_case_reconsideration_resolve",
                    kwargs={"case_id": case.pk},
                ),
                {
                    "outcome": CommunitySafetyReconsideration.Outcome.REVERSED,
                    "resolution_rationale": (
                        "The additional context does not meet the threshold for targeted abuse."
                    ),
                },
                format="json",
            )

        self.assertEqual(reverse_response.status_code, status.HTTP_200_OK)
        self.comment.refresh_from_db()
        self.assertIsNone(self.comment.safety_removed_at)

        historical = CommunityReportOutcome.objects.get(
            safety_decision=decision,
            reporter=self.reporter_one,
        )
        self.assertEqual(
            historical.report_outcome,
            CommunityReportOutcome.ReportOutcome.CONFIRMED,
        )
        self.assertTrue(historical.is_valid_report)

        self.assertEqual(
            calculate_trust_components(self.comment_owner)["moderation_penalty"],
            0.0,
        )
        self.assertEqual(
            calculate_trust_components(self.reporter_one)["validated_actions"],
            0,
        )

    def test_reporter_projection_hides_comment_owner_reconsideration_statement(self):
        response = self._report(
            reporter=self.reporter_one,
            target_type=CommunityReport.TargetType.COMMENT,
        )
        report = CommunityReport.objects.get(pk=response.data["id"])
        decision = self._remove(
            case=self._case(ModerationCase.SafetyTargetType.COMMENT),
            confirmed_report_ids=[report.pk],
        )

        request_statement = (
            "This owner-only reconsideration explanation must not be exposed to the reporter."
        )
        request_response = self._client(self.comment_owner).post(
            reverse(
                "community_moderation_reconsideration",
                kwargs={"decision_id": decision.pk},
            ),
            {"request_statement": request_statement},
            format="json",
        )
        self.assertEqual(request_response.status_code, status.HTTP_201_CREATED)

        reporter_outcome = self._client(self.reporter_one).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        owner_outcome = self._client(self.comment_owner).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )

        self.assertEqual(reporter_outcome.status_code, status.HTTP_200_OK)
        self.assertEqual(owner_outcome.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            "request_statement",
            reporter_outcome.data["reconsideration"],
        )
        self.assertEqual(
            owner_outcome.data["reconsideration"]["request_statement"],
            request_statement,
        )
        self.assertEqual(reporter_outcome.data["target"]["type"], "COMMENT")
