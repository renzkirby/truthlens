# TruthLens Trust Score — Reputation-System Deep Research

Status: research basis for Trust Score validation and hardening  
Scope: Community reputation only; not Partner Organization verification authority  
Current implementation reference: `backend/truthlens_backend/api/trust_service.py`

## Research question

How can TruthLens justify, evaluate, and improve its Trust Score as a Community reputation mechanism using established research on computational trust and reputation, while keeping professional verification authority institutionally separate?

This document is intentionally not a claim that the exact TruthLens formula was copied from a published model. The literature supports several important **design principles** used by TruthLens. The exact weights, caps, nonlinear scaling constants, rank thresholds, and some eligibility rules are **TruthLens-specific calibration choices** that require scenario testing and sensitivity analysis.

---

# 1. What Trust Score means in TruthLens

TruthLens should define Trust Score as:

> **A bounded Community reputation estimate derived from a user's resolved contribution quality, reception of professionally verified evidence, sustained successful participation, and confirmed moderation outcomes.**

It should **not** mean:

- professional fact-checking authority;
- institutional verification authority;
- subject-matter accreditation;
- proof that a user is always correct;
- a universal measure of personal trustworthiness.

This distinction is important because reputation research consistently treats reputation as evidence derived from prior behavior, feedback, and context. Reputation systems are commonly used to help participants make decisions under uncertainty and to encourage good behavior in online communities, but the meaning of a reputation score depends on the system and interaction context.

TruthLens therefore keeps Community reputation separate from Partner Organization authority. Professional verification authority derives from governed organization membership and role capabilities, not from Community Trust Score.

Relevant sources:

- Resnick, Zeckhauser, Friedman & Kuwabara (2000), **Reputation Systems**, *Communications of the ACM*: https://rzeckhauser.scholars.harvard.edu/publications/reputation-systems
- Jøsang, Ismail & Boyd (2007), **A survey of trust and reputation systems for online service provision**, *Decision Support Systems*: https://doi.org/10.1016/j.dss.2005.05.019
- Hendrikx, Bubendorfer & Chard (2015), **Reputation systems: A survey and taxonomy**, *Journal of Parallel and Distributed Computing*: https://doi.org/10.1016/j.jpdc.2014.08.004
- Noorian & Ulieru (2010), **The State of the Art in Trust and Reputation Systems: A Framework for Comparison**: https://doi.org/10.4067/S0718-18762010000200007

TruthLens implication:

- public Community reputation can inform how other users interpret participation history;
- it must not silently become an authorization mechanism for professional verification;
- Partner Organization roles remain the source of professional authority;
- Trust Score labels and explanations should consistently say "Community reputation" rather than imply institutional credibility.

---

# 2. Current TruthLens formula

The current score is:

```text
Trust Score =
    clamp(
        50
        + Contribution Quality
        + Community Reception
        + Sustained History
        - Moderation Penalty,
        0,
        100
    )
```

Current component bounds:

| Component | Current range | Purpose |
|---|---:|---|
| Neutral baseline | 50 | Cold-start position |
| Contribution Quality | -25 to +25 | Resolved evidence/report quality |
| Community Reception | approximately -15 to +15 | Trust-weighted votes on verified evidence |
| Sustained History | 0 to +5 | Successful participation across distinct months |
| Moderation Penalty | 0 to -30 | Confirmed removed/rejected authored threads |

Current constants:

```python
BASE_SCORE = 50.0

CONTRIBUTION_POINTS_CAP = 25.0
PRIOR_SUCCESS = 2.0
PRIOR_FAILURE = 2.0

COMMUNITY_POINTS_CAP = 15.0
COMMUNITY_SIGNAL_SCALE = 8.0

HISTORY_POINTS_CAP = 5.0

REJECTED_THREAD_PENALTY = 5.0
MODERATION_PENALTY_CAP = 30.0
```

The current implementation is therefore a **multi-signal bounded reputation model**, not a raw vote average and not a simple activity-points system.

---

# 3. Bayesian contribution-quality basis

## 3.1 Relevant literature

The strongest direct research basis for the current quality component is:

**Ismail & Jøsang (2002), "The Beta Reputation System."**

Sources:

- BLED proceedings record: https://aisel.aisnet.org/bled2002/41/
- Conference archive: https://domino.fov.um.si/proceedings.nsf/Proceedings/D9E48B66F32A7DFFC1256E9F00355B37/

The Beta Reputation System uses beta probability distributions to combine positive and negative behavioral feedback and derive reputation estimates. Its stated strengths include simplicity, flexibility, and a foundation in statistical theory.

A beta distribution is a natural model for binary outcomes such as:

```text
successful / unsuccessful
valid / invalid
verified / rejected
```

If the prior distribution is:

```text
Beta(alpha, beta)
```

and there are `s` observed successes and `f` observed failures, the posterior mean is:

```text
(alpha + s) / (alpha + beta + s + f)
```

## 3.2 TruthLens mapping

TruthLens currently calculates:

```text
smoothed_accuracy =
    (validated_actions + 2)
    /
    (resolved_actions + 4)
```

Under a binary success/failure interpretation, this is exactly the posterior mean produced by a:

```text
Beta(2, 2)
```

prior.

The prior mean is:

```text
2 / (2 + 2) = 0.5
```

so new users begin at a neutral 50% expectation rather than appearing perfectly reliable or completely unreliable.

TruthLens then transforms the posterior mean around the neutral midpoint:

```text
quality_signal = (smoothed_accuracy - 0.5) * 2
```

and scales it to the contribution-quality cap:

```text
Contribution Quality =
    clamp(quality_signal * 25, -25, +25)
```

Examples:

| Resolved outcomes | Smoothed accuracy | Approx. quality points |
|---|---:|---:|
| none | 0.500 | 0.00 |
| 1 success | 0.600 | +5.00 |
| 1 failure | 0.400 | -5.00 |
| 1 success, 1 failure | 0.500 | 0.00 |
| 2 successes | 0.667 | +8.33 |
| 10 successes | 0.857 | +17.86 |
| 25 successes | 0.931 | +21.55 |
| 50 successes | 0.963 | +23.15 |

## 3.3 Why this is defensible

This design addresses a common cold-start problem:

```text
Raw success rate:
1 success / 1 action = 100%
```

would overstate evidence from a single observation.

With Bayesian smoothing:

```text
1 success -> 60%
```

The prior becomes progressively less important as observed evidence accumulates.

This is a strong design principle to retain.

## 3.4 What is TruthLens-specific

The literature supports beta/Bayesian aggregation, but it does **not** prescribe:

```text
Beta(2,2)
±25 contribution points
```

Those values are TruthLens calibration choices.

They should be defended through sensitivity analysis rather than described as universal academic constants.

---

# 4. Community feedback and rater credibility

## 4.1 Relevant literature

### EigenTrust

Kamvar, Schlosser & Garcia-Molina (2003), **The EigenTrust Algorithm for Reputation Management in P2P Networks**, is an influential example of reputation-weighted feedback.

Sources:

- ACM DOI: https://doi.org/10.1145/775152.775242
- Accessible WWW archive: https://archives.iw3c2.org/www2003/cdrom/papers/refereed/p446/p446-kamvar/index.html

EigenTrust's global trust values are based on local trust assessments weighted through the reputations of peers. Its security analysis specifically considers malicious collectives attempting to subvert the reputation system.

TruthLens does not implement EigenTrust, and should not claim that it does.

The relevant principle is narrower:

> **Feedback need not be treated as equally credible when the reliability of the feedback source differs.**

### Reliability of evidence

A recent survey of trust evaluation approaches similarly summarizes the common principle that different evidence can have different effects and that more reliable evidence supports more reliable trust evaluation:

- Hou et al. (2024), **A survey of the state-of-the-art approaches for evaluating trust in software ecosystems**: https://doi.org/10.1002/smr.2695

## 4.2 TruthLens mapping

TruthLens counts votes only when the target evidence has been professionally resolved as:

```text
VERIFIED
```

Votes on unverified or rejected evidence do not contribute to Community Reception.

That is a particularly strong design decision because raw popularity cannot increase reputation before the underlying contribution has passed professional evidence review.

For eligible votes, the current voter weight is:

```text
weight = 0.5 + voter_trust / 200
```

which gives:

| Voter Trust Score | Vote weight |
|---:|---:|
| 0 | 0.50 |
| 25 | 0.625 |
| 50 | 0.75 |
| 75 | 0.875 |
| 100 | 1.00 |

The maximum voter influence is therefore only twice the minimum.

This prevents highly reputable users from having arbitrarily dominant voting power.

## 4.3 Current nonlinear aggregation

TruthLens aggregates the weighted signal as:

```text
Community Reception =
    tanh(weighted_vote_signal / 8) * 15
```

The hyperbolic tangent is bounded and has diminishing marginal returns.

This gives the system an important structural property:

> Very large vote volumes cannot produce unbounded reputation gains or losses.

Community popularity is capped below Contribution Quality:

```text
Community Reception cap = ±15
Contribution Quality cap = ±25
```

Therefore, votes cannot mathematically overpower the main professionally resolved contribution-quality component by themselves.

## 4.4 What is research-backed vs calibrated

Research-backed principle:

- feedback can inform reputation;
- feedback-source reliability can matter;
- reputation systems need defenses against manipulative feedback;
- feedback should not be allowed unlimited influence.

TruthLens-specific calibration:

- minimum vote weight `0.50`;
- maximum vote weight `1.00`;
- linear mapping `0.5 + trust/200`;
- `tanh` specifically;
- divisor `8`;
- cap `±15`.

Those constants need empirical sensitivity testing.

---

# 5. The vote snapshot issue

TruthLens stores:

```python
Vote.vote_trust_snapshot
```

when a vote is cast.

However, the current Trust Score calculation does not use the snapshot. It retrieves the voter's **current persisted Trust Score** whenever the target contributor is recalculated.

Current behavior can therefore be:

```text
Alice votes when Trust = 50
vote_trust_snapshot = 50

Alice later becomes Trust = 90

Bob's score is recalculated
Alice's old vote is now weighted using 90
```

This creates two problems.

## 5.1 Historical interpretation changes retroactively

An old action changes meaning because the actor's later reputation changed.

That reduces auditability.

## 5.2 Recalculation dependency becomes incomplete

Alice's Trust Score changing does not automatically cause every contributor historically voted on by Alice to be recomputed.

Therefore:

```text
persisted public score
```

can temporarily differ from:

```text
score obtained by recalculating the formula today
```

### Research relevance

Manipulation-resistant reputation research emphasizes reliable feedback aggregation and resistance to strategic manipulation. Deterministic historical evidence is also easier to audit than dynamically reinterpreted old actions.

Relevant sources:

- Friedman, Resnick & Sami (2011), **Manipulation-Resistant Reputation Systems**, in *Algorithmic Game Theory*: https://www.cambridge.org/core/books/abs/algorithmic-game-theory/manipulationresistant-reputation-systems/13DBDA298DFFD00E6DA230C48267BBF1
- Dellarocas (2000), **Mechanisms for Coping with Unfair Ratings and Discriminatory Behavior in Online Reputation Reporting Systems**: https://aisel.aisnet.org/icis2000/52/
- Hoffman, Zage & Nita-Rotaru, **A Survey of Attack and Defense Techniques for Reputation Systems**: https://www.cerias.purdue.edu/apps/reports_and_papers/view/3319

### Current recommendation

This research strongly motivates evaluating:

```text
vote_trust_snapshot
```

as the authoritative historical weighting input.

This change should still be validated through sensitivity and abuse-case simulations before implementation.

---

# 6. Manipulation resistance: Sybil, collusion, ballot stuffing, whitewashing

## 6.1 Relevant literature

Reputation systems are known to face strategic attacks.

Friedman, Resnick & Sami identify three major strategic threats:

- whitewashing: abandoning a bad reputation and re-entering under a fresh identity;
- insufficient honesty or effort in feedback;
- Sybil attacks: using fake identities to manufacture feedback.

Source:

https://www.cambridge.org/core/books/abs/algorithmic-game-theory/manipulationresistant-reputation-systems/13DBDA298DFFD00E6DA230C48267BBF1

A modern survey similarly catalogs:

- Sybil attacks;
- ballot stuffing/self-promotion;
- bad-mouthing/slandering;
- whitewashing;
- oscillation;
- random ratings;
- free riding.

Source:

- Bellini et al. (2022), **Privacy-Preserving Reputation Systems Based on Blockchain and Other Cryptographic Building Blocks: A Survey**, *ACM Computing Surveys*: https://doi.org/10.1145/3490236

Swamynathan, Almeroth & Zhao also identify user collusion and short-lived identities as major sources of erroneous reputation values.

Source:

- **The design of a reliable reputation system**, *Electronic Commerce Research* (2010): https://doi.org/10.1007/s10660-010-9064-y

## 6.2 TruthLens protections already present

TruthLens already has several useful defenses:

- users cannot vote on their own evidence;
- one vote per voter/evidence pair is enforced;
- votes affect reputation only if evidence becomes professionally VERIFIED;
- Community Reception is bounded;
- contribution quality has more maximum positive influence than reception;
- rank promotion requires both score and resolved-action volume;
- professional authority is not granted through Trust Score.

These properties make simple popularity manipulation less powerful than in a raw upvote system.

## 6.3 Remaining exposure

A new TruthLens account begins at Trust Score 50.

Under current weighting:

```text
new account vote weight = 0.75
```

That is relatively high for an identity with little demonstrated history.

This raises an important future research question:

> Should vote influence depend on both reputation score and reputation confidence/sample size?

For example, a conceptual model could eventually distinguish:

```text
high score + little evidence
```

from:

```text
high score + extensive evidence
```

No formula should be adopted yet. This should be tested through Sybil/collusion simulations.

---

# 7. Reputation confidence and sample size

## 7.1 Research basis

Reputation values based on small amounts of evidence should not be interpreted with the same certainty as values backed by extensive history.

The Beta family itself expresses this statistically: as the total evidence represented by the beta parameters grows, posterior variance decreases.

A useful discussion of Beta systems and variance is:

- Schlosser, Voss & Brückner (2006), **On the Simulation of Global Reputation Systems**: https://www.jasss.org/9/1/4.html

Research on reputation with uncertainty explicitly argues for preserving uncertainty/evidence information rather than exposing only one reputation number:

- Škorić et al. (2015), **Flow-based reputation with uncertainty: evidence-based subjective logic**, *International Journal of Information Security*: https://doi.org/10.1007/s10207-015-0298-5

More generally, confidence-based decision approaches emphasize that a metric derived from uncertain evidence benefits from an accompanying confidence concept:

- Basheer et al. (2015), **Certainty, trust and evidence: Towards an integrative model of confidence in multi-agent systems**: https://doi.org/10.1016/j.chb.2014.12.030

## 7.2 TruthLens mapping

TruthLens currently maintains a separate reputation-confidence label based on resolved-action volume:

```text
0-2 actions   -> Provisional
3-9           -> Low
10-24         -> Developing
25-49         -> Established
50+           -> High
```

This is conceptually sound because:

```text
Trust Score
```

answers:

> What does the user's observed record currently indicate?

while:

```text
Reputation confidence
```

answers:

> How much resolved behavioral history supports that estimate?

A low Trust Score can therefore correctly have **High reputation confidence** if it is based on many resolved observations.

## 7.3 Important limitation

The current confidence thresholds are heuristic product thresholds.

They are **not formal Bayesian credible intervals** and should not be described as such.

Future work could compare the simple count-based labels against posterior variance/credible-interval methods, but the current design has the major advantage of being understandable to users.

---

# 8. Transparency and explainability

## 8.1 Relevant research

Sänger & Pernul (2018) identify an important reputation-system trade-off:

- simplistic computation can be easy to manipulate;
- sophisticated computation can become non-transparent and reduce user understanding and trust.

Source:

- **Interactive Reputation Systems: How to Cope with Malicious Behavior in Feedback Mechanisms**, *Business & Information Systems Engineering*: https://doi.org/10.1007/s12599-017-0493-1

## 8.2 TruthLens relevance

TruthLens currently has an explainable decomposition:

```text
50 baseline
+ Contribution Quality
+ Community Reception
+ Sustained History
- Moderation Penalty
```

The Dashboard can show these components independently.

That is a substantial product and research advantage.

A user can be told why their score moved without exposing a black-box machine-learning inference.

### Design implication

Hardening the model should preserve interpretability.

TruthLens should prefer:

- bounded, named components;
- explicit eligibility rules;
- inspectable historical inputs;
- scenario-tested constants;

over an opaque learned score unless strong evidence shows that complexity is necessary.

---

# 9. Context and multidimensional reputation

## 9.1 Relevant literature

Reputation is not necessarily universal across contexts.

Noorian & Ulieru explicitly include **context diversity checking** among the dimensions needed to evaluate trust and reputation systems.

Source:

https://doi.org/10.4067/S0718-18762010000200007

Hendrikx, Bubendorfer & Chard provide a reputation-context reference model and emphasize the importance of defining the context in which reputation evidence is generated.

Source:

https://doi.org/10.1016/j.jpdc.2014.08.004

Kokkodis (2021) argues that uniformly aggregating reputation across heterogeneous skillsets can ignore skill-specific variation, and proposes dynamic, multidimensional, skillset-specific reputation.

Source:

- **Dynamic, Multidimensional, and Skillset-Specific Reputation Systems for Online Work**, *Information Systems Research*: https://doi.org/10.1287/isre.2020.0972

## 9.2 TruthLens question: evidence vs Safety reports

TruthLens currently treats both of these as binary quality observations:

```text
VERIFIED evidence -> successful action
valid Safety report -> successful action

REJECTED evidence -> failed action
dismissed Safety report -> failed action
```

This is reasonable **only if Trust Score is interpreted broadly as Community participation reliability**.

It is weaker if Trust Score is presented as factual-verification expertise.

This is one reason the official definition should remain:

> Community reputation for reliable and constructive participation.

Professional verification expertise remains separately represented by Partner Organization authority.

## 9.3 Open research decision

We still need to test whether:

```text
1 verified evidence item
```

and:

```text
1 valid Safety report
```

should have exactly equal quality weight.

Possible future models include:

- retain equal weighting for simplicity;
- use separate subcomponents;
- use modestly different weights;
- count both for Community reputation but only evidence toward some rank conditions.

No change should be made until sensitivity analysis shows a meaningful benefit.

---

# 10. Sustained participation instead of passive account age

TruthLens does not grant reputation merely because an account is old.

Current logic awards one point for each distinct month with at least one successful resolved contribution, up to five months:

```text
successful month 1 -> +1
successful month 2 -> +1
...
maximum            -> +5
```

This is intentionally different from passive tenure.

### Research relevance

Reputation systems are fundamentally based on observed interactions, experiences, or feedback rather than mere elapsed time.

Sources:

- Jøsang, Ismail & Boyd survey: https://doi.org/10.1016/j.dss.2005.05.019
- Hendrikx et al. taxonomy: https://doi.org/10.1016/j.jpdc.2014.08.004
- Resnick et al., Reputation Systems: https://rzeckhauser.scholars.harvard.edu/publications/reputation-systems

### TruthLens design rationale

The +5 cap deliberately makes sustained history a **supporting signal**, not a dominant source of reputation.

A dormant old account receives no history bonus.

This principle is strong and should be retained unless testing reveals unexpected effects.

The exact `+1 per distinct month` and five-month cap are TruthLens calibration choices.

---

# 11. Moderation outcomes as collaborative sanctioning

Jøsang, Ismail & Boyd describe reputation systems as related to **collaborative sanctioning systems**: aggregated community information can both support decision-making and create incentives for good behavior.

Source:

https://doi.org/10.1016/j.dss.2005.05.019

TruthLens currently imposes:

```text
-5 per rejected/removed authored thread
maximum moderation penalty = -30
```

Rejected evidence is **not** separately penalized here because it already lowers Contribution Quality.

This avoids obvious double punishment:

```text
rejected evidence
-> Contribution Quality decreases
-> no duplicate moderation penalty
```

A removed authored thread is treated separately because it represents a stronger Safety moderation outcome.

### Strength

The penalty is:

- explicit;
- bounded;
- easy to explain;
- separated from ordinary quality failures.

### Limitation

All removed threads currently carry the same penalty regardless of severity or reason.

That is simple and auditable, but not granular.

For the current capstone scope, simplicity may be preferable to an elaborate severity matrix unless empirical evaluation demonstrates a need.

---

# 12. Temporal relevance and forgetting

## 12.1 Research basis

The original Beta Reputation System explicitly discusses **forgetting**:

> old feedback may become less relevant when an agent changes behavior over time.

The paper proposes reducing the weight of older feedback through a forgetting factor.

Source:

- Full Beta Reputation System paper, section on forgetting: https://domino.fov.um.si/proceedings.nsf/Proceedings/D9E48B66F32A7DFFC1256E9F00355B37/$File/josang.pdf

Contemporary work also examines stale ratings and the value of making ratings more reflective of current quality:

- Hamilton & Cui (2024), **Fresh Rating Systems: Structure, Incentives, and Fees**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4875071

Dynamic reputation research similarly criticizes systems that implicitly assume quality is static over time:

- Kokkodis (2021): https://doi.org/10.1287/isre.2020.0972

## 12.2 TruthLens current behavior

TruthLens currently has **no temporal decay** in Contribution Quality.

Old successful and unsuccessful resolved actions retain equal weight.

Example:

```text
100 historical successes
+
1 recent failure
```

changes the Bayesian quality signal only modestly.

## 12.3 Why no-decay is not automatically wrong

There is a legitimate design trade-off.

Historical-stability interpretation:

> A long record of reliable behavior should not disappear because of one recent mistake.

Current-state interpretation:

> Recent deterioration should be reflected more quickly.

TruthLens already has a faster negative path through the separate moderation penalty for removed threads.

### Research recommendation

Do not add time decay automatically.

Sensitivity analysis should compare:

- no decay;
- mild decay;
- windowed evidence;
- hybrid models where severe moderation outcomes respond quickly but ordinary quality history remains stable.

The simplest model that performs adequately should be preferred.

---

# 13. Reputation inflation and social-rating bias

Online ratings can suffer from systematic positive inflation and social pressure.

Filippas, Horton & Golden find that reputation ratings can become inflated over time, reducing their informativeness.

Sources:

- NBER working paper: https://www.nber.org/papers/w25857
- Published version: *Marketing Science* (2022)

Adamic, Lauterbach, Teng & Ackerman similarly discuss social difficulties in providing negative ratings and the resulting scarcity of negative feedback in a social community.

Source:

- **Rating Friends Without Making Enemies**, ICWSM: https://doi.org/10.1609/icwsm.v5i1.14121

### TruthLens relevance

This reinforces the decision **not** to make raw community approval the primary Trust Score driver.

TruthLens limits this risk by:

- counting reception only for professionally verified evidence;
- bounding Community Reception to ±15;
- giving professionally resolved Contribution Quality a larger ±25 range;
- keeping professional authority outside Community voting.

These are strong properties to retain.

---

# 14. Rank systems and multi-tier communities

Ziaie & Krcmar (2012) specifically discuss reputation systems in **multi-tier production communities**, where reputation can support meritocratic promotion between ranks.

Source:

- **Introducing a design framework for reputation systems in multi-tier production communities**: https://doi.org/10.1080/14626268.2012.709946

TruthLens currently uses:

| Rank | Minimum score | Minimum resolved actions |
|---|---:|---:|
| Provisional | — | 0-2 |
| New Contributor | 0 | 3 |
| Contributor | 55 | 10 |
| Trusted Contributor | 70 | 25 |
| Expert Contributor | 85 | 50 |

The two-dimensional gate is important:

```text
rank requires:
score quality
AND
minimum behavioral history
```

This prevents a user with a tiny number of successful actions from immediately reaching a high rank, and prevents high activity volume alone from overcoming a poor score.

### Weakness discovered in current rules

New Contributor has:

```text
minimum score = 0
minimum actions = 3
```

so three resolved failures can still end Provisional status.

The user's Trust Score will be poor, but the rank label becomes New Contributor.

That is logically awkward.

Future testing should compare:

- current rule;
- minimum Trust Score for New Contributor;
- minimum one successful resolved action;
- minimum successful-action count.

No threshold should be changed until scenario testing is complete.

---

# 15. Community-oriented reputation and over-gamification

Rough, De Paoli & Wilson argue that reputation mechanisms designed around competitive/self-interested incentives may be inappropriate for collaborative online communities.

Source:

- **Commonshare: A New Approach to Social Reputation for Online Collaborative Communities**: https://doi.org/10.1177/08944393211028191

### TruthLens relevance

TruthLens should avoid turning Community reputation into:

- a competitive leaderboard;
- a substitute for professional authority;
- a mechanism where users chase points for their own sake;
- a social-status system that overwhelms the informational mission.

This supports the current direction of:

- showing reputation as contextual participation history;
- keeping Partner professional identity separate;
- avoiding Trust Score presentation for current Partner professional identity;
- limiting rank language to Community participation.

---

# 16. Current score ceiling

The nominal range is:

```text
0-100
```

but the maximum positive component sum is:

```text
50 baseline
+25 quality
+15 reception
+5 history
=95
```

In addition:

- Bayesian quality approaches +25 asymptotically;
- `tanh` reception approaches +15 asymptotically.

Therefore exactly 95 is effectively asymptotic and 100 cannot be produced by ordinary current scoring.

This is not necessarily a flaw.

A defensible interpretation is:

```text
0   -> theoretical extreme negative reputation
50  -> neutral
95~ -> exceptional observed Community reputation
100 -> theoretical perfect upper endpoint
```

However, this should be deliberate and documented.

Sensitivity analysis should determine whether:

- the current scale is intuitive enough;
- users are likely to assume 100 is attainable;
- recalibration would materially improve interpretation.

The formula should not be distorted merely to make 100 reachable.

---

# 17. Current research-backed strengths

The strongest aspects of the existing model are:

## 17.1 Neutral cold start

A new user begins at 50 rather than zero or an artificially high score.

## 17.2 Bayesian smoothing

Small samples cannot instantly generate extreme quality estimates.

## 17.3 Resolved outcomes only

Pending evidence and unresolved reports do not influence Contribution Quality.

## 17.4 Professional evidence gate before reception affects reputation

Votes contribute only after evidence becomes VERIFIED.

## 17.5 Bounded community influence

Popularity cannot grow without limit or overpower Contribution Quality by itself.

## 17.6 Sustained successful participation instead of passive tenure

Old accounts do not gain points merely for existing.

## 17.7 Explicit negative outcomes

Poor contribution quality and confirmed moderation outcomes can reduce reputation.

## 17.8 Score + volume rank gates

Higher ranks require both quality and behavioral history.

## 17.9 Separate confidence

The system distinguishes estimated reputation from how much resolved history supports the estimate.

## 17.10 Explainability

The score can be decomposed into named, bounded factors.

---

# 18. Research-identified risks and open decisions

## Priority A — reputation integrity

### A1. Vote snapshot inconsistency

Current score recomputation uses the voter's current score rather than `vote_trust_snapshot`.

Research direction:

- compare snapshot weighting vs dynamic weighting;
- likely prefer immutable historical vote weight for auditability unless simulations demonstrate a clear benefit to dynamic weighting.

### A2. Persisted-score dependency

If dynamic voter scores remain authoritative, changes to a voter would need to trigger recomputation for every contributor affected by historical votes.

This is operationally more complex and easier to leave stale.

## Priority B — rank semantics

### B1. Failed actions advance the resolved-action counter

Three failed resolved actions can remove Provisional status.

Research direction:

- distinguish sample-size confidence from positive-rank qualification;
- evaluate a minimum successful-action gate.

## Priority C — context mixing

### C1. Evidence and Safety reports are equally weighted in quality

Research direction:

- verify whether equal weighting produces desirable Community-reputation behavior;
- preserve the distinction between Community reliability and factual-verification expertise.

## Priority D — manipulation resistance

### D1. Fresh accounts have substantial voting influence

New account:

```text
Trust = 50
vote weight = 0.75
```

Research direction:

- simulate Sybil clusters;
- test whether reputation confidence/history should moderate voter influence.

### D2. Collusion

Groups of accounts may repeatedly support each other's verified contributions.

Professional evidence verification greatly raises the difficulty of this attack, but it does not remove the need for simulation.

## Priority E — temporal adaptation

### E1. No decay

Research direction:

- determine whether stable historical reputation or responsive recent reputation better fits TruthLens;
- compare no-decay with mild forgetting.

---

# 19. TruthLens-specific calibration choices that require validation

The following should **not** be presented as values dictated by the literature:

```text
Beta prior:                (2,2)
Contribution cap:          ±25
Community cap:             ±15
Community signal scale:     8
History cap:                +5
Removed-thread penalty:     5
Moderation penalty cap:    30

New Contributor:            3 actions
Contributor:               55 + 10 actions
Trusted Contributor:       70 + 25 actions
Expert Contributor:        85 + 50 actions
```

These are design parameters.

They can still be well-justified if empirical scenario testing demonstrates desirable properties.

---

# 20. Recommended validation methodology

The next phase should validate the specific TruthLens calibration rather than search for a paper containing identical constants.

## 20.1 Sensitivity analysis

Vary one parameter at a time:

```text
Contribution cap:       20 / 25 / 30
Community cap:          10 / 15 / 20
Community scale:         5 / 8 / 12
History cap:             3 / 5 / 10
Moderation penalty:      3 / 5 / 8
Beta prior:           (1,1), (2,2), (3,3)
```

Observe:

- rank transitions;
- score volatility;
- newcomer behavior;
- impact of one mistake;
- impact of repeated success;
- resistance to community popularity overwhelming quality.

## 20.2 Persona scenarios

At minimum simulate:

1. brand-new user;
2. one excellent contribution;
3. one rejected contribution;
4. consistently strong contributor;
5. high-volume mediocre contributor;
6. strong contributor with one recent mistake;
7. strong contributor with a serious Safety removal;
8. user with many valid Safety reports but no evidence;
9. user with many dismissed Safety reports;
10. user with excellent evidence but no votes;
11. user with mediocre evidence and many votes;
12. user with high votes from fresh accounts;
13. user targeted by coordinated downvotes;
14. long-standing user whose behavior deteriorates;
15. user whose behavior improves after an early poor record.

## 20.3 Attack scenarios

Simulate:

- Sybil ballot stuffing;
- coordinated bad-mouthing;
- reciprocal voting rings;
- whitewashing/fresh accounts;
- oscillation: build reputation, then behave maliciously;
- report spam;
- high-volume low-quality contributions.

## 20.4 Desired invariants

The model should aim to preserve:

### I1 — Neutral cold start

New accounts should not appear strongly trusted or distrusted.

### I2 — Small-sample restraint

One or two actions should not cause extreme reputation.

### I3 — Quality dominance

Consistent professionally resolved contribution quality should matter more than popularity.

### I4 — Community usefulness without dominance

Votes should provide meaningful signal but not override poor contribution history.

### I5 — Bad behavior matters

Repeated poor or confirmed harmful behavior should decrease reputation.

### I6 — Recovery remains possible

A user with an early poor record should be able to recover through sustained legitimate behavior.

### I7 — High ranks require evidence depth

A tiny sample should never produce high reputation rank.

### I8 — Sybil resistance

Fresh-account voting clusters should have limited ability to materially alter high-level reputation outcomes.

### I9 — Auditability

The same stored historical evidence should reproduce the same score unless the system intentionally uses a documented time-dependent policy.

### I10 — Authority separation

No Community score/rank may independently grant Partner Organization verification authority.

---

# 21. Proposed defense statement

A concise defense-ready explanation can be:

> TruthLens Trust Score is a bounded Community reputation metric informed by established computational-reputation principles. It combines Bayesian-smoothed resolved contribution quality, credibility-weighted reception of professionally verified evidence, sustained successful participation, and confirmed moderation outcomes. A separate confidence measure indicates how much resolved behavioral history supports the estimate. Community reception is deliberately bounded below contribution quality so popularity cannot dominate professionally reviewed contribution history. The exact component weights and rank thresholds are TruthLens-specific calibration parameters and are validated through scenario, sensitivity, and adversarial testing. Trust Score represents Community reputation only and does not grant professional fact-checking authority, which remains governed through Partner Organizations.

This wording is stronger and more accurate than claiming that one paper directly defines the complete TruthLens formula.

---

# 22. Literature-to-TruthLens mapping

| Literature / source | Main idea relevant here | TruthLens relevance | Direct adoption? |
|---|---|---|---|
| Resnick et al. (2000), *Reputation Systems* | Reputation history helps establish trust and incentives | General rationale for Community reputation | Principle only |
| Ismail & Jøsang (2002), *The Beta Reputation System* | Beta-distribution aggregation of positive/negative feedback; forgetting | Bayesian-smoothed Contribution Quality; temporal-decay research question | Strong mathematical influence, with custom prior/cap |
| Kamvar et al. (2003), *EigenTrust* | Reputation-weighted trust aggregation; malicious collectives | Credibility-weighted voting and collusion concerns | Principle only |
| Jøsang et al. (2007), survey | Reputation as collaborative sanctioning/security mechanism; aggregation approaches | Multi-factor reputation and moderation outcomes | Principle only |
| Dellarocas (2000) | Unfair ratings and discriminatory feedback threaten predictive value | Need for bounded/manipulation-resistant feedback | Principle only |
| Hoffman et al., attack/defense survey | Attack taxonomy and defenses | Sybil/collusion/feedback threat model | Principle only |
| Swamynathan et al. (2010) | Collusion and short-lived identities harm reliability | Sybil/whitewashing validation | Principle only |
| Noorian & Ulieru (2010) | Context, reliability, honesty, adaptability | Keep Trust Score contextual; evaluate evidence reliability | Principle only |
| Friedman, Resnick & Sami (2011) | Whitewashing, feedback honesty, Sybil attacks | Adversarial validation plan | Principle only |
| Ziaie & Krcmar (2012) | Reputation and promotion in multi-tier communities | Rank/progression design | Principle only |
| Hendrikx et al. (2015) | Reputation taxonomy and context reference model | Define exactly what Truth Score means and where it applies | Principle only |
| Škorić et al. (2015) | Reputation with explicit uncertainty | Separate score from confidence | Principle only |
| Sänger & Pernul (2018) | Manipulation resistance vs transparency trade-off | Preserve understandable component breakdown | Principle only |
| Filippas et al. (2019/2022) | Reputation inflation can reduce informativeness | Do not make raw social ratings dominant | Principle only |
| Kokkodis (2021) | Dynamic, multidimensional, skill-specific reputation | Question context mixing and static history | Principle only |
| Rough et al. (2021/2023) | Competitive reputation can conflict with collaborative communities | Avoid excessive gamification and universal-status interpretation | Principle only |
| Hamilton & Cui (2024) | Old ratings can become stale | Evaluate decay/recency, do not assume it | Research question |

---

# 23. References

1. Resnick, P., Zeckhauser, R., Friedman, E., & Kuwabara, K. (2000). **Reputation Systems.** *Communications of the ACM, 43*(12), 45-48.  
   https://rzeckhauser.scholars.harvard.edu/publications/reputation-systems

2. Ismail, R., & Jøsang, A. (2002). **The Beta Reputation System.** BLED 2002 Proceedings.  
   https://aisel.aisnet.org/bled2002/41/  
   https://domino.fov.um.si/proceedings.nsf/Proceedings/D9E48B66F32A7DFFC1256E9F00355B37/

3. Kamvar, S. D., Schlosser, M. T., & Garcia-Molina, H. (2003). **The EigenTrust Algorithm for Reputation Management in P2P Networks.** WWW '03, 640-651.  
   https://doi.org/10.1145/775152.775242  
   https://archives.iw3c2.org/www2003/cdrom/papers/refereed/p446/p446-kamvar/index.html

4. Jøsang, A., Ismail, R., & Boyd, C. (2007). **A survey of trust and reputation systems for online service provision.** *Decision Support Systems, 43*(2), 618-644.  
   https://doi.org/10.1016/j.dss.2005.05.019

5. Dellarocas, C. (2000). **Mechanisms for Coping with Unfair Ratings and Discriminatory Behavior in Online Reputation Reporting Systems.** ICIS 2000 Proceedings.  
   https://aisel.aisnet.org/icis2000/52/

6. Hoffman, K., Zage, D., & Nita-Rotaru, C. **A Survey of Attack and Defense Techniques for Reputation Systems.** CERIAS, Purdue University.  
   https://www.cerias.purdue.edu/apps/reports_and_papers/view/3319

7. Swamynathan, G., Almeroth, K. C., & Zhao, B. Y. (2010). **The design of a reliable reputation system.** *Electronic Commerce Research, 10*, 239-270.  
   https://doi.org/10.1007/s10660-010-9064-y

8. Noorian, Z., & Ulieru, M. (2010). **The State of the Art in Trust and Reputation Systems: A Framework for Comparison.** *Journal of Theoretical and Applied Electronic Commerce Research, 5*(2), 97-117.  
   https://doi.org/10.4067/S0718-18762010000200007

9. Friedman, E., Resnick, P., & Sami, R. (2011). **Manipulation-Resistant Reputation Systems.** In *Algorithmic Game Theory*. Cambridge University Press.  
   https://www.cambridge.org/core/books/abs/algorithmic-game-theory/manipulationresistant-reputation-systems/13DBDA298DFFD00E6DA230C48267BBF1

10. Ziaie, P., & Krcmar, H. (2012). **Introducing a design framework for reputation systems in multi-tier production communities.** *Digital Creativity, 23*(2), 144-157.  
    https://doi.org/10.1080/14626268.2012.709946

11. Hendrikx, F., Bubendorfer, K., & Chard, R. (2015). **Reputation systems: A survey and taxonomy.** *Journal of Parallel and Distributed Computing, 75*, 184-197.  
    https://doi.org/10.1016/j.jpdc.2014.08.004

12. Škorić et al. (2015). **Flow-based reputation with uncertainty: evidence-based subjective logic.** *International Journal of Information Security.*  
    https://doi.org/10.1007/s10207-015-0298-5

13. Basheer, G. S., Ahmad, M. S., Tang, A. Y. C., & Graf, S. (2015). **Certainty, trust and evidence: Towards an integrative model of confidence in multi-agent systems.** *Computers in Human Behavior, 45*, 307-315.  
    https://doi.org/10.1016/j.chb.2014.12.030

14. Sänger, J., & Pernul, G. (2018). **Interactive Reputation Systems: How to Cope with Malicious Behavior in Feedback Mechanisms.** *Business & Information Systems Engineering, 60*, 273-287.  
    https://doi.org/10.1007/s12599-017-0493-1

15. Filippas, A., Horton, J. J., & Golden, J. M. (2019; published version 2022). **Reputation Inflation.**  
    https://www.nber.org/papers/w25857

16. Kokkodis, M. (2021). **Dynamic, Multidimensional, and Skillset-Specific Reputation Systems for Online Work.** *Information Systems Research.*  
    https://doi.org/10.1287/isre.2020.0972

17. Rough, D., De Paoli, S., & Wilson, A. (2021/2023). **Commonshare: A New Approach to Social Reputation for Online Collaborative Communities.** *Social Science Computer Review, 41*(1).  
    https://doi.org/10.1177/08944393211028191

18. Bellini et al. (2022). **Privacy-Preserving Reputation Systems Based on Blockchain and Other Cryptographic Building Blocks: A Survey.** *ACM Computing Surveys.*  
    https://doi.org/10.1145/3490236

19. Hamilton, M., & Cui, T. (2024). **Fresh Rating Systems: Structure, Incentives, and Fees.**  
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4875071

---

# Research conclusion

TruthLens does **not** need to replace its Trust Score with a published reputation algorithm in order to have a defensible research basis.

The current model already incorporates several principles with strong support in the computational-reputation literature:

- Bayesian smoothing of limited behavioral evidence;
- multiple evidence sources rather than one raw metric;
- reputation-weighted feedback;
- bounded community influence;
- separate treatment of negative moderation outcomes;
- sample-size-aware confidence;
- rank progression requiring both quality and behavioral history;
- explainability;
- contextual separation between Community reputation and professional authority.

The appropriate next step is therefore **calibration validation**, not wholesale redesign.

TruthLens must empirically test its own:

- component weights;
- caps;
- nonlinear scaling constant;
- rank thresholds;
- action eligibility rules;
- resistance to coordinated manipulation;
- temporal behavior.

The strongest defensible position is:

> The architecture is research-informed; the calibration is TruthLens-specific and empirically validated.

That distinction should remain explicit in implementation documentation, the capstone manuscript, and oral defense.
