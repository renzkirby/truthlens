"""Manual-run regressions for optional context; all provider calls are mocked."""
import json
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from api import tasks
from api.claim_matching import get_match_result
from api.knowledge_reuse_service import (
    build_query_fingerprint, get_related_published_fact_check_payloads,
    get_published_fact_check_resolution_for_claim,
)
from api.models import Claim, ClaimFactCheckReference, EvidenceSubmission, RelatedFactCheckDecision
from api.tests.adjudication.test_adjudication_transaction_contract import AdjudicationContractFixtures
from api.tests.workspace import test_publication_snapshot as publication_fixtures
from api.verification import relatedness as related


class RelatednessClassifierTests(SimpleTestCase):
    claim = "Sara Duterte took a presidential oath in 2026."
    representation = {
        "canonical_claim": "Sara Duterte took the vice-presidential oath in 2022.",
        "headline": "The 2022 inauguration", "summary": "A documented earlier inauguration.",
    }

    def response(self, classification="RELATED", category="CHRONOLOGY"):
        return json.dumps({
            "classification": classification, "connection_category": category,
            "claim_anchor": "Sara Duterte took", "publication_anchor": "Sara Duterte took",
        })

    def test_related_chronology_and_equivalent_contract_are_separate(self):
        self.assertEqual(related.validate_response(self.response(), self.claim, self.representation),
                         ("RELATED", "CHRONOLOGY"))
        self.assertEqual(related.validate_response(self.response("EQUIVALENT", "SAME_PROPOSITION"),
                         self.claim, self.representation), ("EQUIVALENT", "SAME_PROPOSITION"))

    def test_unrelated_earthquake_broad_topic_and_uncertain_require_no_anchors(self):
        for classification in ("UNRELATED", "UNCERTAIN"):
            raw = json.dumps(dict(classification=classification, connection_category="NONE",
                                  claim_anchor="", publication_anchor=""))
            self.assertEqual(related.validate_response(raw, self.claim, {
                "canonical_claim": "A 95 percent earthquake forecast for Calayan is false.",
            }), (classification, "NONE"))
        for phrase in ("Shared keywords", "the same person in unrelated incidents"):
            self.assertIn(phrase, related.SYSTEM)

    def test_malformed_contradictory_and_ungrounded_outputs_are_rejected(self):
        valid = json.loads(self.response())
        for raw in ("not json", "[]", '{"classification":"RELATED","classification":"UNRELATED"}',
                    json.dumps({**valid, "reasoning": "Unrequested"}),
                    self.response("RELATED", "NONE"),
                    json.dumps({**valid, "claim_anchor": "An invented factual connection"}),
                    json.dumps({**valid, "publication_anchor": "Sara"})):
            with self.subTest(raw=raw), self.assertRaises((ValueError, TypeError)):
                related.validate_response(raw, self.claim, self.representation)

    def test_one_gemini_attempt_one_groq_fallback_with_finite_bounds_and_no_secrets(self):
        secret = "PRIVATE-PROVIDER-MESSAGE-SECRET"
        with patch("api.services.gemini_client") as gemini, \
             patch("api.services.groq_client") as groq, \
             self.assertLogs(related.logger, level="INFO") as logs:
            gemini.models.generate_content.side_effect = RuntimeError(secret)
            groq.with_options.return_value.chat.completions.create.side_effect = RuntimeError(secret)
            self.assertEqual(related.classify_relatedness(self.claim, self.representation),
                             (related.UNCERTAIN, "PROVIDERS_UNAVAILABLE"))
        gemini.models.generate_content.assert_called_once()
        groq.with_options.return_value.chat.completions.create.assert_called_once()
        config = gemini.models.generate_content.call_args.kwargs["config"]
        self.assertEqual(config.http_options.retry_options.attempts, 1)
        self.assertEqual(config.http_options.timeout, related.PROVIDER_TIMEOUT_SECONDS * 1000)
        self.assertEqual(config.max_output_tokens, related.OUTPUT_TOKENS)
        groq.with_options.assert_called_once_with(timeout=related.PROVIDER_TIMEOUT_SECONDS, max_retries=0)
        self.assertEqual(groq.with_options.return_value.chat.completions.create.call_args.kwargs[
            "max_completion_tokens"], related.OUTPUT_TOKENS)
        for text in (secret, self.claim, self.representation["canonical_claim"]):
            self.assertNotIn(text, "\n".join(logs.output))

    def test_valid_gemini_response_avoids_groq_and_over_budget_avoids_both(self):
        with patch("api.services.gemini_client") as gemini, patch("api.services.groq_client") as groq:
            gemini.models.generate_content.return_value = SimpleNamespace(
                candidates=[SimpleNamespace(finish_reason="STOP")], text=self.response(),
            )
            self.assertEqual(related.classify_relatedness(self.claim, self.representation)[0],
                             ("RELATED", "CHRONOLOGY"))
            groq.with_options.assert_not_called()
            gemini.reset_mock()
            with patch.object(related, "MAX_PROMPT_TOKENS", 1):
                self.assertEqual(related.classify_relatedness(self.claim, self.representation),
                                 (related.UNCERTAIN, "INPUT_BUDGET"))
            gemini.models.generate_content.assert_not_called()
            groq.with_options.assert_not_called()

    def test_malformed_or_truncated_gemini_uses_only_one_valid_groq_fallback(self):
        for reason, raw in (("MAX_TOKENS", self.response()), ("STOP", "invalid json")):
            with self.subTest(reason=reason), patch("api.services.gemini_client") as gemini, \
                 patch("api.services.groq_client") as groq:
                gemini.models.generate_content.return_value = SimpleNamespace(
                    candidates=[SimpleNamespace(finish_reason=reason)], text=raw,
                )
                groq.with_options.return_value.chat.completions.create.return_value = SimpleNamespace(
                    choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=self.response()))],
                )
                self.assertEqual(related.classify_relatedness(self.claim, self.representation)[0],
                                 ("RELATED", "CHRONOLOGY"))
                gemini.models.generate_content.assert_called_once()
                groq.with_options.return_value.chat.completions.create.assert_called_once()


class RelatednessFixtures(AdjudicationContractFixtures):
    make_submitted_draft = publication_fixtures.PublicationSnapshotTests.make_submitted_draft
    publish_context = publication_fixtures.PublicationSnapshotTests.publish_context

    def setUp(self):
        super().setUp()
        self.enterContext(patch("api.publishing_service._queue_fact_check_index"))
        context = self.make_context(evidence_statuses=[EvidenceSubmission.EvidenceStatus.VERIFIED])
        context["decision"] = self.issue(context, canonical_claim=(
            "Sara Duterte took the vice-presidential oath in 2022."
        ))["decision"]
        context["decision_snapshot"] = context["decision"].evidence_snapshot
        self.publication, _ = self.publish_context(context)
        self.organization.public_profile_enabled = True
        self.organization.save()
        self.proposition = "Sara Duterte took a presidential oath in 2026."
        self.target = Claim.objects.create(
            claim_type="URL", context_text="Article text, not the cleaned proposition.",
            ai_verdict="FAKE", ai_summary="Primary evidence result", ai_sources=["https://primary.example"],
            consensus_score=80,
        )
        self.candidate = {"fact_check_id": str(self.publication.pk),
                          "match_method": "SEMANTIC", "similarity_score": 0.91}

    def schedule(self, claim=None, proposition=None):
        claim = claim or self.target
        with patch("api.tasks.validate_related_fact_check.apply_async") as enqueue, \
             self.captureOnCommitCallbacks(execute=True):
            related.schedule_relatedness(claim.pk, proposition or self.proposition, self.candidate)
        claim.refresh_from_db()
        return claim.relatedness_decision, enqueue


class RelatednessDecisionTests(RelatednessFixtures, TestCase):
    def finish(self, outcome=("RELATED", "CHRONOLOGY"), failure=""):
        decision, enqueue = self.schedule()
        enqueue.assert_called_once_with(args=[str(decision.pk)], retry=False)
        with patch.object(related, "classify_relatedness", return_value=(outcome, failure)) as classify:
            related.process_decision(decision.pk)
        return decision, classify

    def test_related_historical_context_reappears_without_changing_primary_results(self):
        before = get_match_result(self.target)
        decision, classify = self.finish()
        classify.assert_called_once()
        self.target.refresh_from_db()
        after = get_match_result(self.target)
        self.assertEqual(len(after["related_fact_checks"]), 1)
        self.assertEqual({k: v for k, v in after.items() if k != "related_fact_checks"},
                         {k: v for k, v in before.items() if k != "related_fact_checks"})
        self.assertEqual(self.target.relatedness_context["proposition"], self.proposition)
        self.assertIsNone(get_published_fact_check_resolution_for_claim(self.target))
        decision.refresh_from_db()
        self.assertEqual((decision.attempts, decision.state), (1, "COMPLETED"))

    def test_negative_uncertain_equivalent_and_provider_outage_never_create_authority(self):
        for classification, category in (("UNRELATED", "NONE"), ("UNCERTAIN", "NONE"),
                                         ("EQUIVALENT", "SAME_PROPOSITION")):
            with self.subTest(classification=classification):
                decision, _ = self.schedule(proposition=self.proposition + classification)
                with patch.object(related, "classify_relatedness", return_value=((classification, category), "")):
                    related.process_decision(decision.pk)
                self.assertFalse(self.target.fact_check_references.exists())
                self.assertEqual(get_related_published_fact_check_payloads(self.target), [])
                self.assertIsNone(get_published_fact_check_resolution_for_claim(self.target))
        decision, _ = self.schedule()
        with patch.object(related, "classify_relatedness", return_value=(related.UNCERTAIN, "PROVIDERS_UNAVAILABLE")):
            related.process_decision(decision.pk)
        self.target.refresh_from_db()
        self.assertEqual((self.target.ai_verdict, self.target.ai_sources), ("FAKE", ["https://primary.example"]))

    def test_earthquake_and_broad_overlap_classifier_rejection_are_retained(self):
        for text in ("A 95 percent earthquake forecast for Calayan is false.",
                     "Sara Duterte attended an unrelated private event."):
            decision, _ = self.schedule(proposition=text)
            with patch.object(related, "classify_relatedness", return_value=(("UNRELATED", "NONE"), "")) as classify:
                related.process_decision(decision.pk)
                again, enqueue = self.schedule(proposition=text)
                related.process_decision(again.pk)
            classify.assert_called_once()
            enqueue.assert_not_called()
            self.assertEqual(get_related_published_fact_check_payloads(self.target), [])

    def test_reuse_same_pair_across_claims_and_preserve_first_reference_provenance(self):
        decision, _ = self.finish()
        reference = self.target.fact_check_references.get()
        before = ClaimFactCheckReference.objects.values().get(pk=reference.pk)
        self.candidate.update(match_method="FULL_TEXT", similarity_score=None)
        again, enqueue = self.schedule()
        self.assertEqual(again.pk, decision.pk)
        enqueue.assert_not_called()
        self.assertEqual(ClaimFactCheckReference.objects.values().get(pk=reference.pk), before)
        other = Claim.objects.create(claim_type="IMAGE", context_text=self.proposition, ai_verdict="FAKE")
        reused, enqueue = self.schedule(claim=other)
        self.assertEqual(reused.pk, decision.pk)
        self.assertEqual(other.relatedness_context["proposition"], "")
        enqueue.assert_not_called()
        self.assertEqual(RelatedFactCheckDecision.objects.count(), 1)

    def test_pending_interrupted_and_duplicate_delivery_are_hidden_and_one_shot(self):
        decision, _ = self.schedule()
        with patch.object(related, "classify_relatedness", side_effect=RuntimeError("PRIVATE-ERROR")) as classify:
            with self.assertLogs(related.logger, level="WARNING") as logs:
                related.process_decision(decision.pk)
            related.process_decision(decision.pk)
        classify.assert_called_once()
        self.assertNotIn("PRIVATE-ERROR", "\n".join(logs.output))
        decision.refresh_from_db()
        self.assertEqual((decision.state, decision.attempts), ("FAILED", 1))
        self.assertEqual(get_related_published_fact_check_payloads(self.target), [])

    def test_proposition_contract_and_publication_edits_invalidate_display(self):
        decision, _ = self.finish()
        for field, value in (("version", self.publication.version + 1), ("summary", "Changed material summary")):
            original = getattr(self.publication, field)
            type(self.publication).objects.filter(pk=self.publication.pk).update(**{field: value})
            self.assertEqual(get_related_published_fact_check_payloads(self.target), [])
            type(self.publication).objects.filter(pk=self.publication.pk).update(**{field: original})
        with patch.object(related, "CONTRACT_VERSION", "related-context-v2"):
            self.assertEqual(get_related_published_fact_check_payloads(self.target), [])
            new, _ = self.schedule()
            self.assertNotEqual(new.pk, decision.pk)
        changed, _ = self.schedule(proposition=self.proposition.replace("2026", "2027"))
        self.assertNotEqual(changed.pk, decision.pk)
        self.assertEqual(get_related_published_fact_check_payloads(self.target), [])

    def test_historical_reference_hidden_until_validation_and_never_rewritten(self):
        reference = ClaimFactCheckReference.objects.create(
            target_claim=self.target, fact_check=self.publication, relationship_kind="RELATED",
            match_method="FULL_TEXT", query_fingerprint=build_query_fingerprint("Original historical query."),
        )
        before = ClaimFactCheckReference.objects.values().get(pk=reference.pk)
        self.assertEqual(get_related_published_fact_check_payloads(self.target), [])
        self.finish()
        self.assertEqual(len(get_related_published_fact_check_payloads(self.target)), 1)
        self.assertEqual(ClaimFactCheckReference.objects.values().get(pk=reference.pk), before)

    def test_polling_never_enqueues_or_calls_providers_and_store_failure_is_optional(self):
        self.finish()
        with patch.object(related, "classify_relatedness") as classify, \
             patch("api.tasks.validate_related_fact_check.apply_async") as enqueue:
            for _ in range(3):
                self.assertEqual(len(get_match_result(self.target)["related_fact_checks"]), 1)
        classify.assert_not_called()
        enqueue.assert_not_called()
        with patch.object(related, "accepted_reference", side_effect=RuntimeError("PRIVATE-STORE-ERROR")):
            self.assertEqual(get_match_result(self.target)["verdict"], "FAKE")
            self.assertEqual(get_match_result(self.target)["related_fact_checks"], [])

    def test_primary_save_survives_enqueue_failure_and_failed_primary_never_schedules(self):
        with patch("api.embedding_service.generate_embedding", return_value=None), \
             patch("api.tasks.validate_related_fact_check.apply_async", side_effect=RuntimeError("PRIVATE-QUEUE")), \
             self.captureOnCommitCallbacks(execute=True):
            tasks._save_claim(self.target.pk, {"verdict": "FAKE", "confidence_score": 80}, "Fresh",
                              "URL article context", ["https://primary.example"],
                              related_proposition=self.proposition, related_candidate=self.candidate)
        self.target.refresh_from_db()
        self.assertEqual(self.target.ai_verdict, "FAKE")
        self.assertEqual(self.target.relatedness_decision.state, "FAILED")
        with patch.object(related, "schedule_relatedness") as schedule:
            with self.assertRaises(tasks.ClaimPersistenceError):
                tasks._save_claim(self.target.pk, "not a verdict", "Fresh", "Context",
                                  related_proposition=self.proposition, related_candidate=self.candidate)
        schedule.assert_not_called()

    def test_stale_work_and_oversized_proposition_make_no_provider_call(self):
        decision, _ = self.schedule()
        Claim.objects.filter(pk=self.target.pk).update(context_text="New primary context")
        with patch.object(related, "classify_relatedness") as classify:
            related.process_decision(decision.pk)
        classify.assert_not_called()
        count = RelatedFactCheckDecision.objects.count()
        self.schedule(proposition="x" * (related.MAX_CLAIM_CHARS + 1))
        self.assertEqual(RelatedFactCheckDecision.objects.count(), count)

    def test_enqueue_waits_for_commit_and_authoritative_or_missing_candidates_do_not_schedule(self):
        from api.knowledge_reuse_service import record_authoritative_claim_fact_check_reference
        with patch("api.tasks.validate_related_fact_check.apply_async") as enqueue:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                related.schedule_relatedness(self.target.pk, self.proposition, self.candidate)
            enqueue.assert_not_called()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
            enqueue.assert_called_once()
        record_authoritative_claim_fact_check_reference(
            target_claim=self.target, fact_check=self.publication,
            query_text=self.publication.canonical_claim,
        )
        with patch("api.tasks.validate_related_fact_check.apply_async") as enqueue:
            related.schedule_relatedness(self.target.pk, self.proposition, None)
            related.schedule_relatedness(self.target.pk, self.proposition + " Changed.", self.candidate)
        enqueue.assert_not_called()
        self.assertEqual(get_published_fact_check_resolution_for_claim(self.target).fact_check.pk,
                         self.publication.pk)

    def test_new_result_invalidates_binding_and_successor_identity_does_not_inherit(self):
        self.finish()
        with patch("api.embedding_service.generate_embedding", return_value=None):
            tasks._save_claim(self.target.pk, {"verdict": "FAKE", "confidence_score": 80},
                              "Fresh", "A different primary context", ["https://new.example"])
        self.target.refresh_from_db()
        self.assertIsNone(self.target.relatedness_decision_id)
        self.assertEqual(get_related_published_fact_check_payloads(self.target), [])
        self.assertTrue(self.target.fact_check_references.exists())
        fields, _ = related.publication_identity(self.publication)
        identity = related.decision_identity(build_query_fingerprint(self.proposition), fields)
        changed = {**fields, "publication_id": uuid.uuid4()}
        self.assertNotEqual(related.decision_identity(build_query_fingerprint(self.proposition), changed), identity)

    def test_publication_change_during_classification_is_discarded(self):
        decision, _ = self.schedule()

        def changed_publication(*args):
            type(self.publication).objects.filter(pk=self.publication.pk).update(summary="Changed during request")
            return ("RELATED", "CHRONOLOGY"), ""

        with patch.object(related, "classify_relatedness", side_effect=changed_publication):
            related.process_decision(decision.pk)
        decision.refresh_from_db()
        self.assertEqual(decision.state, "FAILED")
        self.assertFalse(self.target.fact_check_references.exists())


class RelatednessConcurrencyTests(RelatednessFixtures, TransactionTestCase):
    def test_simultaneous_binding_and_worker_delivery_are_deduplicated(self):
        # This regression intentionally uses PostgreSQL's real row/unique locks.
        self.assertEqual(connection.vendor, "postgresql")
        other = Claim.objects.create(claim_type="IMAGE", context_text=self.proposition, ai_verdict="FAKE")
        errors = []
        barrier = threading.Barrier(2)

        def bind(claim_id):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                related.schedule_relatedness(claim_id, self.proposition, self.candidate)
            except Exception as exc:
                errors.append(type(exc).__name__)
            finally:
                close_old_connections()

        with patch("api.tasks.validate_related_fact_check.apply_async") as enqueue:
            threads = [threading.Thread(target=bind, args=(pk,)) for pk in (self.target.pk, other.pk)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=20)
                self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(RelatedFactCheckDecision.objects.count(), 1)
        enqueue.assert_called_once()
        decision = RelatedFactCheckDecision.objects.get()
        self.assertEqual(decision.bound_claims.count(), 2)
        def classify_without_transaction(*args):
            self.assertFalse(connection.in_atomic_block)
            return ("RELATED", "CHRONOLOGY"), ""

        with patch.object(related, "classify_relatedness", side_effect=classify_without_transaction) as classify:
            def deliver():
                close_old_connections()
                try:
                    related.process_decision(decision.pk)
                finally:
                    close_old_connections()

            workers = [threading.Thread(target=deliver) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=20)
                self.assertFalse(worker.is_alive())
        classify.assert_called_once()
        self.assertEqual(ClaimFactCheckReference.objects.filter(relationship_kind="RELATED").count(), 2)
