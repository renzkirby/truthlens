"""Deterministic Trust Score sensitivity and adversarial analysis.

This module never reads or writes the database. It mirrors the production
Trust Score mathematics using calibration defaults imported from trust_service,
then lets us vary those calibration values without changing production
behavior.
"""

from dataclasses import dataclass, replace
import math

from .trust_service import (
    BASE_SCORE,
    COMMUNITY_POINTS_CAP,
    COMMUNITY_SIGNAL_SCALE,
    CONTRIBUTION_POINTS_CAP,
    HISTORY_POINTS_CAP,
    MODERATION_PENALTY_CAP,
    PRIOR_FAILURE,
    PRIOR_SUCCESS,
    RANK_REQUIREMENTS,
    REJECTED_THREAD_PENALTY,
)


@dataclass(frozen=True)
class RankRequirement:
    name: str
    min_score: float
    min_actions: int


@dataclass(frozen=True)
class TrustScoreCalibration:
    base_score: float = BASE_SCORE
    contribution_points_cap: float = CONTRIBUTION_POINTS_CAP
    prior_success: float = PRIOR_SUCCESS
    prior_failure: float = PRIOR_FAILURE
    community_points_cap: float = COMMUNITY_POINTS_CAP
    community_signal_scale: float = COMMUNITY_SIGNAL_SCALE
    history_points_cap: float = HISTORY_POINTS_CAP
    rejected_thread_penalty: float = REJECTED_THREAD_PENALTY
    moderation_penalty_cap: float = MODERATION_PENALTY_CAP
    rank_requirements: tuple[RankRequirement, ...] = tuple(
        RankRequirement(
            name=rank["name"],
            min_score=float(rank["min_score"]),
            min_actions=int(rank["min_actions"]),
        )
        for rank in RANK_REQUIREMENTS
    )


DEFAULT_CALIBRATION = TrustScoreCalibration()


@dataclass(frozen=True)
class TrustScenario:
    name: str
    verified_evidence: int = 0
    rejected_evidence: int = 0
    valid_reports: int = 0
    invalid_reports: int = 0
    upvote_trust_scores: tuple[float, ...] = ()
    downvote_trust_scores: tuple[float, ...] = ()
    active_months: int = 0
    rejected_threads: int = 0
    description: str = ""

    @property
    def resolved_actions(self):
        return (
            self.verified_evidence
            + self.rejected_evidence
            + self.valid_reports
            + self.invalid_reports
        )

    @property
    def validated_actions(self):
        return self.verified_evidence + self.valid_reports


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _confidence_level(resolved_actions):
    if resolved_actions < 3:
        return {"key": "PROVISIONAL", "label": "Provisional"}
    if resolved_actions < 10:
        return {"key": "LOW", "label": "Low"}
    if resolved_actions < 25:
        return {"key": "DEVELOPING", "label": "Developing"}
    if resolved_actions < 50:
        return {"key": "ESTABLISHED", "label": "Established"}
    return {"key": "HIGH", "label": "High"}


def _vote_weight(score):
    bounded_score = _clamp(float(score), 0.0, 100.0)
    return 0.5 + (bounded_score / 200.0)


def _progression(score, resolved_actions, calibration):
    requirements = calibration.rank_requirements
    confidence = _confidence_level(resolved_actions)

    if resolved_actions < requirements[0].min_actions:
        next_rank = requirements[0]
        progress_percent = _clamp(
            (resolved_actions / next_rank.min_actions) * 100,
            0.0,
            100.0,
        )
        return {
            "status": "PROVISIONAL",
            "current_rank": "Provisional",
            "next_rank": next_rank.name,
            "score_to_next_rank": 0.0,
            "actions_to_next_rank": max(
                0,
                next_rank.min_actions - resolved_actions,
            ),
            "progress_percent": round(progress_percent, 2),
            "confidence": confidence,
        }

    current_index = 0
    for index, rank in enumerate(requirements):
        if score >= rank.min_score and resolved_actions >= rank.min_actions:
            current_index = index

    current_rank = requirements[current_index]
    if current_index == len(requirements) - 1:
        return {
            "status": "ESTABLISHED",
            "current_rank": current_rank.name,
            "next_rank": None,
            "score_to_next_rank": 0.0,
            "actions_to_next_rank": 0,
            "progress_percent": 100.0,
            "confidence": confidence,
        }

    next_rank = requirements[current_index + 1]
    score_progress = (
        1.0
        if next_rank.min_score <= 0
        else _clamp(score / next_rank.min_score, 0.0, 1.0)
    )
    action_progress = _clamp(
        resolved_actions / next_rank.min_actions,
        0.0,
        1.0,
    )

    return {
        "status": "ESTABLISHED",
        "current_rank": current_rank.name,
        "next_rank": next_rank.name,
        "score_to_next_rank": round(max(0.0, next_rank.min_score - score), 2),
        "actions_to_next_rank": max(
            0,
            next_rank.min_actions - resolved_actions,
        ),
        "progress_percent": round(
            min(score_progress, action_progress) * 100,
            2,
        ),
        "confidence": confidence,
    }


def simulate_trust_score(scenario, calibration=DEFAULT_CALIBRATION):
    resolved_actions = scenario.resolved_actions
    validated_actions = scenario.validated_actions

    smoothed_accuracy = (
        validated_actions + calibration.prior_success
    ) / (
        resolved_actions
        + calibration.prior_success
        + calibration.prior_failure
    )

    quality_signal = (smoothed_accuracy - 0.5) * 2
    contribution_points = _clamp(
        quality_signal * calibration.contribution_points_cap,
        -calibration.contribution_points_cap,
        calibration.contribution_points_cap,
    )

    weighted_vote_signal = sum(
        _vote_weight(score)
        for score in scenario.upvote_trust_scores
    ) - sum(
        _vote_weight(score)
        for score in scenario.downvote_trust_scores
    )

    community_points = (
        math.tanh(
            weighted_vote_signal / calibration.community_signal_scale
        )
        * calibration.community_points_cap
    )

    history_points = min(
        calibration.history_points_cap,
        float(max(0, scenario.active_months)),
    )
    moderation_penalty = min(
        calibration.moderation_penalty_cap,
        max(0, scenario.rejected_threads)
        * calibration.rejected_thread_penalty,
    )

    raw_score = (
        calibration.base_score
        + contribution_points
        + community_points
        + history_points
        - moderation_penalty
    )
    trust_score = _clamp(raw_score, 0.0, 100.0)
    progression = _progression(
        trust_score,
        resolved_actions,
        calibration,
    )

    return {
        "name": scenario.name,
        "description": scenario.description,
        "resolved_actions": resolved_actions,
        "validated_actions": validated_actions,
        "smoothed_accuracy": round(smoothed_accuracy, 4),
        "contribution_points": round(contribution_points, 2),
        "weighted_vote_signal": round(weighted_vote_signal, 2),
        "community_points": round(community_points, 2),
        "history_points": round(history_points, 2),
        "moderation_penalty": round(float(moderation_penalty), 2),
        "raw_score": round(float(raw_score), 2),
        "trust_score": round(float(trust_score), 2),
        "current_rank": progression["current_rank"],
        "next_rank": progression["next_rank"],
        "confidence": progression["confidence"]["label"],
    }


def baseline_scenarios():
    fresh_votes = (50.0,) * 10

    return (
        TrustScenario(
            name="new_user",
            description="No resolved Community reputation evidence.",
        ),
        TrustScenario(
            name="one_verified",
            verified_evidence=1,
            active_months=1,
            description="One professionally verified evidence contribution.",
        ),
        TrustScenario(
            name="one_rejected",
            rejected_evidence=1,
            description="One rejected evidence contribution.",
        ),
        TrustScenario(
            name="consistent_strong",
            verified_evidence=25,
            active_months=5,
            description="Twenty-five successful evidence contributions.",
        ),
        TrustScenario(
            name="high_volume_mediocre",
            verified_evidence=30,
            rejected_evidence=20,
            active_months=5,
            description="Fifty resolved evidence items with 60% success.",
        ),
        TrustScenario(
            name="strong_one_mistake",
            verified_evidence=49,
            rejected_evidence=1,
            active_months=5,
            description="Strong long history with one rejected contribution.",
        ),
        TrustScenario(
            name="strong_with_safety_removal",
            verified_evidence=50,
            active_months=5,
            rejected_threads=1,
            description="Strong history plus one confirmed removed thread.",
        ),
        TrustScenario(
            name="valid_reports_only",
            valid_reports=25,
            active_months=5,
            description="Twenty-five valid Safety reports and no evidence.",
        ),
        TrustScenario(
            name="invalid_reports_only",
            invalid_reports=25,
            description="Twenty-five dismissed Safety reports.",
        ),
        TrustScenario(
            name="good_evidence_no_votes",
            verified_evidence=25,
            active_months=5,
            description="Strong evidence record with no Community votes.",
        ),
        TrustScenario(
            name="mediocre_no_votes",
            verified_evidence=18,
            rejected_evidence=7,
            active_months=5,
            description="Seventy-two percent resolved success, no votes.",
        ),
        TrustScenario(
            name="mediocre_plus_fresh_vote_cluster",
            verified_evidence=18,
            rejected_evidence=7,
            upvote_trust_scores=fresh_votes,
            active_months=5,
            description="Same record plus ten upvotes from fresh 50-score accounts.",
        ),
        TrustScenario(
            name="strong_plus_fresh_downvote_cluster",
            verified_evidence=25,
            downvote_trust_scores=fresh_votes,
            active_months=5,
            description="Strong record plus ten fresh-account downvotes.",
        ),
        TrustScenario(
            name="early_failures",
            rejected_evidence=5,
            description="Five early rejected evidence contributions.",
        ),
        TrustScenario(
            name="recovered_after_early_failures",
            verified_evidence=20,
            rejected_evidence=5,
            active_months=5,
            description="Five early failures followed by twenty successes.",
        ),
        TrustScenario(
            name="three_failed_actions",
            invalid_reports=3,
            description="Three resolved failures and no successful action.",
        ),
    )


def invariant_results(calibration=DEFAULT_CALIBRATION):
    scenarios = {
        scenario.name: simulate_trust_score(scenario, calibration)
        for scenario in baseline_scenarios()
    }

    positive_reception = simulate_trust_score(
        TrustScenario(
            name="positive_reception_probe",
            verified_evidence=10,
            upvote_trust_scores=(50.0,) * 5,
            active_months=2,
        ),
        calibration,
    )
    neutral_reception = simulate_trust_score(
        TrustScenario(
            name="neutral_reception_probe",
            verified_evidence=10,
            active_months=2,
        ),
        calibration,
    )
    negative_reception = simulate_trust_score(
        TrustScenario(
            name="negative_reception_probe",
            verified_evidence=10,
            downvote_trust_scores=(50.0,) * 5,
            active_months=2,
        ),
        calibration,
    )

    old_vote_weight = simulate_trust_score(
        TrustScenario(
            name="historical_vote_at_50",
            verified_evidence=10,
            upvote_trust_scores=(50.0,) * 5,
            active_months=2,
        ),
        calibration,
    )
    reinterpreted_vote_weight = simulate_trust_score(
        TrustScenario(
            name="same_votes_after_voters_reach_90",
            verified_evidence=10,
            upvote_trust_scores=(90.0,) * 5,
            active_months=2,
        ),
        calibration,
    )

    expert_depth_probe = _progression(
        95.0,
        25,
        calibration,
    )

    checks = (
        {
            "id": "I1",
            "name": "Neutral cold start",
            "passed": scenarios["new_user"]["trust_score"]
            == calibration.base_score,
            "detail": (
                "A user with no resolved evidence starts at the neutral "
                f"{calibration.base_score:.0f} baseline."
            ),
        },
        {
            "id": "I2",
            "name": "Small-sample restraint",
            "passed": (
                scenarios["one_verified"]["trust_score"] <= 60.0
                and scenarios["one_rejected"]["trust_score"] >= 40.0
            ),
            "detail": (
                "One success/failure must not create an extreme score. "
                "History points are included when the success has a resolved month."
            ),
        },
        {
            "id": "I3",
            "name": "Quality dominance",
            "passed": (
                calibration.contribution_points_cap
                > calibration.community_points_cap
            ),
            "detail": (
                "The maximum Contribution Quality effect is larger than the "
                "maximum Community Reception effect."
            ),
        },
        {
            "id": "I4",
            "name": "Community signal remains meaningful",
            "passed": (
                positive_reception["trust_score"]
                > neutral_reception["trust_score"]
                > negative_reception["trust_score"]
            ),
            "detail": (
                "Eligible positive reception raises reputation and negative "
                "reception lowers it."
            ),
        },
        {
            "id": "I5",
            "name": "Confirmed bad behavior matters",
            "passed": (
                scenarios["strong_with_safety_removal"]["trust_score"]
                < simulate_trust_score(
                    TrustScenario(
                        name="strong_without_safety_removal",
                        verified_evidence=50,
                        active_months=5,
                    ),
                    calibration,
                )["trust_score"]
            ),
            "detail": "A confirmed removed thread lowers an otherwise equal score.",
        },
        {
            "id": "I6",
            "name": "Recovery remains possible",
            "passed": (
                scenarios["recovered_after_early_failures"]["trust_score"]
                > scenarios["early_failures"]["trust_score"]
                and scenarios["recovered_after_early_failures"]["trust_score"]
                > calibration.base_score
            ),
            "detail": (
                "Sustained successful behavior can recover from an early poor record."
            ),
        },
        {
            "id": "I7",
            "name": "High rank requires evidence depth",
            "passed": (
                expert_depth_probe["current_rank"] != "Expert Contributor"
            ),
            "detail": (
                "Even a 95 score at 25 actions does not satisfy the 50-action "
                "Expert Contributor gate."
            ),
        },
        {
            "id": "I8",
            "name": "Fresh-account vote cluster cannot change a high-level rank",
            "passed": (
                scenarios["mediocre_no_votes"]["current_rank"]
                == scenarios["mediocre_plus_fresh_vote_cluster"]["current_rank"]
            ),
            "detail": (
                "Ten fresh 50-score upvotes are treated as a Sybil/collusion "
                "stress probe. A rank change is a failed invariant."
            ),
        },
        {
            "id": "I9",
            "name": "Historical vote interpretation is reproducible",
            "passed": (
                old_vote_weight["trust_score"]
                == reinterpreted_vote_weight["trust_score"]
            ),
            "detail": (
                "The same historical votes are re-evaluated at voter Trust 50 "
                "and 90. The current dynamic weighting policy changes the result."
            ),
        },
    )

    return {
        "checks": checks,
        "scenarios": scenarios,
        "probes": {
            "positive_reception": positive_reception,
            "neutral_reception": neutral_reception,
            "negative_reception": negative_reception,
            "historical_vote_at_50": old_vote_weight,
            "same_votes_after_voters_reach_90": reinterpreted_vote_weight,
        },
        "non_numeric_invariant": {
            "id": "I10",
            "name": "Authority separation",
            "status": "ARCHITECTURAL",
            "detail": (
                "Community reputation must not grant Partner Organization "
                "verification authority. This is enforced outside the score math."
            ),
        },
    }


def attack_results(calibration=DEFAULT_CALIBRATION):
    voter_scores = (0.0, 25.0, 50.0, 75.0, 100.0)

    promotion_base = TrustScenario(
        name="promotion_base",
        verified_evidence=18,
        rejected_evidence=7,
        active_months=5,
    )
    demotion_base = TrustScenario(
        name="demotion_base",
        verified_evidence=25,
        active_months=5,
    )

    promotion_baseline = simulate_trust_score(
        promotion_base,
        calibration,
    )
    demotion_baseline = simulate_trust_score(
        demotion_base,
        calibration,
    )

    promotion_thresholds = []
    demotion_thresholds = []

    for voter_score in voter_scores:
        promotion = None
        demotion = None

        for count in range(1, 51):
            promoted = simulate_trust_score(
                replace(
                    promotion_base,
                    name=f"promotion_{voter_score}_{count}",
                    upvote_trust_scores=(voter_score,) * count,
                ),
                calibration,
            )
            if (
                promoted["current_rank"]
                != promotion_baseline["current_rank"]
            ):
                promotion = {
                    "voter_trust_score": voter_score,
                    "minimum_votes": count,
                    "from_rank": promotion_baseline["current_rank"],
                    "to_rank": promoted["current_rank"],
                    "score": promoted["trust_score"],
                }
                break

        for count in range(1, 51):
            demoted = simulate_trust_score(
                replace(
                    demotion_base,
                    name=f"demotion_{voter_score}_{count}",
                    downvote_trust_scores=(voter_score,) * count,
                ),
                calibration,
            )
            if (
                demoted["current_rank"]
                != demotion_baseline["current_rank"]
            ):
                demotion = {
                    "voter_trust_score": voter_score,
                    "minimum_votes": count,
                    "from_rank": demotion_baseline["current_rank"],
                    "to_rank": demoted["current_rank"],
                    "score": demoted["trust_score"],
                }
                break

        promotion_thresholds.append(promotion)
        demotion_thresholds.append(demotion)

    return {
        "promotion_probe": {
            "baseline": promotion_baseline,
            "thresholds": promotion_thresholds,
        },
        "demotion_probe": {
            "baseline": demotion_baseline,
            "thresholds": demotion_thresholds,
        },
    }


def diagnostic_results(calibration=DEFAULT_CALIBRATION):
    failed_only = simulate_trust_score(
        TrustScenario(
            name="three_failed_actions",
            invalid_reports=3,
        ),
        calibration,
    )
    evidence_only = simulate_trust_score(
        TrustScenario(
            name="verified_evidence_only",
            verified_evidence=25,
            active_months=5,
        ),
        calibration,
    )
    reports_only = simulate_trust_score(
        TrustScenario(
            name="valid_reports_only",
            valid_reports=25,
            active_months=5,
        ),
        calibration,
    )

    return {
        "failed_actions_leave_provisional": {
            "scenario": failed_only,
            "finding": (
                "Three resolved failures currently satisfy the action-volume "
                "gate for New Contributor."
            ),
        },
        "evidence_report_equivalence": {
            "evidence": evidence_only,
            "reports": reports_only,
            "finding": (
                "Twenty-five verified evidence actions and twenty-five valid "
                "Safety reports currently produce identical quality/history "
                "results when other inputs are equal."
            ),
        },
        "positive_component_ceiling": {
            "nominal_score": (
                calibration.base_score
                + calibration.contribution_points_cap
                + calibration.community_points_cap
                + calibration.history_points_cap
            ),
            "finding": (
                "The nominal positive-component ceiling is below 100 and the "
                "Bayesian/tanh components approach their caps asymptotically."
            ),
        },
        "temporal_order": {
            "status": "NOT_MODELED",
            "finding": (
                "The current formula aggregates lifetime resolved outcomes; "
                "two histories with identical counts but different recency "
                "produce the same quality result."
            ),
        },
    }


SENSITIVITY_VARIANTS = (
    ("prior_1_1", {"prior_success": 1.0, "prior_failure": 1.0}),
    ("prior_2_2", {"prior_success": 2.0, "prior_failure": 2.0}),
    ("prior_3_3", {"prior_success": 3.0, "prior_failure": 3.0}),
    ("contribution_cap_20", {"contribution_points_cap": 20.0}),
    ("contribution_cap_25", {"contribution_points_cap": 25.0}),
    ("contribution_cap_30", {"contribution_points_cap": 30.0}),
    ("community_cap_10", {"community_points_cap": 10.0}),
    ("community_cap_15", {"community_points_cap": 15.0}),
    ("community_cap_20", {"community_points_cap": 20.0}),
    ("community_scale_5", {"community_signal_scale": 5.0}),
    ("community_scale_8", {"community_signal_scale": 8.0}),
    ("community_scale_12", {"community_signal_scale": 12.0}),
    ("history_cap_3", {"history_points_cap": 3.0}),
    ("history_cap_5", {"history_points_cap": 5.0}),
    ("history_cap_10", {"history_points_cap": 10.0}),
    ("thread_penalty_3", {"rejected_thread_penalty": 3.0}),
    ("thread_penalty_5", {"rejected_thread_penalty": 5.0}),
    ("thread_penalty_8", {"rejected_thread_penalty": 8.0}),
)


def sensitivity_results(calibration=DEFAULT_CALIBRATION):
    probes = (
        TrustScenario(
            name="one_verified",
            verified_evidence=1,
            active_months=1,
        ),
        TrustScenario(
            name="mediocre_plus_fresh_vote_cluster",
            verified_evidence=18,
            rejected_evidence=7,
            upvote_trust_scores=(50.0,) * 10,
            active_months=5,
        ),
        TrustScenario(
            name="strong_with_safety_removal",
            verified_evidence=50,
            active_months=5,
            rejected_threads=1,
        ),
        TrustScenario(
            name="recovered_after_early_failures",
            verified_evidence=20,
            rejected_evidence=5,
            active_months=5,
        ),
    )

    rows = []
    for label, changes in SENSITIVITY_VARIANTS:
        variant = replace(calibration, **changes)
        rows.append(
            {
                "variant": label,
                "changes": changes,
                "results": {
                    probe.name: simulate_trust_score(probe, variant)
                    for probe in probes
                },
            }
        )
    return rows


def build_validation_report(calibration=DEFAULT_CALIBRATION):
    baseline = [
        simulate_trust_score(scenario, calibration)
        for scenario in baseline_scenarios()
    ]
    invariants = invariant_results(calibration)

    return {
        "calibration": {
            "base_score": calibration.base_score,
            "contribution_points_cap": calibration.contribution_points_cap,
            "prior_success": calibration.prior_success,
            "prior_failure": calibration.prior_failure,
            "community_points_cap": calibration.community_points_cap,
            "community_signal_scale": calibration.community_signal_scale,
            "history_points_cap": calibration.history_points_cap,
            "rejected_thread_penalty": calibration.rejected_thread_penalty,
            "moderation_penalty_cap": calibration.moderation_penalty_cap,
            "rank_requirements": [
                {
                    "name": rank.name,
                    "min_score": rank.min_score,
                    "min_actions": rank.min_actions,
                }
                for rank in calibration.rank_requirements
            ],
        },
        "baseline_scenarios": baseline,
        "invariants": invariants,
        "attacks": attack_results(calibration),
        "diagnostics": diagnostic_results(calibration),
        "sensitivity": sensitivity_results(calibration),
    }
