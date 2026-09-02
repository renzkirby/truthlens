from unittest.mock import Mock, patch

import requests

from django.test import SimpleTestCase

from .tasks import (
    GFC_HTTP_TIMEOUT_SEC,
    _retrieve_and_ingest_gfc,
    execute_core_text_pipeline,
)


class GoogleFactCheckRuntimeBridgeTests(
    SimpleTestCase
):
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
            patch(
                "api.tasks.GoogleFactCheckProvider"
            ) as provider_class,
            patch(
                "api.tasks.ingest_raw_evidence"
            ) as ingest,
            patch(
                "api.tasks._log_stage"
            ),
        ):
            provider = (
                provider_class.return_value
            )

            provider.search_with_payload.return_value = (
                payload,
                raw_evidence_items,
            )

            ingest.return_value = (
                persisted_sources
            )

            returned_payload = (
                _retrieve_and_ingest_gfc(
                    "example claim",
                    "claim-id",
                )
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

        ingest.assert_called_once_with(
            raw_evidence_items
        )

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
            patch(
                "api.tasks.GoogleFactCheckProvider"
            ) as provider_class,
            patch(
                "api.tasks.ingest_raw_evidence",
                side_effect=RuntimeError(
                    "database unavailable"
                ),
            ),
            patch(
                "api.tasks._log_stage"
            ),
        ):
            provider = (
                provider_class.return_value
            )

            provider.search_with_payload.return_value = (
                payload,
                raw_evidence_items,
            )

            returned_payload = (
                _retrieve_and_ingest_gfc(
                    "example claim",
                    "claim-id",
                )
            )

        self.assertIs(
            returned_payload,
            payload,
        )

    def test_provider_failure_still_propagates_to_runtime_fallback(
        self,
    ):
        with (
            patch(
                "api.tasks.GoogleFactCheckProvider"
            ) as provider_class,
            patch(
                "api.tasks.ingest_raw_evidence"
            ) as ingest,
        ):
            provider = (
                provider_class.return_value
            )

            provider.search_with_payload.side_effect = (
                requests.HTTPError(
                    "Google unavailable"
                )
            )

            with self.assertRaises(
                requests.HTTPError
            ):
                _retrieve_and_ingest_gfc(
                    "example claim",
                    "claim-id",
                )

        ingest.assert_not_called()

    def test_text_pipeline_uses_runtime_bridge_and_preserves_gfc_verdict_path(
        self,
    ):
        claim_id = "claim-id"

        cleaned_claim = (
            "Example public claim."
        )

        search_query = (
            "example public claim"
        )

        gfc_payload = {
            "claims": [
                {
                    "text": (
                        "Example public claim."
                    ),
                    "claimReview": [
                        {
                            "publisher": {
                                "name": (
                                    "Example Checker"
                                ),
                            },
                            "url": (
                                "https://example.com/"
                                "fact-check"
                            ),
                            "textualRating": (
                                "False"
                            ),
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
        claim_queryset.first.return_value = (
            Mock()
        )

        with (
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
            patch(
                "api.tasks._save_claim"
            ) as save_claim,
            patch(
                "api.tasks.TavilyClient"
            ) as tavily_class,
            patch(
                "api.tasks.requests.get"
            ) as requests_get,
            patch(
                "api.tasks._log_stage"
            ),
        ):
            execute_core_text_pipeline(
                "Raw submitted claim.",
                claim_id,
            )

        retrieve_gfc.assert_called_once_with(
            search_query,
            claim_id,
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
            [
                (
                    "https://example.com/"
                    "fact-check"
                )
            ],
        )

        tavily_class.assert_not_called()

        requests_get.assert_not_called()

    def test_text_pipeline_provider_failure_still_falls_back_to_tavily(
        self,
    ):
        claim_id = "claim-id"

        cleaned_claim = (
            "Example public claim."
        )

        search_query = (
            "example public claim"
        )

        tavily_response = {
            "answer": "Web evidence answer.",
            "results": [
                {
                    "title": "Web Result",
                    "url": (
                        "https://example.com/web"
                    ),
                    "content": (
                        "Relevant web evidence."
                    ),
                }
            ],
        }

        ai_verdict = {
            "verdict": "UNVERIFIED",
            "summary": "Example summary.",
            "confidence_score": 60,
        }

        claim_queryset = Mock()
        claim_queryset.first.return_value = (
            Mock()
        )

        with (
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
                side_effect=requests.HTTPError(
                    "Google unavailable"
                ),
            ) as retrieve_gfc,
            patch(
                "api.tasks.evaluate_image_claim_with_tavily",
                return_value=ai_verdict,
            ),
            patch(
                "api.tasks._save_claim"
            ) as save_claim,
            patch(
                "api.tasks.TavilyClient"
            ) as tavily_class,
            patch(
                "api.tasks.requests.get"
            ) as requests_get,
            patch(
                "api.tasks._log_stage"
            ),
        ):
            (
                tavily_class
                .return_value
                .search
                .return_value
            ) = tavily_response

            execute_core_text_pipeline(
                "Raw submitted claim.",
                claim_id,
            )

        retrieve_gfc.assert_called_once_with(
            search_query,
            claim_id,
        )

        (
            tavily_class
            .return_value
            .search
            .assert_called_once()
        )

        self.assertEqual(
            save_claim.call_args.args[2],
            "Live Web Search",
        )

        requests_get.assert_not_called()
