from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import tasks
from api.models import VerificationEvidence
from api.services import (
    LLMProviderUnavailableError,
    OFFICIAL_FACT_CHECK_RESOLUTION_FAKE_CONFLICT,
    OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
    OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
    classify_official_fact_check_rating,
    extract_persisted_fact_check_claim_rating,
)


def _groups(*records):
    items = []
    for index, (claim_text, rating) in enumerate(records, start=1):
        items.append(SimpleNamespace(
            provider=tasks.GFC_PROVIDER_NAME,
            source_type="FACT_CHECK",
            evidence_role=VerificationEvidence.EvidenceRole.FACT_CHECK,
            evidence_link_id=f"evidence-{index}",
            content=(
                f"Claim reviewed: {claim_text} "
                f"Rating: {rating} "
                "Review title: Example review "
                "Publisher: Example Fact Checker"
            ),
        ))
    return [SimpleNamespace(evidence=tuple(items))]


class OfficialFactCheckRatingPolicyTests(SimpleTestCase):
    def test_rating_normalization_is_high_precision(self):
        for rating in (
            "Satire",
            "SATIRICAL",
            "Satirical Post",
            "Parody",
            "Satire / Parody",
            "Originated as Satire",
            "Labeled Satire",
            "Satirist",
            "Parody News",
            "This is a satirical post. It was first shared by a satirist.",
            "This is a satiricalpost. It was first shared by a satirist.",
        ):
            with self.subTest(rating=rating):
                self.assertEqual(
                    classify_official_fact_check_rating(rating),
                    "SATIRE",
                )

        for rating in ("False", "FAKE", "Fabricated"):
            with self.subTest(rating=rating):
                self.assertEqual(
                    classify_official_fact_check_rating(rating),
                    "FALSE",
                )

        for rating in (
            "False - originated as satire",
            "Mostly false",
            "Possibly satirical",
            "Not Satire",
            "Misleading use of satire",
            "Missing context",
            "Unproven",
        ):
            with self.subTest(rating=rating):
                self.assertIsNone(
                    classify_official_fact_check_rating(rating)
                )

    def test_flattened_persisted_gfc_content_extracts_claim_and_rating(self):
        content = (
            'Claim reviewed: In October 2026, the town of Mexico, New York, '
            'announced it would change its name to "Epstein List". '
            'Rating: Labeled Satire '
            "Review title: Did Mexico, NY, change its name? "
            "Publisher: Snopes.com"
        )

        parsed = extract_persisted_fact_check_claim_rating(content)

        self.assertEqual(
            parsed["claim_text"],
            (
                'In October 2026, the town of Mexico, New York, '
                'announced it would change its name to "Epstein List".'
            ),
        )
        self.assertEqual(parsed["rating"], "Labeled Satire")
        self.assertEqual(parsed["rating_kind"], "SATIRE")

    def test_multiline_persisted_gfc_content_remains_supported(self):
        parsed = extract_persisted_fact_check_claim_rating(
            "Claim reviewed: Same claim.\n"
            "Rating: Originated as Satire\n"
            "Review title: Example review\n"
            "Publisher: Snopes"
        )

        self.assertEqual(parsed["claim_text"], "Same claim.")
        self.assertEqual(parsed["rating"], "Originated as Satire")
        self.assertEqual(parsed["rating_kind"], "SATIRE")

    def test_live_observed_full_fact_descriptive_rating_is_high_precision_satire(self):
        parsed = extract_persisted_fact_check_claim_rating(
            "Claim reviewed: A post about Donald Trump's Nobel efforts was "
            "written by a committee member. "
            "Rating: This is a satirical post. It was first shared on X by "
            "an account that describes themselves as a satirist and regularly "
            "creates similar content from fictional insiders. "
            "Review title: Post from Nobel Committee member is satire "
            "Publisher: Full Fact"
        )

        self.assertEqual(parsed["rating_kind"], "SATIRE")

    def test_false_only_does_not_activate_special_resolution(self):
        with patch("api.tasks.assess_claim_equivalence") as equivalence:
            result = tasks._resolve_official_fact_check_rating_policy(
                "Same claim.",
                _groups(("Same claim.", "False")),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
        )
        self.assertEqual(result["satire_evidence_ids"], ())
        equivalence.assert_not_called()

    def test_exact_equivalent_satire_rating_authorizes_satire_without_llm_call(self):
        with patch("api.tasks.assess_claim_equivalence") as equivalence:
            result = tasks._resolve_official_fact_check_rating_policy(
                "Same claim.",
                _groups(("Same claim.", "Satire")),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
        )
        self.assertEqual(result["satire_evidence_ids"], ("evidence-1",))
        equivalence.assert_not_called()

    def test_observed_satire_labels_authorize_satire_consensus(self):
        for rating in (
            "Originated as Satire",
            "Labeled Satire",
            "Satirist",
            "Parody News",
        ):
            with self.subTest(rating=rating):
                with patch("api.tasks.assess_claim_equivalence") as equivalence:
                    result = tasks._resolve_official_fact_check_rating_policy(
                        "Same claim.",
                        _groups(("Same claim.", rating)),
                    )

                self.assertEqual(
                    result["resolution"],
                    OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
                )
                equivalence.assert_not_called()

    def test_multiple_observed_satire_labels_still_resolve_to_satire(self):
        with patch("api.tasks.assess_claim_equivalence") as equivalence:
            result = tasks._resolve_official_fact_check_rating_policy(
                "Same claim.",
                _groups(
                    ("Same claim.", "Originated as Satire"),
                    ("Same claim.", "Parody News"),
                    ("Same claim.", "Satirist"),
                ),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
        )
        self.assertEqual(
            result["satire_evidence_ids"],
            ("evidence-1", "evidence-2", "evidence-3"),
        )
        equivalence.assert_not_called()

    def test_equivalent_satire_and_false_ratings_resolve_to_fake_conflict(self):
        with patch("api.tasks.assess_claim_equivalence") as equivalence:
            result = tasks._resolve_official_fact_check_rating_policy(
                "Same claim.",
                _groups(
                    ("Same claim.", "Satire"),
                    ("Same claim.", "False"),
                ),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_FAKE_CONFLICT,
        )
        self.assertEqual(result["satire_evidence_ids"], ("evidence-1",))
        equivalence.assert_not_called()

    def test_equivalent_unknown_rating_blocks_satire_consensus(self):
        with patch("api.tasks.assess_claim_equivalence") as equivalence:
            result = tasks._resolve_official_fact_check_rating_policy(
                "Same claim.",
                _groups(
                    ("Same claim.", "Satire"),
                    ("Same claim.", "Mostly False"),
                ),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
        )
        self.assertEqual(result["satire_evidence_ids"], ())
        equivalence.assert_not_called()

    def test_related_non_equivalent_satire_does_not_authorize_satire(self):
        with patch(
            "api.tasks.assess_claim_equivalence",
            return_value={
                "equivalent": False,
                "reasoning": "Materially different proposition.",
                "material_differences": ["Different action."],
            },
        ) as equivalence:
            result = tasks._resolve_official_fact_check_rating_policy(
                "Submitted factual claim.",
                _groups(("Related parody post.", "Satire")),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
        )
        self.assertEqual(result["satire_evidence_ids"], ())
        equivalence.assert_called_once()

    def test_semantically_equivalent_satire_rating_authorizes_satire(self):
        with patch(
            "api.tasks.assess_claim_equivalence",
            return_value={
                "equivalent": True,
                "reasoning": "Same complete proposition.",
                "material_differences": [],
            },
        ):
            result = tasks._resolve_official_fact_check_rating_policy(
                "Mayor X signed the railway agreement.",
                _groups(("The railway agreement was signed by Mayor X.", "Satire")),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
        )

    def test_unresolved_equivalence_fails_closed_without_blocking_verification(self):
        with patch(
            "api.tasks.assess_claim_equivalence",
            side_effect=LLMProviderUnavailableError("provider unavailable"),
        ):
            result = tasks._resolve_official_fact_check_rating_policy(
                "Submitted factual claim.",
                _groups(("Potentially equivalent claim.", "Satire")),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
        )
        self.assertEqual(result["satire_evidence_ids"], ())

    def test_non_equivalent_false_rating_does_not_block_equivalent_satire(self):
        def equivalence(incoming_claim, reviewed_claim):
            if reviewed_claim == "Equivalent satire wording.":
                return {
                    "equivalent": True,
                    "reasoning": "Same proposition.",
                    "material_differences": [],
                }
            return {
                "equivalent": False,
                "reasoning": "Different proposition.",
                "material_differences": ["Different event."],
            }

        with patch(
            "api.tasks.assess_claim_equivalence",
            side_effect=equivalence,
        ):
            result = tasks._resolve_official_fact_check_rating_policy(
                "Submitted factual claim.",
                _groups(
                    ("Equivalent satire wording.", "Satire"),
                    ("Different false claim.", "False"),
                ),
            )

        self.assertEqual(
            result["resolution"],
            OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE,
        )
