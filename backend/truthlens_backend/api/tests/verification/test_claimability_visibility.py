from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from api.models import Claim, ClaimCheckHistory


class ClaimabilityVisibilityTests(APITestCase):
    def setUp(self):
        self.submitter = User.objects.create_user(
            username="claimability-submitter",
            password="test-password",
        )
        self.viewer = User.objects.create_user(
            username="claimability-viewer",
            password="test-password",
        )

    def test_private_history_retains_nonclaimable_attempt_while_member_history_hides_it(self):
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Joel stole 800 million pesos",
            claimability_status=Claim.ClaimabilityStatus.INSUFFICIENT_CONTEXT,
        )
        ClaimCheckHistory.objects.create(
            user=self.submitter,
            claim=claim,
        )

        self.client.force_authenticate(self.submitter)
        private_response = self.client.get("/api/auth/my-claims/")

        self.assertEqual(private_response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in private_response.data],
            [str(claim.id)],
        )
        self.assertEqual(
            private_response.data[0]["claimability_status"],
            Claim.ClaimabilityStatus.INSUFFICIENT_CONTEXT,
        )

        self.client.force_authenticate(self.viewer)
        member_response = self.client.get(
            f"/api/users/{self.submitter.username}/claims/"
        )

        self.assertEqual(member_response.status_code, 200)
        self.assertEqual(member_response.data, [])
