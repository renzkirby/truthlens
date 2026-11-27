import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from api import services, tasks
from api.verification.runs import CURRENT_VERIFICATION_PIPELINE_VERSION


class VerificationAuditRemediationV1412Tests(SimpleTestCase):
    def _secondary_item(self, **overrides):
        values = {
            "provider": "TAVILY",
            "url": "https://verafiles.org/articles/example",
            "title": "Example claim SATIRE - VERA Files",
            "content": "A short search snippet that omits the provenance explanation.",
            "stance": "REFUTES",
            "relevance_score": 1.0,
            "directness_score": 0.95,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_satire_extract_trigger_requires_title_signal_quality_and_missing_body_signal(self):
        qualified = self._secondary_item()
        low_quality = self._secondary_item(
            url="https://verafiles.org/articles/low",
            relevance_score=0.4,
        )
        already_explained = self._secondary_item(
            url="https://verafiles.org/articles/explained",
            content="The same submitted post was explicitly labeled satire.",
        )
        no_title_signal = self._secondary_item(
            url="https://verafiles.org/articles/plain",
            title="Ordinary fact-check article",
        )
        groups = [SimpleNamespace(
            evidence=(qualified, low_quality, already_explained, no_title_signal)
        )]

        self.assertEqual(
            tasks._satire_provenance_extract_urls(groups),
            ["https://verafiles.org/articles/example"],
        )

    def test_satire_provenance_enrichment_is_bounded_and_assessed(self):
        groups = [SimpleNamespace(evidence=(self._secondary_item(),))]
        run = SimpleNamespace(pk="run-id")
        provider = Mock()
        raw_item = SimpleNamespace(provider="TAVILY_EXTRACT")
        provider.extract_with_payload.return_value = (
            {"results": [{"url": "https://verafiles.org/articles/example"}]},
            [raw_item],
        )
        source = SimpleNamespace(pk="source-id")
        link = SimpleNamespace(pk="link-id")

        with patch("api.tasks.TavilyProvider", return_value=provider), patch(
            "api.tasks.ingest_raw_evidence", return_value=[source]
        ) as ingest, patch(
            "api.tasks.link_evidence_sources_to_run", return_value=[link]
        ) as link_sources, patch(
            "api.tasks.record_retrieval_provenance"
        ) as provenance, patch(
            "api.tasks.load_reasoning_evidence_dossier_for_run", return_value=groups
        ), patch(
            "api.tasks.filter_reasoning_evidence_dossier_by_role",
            return_value=groups,
        ), patch(
            "api.tasks._assess_and_persist_reasoning_evidence"
        ) as assess, patch(
            "api.tasks._log_stage"
        ):
            enriched = tasks._attempt_satire_provenance_enrichment(
                cleaned_claim="The submitted factual-looking claim.",
                claim_id="claim-id",
                run=run,
                secondary_groups=groups,
                is_text_claim=True,
            )

        self.assertTrue(enriched)
        provider.extract_with_payload.assert_called_once_with(
            ["https://verafiles.org/articles/example"],
            query="The submitted factual-looking claim.",
            limit=2,
            timeout=8.0,
        )
        ingest.assert_called_once_with([raw_item])
        link_sources.assert_called_once()
        provenance.assert_called_once()
        self.assertEqual(
            provenance.call_args.kwargs["provider"],
            "TAVILY_EXTRACT",
        )
        assess.assert_called_once()

    def test_gfc_equivalence_downgrades_when_commemorative_purpose_is_missing(self):
        response = json.dumps({
            "candidates": [{
                "candidate_index": 0,
                "relationship": "EQUIVALENT_OR_COVERS",
                "reasoning": "The same banknote issuance is described.",
                "material_differences": [],
            }],
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ):
            result = services.assess_fact_check_proposition_coverage(
                (
                    "The central bank issued a new 500-peso banknote featuring "
                    "Former President A to commemorate him."
                ),
                [
                    (
                        "The central bank newly released a 500-peso banknote "
                        "bearing Former President A's face."
                    )
                ],
            )

        self.assertFalse(result["terminally_sufficient"])
        self.assertEqual(result["reason_code"], "RELATED_BUT_INCOMPLETE")
        row = result["candidates"][0]
        self.assertEqual(row["relationship"], "PARTIAL_OR_RELATED")
        self.assertIn("commemorative/tribute purpose", row["material_differences"][0])

    def test_gfc_equivalence_keeps_candidate_that_covers_commemorative_purpose(self):
        response = json.dumps({
            "candidates": [{
                "candidate_index": 0,
                "relationship": "EQUIVALENT_OR_COVERS",
                "reasoning": "Every material qualifier is covered.",
                "material_differences": [],
            }],
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ):
            result = services.assess_fact_check_proposition_coverage(
                (
                    "The central bank issued a new banknote featuring Former "
                    "President A to commemorate him."
                ),
                [
                    (
                        "A commemorative new banknote featuring Former "
                        "President A was issued by the central bank."
                    )
                ],
            )

        self.assertTrue(result["terminally_sufficient"])
        self.assertEqual(
            result["candidates"][0]["relationship"],
            "EQUIVALENT_OR_COVERS",
        )

    def test_gfc_prompt_explicitly_treats_purpose_as_truth_relevant(self):
        response = json.dumps({
            "candidates": [{
                "candidate_index": 0,
                "relationship": "PARTIAL_OR_RELATED",
                "reasoning": "Purpose differs.",
                "material_differences": ["Purpose differs."],
            }],
        })
        with patch(
            "api.services.call_llm_with_fallback",
            return_value=response,
        ) as provider:
            services.assess_fact_check_proposition_coverage(
                "Agency A acted to commemorate Person B.",
                ["Agency A acted."],
            )

        system_prompt = provider.call_args.args[0]
        for required in (
            "purpose/rationale/intent",
            'A purpose clause such as "to commemorate"',
            "does NOT fully cover",
        ):
            with self.subTest(required=required):
                self.assertIn(required, system_prompt)

    def test_verdict_affecting_second_remediation_has_new_pipeline_version(self):
        self.assertEqual(CURRENT_VERIFICATION_PIPELINE_VERSION, "1.4.12")
