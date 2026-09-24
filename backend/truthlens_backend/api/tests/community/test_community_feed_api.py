from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.test import APIClient

from api.adjudication_service import (
    ensure_adjudication_case,
    issue_adjudication_decision,
)
from api.models import (
    AdjudicationDecision,
    Claim,
    EvidenceSubmission,
    Organization,
    OrganizationMembership,
    Thread,
    VerificationAssignment,
)


class CommunityFeedApiTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="community-feed-author",
            email="feed-author@example.com",
            password="test-password",
        )
        self.reviewer = User.objects.create_user(
            username="community-feed-reviewer",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Community Feed Review Partner",
            slug="community-feed-review-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
            public_logo_enabled=True,
            logo_url="https://example.com/community-feed-review-partner.png",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.reviewer,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.author)
        self.url = reverse("thread-list")

    def _create_thread(
        self,
        label,
        *,
        claim_type=Claim.ClaimType.TEXT,
        ai_verdict=AdjudicationDecision.Verdict.UNVERIFIED,
        status_value=Thread.Status.OPEN,
    ):
        claim = Claim.objects.create(
            claim_type=claim_type,
            context_text=f"Claim context: {label}",
            ai_verdict=ai_verdict,
            ai_summary=f"AI-assisted summary: {label}",
            consensus_score=72,
            source_link="https://example.com/source",
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=f"Thread caption: {label}",
            status=status_value,
        )
        return claim, thread

    def _issue_human_decision(self, claim, thread):
        EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.author,
            evidence_caption="Reviewed source evidence.",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        VerificationAssignment.objects.create(
            claim=claim,
            organization=self.organization,
            claimed_by=self.reviewer,
            status=VerificationAssignment.Status.ACTIVE,
        )
        case = ensure_adjudication_case(
            claim=claim,
            actor=self.reviewer,
            organization=self.organization,
        )
        result = issue_adjudication_decision(
            case_id=case.id,
            organization_id=self.organization.id,
            actor=self.reviewer,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=claim.context_text,
            rationale="A human adjudicator reviewed the available evidence.",
            expected_revision=0,
        )

        return result["decision"]

    @staticmethod
    def _result_ids(response):
        return [item["id"] for item in response.data["results"]]

    def test_default_ordering_is_newest_first(self):
        _old_claim, old_thread = self._create_thread("older")
        _new_claim, new_thread = self._create_thread("newer")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._result_ids(response),
            [str(new_thread.id), str(old_thread.id)],
        )

    def test_oldest_ordering(self):
        _old_claim, old_thread = self._create_thread("older")
        _new_claim, new_thread = self._create_thread("newer")

        response = self.client.get(self.url, {"sort": "oldest"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._result_ids(response),
            [str(old_thread.id), str(new_thread.id)],
        )

    def test_search_matches_thread_and_claim_content(self):
        _matching_claim, matching_thread = self._create_thread("aurora signal")
        self._create_thread("unrelated topic")

        response = self.client.get(self.url, {"search": "aurora"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(matching_thread.id)])

    def test_claim_type_filter_includes_video(self):
        _video_claim, video_thread = self._create_thread(
            "video claim",
            claim_type=Claim.ClaimType.VIDEO,
        )
        self._create_thread("text claim", claim_type=Claim.ClaimType.TEXT)

        response = self.client.get(
            self.url,
            {"claim_type": Claim.ClaimType.VIDEO},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(video_thread.id)])

    def test_invalid_claim_type_returns_controlled_bad_request(self):
        response = self.client.get(self.url, {"claim_type": "AUDIO"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("claim_type", response.data)

    def test_assessment_source_human_uses_attributable_provenance(self):
        human_claim, human_thread = self._create_thread("human reviewed")
        decision = self._issue_human_decision(human_claim, human_thread)
        self._create_thread("AI only")

        response = self.client.get(self.url, {"assessment_source": "human"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(human_thread.id)])
        human_verdict = response.data["results"][0]["claim"]["human_verdict"]
        self.assertEqual(human_verdict["verdict"], decision.verdict)
        self.assertEqual(
            parse_datetime(human_verdict["reviewed_at"]),
            decision.decided_at,
        )
        self.assertEqual(
            human_verdict["organization"],
            {
                "id": str(self.organization.id),
                "name": self.organization.name,
                "slug": self.organization.slug,
                "logo_url": self.organization.logo_url,
            },
        )

    def test_human_verdict_logo_requires_public_logo_permission(self):
        self.organization.public_logo_enabled = False
        self.organization.save(update_fields=["public_logo_enabled"])
        claim, thread = self._create_thread("logo disabled")
        self._issue_human_decision(claim, thread)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        organization = response.data["results"][0]["claim"]["human_verdict"][
            "organization"
        ]
        self.assertEqual(organization["name"], self.organization.name)
        self.assertIsNone(organization["logo_url"])

    def test_non_public_adjudicating_organization_is_not_exposed(self):
        self.organization.public_profile_enabled = False
        self.organization.save(update_fields=["public_profile_enabled"])
        claim, thread = self._create_thread("private organization")
        decision = self._issue_human_decision(claim, thread)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        human_verdict = response.data["results"][0]["claim"]["human_verdict"]
        self.assertEqual(human_verdict["verdict"], decision.verdict)
        self.assertIsNone(human_verdict["organization"])

    def test_non_active_partner_organization_is_not_exposed(self):
        claim, thread = self._create_thread("suspended partner")
        self._issue_human_decision(claim, thread)

        for partner_status in (
            Organization.PartnerStatus.SUSPENDED,
            Organization.PartnerStatus.NONE,
            Organization.PartnerStatus.FORMER,
        ):
            with self.subTest(partner_status=partner_status):
                self.organization.partner_status = partner_status
                self.organization.save(update_fields=["partner_status"])

                response = self.client.get(self.url)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIsNone(
                    response.data["results"][0]["claim"]["human_verdict"][
                        "organization"
                    ]
                )

    def test_unverified_partner_organization_is_not_exposed(self):
        claim, thread = self._create_thread("unverified partner")
        self._issue_human_decision(claim, thread)
        self.organization.verification_status = (
            Organization.VerificationStatus.UNVERIFIED
        )
        self.organization.save(update_fields=["verification_status"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(
            response.data["results"][0]["claim"]["human_verdict"]["organization"]
        )

    def test_canonical_review_does_not_fall_back_to_decision_organization(self):
        claim, thread = self._create_thread("canonical organization removed")
        decision = self._issue_human_decision(claim, thread)
        self.assertEqual(decision.organization_id, self.organization.id)
        decision.moderation_case.organization = None
        decision.moderation_case.save(update_fields=["organization"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        human_verdict = response.data["results"][0]["claim"]["human_verdict"]
        self.assertEqual(human_verdict["verdict"], decision.verdict)
        self.assertEqual(
            parse_datetime(human_verdict["reviewed_at"]),
            decision.decided_at,
        )
        self.assertIsNone(human_verdict["organization"])

    def test_attributable_legacy_review_uses_decision_organization(self):
        claim, thread = self._create_thread("legacy review")
        thread.moderated_by = self.reviewer
        thread.moderator_verdict = AdjudicationDecision.Verdict.FACT
        thread.save(update_fields=["moderated_by", "moderator_verdict"])
        decision = AdjudicationDecision.objects.create(
            claim=claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=claim.context_text,
            rationale="Historical human review with attributable provenance.",
            decided_by=self.reviewer,
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        human_verdict = response.data["results"][0]["claim"]["human_verdict"]
        self.assertEqual(human_verdict["verdict"], decision.verdict)
        self.assertEqual(
            parse_datetime(human_verdict["reviewed_at"]),
            decision.decided_at,
        )
        self.assertEqual(
            human_verdict["organization"],
            {
                "id": str(self.organization.id),
                "name": self.organization.name,
                "slug": self.organization.slug,
                "logo_url": self.organization.logo_url,
            },
        )
        self.assertEqual(
            set(human_verdict),
            {"verdict", "reviewed_at", "organization"},
        )
        self.assertEqual(
            set(human_verdict["organization"]),
            {"id", "name", "slug", "logo_url"},
        )

    def test_ai_only_claim_has_no_human_verdict(self):
        self._create_thread("AI only projection")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["results"][0]["claim"]["human_verdict"])

    def test_human_verdict_projection_contains_only_public_safe_fields(self):
        claim, thread = self._create_thread("public-safe projection")
        self._issue_human_decision(claim, thread)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        human_verdict = response.data["results"][0]["claim"]["human_verdict"]
        self.assertEqual(
            set(human_verdict),
            {"verdict", "reviewed_at", "organization"},
        )
        self.assertEqual(
            set(human_verdict["organization"]),
            {"id", "name", "slug", "logo_url"},
        )
        self.assertNotIn("reviewer", human_verdict)
        self.assertNotIn("email", human_verdict["organization"])
        self.assertNotIn("verification_status", human_verdict["organization"])
        self.assertNotIn("partner_status", human_verdict["organization"])

    def test_assessment_source_ai_excludes_only_attributable_human_reviews(self):
        human_claim, human_thread = self._create_thread("human reviewed")
        self._issue_human_decision(human_claim, human_thread)
        unattributed_claim, unattributed_thread = self._create_thread(
            "unattributed cache"
        )
        Claim.objects.filter(pk=unattributed_claim.pk).update(
            final_verdict=AdjudicationDecision.Verdict.FAKE
        )
        AdjudicationDecision.objects.create(
            claim=unattributed_claim,
            verdict=AdjudicationDecision.Verdict.FAKE,
            canonical_claim=unattributed_claim.context_text,
            rationale="Stored without a canonical adjudication case.",
            decided_by=self.reviewer,
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.HUMAN_REVIEW,
        )
        _ai_claim, ai_thread = self._create_thread("AI only")

        response = self.client.get(self.url, {"assessment_source": "ai"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = set(self._result_ids(response))
        self.assertNotIn(str(human_thread.id), result_ids)
        self.assertEqual(
            result_ids,
            {str(unattributed_thread.id), str(ai_thread.id)},
        )
        unattributed_item = next(
            item
            for item in response.data["results"]
            if item["id"] == str(unattributed_thread.id)
        )
        self.assertIsNone(unattributed_item["claim"]["human_verdict"])

    def test_legacy_thread_moderator_fields_alone_do_not_count_as_human_review(self):
        _claim, thread = self._create_thread("legacy moderator fields only")
        thread.moderator_verdict = AdjudicationDecision.Verdict.FACT
        thread.moderated_by = self.reviewer
        thread.save(update_fields=["moderator_verdict", "moderated_by"])

        human_response = self.client.get(
            self.url,
            {"assessment_source": "human"},
        )
        ai_response = self.client.get(
            self.url,
            {"assessment_source": "ai"},
        )

        self.assertEqual(human_response.status_code, status.HTTP_200_OK)
        self.assertEqual(human_response.data["results"], [])
        self.assertEqual(ai_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(ai_response), [str(thread.id)])

    def test_invalid_assessment_source_returns_controlled_bad_request(self):
        response = self.client.get(self.url, {"assessment_source": "pending"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assessment_source", response.data)

    def test_rejected_threads_remain_excluded(self):
        _open_claim, open_thread = self._create_thread("visible")
        self._create_thread("rejected", status_value=Thread.Status.REJECTED)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(open_thread.id)])

    def test_search_claim_type_assessment_and_sort_can_be_combined(self):
        matching_claim, matching_thread = self._create_thread(
            "combined needle",
            claim_type=Claim.ClaimType.URL,
        )
        self._issue_human_decision(matching_claim, matching_thread)
        self._create_thread("combined needle", claim_type=Claim.ClaimType.TEXT)
        self._create_thread("different", claim_type=Claim.ClaimType.URL)

        response = self.client.get(
            self.url,
            {
                "search": "combined needle",
                "claim_type": Claim.ClaimType.URL,
                "assessment_source": "human",
                "sort": "oldest",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(matching_thread.id)])

    def test_cursor_next_link_preserves_active_query_parameters(self):
        for index in range(21):
            self._create_thread(
                f"cursor match {index}",
                claim_type=Claim.ClaimType.VIDEO,
            )

        response = self.client.get(
            self.url,
            {
                "search": "cursor match",
                "claim_type": Claim.ClaimType.VIDEO,
                "assessment_source": "ai",
                "sort": "oldest",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["next"])
        next_query = parse_qs(urlparse(response.data["next"]).query)
        self.assertEqual(next_query["search"], ["cursor match"])
        self.assertEqual(next_query["claim_type"], [Claim.ClaimType.VIDEO])
        self.assertEqual(next_query["assessment_source"], ["ai"])
        self.assertEqual(next_query["sort"], ["oldest"])
        self.assertIn("cursor", next_query)

    def test_list_serializer_is_minimized_for_feed_use(self):
        _claim, thread = self._create_thread("projection")
        EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.author,
            evidence_caption="Community evidence.",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["results"][0]
        self.assertEqual(
            set(item),
            {
                "id",
                "display_id",
                "caption",
                "status",
                "created_at",
                "comment_count",
                "evidence_count",
                "author",
                "claim",
            },
        )
        self.assertEqual(set(item["author"]), {"id", "username", "avatar_url"})
        self.assertNotIn("email", item["author"])
        self.assertEqual(
            set(item["claim"]),
            {
                "id",
                "claim_type",
                "context_text",
                "media_url",
                "canonical_source_url",
                "ai_verdict",
                "ai_summary",
                "consensus_score",
                "human_verdict",
                "verified_evidence_count",
            },
        )
        self.assertEqual(item["evidence_count"], 1)
        self.assertEqual(item["claim"]["verified_evidence_count"], 0)
