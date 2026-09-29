import hashlib
import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import Claim


class AnalyzedClaimBackfillTests(TestCase):
    def setUp(self):
        self.article = ("Historical extracted article content. " * 100)[:3000].strip()
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            url_link="https://example.com/historical-article",
            context_text=self.article,
            ai_verdict="FACT",
            final_verdict="FACT",
            ai_summary="Existing assessment summary.",
            claim_fingerprint="historical-url-fingerprint",
        )
        self.proposition = "A specific factual proposition was reported."
        self.corrected_proposition = (
            "A specific factual proposition was accurately reported."
        )
        self.result = {
            "cleaned_claim": self.proposition,
            "search_query": "specific factual proposition reported",
            "search_queries": ["specific factual proposition reported"],
            "article_stance": "REPORTING",
        }

    def _run(self, **options):
        output = StringIO()
        call_command("backfill_analyzed_claims", stdout=output, **options)
        return output.getvalue()

    def _dry_run(self):
        with patch(
            "api.management.commands.backfill_analyzed_claims.extract_search_query",
            return_value=self.result,
        ) as extract:
            output = self._run(claim_id=self.claim.pk, dry_run=True)
        extract.assert_called_once_with(self.article, self.claim.url_link)
        token = next(
            line.removeprefix("approval_token=")
            for line in output.splitlines()
            if line.startswith("approval_token=")
        )
        return output, token

    def _review(self, proposition=None):
        reviewed_claim = (
            self.corrected_proposition if proposition is None else proposition
        )
        with patch(
            "api.management.commands.backfill_analyzed_claims.extract_search_query"
        ) as extract:
            output = self._run(
                claim_id=self.claim.pk,
                reviewed_analyzed_claim=reviewed_claim,
            )
        extract.assert_not_called()
        token = next(
            line.removeprefix("approval_token=")
            for line in output.splitlines()
            if line.startswith("approval_token=")
        )
        return output, token

    def _apply(self, token, proposition=None):
        return self._run(
            claim_id=self.claim.pk,
            approved_analyzed_claim=(
                self.proposition if proposition is None else proposition
            ),
            approval_token=token,
        )

    def test_targeted_dry_run_reports_review_material_without_mutating(self):
        before = Claim.objects.filter(pk=self.claim.pk).values().get()

        output, token = self._dry_run()
        lines = output.splitlines()

        self.assertEqual(Claim.objects.filter(pk=self.claim.pk).values().get(), before)
        self.assertIn("[CANDIDATE]", lines)
        self.assertIn(f"claim_id={self.claim.pk}", lines)
        self.assertIn("claim_type=URL", lines)
        self.assertIn(f"url={self.claim.url_link}", lines)
        self.assertIn("source_field=context_text", lines)
        self.assertIn(f"source_length={len(self.article)}", lines)
        self.assertIn(
            f"source_sha256={hashlib.sha256(self.article.encode('utf-8')).hexdigest()}",
            lines,
        )
        self.assertIn(
            f"proposed_analyzed_claim={json.dumps(self.proposition)}",
            lines,
        )
        self.assertIn(f"proposition_length={len(self.proposition)}", lines)
        self.assertIn(f"approval_token={token}", lines)

    def test_approved_write_uses_exact_candidate_without_calling_claimgate(self):
        _output, token = self._dry_run()
        before = Claim.objects.filter(pk=self.claim.pk).values().get()

        with patch(
            "api.management.commands.backfill_analyzed_claims.extract_search_query"
        ) as extract:
            output = self._apply(token)

        extract.assert_not_called()
        after = Claim.objects.filter(pk=self.claim.pk).values().get()
        self.assertEqual(after["analyzed_claim"], self.proposition)
        self.assertEqual(after["source_context"], self.article)
        for field in before.keys() - {"analyzed_claim", "source_context"}:
            self.assertEqual(after[field], before[field], field)
        self.assertIn("[UPDATED]", output)

    def test_reviewed_candidate_is_non_mutating_and_does_not_call_claimgate(self):
        before = Claim.objects.filter(pk=self.claim.pk).values().get()

        output, token = self._review(
            f"  {self.corrected_proposition.replace(' ', '  ')}\n"
        )
        lines = output.splitlines()

        self.assertEqual(Claim.objects.filter(pk=self.claim.pk).values().get(), before)
        self.assertIn("[REVIEWED CANDIDATE]", lines)
        self.assertIn(f"claim_id={self.claim.pk}", lines)
        self.assertIn("claim_type=URL", lines)
        self.assertIn(f"url={self.claim.url_link}", lines)
        self.assertIn("source_field=context_text", lines)
        self.assertIn(f"source_length={len(self.article)}", lines)
        self.assertIn(
            f"source_sha256={hashlib.sha256(self.article.encode('utf-8')).hexdigest()}",
            lines,
        )
        self.assertIn(
            f"reviewed_analyzed_claim={json.dumps(self.corrected_proposition)}",
            lines,
        )
        self.assertIn(
            f"proposition_length={len(self.corrected_proposition)}",
            lines,
        )
        self.assertIn(f"approval_token={token}", lines)

    @patch("api.management.commands.backfill_analyzed_claims.extract_search_query")
    def test_invalid_reviewed_candidate_is_rejected(self, extract):
        before = Claim.objects.filter(pk=self.claim.pk).values().get()

        for invalid in ("   ", "word " * 151):
            with self.subTest(invalid=invalid[:20]):
                with self.assertRaisesMessage(
                    CommandError, "reviewed analyzed claim is invalid"
                ):
                    self._run(
                        claim_id=self.claim.pk,
                        reviewed_analyzed_claim=invalid,
                    )

        extract.assert_not_called()
        self.assertEqual(Claim.objects.filter(pk=self.claim.pk).values().get(), before)

    def test_original_token_cannot_approve_corrected_proposition(self):
        _output, original_token = self._dry_run()

        with self.assertRaisesMessage(CommandError, "Approval token mismatch"):
            self._apply(
                original_token,
                proposition=self.corrected_proposition,
            )

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.analyzed_claim)
        self.assertIsNone(self.claim.source_context)

    def test_reviewed_token_approves_exact_candidate_and_only_new_fields(self):
        _output, reviewed_token = self._review()
        before = Claim.objects.filter(pk=self.claim.pk).values().get()

        with patch(
            "api.management.commands.backfill_analyzed_claims.extract_search_query"
        ) as extract:
            output = self._apply(
                reviewed_token,
                proposition=self.corrected_proposition,
            )

        extract.assert_not_called()
        after = Claim.objects.filter(pk=self.claim.pk).values().get()
        self.assertEqual(after["analyzed_claim"], self.corrected_proposition)
        self.assertEqual(after["source_context"], self.article)
        for field in before.keys() - {"analyzed_claim", "source_context"}:
            self.assertEqual(after[field], before[field], field)
        self.assertIn("[UPDATED]", output)

    def test_source_changed_after_reviewed_candidate_rejects(self):
        _output, reviewed_token = self._review()
        self.claim.context_text = f"{self.article} Changed after review."
        self.claim.save(update_fields=["context_text"])

        with self.assertRaisesMessage(CommandError, "Approval token mismatch"):
            self._apply(
                reviewed_token,
                proposition=self.corrected_proposition,
            )

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.analyzed_claim)
        self.assertIsNone(self.claim.source_context)

    def test_invalid_approval_token_rejects_without_mutation(self):
        self._dry_run()
        before = Claim.objects.filter(pk=self.claim.pk).values().get()

        with self.assertRaisesMessage(CommandError, "Approval token mismatch"):
            self._apply("0" * 64)

        self.assertEqual(Claim.objects.filter(pk=self.claim.pk).values().get(), before)

    def test_source_changed_after_dry_run_rejects(self):
        _output, token = self._dry_run()
        self.claim.context_text = f"{self.article} Changed after review."
        self.claim.save(update_fields=["context_text"])

        with self.assertRaisesMessage(CommandError, "Approval token mismatch"):
            self._apply(token)

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.analyzed_claim)
        self.assertIsNone(self.claim.source_context)

    def test_different_concurrent_analyzed_claim_rejects(self):
        _output, token = self._dry_run()
        self.claim.analyzed_claim = "A different proposition was stored concurrently."
        self.claim.save(update_fields=["analyzed_claim"])

        with self.assertRaisesMessage(CommandError, "different analyzed claim"):
            self._apply(token)

        self.claim.refresh_from_db()
        self.assertEqual(
            self.claim.analyzed_claim,
            "A different proposition was stored concurrently.",
        )
        self.assertIsNone(self.claim.source_context)

    def test_second_approved_invocation_is_idempotently_skipped(self):
        _output, token = self._dry_run()
        self._apply(token)

        with patch(
            "api.management.commands.backfill_analyzed_claims.extract_search_query"
        ) as extract:
            output = self._apply(token)

        extract.assert_not_called()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.analyzed_claim, self.proposition)
        self.assertEqual(self.claim.source_context, self.article)
        self.assertIn("already applied", output)

    @patch("api.management.commands.backfill_analyzed_claims.extract_search_query")
    def test_existing_analyzed_claim_is_not_overwritten_by_dry_run(self, extract):
        self.claim.analyzed_claim = "Original verified proposition."
        self.claim.save(update_fields=["analyzed_claim"])

        output = self._run(claim_id=self.claim.pk, dry_run=True)

        extract.assert_not_called()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.analyzed_claim, "Original verified proposition.")
        self.assertIsNone(self.claim.source_context)
        self.assertIn("already exists", output)

    @patch("api.management.commands.backfill_analyzed_claims.extract_search_query")
    def test_bulk_mode_requires_source_context(self, extract):
        output = self._run(dry_run=True)

        extract.assert_not_called()
        self.assertIn("bulk mode requires source_context", output)

    @patch("api.management.commands.backfill_analyzed_claims.extract_search_query")
    def test_bulk_dry_run_uses_existing_source_context(self, extract):
        self.claim.source_context = "Stored extracted URL article."
        self.claim.save(update_fields=["source_context"])
        extract.return_value = self.result

        output = self._run(dry_run=True)

        extract.assert_called_once_with(
            "Stored extracted URL article.", self.claim.url_link
        )
        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.analyzed_claim)
        self.assertIn("source_field=source_context", output)

    @patch("api.management.commands.backfill_analyzed_claims.extract_search_query")
    def test_non_url_claim_is_skipped(self, extract):
        self.claim.claim_type = Claim.ClaimType.IMAGE
        self.claim.save(update_fields=["claim_type"])

        output = self._run(claim_id=self.claim.pk, dry_run=True)

        extract.assert_not_called()
        self.assertIn("only URL claims are eligible", output)

    @patch("api.management.commands.backfill_analyzed_claims.extract_search_query")
    def test_over_limit_claimgate_candidate_is_skipped(self, extract):
        extract.return_value = {
            **self.result,
            "cleaned_claim": "Article sentence. " * 100,
        }

        output = self._run(claim_id=self.claim.pk, dry_run=True)

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.analyzed_claim)
        self.assertIsNone(self.claim.source_context)
        self.assertIn("no usable proposition", output)

    def test_approved_write_rejects_non_normalized_proposition(self):
        _output, token = self._dry_run()

        with self.assertRaisesMessage(CommandError, "exactly match"):
            self._apply(token, proposition=f"  {self.proposition}  ")

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.analyzed_claim)
        self.assertIsNone(self.claim.source_context)
