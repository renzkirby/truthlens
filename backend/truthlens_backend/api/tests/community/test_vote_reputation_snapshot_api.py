from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Claim, EvidenceSubmission, Thread, Vote


class VoteReputationSnapshotApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.contributor = User.objects.create_user(
            username="vote-snapshot-contributor",
            password="pass1234",
        )
        self.voter = User.objects.create_user(
            username="vote-snapshot-voter",
            password="pass1234",
        )
        self.voter.profile.trust_score = 60.0
        self.voter.profile.save(update_fields=["trust_score"])

        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/vote-snapshot-target",
            verified_via=Claim.VerificationSource.PENDING,
        )
        self.thread = Thread.objects.create(
            claim=claim,
            author=self.voter,
            caption="Vote snapshot target thread",
        )
        self.target_evidence = EvidenceSubmission.objects.create(
            thread=self.thread,
            contributor=self.contributor,
            evidence_caption="Target evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            verified_at=timezone.now(),
        )

        for index in range(3):
            self._create_resolved_evidence(
                contributor=self.voter,
                index=index,
            )

        self.client.force_authenticate(self.voter)

    def _create_resolved_evidence(self, *, contributor, index):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link=f"https://example.com/voter-history-{index}",
            verified_via=Claim.VerificationSource.PENDING,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.contributor,
            caption=f"Voter history thread {index}",
        )
        return EvidenceSubmission.objects.create(
            thread=thread,
            contributor=contributor,
            evidence_caption=f"Resolved contribution {index}",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    @patch("api.views.recompute_user_trust_score_task.delay")
    def test_create_vote_snapshots_trust_history_and_final_weight(
        self,
        recompute_delay,
    ):
        response = self.client.post(
            reverse("vote-list"),
            {
                "evidence": str(self.target_evidence.pk),
                "vote_value": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        vote = Vote.objects.get(
            evidence=self.target_evidence,
            voter=self.voter,
        )
        self.assertEqual(vote.vote_trust_snapshot, 60.0)
        self.assertEqual(
            vote.vote_resolved_actions_snapshot,
            3,
        )
        self.assertEqual(
            vote.vote_validated_actions_snapshot,
            3,
        )
        self.assertAlmostEqual(
            vote.vote_reputation_weight_snapshot,
            0.8 * (3 / 7),
        )
        recompute_delay.assert_called_once_with(
            self.contributor.pk,
        )

    @patch("api.views.recompute_user_trust_score_task.delay")
    def test_changing_vote_refreshes_reputation_snapshots(
        self,
        recompute_delay,
    ):
        create_response = self.client.post(
            reverse("vote-list"),
            {
                "evidence": str(self.target_evidence.pk),
                "vote_value": True,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        vote = Vote.objects.get(
            evidence=self.target_evidence,
            voter=self.voter,
        )

        self.voter.profile.trust_score = 80.0
        self.voter.profile.save(update_fields=["trust_score"])
        for index in range(3, 10):
            self._create_resolved_evidence(
                contributor=self.voter,
                index=index,
            )

        response = self.client.patch(
            reverse("vote-detail", args=[vote.pk]),
            {"vote_value": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        vote.refresh_from_db()
        self.assertFalse(vote.vote_value)
        self.assertEqual(vote.vote_trust_snapshot, 80.0)
        self.assertEqual(
            vote.vote_resolved_actions_snapshot,
            10,
        )
        self.assertEqual(
            vote.vote_validated_actions_snapshot,
            10,
        )
        self.assertAlmostEqual(
            vote.vote_reputation_weight_snapshot,
            0.9 * (10 / 14),
        )
        self.assertEqual(
            recompute_delay.call_count,
            2,
        )

    @patch("api.views.recompute_user_trust_score_task.delay")
    def test_vote_snapshot_fields_are_read_only(
        self,
        recompute_delay,
    ):
        response = self.client.post(
            reverse("vote-list"),
            {
                "evidence": str(self.target_evidence.pk),
                "vote_value": True,
                "vote_trust_snapshot": 100.0,
                "vote_resolved_actions_snapshot": 999,
                "vote_validated_actions_snapshot": 999,
                "vote_reputation_weight_snapshot": 1.0,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        vote = Vote.objects.get(
            evidence=self.target_evidence,
            voter=self.voter,
        )
        self.assertEqual(vote.vote_trust_snapshot, 60.0)
        self.assertEqual(
            vote.vote_resolved_actions_snapshot,
            3,
        )
        self.assertEqual(
            vote.vote_validated_actions_snapshot,
            3,
        )
        self.assertLess(
            vote.vote_reputation_weight_snapshot,
            1.0,
        )
