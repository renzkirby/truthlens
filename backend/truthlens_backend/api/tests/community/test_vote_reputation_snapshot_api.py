from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Claim, EvidenceSubmission, Thread, Vote
from api.trust_service import calculate_trust_components


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

    def test_create_vote_snapshots_live_trust_history_and_final_weight(self):
        expected = calculate_trust_components(self.voter)

        with self.captureOnCommitCallbacks(execute=True):
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
        self.assertEqual(
            vote.vote_trust_snapshot,
            expected["trust_score"],
        )
        self.assertNotEqual(
            vote.vote_trust_snapshot,
            self.voter.profile.trust_score,
        )
        self.assertEqual(vote.vote_resolved_actions_snapshot, 3)
        self.assertEqual(vote.vote_validated_actions_snapshot, 3)
        self.assertAlmostEqual(
            vote.vote_reputation_weight_snapshot,
            (0.5 + expected["trust_score"] / 200.0) * (3 / 7),
        )

        self.contributor.profile.refresh_from_db()
        self.assertEqual(
            self.contributor.profile.trust_score,
            calculate_trust_components(self.contributor)["trust_score"],
        )

    def test_changing_vote_refreshes_snapshots_from_live_reputation(self):
        with self.captureOnCommitCallbacks(execute=True):
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

        expected = calculate_trust_components(self.voter)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                reverse("vote-detail", args=[vote.pk]),
                {"vote_value": False},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        vote.refresh_from_db()
        self.assertFalse(vote.vote_value)
        self.assertEqual(
            vote.vote_trust_snapshot,
            expected["trust_score"],
        )
        self.assertNotEqual(
            vote.vote_trust_snapshot,
            self.voter.profile.trust_score,
        )
        self.assertEqual(vote.vote_resolved_actions_snapshot, 10)
        self.assertEqual(vote.vote_validated_actions_snapshot, 10)
        self.assertAlmostEqual(
            vote.vote_reputation_weight_snapshot,
            (0.5 + expected["trust_score"] / 200.0) * (10 / 14),
        )

        self.contributor.profile.refresh_from_db()
        self.assertEqual(
            self.contributor.profile.trust_score,
            calculate_trust_components(self.contributor)["trust_score"],
        )

    def test_noop_patch_does_not_refresh_vote_weight(self):
        with self.captureOnCommitCallbacks(execute=True):
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
        original_trust_snapshot = vote.vote_trust_snapshot
        original_weight = vote.vote_reputation_weight_snapshot

        self.voter.profile.trust_score = 80.0
        self.voter.profile.save(update_fields=["trust_score"])
        for index in range(3, 10):
            self._create_resolved_evidence(
                contributor=self.voter,
                index=index,
            )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(
                reverse("vote-detail", args=[vote.pk]),
                {"vote_value": True},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        vote.refresh_from_db()
        self.assertTrue(vote.vote_value)
        self.assertEqual(vote.vote_trust_snapshot, original_trust_snapshot)
        self.assertEqual(vote.vote_resolved_actions_snapshot, 3)
        self.assertEqual(vote.vote_validated_actions_snapshot, 3)
        self.assertEqual(vote.vote_reputation_weight_snapshot, original_weight)

    def test_failed_history_does_not_gain_reputation_vote_weight(self):
        failed_voter = User.objects.create_user(
            username="vote-snapshot-failed-voter",
            password="pass1234",
        )
        failed_voter.profile.trust_score = 99.0
        failed_voter.profile.save(update_fields=["trust_score"])

        for index in range(25):
            claim = Claim.objects.create(
                claim_type=Claim.ClaimType.URL,
                url_link=f"https://example.com/failed-voter-history-{index}",
                verified_via=Claim.VerificationSource.PENDING,
            )
            thread = Thread.objects.create(
                claim=claim,
                author=self.contributor,
                caption=f"Failed voter history thread {index}",
            )
            EvidenceSubmission.objects.create(
                thread=thread,
                contributor=failed_voter,
                evidence_caption=f"Rejected contribution {index}",
                evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
                evidence_status=EvidenceSubmission.EvidenceStatus.REJECTED,
                verified_at=timezone.now(),
            )

        self.client.force_authenticate(failed_voter)
        expected = calculate_trust_components(failed_voter)

        with self.captureOnCommitCallbacks(execute=True):
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
            voter=failed_voter,
        )
        self.assertEqual(vote.vote_trust_snapshot, expected["trust_score"])
        self.assertNotEqual(
            vote.vote_trust_snapshot,
            failed_voter.profile.trust_score,
        )
        self.assertEqual(vote.vote_resolved_actions_snapshot, 25)
        self.assertEqual(vote.vote_validated_actions_snapshot, 0)
        self.assertEqual(vote.vote_reputation_weight_snapshot, 0.0)

    @patch(
        "api.views.recompute_user_trust_score",
        side_effect=RuntimeError("Trust calculation unavailable"),
    )
    def test_vote_remains_successful_when_direct_trust_refresh_fails(
        self,
        recompute,
    ):
        with self.assertLogs("api.views", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("vote-list"),
                    {
                        "evidence": str(self.target_evidence.pk),
                        "vote_value": True,
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Vote.objects.filter(
                evidence=self.target_evidence,
                voter=self.voter,
            ).exists()
        )
        recompute.assert_called_once_with(self.contributor.pk)

    def test_vote_snapshot_fields_are_read_only(self):
        expected = calculate_trust_components(self.voter)

        with self.captureOnCommitCallbacks(execute=True):
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
        self.assertEqual(vote.vote_trust_snapshot, expected["trust_score"])
        self.assertEqual(vote.vote_resolved_actions_snapshot, 3)
        self.assertEqual(vote.vote_validated_actions_snapshot, 3)
        self.assertLess(vote.vote_reputation_weight_snapshot, 1.0)
