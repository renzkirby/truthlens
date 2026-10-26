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
    ClaimInvestigationClassification,
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

    def _classify_claim(
        self,
        claim,
        *domains,
        primary_subject=None,
        campus_context_state=None,
    ):
        return ClaimInvestigationClassification.objects.create(
            claim=claim,
            domains=list(domains),
            primary_subject=primary_subject,
            campus_context_state=campus_context_state,
            rationale=(
                "Authoritative subject classification created for "
                "Community feed API tests."
            ),
        )

    @staticmethod
    def _result_ids(response):
        return [item["id"] for item in response.data["results"]]

    def test_default_ordering_is_newest_first(self):
        _old_claim, old_thread = self._create_thread("older")
        _new_claim, new_thread = self._create_thread("newer")
        Thread.objects.filter(pk=old_thread.pk).update(
            created_at=parse_datetime("2026-01-01T00:00:00Z")
        )
        Thread.objects.filter(pk=new_thread.pk).update(
            created_at=parse_datetime("2026-01-01T00:00:01Z")
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._result_ids(response),
            [str(new_thread.id), str(old_thread.id)],
        )

    def test_oldest_ordering(self):
        _old_claim, old_thread = self._create_thread("older")
        _new_claim, new_thread = self._create_thread("newer")
        Thread.objects.filter(pk=old_thread.pk).update(
            created_at=parse_datetime("2026-01-01T00:00:00Z")
        )
        Thread.objects.filter(pk=new_thread.pk).update(
            created_at=parse_datetime("2026-01-01T00:00:01Z")
        )

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

    def test_public_topic_projection_uses_only_single_authoritative_subject(self):
        education_claim, education_thread = self._create_thread("education topic")
        self._classify_claim(education_claim, "EDUCATION")

        multi_claim, multi_thread = self._create_thread("multi-domain topic")
        self._classify_claim(multi_claim, "ELECTIONS", "TECHNOLOGY")

        _unclassified_claim, unclassified_thread = self._create_thread(
            "unclassified topic"
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = {item["id"]: item for item in response.data["results"]}
        self.assertEqual(
            items[str(education_thread.id)]["claim"]["public_topic"],
            {"code": "EDUCATION", "label": "Education"},
        )
        self.assertIsNone(
            items[str(multi_thread.id)]["claim"]["public_topic"]
        )
        self.assertIsNone(
            items[str(unclassified_thread.id)]["claim"]["public_topic"]
        )

    def test_public_topic_projection_uses_explicit_multidomain_primary_subject(self):
        claim, thread = self._create_thread("explicit primary topic")
        self._classify_claim(
            claim,
            "ELECTIONS",
            "TECHNOLOGY",
            primary_subject="ELECTIONS",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(
            item for item in response.data["results"] if item["id"] == str(thread.id)
        )
        self.assertEqual(
            item["claim"]["public_topic"],
            {
                "code": "POLITICS_GOVERNMENT_LAW",
                "label": "Politics, Governance & Law",
            },
        )

    def test_topic_filter_uses_explicit_multidomain_primary_subject(self):
        politics_claim, politics_thread = self._create_thread(
            "explicit politics primary"
        )
        self._classify_claim(
            politics_claim,
            "ELECTIONS",
            "TECHNOLOGY",
            primary_subject="ELECTIONS",
        )
        technology_claim, technology_thread = self._create_thread(
            "explicit technology primary"
        )
        self._classify_claim(
            technology_claim,
            "ELECTIONS",
            "TECHNOLOGY",
            primary_subject="TECHNOLOGY",
        )

        response = self.client.get(
            self.url,
            {"topic": "POLITICS_GOVERNMENT_LAW"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = set(self._result_ids(response))
        self.assertIn(str(politics_thread.id), result_ids)
        self.assertNotIn(str(technology_thread.id), result_ids)

    def test_topic_filter_treats_blank_primary_as_legacy_missing_primary(self):
        claim, thread = self._create_thread("blank primary compatibility")
        self._classify_claim(claim, "EDUCATION", primary_subject="")

        response = self.client.get(self.url, {"topic": "EDUCATION"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(str(thread.id), set(self._result_ids(response)))

    def test_topic_filter_groups_single_domain_authoritative_claims(self):
        expected = set()
        for domain in ("CIVICS", "ELECTIONS", "LAW"):
            claim, thread = self._create_thread(f"{domain.lower()} topic")
            self._classify_claim(claim, domain)
            expected.add(str(thread.id))

        health_claim, health_thread = self._create_thread("health topic")
        self._classify_claim(health_claim, "HEALTH")
        multi_claim, multi_thread = self._create_thread("multi politics topic")
        self._classify_claim(multi_claim, "ELECTIONS", "TECHNOLOGY")

        response = self.client.get(
            self.url,
            {"topic": "POLITICS_GOVERNMENT_LAW"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = set(self._result_ids(response))
        self.assertEqual(result_ids, expected)
        self.assertNotIn(str(health_thread.id), result_ids)
        self.assertNotIn(str(multi_thread.id), result_ids)

    def test_campus_affairs_topic_filters_confirmed_context_across_subjects(self):
        health_claim, health_thread = self._create_thread("campus health")
        self._classify_claim(
            health_claim,
            "HEALTH",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
        )
        election_claim, election_thread = self._create_thread("campus election")
        self._classify_claim(
            election_claim,
            "ELECTIONS",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
        )
        multi_claim, multi_thread = self._create_thread("campus multi-domain")
        self._classify_claim(
            multi_claim,
            "EDUCATION",
            "TECHNOLOGY",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
        )

        city_claim, city_thread = self._create_thread("city-wide suspension")
        self._classify_claim(
            city_claim,
            "EDUCATION",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
            ),
        )
        uncertain_claim, uncertain_thread = self._create_thread("uncertain campus")
        self._classify_claim(
            uncertain_claim,
            "TECHNOLOGY",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.UNCERTAIN
            ),
        )
        unassessed_claim, unassessed_thread = self._create_thread("unassessed campus")
        self._classify_claim(unassessed_claim, "SCIENCE")

        response = self.client.get(self.url, {"topic": "CAMPUS_AFFAIRS"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = set(self._result_ids(response))
        self.assertEqual(
            result_ids,
            {
                str(health_thread.id),
                str(election_thread.id),
                str(multi_thread.id),
            },
        )
        self.assertNotIn(str(city_thread.id), result_ids)
        self.assertNotIn(str(uncertain_thread.id), result_ids)
        self.assertNotIn(str(unassessed_thread.id), result_ids)

        health_item = next(
            item
            for item in response.data["results"]
            if item["id"] == str(health_thread.id)
        )
        self.assertEqual(
            health_item["claim"]["public_topic"]["code"],
            "HEALTH_MEDICINE",
        )
        multi_item = next(
            item
            for item in response.data["results"]
            if item["id"] == str(multi_thread.id)
        )
        self.assertIsNone(multi_item["claim"]["public_topic"])

    def test_campus_affairs_combines_with_existing_feed_filters(self):
        matching_claim, matching_thread = self._create_thread(
            "campus combined needle",
            claim_type=Claim.ClaimType.URL,
        )
        self._classify_claim(
            matching_claim,
            "EDUCATION",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
        )
        self._issue_human_decision(matching_claim, matching_thread)

        wrong_type_claim, wrong_type_thread = self._create_thread(
            "campus combined needle",
            claim_type=Claim.ClaimType.TEXT,
        )
        self._classify_claim(
            wrong_type_claim,
            "EDUCATION",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
        )
        self._issue_human_decision(wrong_type_claim, wrong_type_thread)

        non_campus_claim, non_campus_thread = self._create_thread(
            "campus combined needle",
            claim_type=Claim.ClaimType.URL,
        )
        self._classify_claim(
            non_campus_claim,
            "EDUCATION",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.NOT_APPLICABLE
            ),
        )
        self._issue_human_decision(non_campus_claim, non_campus_thread)

        ai_claim, ai_thread = self._create_thread(
            "campus combined needle",
            claim_type=Claim.ClaimType.URL,
        )
        self._classify_claim(
            ai_claim,
            "EDUCATION",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
        )

        response = self.client.get(
            self.url,
            {
                "search": "campus combined needle",
                "claim_type": Claim.ClaimType.URL,
                "assessment_source": "human",
                "sort": "oldest",
                "topic": "CAMPUS_AFFAIRS",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(matching_thread.id)])
        excluded_ids = {
            str(wrong_type_thread.id),
            str(non_campus_thread.id),
            str(ai_thread.id),
        }
        self.assertTrue(excluded_ids.isdisjoint(set(self._result_ids(response))))

    def test_invalid_topic_returns_controlled_bad_request(self):
        response = self.client.get(self.url, {"topic": "UNKNOWN_TOPIC"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("topic", response.data)

    def test_assessment_source_ai_requires_actual_ai_analysis(self):
        _ai_claim, ai_thread = self._create_thread("actual AI analysis")
        no_ai_claim, no_ai_thread = self._create_thread("no AI analysis")
        Claim.objects.filter(pk=no_ai_claim.pk).update(
            ai_verdict=None,
            ai_summary=None,
            consensus_score=None,
        )

        response = self.client.get(self.url, {"assessment_source": "ai"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_ids = set(self._result_ids(response))
        self.assertIn(str(ai_thread.id), result_ids)
        self.assertNotIn(str(no_ai_thread.id), result_ids)

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
        self._classify_claim(matching_claim, "EDUCATION")
        self._issue_human_decision(matching_claim, matching_thread)
        text_claim, _text_thread = self._create_thread(
            "combined needle", claim_type=Claim.ClaimType.TEXT
        )
        self._classify_claim(text_claim, "EDUCATION")
        other_claim, _other_thread = self._create_thread(
            "different", claim_type=Claim.ClaimType.URL
        )
        self._classify_claim(other_claim, "HEALTH")

        response = self.client.get(
            self.url,
            {
                "search": "combined needle",
                "claim_type": Claim.ClaimType.URL,
                "assessment_source": "human",
                "sort": "oldest",
                "topic": "EDUCATION",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self._result_ids(response), [str(matching_thread.id)])

    def test_campus_affairs_cursor_preserves_context_topic(self):
        for index in range(21):
            claim, _thread = self._create_thread(
                f"campus cursor match {index}",
                claim_type=Claim.ClaimType.TEXT,
            )
            self._classify_claim(
                claim,
                "EDUCATION",
                campus_context_state=(
                    ClaimInvestigationClassification.CampusContextState.CONFIRMED
                ),
            )

        response = self.client.get(
            self.url,
            {
                "search": "campus cursor match",
                "sort": "oldest",
                "topic": "CAMPUS_AFFAIRS",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["next"])
        next_query = parse_qs(urlparse(response.data["next"]).query)
        self.assertEqual(next_query["search"], ["campus cursor match"])
        self.assertEqual(next_query["sort"], ["oldest"])
        self.assertEqual(next_query["topic"], ["CAMPUS_AFFAIRS"])
        self.assertIn("cursor", next_query)

    def test_cursor_next_link_preserves_active_query_parameters(self):
        for index in range(21):
            claim, _thread = self._create_thread(
                f"cursor match {index}",
                claim_type=Claim.ClaimType.VIDEO,
            )
            self._classify_claim(claim, "TECHNOLOGY")

        response = self.client.get(
            self.url,
            {
                "search": "cursor match",
                "claim_type": Claim.ClaimType.VIDEO,
                "assessment_source": "ai",
                "sort": "oldest",
                "topic": "SCIENCE_TECHNOLOGY",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["next"])
        next_query = parse_qs(urlparse(response.data["next"]).query)
        self.assertEqual(next_query["search"], ["cursor match"])
        self.assertEqual(next_query["claim_type"], [Claim.ClaimType.VIDEO])
        self.assertEqual(next_query["assessment_source"], ["ai"])
        self.assertEqual(next_query["sort"], ["oldest"])
        self.assertEqual(next_query["topic"], ["SCIENCE_TECHNOLOGY"])
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
        self.assertEqual(
            set(item["author"]),
            {"id", "username", "avatar_url", "partner_affiliations"},
        )
        self.assertEqual(item["author"]["partner_affiliations"], [])
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
                "public_topic",
                "verified_evidence_count",
            },
        )
        self.assertEqual(item["evidence_count"], 1)
        self.assertEqual(item["claim"]["verified_evidence_count"], 0)
        self.assertIsNone(item["claim"]["public_topic"])
