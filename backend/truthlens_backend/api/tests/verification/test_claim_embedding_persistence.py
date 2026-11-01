from unittest.mock import patch

from django.test import TestCase

from api.models import Claim
from api.tasks import _save_claim


class ClaimEmbeddingPersistenceTests(TestCase):
    def test_existing_embedding_is_not_boolean_evaluated_or_regenerated(self):
        embedding = [0.001] * 384
        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="A claim that already has a semantic embedding.",
            claim_embedding=embedding,
        )

        # Reload through the database so pgvector can return its normal
        # deserialized vector representation rather than the original list.
        claim.refresh_from_db()
        self.assertIsNotNone(claim.claim_embedding)

        with patch(
            "api.embedding_service.generate_embedding",
            side_effect=AssertionError("existing embedding must not be regenerated"),
        ):
            saved = _save_claim(
                claim.id,
                {
                    "verdict": "UNVERIFIED",
                    "summary": "The claim remains under automated review.",
                    "confidence_score": 40,
                },
                "Live Web Search",
                "A claim that already has a semantic embedding.",
                ["https://example.com/source"],
            )

        self.assertEqual(saved.pk, claim.pk)
        saved.refresh_from_db()
        self.assertEqual(saved.ai_verdict, "UNVERIFIED")
        self.assertIsNotNone(saved.claim_embedding)
        self.assertEqual(len(saved.claim_embedding), 384)
