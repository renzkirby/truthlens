from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from api import tasks
from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification import runs
from api.verification.contracts import RawEvidence


class VerificationRunURLRuntimeTests(TestCase):
    def setUp(self):
        self.url = "https://example.com/article"
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL, context_text="Submitted URL claim.",
        )
        self.cleaned_text = "Cleaned article content."
        self.cleaned = {
            "cleaned_claim": "Example public claim.",
            "search_query": "example public claim",
            "article_stance": "NEUTRAL",
        }
        self.verdict = {
            "verdict": "FAKE", "summary": "Evidence refutes the claim.",
            "confidence_score": 95,
        }
        self.payload = {"claims": [{
            "text": self.cleaned["cleaned_claim"],
            "claimReview": [{
                "url": "https://example.com/fact-check", "textualRating": "False",
            }],
        }]}
        self.response = Mock(status_code=200)
        self.response.json.return_value = {
            "results": [{"raw_content": "Raw article content."}],
        }
        self.extract = self._patch("api.tasks.requests.post", return_value=self.response)
        self.clean = self._patch(
            "api.tasks.clean_extracted_text", return_value=self.cleaned_text,
        )
        self.query = self._patch("api.tasks.extract_search_query", return_value=self.cleaned)
        self.vault = self._patch("api.tasks.search_official_vault", return_value=None)
        self.real_bridge = tasks._retrieve_and_ingest_gfc
        self.bridge = self._patch(
            "api.tasks._retrieve_and_ingest_gfc", return_value=self.payload,
        )
        self.relevance = self._patch("api.tasks.is_fact_check_relevant", return_value=True)
        self.evaluate_gfc = self._patch(
            "api.tasks.evaluate_url_claim_with_gfc", return_value=self.verdict,
        )
        self.evaluate_tavily = self._patch(
            "api.tasks.evaluate_url_claim_with_tavily", return_value=self.verdict,
        )
        self.retrieve_tavily = self._patch("api.tasks._retrieve_and_ingest_tavily")
        self.retrieve_tavily.return_value = {
            "answer": "Web evidence answer.",
            "results": [{
                "url": "https://example.com/web", "title": "Web result",
                "content": "Relevant web evidence.",
            }],
        }
        self._patch("api.embedding_service.generate_embedding", return_value=None)
        self._patch("api.tasks._log_stage")
        self.save_claim = self._patch("api.tasks._save_claim", wraps=tasks._save_claim)
        self.create_run = self._patch(
            "api.tasks.create_verification_run", wraps=runs.create_verification_run,
        )
        self.start_run = self._patch(
            "api.tasks.start_verification_run", wraps=runs.start_verification_run,
        )
        self.complete_run = self._patch(
            "api.tasks.complete_verification_run", wraps=runs.complete_verification_run,
        )
        self.abstain_run = self._patch(
            "api.tasks.abstain_verification_run", wraps=runs.abstain_verification_run,
        )
        self.fail_run = self._patch(
            "api.tasks.fail_verification_run", wraps=runs.fail_verification_run,
        )

    def _patch(self, target, **kwargs):
        return self.enterContext(patch(target, **kwargs))

    def _terminal_count(self):
        return sum(helper.call_count for helper in (
            self.complete_run, self.abstain_run, self.fail_run,
        ))

    def _invoke(self):
        return tasks.url_fact_check_process.run(self.url, self.claim.pk)

    def _execute(self):
        before = self._terminal_count()
        tavily_before = self.retrieve_tavily.call_count
        try:
            self._invoke()
        finally:
            self.assertEqual(self._terminal_count() - before, 1)
            if self.retrieve_tavily.call_count > tavily_before:
                self.assertEqual(self.retrieve_tavily.call_count - tavily_before, 1)
                self.retrieve_tavily.assert_called_with(
                    self.cleaned["search_query"][:300], self.claim.pk, stage_prefix="url_",
                )
        return self.claim.verification_runs.latest("created_at")

    def _assert_terminal(self, run, status):
        self.assertEqual(run.status, status)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.completed_at)
        if status != VerificationRun.Status.FAILED:
            self.assertIsNone(run.failure_stage)
            self.assertIsNone(run.failure_code)
            self.assertIsNone(run.failure_message)

    def _assert_no_run_or_verification(self):
        self.assertEqual(VerificationRun.objects.count(), 0)
        self.create_run.assert_not_called()
        self.start_run.assert_not_called()
        self.assertEqual(self._terminal_count(), 0)
        self.vault.assert_not_called()
        self.bridge.assert_not_called()
        self.retrieve_tavily.assert_not_called()
        self.save_claim.assert_not_called()

    def test_extraction_no_results_deletes_claim_without_run(self):
        self.response.json.return_value = {"results": []}
        self._invoke()
        self.assertFalse(Claim.objects.filter(pk=self.claim.pk).exists())
        self._assert_no_run_or_verification()
        self.clean.assert_not_called()

    def test_extraction_failure_deletes_claim_without_run(self):
        self.extract.side_effect = requests.Timeout("Extraction timed out")
        self._invoke()
        self.assertFalse(Claim.objects.filter(pk=self.claim.pk).exists())
        self._assert_no_run_or_verification()

    def test_query_extraction_failure_preserves_deletion_without_run(self):
        self.query.side_effect = RuntimeError("Query extraction unavailable")
        self._invoke()
        self.assertFalse(Claim.objects.filter(pk=self.claim.pk).exists())
        self._assert_no_run_or_verification()

    def test_run_starts_only_after_extraction_and_before_verification(self):
        def observe_extraction(*args):
            self.assertEqual(VerificationRun.objects.count(), 0)
            return self.cleaned

        def observe_vault(*args, **kwargs):
            self.assertEqual(
                self.claim.verification_runs.get().status, VerificationRun.Status.RUNNING,
            )
            return None

        self.query.side_effect = observe_extraction
        self.vault.side_effect = observe_vault
        run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.create_run.assert_called_once_with(self.claim)
        self.start_run.assert_called_once()
        self.assertEqual(self.start_run.call_args.args[0].pk, run.pk)
        self.assertEqual(VerificationRun.objects.count(), 1)
        self.assertIsNone(run.triggered_by_id)
        self.assertEqual(
            run.pipeline_version, VerificationRun._meta.get_field("pipeline_version").get_default(),
        )

    def test_repeated_url_attempts_create_distinct_runs(self):
        first = self._execute()
        second = self._execute()
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.claim.verification_runs.count(), 2)

    def test_out_of_scope_abstains(self):
        self.cleaned["cleaned_claim"] = "OUT_OF_SCOPE"
        self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "OUT_OF_SCOPE")
        self.vault.assert_not_called()
        self.bridge.assert_not_called()
        self.retrieve_tavily.assert_not_called()

    def test_satire_completes(self):
        self.cleaned["article_stance"] = "SATIRE"
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "SATIRE")
        self.assertEqual(self.save_claim.call_args.args[4], self.url)
        self.vault.assert_not_called()
        self.bridge.assert_not_called()

    def test_vault_substantive_verdict_completes_before_gfc(self):
        self.vault.return_value = {
            "canonical_claim": "Verified claim.", "verdict": "False",
            "summary": "Verified summary.", "sources": ["https://example.com/vault"],
        }
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.save_claim.assert_called_once_with(
            self.claim.pk, self.verdict, "TruthLens Verified Vault",
            "Verified summary.", ["https://example.com/vault"],
        )
        self.bridge.assert_not_called()
        self.retrieve_tavily.assert_not_called()

    def test_gfc_receives_active_running_run_and_completes(self):
        observed = []

        def observe_bridge(*args, **kwargs):
            run = kwargs["verification_run"]
            observed.append(run.pk)
            self.assertEqual(run.status, VerificationRun.Status.RUNNING)
            self.assertEqual(
                VerificationRun.objects.get(pk=run.pk).status, VerificationRun.Status.RUNNING,
            )
            return self.payload

        self.bridge.side_effect = observe_bridge
        run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.assertEqual(observed, [run.pk])
        self.bridge.assert_called_once_with(
            self.cleaned["search_query"], self.claim.pk,
            stage_prefix="url_", verification_run=run,
        )
        self.evaluate_gfc.assert_called_once_with(
            self.cleaned["cleaned_claim"], self.payload, "NEUTRAL",
        )
        self.save_claim.assert_called_once_with(
            self.claim.pk, self.verdict, "Official Fact Check",
            self.cleaned_text, ["https://example.com/fact-check"],
        )
        self.retrieve_tavily.assert_not_called()
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_gfc_persisted_evidence_links_through_existing_bridge(self):
        self.bridge.side_effect = self.real_bridge
        raw_sources = [RawEvidence(
            provider="GOOGLE_FACT_CHECK", url="https://example.com/fact-check",
            content="Rating: False", source_type="FACT_CHECK",
        )]
        with patch("api.tasks.GoogleFactCheckProvider") as provider:
            provider.return_value.search_with_payload.return_value = (self.payload, raw_sources)
            run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        self.assertEqual(link.verification_run_id, run.pk)
        self.assertEqual(link.evidence_source_id, EvidenceSource.objects.get().pk)
        self.assertEqual(link.evidence_role, VerificationEvidence.EvidenceRole.FACT_CHECK)
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.assertIsNone(link.recency_score)

    def test_gfc_failure_then_tavily_completes_same_run(self):
        observed = []

        def fail_bridge(*args, **kwargs):
            observed.append(kwargs["verification_run"].pk)
            raise requests.HTTPError("GFC unavailable")

        self.bridge.side_effect = fail_bridge
        run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.assertEqual(observed, [run.pk])
        self.assertEqual(self.claim.verification_runs.count(), 1)
        self.retrieve_tavily.assert_called_once()
        self.fail_run.assert_not_called()
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_provider_verdicts_use_required_terminal_mapping(self):
        for provider in ("vault", "gfc", "tavily"):
            for verdict in ("FACT", "FAKE", "MISLEADING", "SATIRE",
                            "OUT_OF_SCOPE", "UNVERIFIED", None, "UNKNOWN"):
                with self.subTest(provider=provider, verdict=verdict):
                    self.vault.return_value = (
                        {"canonical_claim": "Claim", "verdict": "False", "summary": "Summary"}
                        if provider == "vault" else None
                    )
                    self.bridge.return_value = {"claims": []} if provider == "tavily" else self.payload
                    self.verdict["verdict"] = verdict
                    expected = (
                        VerificationRun.Status.COMPLETED
                        if verdict in ("FACT", "FAKE", "MISLEADING", "SATIRE")
                        else VerificationRun.Status.ABSTAINED
                    )
                    self._assert_terminal(self._execute(), expected)

    def test_missing_verdict_abstains(self):
        self.verdict.pop("verdict")
        self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)

    def test_tavily_missing_verdict_abstains(self):
        self.bridge.return_value = {"claims": []}
        self.verdict.pop("verdict")
        self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)
        self.retrieve_tavily.assert_called_once()

    def test_tavily_query_is_truncated_before_bridge_call(self):
        self.bridge.return_value = {"claims": []}
        self.cleaned["search_query"] = "Long search query " * 30
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.retrieve_tavily.assert_called_once_with(
            self.cleaned["search_query"][:300], self.claim.pk, stage_prefix="url_",
        )

    def test_handled_tavily_failure_abstains(self):
        self.bridge.return_value = {"claims": []}
        self.retrieve_tavily.side_effect = requests.Timeout("Tavily timed out")
        self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.fail_run.assert_not_called()

    def test_unrecovered_failure_records_metadata_and_preserves_exception(self):
        error = RuntimeError("Vault unavailable: " + "details " * 30)
        self.vault.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self._execute()
        self.assertIs(raised.exception, error)
        run = self.claim.verification_runs.get()
        self._assert_terminal(run, VerificationRun.Status.FAILED)
        self.assertEqual(run.failure_stage, "url_fact_check_pipeline")
        self.assertEqual(run.failure_code, "UNHANDLED_EXCEPTION")
        self.assertEqual(run.failure_message, str(error))
        self.assertTrue(Claim.objects.filter(pk=self.claim.pk).exists())
        self.save_claim.assert_not_called()
        self.bridge.assert_not_called()

    def test_finalization_failure_preserves_propagating_original_exception(self):
        original = RuntimeError("Original vault failure")
        storage = RuntimeError("Lifecycle storage unavailable")
        self.vault.side_effect = original
        self.fail_run.side_effect = storage
        with self.assertLogs("api.tasks", level="ERROR") as logs:
            with self.assertRaises(RuntimeError) as raised:
                self._execute()
        self.assertIs(raised.exception, original)
        self.assertEqual(self.fail_run.call_args.kwargs["failure_message"], str(original))
        self.assertIn("VerificationRun finalization failed", "\n".join(logs.output))
        self.assertIn(str(storage), "\n".join(logs.output))
        self.complete_run.assert_not_called()
        self.abstain_run.assert_not_called()

    def test_terminal_failure_does_not_attempt_alternate_transition(self):
        for verdict, helper in (("FAKE", self.complete_run), ("UNVERIFIED", self.abstain_run)):
            with self.subTest(verdict=verdict):
                self.verdict["verdict"] = verdict
                error = RuntimeError("Terminal storage unavailable")
                helper.side_effect = error
                try:
                    with self.assertRaises(RuntimeError) as raised:
                        self._execute()
                    self.assertIs(raised.exception, error)
                    self.assertEqual(
                        self.claim.verification_runs.latest("created_at").status,
                        VerificationRun.Status.RUNNING,
                    )
                finally:
                    helper.side_effect = None
        self.fail_run.assert_not_called()
        self.retrieve_tavily.assert_not_called()

    def test_create_failure_prevents_verification(self):
        error = RuntimeError("Create unavailable")
        self.create_run.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self._invoke()
        self.assertIs(raised.exception, error)
        self.assertEqual(VerificationRun.objects.count(), 0)
        self.start_run.assert_not_called()
        self.assertEqual(self._terminal_count(), 0)
        self.vault.assert_not_called()
        self.bridge.assert_not_called()

    def test_start_failure_prevents_verification(self):
        error = RuntimeError("Start unavailable")
        self.start_run.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self._invoke()
        self.assertIs(raised.exception, error)
        self.assertEqual(self.claim.verification_runs.get().status, VerificationRun.Status.PENDING)
        self.assertEqual(self._terminal_count(), 0)
        self.vault.assert_not_called()
        self.bridge.assert_not_called()
