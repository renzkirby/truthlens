from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import Claim, EvidenceSubmission, Thread, Vote


migration_module = import_module(
    "api.migrations.0099_vote_reputation_weight_snapshots"
)


class VoteReputationWeightMigrationTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="legacy-vote-contributor",
        )
        self.voter_a = User.objects.create_user(
            username="legacy-voter-a",
        )
        self.voter_b = User.objects.create_user(
            username="legacy-voter-b",
        )
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/legacy-vote-migration",
            verified_via=Claim.VerificationSource.PENDING,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.voter_a,
            caption="Legacy vote migration thread",
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption="Legacy migration evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            verified_at=timezone.now(),
        )

    def test_backfill_freezes_legacy_trust_snapshot_without_inventing_history(self):
        vote_a = Vote.objects.create(
            evidence=self.evidence,
            voter=self.voter_a,
            vote_value=True,
            vote_trust_snapshot=65.0,
            vote_resolved_actions_snapshot=None,
            vote_validated_actions_snapshot=None,
            vote_reputation_weight_snapshot=None,
        )
        vote_b = Vote.objects.create(
            evidence=self.evidence,
            voter=self.voter_b,
            vote_value=False,
            vote_trust_snapshot=None,
            vote_resolved_actions_snapshot=None,
            vote_validated_actions_snapshot=None,
            vote_reputation_weight_snapshot=None,
        )

        migration_module.backfill_legacy_vote_reputation_weights(
            apps,
            None,
        )

        vote_a.refresh_from_db()
        vote_b.refresh_from_db()

        self.assertAlmostEqual(
            vote_a.vote_reputation_weight_snapshot,
            0.825,
        )
        self.assertAlmostEqual(
            vote_b.vote_reputation_weight_snapshot,
            0.75,
        )
        self.assertIsNone(
            vote_a.vote_resolved_actions_snapshot,
        )
        self.assertIsNone(
            vote_a.vote_validated_actions_snapshot,
        )
        self.assertIsNone(
            vote_b.vote_resolved_actions_snapshot,
        )
        self.assertIsNone(
            vote_b.vote_validated_actions_snapshot,
        )

        migration_module.backfill_legacy_vote_reputation_weights(
            apps,
            None,
        )
        vote_a.refresh_from_db()
        self.assertAlmostEqual(
            vote_a.vote_reputation_weight_snapshot,
            0.825,
        )
