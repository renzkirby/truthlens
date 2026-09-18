import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from api.verification_metrics_service import (
    VerificationMetricsIntegrityError,
    get_organization_verification_baseline,
)


class VerificationMetricsBaselineTests(SimpleTestCase):
    def setUp(self):
        self.organization = SimpleNamespace(pk=uuid.uuid4())
        self.claim_id = str(uuid.uuid4())
        self.claimed_at = datetime(2026, 9, 15, 8, 0, tzinfo=timezone.utc)

    def attempt(self, assignment_id, status="ACTIVE", *, duration=None, claimed_at=None):
        claimed_at = claimed_at if claimed_at is not None else self.claimed_at
        return {
            "assignment_id": assignment_id,
            "claim_id": self.claim_id,
            "organization_id": str(self.organization.pk),
            "status": status,
            "claimed_at": claimed_at,
            "terminal_at": (
                claimed_at + timedelta(seconds=duration) if duration is not None else None
            ),
            "duration_seconds": duration,
        }

    def aggregate(self, attempts):
        # SimpleTestCase forbids database queries, isolating the projection boundary.
        with patch(
            "api.verification_metrics_service.project_organization_assignment_lifecycles",
            return_value=attempts,
        ) as projection:
            baseline = get_organization_verification_baseline(organization=self.organization)
        projection.assert_called_once_with(organization=self.organization)
        return baseline

    def test_empty_organization_returns_exact_zero_and_none_contract(self):
        self.assertEqual(self.aggregate([]), {
            "organization_id": str(self.organization.pk),
            "measurement_basis": {
                "source": "ACCOUNTABILITY_EVENT",
                "coverage": "INSTRUMENTATION_ERA_ONLY",
                "historical_backfill": False,
                "first_observed_claimed_at": None,
                "last_observed_claimed_at": None,
            },
            "attempts": {
                "claimed": 0, "active": 0, "released": 0, "completed": 0, "terminal": 0,
            },
            "reliability": {
                "terminal_completion_rate": None,
                "terminal_release_rate": None,
            },
            "completed_turnaround": {
                "count": 0,
                "average_seconds": None,
                "median_seconds": None,
                "minimum_seconds": None,
                "maximum_seconds": None,
            },
        })

    def test_mixed_attempts_use_terminal_denominator_and_preserve_count_invariant(self):
        baseline = self.aggregate([
            self.attempt("active-1"),
            self.attempt("active-2"),
            self.attempt("released", "RELEASED", duration=10000.0),
            self.attempt("completed-1", "COMPLETED", duration=10.0),
            self.attempt("completed-2", "COMPLETED", duration=20.0),
        ])
        self.assertEqual(baseline["attempts"], {
            "claimed": 5, "active": 2, "released": 1, "completed": 2, "terminal": 3,
        })
        counts = baseline["attempts"]
        self.assertEqual(counts["claimed"],
                         counts["active"] + counts["released"] + counts["completed"])
        rates = baseline["reliability"]
        self.assertEqual(rates["terminal_completion_rate"], 2 / 3)
        self.assertEqual(rates["terminal_release_rate"], 1 / 3)
        self.assertAlmostEqual(sum(rates.values()), 1.0)
        for rate in rates.values():
            self.assertIsInstance(rate, float)
            self.assertGreaterEqual(rate, 0.0)
            self.assertLessEqual(rate, 1.0)
        self.assertEqual(baseline["completed_turnaround"], {
            "count": 2, "average_seconds": 15.0, "median_seconds": 15.0,
            "minimum_seconds": 10.0, "maximum_seconds": 20.0,
        })

    def test_active_only_attempts_have_none_rates_and_no_completed_turnaround(self):
        baseline = self.aggregate([self.attempt("active-1"), self.attempt("active-2")])
        self.assertEqual(baseline["attempts"], {
            "claimed": 2, "active": 2, "released": 0, "completed": 0, "terminal": 0,
        })
        self.assertEqual(baseline["reliability"], {
            "terminal_completion_rate": None, "terminal_release_rate": None,
        })
        self.assertEqual(baseline["completed_turnaround"], {
            "count": 0, "average_seconds": None, "median_seconds": None,
            "minimum_seconds": None, "maximum_seconds": None,
        })

    def test_completed_statistics_cover_odd_and_even_samples_without_rounding(self):
        for durations, expected_average, expected_median in (
            ([1.25, 2.5, 9.75], 4.5, 2.5),
            ([1.25, 2.5, 9.75, 10.25], 5.9375, 6.125),
        ):
            with self.subTest(durations=durations):
                baseline = self.aggregate([
                    self.attempt(str(index), "COMPLETED", duration=duration)
                    for index, duration in enumerate(durations)
                ])
                self.assertEqual(baseline["completed_turnaround"], {
                    "count": len(durations),
                    "average_seconds": expected_average,
                    "median_seconds": expected_median,
                    "minimum_seconds": 1.25,
                    "maximum_seconds": durations[-1],
                })
                for key, value in baseline["completed_turnaround"].items():
                    if key != "count":
                        self.assertIsInstance(value, float)

    def test_released_only_duration_does_not_become_verification_turnaround(self):
        baseline = self.aggregate([self.attempt("released", "RELEASED", duration=900.0)])
        self.assertEqual(baseline["reliability"], {
            "terminal_completion_rate": 0.0, "terminal_release_rate": 1.0,
        })
        self.assertEqual(baseline["completed_turnaround"], {
            "count": 0, "average_seconds": None, "median_seconds": None,
            "minimum_seconds": None, "maximum_seconds": None,
        })

    def test_same_claim_on_distinct_assignment_ids_counts_as_distinct_attempts(self):
        baseline = self.aggregate([
            self.attempt("original", "RELEASED", duration=50.0),
            self.attempt("replacement", "COMPLETED", duration=30.0,
                         claimed_at=self.claimed_at + timedelta(seconds=60)),
        ])
        self.assertEqual(baseline["attempts"], {
            "claimed": 2, "active": 0, "released": 1, "completed": 1, "terminal": 2,
        })
        self.assertEqual(baseline["reliability"], {
            "terminal_completion_rate": 0.5, "terminal_release_rate": 0.5,
        })

    def test_coverage_timestamps_use_minimum_and_maximum_observed_claims(self):
        first = self.claimed_at - timedelta(days=1)
        last = self.claimed_at + timedelta(days=1)
        baseline = self.aggregate([
            self.attempt("last", claimed_at=last),
            self.attempt("first", "COMPLETED", duration=300000.0, claimed_at=first),
            self.attempt("middle"),
        ])
        self.assertEqual(baseline["measurement_basis"], {
            "source": "ACCOUNTABILITY_EVENT",
            "coverage": "INSTRUMENTATION_ERA_ONLY",
            "historical_backfill": False,
            "first_observed_claimed_at": first,
            "last_observed_claimed_at": last,
        })

    def test_zero_second_completion_is_valid_and_included_in_statistics(self):
        for durations, expected in (
            ([0.0], {"count": 1, "average_seconds": 0.0, "median_seconds": 0.0,
                     "minimum_seconds": 0.0, "maximum_seconds": 0.0}),
            ([0.0, 10.0], {"count": 2, "average_seconds": 5.0, "median_seconds": 5.0,
                           "minimum_seconds": 0.0, "maximum_seconds": 10.0}),
        ):
            with self.subTest(durations=durations):
                baseline = self.aggregate([
                    self.attempt(str(index), "COMPLETED", duration=duration)
                    for index, duration in enumerate(durations)
                ])
                self.assertEqual(baseline["completed_turnaround"], expected)
                self.assertEqual(baseline["reliability"], {
                    "terminal_completion_rate": 1.0, "terminal_release_rate": 0.0,
                })

    def test_projection_integrity_error_propagates_unchanged(self):
        error = VerificationMetricsIntegrityError("Contradictory assignment history")
        with patch(
            "api.verification_metrics_service.project_organization_assignment_lifecycles",
            side_effect=error,
        ) as projection:
            with self.assertRaises(VerificationMetricsIntegrityError) as raised:
                get_organization_verification_baseline(organization=self.organization)
        self.assertIs(raised.exception, error)
        projection.assert_called_once_with(organization=self.organization)
