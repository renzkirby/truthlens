"""No-network integration acceptance for investigation-classification shadow mode.

Exercise the real shared Gemini -> Cloudflare -> Groq router, persisted
claim input, Celery task entry point, and authority separation together.
All provider clients are mocks. No real provider calls or partner grants.
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from api.investigation_classifier import classify_investigation_claim
from api.models import (
    AccountabilityEvent, Claim, ClaimInvestigationClassification,
    InvestigationClassificationAssessment,
)
from api.tasks import classify_investigation_claim_task
from api.verification.cloudflare_evaluation import CloudflareEvaluationError
from api.verification_domain_policy import eligibility_reason


CLAIM_TEXT = (
    "Researchers reported that a science experiment achieved "
    "reproducible results."
)
SCIENCE_RESULT = json.dumps({
    "decision": "CLASSIFY",
    "domains": [{"code": "SCIENCE", "evidence": "science experiment"}],
})
ABSTAIN_RESULT = '{"decision":"ABSTAIN","domains":[]}'
INVALID_DUPLICATE = json.dumps({
    "decision": "CLASSIFY",
    "domains": [
        {"code": "SCIENCE", "evidence": "science experiment"},
        {"code": "SCIENCE", "evidence": "science experiment"},
    ],
})


@override_settings(
    APP_ENV="development", DEBUG=True,
    INVESTIGATION_CLASSIFICATION_MODE="shadow",
)
class InvestigationClassificationShadowIntegrationTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "1",
            "ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "1",
            "CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS": "4096",
            "CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC": "45",
        }))
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT, context_text=CLAIM_TEXT,
        )
        self.original_verdict = self.claim.ai_verdict
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(
            text=SCIENCE_RESULT,
        )
        self.gemini = self.enterContext(patch(
            "api.services.gemini_client", gemini,
        ))
        self.cloudflare = self.enterContext(patch(
            "api.services.call_validated_cloudflare_pilot",
            return_value=SCIENCE_RESULT,
        ))
        groq = Mock()
        groq.with_options.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=SCIENCE_RESULT),
                )],
            )
        )
        self.groq = self.enterContext(patch("api.services.groq_client", groq))
        self.groq_request = (
            groq.with_options.return_value.chat.completions.create
        )

    def _run(self):
        # Use Celery's underlying task function; no broker or worker needed.
        return classify_investigation_claim_task.run(str(self.claim.pk))

    def _assert_not_authoritative(self):
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.ai_verdict, self.original_verdict)
        self.assertFalse(ClaimInvestigationClassification.objects.filter(
            claim=self.claim,
        ).exists())
        self.assertEqual(eligibility_reason(
            classification=ClaimInvestigationClassification.objects.filter(
                claim=self.claim,
            ).first(),
            specializations=["SCIENCE", "LAW"],
        ), "NEEDS_CLASSIFICATION")
        self.assertFalse(AccountabilityEvent.objects.filter(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
            resource_id=str(self.claim.pk),
        ).exists())

    def test_valid_gemini_task_stores_shadow_suggestion_only(self):
        self.assertEqual(self._run(), "SUGGESTED")
        a = InvestigationClassificationAssessment.objects.get(claim=self.claim)
        self.assertEqual(a.candidate_domains, ["SCIENCE"])
        self.assertEqual(a.reason_code, "")
        self.gemini.models.generate_content.assert_called_once()
        self.cloudflare.assert_not_called()
        self.groq_request.assert_not_called()
        self._assert_not_authoritative()

    def test_gemini_unavailable_cloudflare_suggestion_stays_non_authoritative(self):
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "synthetic Gemini billing unavailable"
        )
        self.assertEqual(self._run(), "SUGGESTED")
        self.gemini.models.generate_content.assert_called_once()
        self.cloudflare.assert_called_once()
        self.assertEqual(
            self.cloudflare.call_args.kwargs["operation"],
            "investigation_classification",
        )
        self.groq_request.assert_not_called()
        self.assertEqual(
            InvestigationClassificationAssessment.objects.get(
                claim=self.claim,
            ).candidate_domains, ["SCIENCE"],
        )
        self._assert_not_authoritative()

    def test_invalid_gemini_cloudflare_failure_groq_suggestion_remains_shadow(self):
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=INVALID_DUPLICATE,
        )
        self.cloudflare.side_effect = CloudflareEvaluationError(
            "INVALID_CLASSIFICATION_JSON",
        )
        self.assertEqual(self._run(), "SUGGESTED")
        self.gemini.models.generate_content.assert_called_once()
        self.cloudflare.assert_called_once()
        self.groq.with_options.assert_called_once_with(max_retries=0)
        self.groq_request.assert_called_once()
        self._assert_not_authoritative()

    def test_valid_model_abstention_is_distinct_from_provider_failure(self):
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=ABSTAIN_RESULT,
        )
        self.assertEqual(self._run(), "ABSTAINED")
        a = InvestigationClassificationAssessment.objects.get(claim=self.claim)
        self.assertEqual(a.reason_code, "MODEL_ABSTAINED")
        self.assertEqual(a.candidate_domains, [])
        self.cloudflare.assert_not_called()
        self.groq_request.assert_not_called()
        self._assert_not_authoritative()

    def test_invalid_groq_final_output_is_a_failed_shadow_assessment(self):
        self.gemini.models.generate_content.side_effect = RuntimeError(
            "synthetic Gemini outage"
        )
        self.cloudflare.side_effect = CloudflareEvaluationError(
            "INVALID_CLASSIFICATION_JSON",
        )
        self.groq_request.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=INVALID_DUPLICATE),
            )],
        )
        self.assertEqual(self._run(), "FAILED")
        assessment = InvestigationClassificationAssessment.objects.get(
            claim=self.claim,
        )
        self.assertEqual(assessment.reason_code, "PROVIDER_UNAVAILABLE")
        self.assertEqual(assessment.candidate_domains, [])
        self.groq_request.assert_called_once()
        self._assert_not_authoritative()

    def test_invalid_legacy_boundary_is_failure_not_valid_abstain(self):
        # When provider-stage validation is disabled, the independent
        # classifier boundary must still reject duplicate/loose JSON.
        with patch.dict(os.environ, {
            "ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0",
            "ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT": "0",
        }):
            self.gemini.models.generate_content.return_value = (
                SimpleNamespace(text=INVALID_DUPLICATE)
            )
            self.groq_request.return_value = SimpleNamespace(
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=INVALID_DUPLICATE),
                )],
            )
            self.assertEqual(self._run(), "FAILED")
        a = InvestigationClassificationAssessment.objects.get(claim=self.claim)
        self.assertEqual(a.reason_code, "INVALID_CLASSIFICATION_RESPONSE")
        self._assert_not_authoritative()

    def test_valid_but_extra_subject_is_only_shadow_candidate(self):
        # The JSON contract does not prove subject accuracy. It is allowed
        # as a suggestion, but must never grant/deny partner eligibility.
        self.claim.context_text = (
            "Researchers reported that a science experiment was discussed "
            "during a court hearing about laboratory funding."
        )
        self.claim.save(update_fields=["context_text"])
        self.gemini.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps({
                "decision": "CLASSIFY",
                "domains": [
                    {"code": "SCIENCE", "evidence": "science experiment"},
                    {"code": "LAW", "evidence": "court hearing"},
                ],
            }),
        )
        self.assertEqual(self._run(), "SUGGESTED")
        self.assertEqual(
            InvestigationClassificationAssessment.objects.get(
                claim=self.claim,
            ).candidate_domains,
            ["LAW", "SCIENCE"],
        )
        self._assert_not_authoritative()

    def test_idempotent_second_task_call_does_not_consume_another_provider_call(self):
        self.assertEqual(self._run(), "SUGGESTED")
        self.assertEqual(self._run(), "ALREADY_ASSESSED")
        self.gemini.models.generate_content.assert_called_once()
        self.cloudflare.assert_not_called()
        self.groq_request.assert_not_called()
        self._assert_not_authoritative()

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    def test_off_mode_does_not_call_any_provider_or_write_assessment(self):
        self.assertEqual(self._run(), "DISABLED")
        self.assertFalse(
            InvestigationClassificationAssessment.objects.filter(
                claim=self.claim,
            ).exists()
        )
        self.gemini.models.generate_content.assert_not_called()
        self.cloudflare.assert_not_called()
        self.groq_request.assert_not_called()
        self._assert_not_authoritative()
