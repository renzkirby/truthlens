import os
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from api import tasks
from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification.contracts import RawEvidence
from api.verification.ingestion import ingest_raw_evidence
from api.verification.linking import link_evidence_sources_to_run


class PersistenceQueryCountTests(TestCase):
    """Deterministic ORM-query regression coverage for Tavily persistence."""

    # Captured on PostgreSQL from the same fixtures before the optimization.
    BEFORE_QUERY_COUNTS = {
        "ingest_5_new": 46,
        "ingest_5_existing": 22,
        "link_5_new": 23,
        "link_5_existing": 8,
        "full_path_1q_x_5": 73,
        "full_path_3q_x_5": 197,
    }
    QUERY_BOUNDS = {
        "ingest_5_new": 22,
        "ingest_5_existing": 11,
        "link_5_new": 7,
        "link_5_existing": 5,
        "full_path_1q_x_5": 34,
        "full_path_3q_x_5": 88,
    }

    def setUp(self):
        self.claim = Claim.objects.create(context_text="Query-count fixture claim.")
        self.run = VerificationRun.objects.create(claim=self.claim)

    @staticmethod
    def _raw_items(prefix="source"):
        return [
            RawEvidence(
                provider="TAVILY",
                url=f"https://example.com/{prefix}-{index}",
                content=f"{prefix} content {index}",
                source_type="WEB_SEARCH",
                raw_reference={"tavily_result_index": index},
            )
            for index in range(5)
        ]

    @staticmethod
    def _report(name, count):
        if os.environ.get("TRUTHLENS_REPORT_QUERY_COUNTS") == "1":
            print(f"QUERY_COUNT {name}={count}")

    def _capture(self, name, operation):
        with CaptureQueriesContext(connection) as queries:
            result = operation()
        count = len(queries)
        self._report(name, count)
        self.assertLessEqual(count, self.QUERY_BOUNDS[name])
        return result, count

    def test_ingest_five_new_sources_query_bound(self):
        sources, count = self._capture(
            "ingest_5_new",
            lambda: ingest_raw_evidence(self._raw_items()),
        )

        self.assertEqual(len(sources), 5)
        self.assertEqual(EvidenceSource.objects.count(), 5)
        self.assertGreater(count, 0)

    def test_ingest_five_existing_sources_query_bound(self):
        existing = ingest_raw_evidence(self._raw_items())

        sources, count = self._capture(
            "ingest_5_existing",
            lambda: ingest_raw_evidence(self._raw_items()),
        )

        self.assertEqual([source.pk for source in sources], [source.pk for source in existing])
        self.assertEqual(EvidenceSource.objects.count(), 5)
        self.assertGreater(count, 0)

    def test_link_five_new_sources_query_bound(self):
        sources = ingest_raw_evidence(self._raw_items())

        links, count = self._capture(
            "link_5_new",
            lambda: link_evidence_sources_to_run(
                self.run,
                sources,
                evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            ),
        )

        self.assertEqual(len(links), 5)
        self.assertGreater(count, 0)

    def test_link_five_existing_sources_query_bound(self):
        sources = ingest_raw_evidence(self._raw_items())
        existing = link_evidence_sources_to_run(
            self.run,
            sources,
            evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
        )

        links, count = self._capture(
            "link_5_existing",
            lambda: link_evidence_sources_to_run(
                self.run,
                sources,
                evidence_role=VerificationEvidence.EvidenceRole.SECONDARY,
            ),
        )

        self.assertEqual([link.pk for link in links], [link.pk for link in existing])
        self.assertGreater(count, 0)

    def _retrieval_result(self, query_index):
        shared = RawEvidence(
            provider="TAVILY",
            url="https://example.com/shared",
            content="Shared evidence",
            source_type="WEB_SEARCH",
            raw_reference={"tavily_result_index": 0},
        )
        unique = [
            RawEvidence(
                provider="TAVILY",
                url=f"https://example.com/query-{query_index}-{index}",
                content=f"Query {query_index} evidence {index}",
                source_type="WEB_SEARCH",
                raw_reference={"tavily_result_index": index},
            )
            for index in range(1, 5)
        ]
        raw_items = [shared, *unique]
        payload = {
            "answer": f"Answer {query_index}",
            "results": [
                {"url": item.url, "content": item.content}
                for item in raw_items
            ],
        }
        return payload, raw_items

    def _capture_full_path(self, queries):
        results_by_query = {
            query: self._retrieval_result(index)
            for index, query in enumerate(queries)
        }

        with (
            patch("api.tasks._retrieve_tavily", side_effect=lambda query: results_by_query[query]),
            patch("api.tasks._log_stage"),
        ):
            return self._capture(
                f"full_path_{len(queries)}q_x_5",
                lambda: tasks._retrieve_and_ingest_tavily_queries(
                    queries,
                    str(self.claim.pk),
                    verification_run=self.run,
                ),
            )

    def test_one_query_five_result_full_path_query_bound(self):
        payload, count = self._capture_full_path(["query 0"])

        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual(VerificationEvidence.objects.count(), 5)
        self.assertGreater(count, 0)

    def test_three_query_five_result_overlapping_full_path_query_bound(self):
        payload, count = self._capture_full_path(["query 0", "query 1", "query 2"])

        self.assertEqual(len(payload["results"]), 13)
        self.assertEqual(VerificationEvidence.objects.count(), 13)
        shared_link = VerificationEvidence.objects.get(
            evidence_source__canonical_url="https://example.com/shared"
        )
        self.assertEqual(
            [entry["query_index"] for entry in shared_link.retrieval_provenance],
            [0, 1, 2],
        )
        self.assertGreater(count, 0)
