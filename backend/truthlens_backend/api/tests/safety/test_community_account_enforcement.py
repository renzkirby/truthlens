from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from api.community_account_enforcement_service import get_user_community_access
from api.models import (
    AccountabilityEvent,
    Claim,
    CommunityAccountEnforcement,
    CommunityAccountEnforcementReview,
    CommunityReport,
    CommunitySafetyDecision,
    ModerationCase,
    Notification,
    Organization,
    OrganizationMembership,
    Thread,
    ThreadComment,
    ThreadCommentLike,
    UserProfile,
)
from api.community_access_permissions import CanContributeToCommunity
from api.moderation_service import create_moderation_case
from api.throttles import (
    CommunityReportBurstRateThrottle,
    CommunityReportHourlyRateThrottle,
)
from api.trust_service import calculate_trust_components
from api import urls as api_urls
from api import views as api_views


@override_settings(COMMUNITY_ACCOUNT_ENFORCEMENT_ISSUANCE_ENABLED=True)
class CommunityAccountEnforcementTests(APITestCase):
    def setUp(self):
        self.author = self._user("account-enforcement-author")
        self.reporter = self._user("account-enforcement-reporter")
        self.unrelated = self._user("account-enforcement-unrelated")
        self.moderator = self._moderator("account-enforcement-moderator")
        self.other_moderator = self._moderator(
            "account-enforcement-other-moderator"
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

    def _reported_thread(self, suffix, *, author=None):
        author = author or self.author
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Account enforcement claim {suffix}.",
            verified_via=Claim.VerificationSource.PENDING,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=author,
            caption=f"Account enforcement discussion {suffix}.",
            status=Thread.Status.OPEN,
        )
        case = create_moderation_case(
            case_type=ModerationCase.CaseType.SAFETY,
            actor=self.reporter,
            source=ModerationCase.Source.USER_REPORT,
            thread=thread,
        )
        report = CommunityReport.objects.create(
            thread=thread,
            reporter=self.reporter,
            reason=CommunityReport.Reason.HARASSMENT,
            notes="Targeted abusive language requires Platform Safety review.",
        )
        return thread, case, report

    def _remove(self, suffix, *, author=None, moderator=None):
        moderator = moderator or self.moderator
        thread, case, report = self._reported_thread(suffix, author=author)
        client = self._client(moderator)

        claim = client.post(
            reverse("safety_case_claim", kwargs={"case_id": case.pk}),
            {},
            format="json",
        )
        self.assertEqual(claim.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("safety_case_action", kwargs={"case_id": case.pk}),
                {
                    "action": "REMOVE",
                    "notes": (
                        "The reviewed content contains targeted abuse that meets "
                        "the Community Guidelines threshold."
                    ),
                    "violation_code": "HARASSMENT_TARGETED_ABUSE",
                    "confirmed_report_ids": [str(report.pk)],
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        decision = CommunitySafetyDecision.objects.get(moderation_case=case)
        return thread, case, report, decision

    def _issue(
        self,
        case,
        *,
        action="TEMPORARY_RESTRICTION",
        duration_code="24_HOURS",
        moderator=None,
        user_rationale=None,
        internal_note="Internal Safety context for the account action.",
    ):
        moderator = moderator or self.moderator
        body = {
            "action": action,
            "user_rationale": user_rationale
            or (
                "This account action is based on the confirmed Community "
                "Guidelines violation and the reviewed context."
            ),
            "internal_note": internal_note,
        }
        if action == "TEMPORARY_RESTRICTION":
            body["duration_code"] = duration_code
        if action == "INDEFINITE_RESTRICTION":
            body["confirm_indefinite"] = True

        with self.captureOnCommitCallbacks(execute=True):
            return self._client(moderator).post(
                reverse(
                    "safety_case_account_enforcement",
                    kwargs={"case_id": case.pk},
                ),
                body,
                format="json",
            )

    def _request_account_review(self, enforcement, *, actor=None):
        actor = actor or self.author
        return self._client(actor).post(
            reverse(
                "community_account_enforcement_review",
                kwargs={"enforcement_id": enforcement.pk},
            ),
            {
                "request_statement": (
                    "The account-level consequence is disproportionate to the "
                    "context and should be reviewed separately."
                )
            },
            format="json",
        )

    def test_issuance_flag_off_blocks_new_actions_but_not_existing_access_state(self):
        _, case, _, _ = self._remove("flag")

        with override_settings(
            COMMUNITY_ACCOUNT_ENFORCEMENT_ISSUANCE_ENABLED=False
        ):
            blocked = self._issue(case, action="WARNING")

        self.assertEqual(blocked.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(CommunityAccountEnforcement.objects.exists())

        issued = self._issue(case)
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()

        with override_settings(
            COMMUNITY_ACCOUNT_ENFORCEMENT_ISSUANCE_ENABLED=False
        ):
            self.assertFalse(
                get_user_community_access(self.author)["can_contribute"]
            )
            lifted = self._client(self.moderator).post(
                reverse(
                    "safety_account_enforcement_lift",
                    kwargs={"enforcement_id": enforcement.pk},
                ),
                {
                    "rationale": (
                        "Platform Safety is ending this restriction early after "
                        "reviewing the operational circumstances."
                    )
                },
                format="json",
            )

        self.assertEqual(lifted.status_code, status.HTTP_200_OK)
        self.assertTrue(get_user_community_access(self.author)["can_contribute"])

    def test_warning_is_historical_only_and_does_not_change_trust(self):
        _, case, _, _ = self._remove("warning")
        trust_after_removal = calculate_trust_components(self.author)[
            "trust_score"
        ]

        response = self._issue(case, action="WARNING")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()
        self.assertEqual(
            enforcement.action,
            CommunityAccountEnforcement.Action.WARNING,
        )
        self.assertTrue(get_user_community_access(self.author)["can_contribute"])
        self.assertEqual(
            calculate_trust_components(self.author)["trust_score"],
            trust_after_removal,
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.author,
                notification_type=(
                    Notification.NotificationType.COMMUNITY_ACCOUNT_ENFORCEMENT
                ),
            ).count(),
            1,
        )

    def test_temporary_restriction_blocks_new_edits_but_keeps_read_report_and_withdrawal(self):
        other_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Other Community discussion.",
            verified_via=Claim.VerificationSource.PENDING,
        )
        other_thread = Thread.objects.create(
            claim=other_claim,
            author=self.unrelated,
            caption="Other Community discussion.",
            status=Thread.Status.OPEN,
        )
        own_comment = ThreadComment.objects.create(
            thread=other_thread,
            commenter=self.author,
            comment_text="Existing author comment that may be withdrawn.",
        )
        report_target = ThreadComment.objects.create(
            thread=other_thread,
            commenter=self.unrelated,
            comment_text="Reportable comment from another member.",
        )
        ThreadCommentLike.objects.create(
            comment=report_target,
            user=self.author,
        )

        _, case, _, _ = self._remove("permissions")
        issued = self._issue(case)
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)

        client = self._client(self.author)

        read = client.get(reverse("thread-list"))
        create_thread = client.post(reverse("thread-list"), {}, format="json")
        edit_comment = client.patch(
            reverse("comment-detail", kwargs={"pk": own_comment.pk}),
            {"comment_text": "Edited while restricted."},
            format="json",
        )
        create_evidence = client.post(
            reverse("evidence-list"),
            {},
            format="json",
        )
        create_vote = client.post(reverse("vote-list"), {}, format="json")
        report = client.post(
            reverse("community-report-list"),
            {
                "target_type": CommunityReport.TargetType.COMMENT,
                "thread_id": str(other_thread.pk),
                "comment_id": str(report_target.pk),
                "reason": CommunityReport.Reason.HARASSMENT,
                "notes": "This comment contains targeted abusive language.",
            },
            format="json",
        )
        unlike = client.delete(
            reverse("comment-like", kwargs={"pk": report_target.pk})
        )
        relike = client.post(
            reverse("comment-like", kwargs={"pk": report_target.pk}),
            {},
            format="json",
        )
        delete_comment = client.delete(
            reverse("comment-detail", kwargs={"pk": own_comment.pk})
        )

        self.assertEqual(read.status_code, status.HTTP_200_OK)
        for response in (
            create_thread,
            edit_comment,
            create_evidence,
            create_vote,
        ):
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(
                str(response.data["code"]),
                "COMMUNITY_CONTRIBUTION_RESTRICTED",
            )
        self.assertEqual(report.status_code, status.HTTP_201_CREATED)
        self.assertEqual(unlike.status_code, status.HTTP_200_OK)
        self.assertFalse(unlike.data["is_liked"])
        self.assertEqual(relike.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            str(relike.data["code"]),
            "COMMUNITY_CONTRIBUTION_RESTRICTED",
        )
        self.assertEqual(delete_comment.status_code, status.HTTP_204_NO_CONTENT)

    def test_restricted_user_can_unfollow_but_cannot_start_new_follow(self):
        self.unrelated.profile.followers.add(self.author)
        _, case, _, _ = self._remove("follow")
        self.assertEqual(self._issue(case).status_code, status.HTTP_201_CREATED)

        client = self._client(self.author)
        unfollow = client.post(
            f"/api/users/{self.unrelated.username}/follow/"
        )
        follow_again = client.post(
            f"/api/users/{self.unrelated.username}/follow/"
        )

        self.assertEqual(unfollow.status_code, status.HTTP_200_OK)
        self.assertFalse(unfollow.data["is_following"])
        self.assertEqual(follow_again.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            str(follow_again.data["code"]),
            "COMMUNITY_CONTRIBUTION_RESTRICTED",
        )

    def test_temporary_restriction_expires_at_server_boundary_without_task(self):
        _, case, _, _ = self._remove("expiry")
        response = self._issue(case)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()

        before = enforcement.restriction_ends_at - timedelta(microseconds=1)
        boundary = enforcement.restriction_ends_at

        with patch(
            "api.community_account_enforcement_service.timezone.now",
            return_value=before,
        ):
            self.assertFalse(
                get_user_community_access(self.author)["can_contribute"]
            )

        with patch(
            "api.community_account_enforcement_service.timezone.now",
            return_value=boundary,
        ):
            self.assertTrue(
                get_user_community_access(self.author)["can_contribute"]
            )

    def test_overlap_rules_reject_shorter_and_indefinite_supersedes_temporary(self):
        _, case_one, _, _ = self._remove("overlap-one")
        first = self._issue(case_one, duration_code="30_DAYS")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        first_enforcement = CommunityAccountEnforcement.objects.get(
            safety_decision__moderation_case=case_one
        )

        _, case_two, _, _ = self._remove("overlap-two")
        shorter = self._issue(case_two, duration_code="24_HOURS")
        self.assertEqual(shorter.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(
            CommunityAccountEnforcement.objects.filter(
                safety_decision__moderation_case=case_two
            ).exists()
        )

        indefinite = self._issue(
            case_two,
            action="INDEFINITE_RESTRICTION",
        )
        self.assertEqual(indefinite.status_code, status.HTTP_201_CREATED)

        first_enforcement.refresh_from_db()
        self.assertEqual(
            first_enforcement.revocation_reason,
            CommunityAccountEnforcement.RevocationReason.SUPERSEDED,
        )
        access = get_user_community_access(self.author)
        self.assertEqual(access["status"], "INDEFINITELY_RESTRICTED")

        _, case_three, _, _ = self._remove("overlap-three")
        duplicate_indefinite = self._issue(
            case_three,
            action="INDEFINITE_RESTRICTION",
        )
        self.assertEqual(
            duplicate_indefinite.status_code,
            status.HTTP_409_CONFLICT,
        )

    def test_one_safety_decision_cannot_issue_two_account_actions(self):
        _, case, _, _ = self._remove("duplicate")
        first = self._issue(case, action="WARNING")
        second = self._issue(case, action="WARNING")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(CommunityAccountEnforcement.objects.count(), 1)
        self.assertEqual(
            Notification.objects.filter(
                notification_type=(
                    Notification.NotificationType.COMMUNITY_ACCOUNT_ENFORCEMENT
                )
            ).count(),
            1,
        )

    def test_pending_content_reconsideration_blocks_account_issuance(self):
        _, case, _, decision = self._remove("pending-content-review")
        request = self._client(self.author).post(
            reverse(
                "community_moderation_reconsideration",
                kwargs={"decision_id": decision.pk},
            ),
            {
                "request_statement": (
                    "The content removal should be reconsidered because important "
                    "context was not considered in the original decision."
                )
            },
            format="json",
        )
        self.assertEqual(request.status_code, status.HTTP_201_CREATED)

        response = self._issue(case)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertFalse(CommunityAccountEnforcement.objects.exists())

    def test_self_review_requires_independence_override_when_other_reviewer_exists(self):
        _, case, _, _ = self._remove("independence")
        self.assertEqual(self._issue(case).status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()

        request = self._request_account_review(enforcement)
        self.assertEqual(request.status_code, status.HTTP_201_CREATED)
        review = CommunityAccountEnforcementReview.objects.get()

        no_override = self._client(self.moderator).post(
            reverse(
                "safety_account_enforcement_review_start",
                kwargs={"review_id": review.pk},
            ),
            {},
            format="json",
        )
        self.assertEqual(no_override.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("independence_override_rationale", no_override.data)

        with_override = self._client(self.moderator).post(
            reverse(
                "safety_account_enforcement_review_start",
                kwargs={"review_id": review.pk},
            ),
            {
                "independence_override_rationale": (
                    "Operational coverage requires the original reviewer to handle "
                    "this request despite another qualified reviewer being active."
                )
            },
            format="json",
        )
        self.assertEqual(with_override.status_code, status.HTTP_200_OK)

    def test_account_review_reversal_restores_access_but_not_content_or_trust_penalty(self):
        thread, case, _, _ = self._remove("review-reversal")
        trust_after_content_removal = calculate_trust_components(self.author)[
            "trust_score"
        ]
        self.assertEqual(self._issue(case).status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()

        self.assertEqual(
            self._request_account_review(enforcement).status_code,
            status.HTTP_201_CREATED,
        )
        review = CommunityAccountEnforcementReview.objects.get()

        start = self._client(self.other_moderator).post(
            reverse(
                "safety_account_enforcement_review_start",
                kwargs={"review_id": review.pk},
            ),
            {},
            format="json",
        )
        self.assertEqual(start.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            resolved = self._client(self.other_moderator).post(
                reverse(
                    "safety_account_enforcement_review_resolve",
                    kwargs={"review_id": review.pk},
                ),
                {
                    "outcome": "REVERSED",
                    "resolution_rationale": (
                        "The content removal remains valid, but the separate account "
                        "restriction was disproportionate to the reviewed context."
                    ),
                    "internal_note": "Independent proportionality review completed.",
                },
                format="json",
            )
        self.assertEqual(resolved.status_code, status.HTTP_200_OK)

        enforcement.refresh_from_db()
        thread.refresh_from_db()
        self.assertEqual(
            enforcement.revocation_reason,
            CommunityAccountEnforcement.RevocationReason.REVIEW_REVERSED,
        )
        self.assertTrue(get_user_community_access(self.author)["can_contribute"])
        self.assertEqual(thread.status, Thread.Status.REJECTED)
        self.assertEqual(
            calculate_trust_components(self.author)["trust_score"],
            trust_after_content_removal,
        )

    def test_phase_c_reversal_atomically_revokes_basis_and_moots_account_review(self):
        thread, case, _, decision = self._remove("basis-reversal")
        self.assertEqual(self._issue(case).status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()

        self.assertEqual(
            self._request_account_review(enforcement).status_code,
            status.HTTP_201_CREATED,
        )
        review = CommunityAccountEnforcementReview.objects.get()

        content_request = self._client(self.author).post(
            reverse(
                "community_moderation_reconsideration",
                kwargs={"decision_id": decision.pk},
            ),
            {
                "request_statement": (
                    "The content removal should be reversed because the full "
                    "discussion context changes the Safety finding."
                )
            },
            format="json",
        )
        self.assertEqual(content_request.status_code, status.HTTP_201_CREATED)

        claim = self._client(self.other_moderator).post(
            reverse("safety_case_claim", kwargs={"case_id": case.pk}),
            {},
            format="json",
        )
        self.assertEqual(claim.status_code, status.HTTP_200_OK)

        with self.captureOnCommitCallbacks(execute=True):
            reversed_response = self._client(self.other_moderator).post(
                reverse(
                    "safety_case_reconsideration_resolve",
                    kwargs={"case_id": case.pk},
                ),
                {
                    "outcome": "REVERSED",
                    "resolution_rationale": (
                        "The complete context does not support the original "
                        "Community Safety removal."
                    ),
                },
                format="json",
            )
        self.assertEqual(reversed_response.status_code, status.HTTP_200_OK)

        enforcement.refresh_from_db()
        review.refresh_from_db()
        thread.refresh_from_db()

        self.assertEqual(
            enforcement.revocation_reason,
            CommunityAccountEnforcement.RevocationReason.BASIS_REVERSED,
        )
        self.assertEqual(
            review.status,
            CommunityAccountEnforcementReview.Status.MOOT,
        )
        self.assertTrue(get_user_community_access(self.author)["can_contribute"])
        self.assertEqual(thread.status, Thread.Status.OPEN)

    def test_account_action_privacy_keeps_internal_note_and_owner_action_from_reporter(self):
        _, case, _, decision = self._remove("privacy")
        self.assertEqual(
            self._issue(
                case,
                internal_note=(
                    "Private Safety context includes information that must not be "
                    "projected to the affected user or reporter."
                ),
            ).status_code,
            status.HTTP_201_CREATED,
        )

        author_outcome = self._client(self.author).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        reporter_outcome = self._client(self.reporter).get(
            reverse(
                "community_moderation_outcome",
                kwargs={"decision_id": decision.pk},
            )
        )
        safety_collection = self._client(self.moderator).get(
            reverse("safety_account_enforcement_collection")
        )

        self.assertEqual(author_outcome.status_code, status.HTTP_200_OK)
        self.assertIn("account_enforcement", author_outcome.data)
        self.assertNotIn(
            "internal_note",
            author_outcome.data["account_enforcement"],
        )

        self.assertEqual(reporter_outcome.status_code, status.HTTP_200_OK)
        self.assertNotIn("account_enforcement", reporter_outcome.data)

        self.assertEqual(safety_collection.status_code, status.HTTP_200_OK)
        self.assertIn(
            "Private Safety context",
            safety_collection.data["results"][0]["internal_note"],
        )

    def test_seen_action_is_durable_in_standing_and_can_be_acknowledged(self):
        _, case, _, _ = self._remove("seen")
        self.assertEqual(self._issue(case, action="WARNING").status_code, 201)
        enforcement = CommunityAccountEnforcement.objects.get()

        hub_before = self._client(self.author).get(reverse("user_hub"))
        self.assertTrue(
            hub_before.data["community_standing"]["access"]["has_unseen_action"]
        )
        self.assertFalse(
            hub_before.data["community_standing"]["history"][0]["seen"]
        )

        seen = self._client(self.author).post(
            reverse(
                "community_account_enforcement_seen",
                kwargs={"enforcement_id": enforcement.pk},
            ),
            {},
            format="json",
        )
        self.assertEqual(seen.status_code, status.HTTP_200_OK)

        hub_after = self._client(self.author).get(reverse("user_hub"))
        self.assertFalse(
            hub_after.data["community_standing"]["access"]["has_unseen_action"]
        )
        self.assertTrue(
            hub_after.data["community_standing"]["history"][0]["seen"]
        )

    def test_partner_professional_authority_survives_community_restriction(self):
        organization = Organization.objects.create(
            name="Account Enforcement Partner",
            slug="account-enforcement-partner",
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
        )
        OrganizationMembership.objects.create(
            organization=organization,
            user=self.author,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )

        _, case, _, _ = self._remove("partner-authority")
        self.assertEqual(self._issue(case).status_code, status.HTTP_201_CREATED)

        response = self._client(self.author).get(reverse("auth_me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        identity = response.data["community_identity"]
        self.assertTrue(identity["can_participate"])
        self.assertFalse(identity["community_access"]["can_contribute"])
        self.assertEqual(
            identity["professional_identity"]["role"],
            OrganizationMembership.Role.LEAD_VERIFIER,
        )
        self.assertTrue(
            identity["professional_identity"]["authority_active"]
        )

    def test_warning_and_expired_temporary_actions_remain_reviewable(self):
        _, warning_case, _, _ = self._remove("review-warning")
        self.assertEqual(
            self._issue(warning_case, action="WARNING").status_code,
            status.HTTP_201_CREATED,
        )
        warning = CommunityAccountEnforcement.objects.get(
            safety_decision__moderation_case=warning_case
        )
        warning_review = self._request_account_review(warning)
        self.assertEqual(warning_review.status_code, status.HTTP_201_CREATED)

        _, temp_case, _, _ = self._remove("review-expired")
        self.assertEqual(
            self._issue(temp_case, duration_code="24_HOURS").status_code,
            status.HTTP_201_CREATED,
        )
        temporary = CommunityAccountEnforcement.objects.get(
            safety_decision__moderation_case=temp_case
        )
        CommunityAccountEnforcement.objects.filter(pk=temporary.pk).update(
            restriction_ends_at=timezone.now() - timedelta(seconds=1)
        )
        temporary.refresh_from_db()

        self.assertTrue(get_user_community_access(self.author)["can_contribute"])
        expired_review = self._request_account_review(temporary)
        self.assertEqual(expired_review.status_code, status.HTTP_201_CREATED)

    def test_router_community_mutations_explicitly_apply_contribution_policy(self):
        exempt_viewsets = {api_views.CommunityReportViewSet}
        governed = []

        for _prefix, viewset, _basename in api_urls.router.registry:
            permissions = set(getattr(viewset, "permission_classes", ()))
            if api_views.CanParticipateInCommunity not in permissions:
                continue
            governed.append(viewset)
            if viewset in exempt_viewsets:
                self.assertNotIn(CanContributeToCommunity, permissions)
            else:
                self.assertIn(
                    CanContributeToCommunity,
                    permissions,
                    msg=(
                        f"{viewset.__name__} participates in Community mutations "
                        "but does not declare the contribution-access policy."
                    ),
                )

        self.assertIn(api_views.ThreadViewSet, governed)
        self.assertIn(api_views.ThreadCommentViewSet, governed)
        self.assertIn(api_views.EvidenceSubmissionViewSet, governed)
        self.assertIn(api_views.VoteViewSet, governed)
        self.assertIn(api_views.CommunityReportViewSet, governed)

    def test_report_throttle_limits_post_burst_without_blocking_report_history_reads(self):
        cache.clear()
        original_burst = CommunityReportBurstRateThrottle.THROTTLE_RATES
        original_hourly = CommunityReportHourlyRateThrottle.THROTTLE_RATES
        CommunityReportBurstRateThrottle.THROTTLE_RATES = {
            **(original_burst or {}),
            "community_report_burst": "2/minute",
        }
        CommunityReportHourlyRateThrottle.THROTTLE_RATES = {
            **(original_hourly or {}),
            "community_report_hour": "100/hour",
        }

        try:
            claim = Claim.objects.create(
                claim_type=Claim.ClaimType.TEXT,
                context_text="Report throttle target.",
                verified_via=Claim.VerificationSource.PENDING,
            )
            thread = Thread.objects.create(
                claim=claim,
                author=self.unrelated,
                caption="Report throttle discussion.",
                status=Thread.Status.OPEN,
            )
            target = ThreadComment.objects.create(
                thread=thread,
                commenter=self.unrelated,
                comment_text="Report throttle comment.",
            )
            payload = {
                "target_type": CommunityReport.TargetType.COMMENT,
                "thread_id": str(thread.pk),
                "comment_id": str(target.pk),
                "reason": CommunityReport.Reason.HARASSMENT,
                "notes": "Repeated report request used only for throttle testing.",
            }
            client = self._client(self.author)

            first = client.post(
                reverse("community-report-list"),
                payload,
                format="json",
            )
            duplicate = client.post(
                reverse("community-report-list"),
                payload,
                format="json",
            )
            throttled = client.post(
                reverse("community-report-list"),
                payload,
                format="json",
            )
            history = client.get(reverse("community-report-list"))

            self.assertEqual(first.status_code, status.HTTP_201_CREATED)
            self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(
                throttled.status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
            )
            self.assertIn("Retry-After", throttled)
            self.assertEqual(history.status_code, status.HTTP_200_OK)
        finally:
            CommunityReportBurstRateThrottle.THROTTLE_RATES = original_burst
            CommunityReportHourlyRateThrottle.THROTTLE_RATES = original_hourly
            cache.clear()

    def test_safety_audit_records_account_events_without_exposing_user_request_as_platform_authority(self):
        _, case, _, _ = self._remove("audit")
        self.assertEqual(self._issue(case).status_code, status.HTTP_201_CREATED)
        enforcement = CommunityAccountEnforcement.objects.get()
        self.assertEqual(
            self._request_account_review(enforcement).status_code,
            status.HTTP_201_CREATED,
        )

        issue_event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.COMMUNITY_RESTRICTION_ISSUED
            )
        )
        request_event = AccountabilityEvent.objects.get(
            action_type=(
                AccountabilityEvent.ActionType.COMMUNITY_ENFORCEMENT_REVIEW_SUBMITTED
            )
        )

        self.assertEqual(
            issue_event.authority_scope,
            AccountabilityEvent.AuthorityScope.PLATFORM,
        )
        self.assertEqual(
            request_event.authority_scope,
            AccountabilityEvent.AuthorityScope.PERSONAL,
        )
