# TruthLens Trust Score — Hardening Experiments

Status: candidate-policy comparison; no production behavior changed  
Research basis: `docs/TRUST_SCORE_REPUTATION_DEEP_RESEARCH.md`  
Baseline validation: `docs/TRUST_SCORE_CALIBRATION_VALIDATION.md`  
Experiment implementation: `backend/truthlens_backend/api/trust_score_hardening_experiments.py`

## Purpose

The baseline validation found two material failures:

- **I8:** fresh accounts have enough immediate voting influence to change a major reputation rank with a small coordinated cluster;
- **I9:** historical vote impact changes when the voter's later Trust Score changes.

This document compares narrow hardening policies intended to solve those failures **without redesigning the Bayesian contribution-quality core**.

No candidate in this document is active in production.

---

# 1. External comparison: fact-checking systems also reduce new-rater influence

TruthLens should not copy another platform's algorithm, but systems operating in community fact-checking provide useful design comparisons.

X Community Notes explicitly describes a contributor reputation system in which contributors with a demonstrated history of high-quality contributions receive more influence, while new accounts with no helpful track record receive lower influence.

Sources:

- Community Notes, challenges / preventing coordinated manipulation:  
  https://github.com/twitter/communitynotes/blob/main/documentation/about/challenges.md
- Community Notes ranking algorithm:  
  https://communitynotes.x.com/guide/en/under-the-hood/ranking-notes

Community Notes has also evolved beyond raw vote ratios. Its public algorithm documentation records changes from direct averages toward approaches using contributor/rater histories and cross-perspective agreement.

Meta's Community Notes implementation similarly places eligibility requirements on contributors, including account age and good standing, and uses rating history as part of its approach.

Sources:

- https://www.meta.com/technologies/community-notes/
- https://about.fb.com/news/2025/03/testing-begins-community-notes-facebook-instagram-threads/

TruthLens implication:

> The finding that a brand-new TruthLens account immediately receives substantial reputation influence is a legitimate hardening concern, not merely an aesthetic preference.

TruthLens still needs its own simpler and explainable policy.

---

# 2. Current control policy

Current production behavior:

```text
vote weight =
    0.5 + current_voter_trust / 200
```

Examples:

| Current voter Trust | Weight |
|---:|---:|
| 0 | 0.50 |
| 25 | 0.625 |
| 50 | 0.75 |
| 75 | 0.875 |
| 100 | 1.00 |

A new account starts at Trust 50 and therefore immediately has:

```text
0.75
```

vote weight.

The calculation uses the voter's **current** Trust Score rather than the stored vote-time snapshot.

---

# 3. Candidate A — immutable vote-time snapshot only

Formula:

```text
vote weight =
    0.5 + vote_trust_snapshot / 200
```

## Result

This directly fixes historical reinterpretation.

A historical vote cast at Trust 50 remains weighted from Trust 50 even if the voter later becomes Trust 90.

### Strengths

- fixes I9;
- deterministic and auditable;
- uses data TruthLens already stores;
- removes cascading dependency on the voter's future score;
- simple to explain.

### Limitation

It does **nothing** to fix I8.

A fresh account's snapshot is still:

```text
50
```

so the vote still receives:

```text
0.75
```

weight.

Attack thresholds therefore remain essentially unchanged.

Conclusion:

> **Snapshot weighting should be considered a historical-integrity fix, not a complete manipulation-resistance solution.**

---

# 4. Candidate B — snapshot × observed-evidence share

This experiment keeps the immutable snapshot and introduces a smooth history-depth factor.

Formula:

```text
base_vote_weight =
    0.5 + vote_trust_snapshot / 200

observed_evidence_share =
    n / (n + 4)

effective_vote_weight =
    base_vote_weight × observed_evidence_share
```

where:

```text
n = voter's resolved Community reputation actions
4 = current Beta(2,2) prior mass
```

## Why `n/(n+4)`?

TruthLens already uses:

```text
Beta(2,2)
```

for contribution-quality smoothing.

That prior contributes:

```text
2 + 2 = 4
```

pseudo-observations.

After `n` real resolved actions, the fraction of posterior observation mass contributed by real observations is:

```text
n / (n + 4)
```

This experiment uses that value as a transparent **evidence-depth shrinkage factor**.

Important:

> This is not claimed to be a formal Bayesian credible interval or a literature-prescribed vote formula.

It is a TruthLens candidate derived consistently from the prior already used by the system.

## Effect by history depth

| Resolved actions | Evidence-share factor |
|---:|---:|
| 0 | 0.000 |
| 1 | 0.200 |
| 2 | 0.333 |
| 3 | 0.429 |
| 5 | 0.556 |
| 10 | 0.714 |
| 25 | 0.862 |
| 50 | 0.926 |
| 100 | 0.962 |

Thus:

```text
fresh account
n = 0
effective reputation vote influence = 0
```

without banning the user from voting in the Community UI.

The vote can still be stored as social feedback; it simply does not yet affect somebody else's reputation calculation.

---

# 5. Candidate C — Contributor eligibility gate

This experiment counts reputation votes only from users satisfying:

```text
resolved actions >= 10
AND
Trust Score >= 55
```

These are the current Contributor rank gates.

Eligible users receive the full snapshot-based weight.

## Strengths

- simple;
- blocks fresh/low-history accounts completely;
- materially raises the cost of Sybil influence;
- fixes I9 when used with snapshots.

## Limitation

It is blunt.

A user with:

```text
9 resolved actions
excellent record
```

has zero reputation influence, while crossing the tenth action suddenly grants full influence.

This suppresses legitimate low-history participation more strongly than Candidate B.

---

# 6. Attack-threshold comparison

Promotion baseline:

```text
18 verified
7 rejected
5 successful months

64.48
Contributor
```

Demotion baseline:

```text
25 verified
0 rejected
5 successful months

76.55
Trusted Contributor
```

## 6.1 Current / snapshot-only

Snapshot-only has the same attack thresholds as current behavior when the voter's score has not changed.

| Voter archetype | Effective weight | Upvotes to promote | Downvotes to demote |
|---|---:|---:|---:|
| Fresh, Trust 50, 0 actions | 0.750 | 5 | 5 |
| 3 successes, Trust 61.71 | 0.809 | 4 | 5 |
| 3 failures, Trust 39.29 | 0.696 | 5 | 6 |
| 10 successes, Trust 72.86 | 0.864 | 4 | 5 |
| 25 successes, Trust 76.55 | 0.883 | 4 | 5 |

This confirms that snapshot-only solves historical integrity but not low-history influence.

## 6.2 Snapshot × observed-evidence share

| Voter archetype | Effective weight | Upvotes to promote | Downvotes to demote |
|---|---:|---:|---:|
| Fresh, 0 actions | 0.000 | >100 / none | >100 / none |
| 3 successes | 0.347 | 9 | 11 |
| 3 failures | 0.298 | 11 | 13 |
| 10 successes | 0.617 | 6 | 7 |
| 25 successes | 0.761 | 5 | 5 |

This candidate changes the attack economics substantially.

Fresh identities cannot alter reputation by creating additional fresh identities alone.

To obtain meaningful influence, an attacker must first build resolved Community history.

The policy does **not** make collusion impossible.

For example:

```text
9 accounts × 3 successful resolved actions
```

can still cross the tested promotion boundary.

The value of the policy is that it converts a near-zero-history attack into an attack requiring independently accumulated resolved reputation evidence.

## 6.3 Snapshot + Contributor gate

| Voter archetype | Upvotes to promote | Downvotes to demote |
|---|---:|---:|
| Fresh | none | none |
| 3 successes | none | none |
| 3 failures | none | none |
| 10 successes | 4 | 5 |
| 25 successes | 4 | 5 |

This creates the strongest simple entry barrier but does not attenuate influence once the eligibility boundary is crossed.

---

# 7. Legitimate-participation trade-off

A good anti-manipulation policy should not remove useful Community signal unnecessarily.

Community points generated by five positive votes:

| Voter history | Current / snapshot-only | Snapshot × evidence share | Contributor gate |
|---|---:|---:|---:|
| 3 successful actions | +6.99 | +3.20 | 0.00 |
| 10 successful actions | +7.40 | +5.52 | +7.40 |
| 25 successful actions | +7.53 | +6.64 | +7.53 |

Interpretation:

### Snapshot-only

Preserves all current Community influence, including the fresh-account problem.

### Contributor gate

Preserves full established influence but completely discards reputation impact from legitimate users below Contributor depth.

### Snapshot × evidence share

Provides a gradual transition:

```text
no history -> no reputation influence
little history -> partial influence
substantial history -> most of full influence
```

This is currently the most balanced candidate in the experiment.

---

# 8. Historical stability result

Test case:

```text
five votes cast when voter Trust = 50
later voter Trust = 90
```

Results:

| Policy | Historical effect stable? |
|---|---|
| Current dynamic Trust | **No** |
| Snapshot only | **Yes** |
| Snapshot × evidence share | **Yes** |
| Snapshot + Contributor gate | **Yes** |

All snapshot-based candidates fix I9.

---

# 9. Provisional graduation experiment

Current rule:

```text
resolved actions >= 3
```

is sufficient to leave Provisional because New Contributor has no meaningful score floor above zero.

Observed current behavior:

```text
3 failures
Trust Score 39.29
-> New Contributor
```

Candidate:

```text
resolved actions >= 3
AND
validated actions >= 1
```

Results:

| Scenario | Current | Positive-evidence gate |
|---|---|---|
| 3 failures | New Contributor | **Provisional** |
| 1 success + 2 failures | New Contributor | New Contributor |
| 3 successes | New Contributor | New Contributor |

This candidate separates:

```text
sample size
```

from:

```text
positive qualification for first rank
```

without changing higher-rank score/action thresholds.

This appears more semantically coherent than the current rule and is simple to explain.

---

# 10. Evidence vs Safety-report weighting

The hardening experiments do **not** change the current 1:1 treatment of:

```text
verified evidence
valid Safety report
```

Reasons:

1. the research definition of Trust Score is Community reputation, not verification expertise;
2. there is not yet empirical evidence showing that a different numeric ratio would improve the model;
3. arbitrary partial weights would weaken the clean Beta success/failure interpretation;
4. professional factual authority is already separated institutionally.

Current recommendation:

> **Retain equal weighting for this phase, while documenting it as a Community-reputation design choice.**

Revisit only if user/evaluator research indicates that Trust Score is being interpreted as factual expertise.

---

# 11. Temporal decay

The candidate experiments also retain:

```text
no temporal decay
```

The baseline analysis showed that the model is stable, recoverable, and already has a faster negative response through Safety moderation penalties.

The literature provides a basis for investigating forgetting, but the current experiments do not establish a concrete need.

Recommendation:

> **Do not add temporal decay in this hardening phase.**

---

# 12. Preliminary candidate assessment

| Candidate | Fixes I9 | Fixes fresh I8 | Smooth participation | Explainable | Current assessment |
|---|:---:|:---:|:---:|:---:|---|
| Snapshot only | ✅ | ❌ | ✅ | ✅ | Necessary integrity fix, insufficient alone |
| Snapshot × evidence share | ✅ | ✅ | ✅ | ✅ | **Best current trade-off** |
| Snapshot + Contributor gate | ✅ | ✅ | ❌ | ✅ | Effective but likely too restrictive |
| Positive-evidence Provisional gate | n/a | n/a | ✅ | ✅ | Strong first-rank candidate |

---

# 13. Important limitation

Passing the fresh-account stress probe does **not** mean TruthLens becomes Sybil-proof.

An attacker may still:

- age/farm accounts;
- build resolved history across multiple accounts;
- coordinate established users;
- compromise legitimate accounts.

This is normal for reputation systems.

Formula-level hardening should therefore be complemented by platform-level controls such as:

- rate limiting;
- account security;
- duplicate/automation detection;
- suspicious coordinated-activity monitoring;
- moderation/accountability;
- possible eligibility controls if future evidence requires them.

Community Notes similarly describes reputation weighting alongside suspicious-activity guardrails rather than treating one formula as a complete defense.

---

# 14. Current recommendation

Before implementation, the strongest candidate package is:

## H1 — immutable vote-time weight

Use:

```text
vote_trust_snapshot
```

instead of the voter's current persisted Trust Score.

## H2 — history-depth attenuation

For reputation impact only:

```text
effective_vote_weight =
    (0.5 + vote_trust_snapshot / 200)
    ×
    resolved_actions / (resolved_actions + 4)
```

The four derives from the existing `Beta(2,2)` prior mass.

## H3 — positive evidence for first rank

To leave Provisional:

```text
resolved_actions >= 3
AND
validated_actions >= 1
```

## H4 — leave the rest unchanged initially

Retain for the first hardening iteration:

- Beta(2,2);
- Contribution Quality ±25;
- Community Reception ±15;
- signal scale 8;
- history +5;
- moderation penalty 5 / cap 30;
- Contributor / Trusted / Expert thresholds;
- equal evidence/report binary quality treatment;
- no temporal decay.

This minimizes simultaneous variables and makes post-change validation interpretable.

---

# 15. Decision standard

These candidates should be implemented in production **only after**:

1. automated experiment tests pass;
2. production-parity tests remain green;
3. the proposed production calculation has migration/backfill semantics defined;
4. existing votes with null snapshots are handled safely;
5. score recalculation behavior is specified;
6. user-facing explanations remain accurate;
7. the full baseline scenario suite is rerun against the candidate;
8. the research/calibration documents are updated with final accepted behavior.

The goal is targeted hardening, not formula churn.
