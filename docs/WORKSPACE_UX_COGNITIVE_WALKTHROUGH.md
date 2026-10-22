# Verification Workspace Cognitive Walkthrough

Issue: #129 — WORKSPACE-UX-1 Guided Investigation Workflow

Baseline: `main@c78a9ad155baf7b95c6b30b3b97c619fffb17391`

## Purpose

Use this document to compare the current Workspace with the redesigned branch from the perspective of a first-time Partner Organization member.

For each task/action, answer:

1. Will the user form the correct goal?
2. Will the user notice the correct action?
3. Will the user associate that action with the desired outcome?
4. After acting, will the user understand what happened and what to do next?

Record observable failures rather than only subjective aesthetic reactions.

---

## Persona / context

Representative first-time user:
- authenticated TruthLens user;
- active Partner Organization membership;
- authorized for the task under test;
- understands professional fact-checking at a domain level;
- has not been trained on the internal architecture of TruthLens.

Do not assume knowledge of capability constants, internal module names, or backend lifecycle implementation.

---

## Scenario A — Enter and orient

Task:
> Enter the Verification Workspace and determine what work needs your attention.

Record:
- first click from the main app;
- first Workspace destination noticed;
- whether organization context is understood;
- whether role/authority is understood;
- whether user can explain what the Workspace is for;
- wrong-section visits;
- questions/help needed.

Current-state hypothesis:
- "Available tools" exposes software sections but may not make the current work queue/priority obvious.

Redesign acceptance:
- user identifies a work-oriented starting point without instruction;
- user can state which organization and work context they are operating under.

---

## Scenario B — Find and evaluate available work

Task:
> Find a claim/investigation available to your organization and decide whether to claim it.

Record:
- ability to find Intake;
- whether available status is understood;
- whether AI assessment is mistaken for institutional truth/authority;
- whether claim/context links are sufficient;
- whether claiming consequence is understood.

Redesign acceptance:
- Intake is discoverable from the primary work model;
- action language communicates what claiming does.

---

## Scenario C — Claim and continue

Task:
> Claim the investigation, then continue working on it.

Record:
- feedback after claim;
- whether user knows where the item moved;
- whether user can open it without searching another unrelated section;
- time/clicks from successful claim to investigation work surface;
- wrong turns/backtracking.

Current-state finding:
- intake currently removes the claimed item and reports that it is now in Organization Workload, but does not directly open the investigation.

Redesign acceptance:
- success state provides an immediate continuation;
- ideally transition directly to canonical investigation work context or expose one dominant `Open investigation` action;
- user does not need to remember "Organization Workload" as an architectural destination.

---

## Scenario D — Understand investigation state

Task:
> Explain the current state of this investigation and what must happen before it can progress.

Ask user:
- Where are you?
- What stage is this?
- What has already happened?
- What is blocked/pending?
- What should you do next?

Redesign acceptance:
- answers can be derived directly from the work surface;
- no external explanation required;
- no implication that the lifecycle is strictly linear when it is not.

---

## Scenario E — Review evidence

Task:
> Review the evidence that currently needs attention for this investigation.

Record:
- whether user can move from investigation context to required evidence without losing case identity;
- whether evidence status/action is clear;
- whether rejection/acceptance consequences are understandable;
- whether user can return to the investigation.

Redesign acceptance:
- case identity remains visible or recoverable;
- evidence review feels like work within/for the investigation rather than a disconnected global tool.

---

## Scenario F — Determine adjudication readiness

Task:
> Determine whether the investigation is ready for adjudication and, if authorized, continue.

Record:
- whether readiness/blockers are visible;
- whether the user confuses AI verdict with human adjudication;
- whether required evidence state is understood;
- whether unauthorized roles receive understandable status instead of dead controls.

Redesign acceptance:
- next action derives from real persisted state/capabilities;
- no frontend-fabricated authority.

---

## Scenario G — Draft / publish handoff

Task:
> After an authoritative decision exists, find the next publication-related work.

Record:
- continuity of investigation identity;
- whether Drafting/Publishing are understood as later work states;
- whether institutional authority and current actor responsibilities remain clear.

Redesign acceptance:
- transition is contextual and comprehensible;
- publication does not appear to be equivalent to AI output or ordinary evidence review.

---

## Scenario H — Leave and resume

Task:
> Leave the Workspace, then return to the same investigation.

Record:
- whether browser Back behaves predictably;
- whether refresh preserves meaningful context;
- whether a direct URL can reopen the work;
- whether user can find active work again without remembering the previous tool.

Redesign acceptance:
- canonical route/deep link exists for meaningful investigation work;
- refresh and navigation preserve coherent state.

---

## Scenario I — Distinguish administration from verification

Task:
> Add/manage an organization member or change organization public/specialization settings, then return to factual-verification work.

Record:
- whether user understands that this is organization administration rather than an investigation step;
- whether return path is clear;
- whether platform-controlled vs organization-controlled authority is understandable.

Redesign acceptance:
- administration and factual verification are visibly/conceptually distinct;
- moving between them does not imply shared authority semantics.

---

## Observation sheet

For each scenario record:

| Measure | Observation |
|---|---|
| First action/click | |
| Correct first click? | |
| Completion without help? | |
| Time to core action | |
| Wrong-section visits | |
| Backtracks | |
| Help/questions | |
| Error recovery | |
| Can answer "Where am I?" | |
| Can answer "What happens next?" | |
| Notes | |

---

## Acceptance principle

Do not accept the redesign merely because it looks cleaner.

The redesigned flow should materially reduce:
- navigation guessing;
- memory burden;
- wrong-section visits;
- backtracking;
- "where did it go?" moments;
- "what do I do next?" moments.

A first-time Partner Organization member should be able to complete the representative investigation flow using domain knowledge, not TruthLens architectural knowledge.
