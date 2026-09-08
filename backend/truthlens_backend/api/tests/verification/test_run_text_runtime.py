from unittest.mock import patch

import requests
from django.test import TestCase

from api import tasks
from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification.contracts import RawEvidence
from api.verification import runs


class VerificationRunTextRuntimeTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Raw submitted claim.",
        )
        self.evidence_count = VerificationEvidence.objects.count()
        self.cleaned = {
            "cleaned_claim": "Example public claim.",
            "search_query": "example public claim",
            "article_stance": "NEUTRAL",
        }
        self.verdict = {
            "verdict": "FAKE",
            "summary": "The retrieved evidence refutes this claim.",
            "confidence_score": 95,
        }
        self.gfc_payload = {
            "claims": [{
                "text": self.cleaned["cleaned_claim"],
                "claimReview": [{
                    "publisher": {"name": "Example Checker"},
                    "url": "https://example.com/fact-check",
                    "textualRating": "False",
                }],
            }],
        }
        self.fingerprint = self._patch(
            "api.claim_matching.compute_fingerprint", return_value="txt:vrt-1"
        )
        self.match = self._patch(
            "api.claim_matching.find_matching_claim", return_value=None
        )
        self.clean = self._patch("api.tasks.clean_ocr_text", return_value=self.cleaned)
        self.vault = self._patch("api.tasks.search_official_vault", return_value=None)
        self.retrieve_gfc = self._patch(
            "api.tasks._retrieve_and_ingest_gfc", return_value=self.gfc_payload
        )
        self.relevance = self._patch("api.tasks.is_fact_check_relevant", return_value=True)
        self.evaluate_gfc = self._patch(
            "api.tasks.evaluate_image_claim_with_gfc", return_value=self.verdict
        )
        self.evaluate_tavily = self._patch(
            "api.tasks.evaluate_image_claim_with_tavily", return_value=self.verdict
        )
        self.tavily = self._patch("api.tasks.TavilyClient")
        self.tavily.return_value.search.return_value = {
            "answer": "Web evidence answer.",
            "results": [{
                "title": "Web Result",
                "url": "https://example.com/web",
                "content": "Relevant web evidence.",
            }],
        }
        self._patch("api.embedding_service.generate_embedding", return_value=None)
        self._patch("api.tasks._log_stage")
        self.save_claim = self._patch("api.tasks._save_claim", wraps=tasks._save_claim)
        self.create_run = self._patch(
            "api.tasks.create_verification_run", wraps=runs.create_verification_run
        )
        self.start_run = self._patch(
            "api.tasks.start_verification_run", wraps=runs.start_verification_run
        )
        self.complete_run = self._patch(
            "api.tasks.complete_verification_run", wraps=runs.complete_verification_run
        )
        self.abstain_run = self._patch(
            "api.tasks.abstain_verification_run", wraps=runs.abstain_verification_run
        )
        self.fail_run = self._patch(
            "api.tasks.fail_verification_run", wraps=runs.fail_verification_run
        )

    def _patch(self, target, **kwargs):
        patcher = patch(target, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def _terminal_count(self):
        return sum(helper.call_count for helper in (
            self.complete_run, self.abstain_run, self.fail_run
        ))

    def _execute(self):
        terminal_count = self._terminal_count()
        try:
            tasks.execute_core_text_pipeline(self.claim.context_text, self.claim.id)
        finally:
            self.assertLessEqual(self._terminal_count() - terminal_count, 1)
            self.assertEqual(VerificationEvidence.objects.count(), self.evidence_count)
        self.assertEqual(self._terminal_count() - terminal_count, 1)
        return self.claim.verification_runs.latest("created_at")

    def _assert_terminal(self, run, status):
        self.assertEqual(run.status, status)
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.completed_at)
        self.assertLessEqual(run.started_at, run.completed_at)
        if status != VerificationRun.Status.FAILED:
            self.assertIsNone(run.failure_stage)
            self.assertIsNone(run.failure_code)
            self.assertIsNone(run.failure_message)

    def _assert_no_verification_work(self):
        for mocked in (
            self.fingerprint, self.match, self.clean, self.vault,
            self.retrieve_gfc, self.evaluate_gfc, self.tavily, self.evaluate_tavily,
        ):
            mocked.assert_not_called()

    def _cached_claim(self, ai_verdict, final_verdict=None):
        cached = Claim.objects.create(
            context_text="Previously verified claim.",
            ai_verdict=ai_verdict,
            final_verdict=final_verdict,
            ai_summary="Cached summary.",
            consensus_score=91,
            source_type="Official Fact Check",
            source_link="https://example.com/cached",
            top_verdict_source="https://example.com/cached",
            ai_sources=["https://example.com/cached"],
            is_ai_generated=True,
        )
        self.match.return_value = cached
        return cached

    def test_one_run_per_invocation_preserves_defaults(self):
        run = self._execute()

        self.assertEqual(VerificationRun.objects.count(), 1)
        self.assertEqual(run.claim_id, self.claim.id)
        self.assertEqual(
            run.pipeline_version,
            VerificationRun._meta.get_field("pipeline_version").get_default(),
        )
        self.assertIsNone(run.triggered_by)
        self.create_run.assert_called_once_with(self.claim)
        self.start_run.assert_called_once()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)

    def test_repeated_attempts_create_distinct_runs(self):
        first = self._execute()
        second = self._execute()

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.claim.verification_runs.count(), 2)
        self.assertEqual(self.create_run.call_count, 2)
        self.assertEqual(self.complete_run.call_count, 2)

    def test_run_is_running_before_dedup_and_verification(self):
        def assert_running(result):
            def callback(*args, **kwargs):
                run = self.claim.verification_runs.get()
                self.assertEqual(run.status, VerificationRun.Status.RUNNING)
                self.assertIsNotNone(run.started_at)
                self.assertIsNone(run.completed_at)
                return result
            return callback

        self.fingerprint.side_effect = assert_running("txt:vrt-1")
        self.match.side_effect = assert_running(None)
        self.clean.side_effect = assert_running(self.cleaned)
        self._execute()
        self.match.assert_called_once_with(
            "txt:vrt-1", "TEXT", context_text=self.claim.context_text,
            allow_semantic_fallback=False,
        )

    def test_cached_substantive_ai_verdicts_complete_and_preserve_ai_fields(self):
        for verdict in ("FACT", "FAKE", "MISLEADING", "SATIRE"):
            with self.subTest(verdict=verdict):
                cached = self._cached_claim(verdict)
                run = self._execute()
                self._assert_terminal(run, VerificationRun.Status.COMPLETED)
                self.claim.refresh_from_db()
                for field in (
                    "ai_verdict", "ai_summary", "consensus_score",
                    "source_type", "source_link", "top_verdict_source", "ai_sources",
                    "is_ai_generated",
                ):
                    self.assertEqual(getattr(self.claim, field), getattr(cached, field))
                self.assertIsNone(self.claim.final_verdict)
                self.assertEqual(
                    self.claim.score_context,
                    "This result was matched from a prior analysis of the same claim.",
                )
        self.clean.assert_not_called()
        self.retrieve_gfc.assert_not_called()
        self.tavily.assert_not_called()
        self.save_claim.assert_not_called()

    def test_cached_abstaining_verdicts_abstain(self):
        for verdict in ("OUT_OF_SCOPE", "UNVERIFIED", None, "", "UNKNOWN"):
            with self.subTest(verdict=verdict):
                self._cached_claim(verdict)
                self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)
        self.clean.assert_not_called()
        self.tavily.assert_not_called()

    def test_cached_human_verdict_is_not_copied_or_used_as_run_outcome(self):
        for ai_verdict, final_verdict, status in (
            ("UNVERIFIED", "FACT", VerificationRun.Status.ABSTAINED),
            ("FACT", "UNVERIFIED", VerificationRun.Status.COMPLETED),
        ):
            with self.subTest(final_verdict=final_verdict):
                self._cached_claim(ai_verdict, final_verdict)
                self._assert_terminal(self._execute(), status)
                self.claim.refresh_from_db()
                self.assertEqual(self.claim.ai_verdict, ai_verdict)
                self.assertIsNone(self.claim.final_verdict)

    def test_self_match_continues_verification_with_one_run(self):
        self.match.return_value = self.claim
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.clean.assert_called_once()
        self.assertEqual(self.claim.verification_runs.count(), 1)

    def test_out_of_scope_abstains(self):
        self.cleaned["cleaned_claim"] = "OUT_OF_SCOPE"
        self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "OUT_OF_SCOPE")
        self.assertIsNone(self.claim.final_verdict)
        self.vault.assert_not_called()
        self.retrieve_gfc.assert_not_called()
        self.tavily.assert_not_called()

    def test_satire_shortcut_completes(self):
        self.cleaned["article_stance"] = "SATIRE"
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "SATIRE")
        self.vault.assert_not_called()
        self.retrieve_gfc.assert_not_called()
        self.tavily.assert_not_called()

    def test_vault_substantive_verdict_completes(self):
        self.vault.return_value = {
            "canonical_claim": "Verified public claim.", "verdict": "False",
            "summary": "Verified summary.", "sources": ["https://example.com/vault"],
        }
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.save_claim.assert_called_once_with(
            self.claim.id, self.verdict, "TruthLens Verified Vault",
            "Verified summary.", ["https://example.com/vault"],
        )
        self.retrieve_gfc.assert_not_called()
        self.tavily.assert_not_called()

    def test_gfc_substantive_verdict_completes(self):
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.retrieve_gfc.assert_called_once_with(
            self.cleaned["search_query"], self.claim.id,
            verification_run=self.claim.verification_runs.get(),
        )
        self.evaluate_gfc.assert_called_once_with(
            self.cleaned["cleaned_claim"], self.gfc_payload, "NEUTRAL"
        )
        self.save_claim.assert_called_once_with(
            self.claim.id, self.verdict, "Official Fact Check",
            self.cleaned["cleaned_claim"], ["https://example.com/fact-check"],
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "FAKE")
        self.assertIsNone(self.claim.final_verdict)
        self.tavily.assert_not_called()

    def test_tavily_substantive_verdict_completes(self):
        self.retrieve_gfc.return_value = {"claims": []}
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.tavily.return_value.search.assert_called_once()
        self.evaluate_gfc.assert_not_called()
        self.assertEqual(self.save_claim.call_args.args[2], "Live Web Search")
        self.assertEqual(self.save_claim.call_args.args[4], [{
            "url": "https://example.com/web", "title": "Web Result",
            "snippet": "Relevant web evidence....",
        }])

    def test_provider_selected_abstaining_verdicts_abstain(self):
        for provider in ("vault", "gfc", "tavily"):
            for verdict in ("OUT_OF_SCOPE", "UNVERIFIED", None, "UNKNOWN"):
                with self.subTest(provider=provider, verdict=verdict):
                    self.vault.return_value = (
                        {"canonical_claim": "Claim.", "verdict": "False", "summary": "Summary."}
                        if provider == "vault" else None
                    )
                    self.retrieve_gfc.return_value = (
                        {"claims": []} if provider == "tavily" else self.gfc_payload
                    )
                    self.verdict["verdict"] = verdict
                    self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)

    def test_provider_failure_then_successful_fallback_does_not_fail_run(self):
        self.retrieve_gfc.side_effect = requests.HTTPError("Google unavailable")
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.fail_run.assert_not_called()
        self.tavily.return_value.search.assert_called_once()
        self.assertEqual(self.save_claim.call_args.args[2], "Live Web Search")

    def test_irrelevant_gfc_results_continue_to_tavily(self):
        self.relevance.return_value = False
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.evaluate_gfc.assert_not_called()
        self.tavily.return_value.search.assert_called_once()

    def test_gfc_evaluation_failure_continues_to_tavily(self):
        self.evaluate_gfc.side_effect = RuntimeError("GFC evaluation unavailable")
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.fail_run.assert_not_called()
        self.tavily.return_value.search.assert_called_once()

    def test_handled_tavily_failure_abstains(self):
        self.retrieve_gfc.return_value = {"claims": []}
        self.tavily.return_value.search.side_effect = requests.Timeout("Tavily timed out")
        self._assert_terminal(self._execute(), VerificationRun.Status.ABSTAINED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertEqual(self.claim.consensus_score, 40)
        self.fail_run.assert_not_called()

    def test_fatal_core_exception_fails_with_original_metadata(self):
        error = RuntimeError("Preprocessor unavailable: " + "details " * 30)
        self.clean.side_effect = error
        run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.FAILED)
        self.assertEqual(run.failure_stage, "core_text_pipeline")
        self.assertEqual(run.failure_code, "UNHANDLED_EXCEPTION")
        self.assertEqual(run.failure_message, str(error))
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertIsNone(self.claim.final_verdict)
        self.assertEqual(self.claim.ai_summary, "An error occurred during analysis.")
        self.retrieve_gfc.assert_not_called()
        self.tavily.assert_not_called()

    def test_dedup_exception_fails_run_and_preserves_propagation(self):
        error = RuntimeError("Matching failed")
        self.match.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self._execute()
        self.assertIs(raised.exception, error)
        run = self.claim.verification_runs.get()
        self._assert_terminal(run, VerificationRun.Status.FAILED)
        self.assertEqual(run.failure_message, str(error))
        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.ai_verdict)
        self.clean.assert_not_called()

    def test_create_failure_prevents_verification(self):
        error = RuntimeError("Run creation unavailable")
        self.create_run.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self._execute()
        self.assertIs(raised.exception, error)
        self.assertEqual(VerificationRun.objects.count(), 0)
        self.start_run.assert_not_called()
        self.assertEqual(self._terminal_count(), 0)
        self._assert_no_verification_work()

    def test_start_failure_prevents_verification(self):
        error = RuntimeError("Run start unavailable")
        self.start_run.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self._execute()
        self.assertIs(raised.exception, error)
        self.assertEqual(self.claim.verification_runs.get().status, VerificationRun.Status.PENDING)
        self.assertEqual(self._terminal_count(), 0)
        self._assert_no_verification_work()

    def test_terminal_failure_propagates_without_an_alternate_transition(self):
        for outcome, helper in (
            ("completed", self.complete_run),
            ("abstained", self.abstain_run),
            ("failed", self.fail_run),
        ):
            with self.subTest(outcome=outcome):
                self.cleaned["cleaned_claim"] = (
                    "OUT_OF_SCOPE" if outcome == "abstained" else "Example public claim."
                )
                self.clean.side_effect = (
                    RuntimeError("Core failure") if outcome == "failed" else None
                )
                error = RuntimeError("Terminal storage unavailable")
                helper.side_effect = error
                before = self._terminal_count()
                try:
                    with self.assertRaises(RuntimeError) as raised:
                        self._execute()
                    self.assertIs(raised.exception, error)
                    self.assertEqual(self._terminal_count() - before, 1)
                    self.assertEqual(
                        self.claim.verification_runs.latest("created_at").status,
                        VerificationRun.Status.RUNNING,
                    )
                finally:
                    helper.side_effect = None
        self.tavily.assert_not_called()

    def test_terminal_failure_does_not_mask_propagating_runtime_exception(self):
        original_error = RuntimeError("Original matching error")
        lifecycle_error = RuntimeError("Failure metadata storage unavailable")
        self.match.side_effect = original_error
        self.fail_run.side_effect = lifecycle_error

        with self.assertLogs("api.tasks", level="ERROR") as logs:
            with self.assertRaises(RuntimeError) as raised:
                self._execute()

        self.assertIs(raised.exception, original_error)
        self.fail_run.assert_called_once()
        self.complete_run.assert_not_called()
        self.abstain_run.assert_not_called()
        self.assertIn("VerificationRun finalization failed", "\n".join(logs.output))
        self.assertIn(str(lifecycle_error), "\n".join(logs.output))
        self.assertEqual(self.fail_run.call_args.kwargs["failure_message"], str(original_error))


class VerificationEvidenceTextRuntimeTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(context_text="Raw submitted claim.")
        self.cleaned = {
            "cleaned_claim": "Example public claim.",
            "search_query": "example public claim",
            "article_stance": "NEUTRAL",
        }
        self.verdict = {"verdict": "FAKE", "summary": "Fact check summary.", "confidence_score": 95}
        self.payload = {"claims": [{
            "text": self.cleaned["cleaned_claim"],
            "claimReview": [{"url": "https://example.com/fact-check", "textualRating": "False"}],
        }]}
        self.raw_sources = [RawEvidence(
            provider="GOOGLE_FACT_CHECK", url="https://example.com/fact-check",
            content="Rating: False", source_type="FACT_CHECK",
        )]
        self.enterContext(patch("api.claim_matching.compute_fingerprint", return_value="txt:vel-1"))
        self.enterContext(patch("api.claim_matching.find_matching_claim", return_value=None))
        self.enterContext(patch("api.tasks.clean_ocr_text", return_value=self.cleaned))
        self.enterContext(patch("api.tasks.search_official_vault", return_value=None))
        self.enterContext(patch("api.embedding_service.generate_embedding", return_value=None))
        self.enterContext(patch("api.tasks._log_stage"))
        self.relevance = self.enterContext(patch("api.tasks.is_fact_check_relevant", return_value=True))
        self.evaluate_gfc = self.enterContext(patch(
            "api.tasks.evaluate_image_claim_with_gfc", return_value=self.verdict,
        ))
        self.enterContext(patch("api.tasks.evaluate_image_claim_with_tavily", return_value=self.verdict))
        self.provider = self.enterContext(patch("api.tasks.GoogleFactCheckProvider")).return_value
        self.provider.search_with_payload.return_value = (self.payload, self.raw_sources)
        self.tavily = self.enterContext(patch("api.tasks.TavilyClient")).return_value
        self.tavily_response = {
            "answer": "Web evidence.",
            "results": [{"url": "https://example.com/web", "title": "Web source", "content": "Evidence."}],
        }
        self.tavily.search.return_value = self.tavily_response
        self.terminals = [self.enterContext(patch(
            f"api.tasks.{name}_verification_run", wraps=getattr(runs, f"{name}_verification_run"),
        )) for name in ("complete", "abstain", "fail")]

        real_bridge = tasks._retrieve_and_ingest_gfc
        self.observed_runs = []

        def record_running_run(*args, **kwargs):
            run = kwargs["verification_run"]
            persisted = VerificationRun.objects.get(pk=run.pk)
            self.observed_runs.append((run.pk, run.status, persisted.status))
            return real_bridge(*args, **kwargs)

        self.bridge = self.enterContext(patch(
            "api.tasks._retrieve_and_ingest_gfc", side_effect=record_running_run,
        ))

    def _execute(self):
        before = sum(helper.call_count for helper in self.terminals)
        observations_before = len(self.observed_runs)
        tasks.execute_core_text_pipeline(self.claim.context_text, self.claim.pk)
        run = self.claim.verification_runs.latest("created_at")
        self.assertEqual(sum(helper.call_count for helper in self.terminals) - before, 1)
        self.assertEqual(self.observed_runs[observations_before:], [
            (run.pk, VerificationRun.Status.RUNNING, VerificationRun.Status.RUNNING),
        ])
        self.assertIsNone(run.failure_stage)
        self.assertIsNone(run.failure_code)
        self.assertIsNone(run.failure_message)
        return run

    def _record_links_at_fallback(self, **kwargs):
        self.links_at_fallback = list(VerificationEvidence.objects.values_list("evidence_source_id", flat=True))
        return self.tavily_response

    def test_text_runtime_passes_active_running_run_to_gfc_bridge(self):
        run = self._execute()
        self.bridge.assert_called_once_with(
            self.cleaned["search_query"], self.claim.pk, verification_run=run,
        )
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assertEqual(VerificationEvidence.objects.get().verification_run_id, run.pk)

    def test_text_gfc_success_links_evidence_and_preserves_completion(self):
        run = self._execute()
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        self.assertEqual(link.verification_run_id, run.pk)
        self.assertEqual(link.evidence_source_id, EvidenceSource.objects.get().pk)
        self.assertEqual(link.evidence_role, VerificationEvidence.EvidenceRole.FACT_CHECK)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "FAKE")
        self.assertIsNone(self.claim.final_verdict)
        self.assertEqual(self.claim.source_type, "Official Fact Check")
        self.assertEqual(self.claim.ai_sources, ["https://example.com/fact-check"])
        self.tavily.search.assert_not_called()

    def test_irrelevant_gfc_evidence_remains_linked_before_tavily_fallback(self):
        self.relevance.return_value = False
        self.tavily.search.side_effect = self._record_links_at_fallback
        run = self._execute()
        self.tavily.search.assert_called_once()
        self.assertEqual(self.links_at_fallback, [EvidenceSource.objects.get().pk])
        self.assertEqual(VerificationEvidence.objects.get().verification_run_id, run.pk)
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.evaluate_gfc.assert_not_called()

    def test_gfc_evaluation_failure_keeps_links_before_tavily_fallback(self):
        self.evaluate_gfc.side_effect = RuntimeError("Evaluator unavailable")
        self.tavily.search.side_effect = self._record_links_at_fallback
        run = self._execute()
        self.tavily.search.assert_called_once()
        self.assertEqual(self.links_at_fallback, [EvidenceSource.objects.get().pk])
        self.assertEqual(VerificationEvidence.objects.get().verification_run_id, run.pk)
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)

    def test_gfc_provider_failure_falls_back_without_links(self):
        self.provider.search_with_payload.side_effect = requests.HTTPError("Provider unavailable")
        run = self._execute()
        self.tavily.search.assert_called_once()
        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_linking_failure_preserves_vrt1_terminal_status(self):
        for verdict, expected in (
            ("FACT", VerificationRun.Status.COMPLETED),
            ("UNVERIFIED", VerificationRun.Status.ABSTAINED),
            ("OUT_OF_SCOPE", VerificationRun.Status.ABSTAINED),
        ):
            with self.subTest(verdict=verdict):
                self.verdict["verdict"] = verdict
                with patch(
                    "api.tasks.link_evidence_sources_to_run", side_effect=RuntimeError("Link storage failed"),
                ):
                    run = self._execute()
                self.assertEqual(run.status, expected)
                self.assertEqual(EvidenceSource.objects.count(), 1)
                self.assertEqual(VerificationEvidence.objects.count(), 0)
                self.claim.refresh_from_db()
                self.assertEqual(self.claim.ai_verdict, verdict)
        self.tavily.search.assert_not_called()
        self.terminals[2].assert_not_called()
