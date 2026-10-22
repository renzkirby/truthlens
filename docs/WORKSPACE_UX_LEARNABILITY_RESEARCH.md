# Verification Workspace Learnability & Interaction Research

Status: approved design/research basis for WORKSPACE-UX-1 (#129)

## Purpose

This document captures the research basis and repository findings used to redesign the TruthLens Verification Workspace for improved learnability, intuitiveness, orientation, and first-time Partner Organization use.

It is intentionally durable project documentation so implementation decisions can be checked against the same rationale later.

This document does **not** replace `DESIGN.md`. TruthLens domain semantics, authority boundaries, provenance rules, and the approved product design brief remain higher-priority constraints.

---

## 1. Evaluator finding

The capstone evaluator criticized the intuitiveness and process clarity of the administrative/operational side of TruthLens, especially the Verification Workspace. The concern is that Partner Organizations may find the system difficult to learn and the workflow difficult to understand without prior instruction.

This is treated as a structural interaction-design problem, not merely a styling problem.

The main question is:

> Can a first-time Partner Organization member understand where they are, what has happened in an investigation, and what they should do next without learning TruthLens's internal architecture first?

---

## 2. Relevant quality concepts

### ISO/IEC 25010

Use the exact terminology from the ISO/IEC 25010 edition declared by the capstone evaluation instrument when writing the thesis/report.

The current ISO/IEC 25010:2023 model uses **Interaction Capability** and includes concepts directly relevant to this work, including:
- appropriateness recognizability;
- learnability;
- operability;
- user assistance;
- self-descriptiveness.

For TruthLens, the practical interpretation is:
- users should be able to recognize what a Workspace function is for;
- learn common workflows in an expected amount of time;
- operate the workflow without unnecessary complexity;
- receive help/context where the task requires it;
- infer how to use the system from the interface itself rather than external training.

Reference:
- ISO/IEC 25010:2023 overview/catalog: https://www.iso.org/standard/78176.html
- ITeh catalog summary: https://www.iteh.eu/catalog/standards/iso/8c5bd63e-9e67-4b55-90e3-8cb2b10a2030/iso-iec-25010-2023

### ISO 9241-11

ISO 9241-11 frames usability in terms of specified users achieving specified goals with effectiveness, efficiency, and satisfaction in a specified context of use.

Reference:
- https://www.iso.org/standard/63500.html

### ISO 9241-110

ISO 9241-110 interaction principles are particularly relevant because the Workspace should be organized around the user's task rather than exposing implementation structure.

Relevant principles include:
- suitability for the user's tasks;
- self-descriptiveness;
- conformity with user expectations;
- learnability;
- controllability;
- robustness against use error;
- user engagement.

Reference/catalog:
- https://www.iso.org/standard/75258.html
- https://www.iteh.fr/catalog/standards/cen/7cfeb7e3-9a82-44af-871c-116631d1d051/en-iso-9241-110-2020

---

## 3. Established usability principles applied to TruthLens

### Visibility of system status

After a consequential action, users should understand what the system did.

TruthLens implication:
- after claiming an investigation, do not only remove the item and show a generic success notice;
- show where the investigation now lives and provide the next action.

### Match between system and the real world

Interfaces should use concepts from the user's task/domain rather than internal implementation terminology where possible.

TruthLens implication:
- the Partner user thinks in terms of investigations, evidence, decisions, drafts, and publications;
- they should not have to infer a process from a list of software capability modules.

### Recognition rather than recall

Users should not be required to remember information or workflow position from one view while navigating another.

TruthLens implication:
- investigation identity, current stage, blockers, and next action should travel with the task;
- Evidence Review and Adjudication should not require the user to remember which previous list item they were working on.

### User control and freedom

Back/Forward, cancellation, return-to-work, and error recovery should remain predictable.

TruthLens implication:
- meaningful Workspace views should use durable URL state;
- refresh and browser navigation should preserve sensible context.

### Help users recognize, diagnose, and recover from errors

Errors should explain the problem and recovery action.

TruthLens implication:
- claim conflicts, unavailable work, stale state, failed requests, and authorization changes should lead to a clear next step.

Reference:
- Nielsen Norman Group, Ten Usability Heuristics:
  https://www.nngroup.com/articles/ten-usability-heuristics/

---

## 4. Cognitive walkthrough as the primary learnability method

A cognitive walkthrough is particularly appropriate because the evaluator concern is first-time learnability.

For each representative task, examine whether a first-time user can:
1. form the correct goal;
2. discover the correct action;
3. associate the action with the desired outcome;
4. understand the feedback after acting.

TruthLens should perform this walkthrough on the current implementation before redesign acceptance and repeat the same scenarios on the redesign.

Reference:
- Nielsen Norman Group, Cognitive Walkthroughs:
  https://www.nngroup.com/articles/cognitive-walkthroughs/

---

## 5. W3C cognitive accessibility guidance

Relevant W3C guidance emphasizes:
- clear hierarchy;
- easily found important actions;
- understandable steps/process position;
- instructions placed close to the activity;
- recognizable page/region purpose;
- reducing memory burden.

TruthLens implication:
- distinguish general process education from current-case status;
- show completed/current/pending investigation work;
- expose immediate instructions or blockers near the work itself.

References:
- Clear Steps:
  https://www.w3.org/WAI/WCAG2/supplemental/patterns/o1p04-clear-steps/
- Findable / orientation objective:
  https://www.w3.org/WAI/WCAG2/supplemental/objectives/o2-find/

---

## 6. Process indicator vs. workflow state

TruthLens verification is not always a strictly linear wizard.

Possible branches include:
- more evidence requested;
- evidence rejected/replaced;
- adjudication revision;
- drafting revision;
- publication;
- later factual correction.

Therefore:
- a static **process map** may teach the general workflow;
- a **case status/lifecycle view** should explain the current investigation;
- a **next-action control** should guide the user now.

Do not force legitimate branching into a fake `Step 1 → Step 2 → Step 3` wizard.

USWDS explicitly recommends its step indicator for linear progression and a different pattern for conditional/nonlinear processes.

References:
- USWDS Step Indicator:
  https://designsystem.digital.gov/components/step-indicator/
- USWDS Process List:
  https://designsystem.digital.gov/components/process-list/

---

## 7. Repository findings on current main

Baseline inspected: `c78a9ad155baf7b95c6b30b3b97c619fffb17391`

### 7.1 Workspace is capability-oriented

`WorkspacePage.jsx` exposes peer sections including:
- Verification Intake;
- Organization Workload;
- Evidence Review;
- Adjudication;
- Drafting;
- Publishing;
- Publications;
- Factual Corrections;
- Organization;
- Analytics;
- Accountability.

The sidebar itself is labeled **Available tools**.

This is technically faithful to the capability model but makes the user reconstruct the end-to-end verification workflow mentally.

### 7.2 Claiming work produces a state change but weak continuation

`VerificationIntakePanel.jsx`:
- claims the assignment;
- removes it from intake;
- displays a notice saying it is now part of Organization Workload.

It does not open the investigation or expose a dominant `Open investigation` continuation action.

This exactly matches the original #129 concern.

### 7.3 Workload is a list, not yet a durable investigation work context

`OrganizationWorkloadPanel.jsx` displays active assignments and context links, but the work item does not become a canonical investigation-centered route/work surface.

### 7.4 Most Workspace sections are local state under one URL

Outside factual corrections, `WorkspacePage.jsx` selects sections using `requestedSectionId`.

This weakens:
- refresh continuity;
- browser Back/Forward semantics;
- bookmarking;
- direct links;
- notification handoff;
- orientation.

A user can be in Evidence Review or Adjudication while the URL still primarily says `/workspace`.

### 7.5 Design brief and implementation are misaligned

`DESIGN.md` already specifies the preferred workbench mental model:

- Queue — What needs my attention?
- Work surface — What am I evaluating/deciding/drafting/publishing?
- Context — What evidence/provenance/history/context do I need without leaving the task?

Candidate composition:

`queue | primary work surface | optional contextual drawer/panel`

This means the redesign can be framed as implementing the approved TruthLens design direction rather than inventing a new visual identity.

### 7.6 Organization administration is mixed with factual work

The Workspace exposes an `Organization` section beside factual verification tools.

That section itself contains:
- Members & invitations;
- Public presence;
- Verification scope.

These are administrative tasks, not investigation steps.

The backend authority separation is sound, but the frontend hierarchy makes factual work and organization administration feel like peer parts of one workflow.

### 7.7 Management Console is structurally stronger

The platform Management Console already uses canonical routes and a persistent shell:
- `/management`
- `/management/pipeline`
- `/management/organizations`
- `/management/memberships`
- `/management/invitations`
- `/management/audit`

Its main remaining learnability problem is clearer framing of authority:
- TruthLens/platform-controlled governance;
- Partner Organization-controlled administration.

That work is tracked separately from #129 to keep the Guided Investigation branch bounded.

---

## 8. Target TruthLens mental model

### Primary object: Investigation

The central object should be the investigation/work item, not the list of software tools.

A user opening an investigation should quickly see:
- claim;
- organization;
- assignment/status;
- current stage;
- blockers/pending work;
- next action;
- evidence/context/history as authorized.

### Three immediate questions

The interface should answer:

**Where am I?**
- organization;
- investigation;
- current stage/status.

**What happened?**
- completed work;
- pending work;
- blockers.

**What next?**
- the user's next meaningful authorized action.

### Backend vs frontend responsibility

Backend model:
> What is this person authorized to do?

Frontend model:
> What does this person need to do now?

The frontend must not invent authority, but it should translate capabilities into a task-oriented experience.

---

## 9. Candidate information architecture

Candidate primary Workspace structure:

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

Evaluate Evidence Review, Adjudication, Drafting, and Publishing as investigation-context stages/actions instead of automatically preserving them as top-level peer tools.

### Administration

Treat organization administration as a distinct secondary environment/purpose:

```
Verification Workspace
  Do verification work

Organization Administration
  Manage our organization

Management Console / Platform Governance
  TruthLens manages institutional participation
```

The interfaces may share TruthLens visual foundations while communicating clearly different authority/purpose.

---

## 10. Candidate routing model

Validate a route structure along these lines:

```
/workspace
/workspace/intake
/workspace/investigations
/workspace/investigations/:assignmentId
/workspace/publications
/workspace/factual-corrections
/workspace/factual-corrections/:requestId
```

Benefits:
- meaningful Back/Forward;
- refresh continuity;
- bookmarks;
- direct queue-to-case handoff;
- notification links;
- resumable work;
- easier testing/debugging.

Do not finalize identifiers until the backend assignment/investigation domain model is audited.

---

## 11. UI UX Pro Max assessment

Repository:
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

The inspected skill is useful as a design-intelligence/checklist layer. Its guidance prioritizes:
- accessibility;
- interaction feedback;
- responsive layout;
- forms/feedback;
- navigation hierarchy;
- active-state visibility;
- Back behavior;
- deep linking;
- progressive disclosure.

It also contains React-specific implementation guidance and a searchable UX-rule dataset.

### Correct precedence for TruthLens

Use:

```
TruthLens domain/authority model
  ↓
TruthLens DESIGN.md
  ↓
UX/HCI research + evaluator findings
  ↓
UI UX Pro Max recommendations
  ↓
Implementation
```

Do **not** use:

```
UI UX Pro Max
  ↓
replace TruthLens identity/domain semantics
```

Do not persist/generated-overwrite a new product design system over existing TruthLens rules without separate approval.

---

## 12. Learnability acceptance measures

For a bounded manual acceptance session, track:

- first-click correctness;
- unassisted completion;
- time to core task;
- wrong-section visits;
- backtracking;
- help requests;
- recoverability from conflict/error;
- ability to answer `Where am I?`;
- ability to answer `What happens next?`;
- repeated-task improvement.

These are practical signals for the evaluator concern. They should supplement, not replace, any formal capstone questionnaire/statistical protocol.

---

## 13. Implementation guardrails

Preserve:
- backend authorization/capabilities;
- institutional/human/AI authority distinctions;
- evidence provenance;
- accountability;
- factual-correction semantics;
- unsaved-work protections;
- accessible keyboard/focus behavior;
- reduced-motion support;
- responsive professional-workbench behavior;
- canonical TruthLens design tokens.

Avoid:
- exposing architecture as user workflow;
- rigid wizardification;
- giant dashboard-card grids as a substitute for information architecture;
- cards inside cards;
- hover-only discoverability;
- a visual rebrand disguised as usability remediation;
- frontend-only fabricated lifecycle state.

If the current backend cannot reliably answer `current stage / blockers / next action`, introduce a bounded read model/API rather than guessing in React.

---

## 14. Working design principle

> A Partner Organization member should not need to understand the architecture of TruthLens in order to conduct an investigation. TruthLens should expose the investigation, its current state, and the user's next meaningful action; the underlying modules and capabilities should remain implementation details.
