from django.core.exceptions import ValidationError
from django.test import TestCase

from api.models import Claim, ClaimInvestigationClassification


class ClaimTaxonomyPersistenceTests(TestCase):
    def _claim(self, label):
        return Claim.objects.create(
            claim_type=Claim.ClaimType.TEXT,
            context_text=f"Persisted taxonomy claim: {label}",
        )

    def test_explicit_primary_subject_may_match_one_required_domain(self):
        classification = ClaimInvestigationClassification(
            claim=self._claim("valid primary"),
            domains=["ELECTIONS", "TECHNOLOGY"],
            primary_subject="ELECTIONS",
            campus_context_state=(
                ClaimInvestigationClassification.CampusContextState.CONFIRMED
            ),
            rationale="Explicit primary and campus context were reviewed.",
        )

        classification.full_clean()

    def test_primary_subject_must_be_one_of_authoritative_domains(self):
        classification = ClaimInvestigationClassification(
            claim=self._claim("invalid primary"),
            domains=["ELECTIONS", "TECHNOLOGY"],
            primary_subject="HEALTH",
            rationale="Primary does not belong to the required domains.",
        )

        with self.assertRaises(ValidationError) as raised:
            classification.full_clean()

        self.assertIn("primary_subject", raised.exception.message_dict)

    def test_blank_optional_context_values_normalize_to_null(self):
        classification = ClaimInvestigationClassification(
            claim=self._claim("blank optional fields"),
            domains=["EDUCATION"],
            primary_subject="",
            campus_context_state="",
            rationale="Blank form values should retain null persistence semantics.",
        )

        classification.full_clean()

        self.assertIsNone(classification.primary_subject)
        self.assertIsNone(classification.campus_context_state)

    def test_legacy_null_persistence_remains_valid(self):
        classification = ClaimInvestigationClassification(
            claim=self._claim("legacy null fields"),
            domains=["EDUCATION"],
            primary_subject=None,
            campus_context_state=None,
            rationale="Legacy classification without new persistence fields.",
        )

        classification.full_clean()

    def test_invalid_domain_vocabulary_is_rejected_on_validation(self):
        classification = ClaimInvestigationClassification(
            claim=self._claim("invalid domain"),
            domains=["UNKNOWN"],
            primary_subject=None,
            rationale="Invalid domain should not pass authoritative validation.",
        )

        with self.assertRaises(ValidationError):
            classification.full_clean()
