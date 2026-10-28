from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import Claim, EvidenceSubmission, Thread, Vote
from api.trust_score_validation import TrustScenario, simulate_trust_score
from api.trust_service import calculate_trust_components


class TrustScoreProductionParityTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="trust-parity-contributor",
            email="trust-parity-contributor@example.com",
            password="pass1234",
        )
        self.voter = User.objects.create_user(
            username="trust-parity-voter",
            email="trust-parity-voter@example.com",
            password="pass1234",
        )
        self.voter.profile.trust_score = 75.0
        self.voter.profile.save(update_fields=["trust_score"])

        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/trust-parity-evidence",
            verified_via=Claim.VerificationSource.PENDING,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.voter,
            caption="Trust validation parity thread",
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption="Parity evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
            evidence_url="https://evidence.example.com/parity",
            evidence_status=EvidenceSubmission.EvidenceStatus.VERIFIED,
            verified_at=timezone.now(),
            contributor_trust_snapshot=50.0,
        )
        Vote.objects.create(
            evidence=self.evidence,
            voter=self.voter,
            vote_value=True,
            vote_trust_snapshot=75.0,
        )

        rejected_claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/trust-parity-rejected-thread",
            verified_via=Claim.VerificationSource.PENDING,
        )
        Thread.objects.create(
            claim=rejected_claim,
            author=self.contributor,
            caption="Rejected authored thread",
            status=Thread.Status.REJECTED,
        )

    def test_simulator_matches_production_component_calculation(self):
        production = calculate_trust_components(self.contributor)
        simulated = simulate_trust_score(
            TrustScenario(
                name="production_parity",
                verified_evidence=1,
                upvote_trust_scores=(75.0,),
                active_months=1,
                rejected_threads=1,
            )
        )

        for field in (
            "resolved_actions",
            "validated_actions",
            "smoothed_accuracy",
            "contribution_points",
            "weighted_vote_signal",
            "community_points",
            "history_points",
            "moderation_penalty",
            "raw_score",
            "trust_score",
        ):
            self.assertEqual(
                simulated[field],
                production[field],
                msg=f"Simulator drifted from production field: {field}",
            )
