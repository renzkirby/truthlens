import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.test import SimpleTestCase, TestCase

from api import services
from api.models import Claim, EvidenceSource, VerificationEvidence, VerificationRun
from api.verification import evidence_budget as budget
from api.verification.evidence_assessment import (
    _SYSTEM_INSTRUCTIONS, assess_reasoning_evidence_batch_against_claim,
)
from api.verification.evidence_dossier import (
    ReasoningEvidenceGroup, ReasoningEvidenceItem,
    load_reasoning_evidence_dossier_for_run,
)
from api.verification.linking import link_evidence_sources_to_run, record_retrieval_provenance


def item(index, **overrides):
    values = dict(
        evidence_link_id=UUID(int=index + 1), evidence_source_id=UUID(int=index + 1),
        provider="TAVILY", url=f"https://example.com/{index}",
        canonical_url=f"https://example.com/{index}", title=f"Article {index}",
        publisher="Example", source_type="WEB_SEARCH", content=f"Distinct fact {index}.",
        published_at=None, retrieved_at=None, evidence_role="SECONDARY",
        stance="SUPPORTS", relevance_score=0.9, directness_score=0.9, recency_score=None,
    )
    values.update(overrides)
    return ReasoningEvidenceItem(**values)


def group(index, *items):
    return ReasoningEvidenceGroup("CANONICAL_SOURCE", UUID(int=index + 1), items)


def prompt(context):
    return services.build_persisted_evidence_prompt("The bridge opened in 2024.", context)


class EvidenceBudgetTests(SimpleTestCase):
    def test_soft_final_target_reserves_completion_and_keeps_existing_bounds(self):
        self.assertEqual(budget.soft_final_target(0), budget.FINAL_PROMPT_TARGET)
        recent = 1200
        available = (budget.LOCAL_GROQ_SOFT_TOKENS - recent
                     - budget.FINAL_EVALUATION_OUTPUT_TOKENS)
        self.assertGreater(available, budget.MIN_SOFT_PROMPT_TARGET)
        self.assertLess(available, budget.FINAL_PROMPT_TARGET)
        self.assertEqual(budget.soft_final_target(recent), available)
        self.assertEqual(budget.soft_final_target(100000), budget.MIN_SOFT_PROMPT_TARGET)
        targets = [budget.soft_final_target(usage) for usage in (0, 1200, 1800, 100000)]
        self.assertEqual(targets, sorted(targets, reverse=True))
        self.assertLess(targets[1], targets[0])
        self.assertLess(targets[2], targets[1])
        self.assertEqual(targets, [budget.soft_final_target(usage)
                                   for usage in (0, 1200, 1800, 100000)])

    def test_small_content_preserved_unchanged(self):
        text = "Hindi ito binuksan noong 2024. Only 12 permits."
        self.assertEqual(budget.bounded_content(text, 100), text)

    def test_oversized_representation_preserves_both_ends_and_late_qualification(self):
        text = "BEGINNING official report. " + "Background context. " * 5000 + (
            " Hindi ito totoo: NOT opened in 2024; only 12 permits, dated 2025-01-02. ENDING"
        )
        excerpt = budget.bounded_content(text, budget.ASSESSMENT_CONTENT_TOKENS)
        self.assertTrue(excerpt.startswith("BEGINNING"))
        self.assertTrue(excerpt.endswith("ENDING"))
        self.assertIn("NOT opened in 2024; only 12 permits, dated 2025-01-02.", excerpt)
        self.assertIn(budget.OMISSION_MARKER, excerpt)
        self.assertLessEqual(budget.token_count(excerpt), budget.ASSESSMENT_CONTENT_TOKENS)

    def test_complete_prompt_counts_instructions_and_wrappers(self):
        system, user = prompt("Evidence")
        estimate = budget.estimate_prompt_tokens(system, user)
        self.assertGreater(estimate, budget.token_count("Evidence"))
        self.assertGreater(estimate, budget.token_count(system) + budget.token_count(user))

    def test_unknown_model_fallback(self):
        with patch.dict("os.environ", {"GROQ_MODEL": "unknown-test-model"}):
            self.assertGreater(budget.token_count("Taglish: hindi totoo."), 0)

    def test_one_two_five_ten_and_fifteen_plus_items(self):
        for count in (1, 2, 5, 10, 17):
            with self.subTest(count=count):
                groups = [group(i, item(i)) for i in range(count)]
                dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
                self.assertTrue(dossier)
                self.assertEqual(metrics["reasoning_candidates"], count)
                self.assertLessEqual(metrics["final_prompt_tokens_est"], budget.HARD_PROMPT_TOKENS)
                self.assertEqual(dossier.count("Content:\n"), metrics["reasoning_selected"])
                self.assertEqual(dossier.count("--- EVIDENCE ITEM"), metrics["reasoning_selected"])
                self.assertIn("not guaranteed to be editorially independent", dossier)

    def test_diversity_prefers_second_source_group_under_constrained_budget(self):
        groups = [group(0, *(item(i) for i in range(5))), group(1, item(5, relevance_score=0.8))]
        with patch.object(budget, "estimate_prompt_tokens", side_effect=lambda system, user:
                          100 + 100 * user.count("--- EVIDENCE ITEM")), patch.object(
                              budget, "FINAL_PROMPT_TARGET", 300):
            dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertIn("Distinct fact 0.", dossier)
        self.assertIn("Distinct fact 5.", dossier)
        for index in range(1, 5):
            self.assertNotIn(f"Distinct fact {index}.", dossier)
        self.assertEqual(metrics["reasoning_selected"], 2)
        self.assertEqual(metrics["reasoning_groups"], 2)

    def test_distinct_articles_from_same_group_remain_eligible_with_roomy_budget(self):
        groups = [group(0, *(item(i) for i in range(5))), group(1, item(5, relevance_score=0.8))]
        dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertEqual(metrics["reasoning_selected"], 6)
        self.assertEqual(metrics["reasoning_groups"], 2)
        for index in range(6):
            self.assertIn(f"Distinct fact {index}.", dossier)

    def test_equal_scores_keep_input_order(self):
        groups = [group(0, item(2), item(0), item(1))]
        first = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertEqual(first, budget.bounded_reasoning_dossier(groups, prompt))
        self.assertLess(first[0].index("Distinct fact 2."), first[0].index("Distinct fact 0."))

    def test_competitive_opposition_survives_cutoff_in_both_directions(self):
        for majority, minority in (("SUPPORTS", "REFUTES"), ("REFUTES", "SUPPORTS")):
            with self.subTest(majority=majority):
                groups = [group(i, item(i, stance=majority,
                    content=f"Beginning {i}. " + "Report context. " * 800 + f" Ending {i}."))
                    for i in range(15)]
                groups.append(group(20, item(20, stance=minority, relevance_score=0.88,
                                            content="COMPETITIVE OPPOSITION.")))
                dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
                self.assertIn("COMPETITIVE OPPOSITION.", dossier)
                self.assertIn(f"Stance: {majority}", dossier)
                self.assertIn(f"Stance: {minority}", dossier)
                self.assertLessEqual(metrics["final_prompt_tokens_est"], budget.HARD_PROMPT_TOKENS)
                self.assertLessEqual(metrics["final_prompt_tokens_est"], metrics["final_prompt_budget"])

    def test_weak_opposition_does_not_get_artificial_priority(self):
        self.assertFalse(budget.competitively_strong(
            item(20, stance="REFUTES", relevance_score=0.2, directness_score=0.2),
            [item(0)],
        ))
        self.assertFalse(budget.competitively_strong(
            item(20, stance="REFUTES", relevance_score=None, directness_score=None),
            [item(0)],
        ))

    def test_context_does_not_lower_material_contradiction_threshold(self):
        for stance, opposite in (("SUPPORTS", "REFUTES"), ("REFUTES", "SUPPORTS")):
            with self.subTest(stance=stance):
                selected = [item(0, stance=stance, relevance_score=0.95, directness_score=0.95),
                            item(1, stance="CONTEXT", relevance_score=0.1, directness_score=0.1)]
                weak = item(2, stance=opposite, relevance_score=0.75, directness_score=0.75)
                self.assertFalse(budget.competitively_strong(weak, selected))
                self.assertTrue(budget.competitively_strong(replace(
                    weak, relevance_score=0.9, directness_score=0.9,
                ), selected))
                self.assertFalse(budget.competitively_strong(weak, selected[1:]))

    def test_assessed_groups_precede_unknown_without_equal_interleaving(self):
        groups = [group(i, item(i)) for i in range(4)] + [group(i, item(
            i, stance="UNKNOWN", relevance_score=None, directness_score=None,
        )) for i in range(4, 8)]
        dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertLess(dossier.index("Distinct fact 3."), dossier.index("Distinct fact 4."))
        self.assertIn("Distinct fact 4.", dossier)
        self.assertLessEqual(metrics["final_prompt_tokens_est"], metrics["final_prompt_budget"])

    def test_entirely_unknown_pool_is_deterministic_and_bounded(self):
        groups = [group(i, item(i, stance="UNKNOWN", relevance_score=None,
                                directness_score=None)) for i in range(20)]
        first = budget.bounded_reasoning_dossier(groups, prompt, 5000)
        self.assertEqual(first, budget.bounded_reasoning_dossier(groups, prompt, 5000))
        dossier, metrics = first
        self.assertTrue(dossier)
        self.assertGreater(metrics["reasoning_selected"], 0)
        self.assertNotIn("Relevance score:", dossier)
        self.assertNotIn("Directness score:", dossier)
        self.assertLessEqual(metrics["final_prompt_tokens_est"], budget.soft_final_target(5000))

    def test_limited_context_prefers_several_assessed_groups_and_one_unknown(self):
        groups = [group(i, item(i)) for i in range(5)] + [group(i, item(
            i, stance="UNKNOWN", relevance_score=None, directness_score=None,
        )) for i in range(5, 10)]
        with patch.object(budget, "estimate_prompt_tokens", side_effect=lambda system, user:
                          100 + 100 * user.count("--- EVIDENCE ITEM")), patch.object(
                              budget, "MIN_SOFT_PROMPT_TARGET", 100):
            dossier, metrics = budget.bounded_reasoning_dossier(
                groups, prompt, budget.LOCAL_GROQ_SOFT_TOKENS
                - budget.FINAL_EVALUATION_OUTPUT_TOKENS - 600,
            )
        self.assertEqual(dossier.count("Stance: SUPPORTS"), 4)
        self.assertEqual(dossier.count("Stance: UNKNOWN"), 1)
        self.assertEqual(metrics["reasoning_groups"], 5)

    def test_contradiction_respects_recent_usage_target_in_both_directions(self):
        # Controlled prompt costs force the opposition outside normal selection.
        # Each complete block costs 100; pressure allows exactly two blocks.
        def estimate(system, user):
            return 100 + 100 * user.count("--- EVIDENCE ITEM")

        for majority, minority in (("SUPPORTS", "REFUTES"), ("REFUTES", "SUPPORTS")):
            groups = [group(i, item(i, stance=majority)) for i in range(5)]
            groups.append(group(10, item(10, stance=minority, relevance_score=0.88)))
            with self.subTest(majority=majority), patch.object(
                budget, "estimate_prompt_tokens", side_effect=estimate,
            ), patch.object(budget, "MIN_SOFT_PROMPT_TARGET", 100):
                recent = (budget.LOCAL_GROQ_SOFT_TOKENS
                          - budget.FINAL_EVALUATION_OUTPUT_TOKENS - 300)
                dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt, recent)
                self.assertIn(f"Stance: {majority}", dossier)
                self.assertIn(f"Stance: {minority}", dossier)
                self.assertEqual(metrics["reasoning_selected"], 2)
                self.assertEqual(metrics["final_prompt_budget"], 300)
                self.assertLessEqual(metrics["final_prompt_tokens_est"], budget.soft_final_target(recent))

    def test_contradiction_cannot_fall_back_to_hard_ceiling_when_pair_will_not_fit(self):
        groups = [group(0, item(0)), group(1, item(1, stance="REFUTES", relevance_score=0.88))]
        with patch.object(budget, "estimate_prompt_tokens", side_effect=lambda system, user:
                          100 + 100 * user.count("--- EVIDENCE ITEM")), patch.object(
                              budget, "MIN_SOFT_PROMPT_TARGET", 100):
            recent = (budget.LOCAL_GROQ_SOFT_TOKENS
                      - budget.FINAL_EVALUATION_OUTPUT_TOKENS - 200)
            with self.assertRaises(budget.LLMRequestBudgetExceededError):
                budget.bounded_reasoning_dossier(groups, prompt, recent)

    def test_single_minimum_block_cannot_bypass_effective_target(self):
        with patch.object(budget, "estimate_prompt_tokens", return_value=1900):
            with self.assertRaises(budget.LLMRequestBudgetExceededError):
                budget.bounded_reasoning_dossier([group(0, item(0))], prompt, 100000)

    def test_partial_and_entirely_unavailable_pools_remain_eligible(self):
        unknown = item(20, stance="UNKNOWN", relevance_score=None, directness_score=None)
        for groups in ([group(0, item(0)), group(1, unknown)], [group(1, unknown)]):
            dossier, _ = budget.bounded_reasoning_dossier(groups, prompt)
            self.assertIn("Distinct fact 20.", dossier)
            self.assertNotIn("Relevance score: 0", dossier.split("Distinct fact 0.")[-1])
            self.assertIsNone(unknown.relevance_score)
            self.assertIsNone(unknown.directness_score)

    def test_unavailable_source_is_not_starved_by_many_scored_sources(self):
        groups = [group(i, item(i, content=f"Article {i}. " + "context " * 900))
                  for i in range(20)]
        groups.append(group(21, item(21, stance="UNKNOWN", relevance_score=None,
                                    directness_score=None, content="UNASSESSED FALLBACK")))
        dossier, _ = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertIn("UNASSESSED FALLBACK", dossier)

    def test_exact_duplicates_do_not_waste_context(self):
        original = item(0)
        groups = [group(0, original, replace(original, evidence_link_id=UUID(int=100))),
                  group(1, item(1, canonical_url=original.canonical_url)),
                  group(2, item(2, content="  Distinct   fact 0.  "))]
        _, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertEqual(metrics["reasoning_candidates"], 4)
        self.assertEqual(metrics["reasoning_selected"], 1)

    def test_soft_usage_reduces_target_without_account_wide_failure(self):
        groups = [group(i, item(i, content=f"Article {i}. " + "Context report. " * 800))
                  for i in range(20)]
        normal, _ = budget.bounded_reasoning_dossier(groups, prompt)
        pressured, metrics = budget.bounded_reasoning_dossier(groups, prompt, 1000000)
        self.assertTrue(pressured)
        self.assertLess(budget.token_count(pressured), budget.token_count(normal))
        self.assertLessEqual(metrics["final_prompt_tokens_est"], budget.HARD_PROMPT_TOKENS)

    def test_prior_ten_thousand_token_case_never_reaches_provider_oversized(self):
        groups = [group(i, item(i, content=f"Evidence {i}. " + "Report context. " * 500))
                  for i in range(15)]
        self.assertGreater(sum(budget.token_count(g.evidence[0].content) for g in groups), 10000)
        dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        response = json.dumps(dict(reasoning="Evidence", verdict="UNVERIFIED",
                                   summary="Insufficient", confidence_score=0, score_context="Context"))
        with patch("api.services.call_llm_with_fallback", return_value=response) as provider:
            services.evaluate_claim_with_persisted_evidence("The bridge opened in 2024.", dossier)
        system, user = provider.call_args.args
        self.assertLessEqual(budget.estimate_prompt_tokens(system, user), budget.HARD_PROMPT_TOKENS)
        self.assertLessEqual(metrics["final_prompt_tokens_est"], budget.FINAL_PROMPT_TARGET)

    def test_rich_block_shrinks_before_item_exclusion(self):
        groups = [group(0, item(0, content="BEGIN " + "context " * 2000 + " END"))]
        with patch.object(budget, "FINAL_PROMPT_TARGET", 1300):
            dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertEqual(metrics["reasoning_selected"], 1)
        self.assertIn("BEGIN", dossier)
        self.assertIn("END", dossier)
        self.assertIn(budget.OMISSION_MARKER, dossier)

    def test_impossible_minimum_request_raises_typed_failure_before_provider(self):
        huge_claim = "Oversized claim. " * 10000
        with patch("api.services.call_llm_with_fallback") as provider:
            with self.assertRaises(budget.LLMRequestBudgetExceededError):
                services.evaluate_claim_with_persisted_evidence(huge_claim, "Evidence.")
        provider.assert_not_called()

    def test_no_minimum_evidence_block_fits_raises(self):
        with patch.object(budget, "HARD_PROMPT_TOKENS", 100):
            with self.assertRaises(budget.LLMRequestBudgetExceededError):
                budget.bounded_reasoning_dossier([group(0, item(0))], prompt)


class AssessmentPackingTests(SimpleTestCase):
    @staticmethod
    def response(system, user, **kwargs):
        data = json.loads(user.split("\n", 1)[1])
        return json.dumps({"assessments": [dict(key=entry["key"], stance="CONTEXT",
            relevance_score=int(entry["key"].split("_")[1]) / 100, directness_score=0.8)
            for entry in reversed(data["evidence_items"])]})

    def test_small_sets_remain_one_call_and_metadata_is_excluded(self):
        for count in (1, 2, 5, 10, 17):
            with self.subTest(count=count), patch(
                "api.verification.evidence_assessment.call_llm_with_fallback",
                side_effect=self.response,
            ) as provider:
                results = assess_reasoning_evidence_batch_against_claim("Claim", [item(i) for i in range(count)])
                self.assertEqual(provider.call_count, 1)
                data = json.loads(provider.call_args.args[1].split("\n", 1)[1])
                self.assertEqual(set(data), {"claim_text", "evidence_items"})
                for entry in data["evidence_items"]:
                    self.assertEqual(set(entry), {"key", "evidence_content"})
                self.assertEqual([r.relevance_score for r in results], [i / 100 for i in range(count)])
                self.assertEqual(provider.call_args.kwargs["max_output_tokens"], budget.assessment_output_limit(count))
                self.assertLessEqual(
                    budget.estimate_prompt_tokens(*provider.call_args.args)
                    + provider.call_args.kwargs["max_output_tokens"],
                    budget.ASSESSMENT_REQUEST_TARGET,
                )

    def test_large_sets_use_maximal_packs_and_preserve_positions(self):
        items = [item(i, content=f"BEGIN {i}. " + "Long evidence. " * 1200 + f" END {i}.")
                 for i in range(17)]
        with patch("api.verification.evidence_assessment.call_llm_with_fallback",
                   side_effect=self.response) as provider:
            results = assess_reasoning_evidence_batch_against_claim("Claim", items)
        self.assertGreater(provider.call_count, 1)
        self.assertEqual([r.relevance_score for r in results], [i / 100 for i in range(17)])
        packs = []
        for call in provider.call_args_list:
            system, user = call.args
            self.assertLessEqual(budget.estimate_prompt_tokens(system, user), budget.HARD_PROMPT_TOKENS)
            self.assertLessEqual(budget.estimate_prompt_tokens(system, user)
                                 + call.kwargs["max_output_tokens"], budget.ASSESSMENT_REQUEST_TARGET)
            packs.append(json.loads(user.split("\n", 1)[1])["evidence_items"])
        for current, following in zip(packs, packs[1:]):
            self.assertFalse(budget.assessment_request_fits(
                _SYSTEM_INSTRUCTIONS, "Claim", current + following[:1],
            ))

    def test_completion_allowance_splits_batch_even_when_input_fits(self):
        items = [item(i) for i in range(60)]
        # A constant prompt estimate isolates output capacity as the split cause.
        with patch.object(budget, "estimate_prompt_tokens", return_value=2000), patch(
            "api.verification.evidence_assessment.call_llm_with_fallback", side_effect=self.response,
        ) as provider:
            results = assess_reasoning_evidence_batch_against_claim("Claim", items)
        capacity = ((budget.ASSESSMENT_REQUEST_TARGET - 2000 - budget.ASSESSMENT_OUTPUT_BASE)
                    // budget.ASSESSMENT_OUTPUT_PER_ITEM)
        self.assertEqual(provider.call_count, (len(items) + capacity - 1) // capacity)
        self.assertEqual([r.relevance_score for r in results], [i / 100 for i in range(60)])
        for call in provider.call_args_list:
            self.assertLessEqual(2000 + call.kwargs["max_output_tokens"], budget.ASSESSMENT_REQUEST_TARGET)
        self.assertLessEqual(2000, budget.ASSESSMENT_PROMPT_TARGET)
        self.assertGreater(2000 + budget.assessment_output_limit(len(items)), budget.ASSESSMENT_REQUEST_TARGET)

    def test_minimum_assessment_must_fit_combined_request_budget(self):
        with patch.object(budget, "ASSESSMENT_REQUEST_TARGET", 100):
            with self.assertRaises(budget.LLMRequestBudgetExceededError):
                budget.pack_assessment_requests(_SYSTEM_INSTRUCTIONS, "Claim", [
                    {"key": "item_0", "evidence_content": "Evidence"},
                ])

    def test_provider_or_parse_failure_only_affects_its_pack_and_blank_positions(self):
        items = [item(0, content=None), item(1, content=12)] + [
            item(i, content=f"Fact {i}. " + "context " * 1500) for i in range(2, 17)]
        calls = 0
        def fail_first(system, user, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("simulated provider outage")
            return self.response(system, user, **kwargs)
        with patch("api.verification.evidence_assessment.call_llm_with_fallback", side_effect=fail_first):
            results = assess_reasoning_evidence_batch_against_claim("Claim", items)
        self.assertEqual(len(results), len(items))
        self.assertTrue(any(result.relevance_score is not None for result in results))
        for result in results[:3]:
            self.assertEqual((result.stance, result.relevance_score, result.directness_score),
                             ("UNKNOWN", None, None))

    def test_output_cap_scales_with_size(self):
        self.assertGreater(budget.assessment_output_limit(10), budget.assessment_output_limit(2))

    def test_output_allowance_has_headroom_over_actual_json_schema(self):
        for count in (1, 5, 17, 30):
            data = [{"key": f"item_{i}", "evidence_content": "Evidence"} for i in range(count)]
            response = self.response("System", budget.assessment_prompt("Claim", data))
            self.assertLess(budget.token_count(response), budget.assessment_output_limit(count))


class GroqExecutionUsageTests(SimpleTestCase):
    def test_successful_usage_is_local_and_resets_between_scopes(self):
        gemini, groq = Mock(), Mock()
        gemini.models.generate_content.side_effect = RuntimeError("simulated fallback")
        groq.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
            usage=SimpleNamespace(prompt_tokens=123, completion_tokens=45, total_tokens=168),
        )
        with patch.object(services, "gemini_client", gemini), patch.object(services, "groq_client", groq):
            with services.llm_provider_scope():
                services.call_llm_with_fallback("System", "User", max_output_tokens=800)
                self.assertEqual(services.recent_groq_tokens(), 168)
                self.assertEqual(services.get_recent_groq_usage()[0]["completion_tokens"], 45)
                self.assertIn("timestamp", services.get_recent_groq_usage()[0])
                self.assertEqual(groq.chat.completions.create.call_args.kwargs["max_completion_tokens"], 800)
            with services.llm_provider_scope():
                self.assertEqual(services.recent_groq_tokens(), 0)
        self.assertEqual(services.recent_groq_tokens(), 0)

    def test_missing_or_unexpected_usage_is_harmless(self):
        with services.llm_provider_scope():
            for response in (None, SimpleNamespace(), SimpleNamespace(usage=None),
                             SimpleNamespace(usage={"total_tokens": "invalid"})):
                services._record_groq_usage(response)
            self.assertEqual(services.recent_groq_tokens(), 0)

    def test_expired_usage_is_not_recent(self):
        with services.llm_provider_scope(), patch("api.services.time.monotonic", return_value=100):
            services._record_groq_usage(SimpleNamespace(usage={"total_tokens": 200}))
            with patch("api.services.time.monotonic", return_value=200):
                self.assertEqual(services.recent_groq_tokens(), 0)

    def test_optional_gemini_output_cap_and_unchanged_default(self):
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(text="{}")
        with patch.object(services, "gemini_client", gemini):
            services.call_llm_with_fallback("System", "User", max_output_tokens=900)
            self.assertEqual(gemini.models.generate_content.call_args.kwargs["config"].max_output_tokens, 900)
            services.call_llm_with_fallback("System", "User")
            self.assertIsNone(gemini.models.generate_content.call_args.kwargs["config"].max_output_tokens)

    def test_default_groq_call_still_omits_completion_cap(self):
        gemini, groq = Mock(), Mock()
        gemini.models.generate_content.side_effect = RuntimeError("simulated fallback")
        groq.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        )
        with patch.object(services, "gemini_client", gemini), patch.object(services, "groq_client", groq):
            services.call_llm_with_fallback("System", "User")
        self.assertNotIn("max_completion_tokens", groq.chat.completions.create.call_args.kwargs)


class BudgetPersistenceTests(TestCase):
    def test_selection_never_changes_persisted_content_links_or_provenance(self):
        claim = Claim.objects.create(context_text="Claim")
        run = VerificationRun.objects.create(claim=claim)
        sources = [EvidenceSource.objects.create(provider="TAVILY", content=
            f"Evidence {i}. " + "Unabridged report. " * 1000) for i in range(17)]
        links = link_evidence_sources_to_run(run, sources, evidence_role="SECONDARY")
        record_retrieval_provenance(links, provider="TAVILY", query="existing query", query_index=0)
        before = list(VerificationEvidence.objects.filter(verification_run=run).order_by("pk").values())
        contents = list(EvidenceSource.objects.order_by("pk").values_list("content", flat=True))
        groups = load_reasoning_evidence_dossier_for_run(run)
        with self.assertNumQueries(0):
            dossier, metrics = budget.bounded_reasoning_dossier(groups, prompt)
        self.assertTrue(dossier)
        self.assertLess(metrics["reasoning_selected"], len(sources))
        self.assertEqual(before, list(VerificationEvidence.objects.filter(verification_run=run).order_by("pk").values()))
        self.assertEqual(contents, list(EvidenceSource.objects.order_by("pk").values_list("content", flat=True)))
        self.assertEqual(link_evidence_sources_to_run(run, sources, evidence_role="SECONDARY"), links)
