from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.models import (
    Claim,
    CommunitySafetyDecision,
    CommunitySafetyReconsideration,
    FlagResolutionLog,
    ModerationCase,
    Notification,
    Thread,
    ThreadFlag,
    UserProfile,
)
from api.moderation_service import create_moderation_case
from api.trust_service import calculate_trust_components


class CommunitySafetyReconsiderationApiTests(APITestCase):
    def setUp(self):
        self.author = self._user("reconsider-author")
        self.reporter_one = self._user("reconsider-reporter-one")
        self.reporter_two = self._user("reconsider-reporter-two")
        self.unrelated = self._user("reconsider-unrelated")
        self.moderator = self._moderator("reconsider-moderator")
        self.other_moderator = self._moderator("reconsider-other-moderator")

        self.thread, self.case, self.report_one, self.report_two = self._reported_thread(
            "Reconsideration fixture",
            thread_status=Thread.Status.OPEN,
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
    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _reported_thread(self, caption, *, thread_status):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Claim context for {caption}.",
            verified_via=Claim.VerificationSource.PENDING,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=caption,
            status=thread_status,
        )
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.reporter_one,
            source=ModerationCase.Source.USER_REPORT,
            thread=thread,
        )
        report_one = ThreadFlag.objects.create(
            thread=thread,
            flagged_by=self.reporter_one,
            reason=ThreadFlag.Reason.SPAM,
            notes="Promotional repetition.",
        )
        report_two = ThreadFlag.objects.create(
            thread=thread,
            flagged_by=self.reporter_two,
            reason=ThreadFlag.Reason.HARASSMENT,
            notes="Targeted abusive language.",
        )
        return thread, case, report_one, report_two

    def _claim(self, case, moderator=None):
        moderator = moderator or self.moderator
        return self._client_for(moderator).post(
            reverse("safety_case_claim", kwargs={"case_id": case.pk}),
            {},
            format="json",
        )

    def _remove(self, *, case=None, report_to_confirm=None, moderator=None):
        case = case or self.case
        report_to_confirm = report_to_confirm or self.report_two
        moderator = moderator or self.moderator

        claim_response = self._claim(case, moderator)
        self.assertEqual(claim_response.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(moderator).post(
                reverse("safety_case_action", kwargs={"case_id": case.pk}),
                {
                    "action": "REMOVE",
                    "notes": "The content meets the targeted harassment rule.",
                    "violation_code": "HARASSMENT_TARGETED_ABUSE",
                    "confirmed_report_ids": [str(report_to_confirm.pk)],
                },
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        decision = CommunitySafetyDecision.objects.get(moderation_case=case)
        return decision

    def _request(self, decision, *, actor=None, statement=None):
        actor = actor or self.author
        statement = statement or (
            "The context was misunderstood and I would like Platform Safety "
            "to review the removal again."
        )
        return self._client_for(actor).post(
            reverse(
                "community_moderation_reconsideration",
                kwargs={"decision_id": decision.pk},
            ),
            {"request_statement": statement},
            format="json",
        )

    def _resolve(self, case, *, outcome, moderator=None, rationale=None):
        moderator = moderator or self.other_moderator
        rationale = rationale or (
            "The original decision was reviewed again against the Community "
            "Guidelines and the available context."
        )

        claim_response = self._claim(case, moderator)
        self.assertEqual(claim_response.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            return self._client_for(moderator).post(
                reverse(
                    "safety_case_reconsideration_resolve",
                    kwargs={"case_id": case.pk},
                ),
                {
                    "outcome": outcome,
                    "resolution_rationale": rationale,
                },
                format="json",
            )

    def test_author_request_reopens_case_without_restoring_content(self):
        decision = self._remove()

        response = self._request(decision)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.case.refresh_from_db()
        self.thread.refresh_from_db()
        reconsideration = CommunitySafetyReconsideration.objects.get(
            safety_decision=decision,
        )

        self.assertEqual(self.case.status, ModerationCase.Status.REOPENED)
        self.assertIsNone(self.case.assigned_to_id)
        self.assertEqual(self.thread.status, Thread.Status.REJECTED)
        self.assertEqual(reconsideration.requested_by, self.author)
        self.assertEqual(reconsideration.outcome, "")
        self.assertEqual(response.data["reconsideration"]["status"], "SUBMITTED")
        self.assertIn(
            "misunderstood",
            response.data["reconsideration"]["request_statement"],
        )
        self.assertFalse(response.data["can_request_reconsideration"])

    def test_only_author_can_request_and_request_is_single_use(self):
        decision = self._remove()

        unrelated = self._request(decision, actor=self.unrelated)
        self.assertEqual(unrelated.status_code, status.HTTP_404_NOT_FOUND)

        first = self._request(decision)
        second = self._request(decision)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            CommunitySafetyReconsideration.objects.filter(
                safety_decision=decision,
            ).count(),
            1,
        )

    def test_historical_removal_without_complete_snapshot_is_not_reconsiderable(self):
        decision = self._remove()
        CommunitySafetyDecision.objects.filter(pk=decision.pk).update(
            restoration_snapshot_complete=False,
        )
        decision.refresh_from_db()

        outcome_response = self._client_for(self.author).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        request_response = self._request(decision)

        self.assertEqual(outcome_response.status_code, status.HTTP_200_OK)
        self.assertFalse(outcome_response.data["can_request_reconsideration"])
        self.assertEqual(request_response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn(
            "historical removal",
            request_response.data["detail"].lower(),
        )
        self.assertFalse(
            CommunitySafetyReconsideration.objects.filter(
                safety_decision=decision,
            ).exists()
        )

    def test_request_validation_is_simple_and_bounded(self):
        decision = self._remove()
        client = self._client_for(self.author)
        url = reverse(
            "community_moderation_reconsideration",
            kwargs={"decision_id": decision.pk},
        )

        too_short = client.post(
            url,
            {"request_statement": "Too short"},
            format="json",
        )
        unknown_field = client.post(
            url,
            {
                "request_statement": (
                    "This is long enough to be a valid request statement."
                ),
                "extra": "not supported",
            },
            format="json",
        )

        self.assertEqual(too_short.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(unknown_field.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            CommunitySafetyReconsideration.objects.filter(
                safety_decision=decision,
            ).exists()
        )

    def test_dismissed_decision_cannot_be_reconsidered(self):
        claim_response = self._claim(self.case, self.moderator)
        self.assertEqual(claim_response.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            dismiss_response = self._client_for(self.moderator).post(
                reverse("safety_case_action", kwargs={"case_id": self.case.pk}),
                {
                    "action": "DISMISS",
                },
                format="json",
            )
        self.assertEqual(dismiss_response.status_code, status.HTTP_200_OK)

        decision = CommunitySafetyDecision.objects.get(moderation_case=self.case)
        response = self._request(decision)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(
            CommunitySafetyReconsideration.objects.filter(
                safety_decision=decision,
            ).exists()
        )

    def test_reconsideration_must_be_claimed_before_resolution(self):
        decision = self._remove()
        self._request(decision)

        response = self._client_for(self.other_moderator).post(
            reverse(
                "safety_case_reconsideration_resolve",
                kwargs={"case_id": self.case.pk},
            ),
            {
                "outcome": "UPHELD",
                "resolution_rationale": (
                    "The reconsideration cannot be resolved before a reviewer "
                    "claims the reopened Safety case."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        reconsideration = CommunitySafetyReconsideration.objects.get(
            safety_decision=decision,
        )
        self.assertEqual(reconsideration.outcome, "")

    def test_original_qualified_reviewer_may_resolve_reconsideration(self):
        decision = self._remove(moderator=self.moderator)
        self._request(decision)

        response = self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.UPHELD,
            moderator=self.moderator,
            rationale=(
                "A second review of the context still supports the original "
                "Community Guidelines finding."
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        reconsideration = CommunitySafetyReconsideration.objects.get(
            safety_decision=decision,
        )
        self.assertEqual(
            reconsideration.outcome,
            CommunitySafetyReconsideration.Outcome.UPHELD,
        )
        self.assertEqual(reconsideration.reviewed_by, self.moderator)

    def test_normal_safety_actions_are_blocked_during_reconsideration(self):
        decision = self._remove()
        self._request(decision)
        self._claim(self.case, self.other_moderator)

        response = self._client_for(self.other_moderator).post(
            reverse("safety_case_action", kwargs={"case_id": self.case.pk}),
            {
                "action": "DISMISS",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("reconsideration", response.data["detail"].lower())

    def test_upheld_reconsideration_preserves_original_enforcement_and_history(self):
        decision = self._remove()
        original_log = FlagResolutionLog.objects.get(
            safety_decision=decision,
            flagged_by=self.reporter_two,
        )
        reporter_trust_after_removal = calculate_trust_components(
            self.reporter_two
        )["trust_score"]
        author_trust_after_removal = calculate_trust_components(
            self.author
        )["trust_score"]

        self._request(decision)
        response = self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.UPHELD,
            rationale=(
                "The additional context does not change the original finding "
                "of targeted abusive conduct."
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thread.refresh_from_db()
        self.case.refresh_from_db()
        decision.refresh_from_db()
        original_log.refresh_from_db()
        reconsideration = CommunitySafetyReconsideration.objects.get(
            safety_decision=decision,
        )

        self.assertEqual(self.thread.status, Thread.Status.REJECTED)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(
            self.case.resolution_code,
            "RECONSIDERATION_UPHELD",
        )
        self.assertEqual(decision.action, CommunitySafetyDecision.Action.REMOVE)
        self.assertEqual(
            original_log.report_outcome,
            FlagResolutionLog.ReportOutcome.CONFIRMED,
        )
        self.assertTrue(original_log.is_valid_report)
        self.assertEqual(
            reconsideration.outcome,
            CommunitySafetyReconsideration.Outcome.UPHELD,
        )
        self.assertEqual(
            calculate_trust_components(self.reporter_two)["trust_score"],
            reporter_trust_after_removal,
        )
        self.assertEqual(
            calculate_trust_components(self.author)["trust_score"],
            author_trust_after_removal,
        )

    def test_reversal_restores_exact_pre_removal_status_and_corrects_trust(self):
        decision = self._remove()
        self.assertEqual(
            decision.pre_removal_thread_status,
            Thread.Status.OPEN,
        )

        self.assertEqual(
            calculate_trust_components(self.author)["moderation_penalty"],
            5.0,
        )
        self.assertGreater(
            calculate_trust_components(self.reporter_two)["trust_score"],
            50.0,
        )

        self._request(decision)
        response = self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.REVERSED,
            rationale=(
                "The additional context shows that the content did not meet "
                "the threshold for targeted abuse."
            ),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.thread.refresh_from_db()
        self.case.refresh_from_db()
        decision.refresh_from_db()
        confirmed_log = FlagResolutionLog.objects.get(
            safety_decision=decision,
            flagged_by=self.reporter_two,
        )

        self.assertEqual(self.thread.status, Thread.Status.OPEN)
        self.assertIsNone(self.thread.moderated_by_id)
        self.assertIsNone(self.thread.moderated_at)
        self.assertIsNone(self.thread.moderator_notes)
        self.assertEqual(self.case.status, ModerationCase.Status.RESOLVED)
        self.assertEqual(
            self.case.resolution_code,
            "RECONSIDERATION_REVERSED",
        )

        # Historical facts remain unchanged.
        self.assertEqual(decision.action, CommunitySafetyDecision.Action.REMOVE)
        self.assertEqual(
            confirmed_log.report_outcome,
            FlagResolutionLog.ReportOutcome.CONFIRMED,
        )
        self.assertTrue(confirmed_log.is_valid_report)

        # Current reputation effects are corrected from canonical history.
        author_components = calculate_trust_components(self.author)
        reporter_components = calculate_trust_components(self.reporter_two)
        self.assertEqual(author_components["moderation_penalty"], 0.0)
        self.assertEqual(author_components["trust_score"], 50.0)
        self.assertEqual(reporter_components["resolved_actions"], 0)
        self.assertEqual(reporter_components["validated_actions"], 0)
        self.assertEqual(reporter_components["trust_score"], 50.0)

    def test_reversal_restores_closed_thread_and_prior_moderation_metadata(self):
        thread, case, _, report_two = self._reported_thread(
            "Originally closed discussion",
            thread_status=Thread.Status.CLOSED,
        )
        prior_moderated_at = timezone.now()
        prior_notes = "Prior professional adjudication context."
        thread.moderated_by = self.other_moderator
        thread.moderated_at = prior_moderated_at
        thread.moderator_notes = prior_notes
        thread.save(
            update_fields=[
                "moderated_by",
                "moderated_at",
                "moderator_notes",
            ]
        )

        decision = self._remove(
            case=case,
            report_to_confirm=report_two,
        )
        self.assertEqual(
            decision.pre_removal_thread_status,
            Thread.Status.CLOSED,
        )
        self.assertEqual(
            decision.pre_removal_moderated_by,
            self.other_moderator,
        )
        self.assertEqual(
            decision.pre_removal_moderated_at,
            prior_moderated_at,
        )
        self.assertEqual(
            decision.pre_removal_moderator_notes,
            prior_notes,
        )

        self._request(decision)
        response = self._resolve(
            case,
            outcome=CommunitySafetyReconsideration.Outcome.REVERSED,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        thread.refresh_from_db()
        self.assertEqual(thread.status, Thread.Status.CLOSED)
        self.assertEqual(thread.moderated_by, self.other_moderator)
        self.assertEqual(thread.moderated_at, prior_moderated_at)
        self.assertEqual(thread.moderator_notes, prior_notes)

    def test_reporter_projection_hides_author_request_and_reflects_reversal(self):
        decision = self._remove()
        self._request(
            decision,
            statement=(
                "The author is providing additional context that should not "
                "be exposed to the users who submitted reports."
            ),
        )

        pending_reporter = self._client_for(self.reporter_two).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        self.assertEqual(pending_reporter.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            "request_statement",
            pending_reporter.data["reconsideration"],
        )

        self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.REVERSED,
        )

        reporter = self._client_for(self.reporter_two).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        author = self._client_for(self.author).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        unrelated = self._client_for(self.unrelated).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )

        self.assertEqual(reporter.status_code, status.HTTP_200_OK)
        self.assertEqual(author.status_code, status.HTTP_200_OK)
        self.assertEqual(unrelated.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            reporter.data["reconsideration"]["outcome"],
            "REVERSED",
        )
        self.assertFalse(reporter.data["report"]["counts_toward_reputation"])
        self.assertNotIn(
            "request_statement",
            reporter.data["reconsideration"],
        )
        self.assertIn(
            "request_statement",
            author.data["reconsideration"],
        )

    def test_reversal_notifies_author_and_only_reporters_whose_credit_changes(self):
        decision = self._remove()

        # Ignore the original removal notifications; this test is only about
        # the update generated by the reconsideration result.
        Notification.objects.all().delete()

        self._request(decision)
        response = self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.REVERSED,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        author_notifications = Notification.objects.filter(
            recipient=self.author,
            title="Your discussion was restored",
        )
        confirmed_reporter_notifications = Notification.objects.filter(
            recipient=self.reporter_two,
            title="Moderation decision updated",
        )
        neutral_reporter_notifications = Notification.objects.filter(
            recipient=self.reporter_one,
            title="Moderation decision updated",
        )

        self.assertEqual(author_notifications.count(), 1)
        self.assertEqual(confirmed_reporter_notifications.count(), 1)
        self.assertEqual(neutral_reporter_notifications.count(), 0)

    def test_removed_thread_cannot_be_re_reported_but_restored_thread_can(self):
        decision = self._remove()

        removed_response = self._client_for(self.unrelated).post(
            reverse("thread-flag-list"),
            {
                "thread_id": str(self.thread.pk),
                "reason": ThreadFlag.Reason.OTHER,
                "notes": "Direct API report against removed content.",
            },
            format="json",
        )
        self.assertEqual(removed_response.status_code, status.HTTP_404_NOT_FOUND)

        self._request(decision)
        self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.REVERSED,
        )

        restored_response = self._client_for(self.unrelated).post(
            reverse("thread-flag-list"),
            {
                "thread_id": str(self.thread.pk),
                "reason": ThreadFlag.Reason.OTHER,
                "notes": "A new concern after the discussion was restored.",
            },
            format="json",
        )

        self.assertEqual(restored_response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ModerationCase.objects.filter(
                thread=self.thread,
                case_type=ModerationCase.CaseType.SAFETY,
                status__in=[
                    ModerationCase.Status.OPEN,
                    ModerationCase.Status.IN_REVIEW,
                    ModerationCase.Status.ESCALATED,
                    ModerationCase.Status.REOPENED,
                ],
            ).exists()
        )

    def test_second_reconsideration_resolution_is_rejected(self):
        decision = self._remove()
        self._request(decision)
        first = self._resolve(
            self.case,
            outcome=CommunitySafetyReconsideration.Outcome.UPHELD,
        )
        self.assertEqual(first.status_code, status.HTTP_200_OK)

        second = self._client_for(self.other_moderator).post(
            reverse(
                "safety_case_reconsideration_resolve",
                kwargs={"case_id": self.case.pk},
            ),
            {
                "outcome": "REVERSED",
                "resolution_rationale": (
                    "This second attempt must not mutate the resolved outcome."
                ),
            },
            format="json",
        )

        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        reconsideration = CommunitySafetyReconsideration.objects.get(
            safety_decision=decision,
        )
        self.assertEqual(
            reconsideration.outcome,
            CommunitySafetyReconsideration.Outcome.UPHELD,
        )
