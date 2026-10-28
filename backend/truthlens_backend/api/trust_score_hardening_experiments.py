"""Compare candidate Trust Score hardening policies without changing production.

The experiments intentionally keep the production Trust Score formula as the
control. They vary only targeted policy choices identified by the literature
and calibration audit:

1. historical vote weighting source;
2. how much reputation history a voter needs before their vote can affect
   somebody else's Community reputation;
3. whether leaving Provisional requires at least one successful resolved action.
"""

from dataclasses import dataclass
import math

from .trust_score_validation import (
    DEFAULT_CALIBRATION,
    TrustScenario,
    simulate_trust_score,
)


@dataclass(frozen=True)
class VoterObservation:
    name: str
    snapshot_score: float
    current_score: float
    snapshot_resolved_actions: int
    current_resolved_actions: int
    validated_actions: int


@dataclass(frozen=True)
class VotePolicy:
    key: str
    label: str
    use_snapshot: bool
    evidence_share_scaling: bool = False
    contributor_gate: bool = False


BASELINE_DYNAMIC = VotePolicy(
    key="baseline_dynamic",
    label="Current dynamic voter Trust",
    use_snapshot=False,
)

SNAPSHOT_ONLY = VotePolicy(
    key="snapshot_only",
    label="Immutable vote-time Trust snapshot",
    use_snapshot=True,
)

SNAPSHOT_EVIDENCE_SHARE = VotePolicy(
    key="snapshot_evidence_share",
    label="Snapshot Trust × observed-evidence share",
    use_snapshot=True,
    evidence_share_scaling=True,
)

SNAPSHOT_CONTRIBUTOR_GATE = VotePolicy(
    key="snapshot_contributor_gate",
    label="Snapshot Trust, Contributor gate",
    use_snapshot=True,
    contributor_gate=True,
)

VOTE_POLICIES = (
    BASELINE_DYNAMIC,
    SNAPSHOT_ONLY,
    SNAPSHOT_EVIDENCE_SHARE,
    SNAPSHOT_CONTRIBUTOR_GATE,
)


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def base_vote_weight(score):
    bounded = _clamp(float(score), 0.0, 100.0)
    return 0.5 + (bounded / 200.0)


def observed_evidence_share(
    resolved_actions,
    calibration=DEFAULT_CALIBRATION,
):
    """Return how much posterior evidence comes from observed actions.

    TruthLens currently uses a Beta(2,2) prior. The prior contributes four
    pseudo-observations. With n resolved actions, n / (n + 4) is the share of
    posterior observation mass supplied by real resolved history.

    This is a transparent shrinkage factor, not a Bayesian credible interval.
    """

    observed = max(0, int(resolved_actions))
    prior_mass = (
        calibration.prior_success
        + calibration.prior_failure
    )
    denominator = observed + prior_mass
    if denominator <= 0:
        return 0.0
    return observed / denominator


def effective_vote_weight(
    voter,
    policy,
    calibration=DEFAULT_CALIBRATION,
):
    score = (
        voter.snapshot_score
        if policy.use_snapshot
        else voter.current_score
    )

    history_actions = (
        voter.snapshot_resolved_actions
        if policy.use_snapshot
        else voter.current_resolved_actions
    )

    if policy.contributor_gate:
        if history_actions < 10 or score < 55.0:
            return 0.0

    weight = base_vote_weight(score)

    if policy.evidence_share_scaling:
        weight *= observed_evidence_share(
            history_actions,
            calibration,
        )

    return weight


def community_points_from_voters(
    *,
    upvoters=(),
    downvoters=(),
    policy=BASELINE_DYNAMIC,
    calibration=DEFAULT_CALIBRATION,
):
    signal = sum(
        effective_vote_weight(voter, policy, calibration)
        for voter in upvoters
    ) - sum(
        effective_vote_weight(voter, policy, calibration)
        for voter in downvoters
    )

    points = (
        math.tanh(
            signal / calibration.community_signal_scale
        )
        * calibration.community_points_cap
    )
    return {
        "weighted_vote_signal": round(signal, 4),
        "community_points": round(points, 4),
    }


def voter_archetypes():
    """Representative histories used for attack/legitimate-influence probes."""

    return (
        VoterObservation(
            name="fresh",
            snapshot_score=50.0,
            current_score=50.0,
            snapshot_resolved_actions=0,
            current_resolved_actions=0,
            validated_actions=0,
        ),
        VoterObservation(
            name="three_successes",
            snapshot_score=61.71,
            current_score=61.71,
            snapshot_resolved_actions=3,
            current_resolved_actions=3,
            validated_actions=3,
        ),
        VoterObservation(
            name="three_failures",
            snapshot_score=39.29,
            current_score=39.29,
            snapshot_resolved_actions=3,
            current_resolved_actions=3,
            validated_actions=0,
        ),
        VoterObservation(
            name="ten_successes",
            snapshot_score=72.86,
            current_score=72.86,
            snapshot_resolved_actions=10,
            current_resolved_actions=10,
            validated_actions=10,
        ),
        VoterObservation(
            name="twenty_five_successes",
            snapshot_score=76.55,
            current_score=76.55,
            snapshot_resolved_actions=25,
            current_resolved_actions=25,
            validated_actions=25,
        ),
    )


def _score_with_reception(base_scenario, community_points, calibration):
    baseline = simulate_trust_score(
        base_scenario,
        calibration,
    )
    score = _clamp(
        baseline["trust_score"] + community_points,
        0.0,
        100.0,
    )
    return score


def _rank_for_score(score, resolved_actions, calibration):
    current = "Provisional"
    if resolved_actions < calibration.rank_requirements[0].min_actions:
        return current

    for rank in calibration.rank_requirements:
        if (
            score >= rank.min_score
            and resolved_actions >= rank.min_actions
        ):
            current = rank.name
    return current


def minimum_rank_change_votes(
    *,
    voter,
    policy,
    direction,
    base_scenario,
    calibration=DEFAULT_CALIBRATION,
    maximum_votes=100,
):
    baseline = simulate_trust_score(
        base_scenario,
        calibration,
    )
    baseline_rank = baseline["current_rank"]

    for count in range(1, maximum_votes + 1):
        voters = (voter,) * count
        reception = community_points_from_voters(
            upvoters=voters if direction == "up" else (),
            downvoters=voters if direction == "down" else (),
            policy=policy,
            calibration=calibration,
        )
        score = _score_with_reception(
            base_scenario,
            reception["community_points"],
            calibration,
        )
        rank = _rank_for_score(
            score,
            base_scenario.resolved_actions,
            calibration,
        )
        if rank != baseline_rank:
            return {
                "minimum_votes": count,
                "result_score": round(score, 2),
                "from_rank": baseline_rank,
                "to_rank": rank,
                "community_points": round(
                    reception["community_points"],
                    2,
                ),
            }

    return {
        "minimum_votes": None,
        "result_score": baseline["trust_score"],
        "from_rank": baseline_rank,
        "to_rank": baseline_rank,
        "community_points": 0.0,
    }


def vote_policy_comparison(calibration=DEFAULT_CALIBRATION):
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

    rows = []
    for policy in VOTE_POLICIES:
        archetype_rows = []
        for voter in voter_archetypes():
            promotion = minimum_rank_change_votes(
                voter=voter,
                policy=policy,
                direction="up",
                base_scenario=promotion_base,
                calibration=calibration,
            )
            demotion = minimum_rank_change_votes(
                voter=voter,
                policy=policy,
                direction="down",
                base_scenario=demotion_base,
                calibration=calibration,
            )
            archetype_rows.append(
                {
                    "voter": voter.name,
                    "effective_weight": round(
                        effective_vote_weight(
                            voter,
                            policy,
                            calibration,
                        ),
                        4,
                    ),
                    "promotion": promotion,
                    "demotion": demotion,
                }
            )

        rows.append(
            {
                "policy": policy.key,
                "label": policy.label,
                "archetypes": archetype_rows,
            }
        )

    return {
        "promotion_baseline": simulate_trust_score(
            promotion_base,
            calibration,
        ),
        "demotion_baseline": simulate_trust_score(
            demotion_base,
            calibration,
        ),
        "policies": rows,
    }


def historical_vote_stability(calibration=DEFAULT_CALIBRATION):
    historical_voter = VoterObservation(
        name="historical_voter",
        snapshot_score=50.0,
        current_score=90.0,
        snapshot_resolved_actions=3,
        current_resolved_actions=25,
        validated_actions=8,
    )

    rows = []
    for policy in VOTE_POLICIES:
        at_vote_time = community_points_from_voters(
            upvoters=(
                VoterObservation(
                    name="historical_voter_at_vote_time",
                    snapshot_score=50.0,
                    current_score=50.0,
                    snapshot_resolved_actions=3,
                    current_resolved_actions=3,
                    validated_actions=8,
                ),
            ) * 5,
            policy=policy,
            calibration=calibration,
        )
        after_reputation_change = community_points_from_voters(
            upvoters=(historical_voter,) * 5,
            policy=policy,
            calibration=calibration,
        )
        rows.append(
            {
                "policy": policy.key,
                "before_points": round(
                    at_vote_time["community_points"],
                    4,
                ),
                "after_points": round(
                    after_reputation_change["community_points"],
                    4,
                ),
                "stable": (
                    at_vote_time["community_points"]
                    == after_reputation_change["community_points"]
                ),
            }
        )
    return rows


def provisional_policy_comparison(calibration=DEFAULT_CALIBRATION):
    scenarios = (
        TrustScenario(
            name="three_failures",
            invalid_reports=3,
        ),
        TrustScenario(
            name="one_success_two_failures",
            valid_reports=1,
            invalid_reports=2,
            active_months=1,
        ),
        TrustScenario(
            name="three_successes",
            valid_reports=3,
            active_months=1,
        ),
    )

    rows = []
    for scenario in scenarios:
        result = simulate_trust_score(
            scenario,
            calibration,
        )
        current_rank = result["current_rank"]

        positive_evidence_rank = current_rank
        if (
            scenario.resolved_actions >= 3
            and scenario.validated_actions < 1
        ):
            positive_evidence_rank = "Provisional"

        rows.append(
            {
                "scenario": scenario.name,
                "score": result["trust_score"],
                "resolved_actions": scenario.resolved_actions,
                "validated_actions": scenario.validated_actions,
                "current_rank": current_rank,
                "positive_evidence_gate_rank": positive_evidence_rank,
            }
        )

    return rows


def legitimate_influence_comparison(calibration=DEFAULT_CALIBRATION):
    """Measure how much candidate policies attenuate established-user feedback."""

    voters = {
        voter.name: voter
        for voter in voter_archetypes()
    }

    rows = []
    for policy in VOTE_POLICIES:
        for voter_name in (
            "three_successes",
            "ten_successes",
            "twenty_five_successes",
        ):
            voter = voters[voter_name]
            reception = community_points_from_voters(
                upvoters=(voter,) * 5,
                policy=policy,
                calibration=calibration,
            )
            rows.append(
                {
                    "policy": policy.key,
                    "voter": voter_name,
                    "effective_weight": round(
                        effective_vote_weight(
                            voter,
                            policy,
                            calibration,
                        ),
                        4,
                    ),
                    "five_upvote_points": round(
                        reception["community_points"],
                        2,
                    ),
                }
            )

    return rows


def build_hardening_experiment_report(calibration=DEFAULT_CALIBRATION):
    return {
        "vote_policy_comparison": vote_policy_comparison(calibration),
        "historical_vote_stability": historical_vote_stability(calibration),
        "provisional_policy_comparison": provisional_policy_comparison(
            calibration
        ),
        "legitimate_influence_comparison": legitimate_influence_comparison(
            calibration
        ),
        "candidate_notes": {
            "snapshot_only": (
                "Fixes historical reinterpretation but does not reduce fresh "
                "account influence."
            ),
            "snapshot_evidence_share": (
                "Freezes historical score and scales influence by n/(n+4), "
                "where four is the current Beta(2,2) prior mass."
            ),
            "snapshot_contributor_gate": (
                "Strongest simple anti-Sybil gate tested, but suppresses all "
                "reputation influence from users below Contributor depth."
            ),
            "positive_evidence_gate": (
                "Keeps three resolved actions as the sample-size requirement "
                "but requires at least one successful resolved action to leave "
                "Provisional."
            ),
        },
    }
