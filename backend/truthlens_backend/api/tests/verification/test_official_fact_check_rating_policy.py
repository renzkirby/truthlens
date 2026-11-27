from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api import tasks
from api.models import VerificationEvidence
from api.services import (
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


def _coverage(*records):
    rows = []
    for index, (reviewed_claim, relationship) in enumerate(records):
        rows.append({
            "candidate_index": index,
            "relationship": relationship,
            "reasoning": "Deterministic test relationship.",
            "material_differences": (
                [] if relationship == "EQUIVALENT_OR_COVERS"
                else ["Material difference."]
            ),
            "reviewed_claim": reviewed_claim,
        })
    covered = sum(
        row["relationship"] == "EQUIVALENT_OR_COVERS"
        for row in rows
    )
    relevant = sum(
        row["relationship"] in {
            "EQUIVALENT_OR_COVERS",
            "PARTIAL_OR_RELATED",
        }
        for row in rows
    )
    return {
        "candidate_count": len(rows),
        "relevant_candidate_count": relevant,
        "covered_candidate_count": covered,
        "terminally_sufficient": covered > 0,
        "reason_code": (
            "EXACT_OR_EQUIVALENT_COVERAGE"
            if covered
            else "RELATED_BUT_INCOMPLETE"
        ),
        "candidates": rows,
    }


class OfficialFactCheckRatingPolicyTests(SimpleTestCase):
    def test_evaluator_wrapper_preserves_legacy_none_call_shape(self):
        policy = {
            "resolution": OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
            "satire_evidence_ids": (),
            "misleading_evidence_ids": (),
            "false_evidence_ids": (),
        }
        with patch(
            "api.tasks.evaluate_claim_with_persisted_evidence",
            return_value={"verdict": "UNVERIFIED"},
        ) as evaluator:
            tasks._evaluate_persisted_with_official_rating_policy(
                "Claim.",
                "Persisted evidence.",
                "NEUTRAL",
                policy,
                evidence_groups=["group"],
            )

        evaluator.assert_called_once_with(
            "Claim.",
            "Persisted evidence.",
            "NEUTRAL",
            evidence_groups=["group"],
        )

    def test_evaluator_wrapper_forwards_false_only_metadata_additively(self):
        policy = {
            "resolution": OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
            "satire_evidence_ids": (),
            "misleading_evidence_ids": (),
            "false_evidence_ids": ("false-1",),
        }
        with patch(
            "api.tasks.evaluate_claim_with_persisted_evidence",
            return_value={"verdict": "FAKE"},
        ) as evaluator:
            tasks._evaluate_persisted_with_official_rating_policy(
                "Claim.",
                "Persisted evidence.",
                "NEUTRAL",
                policy,
                evidence_groups=["group"],
            )

        evaluator.assert_called_once_with(
            "Claim.",
            "Persisted evidence.",
            "NEUTRAL",
            official_false_evidence_ids=("false-1",),
            evidence_groups=["group"],
        )

    def test_evaluator_wrapper_preserves_legacy_misleading_call_shape(self):
        policy = {
            "resolution": OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
            "satire_evidence_ids": (),
            "misleading_evidence_ids": ("misleading-1",),
            "false_evidence_ids": (),
        }
        with patch(
            "api.tasks.evaluate_claim_with_persisted_evidence",
            return_value={"verdict": "MISLEADING"},
        ) as evaluator:
            tasks._evaluate_persisted_with_official_rating_policy(
                "Claim.",
                "Persisted evidence.",
                "NEUTRAL",
                policy,
                evidence_groups=["group"],
            )

        evaluator.assert_called_once_with(
            "Claim.",
            "Persisted evidence.",
            "NEUTRAL",
            OFFICIAL_FACT_CHECK_RESOLUTION_NONE,
            (),
            ("misleading-1",),
            evidence_groups=["group"],
        )

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

        for rating in ("Misleading", "MISLEADING", " misleading "):
            with self.subTest(rating=rating):
                self.assertEqual(
                    classify_official_fact_check_rating(rating),
                    "MISLEADING",
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
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(("Same claim.", "False")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())
        self.assertEqual(result["misleading_evidence_ids"], ())
        self.assertEqual(result["false_evidence_ids"], ("evidence-1",))

    def test_exact_misleading_rating_becomes_context_signal_without_coverage(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(("Same claim.", "Misleading")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())
        self.assertEqual(result["misleading_evidence_ids"], ("evidence-1",))

    def test_exact_equivalent_satire_rating_authorizes_satire_without_coverage(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(("Same claim.", "Satire")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE)
        self.assertEqual(result["satire_evidence_ids"], ("evidence-1",))

    def test_multiple_observed_satire_labels_still_resolve_to_satire(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(
                ("Same claim.", "Originated as Satire"),
                ("Same claim.", "Parody News"),
                ("Same claim.", "Satirist"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE)
        self.assertEqual(
            result["satire_evidence_ids"],
            ("evidence-1", "evidence-2", "evidence-3"),
        )

    def test_equivalent_satire_and_false_ratings_resolve_to_fake_conflict(self):
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
        self.assertEqual(result["false_evidence_ids"], ("evidence-2",))

    def test_equivalent_unknown_rating_defers_to_normal_evaluator(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(
                ("Same claim.", "Satire"),
                ("Same claim.", "Mostly False"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())

    def test_related_non_equivalent_satire_does_not_authorize_satire(self):
        reviewed = "Related parody post."
        result = tasks._resolve_official_fact_check_rating_policy(
            "Submitted factual claim.",
            _groups((reviewed, "Satire")),
            coverage=_coverage((reviewed, "PARTIAL_OR_RELATED")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())

    def test_semantic_coverage_can_authorize_satire_without_second_match_call(self):
        reviewed = "The railway agreement was signed by Mayor X."
        result = tasks._resolve_official_fact_check_rating_policy(
            "Mayor X signed the railway agreement.",
            _groups((reviewed, "Satire")),
            coverage=_coverage((reviewed, "EQUIVALENT_OR_COVERS")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE)

    def test_semantic_coverage_preserves_equivalent_false_signal_without_shortcut(self):
        reviewed = "The athlete met the head of state after the tournament final."
        result = tasks._resolve_official_fact_check_rating_policy(
            "The athlete met with the head of state after the tournament final.",
            _groups((reviewed, "False")),
            coverage=_coverage((reviewed, "EQUIVALENT_OR_COVERS")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())
        self.assertEqual(result["misleading_evidence_ids"], ())
        self.assertEqual(result["false_evidence_ids"], ("evidence-1",))
        self.assertFalse(tasks._official_rating_policy_has_signal(result))

    def test_semantic_coverage_can_activate_misleading_context_signal(self):
        reviewed = (
            "Erwin Tulfo said stop meddling with flood-control projects; "
            "posts falsely framed the clip as calling to end the probe."
        )
        result = tasks._resolve_official_fact_check_rating_policy(
            (
                "In a viral July 2026 clip, Senator Erwin Tulfo called for "
                "the flood-control corruption investigation to be stopped."
            ),
            _groups((reviewed, "Misleading")),
            coverage=_coverage((reviewed, "EQUIVALENT_OR_COVERS")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())
        self.assertEqual(result["misleading_evidence_ids"], ("evidence-1",))

    def test_partial_or_related_misleading_rating_does_not_activate_signal(self):
        reviewed = (
            "Erwin Tulfo discussed politicians meddling with flood-control projects."
        )
        result = tasks._resolve_official_fact_check_rating_policy(
            (
                "In a viral July 2026 clip, Senator Erwin Tulfo called for "
                "the flood-control corruption investigation to be stopped."
            ),
            _groups((reviewed, "Misleading")),
            coverage=_coverage((reviewed, "PARTIAL_OR_RELATED")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["misleading_evidence_ids"], ())

    def test_undetermined_semantic_match_fails_closed(self):
        reviewed = "Potentially equivalent claim."
        result = tasks._resolve_official_fact_check_rating_policy(
            "Submitted factual claim.",
            _groups((reviewed, "Misleading")),
            coverage=_coverage((reviewed, "UNDETERMINED")),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["misleading_evidence_ids"], ())

    def test_non_equivalent_unknown_rating_does_not_block_equivalent_satire(self):
        satire_claim = "Equivalent satire wording."
        other_claim = "Different contextual claim."
        result = tasks._resolve_official_fact_check_rating_policy(
            "Submitted factual claim.",
            _groups(
                (satire_claim, "Satire"),
                (other_claim, "Mostly False"),
            ),
            coverage=_coverage(
                (satire_claim, "EQUIVALENT_OR_COVERS"),
                (other_claim, "DIFFERENT"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE)
        self.assertEqual(result["satire_evidence_ids"], ("evidence-1",))

    def test_equivalent_misleading_and_false_ratings_preserve_both_signals(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(
                ("Same claim.", "Misleading"),
                ("Same claim.", "False"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["misleading_evidence_ids"], ("evidence-1",))
        self.assertEqual(result["false_evidence_ids"], ("evidence-2",))

    def test_equivalent_misleading_and_unknown_ratings_disable_context_signal(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(
                ("Same claim.", "Misleading"),
                ("Same claim.", "Mostly False"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["misleading_evidence_ids"], ())

    def test_equivalent_misleading_and_satire_ratings_disable_both_signals(self):
        result = tasks._resolve_official_fact_check_rating_policy(
            "Same claim.",
            _groups(
                ("Same claim.", "Misleading"),
                ("Same claim.", "Satire"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_NONE)
        self.assertEqual(result["satire_evidence_ids"], ())
        self.assertEqual(result["misleading_evidence_ids"], ())

    def test_non_equivalent_false_rating_does_not_block_equivalent_satire(self):
        satire_claim = "Equivalent satire wording."
        false_claim = "Different false claim."
        result = tasks._resolve_official_fact_check_rating_policy(
            "Submitted factual claim.",
            _groups(
                (satire_claim, "Satire"),
                (false_claim, "False"),
            ),
            coverage=_coverage(
                (satire_claim, "EQUIVALENT_OR_COVERS"),
                (false_claim, "DIFFERENT"),
            ),
        )

        self.assertEqual(result["resolution"], OFFICIAL_FACT_CHECK_RESOLUTION_SATIRE)
        self.assertEqual(result["satire_evidence_ids"], ("evidence-1",))
