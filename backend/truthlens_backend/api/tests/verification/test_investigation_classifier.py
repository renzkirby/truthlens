from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from api.investigation_classifier import (
    classify_investigation_claim, validate_model_suggestion,
)
from api.models import (
    AccountabilityEvent, Claim,
    ClaimInvestigationClassification, InvestigationClassificationAssessment,
)


class AutomaticInvestigationClassificationTests(TestCase):
    def setUp(self):
        self.claim = Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=(
                "Researchers in the Philippines reported that a science "
                "experiment achieved reproducible results."
            ),
        )

    def suggestion(self):
        return {
            "decision": "CLASSIFY",
            "domains": [
                {"code": "SCIENCE", "evidence": "science experiment"},
            ],
            "jurisdiction": "PH",
            "jurisdiction_evidence": "Philippines",
        }

    def test_unverifiable_geographic_scope_must_abstain(self):
        invalid = self.suggestion()
        invalid["jurisdiction"] = "US"
        self.assertIsNone(
            validate_model_suggestion(self.claim.context_text, invalid)
        )
        invalid["jurisdiction"] = "PH"
        invalid["jurisdiction_evidence"] = "United States"
        self.assertIsNone(
            validate_model_suggestion(self.claim.context_text, invalid)
        )

    def test_unquoted_domain_evidence_cannot_authorize_claim(self):
        invalid = self.suggestion()
        invalid["domains"][0]["evidence"] = "vaccination mandates"
        self.assertIsNone(
            validate_model_suggestion(self.claim.context_text, invalid)
        )

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="off")
    @patch("api.investigation_classifier._query_classifier")
    def test_default_off_mode_does_not_call_provider(self, mock_provider):
        self.assertEqual(
            classify_investigation_claim(self.claim.pk), "DISABLED"
        )
        mock_provider.assert_not_called()
        self.assertFalse(InvestigationClassificationAssessment.objects.exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_shadow_mode_records_only_a_candidate(self, mock_provider):
        mock_provider.return_value = self.suggestion()
        self.assertEqual(
            classify_investigation_claim(self.claim.pk), "SUGGESTED"
        )
        assessment = InvestigationClassificationAssessment.objects.get(
            claim=self.claim
        )
        self.assertEqual(assessment.candidate_domains, ["SCIENCE"])
        self.assertEqual(assessment.candidate_jurisdiction, "PH")
        self.assertFalse(
            ClaimInvestigationClassification.objects.filter(claim=self.claim).exists()
        )

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="shadow")
    @patch("api.investigation_classifier._query_classifier")
    def test_ambiguous_model_reply_abstains(self, mock_provider):
        mock_provider.return_value = {"decision": "ABSTAIN", "domains": []}
        self.assertEqual(
            classify_investigation_claim(self.claim.pk), "ABSTAINED"
        )
        self.assertFalse(ClaimInvestigationClassification.objects.exists())

    @override_settings(INVESTIGATION_CLASSIFICATION_MODE="enforce")
    @patch("api.investigation_classifier._query_classifier")
    def test_enforce_mode_creates_distinct_audited_classification(self, mock_provider):
        mock_provider.return_value = self.suggestion()
        self.assertEqual(
            classify_investigation_claim(self.claim.pk), "APPLIED"
        )
        classification = ClaimInvestigationClassification.objects.get(
            claim=self.claim
        )
        self.assertEqual(
            classification.source, ClaimInvestigationClassification.Source.AUTOMATIC
        )
        self.assertEqual(classification.domains, ["SCIENCE"])
        self.assertIsNone(classification.classified_by)
        event = AccountabilityEvent.objects.get(
            action_type=AccountabilityEvent.ActionType.CLAIM_INVESTIGATION_CLASSIFIED,
            resource_id=str(self.claim.pk),
        )
        self.assertEqual(
            event.authority_scope, AccountabilityEvent.AuthorityScope.SYSTEM
        )
        self.assertEqual(classify_investigation_claim(self.claim.pk), "ALREADY_CLASSIFIED")
        mock_provider.assert_called_once()
