from unittest.mock import Mock, patch

import requests

from django.test import SimpleTestCase

from .tasks import (
    GFC_HTTP_TIMEOUT_SEC,
    _retrieve_and_ingest_gfc,
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
