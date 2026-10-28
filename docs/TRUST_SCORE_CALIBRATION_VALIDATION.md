# TruthLens Trust Score — Calibration & Adversarial Validation

Status: baseline validation of the current production formula  
Companion research: `docs/TRUST_SCORE_REPUTATION_DEEP_RESEARCH.md`  
Validation implementation: `backend/truthlens_backend/api/trust_score_validation.py`  
Management command: `analyze_trust_score_model`

## Purpose

This document evaluates the **current** TruthLens Trust Score calibration without changing production scoring behavior.

The research document establishes the theoretical basis for the architecture. This document asks a different question:

> Given TruthLens's actual constants and rank thresholds, does the model behave sensibly under realistic, boundary, and adversarial scenarios?

The validation is deterministic and offline. It does not use production user data, make database writes, call external providers, or modify any user's Trust Score.

---

# 1. Current calibration under test

```text
Base Score                   50

Contribution Quality        -25 to +25
Beta prior                   (2, 2)

Community Reception         -15 to +15
Community signal scale        8

Sustained History             0 to +5

Removed-thread penalty        5 each
Moderation penalty cap       30
```

Current ranks:

| Rank | Minimum score | Minimum resolved actions |
|---|---:|---:|
| Provisional | — | 0-2 |
| New Contributor | 0 | 3 |
| Contributor | 55 | 10 |
| Trusted Contributor | 70 | 25 |
| Expert Contributor | 85 | 50 |

No parameter in this document has yet been approved for change.

---

# 2. Reproducible validation command

From:

```text
backend/truthlens_backend
```

run:

```powershell
py .\manage.py analyze_trust_score_model --settings=truthlens_backend.test_settings
```

For the sensitivity matrix:

```powershell
py .\manage.py analyze_trust_score_model --sensitivity --settings=truthlens_backend.test_settings
```

For machine-readable output:

```powershell
py .\manage.py analyze_trust_score_model --json --settings=truthlens_backend.test_settings
```

The command is intentionally:

```text
OFFLINE ONLY
NO DATABASE READS
NO DATABASE WRITES
NO EXTERNAL CALLS
NO PRODUCTION SCORE CHANGES
```

A separate parity test verifies that the simulator's mathematical output matches the production `calculate_trust_components()` implementation for a database-backed scenario.

---

# 3. Baseline persona results

| Scenario | Score | Rank | Quality | Community | History | Penalty |
|---|---:|---|---:|---:|---:|---:|
| New user | 50.00 | Provisional | 0.00 | 0.00 | 0 | 0 |
| One verified evidence item | 56.00 | Provisional | +5.00 | 0.00 | +1 | 0 |
| One rejected evidence item | 45.00 | Provisional | -5.00 | 0.00 | 0 | 0 |
| 25/25 verified evidence | 76.55 | Trusted Contributor | +21.55 | 0.00 | +5 | 0 |
| 30 verified / 20 rejected | 59.63 | Contributor | +4.63 | 0.00 | +5 | 0 |
| 49 verified / 1 rejected | 77.22 | Trusted Contributor | +22.22 | 0.00 | +5 | 0 |
| 50 verified + one removed thread | 73.15 | Trusted Contributor | +23.15 | 0.00 | +5 | -5 |
| 25 valid Safety reports only | 76.55 | Trusted Contributor | +21.55 | 0.00 | +5 | 0 |
| 25 invalid Safety reports only | 28.45 | New Contributor | -21.55 | 0.00 | 0 | 0 |
| 18 verified / 7 rejected, no votes | 64.48 | Contributor | +9.48 | 0.00 | +5 | 0 |
| Same 18/7 + ten fresh-account upvotes | 75.49 | Trusted Contributor | +9.48 | +11.01 | +5 | 0 |
| 25/25 verified + ten fresh-account downvotes | 65.54 | Contributor | +21.55 | -11.01 | +5 | 0 |
| Five early failures | 36.11 | New Contributor | -13.89 | 0.00 | 0 | 0 |
| Five failures + twenty later successes | 67.93 | Contributor | +12.93 | 0.00 | +5 | 0 |
| Three failed resolved actions | 39.29 | New Contributor | -10.71 | 0.00 | 0 | 0 |

"Fresh account" in these probes means an otherwise eligible Community identity with the default Trust Score of 50. Current Community participation checks require an active authenticated non-platform-staff identity; they do not require an established reputation history.

---

# 4. Invariant evaluation

The research phase defined ten desirable invariants.

## I1 — Neutral cold start

**PASS**

A user with no resolved Community reputation evidence remains at:

```text
50
```

This preserves a neutral cold start.

## I2 — Small-sample restraint

**PASS**

One success:

```text
Contribution Quality = +5
Trust Score with one successful month = 56
```

One failure:

```text
Contribution Quality = -5
Trust Score = 45
```

A single action cannot create an extreme reputation.

## I3 — Quality dominance

**PASS structurally**

```text
Contribution Quality cap = ±25
Community Reception cap  = ±15
```

Professionally resolved contribution quality has more maximum influence than Community reception.

## I4 — Community signal remains meaningful

**PASS**

Eligible positive reception increases Trust Score and negative reception decreases it.

The Community component is not decorative.

## I5 — Confirmed bad behavior matters

**PASS**

A removed/rejected authored thread lowers an otherwise identical score by the configured penalty.

The moderation path has a direct negative reputation effect.

## I6 — Recovery remains possible

**PASS**

Five failed contributions:

```text
36.11
```

followed by twenty successes and sustained activity:

```text
67.93
```

The system does not permanently trap a user because of an early poor record.

## I7 — High rank requires evidence depth

**PASS**

Even a hypothetical Trust Score of 95 with only 25 resolved actions cannot reach Expert Contributor because Expert requires 50 resolved actions.

## I8 — Fresh-account voting should not easily change high-level rank

**FAIL**

Current stress persona:

```text
18 verified
7 rejected
5 successful months
no votes

Trust Score = 64.48
Rank = Contributor
```

Only **five** upvotes from users at the default Trust Score of 50 are sufficient to produce:

```text
Trust Score = 71.04
Rank = Trusted Contributor
```

This does not prove that a real coordinated attack will occur, but it shows that the **mathematical reputation layer gives fresh eligible accounts enough aggregate influence to cross a major rank boundary**.

## I9 — Historical interpretation should be reproducible

**FAIL under current dynamic voter weighting**

Five historical positive votes weighted at voter Trust 50 produce:

```text
76.41
```

If the exact same voters later rise to Trust 90 and the target is recalculated:

```text
77.85
```

The stored vote action did not change, but its historical effect did.

Because changes to those voters do not automatically recompute every past vote recipient, this also creates a persisted-score synchronization risk.

The existing `vote_trust_snapshot` field is therefore highly relevant to the hardening phase.

## I10 — Community reputation must not grant professional authority

**ARCHITECTURAL — currently preserved outside the mathematical model**

Partner Organization verification authority is controlled by organization lifecycle, membership, and role capabilities rather than Trust Score.

The numeric simulator cannot prove this invariant; authorization tests must continue to cover it separately.

---

# 5. Attack-threshold analysis

The validation framework searches for the smallest vote cluster that changes a rank in two controlled scenarios.

## 5.1 Promotion probe

Baseline:

```text
18 verified / 7 rejected
5 successful months
Trust Score 64.48
Contributor
```

Minimum coordinated **upvotes** required to reach Trusted Contributor:

| Voter Trust Score | Minimum votes | Resulting score |
|---:|---:|---:|
| 0 | 7 | 70.66 |
| 25 | 5 | 70.06 |
| 50 | 5 | 71.04 |
| 75 | 4 | 70.66 |
| 100 | 4 | 71.41 |

The current score-only voter weighting therefore gives even zero-score voters meaningful aggregate influence.

## 5.2 Demotion probe

Baseline:

```text
25 verified / 0 rejected
5 successful months
Trust Score 76.55
Trusted Contributor
```

Minimum coordinated **downvotes** required to fall to Contributor:

| Voter Trust Score | Minimum votes | Resulting score |
|---:|---:|---:|
| 0 | 8 | 69.62 |
| 25 | 6 | 69.99 |
| 50 | 5 | 69.99 |
| 75 | 5 | 69.08 |
| 100 | 4 | 69.62 |

Again, Community Reception is bounded, but the current rank thresholds allow a relatively small coordinated voting group to cross a boundary when the target is close enough to that boundary.

### Interpretation

This is not primarily evidence that `±15` is mathematically invalid.

It is evidence that:

```text
voter Trust Score alone
```

may be insufficient as the eligibility/credibility model for Community influence.

A fresh user begins at 50 and immediately receives:

```text
0.75 vote weight
```

despite having no resolved reputation history.

That is the more important policy question.

---

# 6. Rank-semantic diagnostic

Current behavior:

```text
3 failed resolved actions
Trust Score = 39.29
Rank = New Contributor
```

The score correctly reflects poor performance, but the user leaves Provisional because the first rank requires only:

```text
3 resolved actions
score >= 0
```

This confirms the concern identified during the research audit:

> Sample-size confidence and positive rank qualification are currently conflated at the first promotion boundary.

Potential future approaches to test include:

- require at least one successful resolved action;
- require a minimum validated-action count;
- introduce a minimum Trust Score for New Contributor.

No change is approved yet.

---

# 7. Evidence/report context diagnostic

Current model equivalence:

```text
25 verified evidence actions
5 successful months
=> 76.55 / Trusted Contributor
```

and:

```text
25 valid Safety reports
5 successful months
=> 76.55 / Trusted Contributor
```

The two histories are mathematically identical when other inputs are equal.

This is internally consistent **if Trust Score means broad Community participation reliability**.

It is harder to defend if Trust Score is interpreted as factual-verification expertise.

This reinforces the research definition:

> Trust Score is Community reputation, not professional fact-checking authority.

The remaining question is whether equal weighting is the best calibration even under the broader Community-reputation definition.

---

# 8. Sensitivity findings

The simulator varies one parameter at a time while keeping production behavior untouched.

## 8.1 Bayesian prior

One successful evidence item produces:

| Prior | Score with one verified item + one successful month |
|---|---:|
| Beta(1,1) | 59.33 |
| Beta(2,2) — current | 56.00 |
| Beta(3,3) | 54.57 |

Interpretation:

- `Beta(1,1)` reacts more aggressively to very small samples;
- `Beta(3,3)` is more conservative;
- current `Beta(2,2)` sits between them.

At larger sample sizes the prior matters progressively less.

The current choice remains reasonable pending broader simulations.

## 8.2 Contribution cap

For the recovery persona:

| Quality cap | Result |
|---:|---|
| ±20 | 65.34 / Contributor |
| ±25 — current | 67.93 / Contributor |
| ±30 | 70.52 / Trusted Contributor |

For the vote-attack probes, increasing the quality cap does not uniformly improve robustness:

- a larger quality cap makes excellent users harder to demote;
- but it can also move a middling user closer to the Trusted threshold, requiring fewer coordinated upvotes for promotion.

This is evidence against treating one numeric cap as a complete anti-manipulation solution.

## 8.3 Community cap

Fresh-50-voter attack thresholds:

| Community cap | Promotion votes | Demotion votes |
|---:|---:|---:|
| ±10 | 7 | 9 |
| ±15 — current | 5 | 5 |
| ±20 | 4 | 4 |

Reducing the cap helps, but even `±10` still permits rank changes with a relatively small cluster.

## 8.4 Community saturation scale

Fresh-50-voter attack thresholds:

| Signal scale | Promotion votes | Demotion votes |
|---:|---:|---:|
| 5 | 3 | 4 |
| 8 — current | 5 | 5 |
| 12 | 7 | 8 |

A larger scale makes early votes less influential.

Again, this mitigates rather than solves the fresh-account credibility problem.

## 8.5 History cap

Changing the history cap from 5 to 3 reduces mature persona scores by up to two points in these five-month scenarios.

Increasing the cap from 5 to 10 makes no difference until a user has more than five distinct successful months.

This factor is currently modest relative to the other components.

## 8.6 Moderation penalty

For a 50-success user with one removed thread:

| Per-thread penalty | Score |
|---:|---:|
| 3 | 75.15 |
| 5 — current | 73.15 |
| 8 | 70.15 |

All three variants remain Trusted Contributor in this specific scenario.

This suggests the current penalty is meaningful without making one Safety outcome erase an extensive otherwise-successful record.

Whether severe moderation should have additional consequences belongs to Safety/governance policy rather than arbitrary numeric inflation.

---

# 9. Score ceiling diagnostic

The nominal positive-component ceiling is:

```text
50 + 25 + 15 + 5 = 95
```

The Bayesian quality and `tanh` Community components approach their caps asymptotically.

Therefore:

```text
100
```

is a nominal/theoretical endpoint rather than an attainable ordinary score under the current positive components.

The validation does not currently identify this as a mathematical defect.

It should simply be documented so the scale is not misrepresented.

---

# 10. Temporal diagnostic

The current contribution-quality model is lifetime-aggregate.

These two histories are mathematically equivalent:

```text
20 successes, then 5 failures
```

and:

```text
5 failures, then 20 successes
```

if their successful-month counts are also equal.

The formula therefore models:

```text
historical aggregate reputation
```

rather than:

```text
recent behavioral state
```

The literature supports investigating forgetting/decay, but this validation does **not** yet show that TruthLens needs decay.

The existing moderation penalty already supplies a faster response to confirmed severe Community violations.

No temporal-decay change is recommended at this stage.

---

# 11. Preliminary calibration assessment

The validation supports retaining the **overall architecture**:

```text
neutral baseline
+ Bayesian contribution quality
+ bounded community reception
+ sustained successful history
- confirmed moderation penalty
```

The strongest current properties are:

- neutral cold start;
- restrained small-sample behavior;
- recoverability;
- quality having more maximum weight than popularity;
- high ranks requiring both score and action depth;
- bounded components;
- understandable score decomposition.

The main weaknesses are policy/integrity issues rather than evidence that the whole equation is unsound:

1. historical votes are dynamically re-weighted;
2. fresh accounts receive substantial voter influence immediately;
3. three failures can leave Provisional status;
4. valid reports and verified evidence are fully interchangeable in the quality signal;
5. temporal order is ignored.

---

# 12. Current recommendation before behavioral changes

Do **not** redesign the full formula.

The next candidate hardening experiments should be evaluated independently:

### A. Immutable historical vote weighting

Compare:

```text
current voter Trust Score
```

against:

```text
vote_trust_snapshot
```

Primary goals:

- deterministic historical interpretation;
- easier auditing;
- no cascading recomputation dependency.

### B. Voter confidence / eligibility

Test models where a user's vote influence depends on resolved reputation history as well as score.

The research framework should compare options before choosing a formula.

### C. Provisional graduation

Test a positive-evidence requirement for leaving Provisional.

### D. Evidence vs Safety-report weighting

Test whether equal weighting should remain or whether the components should be distinguished.

### E. Temporal sensitivity

Retain no-decay as the baseline and compare it with mild alternatives only if scenario testing shows that recent deterioration is insufficiently represented.

---

# 13. Validation status

Current numeric invariant result:

```text
PASS: 7
FAIL: 2
ARCHITECTURAL: 1
```

Known failed invariants:

```text
I8 — fresh-account vote cluster can change a major rank
I9 — historical vote effect changes when voter Trust changes
```

These failures are intentionally captured in automated tests.

That means a future scoring change cannot silently "fix" or alter the research baseline without requiring the validation expectations to be reviewed.

---

# 14. Interpretation for the capstone

At this stage, the defensible conclusion is:

> **The TruthLens Trust Score architecture is research-informed and its core mathematical structure behaves well across most baseline properties. Deterministic validation identifies two material hardening needs in the current implementation: historical vote-weight stability and resistance to substantial influence from low-history voters. Additional policy questions remain around first-rank qualification and the equal treatment of evidence and Safety-report outcomes. The project therefore retains the existing formula as the baseline while testing targeted hardening alternatives rather than replacing the model wholesale.**

This is stronger than claiming the formula is perfect.

It shows that the team:

- grounded the design in literature;
- made calibration assumptions explicit;
- tested realistic and adversarial scenarios;
- recorded failures rather than hiding them;
- separates research-supported architecture from project-specific constants;
- will change behavior only when validation supports the change.
