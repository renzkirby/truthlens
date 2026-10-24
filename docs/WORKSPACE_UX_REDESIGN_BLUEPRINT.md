# Verification Workspace — UI Redesign Blueprint

Issue: #129 WORKSPACE-UX-1

This blueprint translates the HCI research into an implementable TruthLens workbench redesign.

## 1. Design objective

Preserve the full professional record while ensuring the Partner user sees only the level of detail needed for the current decision by default.

The redesign is **not** a visual rebrand.

It should reuse:
- TruthLens colors/tokens;
- Mona Sans / existing typography;
- existing backend authority model;
- existing evidence/adjudication/publication services;
- existing provenance and audit records.

## 2. Workspace shell

Restore the preferred workflow grouping:

```
Investigation work
  Intake
  Investigations
  Evidence Review
  Adjudication

Publication
  Drafting
  Publishing
  Publications
  Factual Corrections

Organization & insights
  Analytics
  Accountability
```

Evidence Review and Adjudication remain visible because Partner users understand them as meaningful verification activities. However:
- `Investigations` remains the recommended guided path;
- global Evidence Review / Adjudication are broader work queues;
- their pages should make their queue role explicit without renaming the sidebar labels.

## 3. Density model: three information tiers

### Tier 1 — Always visible / decision-critical
- claim/case identity;
- current stage;
- readiness/status;
- one critical blocker;
- primary next action;
- concise evidence counts;
- current authoritative decision state;
- organization/role.

### Tier 2 — Visible summary, expandable detail
- evidence items;
- claim context;
- readiness requirements;
- decision rationale;
- current publication status;
- Verification Intelligence summary.

### Tier 3 — Details on demand
- technical provenance;
- IDs;
- full case metadata;
- complete event/audit history;
- historical decision revisions;
- verbose source metadata;
- raw/secondary contextual fields.

No Tier 3 content should dominate the default work surface.

## 4. Investigation page structure

Desktop:

```
┌─────────────────────────────────────────────────────────────────┐
│ CASE OVERVIEW                                                   │
│ Claim · org · status · stage · owner · context actions          │
└─────────────────────────────────────────────────────────────────┘

┌───────────────────┬─────────────────────────────────────────────┐
│ STAGE / PROGRESS  │ CURRENT WORK                                │
│                   │                                             │
│ Evidence       ✓  │ Current task heading                        │
│ Adjudication   ●  │ concise task explanation                    │
│ Drafting       ○  │                                             │
│ Publication    ○  │ primary information/action                  │
│                   │                                             │
│ blocker/next      │ secondary sections disclosed as needed      │
└───────────────────┴─────────────────────────────────────────────┘

Context/provenance → optional drawer / side panel
```

This is a workbench, not a dashboard-card grid.

## 5. Stage rail

Use a compact lifecycle/orientation rail, not a wizard.

Each stage shows:
- label;
- state icon/text;
- optional short count/attention cue.

Example:

```
Investigation
Evidence review       Complete
Adjudication          Needs attention
Drafting              Not started
Publication           Not started
```

The stage rail must support revision/return states rather than imply irreversible linear completion.

## 6. Evidence Review redesign

Default guided view should show:

### Header
- Evidence Review
- current case identity
- status
- why review is needed

### Primary review unit
- submitted evidence text/caption;
- source link/domain;
- contributor;
- evidence type;
- current disposition;
- Verify / Reject decision controls.

### Supporting context
Collapsed/compact by default:
- claim context;
- thread;
- detailed evidence metadata.

### History
Collapsed by default after resolution:
- prior disposition;
- moderator notes;
- case events.

Once a decision is recorded:
- replace the decision form with a compact outcome confirmation;
- offer Continue investigation immediately.

Do not leave a resolved evidence case displaying the same visual density as an active case.

## 7. Adjudication redesign

Current Adjudication is the strongest example of information overload.

Default selected-case layout should show:

### A. Decision summary bar
- claim;
- current case status;
- evidence readiness;
- primary blocker or "Ready";
- authorized action.

### B. Evidence digest
Do not render all evidence records expanded.

Show:
- total / verified / rejected / unreviewed;
- 3–5 compact evidence rows or a sortable list;
- status + source + concise caption;
- expand a single evidence item on demand.

### C. Decision workspace
When ready:
- canonical claim;
- verdict control;
- rationale;
- explicit authority warning where needed;
- primary Record decision action.

When blocked:
- show the one blocking reason first;
- secondary blockers under "Other requirements".

### D. Context drawer
Optional:
- Verification Intelligence;
- detailed case metadata;
- provenance.

### E. History accordion
Collapsed by default:
- decision history;
- resolution history;
- case events;
- technical IDs.

## 8. White-space policy

Whitespace is semantic.

Use smaller spacing **within** a section and larger spacing **between** sections.

Avoid:
- large empty columns created because adjacent content has different heights;
- multiple full-width blank bands;
- every subsection becoming its own large card;
- nesting bordered cards inside bordered cards without hierarchy.

Prefer:
- section dividers;
- subtle background shifts;
- consistent vertical rhythm;
- alignment to a shared grid.

## 9. Cards and boundaries

Use a card/surface only when it represents a meaningful independent region.

Suggested surface hierarchy:
1. Page/case surface.
2. Current work surface.
3. Optional callout/alert.
4. Inline sub-sections separated by headings/dividers.

Do not wrap every metadata group in a card.

## 10. Typography / scan hierarchy

Recommended relative hierarchy:
- claim/case title: strongest;
- current task/stage title: strong;
- section title: medium;
- field label: quiet uppercase/compact;
- value: normal/high contrast;
- explanation/help: muted;
- technical metadata: quietest.

Long explanatory paragraphs should not appear repeatedly when a short label/caption can carry the same meaning.

## 11. Sticky orientation

On long Evidence/Adjudication pages, retain a compact sticky case bar after the full header scrolls away:

```
Claim: Philippine congressmen...
Adjudication · Ready
[Back to investigation]          [Record decision]
```

This prevents the user from losing case identity and next action during long evidence review.

Do not make large headers sticky.

## 12. Queue + selected work behavior

For global Evidence Review / Adjudication:
- master-detail is appropriate;
- queue list is compact;
- selected work gets most width;
- contextual side panel is optional;
- at narrower widths, queue becomes a separate list screen or drawer.

Avoid permanent three-column layouts when they make the primary work column too narrow.

## 13. Responsive behavior

Wide desktop:
- queue / work;
- context optionally opens as drawer or third region if sufficient width.

Medium desktop/tablet:
- queue collapsible;
- work full width;
- context overlay/drawer.

Mobile:
- queue → detail sequential navigation;
- sticky compact case/action bar;
- disclosure panels stacked;
- no squeezed three-column layout.

## 14. Feedback

Consequential actions:
- local status immediately next to action;
- visible state changes in place;
- success does not require scrolling;
- next action/Continue investigation follows outcome.

Global toast/banner may supplement but never replace action-local feedback.

## 15. Validation metrics

Add to manual usability evaluation:
- NASA-TLX or a lightweight mental-effort item after representative workflows;
- number of expanded sections before decision;
- number of scroll reversals;
- time to find primary blocker;
- time to identify next action;
- evidence-item lookup time;
- first-click correctness;
- wrong-section visits;
- task completion without help.

Compare current baseline against redesigned build.
