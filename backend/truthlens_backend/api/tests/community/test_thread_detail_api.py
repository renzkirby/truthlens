from copy import deepcopy

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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
    OfficialFactCheck,
    OfficialFactCheckPublicationSnapshot,
    Organization,
    OrganizationMembership,
    Thread,
    ThreadComment,
    ThreadCommentLike,
    VerificationAssignment,
)
from api.publishing_service import (
    create_fact_check_draft,
    publish_fact_check,
    submit_fact_check_for_review,
)


class ThreadDetailApiTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="thread-author",
            email="author-private@example.com",
            password="test-password",
        )
        self.reviewer = User.objects.create_user(
            username="thread-reviewer",
            email="reviewer-private@example.com",
            password="test-password",
        )
        self.other_user = User.objects.create_user(
            username="other-commenter",
            email="other-private@example.com",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            name="Thread Detail Review Partner",
            slug="thread-detail-review-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
            public_logo_enabled=True,
            logo_url="https://example.com/thread-detail-review-partner.png",
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.reviewer,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.author)

    def _create_thread(self, label="detail"):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text=f"Primary claim: {label}",
            url_link="https://example.com/claim",
            ai_verdict=AdjudicationDecision.Verdict.UNVERIFIED,
            ai_summary=f"AI analysis: {label}",
            consensus_score=61,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.author,
            caption=f"Community context: {label}",
            status=Thread.Status.OPEN,
        )
        return claim, thread

    def _detail(self, thread):
        return self.client.get(reverse("thread-detail", args=[thread.id]))

    def _issue_human_decision(
        self,
        claim,
        thread,
        *,
        organization=None,
        reviewer=None,
    ):
        organization = organization or self.organization
        reviewer = reviewer or self.reviewer
        EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.author,
            evidence_caption="Verified evidence.",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
        )
        VerificationAssignment.objects.create(
            claim=claim,
            organization=organization,
            claimed_by=reviewer,
            status=VerificationAssignment.Status.ACTIVE,
        )
        case = ensure_adjudication_case(
            claim=claim,
            actor=reviewer,
            organization=organization,
        )
        result = issue_adjudication_decision(
            case_id=case.id,
            organization_id=organization.id,
            actor=reviewer,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=claim.context_text,
            rationale="A human adjudicator reviewed the evidence.",
            expected_revision=0,
        )
        return result["decision"]

    def _create_fact_check(
        self,
        decision,
        *,
        organization=None,
        reviewer=None,
        headline="Exact claim public fact-check",
        target_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
    ):
        organization = organization or self.organization
        reviewer = reviewer or self.reviewer
        draft = create_fact_check_draft(
            decision=decision,
            actor=reviewer,
            organization_id=organization.id,
            expected_decision_revision=decision.revision_number,
            headline=headline,
            summary="A public summary based on the reviewed evidence.",
            article_body="The sealed article body must not appear in Thread Detail.",
            source_urls=["https://example.com/thread-detail-publication-source"],
        )
        if target_status == OfficialFactCheck.PublicationStatus.DRAFT:
            return draft

        in_review = submit_fact_check_for_review(
            fact_check=draft,
            actor=reviewer,
            organization_id=organization.id,
            expected_edit_generation=draft.edit_generation,
            expected_decision_revision=decision.revision_number,
        )
        if target_status == OfficialFactCheck.PublicationStatus.IN_REVIEW:
            return in_review

        return publish_fact_check(
            fact_check=in_review,
            actor=reviewer,
            organization_id=organization.id,
            expected_edit_generation=in_review.edit_generation,
            expected_decision_revision=decision.revision_number,
        )["fact_check"]

    def test_thread_detail_exposes_stored_escalation_reason(self):
        _claim, thread = self._create_thread("discussion focus")
        thread.escalation_reason = Thread.EscalationReason.MISSING_CONTEXT
        thread.save(update_fields=["escalation_reason"])

        response = self._detail(thread)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["escalation_reason"],
            Thread.EscalationReason.MISSING_CONTEXT,
        )

    def test_thread_detail_serializes_legacy_thread_without_escalation_reason(self):
        _claim, thread = self._create_thread("legacy discussion")

        response = self._detail(thread)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["escalation_reason"])

    def test_thread_detail_uses_public_safe_identity_projections(self):
        _claim, thread = self._create_thread("safe identities")
        comment = ThreadComment.objects.create(
            thread=thread,
            commenter=self.other_user,
            comment_text="Community comment.",
        )
        evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.other_user,
            verified_by=self.reviewer,
            evidence_caption="Community evidence.",
            evidence_type=EvidenceSubmission.EvidenceType.PROVIDES_CONTEXT,
        )

        response = self._detail(thread)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data["author"]),
            {"id", "username", "avatar_url", "role", "trust_score"},
        )
        serialized_comment = next(
            item for item in response.data["comments"] if item["id"] == str(comment.id)
        )
        self.assertEqual(
            set(serialized_comment["commenter"]),
            {"id", "username", "avatar_url", "role"},
        )
        serialized_evidence = next(
            item
            for item in response.data["evidence_submissions"]
            if item["id"] == str(evidence.id)
        )
        self.assertEqual(
            set(serialized_evidence["contributor"]),
            {"id", "username", "avatar_url", "trust_score"},
        )
        self.assertEqual(
            set(serialized_evidence["verified_by"]),
            {"id", "username", "avatar_url"},
        )
        self.assertEqual(
            set(response.data["claim"]),
            {
                "id",
                "claim_type",
                "context_text",
                "media_url",
                "url_link",
                "ai_verdict",
                "ai_summary",
                "consensus_score",
                "verified_evidence_count",
                "human_verdict",
                "published_fact_check",
            },
        )
        for identity in (
            response.data["author"],
            serialized_comment["commenter"],
            serialized_evidence["contributor"],
            serialized_evidence["verified_by"],
        ):
            self.assertNotIn("email", identity)
            self.assertNotIn("is_email_verified", identity)
            self.assertNotIn("has_completed_onboarding", identity)
            self.assertNotIn("organization_name", identity)

    def test_attributable_canonical_human_verdict_projection(self):
        claim, thread = self._create_thread("canonical verdict")
        decision = self._issue_human_decision(claim, thread)

        response = self._detail(thread)

        human_verdict = response.data["claim"]["human_verdict"]
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

    def test_canonical_human_verdict_fails_closed_without_case_organization(self):
        claim, thread = self._create_thread("fail closed")
        decision = self._issue_human_decision(claim, thread)
        self.assertEqual(decision.organization_id, self.organization.id)
        decision.moderation_case.organization = None
        decision.moderation_case.save(update_fields=["organization"])

        response = self._detail(thread)

        human_verdict = response.data["claim"]["human_verdict"]
        self.assertEqual(human_verdict["verdict"], decision.verdict)
        self.assertIsNone(human_verdict["organization"])

    def test_public_ineligible_organization_is_not_exposed(self):
        claim, thread = self._create_thread("private partner")
        decision = self._issue_human_decision(claim, thread)
        self._create_fact_check(decision)
        self.organization.public_profile_enabled = False
        self.organization.save(update_fields=["public_profile_enabled"])

        response = self._detail(thread)

        self.assertIsNone(response.data["claim"]["human_verdict"]["organization"])
        self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_attributable_legacy_review_uses_decision_organization(self):
        claim, thread = self._create_thread("legacy review")
        thread.moderated_by = self.reviewer
        thread.moderator_verdict = AdjudicationDecision.Verdict.FACT
        thread.save(update_fields=["moderated_by", "moderator_verdict"])
        decision = AdjudicationDecision.objects.create(
            claim=claim,
            verdict=AdjudicationDecision.Verdict.FACT,
            canonical_claim=claim.context_text,
            rationale="Attributable historical review.",
            decided_by=self.reviewer,
            organization=self.organization,
            decision_source=AdjudicationDecision.DecisionSource.LEGACY_MIGRATION,
        )

        response = self._detail(thread)

        human_verdict = response.data["claim"]["human_verdict"]
        self.assertEqual(human_verdict["verdict"], decision.verdict)
        self.assertEqual(human_verdict["organization"]["id"], str(self.organization.id))

    def test_ai_only_claim_has_null_human_verdict(self):
        _claim, thread = self._create_thread("AI only")

        response = self._detail(thread)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["claim"]["human_verdict"])
        self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_exact_claim_public_published_fact_check_is_projected(self):
        claim, thread = self._create_thread("published projection")
        decision = self._issue_human_decision(claim, thread)
        publication = self._create_fact_check(
            decision,
            headline="What the reviewed record establishes",
        )

        response = self._detail(thread)

        projected = response.data["claim"]["published_fact_check"]
        self.assertEqual(projected["publication_id"], str(publication.id))
        self.assertEqual(
            projected["headline"],
            publication.publication_snapshot.payload["headline"],
        )
        self.assertEqual(
            projected["published_at"],
            publication.publication_snapshot.payload["published_at"],
        )
        self.assertEqual(
            projected["organization"]["id"],
            response.data["claim"]["human_verdict"]["organization"]["id"],
        )

    def test_published_fact_check_projection_exposes_only_safe_keys(self):
        claim, thread = self._create_thread("safe publication shape")
        decision = self._issue_human_decision(claim, thread)
        self._create_fact_check(decision)

        projected = self._detail(thread).data["claim"]["published_fact_check"]

        self.assertEqual(
            set(projected),
            {"publication_id", "headline", "published_at", "organization"},
        )
        self.assertEqual(
            set(projected["organization"]),
            {"id", "name", "slug", "logo_url"},
        )
        for private_key in (
            "article_body",
            "publication_status",
            "adjudication_decision",
            "moderation_case",
            "sources",
            "lineage",
        ):
            self.assertNotIn(private_key, projected)

    def test_human_review_without_publication_has_null_projection(self):
        claim, thread = self._create_thread("review only")
        self._issue_human_decision(claim, thread)

        response = self._detail(thread)

        self.assertIsNotNone(response.data["claim"]["human_verdict"])
        self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_publication_organization_must_match_human_review_organization(self):
        publishing_organization = Organization.objects.create(
            name="Different Publishing Partner",
            slug="different-publishing-partner",
            organization_type=Organization.OrganizationType.FACT_CHECKING,
            verification_status=Organization.VerificationStatus.VERIFIED,
            partner_status=Organization.PartnerStatus.ACTIVE,
            public_profile_enabled=True,
        )
        OrganizationMembership.objects.create(
            organization=publishing_organization,
            user=self.reviewer,
            role=OrganizationMembership.Role.LEAD_VERIFIER,
            status=OrganizationMembership.Status.ACTIVE,
        )
        claim, thread = self._create_thread("organization mismatch")
        decision = self._issue_human_decision(
            claim,
            thread,
            organization=publishing_organization,
        )
        self._create_fact_check(
            decision,
            organization=publishing_organization,
        )
        decision.moderation_case.organization = self.organization
        decision.moderation_case.save(update_fields=["organization"])

        response = self._detail(thread)

        self.assertEqual(
            response.data["claim"]["human_verdict"]["organization"]["id"],
            str(self.organization.id),
        )
        self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_draft_and_in_review_fact_checks_are_not_projected(self):
        for publication_status in (
            OfficialFactCheck.PublicationStatus.DRAFT,
            OfficialFactCheck.PublicationStatus.IN_REVIEW,
        ):
            with self.subTest(publication_status=publication_status):
                claim, thread = self._create_thread(
                    f"unpublished {publication_status.lower()}"
                )
                decision = self._issue_human_decision(claim, thread)
                self._create_fact_check(
                    decision,
                    target_status=publication_status,
                )

                response = self._detail(thread)

                self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_archived_only_fact_check_is_not_projected(self):
        claim, thread = self._create_thread("archived publication")
        decision = self._issue_human_decision(claim, thread)
        publication = self._create_fact_check(decision)
        OfficialFactCheck.objects.filter(pk=publication.pk).update(
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            archived_at=timezone.now(),
        )

        response = self._detail(thread)

        self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_unsealed_invalid_snapshot_and_invalid_lineage_fail_closed(self):
        claim, thread = self._create_thread("unsealed publication")
        decision = self._issue_human_decision(claim, thread)
        now = timezone.now()
        OfficialFactCheck.objects.create(
            claim=claim,
            adjudication_decision=decision,
            organization=self.organization,
            canonical_claim=decision.canonical_claim,
            verdict=decision.verdict,
            headline="Unsealed publication",
            summary="This mutable row has no public publication seal.",
            article_body="Private mutable content.",
            publication_status=OfficialFactCheck.PublicationStatus.PUBLISHED,
            version=1,
            drafted_by=self.reviewer,
            reviewed_by=self.reviewer,
            reviewed_at=now,
            published_by=self.reviewer,
            published_at=now,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        self.assertIsNone(
            self._detail(thread).data["claim"]["published_fact_check"]
        )

        invalid_claim, invalid_thread = self._create_thread("invalid snapshot")
        invalid_decision = self._issue_human_decision(invalid_claim, invalid_thread)
        invalid_publication = self._create_fact_check(invalid_decision)
        invalid_payload = deepcopy(invalid_publication.publication_snapshot.payload)
        invalid_payload["headline"] = "Tampered sealed headline"
        OfficialFactCheckPublicationSnapshot.objects.filter(
            fact_check=invalid_publication
        ).update(payload=invalid_payload)
        self.assertIsNone(
            self._detail(invalid_thread).data["claim"]["published_fact_check"]
        )

        lineage_claim, lineage_thread = self._create_thread("invalid lineage")
        lineage_decision = self._issue_human_decision(lineage_claim, lineage_thread)
        current = self._create_fact_check(lineage_decision)
        OfficialFactCheck.objects.create(
            claim=lineage_claim,
            adjudication_decision=lineage_decision,
            organization=self.organization,
            canonical_claim=lineage_decision.canonical_claim,
            verdict=lineage_decision.verdict,
            headline="Disconnected archived publication",
            summary="This row is outside the sealed publication lineage.",
            article_body="Disconnected historical content.",
            publication_status=OfficialFactCheck.PublicationStatus.ARCHIVED,
            version=current.version + 1,
            drafted_by=self.reviewer,
            reviewed_by=self.reviewer,
            reviewed_at=now,
            published_by=self.reviewer,
            published_at=now,
            archived_at=now,
            revision_kind=OfficialFactCheck.RevisionKind.INITIAL,
        )
        self.assertIsNone(
            self._detail(lineage_thread).data["claim"]["published_fact_check"]
        )

    def test_publication_for_different_claim_is_not_projected(self):
        claim, thread = self._create_thread("requested exact claim")
        self._issue_human_decision(claim, thread)
        other_claim, other_thread = self._create_thread("different published claim")
        other_decision = self._issue_human_decision(other_claim, other_thread)
        self._create_fact_check(other_decision)

        response = self._detail(thread)

        self.assertIsNone(response.data["claim"]["published_fact_check"])

    def test_publication_logo_fails_closed_when_public_logo_is_disabled(self):
        claim, thread = self._create_thread("logo permission")
        decision = self._issue_human_decision(claim, thread)
        self._create_fact_check(decision)
        self.organization.public_logo_enabled = False
        self.organization.save(update_fields=["public_logo_enabled"])

        response = self._detail(thread)

        projected = response.data["claim"]["published_fact_check"]
        self.assertIsNotNone(projected)
        self.assertIsNone(projected["organization"]["logo_url"])
        self.assertIsNone(
            response.data["claim"]["human_verdict"]["organization"]["logo_url"]
        )

    def test_same_thread_reply_creation_and_projection(self):
        _claim, thread = self._create_thread("reply")
        parent = ThreadComment.objects.create(
            thread=thread,
            commenter=self.other_user,
            comment_text="Parent comment.",
        )

        response = self.client.post(
            reverse("comment-list"),
            {
                "thread_id": str(thread.id),
                "parent_id": str(parent.id),
                "comment_text": "Reply comment.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["parent_id"], parent.id)
        self.assertEqual(response.data["reply_to_username"], self.other_user.username)

    def test_cross_thread_parent_is_rejected(self):
        _claim, thread = self._create_thread("reply target")
        _other_claim, other_thread = self._create_thread("other thread")
        parent = ThreadComment.objects.create(
            thread=other_thread,
            commenter=self.other_user,
            comment_text="Other thread parent.",
        )

        response = self.client.post(
            reverse("comment-list"),
            {
                "thread_id": str(thread.id),
                "parent_id": str(parent.id),
                "comment_text": "Invalid cross-thread reply.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent_id", response.data)

    def test_parent_is_immutable_after_creation(self):
        _claim, thread = self._create_thread("immutable parent")
        first_parent = ThreadComment.objects.create(
            thread=thread,
            commenter=self.other_user,
            comment_text="First parent.",
        )
        second_parent = ThreadComment.objects.create(
            thread=thread,
            commenter=self.other_user,
            comment_text="Second parent.",
        )
        reply = ThreadComment.objects.create(
            thread=thread,
            commenter=self.author,
            parent=first_parent,
            comment_text="Reply.",
        )

        response = self.client.patch(
            reverse("comment-detail", args=[reply.id]),
            {"parent_id": str(second_parent.id)},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        reply.refresh_from_db()
        self.assertEqual(reply.parent_id, first_parent.id)

    def test_deleting_parent_preserves_reply(self):
        _claim, thread = self._create_thread("parent deletion")
        parent = ThreadComment.objects.create(
            thread=thread,
            commenter=self.other_user,
            comment_text="Parent.",
        )
        reply = ThreadComment.objects.create(
            thread=thread,
            commenter=self.author,
            parent=parent,
            comment_text="Reply survives.",
        )

        parent.delete()

        reply.refresh_from_db()
        self.assertIsNone(reply.parent_id)

    def test_comment_like_and_unlike_actions_are_idempotent(self):
        _claim, thread = self._create_thread("likes")
        comment = ThreadComment.objects.create(
            thread=thread,
            commenter=self.other_user,
            comment_text="Likeable comment.",
        )
        like_url = reverse("comment-like", args=[comment.id])

        first_like = self.client.post(like_url)
        duplicate_like = self.client.post(like_url)

        self.assertEqual(first_like.status_code, status.HTTP_200_OK)
        self.assertEqual(duplicate_like.status_code, status.HTTP_200_OK)
        self.assertEqual(
            ThreadCommentLike.objects.filter(comment=comment, user=self.author).count(),
            1,
        )
        self.assertEqual(duplicate_like.data["like_count"], 1)
        self.assertTrue(duplicate_like.data["is_liked"])

        detail_response = self._detail(thread)
        serialized_comment = detail_response.data["comments"][0]
        self.assertEqual(serialized_comment["like_count"], 1)
        self.assertTrue(serialized_comment["is_liked"])

        first_unlike = self.client.delete(like_url)
        repeated_unlike = self.client.delete(like_url)

        self.assertEqual(first_unlike.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_unlike.status_code, status.HTTP_200_OK)
        self.assertEqual(repeated_unlike.data["like_count"], 0)
        self.assertFalse(repeated_unlike.data["is_liked"])

    def test_comment_edit_and_delete_ownership_remains_enforced(self):
        _claim, thread = self._create_thread("ownership")
        comment = ThreadComment.objects.create(
            thread=thread,
            commenter=self.author,
            comment_text="Owner comment.",
        )
        detail_url = reverse("comment-detail", args=[comment.id])

        self.client.force_authenticate(user=self.other_user)
        denied_edit = self.client.patch(
            detail_url,
            {"comment_text": "Not allowed."},
            format="json",
        )
        denied_delete = self.client.delete(detail_url)

        self.assertEqual(denied_edit.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(denied_delete.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.author)
        allowed_edit = self.client.patch(
            detail_url,
            {"comment_text": "Owner edit."},
            format="json",
        )
        allowed_delete = self.client.delete(detail_url)

        self.assertEqual(allowed_edit.status_code, status.HTTP_200_OK)
        self.assertEqual(allowed_delete.status_code, status.HTTP_204_NO_CONTENT)
