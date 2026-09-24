from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from django.test import TestCase

from api import services, tasks
from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification import runs
from api.verification.contracts import RawEvidence
from api.verification.evidence_assessment import EvidenceAssessment
from api.verification.evidence_dossier import ReasoningEvidenceItem
from api.services import ClaimGateError, LLMProviderUnavailableError


class VerificationRunURLRuntimeTests(TestCase):
    def setUp(self):
        self.url = "https://example.com/article"
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Submitted URL claim.",
        )
        self.cleaned_text = "Cleaned article content."
        self.cleaned = {
            "cleaned_claim": "Example public claim.",
            "search_query": "example public claim",
            "article_stance": "NEUTRAL",
        }
        self.verdict = {
            "verdict": "FAKE",
            "summary": "Evidence refutes the claim.",
            "confidence_score": 95,
        }
        self.payload = {
            "claims": [
                {
                    "text": self.cleaned["cleaned_claim"],
                    "claimReview": [
                        {
                            "url": "https://example.com/fact-check",
                            "textualRating": "False",
                        }
                    ],
                }
            ]
        }
        self.response = Mock(status_code=200)
        self.response.json.return_value = {
            "results": [{"raw_content": "Raw article content."}],
        }
        self.extract = self._patch(
            "api.tasks.requests.post", return_value=self.response
        )
        self.clean = self._patch(
            "api.tasks.clean_extracted_text",
            return_value=self.cleaned_text,
        )
        self.query = self._patch(
            "api.tasks.extract_search_query", return_value=self.cleaned
        )
        self.vault = self._patch("api.tasks.search_official_vault", return_value=None)
        self.real_bridge = tasks._retrieve_and_ingest_gfc
        self.bridge = self._patch(
            "api.tasks._retrieve_and_ingest_gfc",
            return_value=self.payload,
        )
        self.relevance = self._patch(
            "api.tasks.is_fact_check_relevant", return_value=True
        )
        self.evaluate_gfc = self._patch(
            "api.tasks.evaluate_url_claim_with_gfc",
            return_value=self.verdict,
        )
        self.evaluate_tavily = self._patch(
            "api.tasks.evaluate_url_claim_with_tavily",
            return_value=self.verdict,
        )
        self.real_load_dossier = tasks.load_reasoning_evidence_dossier_for_run
        self.real_filter_dossier = tasks.filter_reasoning_evidence_dossier_by_role
        self.real_render_dossier = tasks.render_reasoning_evidence_dossier
        self.evaluate_persisted = self._patch(
            "api.tasks.evaluate_claim_with_persisted_evidence",
            return_value=self.verdict,
        )
        self.load_dossier = self._patch(
            "api.tasks.load_reasoning_evidence_dossier_for_run",
            return_value=["persisted dossier"],
        )
        self.filter_dossier = self._patch(
            "api.tasks.filter_reasoning_evidence_dossier_by_role",
            return_value=["selected evidence"],
        )
        self.render_dossier = self._patch(
            "api.tasks.render_reasoning_evidence_dossier",
            return_value="Persisted evidence context.",
        )
        self.assess_evidence = self._patch(
            "api.tasks._assess_and_persist_reasoning_evidence"
        )
        self.retrieve_tavily = self._patch("api.tasks._retrieve_and_ingest_tavily")
        self.retrieve_tavily.return_value = {
            "answer": "Web evidence answer.",
            "results": [
                {
                    "url": "https://example.com/web",
                    "title": "Web result",
                    "content": "Relevant web evidence.",
                }
            ],
        }
        self._patch("api.embedding_service.generate_embedding", return_value=None)
        self.log_stage = self._patch("api.tasks._log_stage")
        self.save_claim = self._patch("api.tasks._save_claim", wraps=tasks._save_claim)
        self.create_run = self._patch(
            "api.tasks.create_verification_run",
            wraps=runs.create_verification_run,
        )
        self.start_run = self._patch(
            "api.tasks.start_verification_run",
            wraps=runs.start_verification_run,
        )
        self.complete_run = self._patch(
            "api.tasks.complete_verification_run",
            wraps=runs.complete_verification_run,
        )
        self.abstain_run = self._patch(
            "api.tasks.abstain_verification_run",
            wraps=runs.abstain_verification_run,
        )
        self.fail_run = self._patch(
            "api.tasks.fail_verification_run",
            wraps=runs.fail_verification_run,
        )

    def _patch(self, target, **kwargs):
        return self.enterContext(patch(target, **kwargs))

    def _terminal_count(self):
        return sum(
            helper.call_count
            for helper in (
                self.complete_run,
                self.abstain_run,
                self.fail_run,
            )
        )

    def _invoke(self):
        return tasks.url_fact_check_process.run(self.url, self.claim.pk)

    def test_provider_scope_isolated_across_jobs_and_failure_exit(self):
        for failed_job in (False, True):
            with self.subTest(failed_job=failed_job):
                self.claim = Claim.objects.create(
                    claim_type=Claim.ClaimType.URL,
                    context_text="First scoped URL claim.",
                )
                gemini = Mock()
                groq = Mock()
                gemini.models.generate_content.return_value = SimpleNamespace(
                    text='{"provider": "gemini"}',
                )
                gemini.models.generate_content.side_effect = RuntimeError(
                    "Gemini unavailable",
                )
                groq_response = SimpleNamespace(choices=[SimpleNamespace(
                    message=SimpleNamespace(content='{"provider": "groq"}'),
                )])
                groq.chat.completions.create.return_value = groq_response
                if failed_job:
                    groq.chat.completions.create.side_effect = [
                        groq_response, RuntimeError("Groq unavailable"),
                    ]

                def query_with_llm(*args, **kwargs):
                    services.call_llm_with_fallback("System", "Claim gate")
                    return self.cleaned

                def evaluate_with_llm(*args, **kwargs):
                    services.call_llm_with_fallback("System", "Final evaluation")
                    return self.verdict

                self.query.side_effect = query_with_llm
                self.evaluate_persisted.side_effect = evaluate_with_llm
                with patch("api.services.gemini_client", gemini), patch(
                    "api.services.groq_client", groq,
                ):
                    if failed_job:
                        with self.assertRaises(LLMProviderUnavailableError):
                            self._execute()
                        run = self.claim.verification_runs.get()
                        self.assertEqual(run.status, VerificationRun.Status.FAILED)
                        self.assertEqual(run.failure_code, "LLM_UNAVAILABLE")
                        self.claim.refresh_from_db()
                        self.assertIsNone(self.claim.ai_verdict)
                    else:
                        self._assert_terminal(
                            self._execute(), VerificationRun.Status.COMPLETED,
                        )
                    gemini.models.generate_content.assert_called_once()
                    self.assertEqual(groq.chat.completions.create.call_count, 2)

                    gemini.models.generate_content.side_effect = None
                    self.assertEqual(
                        services.call_llm_with_fallback("System", "After job"),
                        '{"provider": "gemini"}',
                    )
                    self.claim = Claim.objects.create(
                        claim_type=Claim.ClaimType.URL,
                        context_text="Independent scoped URL claim.",
                    )
                    self._assert_terminal(
                        self._execute(), VerificationRun.Status.COMPLETED,
                    )
                    self.assertEqual(gemini.models.generate_content.call_count, 4)
                    self.assertEqual(groq.chat.completions.create.call_count, 2)

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
                    self.cleaned["search_query"][:300],
                    self.claim.pk,
                    stage_prefix="url_",
                    verification_run=self.claim.verification_runs.latest("created_at"),
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
        self.evaluate_persisted.assert_not_called()
        self.load_dossier.assert_not_called()
        self.filter_dossier.assert_not_called()
        self.render_dossier.assert_not_called()
        self.assess_evidence.assert_not_called()
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

    def test_claim_gate_failure_preserves_claim_and_marks_run_failed(self):
        self.query.side_effect = ClaimGateError("ClaimGate analysis failed.")

        with self.assertRaises(ClaimGateError):
            self._invoke()

        self.assertTrue(Claim.objects.filter(pk=self.claim.pk).exists())

        run = self.claim.verification_runs.get()

        self._assert_terminal(
            run,
            VerificationRun.Status.FAILED,
        )

        self.assertEqual(
            run.failure_stage,
            "claim_gate",
        )
        self.assertEqual(
            run.failure_code,
            "CLAIM_GATE_FAILED",
        )

        self.claim.refresh_from_db()
        self.assertIsNone(self.claim.ai_verdict)
        self.assertIsNone(self.claim.final_verdict)

        self.save_claim.assert_not_called()
        self.vault.assert_not_called()
        self.bridge.assert_not_called()
        self.retrieve_tavily.assert_not_called()
        self.assess_evidence.assert_not_called()

    def test_run_is_running_during_claim_gate_and_verification(self):
        def observe_claim_gate(*args):
            run = self.claim.verification_runs.get()

            self.assertEqual(
                run.status,
                VerificationRun.Status.RUNNING,
            )

            return self.cleaned

        def observe_vault(*args, **kwargs):
            run = self.claim.verification_runs.get()

            self.assertEqual(
                run.status,
                VerificationRun.Status.RUNNING,
            )

            return None

        self.query.side_effect = observe_claim_gate
        self.vault.side_effect = observe_vault

        run = self._execute()

        self._assert_terminal(
            run,
            VerificationRun.Status.COMPLETED,
        )

        self.create_run.assert_called_once_with(self.claim, triggered_by=None)
        self.start_run.assert_called_once()

        self.assertEqual(
            self.start_run.call_args.args[0].pk,
            run.pk,
        )

        self.assertEqual(
            VerificationRun.objects.count(),
            1,
        )

        self.assertIsNone(run.triggered_by_id)

        self.assertEqual(
            run.pipeline_version,
            VerificationRun._meta.get_field("pipeline_version").get_default(),
        )

    def test_repeated_url_attempts_create_distinct_runs(self):
        first = self._execute()
        second = self._execute()
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.claim.verification_runs.count(), 2)

    def test_out_of_scope_abstains_without_persisting_verdict(self):
        self.cleaned["cleaned_claim"] = "OUT_OF_SCOPE"

        self._assert_terminal(
            self._execute(),
            VerificationRun.Status.ABSTAINED,
        )

        self.claim.refresh_from_db()

        self.assertIsNone(self.claim.ai_verdict)
        self.assertIsNone(self.claim.final_verdict)

        self.save_claim.assert_not_called()
        self.vault.assert_not_called()
        self.bridge.assert_not_called()
        self.retrieve_tavily.assert_not_called()
        self.assess_evidence.assert_not_called()

    def test_satire_completes(self):
        self.cleaned["article_stance"] = "SATIRE"
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "SATIRE")
        self.assertEqual(self.save_claim.call_args.args[4], self.url)
        self.vault.assert_called_once_with(
            "Example public claim.",
            target_claim=self.claim,
        )
        self.bridge.assert_not_called()
        self.assess_evidence.assert_not_called()

    def test_vault_substantive_verdict_completes_before_gfc(self):
        self.vault.return_value = {
            "canonical_claim": "Verified claim.",
            "verdict": "False",
            "summary": "Verified summary.",
            "sources": ["https://example.com/vault"],
        }
        self._assert_terminal(self._execute(), VerificationRun.Status.COMPLETED)
        self.save_claim.assert_called_once_with(
            self.claim.pk,
            self.verdict,
            "TruthLens Verified Vault",
            "Verified summary.",
            ["https://example.com/vault"],
        )
        self.bridge.assert_not_called()
        self.retrieve_tavily.assert_not_called()
        self.assess_evidence.assert_not_called()

    def test_gfc_receives_active_running_run_and_completes(self):
        observed = []

        def observe_bridge(*args, **kwargs):
            run = kwargs["verification_run"]
            observed.append(run.pk)
            self.assertEqual(run.status, VerificationRun.Status.RUNNING)
            self.assertEqual(
                VerificationRun.objects.get(pk=run.pk).status,
                VerificationRun.Status.RUNNING,
            )
            return self.payload

        self.bridge.side_effect = observe_bridge
        run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.assertEqual(observed, [run.pk])
        self.bridge.assert_called_once_with(
            self.cleaned["search_query"],
            self.claim.pk,
            stage_prefix="url_",
            verification_run=run,
        )
        self.evaluate_persisted.assert_called_once_with(
            self.cleaned["cleaned_claim"],
            "Persisted evidence context.",
            "NEUTRAL",
        )
        self.evaluate_gfc.assert_not_called()
        self.save_claim.assert_called_once_with(
            self.claim.pk,
            self.verdict,
            "Official Fact Check",
            self.cleaned_text,
            ["https://example.com/fact-check"],
        )
        self.retrieve_tavily.assert_not_called()
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_gfc_persisted_evidence_links_through_existing_bridge(self):
        self.bridge.side_effect = self.real_bridge
        raw_sources = [
            RawEvidence(
                provider="GOOGLE_FACT_CHECK",
                url="https://example.com/fact-check",
                content="Rating: False",
                source_type="FACT_CHECK",
            )
        ]
        with patch("api.tasks.GoogleFactCheckProvider") as provider:
            provider.return_value.search_with_payload.return_value = (
                self.payload,
                raw_sources,
            )
            self.load_dossier.side_effect = self.real_load_dossier
            self.filter_dossier.side_effect = self.real_filter_dossier
            self.render_dossier.side_effect = self.real_render_dossier
            run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        self.assertEqual(link.verification_run_id, run.pk)
        self.assertEqual(link.evidence_source_id, EvidenceSource.objects.get().pk)
        self.assertEqual(
            link.evidence_role, VerificationEvidence.EvidenceRole.FACT_CHECK
        )
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.assertIsNone(link.recency_score)
        persisted_source = EvidenceSource.objects.get()
        self.assertIsNotNone(persisted_source.content)
        self.evaluate_persisted.assert_called_once()
        evidence_context = self.evaluate_persisted.call_args.args[1]
        self.assertIn(persisted_source.content, evidence_context)
        self.assertNotIn("claimReview", evidence_context)
        self.evaluate_gfc.assert_not_called()

    def test_persisted_gfc_unverified_result_abstains_without_tavily_fallback(self):
        self.verdict["verdict"] = "UNVERIFIED"

        run = self._execute()

        self._assert_terminal(run, VerificationRun.Status.ABSTAINED)
        self.evaluate_persisted.assert_called_once_with(
            self.cleaned["cleaned_claim"],
            "Persisted evidence context.",
            "NEUTRAL",
        )
        self.evaluate_gfc.assert_not_called()
        self.retrieve_tavily.assert_not_called()

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
        self.evaluate_persisted.assert_called_once_with(
            self.cleaned["cleaned_claim"],
            "Persisted evidence context.",
            "NEUTRAL",
        )
        self.evaluate_tavily.assert_not_called()
        self.fail_run.assert_not_called()
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_missing_persisted_gfc_evidence_falls_through_to_tavily(self):
        self.render_dossier.side_effect = ["", "Persisted Tavily evidence."]

        run = self._execute()

        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.evaluate_gfc.assert_not_called()
        self.retrieve_tavily.assert_called_once()
        self.evaluate_persisted.assert_called_once_with(
            self.cleaned["cleaned_claim"],
            "Persisted Tavily evidence.",
            "NEUTRAL",
        )
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("url_gfc_persisted_evidence_unavailable", stages)
        self.assertNotIn("url_gfc_llm_evaluation", stages)

    def test_persisted_gfc_evaluator_exception_falls_through_to_tavily(self):
        self.evaluate_persisted.side_effect = [
            RuntimeError("GFC evaluator unavailable"),
            self.verdict,
        ]

        run = self._execute()

        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.retrieve_tavily.assert_called_once()
        self.assertEqual(self.evaluate_persisted.call_count, 2)
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("url_gfc_llm_evaluation_failed", stages)
        self.assertNotIn("url_gfc_llm_evaluation", stages)

    def test_missing_persisted_tavily_evidence_abstains_without_evaluation(self):
        self.bridge.return_value = {"claims": []}
        self.render_dossier.return_value = ""

        run = self._execute()

        self._assert_terminal(run, VerificationRun.Status.ABSTAINED)
        self.evaluate_gfc.assert_not_called()
        self.evaluate_tavily.assert_not_called()
        self.evaluate_persisted.assert_not_called()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertEqual(self.save_claim.call_args.args[1]["confidence_score"], 0)
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("url_tavily_persisted_evidence_unavailable", stages)
        self.assertNotIn("url_tavily_llm_evaluation", stages)

    def test_provider_verdicts_use_required_terminal_mapping(self):
        for provider in ("vault", "gfc", "tavily"):
            for verdict in (
                "FACT",
                "FAKE",
                "MISLEADING",
                "SATIRE",
                "OUT_OF_SCOPE",
                "UNVERIFIED",
                None,
                "UNKNOWN",
            ):
                with self.subTest(provider=provider, verdict=verdict):
                    self.vault.return_value = (
                        {
                            "canonical_claim": "Claim",
                            "verdict": "False",
                            "summary": "Summary",
                        }
                        if provider == "vault"
                        else None
                    )
                    self.bridge.return_value = (
                        {"claims": []} if provider == "tavily" else self.payload
                    )
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
        run = self._execute()
        self._assert_terminal(run, VerificationRun.Status.COMPLETED)
        self.retrieve_tavily.assert_called_once_with(
            self.cleaned["search_query"][:300],
            self.claim.pk,
            stage_prefix="url_",
            verification_run=run,
        )

    def test_missing_claim_compatibility_uses_legacy_gfc_evaluator(self):
        claim_queryset = Mock()
        claim_queryset.first.return_value = None

        with patch("api.tasks.Claim.objects.filter", return_value=claim_queryset):
            self._invoke()

        self.assertEqual(VerificationRun.objects.count(), 0)
        self.evaluate_gfc.assert_called_once_with(
            self.cleaned["cleaned_claim"],
            self.payload,
            "NEUTRAL",
        )
        self.evaluate_persisted.assert_not_called()
        self.load_dossier.assert_not_called()
        self.retrieve_tavily.assert_not_called()

    def test_missing_claim_compatibility_uses_legacy_tavily_evaluator(self):
        self.bridge.return_value = {"claims": []}
        claim_queryset = Mock()
        claim_queryset.first.return_value = None

        with patch("api.tasks.Claim.objects.filter", return_value=claim_queryset):
            self._invoke()

        self.assertEqual(VerificationRun.objects.count(), 0)
        self.evaluate_tavily.assert_called_once()
        combined_context = self.evaluate_tavily.call_args.args[1]
        self.assertIn(self.cleaned_text, combined_context)
        self.assertIn("Web evidence answer.", combined_context)
        self.assertIn("Relevant web evidence.", combined_context)
        self.evaluate_persisted.assert_not_called()
        self.load_dossier.assert_not_called()

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
        self.assertEqual(
            self.fail_run.call_args.kwargs["failure_message"], str(original)
        )
        self.assertIn("VerificationRun finalization failed", "\n".join(logs.output))
        self.assertIn(str(storage), "\n".join(logs.output))
        self.complete_run.assert_not_called()
        self.abstain_run.assert_not_called()

    def test_terminal_failure_does_not_attempt_alternate_transition(self):
        for verdict, helper in (
            ("FAKE", self.complete_run),
            ("UNVERIFIED", self.abstain_run),
        ):
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
        self.assertEqual(
            self.claim.verification_runs.get().status, VerificationRun.Status.PENDING
        )
        self.assertEqual(self._terminal_count(), 0)
        self.vault.assert_not_called()
        self.bridge.assert_not_called()


class VerificationEvidenceURLRuntimeTests(TestCase):
    def setUp(self):
        self.url = "https://example.com/article"
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.URL,
            context_text="Submitted URL article.",
        )
        self.cleaned_text = "Cleaned submitted article content."
        self.cleaned = {
            "cleaned_claim": "Example public claim.",
            "search_query": "example public claim",
            "article_stance": "NEUTRAL",
        }
        self.verdict = {
            "verdict": "FAKE",
            "summary": "Persisted evidence refutes the claim.",
            "confidence_score": 95,
        }
        self.gfc_payload = {
            "claims": [
                {
                    "text": self.cleaned["cleaned_claim"],
                    "claimReview": [
                        {
                            "url": "https://example.com/fact-check",
                            "textualRating": "False",
                        }
                    ],
                }
            ],
        }
        self.gfc_raw_sources = [
            RawEvidence(
                provider="GOOGLE_FACT_CHECK",
                url="https://example.com/fact-check",
                content="Rating: False",
                source_type="FACT_CHECK",
            )
        ]
        extraction_response = Mock(status_code=200)
        extraction_response.json.return_value = {
            "results": [{"raw_content": "Raw submitted URL article."}],
        }
        self.enterContext(
            patch(
                "api.tasks.requests.post",
                return_value=extraction_response,
            )
        )
        self.enterContext(
            patch(
                "api.tasks.clean_extracted_text",
                return_value=self.cleaned_text,
            )
        )
        self.enterContext(
            patch(
                "api.tasks.extract_search_query",
                return_value=self.cleaned,
            )
        )
        self.enterContext(
            patch(
                "api.tasks.search_official_vault",
                return_value=None,
            )
        )
        self.enterContext(
            patch(
                "api.embedding_service.generate_embedding",
                return_value=None,
            )
        )
        self.log_stage = self.enterContext(patch("api.tasks._log_stage"))
        self.relevance = self.enterContext(
            patch(
                "api.tasks.is_fact_check_relevant",
                return_value=True,
            )
        )
        self.evaluate_legacy_gfc = self.enterContext(
            patch(
                "api.tasks.evaluate_url_claim_with_gfc",
                return_value=self.verdict,
            )
        )
        self.evaluate_legacy_tavily = self.enterContext(
            patch(
                "api.tasks.evaluate_url_claim_with_tavily",
                return_value=self.verdict,
            )
        )
        self.evaluate_persisted = self.enterContext(
            patch(
                "api.tasks.evaluate_claim_with_persisted_evidence",
                return_value=self.verdict,
            )
        )
        self.assessment = EvidenceAssessment(
            stance=VerificationEvidence.Stance.REFUTES,
            relevance_score=0.9,
            directness_score=0.8,
        )
        self.assessor = self.enterContext(
            patch(
                "api.tasks.assess_reasoning_evidence_batch_against_claim",
                return_value=[self.assessment],
            )
        )
        self.gfc_provider = self.enterContext(
            patch("api.tasks.GoogleFactCheckProvider")
        ).return_value
        self.gfc_provider.search_with_payload.return_value = (
            self.gfc_payload,
            self.gfc_raw_sources,
        )
        self.retrieve_tavily = self.enterContext(
            patch("api.tasks._retrieve_and_ingest_tavily")
        )
        self.tavily_response = {
            "answer": "Raw Tavily provider answer.",
            "results": [
                {
                    "url": "https://example.com/web",
                    "title": "Web source",
                    "content": "Raw Tavily result content.",
                }
            ],
        }
        self.retrieve_tavily.return_value = self.tavily_response
        self.save_claim = self.enterContext(
            patch(
                "api.tasks._save_claim",
                wraps=tasks._save_claim,
            )
        )
        self.terminals = [
            self.enterContext(
                patch(
                    f"api.tasks.{name}_verification_run",
                    wraps=getattr(runs, f"{name}_verification_run"),
                )
            )
            for name in ("complete", "abstain", "fail")
        ]

        real_bridge = tasks._retrieve_and_ingest_gfc
        self.observed_runs = []

        def record_running_run(*args, **kwargs):
            run = kwargs["verification_run"]
            persisted = VerificationRun.objects.get(pk=run.pk)
            self.observed_runs.append((run.pk, run.status, persisted.status))
            return real_bridge(*args, **kwargs)

        self.bridge = self.enterContext(
            patch(
                "api.tasks._retrieve_and_ingest_gfc",
                side_effect=record_running_run,
            )
        )

    def _execute(self):
        terminal_calls_before = sum(helper.call_count for helper in self.terminals)
        tasks.url_fact_check_process.run(self.url, self.claim.pk)
        run = self.claim.verification_runs.latest("created_at")
        self.assertEqual(
            sum(helper.call_count for helper in self.terminals) - terminal_calls_before,
            1,
        )
        self.assertEqual(
            self.observed_runs,
            [
                (
                    run.pk,
                    VerificationRun.Status.RUNNING,
                    VerificationRun.Status.RUNNING,
                )
            ],
        )
        self.assertIsNone(run.failure_stage)
        self.assertIsNone(run.failure_code)
        self.assertIsNone(run.failure_message)
        return run

    def _record_tavily_link(
        self, search_query, claim_id, *, stage_prefix, verification_run
    ):
        self.assertEqual(stage_prefix, "url_")
        source = EvidenceSource.objects.create(
            provider="TAVILY",
            url="https://example.com/web",
            canonical_url="https://example.com/web",
            title="Persisted web source",
            content="Persisted Tavily evidence.",
        )
        VerificationEvidence.objects.create(
            verification_run=verification_run,
            evidence_source=source,
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )
        return self.tavily_response

    def test_relevant_gfc_evidence_is_assessed_persisted_and_reloaded(self):
        real_bridge = self.bridge.side_effect

        def add_recency_after_linking(*args, **kwargs):
            payload = real_bridge(*args, **kwargs)
            VerificationEvidence.objects.update(recency_score=0.55)
            return payload

        self.bridge.side_effect = add_recency_after_linking

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        link.refresh_from_db()
        self.assertEqual(
            link.evidence_role, VerificationEvidence.EvidenceRole.FACT_CHECK
        )
        self.assertEqual(link.stance, VerificationEvidence.Stance.REFUTES)
        self.assertEqual(link.relevance_score, 0.9)
        self.assertEqual(link.directness_score, 0.8)
        self.assertEqual(link.recency_score, 0.55)
        self.assessor.assert_called_once()
        assessed_claim, assessed_items = self.assessor.call_args.args
        assessed_item = assessed_items[0]
        self.assertEqual(assessed_claim, self.cleaned["cleaned_claim"])
        self.assertIsInstance(assessed_item, ReasoningEvidenceItem)
        self.assertEqual(assessed_item.evidence_link_id, link.pk)
        self.assertEqual(assessed_item.evidence_source_id, link.evidence_source_id)
        self.assertEqual(assessed_item.recency_score, 0.55)
        self.evaluate_persisted.assert_called_once()
        evidence_context = self.evaluate_persisted.call_args.args[1]
        self.assertIn("Rating: False", evidence_context)
        self.assertIn("Stance: REFUTES", evidence_context)
        self.assertIn("Relevance score: 0.9", evidence_context)
        self.assertIn("Directness score: 0.8", evidence_context)
        self.assertIn("Recency score: 0.55", evidence_context)
        self.assertNotIn(self.cleaned_text, evidence_context)
        self.evaluate_legacy_gfc.assert_not_called()
        self.retrieve_tavily.assert_not_called()
        self.assertIn(
            "url_gfc_evidence_assessment",
            [call.args[1] for call in self.log_stage.call_args_list],
        )

    def test_irrelevant_gfc_is_not_assessed_and_tavily_is_role_isolated(self):
        self.relevance.return_value = False
        self.retrieve_tavily.side_effect = self._record_tavily_link

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        gfc_link = VerificationEvidence.objects.get(
            evidence_source__provider="GOOGLE_FACT_CHECK"
        )
        tavily_link = VerificationEvidence.objects.get(
            evidence_source__provider="TAVILY"
        )
        gfc_link.refresh_from_db()
        tavily_link.refresh_from_db()
        self.assertEqual(gfc_link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(gfc_link.relevance_score)
        self.assertIsNone(gfc_link.directness_score)
        self.assertEqual(tavily_link.stance, VerificationEvidence.Stance.REFUTES)
        self.assertEqual(tavily_link.relevance_score, 0.9)
        self.assertEqual(tavily_link.directness_score, 0.8)
        self.assessor.assert_called_once()
        assessed_item = self.assessor.call_args.args[1][0]
        self.assertEqual(assessed_item.evidence_link_id, tavily_link.pk)
        self.assertEqual(
            assessed_item.evidence_role,
            VerificationEvidence.EvidenceRole.SECONDARY,
        )
        evidence_context = self.evaluate_persisted.call_args.args[1]
        self.assertIn("Persisted Tavily evidence.", evidence_context)
        self.assertIn("Stance: REFUTES", evidence_context)
        self.assertNotIn("Rating: False", evidence_context)
        self.assertNotIn(self.cleaned_text, evidence_context)
        self.assertNotIn("Raw Tavily provider answer.", evidence_context)
        self.assertNotIn("Raw Tavily result content.", evidence_context)
        self.assertNotIn("Original URL Content to Verify", evidence_context)
        self.assertNotIn("Top Search Results:", evidence_context)
        self.evaluate_legacy_tavily.assert_not_called()
        self.assertIn(
            "url_tavily_evidence_assessment",
            [call.args[1] for call in self.log_stage.call_args_list],
        )

    def test_any_existing_assessment_field_skips_assessor(self):
        self.gfc_provider.search_with_payload.return_value = ({"claims": []}, [])

        def add_assessed_links(
            search_query, claim_id, *, stage_prefix, verification_run
        ):
            existing_values = (
                {"stance": VerificationEvidence.Stance.CONTEXT},
                {"relevance_score": 0.6},
                {"directness_score": 0.3},
            )
            for index, values in enumerate(existing_values, start=1):
                source = EvidenceSource.objects.create(
                    provider="TAVILY",
                    canonical_url=f"https://example.com/existing-{index}",
                    content=f"Existing assessment {index}.",
                )
                VerificationEvidence.objects.create(
                    verification_run=verification_run,
                    evidence_source=source,
                    evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
                    **values,
                )
            return self.tavily_response

        self.retrieve_tavily.side_effect = add_assessed_links

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assessor.assert_not_called()
        self.assertEqual(VerificationEvidence.objects.count(), 3)
        self.evaluate_persisted.assert_called_once()

    def test_unknown_numeric_assessment_is_persisted_and_rendered(self):
        self.assessor.return_value = [
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.UNKNOWN,
                relevance_score=0.4,
                directness_score=0.2,
            )
        ]

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        link.refresh_from_db()
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertEqual(link.relevance_score, 0.4)
        self.assertEqual(link.directness_score, 0.2)
        evidence_context = self.evaluate_persisted.call_args.args[1]
        self.assertIn("Stance: UNKNOWN", evidence_context)
        self.assertIn("Relevance score: 0.4", evidence_context)
        self.assertIn("Directness score: 0.2", evidence_context)

    def test_unavailable_assessment_preserves_empty_fields_and_evaluates(self):
        self.assessor.return_value = [
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.UNKNOWN,
                relevance_score=None,
                directness_score=None,
            )
        ]

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        link.refresh_from_db()
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.evaluate_persisted.assert_called_once()
        self.assertIn("Rating: False", self.evaluate_persisted.call_args.args[1])
        self.retrieve_tavily.assert_not_called()

    def test_assessor_exception_is_best_effort(self):
        self.assessor.side_effect = RuntimeError("Assessment unavailable")

        with self.assertLogs("api.tasks", level="ERROR") as logs:
            run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        link.refresh_from_db()
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.evaluate_persisted.assert_called_once()
        self.retrieve_tavily.assert_not_called()
        self.assertIn("Evidence assessment failed", "\n".join(logs.output))

    def test_persistence_exception_is_best_effort(self):
        with patch(
            "api.tasks.persist_evidence_assessment",
            side_effect=RuntimeError("Assessment storage unavailable"),
        ), self.assertLogs("api.tasks", level="ERROR") as logs:
            run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        link = VerificationEvidence.objects.get()
        link.refresh_from_db()
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.evaluate_persisted.assert_called_once()
        self.retrieve_tavily.assert_not_called()
        self.assertIn(
            "Evidence assessment persistence failed",
            "\n".join(logs.output),
        )

    def test_missing_persisted_tavily_evidence_abstains_without_evaluation(self):
        self.gfc_provider.search_with_payload.return_value = ({"claims": []}, [])

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.ABSTAINED)
        self.assessor.assert_not_called()
        self.evaluate_persisted.assert_not_called()
        self.evaluate_legacy_tavily.assert_not_called()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertEqual(
            self.save_claim.call_args.args[1]["confidence_score"],
            0,
        )
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("url_tavily_persisted_evidence_unavailable", stages)
        self.assertNotIn("url_tavily_llm_evaluation", stages)

    def test_multiple_gfc_items_use_one_batch_and_persist_positionally(self):
        self.gfc_raw_sources.append(
            RawEvidence(
                provider="GOOGLE_FACT_CHECK",
                url="https://example.com/second-fact-check",
                content="Second persisted fact-check.",
                source_type="FACT_CHECK",
            )
        )
        assessments = [
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.SUPPORTS,
                relevance_score=0.7,
                directness_score=0.6,
            ),
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.REFUTES,
                relevance_score=0.9,
                directness_score=0.8,
            ),
        ]
        self.assessor.return_value = assessments

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assessor.assert_called_once()
        assessed_items = self.assessor.call_args.args[1]
        self.assertEqual(len(assessed_items), 2)
        for item, assessment in zip(assessed_items, assessments):
            link = VerificationEvidence.objects.get(pk=item.evidence_link_id)
            self.assertEqual(link.stance, assessment.stance)
            self.assertEqual(link.relevance_score, assessment.relevance_score)
            self.assertEqual(link.directness_score, assessment.directness_score)

    def test_tavily_batch_omits_assessed_item_and_includes_recency_only_item(self):
        self.gfc_provider.search_with_payload.return_value = ({"claims": []}, [])
        created_links = {}

        def add_secondary_links(
            search_query, claim_id, *, stage_prefix, verification_run
        ):
            values = (
                (
                    "assessed",
                    {"stance": VerificationEvidence.Stance.CONTEXT},
                ),
                ("recency", {"recency_score": 0.45}),
                ("pristine", {}),
            )
            for name, link_values in values:
                source = EvidenceSource.objects.create(
                    provider="TAVILY",
                    canonical_url=f"https://example.com/{name}",
                    content=f"Persisted {name} evidence.",
                )
                created_links[name] = VerificationEvidence.objects.create(
                    verification_run=verification_run,
                    evidence_source=source,
                    evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
                    **link_values,
                )
            return self.tavily_response

        self.retrieve_tavily.side_effect = add_secondary_links
        assessments = [
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.SUPPORTS,
                relevance_score=0.8,
                directness_score=0.7,
            ),
            EvidenceAssessment(
                stance=VerificationEvidence.Stance.REFUTES,
                relevance_score=0.9,
                directness_score=0.85,
            ),
        ]
        self.assessor.return_value = assessments

        run = self._execute()

        self.assertEqual(run.status, VerificationRun.Status.COMPLETED)
        self.assessor.assert_called_once()
        assessed_items = self.assessor.call_args.args[1]
        self.assertEqual(
            {item.evidence_link_id for item in assessed_items},
            {created_links["recency"].pk, created_links["pristine"].pk},
        )
        created_links["assessed"].refresh_from_db()
        self.assertEqual(
            created_links["assessed"].stance,
            VerificationEvidence.Stance.CONTEXT,
        )
        created_links["recency"].refresh_from_db()
        self.assertEqual(created_links["recency"].recency_score, 0.45)
        for item, assessment in zip(assessed_items, assessments):
            link = VerificationEvidence.objects.get(pk=item.evidence_link_id)
            self.assertEqual(link.stance, assessment.stance)
            self.assertEqual(link.relevance_score, assessment.relevance_score)
            self.assertEqual(link.directness_score, assessment.directness_score)

    def test_gfc_final_llm_unavailable_fails_without_tavily_or_fake_verdict(self):
        error = LLMProviderUnavailableError(
            "No configured LLM provider successfully completed this request."
        )
        self.evaluate_persisted.side_effect = error

        with self.assertRaises(LLMProviderUnavailableError) as raised:
            tasks.url_fact_check_process.run(self.url, self.claim.pk)

        self.assertIs(raised.exception, error)
        run = self.claim.verification_runs.get()
        self.assertEqual(run.status, VerificationRun.Status.FAILED)
        self.assertEqual(run.failure_stage, "final_evaluator")
        self.assertEqual(run.failure_code, "LLM_UNAVAILABLE")
        self.retrieve_tavily.assert_not_called()
        self.save_claim.assert_not_called()

    def test_tavily_final_llm_unavailable_fails_without_fake_verdict(self):
        self.gfc_provider.search_with_payload.return_value = ({"claims": []}, [])
        self.retrieve_tavily.side_effect = self._record_tavily_link
        error = LLMProviderUnavailableError(
            "No configured LLM provider successfully completed this request."
        )
        self.evaluate_persisted.side_effect = error

        with self.assertRaises(LLMProviderUnavailableError) as raised:
            tasks.url_fact_check_process.run(self.url, self.claim.pk)

        self.assertIs(raised.exception, error)
        run = self.claim.verification_runs.get()
        self.assertEqual(run.status, VerificationRun.Status.FAILED)
        self.assertEqual(run.failure_stage, "final_evaluator")
        self.assertEqual(run.failure_code, "LLM_UNAVAILABLE")
        self.save_claim.assert_not_called()
