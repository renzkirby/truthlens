import os
from copy import deepcopy
from unittest.mock import Mock, patch

import requests
from django.db import IntegrityError
from django.test import TestCase

from api import tasks
from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
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

    def _retrieve(self):
        return tasks._retrieve_and_ingest_tavily("example query", "claim-id")

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
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                returned = self._retrieve()
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

    def test_provider_failure_propagates_without_ingestion(self):
        error = requests.Timeout("Tavily unavailable")
        self.provider.search_with_payload.side_effect = error
        with patch("api.tasks.ingest_raw_evidence") as ingest:
            with self.assertRaises(requests.Timeout) as raised:
                self._retrieve()
        self.assertIs(raised.exception, error)
        ingest.assert_not_called()
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
        self.gfc = self._patch("api.tasks._retrieve_and_ingest_gfc", return_value={"claims": []})
        self.relevance = self._patch("api.tasks.is_fact_check_relevant", return_value=False)
        self.evaluate_gfc = self._patch("api.tasks.evaluate_image_claim_with_gfc")
        self.evaluate_tavily = self._patch(
            "api.tasks.evaluate_image_claim_with_tavily", return_value=self.verdict,
        )
        self._patch("api.embedding_service.generate_embedding", return_value=None)
        self.log_stage = self._patch("api.tasks._log_stage")
        self.save_claim = self._patch("api.tasks._save_claim", wraps=tasks._save_claim)
        self.bridge = self._patch(
            "api.tasks._retrieve_and_ingest_tavily", wraps=tasks._retrieve_and_ingest_tavily,
        )
        self.terminals = [self._patch(
            f"api.tasks.{name}_verification_run", wraps=getattr(runs, f"{name}_verification_run"),
        ) for name in ("complete", "abstain", "fail")]

    def _patch(self, target, **kwargs):
        return self.enterContext(patch(target, **kwargs))

    def _execute(self, status=VerificationRun.Status.COMPLETED):
        tasks.execute_core_text_pipeline(self.claim.context_text, self.claim.pk)
        run = self.claim.verification_runs.get()
        self.assertEqual(run.status, status)
        self.assertEqual(sum(helper.call_count for helper in self.terminals), 1)
        self.assertIsNone(run.failure_stage)
        self.assertIsNone(run.failure_code)
        self.assertIsNone(run.failure_message)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        return run

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
        self.bridge.assert_called_once_with(self.cleaned["search_query"], self.claim.pk)
        self.provider_class.assert_called_once_with(timeout=tasks.DEFAULT_HTTP_TIMEOUT_SEC)
        self.client.search.assert_called_once()
        self.assertEqual(self.client.search.call_args.kwargs["timeout"], tasks.DEFAULT_HTTP_TIMEOUT_SEC)
        self.assertEqual(EvidenceSource.objects.filter(provider="TAVILY").count(), 4)
        self.assertFalse(EvidenceSource.objects.exclude(authority_score=None).exists())
        self.assertFalse(EvidenceSource.objects.exclude(canonical_source=None).exists())
        self.relevance.assert_not_called()
        self.evaluate_gfc.assert_not_called()
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
        self.bridge.assert_called_once_with(self.cleaned["search_query"], self.claim.pk)
        self.evaluate_gfc.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 4)
        self._assert_original_evaluation_and_sources()

    def test_ingestion_failure_does_not_prevent_completion_or_evaluation(self):
        with patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Storage failed")):
            with self.assertLogs("api.tasks", level="ERROR") as logs:
                self._execute()
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
            self._execute(VerificationRun.Status.ABSTAINED)
        self._assert_original_evaluation_and_sources()

    def test_provider_failure_reaches_existing_unverified_fallback(self):
        self.client.search.side_effect = requests.Timeout("Provider unavailable")
        with patch("api.tasks.ingest_raw_evidence") as ingest:
            self._execute(VerificationRun.Status.ABSTAINED)
        ingest.assert_not_called()
        self.evaluate_tavily.assert_not_called()
        self.client.search.assert_called_once()
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, "UNVERIFIED")
        self.assertEqual(self.claim.ai_sources, [])
        self.assertEqual(self.claim.source_type, "Live Web Search")
        self.assertEqual(EvidenceSource.objects.count(), 0)

    def test_url_runtime_keeps_legacy_client_and_does_not_use_text_bridge(self):
        url = "https://example.com/article"
        self.claim.claim_type = Claim.ClaimType.URL
        self.claim.save(update_fields=["claim_type"])
        response = Mock(status_code=200)
        response.json.return_value = {"results": [{"raw_content": "Article content."}]}
        self.bridge.side_effect = AssertionError("URL must not call the text Tavily bridge")
        with (
            patch("api.tasks.requests.post", return_value=response),
            patch("api.tasks.clean_extracted_text", return_value="Cleaned article."),
            patch("api.tasks.extract_search_query", return_value=self.cleaned),
            patch("api.tasks.TavilyClient") as legacy_client,
            patch("api.tasks.evaluate_url_claim_with_tavily", return_value=self.verdict) as evaluate_url,
        ):
            legacy_client.return_value.search.return_value = self.payload
            tasks.url_fact_check_process.run(url, self.claim.pk)
        self.bridge.assert_not_called()
        self.provider_class.assert_not_called()
        self.client.search.assert_not_called()
        legacy_client.return_value.search.assert_called_once()
        self.assertEqual(
            legacy_client.return_value.search.call_args.kwargs["request_timeout"],
            tasks.DEFAULT_HTTP_TIMEOUT_SEC,
        )
        evaluate_url.assert_called_once()
        self.evaluate_tavily.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.assertEqual(self.claim.verification_runs.get().status, VerificationRun.Status.COMPLETED)
