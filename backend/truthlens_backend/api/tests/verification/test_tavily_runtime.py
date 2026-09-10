import os
from copy import deepcopy
from unittest.mock import Mock, patch

import requests
from django.db import IntegrityError
from django.test import TestCase

from api import tasks
from api.models import (
    CanonicalSource,
    Claim,
    EvidenceSource,
    VerificationEvidence,
    VerificationRun,
)
from api.verification import runs
from api.verification.contracts import RawEvidence
from api.verification.persistence import persist_evidence_source
from api.verification.providers.tavily import TavilyProvider


class TavilyRuntimeBridgeTests(TestCase):
    def setUp(self):
        self.payload = {
            "answer": "Provider answer.",
            "results": [{"url": "https://example.com/article", "score": 0.9}],
            "extra": {"request": "original"},
        }
        self.raw_items = [RawEvidence(
            provider="TAVILY", url="https://example.com/article?utm_source=test",
            content=" Source   content. ", source_type="WEB_SEARCH",
            raw_reference={"tavily_result_index": 0},
        )]
        self.provider_class = self.enterContext(patch("api.tasks.TavilyProvider"))
        self.provider = self.provider_class.return_value
        self.provider.search_with_payload.return_value = (self.payload, self.raw_items)
        self.log_stage = self.enterContext(patch("api.tasks._log_stage"))

    def _retrieve(self, **kwargs):
        return tasks._retrieve_and_ingest_tavily("example query", "claim-id", **kwargs)

    def _running_run(self):
        claim = Claim.objects.create(context_text="Example claim.")
        return runs.start_verification_run(runs.create_verification_run(claim))

    def test_running_run_links_all_sources_with_secondary_role_and_defaults(self):
        run = self._running_run()
        before = VerificationRun.objects.values().get(pk=run.pk)
        self.raw_items.append(RawEvidence(
            provider="TAVILY", url="https://example.com/second", content="Second source",
        ))
        with patch(
            "api.tasks.link_evidence_sources_to_run", wraps=tasks.link_evidence_sources_to_run,
        ) as link_sources:
            self.assertIs(self._retrieve(verification_run=run), self.payload)
        sources = list(EvidenceSource.objects.order_by("canonical_url"))
        self.assertEqual(len(sources), 2)
        link_sources.assert_called_once_with(
            run, sources, evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )
        links = list(VerificationEvidence.objects.filter(verification_run=run))
        self.assertEqual({link.evidence_source_id for link in links}, {s.pk for s in sources})
        self.assertEqual(len(links), 2)
        for link in links:
            self.assertEqual(link.evidence_role, VerificationEvidence.EvidenceRole.SECONDARY)
            self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
            self.assertIsNone(link.relevance_score)
            self.assertIsNone(link.directness_score)
            self.assertIsNone(link.recency_score)
        self.assertEqual(VerificationRun.objects.values().get(pk=run.pk), before)
        self.provider.search_with_payload.assert_called_once_with("example query", limit=5)
        self.assertEqual([call.args[1] for call in self.log_stage.call_args_list], [
            "tavily_evidence_ingestion", "tavily_evidence_linking",
        ])
        self.assertEqual(self.log_stage.call_args.kwargs, {
            "verification_run_id": run.pk, "evidence_links": 2,
        })

    def test_duplicate_and_reused_sources_do_not_duplicate_links(self):
        run = self._running_run()
        self.raw_items.append(self.raw_items[0])
        self.assertIs(self._retrieve(verification_run=run), self.payload)
        source_before = EvidenceSource.objects.values().get()
        link_before = VerificationEvidence.objects.values().get()
        self.assertIs(self._retrieve(verification_run=run), self.payload)
        self.assertEqual(EvidenceSource.objects.values().get(), source_before)
        self.assertEqual(VerificationEvidence.objects.values().get(), link_before)
        self.assertEqual(self.provider.search_with_payload.call_count, 2)

    def test_link_batch_failure_preserves_ingested_sources_and_payload(self):
        run = self._running_run()
        self.raw_items.append(RawEvidence(
            provider="TAVILY", url="https://example.com/second", content="Second source",
        ))
        original_get_or_create = VerificationEvidence.objects.get_or_create
        before = deepcopy(self.payload)

        def fail_second_link(**kwargs):
            if kwargs["evidence_source"].canonical_url == "https://example.com/second":
                self.assertEqual(VerificationEvidence.objects.count(), 1)
                raise IntegrityError("Second link failed")
            return original_get_or_create(**kwargs)

        with patch(
            "api.verification.linking.VerificationEvidence.objects.get_or_create",
            side_effect=fail_second_link,
        ) as get_or_create:
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                self.assertIs(self._retrieve(verification_run=run), self.payload)
        self.assertEqual(get_or_create.call_count, 2)
        self.assertEqual(self.payload, before)
        self.assertEqual(EvidenceSource.objects.count(), 2)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        run.refresh_from_db()
        self.assertEqual(run.status, VerificationRun.Status.RUNNING)
        self.provider.search_with_payload.assert_called_once_with("example query", limit=5)
        self.assertIn("Tavily evidence linking failed", "\n".join(logs.output))
        self.assertEqual(self.log_stage.call_args.args[1], "tavily_evidence_linking_failed")
        self.assertEqual(self.log_stage.call_args.kwargs, {
            "verification_run_id": run.pk, "error": "Second link failed",
        })

    def test_url_prefix_applies_to_linking_success_and_failure(self):
        run = self._running_run()
        self.assertIs(self._retrieve(verification_run=run, stage_prefix="url_"), self.payload)
        self.assertEqual([call.args[1] for call in self.log_stage.call_args_list], [
            "url_tavily_evidence_ingestion", "url_tavily_evidence_linking",
        ])
        self.assertEqual(self.log_stage.call_args.kwargs, {
            "verification_run_id": run.pk, "evidence_links": 1,
        })
        link_before = VerificationEvidence.objects.values().get()
        with patch("api.tasks.link_evidence_sources_to_run", side_effect=RuntimeError("Link failed")):
            with self.assertLogs("api.tasks", level="ERROR"):
                self.assertIs(self._retrieve(verification_run=run, stage_prefix="url_"), self.payload)
        self.assertEqual(self.log_stage.call_args.args[1], "url_tavily_evidence_linking_failed")
        self.assertEqual(self.log_stage.call_args.kwargs, {
            "verification_run_id": run.pk, "error": "Link failed",
        })
        self.assertEqual(EvidenceSource.objects.count(), 1)
        self.assertEqual(VerificationEvidence.objects.values().get(), link_before)

    def test_bridge_searches_once_and_ingests_without_links(self):
        before = deepcopy(self.payload)
        with patch("api.tasks.ingest_raw_evidence", wraps=tasks.ingest_raw_evidence) as ingest:
            returned = self._retrieve()
        self.provider_class.assert_called_once_with(timeout=tasks.DEFAULT_HTTP_TIMEOUT_SEC)
        self.provider.search_with_payload.assert_called_once_with("example query", limit=5)
        ingest.assert_called_once_with(self.raw_items)
        self.assertIs(ingest.call_args.args[0], self.raw_items)
        self.assertIs(returned, self.payload)
        self.assertEqual(self.payload, before)
        source = EvidenceSource.objects.get()
        self.assertEqual(source.provider, "TAVILY")
        self.assertEqual(source.canonical_url, "https://example.com/article")
        self.assertEqual(source.content, "Source content.")
        self.assertEqual(source.raw_reference, {"tavily_result_index": 0})
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.assertEqual(VerificationRun.objects.count(), 0)
        self.assertEqual(self.log_stage.call_args.args[1], "tavily_evidence_ingestion")
        self.assertEqual(self.log_stage.call_args.kwargs["evidence_sources"], 1)

    def test_ingestion_failure_is_logged_and_preserves_payload(self):
        before = deepcopy(self.payload)
        run = self._running_run()
        with (
            patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")),
            patch("api.tasks.link_evidence_sources_to_run") as link_sources,
        ):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                returned = self._retrieve(verification_run=run)
        link_sources.assert_not_called()
        self.assertIs(returned, self.payload)
        self.assertEqual(self.payload, before)
        self.assertIn("Tavily evidence ingestion failed", "\n".join(logs.output))
        self.assertIn("Storage failed", "\n".join(logs.output))
        self.assertEqual(self.log_stage.call_args.args[1], "tavily_evidence_ingestion_failed")
        self.assertEqual(self.log_stage.call_args.kwargs["error"], "Storage failed")
        self.provider.search_with_payload.assert_called_once()
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_batch_failure_rolls_back_sources_and_preserves_payload(self):
        self.raw_items.append(RawEvidence(
            provider="TAVILY", url="https://example.com/second", content="Second source",
        ))

        def fail_second_source(evidence):
            if evidence.url == "https://example.com/second":
                self.assertEqual(EvidenceSource.objects.count(), 1)
                raise IntegrityError("Second source failed")
            return persist_evidence_source(evidence)

        with patch(
            "api.verification.ingestion.persist_evidence_source", side_effect=fail_second_source,
        ) as persist:
            returned = self._retrieve()
        self.assertIs(returned, self.payload)
        self.assertEqual(persist.call_count, 2)
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.provider.search_with_payload.assert_called_once()

    def test_url_stage_prefix_preserves_payload_on_ingestion_success_and_failure(self):
        before = deepcopy(self.payload)
        self.assertIs(self._retrieve(stage_prefix="url_"), self.payload)
        self.assertEqual(self.log_stage.call_args.args[1], "url_tavily_evidence_ingestion")
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            self.assertIs(self._retrieve(stage_prefix="url_"), self.payload)
        self.assertEqual(
            self.log_stage.call_args.args[1], "url_tavily_evidence_ingestion_failed",
        )
        self.assertEqual(self.payload, before)
        self.assertEqual(self.provider.search_with_payload.call_count, 2)
        self.assertEqual(EvidenceSource.objects.count(), 1)
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_provider_failure_propagates_without_ingestion(self):
        run = self._running_run()
        error = requests.Timeout("Tavily unavailable")
        self.provider.search_with_payload.side_effect = error
        with (
            patch("api.tasks.ingest_raw_evidence") as ingest,
            patch("api.tasks.link_evidence_sources_to_run") as link_sources,
        ):
            with self.assertRaises(requests.Timeout) as raised:
                self._retrieve(verification_run=run)
        self.assertIs(raised.exception, error)
        ingest.assert_not_called()
        link_sources.assert_not_called()
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.log_stage.assert_not_called()
        self.provider.search_with_payload.assert_called_once()
        self.assertEqual(EvidenceSource.objects.count(), 0)


class TavilyTextRuntimeIngestionTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT, context_text="Raw submitted claim.",
        )
        self.cleaned = {
            "cleaned_claim": "Example public claim.",
            "search_query": "example public claim",
            "article_stance": "NEUTRAL",
        }
        self.verdict = {
            "verdict": "FAKE", "summary": "Evidence refutes the claim.",
            "confidence_score": 95,
        }
        self.payload = {
            "answer": "Original provider answer.",
            "results": [
                {"url": "https://example.com/first", "title": "First result",
                 "content": "Long first source content. " * 20, "score": 0.99},
                {"url": "https://example.com/second", "content": "Second source content."},
                {"content": "Third source without URL."},
                {"url": "https://example.com/fourth", "content": "Fourth source content."},
            ],
            "extra": {"original": True},
        }
        self.payload_before = deepcopy(self.payload)
        self.client = Mock()
        self.client.search.return_value = self.payload
        self.enterContext(patch.dict(os.environ, {"TAVILY_API_KEY": "test-api-key"}))
        self._patch("api.verification.providers.tavily.TavilyClient", return_value=self.client)
        self.provider_class = self._patch("api.tasks.TavilyProvider", wraps=TavilyProvider)
        self._patch("api.claim_matching.compute_fingerprint", return_value="txt:tavily-runtime")
        self._patch("api.claim_matching.find_matching_claim", return_value=None)
        self._patch("api.tasks.clean_ocr_text", return_value=self.cleaned)
        self._patch("api.tasks.search_official_vault", return_value=None)
        self.real_gfc_bridge = tasks._retrieve_and_ingest_gfc
        self.gfc = self._patch("api.tasks._retrieve_and_ingest_gfc", return_value={"claims": []})
        self.relevance = self._patch("api.tasks.is_fact_check_relevant", return_value=False)
        self.evaluate_gfc = self._patch("api.tasks.evaluate_image_claim_with_gfc")
        self.evaluate_tavily = self._patch(
            "api.tasks.evaluate_image_claim_with_tavily", return_value=self.verdict,
        )
        self._patch("api.embedding_service.generate_embedding", return_value=None)
        self.log_stage = self._patch("api.tasks._log_stage")
        self.save_claim = self._patch("api.tasks._save_claim", wraps=tasks._save_claim)
        real_bridge = tasks._retrieve_and_ingest_tavily
        self.observed_runs = []

        def record_running_run(*args, **kwargs):
            run = kwargs["verification_run"]
            self.assertEqual(run.status, VerificationRun.Status.RUNNING)
            self.assertEqual(VerificationRun.objects.get(pk=run.pk).status, run.status)
            self.observed_runs.append(run.pk)
            return real_bridge(*args, **kwargs)

        self.bridge = self._patch(
            "api.tasks._retrieve_and_ingest_tavily", side_effect=record_running_run,
        )
        self.terminals = [self._patch(
            f"api.tasks.{name}_verification_run", wraps=getattr(runs, f"{name}_verification_run"),
        ) for name in ("complete", "abstain", "fail")]

    def _patch(self, target, **kwargs):
        return self.enterContext(patch(target, **kwargs))

    def _execute(self, status=VerificationRun.Status.COMPLETED, *, expected_links=4):
        tasks.execute_core_text_pipeline(self.claim.context_text, self.claim.pk)
        run = self.claim.verification_runs.get()
        self.assertEqual(run.status, status)
        self.assertEqual(sum(helper.call_count for helper in self.terminals), 1)
        self.assertIsNone(run.failure_stage)
        self.assertIsNone(run.failure_code)
        self.assertIsNone(run.failure_message)
        self.assertEqual(self.observed_runs, [run.pk])
        self.bridge.assert_called_once_with(
            self.cleaned["search_query"], self.claim.pk, verification_run=run,
        )
        self._assert_tavily_links(run, expected_links)
        return run

    def _assert_tavily_links(self, run, expected_count):
        links = list(VerificationEvidence.objects.filter(
            verification_run=run,
            evidence_source__provider="TAVILY",
        ))
        self.assertEqual(len(links), expected_count)
        for link in links:
            self.assertEqual(link.evidence_role, VerificationEvidence.EvidenceRole.SECONDARY)
            self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
            self.assertIsNone(link.relevance_score)
            self.assertIsNone(link.directness_score)
            self.assertIsNone(link.recency_score)

    def _assert_tavily_host_identities(self):
        tavily_sources = EvidenceSource.objects.filter(provider="TAVILY")
        self.assertEqual(
            tavily_sources.filter(canonical_source__domain="example.com").count(),
            3,
        )
        self.assertEqual(tavily_sources.filter(canonical_source=None).count(), 1)
        self.assertEqual(
            tavily_sources.exclude(canonical_source=None)
            .values("canonical_source_id")
            .distinct()
            .count(),
            1,
        )
        self.assertEqual(CanonicalSource.objects.filter(domain="example.com").count(), 1)

    def _assert_original_evaluation_and_sources(self):
        expected_context = (
            "Text Extracted From Image (Do NOT use this as evidence to prove itself):\n"
            "Raw submitted claim.\n\nWeb Search Answer:\nOriginal provider answer.\n\n"
            "Top Search Results:\nSource 1: First result\nURL: https://example.com/first\n"
            f"Content: {self.payload_before['results'][0]['content']}\n\n"
            "Source 2: No Title\nURL: https://example.com/second\n"
            "Content: Second source content.\n\n"
            "Source 3: No Title\nURL: \nContent: Third source without URL.\n\n"
        )
        self.evaluate_tavily.assert_called_once_with(
            self.cleaned["cleaned_claim"], expected_context, "NEUTRAL",
        )
        expected_sources = [
            {"url": "https://example.com/first", "title": "First result",
             "snippet": self.payload_before["results"][0]["content"][:250] + "..."},
            {"url": "https://example.com/second", "title": "External Source",
             "snippet": "Second source content...."},
        ]
        self.save_claim.assert_called_once_with(
            self.claim.pk, self.verdict, "Live Web Search",
            self.cleaned["cleaned_claim"], expected_sources,
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, self.verdict["verdict"])
        self.assertEqual(self.claim.ai_sources, expected_sources)
        self.assertEqual(self.payload, self.payload_before)

    def test_empty_gfc_uses_bridge_and_preserves_evaluation_and_sources(self):
        self._execute()
        self.provider_class.assert_called_once_with(timeout=tasks.DEFAULT_HTTP_TIMEOUT_SEC)
        self.client.search.assert_called_once()
        self.assertEqual(self.client.search.call_args.kwargs["timeout"], tasks.DEFAULT_HTTP_TIMEOUT_SEC)
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self.assertFalse(EvidenceSource.objects.exclude(authority_score=None).exists())
        self._assert_tavily_host_identities()
        self.relevance.assert_not_called()
        self.evaluate_gfc.assert_not_called()
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("tavily_evidence_ingestion", stages)
        self.assertNotIn("url_tavily_evidence_ingestion", stages)
        self._assert_original_evaluation_and_sources()

    def test_irrelevant_gfc_uses_tavily_bridge_after_relevance(self):
        self.gfc.return_value = {"claims": [{"text": "Unrelated claim."}]}
        events = []

        def reject_gfc(*args):
            events.append("gfc_relevance")
            return False

        def search_tavily(**kwargs):
            events.append("tavily_search")
            return self.payload

        self.relevance.side_effect = reject_gfc
        self.client.search.side_effect = search_tavily
        self._execute()
        self.assertEqual(events, ["gfc_relevance", "tavily_search"])
        self.evaluate_gfc.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 4)
        self._assert_original_evaluation_and_sources()

    def test_gfc_and_tavily_evidence_coexist_on_the_same_run(self):
        gfc_payload = {"claims": [{"text": "Unrelated fact check."}]}
        gfc_raw_items = [RawEvidence(
            provider="GOOGLE_FACT_CHECK",
            url="https://fact-check.example/review",
            content="Fact-check evidence.",
            source_type="FACT_CHECK",
        )]
        gfc_provider_class = self._patch("api.tasks.GoogleFactCheckProvider")
        gfc_provider_class.return_value.search_with_payload.return_value = (
            gfc_payload, gfc_raw_items,
        )
        self.gfc.side_effect = self.real_gfc_bridge

        run = self._execute()

        links = list(VerificationEvidence.objects.filter(verification_run=run))
        self.assertEqual(len(links), 5)
        self.assertEqual(
            VerificationEvidence.objects.get(
                verification_run=run,
                evidence_source__provider="GOOGLE_FACT_CHECK",
            ).evidence_role,
            VerificationEvidence.EvidenceRole.FACT_CHECK,
        )
        self.assertEqual(
            VerificationEvidence.objects.filter(
                verification_run=run,
                evidence_source__provider="TAVILY",
                evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            ).count(),
            4,
        )
        self.relevance.assert_called_once_with(
            self.cleaned["cleaned_claim"], "Unrelated fact check.",
        )
        self._assert_original_evaluation_and_sources()

    def test_ingestion_failure_does_not_prevent_completion_or_evaluation(self):
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                self._execute(expected_links=0)
        self.assertIn("Tavily evidence ingestion failed", "\n".join(logs.output))
        self.assertIn("tavily_evidence_ingestion_failed", [
            call.args[1] for call in self.log_stage.call_args_list
        ])
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.client.search.assert_called_once()
        self._assert_original_evaluation_and_sources()

    def test_ingestion_failure_preserves_abstaining_verdict(self):
        self.verdict["verdict"] = "UNVERIFIED"
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            self._execute(VerificationRun.Status.ABSTAINED, expected_links=0)
        self._assert_original_evaluation_and_sources()

    def test_successful_ingestion_preserves_abstaining_verdict_and_links(self):
        self.verdict["verdict"] = "UNVERIFIED"
        self._execute(VerificationRun.Status.ABSTAINED)
        self._assert_original_evaluation_and_sources()

    def test_linking_failure_preserves_completion_and_evaluation(self):
        with patch(
            "api.tasks.link_evidence_sources_to_run",
            side_effect=RuntimeError("Link storage failed"),
        ):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                self._execute(expected_links=0)
        self.assertIn("Tavily evidence linking failed", "\n".join(logs.output))
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self._assert_original_evaluation_and_sources()

    def test_linking_failure_preserves_abstention_and_evaluation(self):
        self.verdict["verdict"] = "UNVERIFIED"
        with patch(
            "api.tasks.link_evidence_sources_to_run",
            side_effect=RuntimeError("Link storage failed"),
        ):
            self._execute(VerificationRun.Status.ABSTAINED, expected_links=0)
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self._assert_original_evaluation_and_sources()

    def test_provider_failure_reaches_existing_unverified_fallback(self):
        self.client.search.side_effect = requests.Timeout("Provider unavailable")
        with patch("api.tasks.ingest_raw_evidence") as ingest:
            self._execute(VerificationRun.Status.ABSTAINED, expected_links=0)
        ingest.assert_not_called()
        self.evaluate_tavily.assert_not_called()
        self.client.search.assert_called_once()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertEqual(self.claim.ai_sources, [])
        self.assertEqual(self.claim.source_type, "Live Web Search")
        self.assertEqual(EvidenceSource.objects.count(), 0)

    def _execute_url(self, status=VerificationRun.Status.COMPLETED, *, expected_links=4):
        url = "https://example.com/article"
        self.claim.claim_type = Claim.ClaimType.URL
        self.claim.save(update_fields=["claim_type"])
        self.cleaned["search_query"] = "q" * 300 + " query suffix excluded"
        self.url_cleaned_text = "Cleaned article content. " * 100
        response = Mock(status_code=200)
        response.json.return_value = {"results": [{"raw_content": "Article content."}]}
        with (
            patch("api.tasks.requests.post", return_value=response),
            patch("api.tasks.clean_extracted_text", return_value=self.url_cleaned_text),
            patch("api.tasks.extract_search_query", return_value=self.cleaned),
            patch("api.tasks.evaluate_url_claim_with_tavily", return_value=self.verdict) as evaluate_url,
        ):
            tasks.url_fact_check_process.run(url, self.claim.pk)
        run = self.claim.verification_runs.get()
        self.bridge.assert_called_once_with(
            self.cleaned["search_query"][:300], self.claim.pk, stage_prefix="url_",
            verification_run=run,
        )
        self.provider_class.assert_called_once_with(timeout=tasks.DEFAULT_HTTP_TIMEOUT_SEC)
        self.client.search.assert_called_once()
        self.assertEqual(self.client.search.call_args.kwargs["query"], "q" * 300)
        self.assertEqual(
            self.client.search.call_args.kwargs["timeout"], tasks.DEFAULT_HTTP_TIMEOUT_SEC,
        )
        self.assertNotIn("request_timeout", self.client.search.call_args.kwargs)
        self.evaluate_tavily.assert_not_called()
        self.assertEqual(self.observed_runs, [run.pk])
        self._assert_tavily_links(run, expected_links)
        self.assertEqual(run.status, status)
        self.assertEqual(sum(helper.call_count for helper in self.terminals), 1)
        self.assertIsNone(run.failure_stage)
        self.assertIsNone(run.failure_code)
        self.assertIsNone(run.failure_message)
        return evaluate_url

    def _assert_original_url_evaluation_and_sources(self, evaluate_url):
        expected_context = (
            "Original URL Content to Verify (Do NOT use this as evidence to prove itself):\n"
            f"{self.url_cleaned_text[:1500]}\n\n"
            "Web Search Answer:\nOriginal provider answer.\n\n"
            "Top Search Results:\nSource 1: First result\nURL: https://example.com/first\n"
            f"Content: {self.payload_before['results'][0]['content']}\n\n"
            "Source 2: No Title\nURL: https://example.com/second\n"
            "Content: Second source content.\n\n"
            "Source 3: No Title\nURL: \nContent: Third source without URL.\n\n"
        )
        evaluate_url.assert_called_once_with(
            self.cleaned["cleaned_claim"], expected_context, "NEUTRAL",
        )
        expected_sources = [
            {"url": "https://example.com/first", "title": "First result",
             "snippet": self.payload_before["results"][0]["content"][:250] + "..."},
            {"url": "https://example.com/second", "title": "External Source",
             "snippet": "Second source content...."},
        ]
        self.save_claim.assert_called_once_with(
            self.claim.pk, self.verdict, "Live Web Search",
            self.url_cleaned_text, expected_sources,
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, self.verdict["verdict"])
        self.assertEqual(self.claim.ai_sources, expected_sources)
        self.assertEqual(self.claim.context_text, self.url_cleaned_text)
        self.assertEqual(self.payload, self.payload_before)

    def test_url_runtime_uses_bridge_and_preserves_payload_evaluation_and_sources(self):
        evaluate_url = self._execute_url()
        self._assert_original_url_evaluation_and_sources(evaluate_url)
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self.assertFalse(EvidenceSource.objects.exclude(authority_score=None).exists())
        self._assert_tavily_host_identities()
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("url_tavily_evidence_ingestion", stages)
        self.assertNotIn("tavily_evidence_ingestion", stages)

    def test_url_ingestion_failure_preserves_completion_and_evaluation(self):
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                evaluate_url = self._execute_url(expected_links=0)
        self._assert_original_url_evaluation_and_sources(evaluate_url)
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertIn("Tavily evidence ingestion failed", "\n".join(logs.output))
        self.assertIn("Storage failed", "\n".join(logs.output))
        stages = [call.args[1] for call in self.log_stage.call_args_list]
        self.assertIn("url_tavily_evidence_ingestion_failed", stages)
        self.assertNotIn("tavily_evidence_ingestion_failed", stages)

    def test_url_ingestion_failure_preserves_abstention_and_evaluation(self):
        self.verdict["verdict"] = "UNVERIFIED"
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            evaluate_url = self._execute_url(VerificationRun.Status.ABSTAINED, expected_links=0)
        self._assert_original_url_evaluation_and_sources(evaluate_url)
        self.assertEqual(EvidenceSource.objects.count(), 0)

    def test_url_successful_ingestion_preserves_abstention_and_links(self):
        self.verdict["verdict"] = "UNVERIFIED"
        evaluate_url = self._execute_url(VerificationRun.Status.ABSTAINED)
        self._assert_original_url_evaluation_and_sources(evaluate_url)

    def test_url_linking_failure_preserves_completion_and_evaluation(self):
        with patch(
            "api.tasks.link_evidence_sources_to_run",
            side_effect=RuntimeError("Link storage failed"),
        ):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                evaluate_url = self._execute_url(expected_links=0)
        self.assertIn("Tavily evidence linking failed", "\n".join(logs.output))
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self._assert_original_url_evaluation_and_sources(evaluate_url)

    def test_url_linking_failure_preserves_abstention_and_evaluation(self):
        self.verdict["verdict"] = "UNVERIFIED"
        with patch(
            "api.tasks.link_evidence_sources_to_run",
            side_effect=RuntimeError("Link storage failed"),
        ):
            evaluate_url = self._execute_url(
                VerificationRun.Status.ABSTAINED, expected_links=0,
            )
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self._assert_original_url_evaluation_and_sources(evaluate_url)

    def test_url_provider_failure_reaches_existing_unverified_fallback(self):
        self.client.search.side_effect = requests.Timeout("Provider unavailable")
        with patch("api.tasks.ingest_raw_evidence") as ingest:
            evaluate_url = self._execute_url(VerificationRun.Status.ABSTAINED, expected_links=0)
        ingest.assert_not_called()
        evaluate_url.assert_not_called()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertEqual(self.claim.ai_sources, [])
        self.assertEqual(self.claim.source_type, "Live Web Search")
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertFalse(any(
            "tavily_evidence_ingestion" in call.args[1]
            for call in self.log_stage.call_args_list
        ))
