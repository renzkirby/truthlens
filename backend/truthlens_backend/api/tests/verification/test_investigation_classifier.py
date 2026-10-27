import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from api.investigation_classifier import (
    classify_investigation_claim, validate_model_suggestion,
    dispatch_classification_task, dispatch_classification_after_text_save,
    _query_classifier,
)
from api.models import (
    AccountabilityEvent, Claim, ClaimInvestigationClassification,
    InvestigationClassificationAssessment, Thread, VerificationAssignment,
)
from api.verification_domain_policy import eligibility_reason, subject_eligibility_enforced


class AutomaticInvestigationClassificationTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Researchers reported that a science experiment achieved reproducible results.",
        )

    def suggestion(self):
        return {
            "decision": "CLASSIFY",
            "primary_subject": "SCIENCE",
            "domains": [{"code": "SCIENCE", "evidence": "science experiment"}],
        }

    def test_no_geography_needed_for_supported_subject(self):
        self.assertEqual(
            validate_model_suggestion(self.claim.context_text, self.suggestion()),
            {"domains": ["SCIENCE"], "primary_subject": "SCIENCE"},
        )

    def test_unquoted_domain_evidence_cannot_authorize_claim(self):
        invalid = self.suggestion()
        invalid["domains"][0]["evidence"] = "vaccination mandates"
        self.assertIsNone(
            validate_model_suggestion(self.claim.context_text, invalid)
        )

    def test_unknown_or_duplicate_subject_abstains(self):
        invalid = self.suggestion()
        invalid["domains"][0]["code"] = "UNKNOWN"
        self.assertIsNone(validate_model_suggestion(self.claim.context_text, invalid))
        invalid = self.suggestion()
        invalid["domains"] *= 2
        self.assertIsNone(validate_model_suggestion(self.claim.context_text, invalid))

    def test_primary_subject_must_be_one_of_selected_domains(self):
        invalid = self.suggestion()
        invalid["primary_subject"] = "HEALTH"
        self.assertIsNone(validate_model_suggestion(self.claim.context_text, invalid))

    def test_authority_gate_rejects_surplus_and_unquoted_json_fields(self):
        valid = self.suggestion()
        for invalid in (
            {**valid, "verdict": "FACT"},
            {**valid, "jurisdiction": "GLOBAL"},
            {"decision": "CLASSIFY", "primary_subject": "SCIENCE", "domains": [
                {**valid["domains"][0], "confidence": 0.99},
            ]},
            {"decision": "ABSTAIN", "primary_subject": None, "domains": [
                {"code": "SCIENCE", "evidence": "science experiment"},
            ]},
            {"decision": "CLASSIFY", "primary_subject": "SCIENCE", "domains": [
                {"code": "SCIENCE", "evidence": "not in claim"},
            ]},
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(validate_model_suggestion(
                    self.claim.context_text, invalid,
                ))

    @patch("api.services.call_llm_with_fallback")
    def test_provider_result_is_strictly_validated_even_without_hierarchy(self, llm):
        # This final boundary applies even if a legacy route bypasses
        # development-only provider-level JSON validation.
        wrong = {**self.suggestion(), "verdict": "FACT"}
        llm.return_value = json.dumps(wrong)
        with self.assertRaisesRegex(ValueError, "INVALID_CLASSIFICATION_RESPONSE"):
            _query_classifier(self.claim.context_text)
        llm.assert_called_once()
        self.assertEqual(llm.call_args.kwargs["operation"], "investigation_classification")

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_enforce_cannot_authorize_loose_structured_payload(self, provider):
        # Even if a future route returns a dict instead of the validated
        # _query_classifier output, no surplus payload becomes authority.
        provider.return_value = {**self.suggestion(), "confidence": 0.99}
        self.assertEqual(classify_investigation_claim(self.claim.pk), "ABSTAINED")
        self.assertFalse(ClaimInvestigationClassification.objects.exists())
        self.assertFalse(AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
        ).exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_shadow_suggestion_never_becomes_partner_claimability(self, provider):
        provider.return_value = self.suggestion()
        self.assertEqual(classify_investigation_claim(self.claim.pk), "SUGGESTED")
        suggestion = InvestigationClassificationAssessment.objects.get(
            claim=self.claim,
        )
        self.assertEqual(suggestion.candidate_domains, ["SCIENCE"])
        self.assertEqual(suggestion.candidate_primary_subject, "SCIENCE")
        self.assertEqual(
            eligibility_reason(classification=None, specializations=["SCIENCE"]),
            "NEEDS_CLASSIFICATION",
        )
        self.assertFalse(
            ClaimInvestigationClassification.objects.filter(claim=self.claim).exists()
        )
        self.assertFalse(AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
        ).exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    @patch("api.investigation_classifier._query_classifier")
    def test_default_off_mode_does_not_call_provider(self, mock_provider):
        self.assertEqual(classify_investigation_claim(self.claim.pk), "DISABLED")
        mock_provider.assert_not_called()
        self.assertFalse(InvestigationClassificationAssessment.objects.exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_shadow_mode_records_only_a_candidate(self, mock_provider):
        mock_provider.return_value = self.suggestion()
        self.assertEqual(classify_investigation_claim(self.claim.pk), "SUGGESTED")
        assessment = InvestigationClassificationAssessment.objects.get(claim=self.claim)
        self.assertEqual(assessment.candidate_domains, ["SCIENCE"])
        self.assertEqual(assessment.candidate_primary_subject, "SCIENCE")
        self.assertEqual(assessment.candidate_jurisdiction, "")
        self.assertFalse(ClaimInvestigationClassification.objects.filter(claim=self.claim).exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_ambiguous_model_reply_abstains(self, mock_provider):
        mock_provider.return_value = {
            "decision": "ABSTAIN",
            "primary_subject": None,
            "domains": [],
        }
        self.assertEqual(classify_investigation_claim(self.claim.pk), "ABSTAINED")
        self.assertFalse(ClaimInvestigationClassification.objects.exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_enforce_mode_creates_system_audited_subject_classification(self, mock_provider):
        mock_provider.return_value = self.suggestion()
        self.assertEqual(classify_investigation_claim(self.claim.pk), "APPLIED")
        classification = ClaimInvestigationClassification.objects.get(claim=self.claim)
        self.assertEqual(classification.source, ClaimInvestigationClassification.Source.AUTOMATIC)
        self.assertEqual(classification.domains, ["SCIENCE"])
        self.assertEqual(classification.primary_subject, "SCIENCE")
        self.assertEqual(classification.jurisdiction, "")
        self.assertIsNone(classification.classified_by)
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
            resource_id=str(self.claim.pk),
        )
        self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.SYSTEM)
        self.assertEqual(event.new_state["primary_subject"], "SCIENCE")
        self.assertEqual(classify_investigation_claim(self.claim.pk), "ALREADY_CLASSIFIED")
        mock_provider.assert_called_once()

    @override_settings(
        INVESTIGATION_CLASSIFICATION_MODE="enforce",
        INVESTIGATION_ROUTING_MODE="off",
    )
    @patch("api.investigation_classifier._query_classifier")
    def test_authoritative_subject_persistence_does_not_enable_partner_routing(
        self, mock_provider,
    ):
        mock_provider.return_value = self.suggestion()

        self.assertEqual(classify_investigation_claim(self.claim.pk), "APPLIED")
        classification = ClaimInvestigationClassification.objects.get(
            claim=self.claim,
        )
        self.assertEqual(classification.domains, ["SCIENCE"])
        self.assertEqual(classification.primary_subject, "SCIENCE")
        self.assertFalse(subject_eligibility_enforced())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_multi_domain_primary_subject_is_explicit_not_sorted(self, mock_provider):
        self.claim.context_text = (
            "Scientists analyzed data from a spacecraft using newly developed "
            "navigation software."
        )
        self.claim.save(update_fields=["context_text", "last_updated"])
        mock_provider.return_value = {
            "decision": "CLASSIFY",
            "primary_subject": "TECHNOLOGY",
            "domains": [
                {"code": "SCIENCE", "evidence": "Scientists analyzed data"},
                {"code": "TECHNOLOGY", "evidence": "navigation software"},
            ],
        }

        self.assertEqual(classify_investigation_claim(self.claim.pk), "APPLIED")
        classification = ClaimInvestigationClassification.objects.get(
            claim=self.claim,
        )
        self.assertEqual(classification.domains, ["SCIENCE", "TECHNOLOGY"])
        self.assertEqual(classification.primary_subject, "TECHNOLOGY")

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_non_text_claim_with_persisted_subject_text_can_be_classified(self, mock_provider):
        mock_provider.return_value = self.suggestion()
        for claim_type in (
            Claim.ClaimType.IMAGE, Claim.ClaimType.URL, Claim.ClaimType.FILE,
        ):
            with self.subTest(claim_type=claim_type):
                claim = Claim.objects.create(
                    claim_type=claim_type,
                    context_text=self.claim.context_text,
                )
                self.assertEqual(classify_investigation_claim(claim.pk), "APPLIED")
                classification = ClaimInvestigationClassification.objects.get(claim=claim)
                self.assertEqual(classification.domains, ["SCIENCE"])
                self.assertEqual(classification.primary_subject, "SCIENCE")
                self.assertEqual(classification.jurisdiction, "")
        self.assertEqual(mock_provider.call_count, 3)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_missing_or_short_extracted_text_abstains_without_llm(self, mock_provider):
        for claim_type, content in (
            (Claim.ClaimType.IMAGE, None),
            (Claim.ClaimType.URL, "Too short"),
            (Claim.ClaimType.FILE, "  "),
        ):
            with self.subTest(claim_type=claim_type):
                claim = Claim.objects.create(
                    claim_type=claim_type, context_text=content,
                )
                self.assertEqual(classify_investigation_claim(claim.pk), "ABSTAINED")
                self.assertFalse(
                    ClaimInvestigationClassification.objects.filter(claim=claim).exists()
                )
        mock_provider.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_unchanged_shadow_assessment_is_idempotent_even_after_mode_switch(self, provider):
        provider.return_value = self.suggestion()
        self.assertEqual(classify_investigation_claim(self.claim.pk), "SUGGESTED")
        with override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce"):
            self.assertEqual(classify_investigation_claim(self.claim.pk), "ALREADY_ASSESSED")
        provider.assert_called_once()
        self.assertFalse(
            ClaimInvestigationClassification.objects.filter(claim=self.claim).exists()
        )

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_late_provider_response_cannot_classify_rewritten_claim(self, provider):
        def rewrite(_text):
            Claim.objects.filter(pk=self.claim.pk).update(
                context_text="This claim was replaced while classification was running."
            )
            return self.suggestion()

        provider.side_effect = rewrite
        self.assertEqual(classify_investigation_claim(self.claim.pk), "STALE_CONTEXT")
        self.assertFalse(ClaimInvestigationClassification.objects.exists())
        self.assertFalse(InvestigationClassificationAssessment.objects.exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_claimed_investigation_cannot_be_classified_after_assignment(self, provider):
        VerificationAssignment.objects.create(
            claim=self.claim,
            status=VerificationAssignment.Status.COMPLETED,
        )
        self.assertEqual(classify_investigation_claim(self.claim.pk), "NO_LONGER_ELIGIBLE")
        provider.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    def test_dispatch_queues_claim_without_community_thread(self, delay):
        self.assertFalse(Thread.objects.filter(claim=self.claim).exists())
        self.assertTrue(dispatch_classification_task(self.claim.pk))
        delay.assert_called_once_with(str(self.claim.pk))

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    def test_existing_thread_is_still_a_valid_fallback_trigger(self, delay):
        author = User.objects.create_user(username="classifier-thread-author")
        Thread.objects.create(
            claim=self.claim,
            author=author,
            caption="Request investigation",
        )
        self.assertTrue(dispatch_classification_task(self.claim.pk))
        delay.assert_called_once_with(str(self.claim.pk))

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    def test_dispatch_broker_failure_does_not_break_community(self, delay):
        author = User.objects.create_user(username="classifier-queue-failure")
        Thread.objects.create(claim=self.claim, author=author)
        delay.side_effect = RuntimeError("broker unavailable")
        self.assertFalse(dispatch_classification_task(self.claim.pk))

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier.dispatch_classification_task")
    def test_post_save_dispatch_runs_only_after_transaction_commit(self, dispatch):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            dispatch_classification_after_text_save(self.claim.pk)
            dispatch.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        dispatch.assert_called_once_with(self.claim.pk)

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    @patch("api.investigation_classifier.dispatch_classification_task")
    def test_off_mode_never_registers_post_save_classification(self, dispatch):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            dispatch_classification_after_text_save(self.claim.pk)
        self.assertEqual(callbacks, [])
        dispatch.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    def test_stable_claim_text_queues_classification_before_verdict(self, delay):
        from api.tasks import _persist_subject_classification_input

        image = Claim.objects.create(
            claim_type=Claim.ClaimType.IMAGE, context_text=None,
        )
        with self.captureOnCommitCallbacks(execute=True):
            persisted = _persist_subject_classification_input(
                image.pk,
                self.claim.context_text,
            )
        self.assertTrue(persisted)
        image.refresh_from_db()
        self.assertEqual(image.context_text, self.claim.context_text)
        self.assertIsNone(image.ai_verdict)
        delay.assert_called_once_with(str(image.pk))

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    def test_off_mode_does_not_early_persist_or_queue_classification(self, delay):
        from api.tasks import _persist_subject_classification_input

        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Original submitted text.",
        )
        persisted = _persist_subject_classification_input(
            claim.pk,
            "Normalized text that should not be written while classification is off.",
        )
        self.assertFalse(persisted)
        claim.refresh_from_db()
        self.assertEqual(claim.context_text, "Original submitted text.")
        delay.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    @patch("api.embedding_service.generate_embedding", return_value=None)
    def test_final_verdict_save_does_not_queue_duplicate_classification(
        self, _embedding, delay,
    ):
        from api.tasks import _persist_subject_classification_input, _save_claim

        claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT, context_text=None,
        )
        with self.captureOnCommitCallbacks(execute=True):
            _persist_subject_classification_input(claim.pk, self.claim.context_text)
        delay.assert_called_once_with(str(claim.pk))
        delay.reset_mock()

        saved = _save_claim(
            claim.pk,
            {"verdict": "UNVERIFIED", "summary": "Needs independent review."},
            "Test source",
            self.claim.context_text,
        )
        self.assertEqual(saved.ai_verdict, "UNVERIFIED")
        delay.assert_not_called()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.tasks.classify_investigation_claim_task.delay")
    @patch("api.tasks.record_authoritative_claim_fact_check_reference")
    @patch("api.tasks.find_exact_canonical_published_fact_check")
    def test_exact_published_resolution_queues_without_thread(
        self, find_match, record_reference, delay,
    ):
        from types import SimpleNamespace
        from api.tasks import _resolve_exact_published_claim

        find_match.return_value = SimpleNamespace(fact_check=object())
        record_reference.return_value = object()
        with self.captureOnCommitCallbacks(execute=True):
            result = _resolve_exact_published_claim(
                self.claim, "A newly saved scientific finding is being examined."
            )
        self.assertTrue(result)
        self.claim.refresh_from_db()
        self.assertEqual(
            self.claim.context_text,
            "A newly saved scientific finding is being examined.",
        )
        delay.assert_called_once_with(str(self.claim.pk))
