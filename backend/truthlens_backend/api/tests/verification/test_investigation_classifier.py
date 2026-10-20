from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from api.investigation_classifier import (
    classify_investigation_claim, validate_model_suggestion,
    dispatch_classification_task, dispatch_classification_after_text_save,
)
from api.models import (
    AccountabilityEvent, Claim, ClaimInvestigationClassification,
    InvestigationClassificationAssessment, Thread, VerificationAssignment,
)


class AutomaticInvestigationClassificationTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text="Researchers reported that a science experiment achieved reproducible results.",
        )

    def suggestion(self):
        return {
            "decision": "CLASSIFY",
            "domains": [{"code": "SCIENCE", "evidence": "science experiment"}],
        }

    def test_no_geography_needed_for_supported_subject(self):
        self.assertEqual(
            validate_model_suggestion(self.claim.context_text, self.suggestion()),
            ["SCIENCE"],
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
        self.assertEqual(assessment.candidate_jurisdiction, "")
        self.assertFalse(ClaimInvestigationClassification.objects.filter(claim=self.claim).exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_ambiguous_model_reply_abstains(self, mock_provider):
        mock_provider.return_value = {"decision": "ABSTAIN", "domains": []}
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
        self.assertEqual(classification.jurisdiction, "")
        self.assertIsNone(classification.classified_by)
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
            resource_id=str(self.claim.pk),
        )
        self.assertEqual(event.authority_scope, AccountabilityEvent.AuthorityScope.SYSTEM)
        self.assertEqual(classify_investigation_claim(self.claim.pk), "ALREADY_CLASSIFIED")
        mock_provider.assert_called_once()

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
    def test_dispatch_only_queues_community_claims(self, delay):
        self.assertFalse(dispatch_classification_task(self.claim.pk))
        delay.assert_not_called()
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
    @patch("api.embedding_service.generate_embedding", return_value=None)
    def test_factual_claim_persistence_queues_late_text_without_modifying_verdict(
        self, _embedding, delay,
    ):
        from api.tasks import _save_claim

        author = User.objects.create_user(username="classifier-late-text")
        image = Claim.objects.create(
            claim_type=Claim.ClaimType.IMAGE, context_text=None,
        )
        Thread.objects.create(claim=image, author=author)
        with self.captureOnCommitCallbacks(execute=True):
            saved = _save_claim(
                image.pk,
                {"verdict": "UNVERIFIED", "summary": "Needs independent review."},
                "Test source",
                self.claim.context_text,
            )
        self.assertEqual(saved.ai_verdict, "UNVERIFIED")
        self.assertEqual(saved.context_text, self.claim.context_text)
        self.assertFalse(
            ClaimInvestigationClassification.objects.filter(claim=image).exists()
        )
        delay.assert_called_once_with(str(image.pk))
