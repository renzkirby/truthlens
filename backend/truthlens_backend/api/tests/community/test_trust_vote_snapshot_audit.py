from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from api.models import Claim, EvidenceSubmission, Thread, Vote


class TrustVoteSnapshotAuditTests(TestCase):
    def setUp(self):
        self.contributor = User.objects.create_user(
            username="snapshot-audit-contributor",
            password="pass1234",
        )
        self.voter = User.objects.create_user(
            username="snapshot-audit-voter",
            password="pass1234",
        )
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/snapshot-audit",
            verified_via=Claim.VerificationSource.PENDING,
        )
        thread = Thread.objects.create(
            claim=claim,
            author=self.voter,
            caption="Snapshot audit thread",
        )
        self.evidence = EvidenceSubmission.objects.create(
            thread=thread,
            contributor=self.contributor,
            evidence_caption="Snapshot audit evidence",
            evidence_type=EvidenceSubmission.EvidenceType.SOURCE_VERIFICATION,
        )

    def test_audit_reports_snapshot_coverage_without_details(self):
        Vote.objects.create(
            evidence=self.evidence,
            voter=self.voter,
            vote_value=True,
            vote_trust_snapshot=None,
        )

        output = StringIO()
        call_command(
            "audit_trust_vote_snapshots",
            stdout=output,
        )
        rendered = output.getvalue()

        self.assertIn("total_votes=1", rendered)
        self.assertIn("null_snapshots=1", rendered)
        self.assertIn("snapshot_coverage_percent=0.00", rendered)
        self.assertIn("weight_coverage_percent=0.00", rendered)
        self.assertIn("history_snapshot_coverage_percent=0.00", rendered)
        self.assertIn("NO VOTE OR USER DETAILS EXPOSED", rendered)
        self.assertNotIn(self.voter.username, rendered)
    def test_audit_recognizes_fully_hardened_vote(self):
        Vote.objects.create(
            evidence=self.evidence,
            voter=self.voter,
            vote_value=True,
            vote_trust_snapshot=60.0,
            vote_resolved_actions_snapshot=3,
            vote_validated_actions_snapshot=2,
            vote_reputation_weight_snapshot=0.2285714286,
        )

        output = StringIO()
        call_command(
            "audit_trust_vote_snapshots",
            stdout=output,
        )
        rendered = output.getvalue()

        self.assertIn("snapshot_coverage_percent=100.00", rendered)
        self.assertIn("weight_coverage_percent=100.00", rendered)
        self.assertIn("history_snapshot_coverage_percent=100.00", rendered)
        self.assertIn("hardened_votes=1", rendered)
        self.assertIn("legacy_preserved_votes=0", rendered)
        self.assertIn("nonstandard_snapshot_rows=0", rendered)

