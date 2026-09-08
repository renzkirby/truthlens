from unittest.mock import Mock, patch

import requests

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase

from api.models import Claim, EvidenceSource, VerificationEvidence
from api.verification.contracts import RawEvidence
from api.verification.ingestion import ingest_raw_evidence
from api.verification.runs import create_verification_run, start_verification_run

from api.tasks import (
    GFC_HTTP_TIMEOUT_SEC,
    _retrieve_and_ingest_gfc,
    execute_core_text_pipeline,
    url_fact_check_process,
)


class GoogleFactCheckRuntimeBridgeTests(SimpleTestCase):
    def test_retrieval_uses_one_provider_call_and_ingests_evidence(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                }
            ]
        }

        raw_evidence_items = [
            Mock(),
        ]

        persisted_sources = [
            Mock(),
        ]

        with (
            patch("api.tasks.GoogleFactCheckProvider") as provider_class,
            patch("api.tasks.ingest_raw_evidence") as ingest,
            patch("api.tasks._log_stage"),
        ):
            provider = provider_class.return_value

            provider.search_with_payload.return_value = (
                payload,
                raw_evidence_items,
            )

            ingest.return_value = persisted_sources

            returned_payload = _retrieve_and_ingest_gfc(
                "example claim",
                "claim-id",
            )

        self.assertIs(
            returned_payload,
            payload,
        )

        provider_class.assert_called_once_with(
            timeout=GFC_HTTP_TIMEOUT_SEC,
        )

        provider.search_with_payload.assert_called_once_with(
            "example claim",
            limit=5,
        )

        ingest.assert_called_once_with(raw_evidence_items)

    def test_ingestion_failure_does_not_discard_gfc_payload(
        self,
    ):
        payload = {
            "claims": [
                {
                    "text": "Example claim.",
                }
            ]
        }

        raw_evidence_items = [
            Mock(),
        ]

        with (
            patch("api.tasks.GoogleFactCheckProvider") as provider_class,
            patch(
                "api.tasks.ingest_raw_evidence",
                side_effect=RuntimeError("database unavailable"),
            ),
            patch("api.tasks._log_stage"),
        ):
            provider = provider_class.return_value

            provider.search_with_payload.return_value = (
                payload,
                raw_evidence_items,
            )

            returned_payload = _retrieve_and_ingest_gfc(
                "example claim",
                "claim-id",
            )

        self.assertIs(
            returned_payload,
            payload,
        )

    def test_provider_failure_still_propagates_to_runtime_fallback(
        self,
    ):
        with (
            patch("api.tasks.GoogleFactCheckProvider") as provider_class,
            patch("api.tasks.ingest_raw_evidence") as ingest,
        ):
            provider = provider_class.return_value

            provider.search_with_payload.side_effect = requests.HTTPError(
                "Google unavailable"
            )

            with self.assertRaises(requests.HTTPError):
                _retrieve_and_ingest_gfc(
                    "example claim",
                    "claim-id",
                )

        ingest.assert_not_called()

    def test_text_pipeline_uses_runtime_bridge_and_preserves_gfc_verdict_path(
        self,
    ):
        claim_id = "claim-id"

        cleaned_claim = "Example public claim."

        search_query = "example public claim"

        gfc_payload = {
            "claims": [
                {
                    "text": ("Example public claim."),
                    "claimReview": [
                        {
                            "publisher": {
                                "name": ("Example Checker"),
                            },
                            "url": ("https://example.com/" "fact-check"),
                            "textualRating": ("False"),
                        }
                    ],
                }
            ]
        }

        ai_verdict = {
            "verdict": "FAKE",
            "summary": "Example summary.",
            "confidence_score": 95,
        }

        claim_queryset = Mock()
        claim_queryset.first.return_value = Mock()

        with (
            patch("api.tasks.create_verification_run"),
            patch("api.tasks.start_verification_run") as start_run,
            patch("api.tasks.complete_verification_run"),
            patch("api.tasks.abstain_verification_run"),
            patch("api.tasks.fail_verification_run"),
            patch(
                "api.claim_matching.compute_fingerprint",
                return_value="fingerprint",
            ),
            patch(
                "api.claim_matching.find_matching_claim",
                return_value=None,
            ),
            patch(
                "api.tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": cleaned_claim,
                    "search_query": search_query,
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.tasks.Claim.objects.filter",
                return_value=claim_queryset,
            ),
            patch(
                "api.tasks.search_official_vault",
                return_value=None,
            ),
            patch(
                "api.tasks._retrieve_and_ingest_gfc",
                return_value=gfc_payload,
            ) as retrieve_gfc,
            patch(
                "api.tasks.is_fact_check_relevant",
                return_value=True,
            ) as relevance_check,
            patch(
                "api.tasks.evaluate_image_claim_with_gfc",
                return_value=ai_verdict,
            ) as evaluate_gfc,
            patch("api.tasks._save_claim") as save_claim,
            patch("api.tasks.TavilyClient") as tavily_class,
            patch("api.tasks.requests.get") as requests_get,
            patch("api.tasks._log_stage"),
        ):
            execute_core_text_pipeline(
                "Raw submitted claim.",
                claim_id,
            )

        retrieve_gfc.assert_called_once_with(
            search_query,
            claim_id,
            verification_run=start_run.return_value,
        )

        relevance_check.assert_called_once_with(
            cleaned_claim,
            "Example public claim.",
        )

        evaluate_gfc.assert_called_once_with(
            cleaned_claim,
            gfc_payload,
            "NEUTRAL",
        )

        save_claim.assert_called_once_with(
            claim_id,
            ai_verdict,
            "Official Fact Check",
            cleaned_claim,
            ["https://example.com/" "fact-check"],
        )

        tavily_class.assert_not_called()

        requests_get.assert_not_called()

    def test_text_pipeline_provider_failure_still_falls_back_to_tavily(
        self,
    ):
        claim_id = "claim-id"

        cleaned_claim = "Example public claim."

        search_query = "example public claim"

        tavily_response = {
            "answer": "Web evidence answer.",
            "results": [
                {
                    "title": "Web Result",
                    "url": ("https://example.com/web"),
                    "content": ("Relevant web evidence."),
                }
            ],
        }

        ai_verdict = {
            "verdict": "UNVERIFIED",
            "summary": "Example summary.",
            "confidence_score": 60,
        }

        claim_queryset = Mock()
        claim_queryset.first.return_value = Mock()

        with (
            patch("api.tasks.create_verification_run"),
            patch("api.tasks.start_verification_run") as start_run,
            patch("api.tasks.complete_verification_run"),
            patch("api.tasks.abstain_verification_run"),
            patch("api.tasks.fail_verification_run"),
            patch(
                "api.claim_matching.compute_fingerprint",
                return_value="fingerprint",
            ),
            patch(
                "api.claim_matching.find_matching_claim",
                return_value=None,
            ),
            patch(
                "api.tasks.clean_ocr_text",
                return_value={
                    "cleaned_claim": cleaned_claim,
                    "search_query": search_query,
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.tasks.Claim.objects.filter",
                return_value=claim_queryset,
            ),
            patch(
                "api.tasks.search_official_vault",
                return_value=None,
            ),
            patch(
                "api.tasks._retrieve_and_ingest_gfc",
                side_effect=requests.HTTPError("Google unavailable"),
            ) as retrieve_gfc,
            patch(
                "api.tasks.evaluate_image_claim_with_tavily",
                return_value=ai_verdict,
            ),
            patch("api.tasks._save_claim") as save_claim,
            patch("api.tasks._retrieve_and_ingest_tavily") as retrieve_tavily,
            patch("api.tasks.requests.get") as requests_get,
            patch("api.tasks._log_stage"),
        ):
            retrieve_tavily.return_value = tavily_response

            execute_core_text_pipeline(
                "Raw submitted claim.",
                claim_id,
            )

        retrieve_gfc.assert_called_once_with(
            search_query,
            claim_id,
            verification_run=start_run.return_value,
        )

        retrieve_tavily.assert_called_once_with(search_query, claim_id)

        self.assertEqual(
            save_claim.call_args.args[2],
            "Live Web Search",
        )

        requests_get.assert_not_called()

    def test_url_pipeline_uses_runtime_bridge_and_preserves_gfc_verdict_path(
        self,
    ):
        claim_id = "claim-id"
        source_url = "https://example.com/article"

        cleaned_text = "Cleaned article content."
        cleaned_claim = "Example public claim."
        search_query = "example public claim"

        extraction_response = Mock()
        extraction_response.status_code = 200
        extraction_response.json.return_value = {
            "results": [
                {
                    "raw_content": ("Raw article content."),
                }
            ]
        }

        gfc_payload = {
            "claims": [
                {
                    "text": "Example public claim.",
                    "claimReview": [
                        {
                            "publisher": {
                                "name": "Example Checker",
                            },
                            "url": ("https://example.com/" "fact-check"),
                            "textualRating": "False",
                        }
                    ],
                }
            ]
        }

        ai_verdict = {
            "verdict": "FAKE",
            "summary": "Example summary.",
            "confidence_score": 95,
        }

        claim_queryset = Mock()
        claim_queryset.first.return_value = Mock()

        with (
            patch("api.tasks.create_verification_run"),
            patch("api.tasks.start_verification_run") as start_run,
            patch("api.tasks.complete_verification_run"),
            patch("api.tasks.abstain_verification_run"),
            patch("api.tasks.fail_verification_run"),
            patch(
                "api.tasks.requests.post",
                return_value=extraction_response,
            ) as requests_post,
            patch("api.tasks.requests.get") as requests_get,
            patch(
                "api.tasks.clean_extracted_text",
                return_value=cleaned_text,
            ),
            patch(
                "api.tasks.extract_search_query",
                return_value={
                    "cleaned_claim": cleaned_claim,
                    "search_query": search_query,
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.tasks.Claim.objects.filter",
                return_value=claim_queryset,
            ),
            patch(
                "api.tasks.search_official_vault",
                return_value=None,
            ),
            patch(
                "api.tasks._retrieve_and_ingest_gfc",
                return_value=gfc_payload,
            ) as retrieve_gfc,
            patch(
                "api.tasks.is_fact_check_relevant",
                return_value=True,
            ) as relevance_check,
            patch(
                "api.tasks.evaluate_url_claim_with_gfc",
                return_value=ai_verdict,
            ) as evaluate_gfc,
            patch("api.tasks._save_claim") as save_claim,
            patch("api.tasks.TavilyClient") as tavily_class,
            patch("api.tasks._log_stage"),
        ):
            url_fact_check_process.run(
                source_url,
                claim_id,
            )

        retrieve_gfc.assert_called_once_with(
            search_query,
            claim_id,
            stage_prefix="url_",
            verification_run=start_run.return_value,
        )

        relevance_check.assert_called_once_with(
            cleaned_claim,
            "Example public claim.",
        )

        evaluate_gfc.assert_called_once_with(
            cleaned_claim,
            gfc_payload,
            "NEUTRAL",
        )

        save_claim.assert_called_once_with(
            claim_id,
            ai_verdict,
            "Official Fact Check",
            cleaned_text,
            ["https://example.com/" "fact-check"],
        )

        requests_post.assert_called_once()
        requests_get.assert_not_called()
        tavily_class.assert_not_called()

    def test_url_pipeline_provider_failure_still_falls_back_to_tavily(
        self,
    ):
        claim_id = "claim-id"
        source_url = "https://example.com/article"

        cleaned_text = "Cleaned article content."
        cleaned_claim = "Example public claim."
        search_query = "example public claim"

        extraction_response = Mock()
        extraction_response.status_code = 200
        extraction_response.json.return_value = {
            "results": [
                {
                    "raw_content": ("Raw article content."),
                }
            ]
        }

        tavily_response = {
            "answer": "Web evidence answer.",
            "results": [
                {
                    "title": "Web Result",
                    "url": "https://example.com/web",
                    "content": ("Relevant web evidence."),
                }
            ],
        }

        ai_verdict = {
            "verdict": "UNVERIFIED",
            "summary": "Example summary.",
            "confidence_score": 60,
        }

        claim_queryset = Mock()
        claim_queryset.first.return_value = Mock()

        with (
            patch("api.tasks.create_verification_run"),
            patch("api.tasks.start_verification_run") as start_run,
            patch("api.tasks.complete_verification_run"),
            patch("api.tasks.abstain_verification_run"),
            patch("api.tasks.fail_verification_run"),
            patch(
                "api.tasks.requests.post",
                return_value=extraction_response,
            ),
            patch("api.tasks.requests.get") as requests_get,
            patch(
                "api.tasks.clean_extracted_text",
                return_value=cleaned_text,
            ),
            patch(
                "api.tasks.extract_search_query",
                return_value={
                    "cleaned_claim": cleaned_claim,
                    "search_query": search_query,
                    "article_stance": "NEUTRAL",
                },
            ),
            patch(
                "api.tasks.Claim.objects.filter",
                return_value=claim_queryset,
            ),
            patch(
                "api.tasks.search_official_vault",
                return_value=None,
            ),
            patch(
                "api.tasks._retrieve_and_ingest_gfc",
                side_effect=requests.HTTPError("Google unavailable"),
            ) as retrieve_gfc,
            patch(
                "api.tasks.evaluate_url_claim_with_tavily",
                return_value=ai_verdict,
            ),
            patch("api.tasks._save_claim") as save_claim,
            patch("api.tasks.TavilyClient") as tavily_class,
            patch("api.tasks._log_stage"),
        ):
            tavily_class.return_value.search.return_value = tavily_response

            url_fact_check_process.run(
                source_url,
                claim_id,
            )

        retrieve_gfc.assert_called_once_with(
            search_query,
            claim_id,
            stage_prefix="url_",
            verification_run=start_run.return_value,
        )

        (tavily_class.return_value.search.assert_called_once())

        self.assertEqual(
            save_claim.call_args.args[2],
            "Live Web Search",
        )

        requests_get.assert_not_called()


class GoogleFactCheckEvidenceLinkingTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(context_text="Example claim.")
        self.run = start_verification_run(create_verification_run(self.claim))
        self.payload = {"claims": [{"text": "Example claim."}]}
        self.raw_sources = [RawEvidence(
            provider="GOOGLE_FACT_CHECK", url="https://example.com/first",
            title="First fact check", content="Rating: False", source_type="FACT_CHECK",
        )]
        provider_class = self.enterContext(patch("api.tasks.GoogleFactCheckProvider"))
        self.provider = provider_class.return_value
        self.provider.search_with_payload.return_value = (self.payload, self.raw_sources)
        self.log_stage = self.enterContext(patch("api.tasks._log_stage"))

    def _retrieve(self, **kwargs):
        return _retrieve_and_ingest_gfc("example query", self.claim.pk, **kwargs)

    def _stages(self):
        return [call.args[1] for call in self.log_stage.call_args_list]

    def test_no_run_preserves_payload_and_ingestion_without_links(self):
        with patch("api.tasks.link_evidence_sources_to_run") as link_sources:
            returned = self._retrieve(stage_prefix="url_")
        self.assertIs(returned, self.payload)
        link_sources.assert_not_called()
        self.provider.search_with_payload.assert_called_once_with("example query", limit=5)
        self.assertEqual(EvidenceSource.objects.count(), 1)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.assertEqual(self._stages(), ["url_gfc_evidence_ingestion"])

    def test_successful_ingestion_links_sources_to_supplied_run(self):
        returned = self._retrieve(verification_run=self.run)
        self.assertIs(returned, self.payload)
        link = VerificationEvidence.objects.get()
        self.assertEqual(link.verification_run_id, self.run.pk)
        self.assertEqual(link.evidence_source_id, EvidenceSource.objects.get().pk)
        self.assertEqual(link.evidence_role, VerificationEvidence.EvidenceRole.FACT_CHECK)
        self.assertEqual(link.stance, VerificationEvidence.Stance.UNKNOWN)
        self.assertIsNone(link.relevance_score)
        self.assertIsNone(link.directness_score)
        self.assertIsNone(link.recency_score)
        self.provider.search_with_payload.assert_called_once_with("example query", limit=5)
        self.assertEqual(self._stages(), ["gfc_evidence_ingestion", "gfc_evidence_linking"])

    def test_ingestion_failure_skips_linking_and_preserves_payload(self):
        with (
            patch("api.tasks.ingest_raw_evidence", side_effect=IntegrityError("Ingestion failed")),
            patch("api.tasks.link_evidence_sources_to_run") as link_sources,
        ):
            returned = self._retrieve(verification_run=self.run)
        self.assertIs(returned, self.payload)
        link_sources.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.assertEqual(self._stages(), ["gfc_evidence_ingestion_failed"])

    def test_linking_failure_preserves_sources_and_payload(self):
        self.raw_sources.append(RawEvidence(
            provider="GOOGLE_FACT_CHECK", url="https://example.com/second",
            content="Second fact check", source_type="FACT_CHECK",
        ))
        get_or_create = VerificationEvidence.objects.get_or_create

        def fail_second_link(**kwargs):
            if kwargs["evidence_source"].url == "https://example.com/second":
                self.assertEqual(VerificationEvidence.objects.count(), 1)
                raise IntegrityError("Second link failed")
            return get_or_create(**kwargs)

        with patch(
            "api.verification.linking.VerificationEvidence.objects.get_or_create",
            side_effect=fail_second_link,
        ) as create_link:
            returned = self._retrieve(verification_run=self.run)

        self.assertIs(returned, self.payload)
        self.assertEqual(create_link.call_count, 2)
        self.assertEqual(EvidenceSource.objects.count(), 2)
        self.assertEqual(VerificationEvidence.objects.count(), 0)
        self.assertEqual(self._stages(), ["gfc_evidence_ingestion", "gfc_evidence_linking_failed"])
        self.assertEqual(self.log_stage.call_args.kwargs["verification_run_id"], self.run.pk)
        self.assertEqual(self.log_stage.call_args.kwargs["error"], "Second link failed")
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "RUNNING")
        self.assertIsNone(self.run.failure_code)

    def test_provider_failure_skips_ingestion_and_linking(self):
        self.provider.search_with_payload.side_effect = requests.HTTPError("Provider unavailable")
        with (
            patch("api.tasks.ingest_raw_evidence") as ingest,
            patch("api.tasks.link_evidence_sources_to_run") as link_sources,
        ):
            with self.assertRaisesMessage(requests.HTTPError, "Provider unavailable"):
                self._retrieve(verification_run=self.run)
        ingest.assert_not_called()
        link_sources.assert_not_called()
        self.assertEqual(EvidenceSource.objects.count(), 0)
        self.assertEqual(VerificationEvidence.objects.count(), 0)

    def test_reused_evidence_source_links_without_source_duplication(self):
        existing = ingest_raw_evidence(self.raw_sources)[0]
        before = EvidenceSource.objects.values().get(pk=existing.pk)
        for _ in range(2):
            self.assertIs(self._retrieve(verification_run=self.run), self.payload)
        self.assertEqual(EvidenceSource.objects.count(), 1)
        self.assertEqual(EvidenceSource.objects.values().get(pk=existing.pk), before)
        self.assertEqual(VerificationEvidence.objects.get().evidence_source_id, existing.pk)

    def test_stage_prefix_applies_to_linking_success_and_failure(self):
        self._retrieve(verification_run=self.run, stage_prefix="test_")
        with patch("api.tasks.link_evidence_sources_to_run", side_effect=RuntimeError("Link failed")):
            self.assertIs(
                self._retrieve(verification_run=self.run, stage_prefix="test_"), self.payload,
            )
        self.assertEqual(self._stages(), [
            "test_gfc_evidence_ingestion", "test_gfc_evidence_linking",
            "test_gfc_evidence_ingestion", "test_gfc_evidence_linking_failed",
        ])
        self.assertEqual(VerificationEvidence.objects.count(), 1)
