# WORKSPACE-UX-1 Target Architecture

Issue: #129 — Guided Investigation Workflow

Status: approved implementation direction, derived from repository audit on `main@c78a9ad155baf7b95c6b30b3b97c619fffb17391`.

## 1. Decision

The redesign will be **investigation-centered**, not capability-tool-centered.

The existing backend authorization model remains authoritative. The frontend should translate that model into task-oriented workflow guidance rather than exposing capability modules as the user's mental model.

The existing `verification_intelligence` contract will **not** be repurposed for next-action guidance.

Reason:
- it is intentionally non-authoritative support context;
- its schema is locked at `1.0`;
- hardening tests prohibit recommendation/verdict-advice semantics;
- existing consumers depend on its stable evidence/provenance contract.

Instead, introduce a separate read-only **Investigation Workspace projection** for operational state/orientation.

---

## 2. Existing persisted sources of truth

The new projection should compose existing state rather than create a new workflow table.

### Assignment

`VerificationAssignment`

Relevant states:
- `AVAILABLE`
- `ACTIVE`
- `RELEASED`
- `COMPLETED`

The investigation work surface operates on an organization-owned `ACTIVE` assignment.

### Human evidence

`EvidenceSubmission`

Relevant states:
- `UNVERIFIED`
- `VERIFIED`
- `REJECTED`

Relevant derived facts:
- total submissions;
- unreviewed submissions;
- reviewed/verified submissions;
- rejected submissions.

### Evidence moderation

`ModerationCase(case_type=EVIDENCE)`

Relevant derived fact:
- active evidence cases for the claim.

### Adjudication

`ModerationCase(case_type=ADJUDICATION)`

The adjudication service already defines important blockers:
- no active assignment;
- assignment organization changed;
- no evidence;
- unreviewed evidence;
- active evidence case;
- direct contribution conflict;
- current/historical decision conflicts;
- resolved/cancelled/reopened case states.

### Authoritative decision

`AdjudicationDecision`

Only attributable current human adjudication may represent authoritative human judgment.

### Publication

`OfficialFactCheck`

Relevant states:
- `DRAFT`
- `IN_REVIEW`
- `PUBLISHED`
- `ARCHIVED`

The publication query service already exposes:
- blockers;
- allowed actions;
- sealed decision evidence;
- lifecycle timestamps;
- concurrency state.

### Supporting context

`verification_intelligence`

Keep as a separate context/evidence/provenance surface. It may be displayed from the Investigation work surface as optional context, but it must not become the source of workflow authority.

---

## 3. New read model

Proposed service:

`api/investigation_workspace_service.py`

Proposed endpoint:

`GET /api/verification/investigations/<assignment_id>/`

Required organization scope:
`?organization_id=<uuid>`

The endpoint is:
- read-only;
- deterministic;
- provider-free;
- side-effect free;
- organization-scoped;
- capability-aware;
- based only on persisted workflow facts.

No migration should be required for the first implementation.

---

## 4. Response responsibilities

The projection should answer four separate questions.

### Identity

- assignment id;
- claim id / claim text / type;
- organization;
- claimed by / claimed at.

### Current state

A user-facing state descriptor derived from persisted records.

Candidate state codes:

- `ACTIVE_NO_EVIDENCE`
- `EVIDENCE_REVIEW`
- `ADJUDICATION_READY`
- `ADJUDICATION`
- `DRAFTING_READY`
- `DRAFTING`
- `PUBLICATION_REVIEW`
- `COMPLETED` (for future history route; active endpoint may initially exclude it)

These are presentation/read-model states, **not new database lifecycle states**.

### Blockers / pending work

Structured, factual blockers such as:
- no evidence submitted;
- evidence awaiting review;
- active evidence cases;
- adjudication blocked;
- draft incomplete;
- publication review pending.

Do not transform absence of permission into a factual workflow blocker. Permission affects actor actions, not the underlying case state.

### Allowed actor actions

Actions should describe operations the current actor is authorized and structurally able to perform.

Examples:
- `REVIEW_EVIDENCE`
- `ADJUDICATE`
- `CREATE_DRAFT`
- `CONTINUE_DRAFT`
- `REVIEW_PUBLICATION`
- `VIEW_PUBLICATION`
- `RELEASE_INVESTIGATION` where release remains valid.

These are **workflow actions**, not verdict recommendations.

They must never suggest a factual verdict.

---

## 5. State derivation

State precedence should follow the most advanced persisted authoritative workflow state, without pretending every case is strictly linear.

Candidate initial derivation:

1. If active publication work exists:
   - DRAFT → `DRAFTING`
   - IN_REVIEW → `PUBLICATION_REVIEW`

2. Else if a current attributable adjudication decision exists:
   - `DRAFTING_READY`

3. Else if an adjudication case exists:
   - `ADJUDICATION`

4. Else if human evidence exists:
   - if any evidence is unreviewed or active evidence cases exist:
     `EVIDENCE_REVIEW`
   - else:
     `ADJUDICATION_READY`

5. Else:
   - `ACTIVE_NO_EVIDENCE`

This order is a read projection only. It must be validated against services/tests before final acceptance.

Do not label a case "completed" until the assignment/publication workflow actually establishes completion.

---

## 6. Next-action selection

The UI may emphasize one **primary allowed action**, but the server should preferably return an ordered set of allowed actions plus reasons/blockers.

Example:

```json
{
  "state": {
    "code": "EVIDENCE_REVIEW",
    "label": "Evidence review",
    "detail": "2 submitted evidence items still require review."
  },
  "pending": [
    {
      "code": "UNREVIEWED_EVIDENCE",
      "count": 2,
      "detail": "Every submitted evidence item must be reviewed before adjudication."
    }
  ],
  "allowed_actions": [
    {
      "code": "REVIEW_EVIDENCE",
      "label": "Review evidence"
    }
  ]
}
```

For an actor lacking Evidence Review authority, the state remains `EVIDENCE_REVIEW`, but `REVIEW_EVIDENCE` is absent. The UI can say the case is waiting for an authorized reviewer rather than showing a dead button.

---

## 7. Investigation route

Canonical frontend route:

`/workspace/investigations/:assignmentId?organization_id=<uuid>`

This route should become the stable context immediately after claiming work.

It should support:
- refresh;
- Back/Forward;
- direct links;
- notification handoff;
- return-to-work;
- organization authorization checks.

The claim success flow should navigate here directly or expose one dominant `Open investigation` action if direct navigation would interrupt necessary confirmation behavior.

---

## 8. Initial work surface

The first implementation does not need to embed every existing editor immediately.

Minimum work surface:

### Header / orientation

- organization;
- investigation status;
- claim;
- claimed by / claimed date where appropriate.

### Current state

- state label;
- concise factual explanation;
- pending/blocking work.

### Primary action

- one emphasized authorized action when available;
- no fabricated action when another role must act.

### Context

- evidence summary;
- adjudication summary;
- publication summary;
- optional Verification Intelligence link/panel;
- community/source context links.

This establishes the mental model before migrating every stage editor into the same screen.

---

## 9. Incremental migration of current top-level tools

Phase A:
- canonical Intake route;
- canonical Investigations list route;
- Investigation detail route;
- claim → investigation handoff;
- state/next-action read model.

Phase B:
- make Evidence Review accept/open a specific investigation/claim context;
- make Adjudication accept/open the corresponding case directly;
- preserve investigation identity while transitioning.

Phase C:
- contextualize Drafting and Publishing;
- reduce redundant top-level peer navigation.

Phase D:
- remove or demote obsolete capability-oriented navigation once equivalent deep links and workflows are stable.

This avoids a big-bang rewrite.

---

## 10. Primary navigation target

Candidate:

```
Work
  Investigations
  Intake

Publication
  Publications
  Corrections

Insights
  Analytics
  Accountability
```

Organization administration is not an investigation stage. Larger cross-surface administration/governance clarification is tracked in #141.

During incremental migration, legacy Evidence Review / Adjudication / Drafting / Publishing destinations may remain temporarily available for compatibility, but the redesigned flow should stop teaching users that these are unrelated tools.

---

## 11. Accessibility / responsive requirements

- semantic heading hierarchy;
- visible focus;
- keyboard-operable queue/detail/action controls;
- status communicated with text, not color alone;
- live-region feedback for claim/action transitions where appropriate;
- no hover-only actions;
- narrow screens use sequential queue/detail/context views;
- desktop may use queue + work surface + optional context;
- reduced motion honored;
- Back behavior predictable.

---

## 12. Security/governance invariants

The read model must not:
- expose organization work across organizations;
- infer authority from descriptive profile/expertise fields;
- transfer AI verdict authority to human adjudication;
- expose private provider payloads;
- create/update workflow records;
- issue provider calls;
- fabricate blockers or lifecycle completion;
- bypass existing capability checks;
- weaken evidence/adjudication/publication concurrency safeguards.

---

## 13. Test plan

Backend:
- authorization by organization and capability;
- wrong organization → not found/forbidden without leakage;
- active assignment required;
- each state derivation;
- unreviewed evidence counts;
- active evidence case blocker;
- adjudication state;
- current decision → drafting-ready;
- draft → drafting;
- in-review → publication-review;
- actor-specific allowed actions;
- no verdict recommendation/advice fields;
- deterministic read/no writes/no provider calls.

Frontend:
- canonical routes;
- claim success navigation;
- direct investigation URL;
- refresh identity;
- back/forward behavior where testable;
- loading/error/not-found/permission states;
- state and pending work rendering;
- no unauthorized action button;
- responsive/keyboard behavior.

Regression:
- existing Verification Intelligence schema remains exactly `1.0`;
- existing evidence/adjudication/publication workflows remain authoritative.
