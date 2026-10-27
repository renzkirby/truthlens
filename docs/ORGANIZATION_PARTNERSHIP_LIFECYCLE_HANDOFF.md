# TruthLens Organization Partnership Lifecycle — Working Context & Handoff

> Living project context for branch `feat/organization-partnership-lifecycle`.
>
> Created: 2026-10-27
>
> Baseline at creation: `main` = `b57c84349bdff3e5b9a846043de012b736a59cbf`
>
> Status: **Impact audit / regression checkpoint. No lifecycle behavior change has been implemented yet.**

## Purpose

This document preserves the reasoning, accepted product decisions, production findings, implementation constraints, and next steps for the Organization Partnership Lifecycle phase.

The phase was opened after an evaluator-created organization, **CSG**, was changed to `UNVERIFIED + NONE` but its memberships remained current. Ordinary factual roles lost Verification Workspace authority, while the active Organization Admin still retained `MANAGE_ORGANIZATION` and could enter the Workspace. Those still-current memberships also prevented members from accepting an invitation to a different Partner Organization because TruthLens enforces one current Partner Organization membership per user.

The resulting conclusion is that platform governance should model **explicit organization lifecycle transitions**, not expose raw verification/partner status fields as independent editable database values.

---

## Branch and workflow

Current feature branch:

```text
feat/organization-partnership-lifecycle
```

The branch was created from current `main` after PR #152 (Platform Governance / Safety Review) was merged.

Repository workflow rules:

- Direct implementation and commits/pushes on the feature branch are authorized.
- GitHub Issues/progress comments are allowed.
- **Do not create a PR or merge without explicit user authorization.**
- Preserve isolated checkpoints and tests before review.
- Production frontend may deploy automatically from `main`; backend deployment is separate.

---

## Accepted product model

### Core lifecycle principle

> **Ending a partnership ends future authority, not historical authorship or provenance.**

A former Partner Organization must lose future operational authority while all completed authoritative work remains intact.

### Completed work that must be retained

The following must remain preserved and attributable to the organization and individual actors who produced them:

- adjudication decisions;
- published Official Fact Checks;
- evidence assessments/reviews;
- completed verification assignments;
- publication snapshots and factual-correction lineage;
- accountability/audit history;
- individual reviewer/author/publisher attribution;
- organization attribution at the time the work was produced.

Membership later becoming `LEFT`, or an organization becoming a former partner, must **not** erase authorship/provenance.

Published fact-checks may continue to be referenced by the verification pipeline / Knowledge Vault after the organization becomes a former partner.

### Unfinished work

When a partnership ends:

- no new verification work may be claimed;
- current organization ownership of unfinished investigations should end;
- unfinished work should become available for another eligible Partner Organization;
- prior work already performed on the investigation must not be deleted;
- ordinary user-facing “release investigation” semantics must not be reused blindly when authoritative work has already begun.

The accepted direction is a dedicated Platform Governance termination path, potentially with a distinct assignment terminal state such as `TERMINATED` rather than overloading ordinary `RELEASED`.

### Memberships

When a partnership ends:

- current memberships should stop granting organization/Workspace authority;
- those memberships should no longer count against the single-current-organization constraint;
- membership records should be retained historically rather than deleted;
- `LEFT` is currently the natural persisted state that no longer counts as current;
- former members must be able to join another Partner Organization;
- ending a partnership should not require deleting the organization.

### Invitations

Pending organization invitations should be cancelled/invalidated when a partnership ends.

### Public presence

A former partner should no longer appear as an **active Partner Organization** in the Partner Directory.

However, valid historical published fact-checks must remain publicly readable and attributable. The public presentation may identify the publisher as a **Former TruthLens Partner**.

This means **active partner directory eligibility** and **historical publication readability** must be treated as different concepts.

---

## Verification status vs partnership lifecycle

The current Management Console exposes:

- Verification status: `UNVERIFIED / PENDING / VERIFIED / REJECTED`
- Partner status: `NONE / ACTIVE / SUSPENDED / FORMER`

through an **Edit platform trust** form with two independent dropdowns.

This is considered the wrong UX and governance abstraction because it lets a Platform Admin edit implementation fields rather than perform real governance actions.

### Accepted direction

Replace raw status editing with explicit actions such as:

- Verify organization
- Reject verification
- Activate partnership
- Suspend partnership
- End partnership
- Reinstate partnership

Transitions should be state-aware and enforce valid combinations and side effects.

### “N/A” verification display

Do **not** add `N/A` as a new persisted `verification_status` merely because an organization becomes a former partner.

Reason: if an organization was legitimately verified while operating, changing `VERIFIED` to `N/A` destroys historical truth.

For a former partner, the UI may instead derive a display such as:

```text
Partnership
Former Partner

Verification
Not applicable — partnership ended
Previously verified
```

while preserving the historical verification result internally.

---

## Organization onboarding must remain intact

A newly created organization intentionally begins as:

```text
verification_status = UNVERIFIED
partner_status = NONE
```

That same state is therefore **not sufficient by itself to mean “retired.”**

The Organization Admin onboarding/setup flow must continue working for new organizations.

This is why the lifecycle implementation must be based on explicit governed transitions and not a blanket rule such as “UNVERIFIED + NONE has no Admin access.”

---

## CSG production audit

CSG was originally created by an evaluator as a test organization, but it later accumulated meaningful workflow data. It must **not** be deleted.

Observed organization:

```text
Name: CSG
Verification: UNVERIFIED
Partner: NONE
```

Observed dependencies:

| Dependency | Count / state |
| --- | --- |
| Organization memberships | 3 active |
| Organization invitations | 3 accepted |
| Verification assignments | 4 total: 3 ACTIVE, 1 COMPLETED |
| Moderation cases | 6 total: 3 ADJUDICATION, 3 EVIDENCE |
| Moderation case status | 5 RESOLVED, 1 OPEN |
| Adjudication decisions | 2 current, both FACT |
| Official Fact Checks | 1 PUBLISHED |
| Factual correction requests | 1 ACTIVE |
| Public reach events | 0 |
| Notifications | 0 |
| Accountability history | substantial |

The published fact-check headline observed during the audit was:

> Philippine Congressmen are reportedly studying a potential Facebook ban in the Philippines if Meta does not comply with their directives.

### Deletion safety findings

Organization relationships include a mix of:

- `CASCADE` for memberships/invitations/follows;
- `SET_NULL` for assignments, moderation cases, adjudications, Official Fact Checks, accountability links, notifications, and public reach;
- `PROTECT` for `FactualCorrectionRequest.organization`.

CSG currently has an active factual-correction request, so Django correctly prevents deletion.

Even without that blocker, deletion would weaken provenance by nulling live organization references on historical authoritative records.

**Decision: retain CSG and retire it operationally through the new lifecycle mechanism.**

---

## TruthLens Internal Verification Team onboarding incident

The new internal Partner Organization exists as:

```text
TruthLens Internal Verification Team
verification_status = VERIFIED
partner_status = ACTIVE
```

An Organization Admin onboarding invitation attempt failed before an invitation row was created because the target account still had a non-`LEFT` CSG membership.

The provisioning service currently rejects any recipient who has a membership whose status is not `LEFT`.

This is the concrete symptom that exposed the lifecycle gap.

Do not use ad hoc deletion of CSG to solve it. The lifecycle feature should make former-partner memberships cease to be current while retaining history.

---

## Current authorization behavior that must be handled carefully

### Organization Admin capability

Current `get_membership_capabilities()` behavior grants management capabilities to an active Organization Admin before checking verified-partner eligibility.

As a result:

- factual verification capabilities require active verified partner eligibility;
- `MANAGE_ORGANIZATION` currently comes from an active Admin membership even if the organization is no longer an active verified partner.

That is why the CSG Admin could still access the Workspace after CSG became `UNVERIFIED + NONE`.

Some organization-admin services also directly require an active Admin membership and do not independently check partner lifecycle.

The lifecycle change must preserve legitimate onboarding administration while preventing former/suspended/rejected organizations from retaining operational Workspace access.

### Workspace access

`get_workspace_access_context()` includes a membership when it yields any Workspace capability.

Because `MANAGE_ORGANIZATION` is currently part of `WORKSPACE_CAPABILITIES`, an active Admin membership can keep Workspace access alive even when no factual verification authority remains.

This needs regression coverage before behavior is changed.

---

## Verification assignment behavior

Current assignment states:

- `AVAILABLE`
- `ACTIVE`
- `RELEASED`
- `COMPLETED`

Ordinary `release_verification_assignment()`:

- works only for `ACTIVE` assignments;
- requires `CLAIM_VERIFICATION_WORK`;
- intentionally refuses release once authoritative review work has begun;
- preserves organization / claimant provenance on the released row;
- creates a fresh `AVAILABLE` replacement assignment.

That behavior is correct for ordinary Partner-side release and should not be weakened.

### Partnership termination needs separate semantics

Platform Admin ending a partnership is a distinct governance event.

The implementation should be able to relinquish organization ownership even when authoritative work has begun, while preserving prior work and provenance.

Do not simply loosen the existing Partner-side release rule.

Before adding a new assignment state such as `TERMINATED`, audit every query/serializer/metric/UI that assumes the current state set.

Known consumers of `ACTIVE` include:

- verification assignment service;
- investigation workspace;
- current-state metrics;
- publication workflow;
- verification intelligence;
- classification/routing;
- Community/thread projections;
- numerous tests.

Known consumers of `RELEASED` are fewer but include assignment/evidence/adjudication tests and service logic.

---

## Factual corrections need special handling

CSG has an **ACTIVE factual-correction request**.

A factual correction is not equivalent to a normal unfinished investigation because it refers to an already-published authoritative fact-check whose correction state matters publicly and historically.

Ending a partnership must not silently delete or erase the correction request.

The implementation must define an explicit policy, likely preservation/handoff, before finalizing partnership termination for organizations with an active factual correction.

This remains an implementation decision to resolve carefully during the lifecycle service design.

---

## Published fact-check preservation: important audit finding

### Knowledge reuse

The core Knowledge Vault / published fact-check matching queries currently select `PUBLISHED` Official Fact Checks without requiring the publisher organization to remain an active partner.

That is good: historical publications can remain reusable by the verification pipeline.

### Public fact-check routes

There is a hidden coupling that must be fixed.

Public fact-check endpoints currently resolve the organization through `get_public_partner_by_slug()`.

That helper only returns organizations satisfying active public-partner eligibility:

```text
public_profile_enabled = true
verification_status = VERIFIED
partner_status = ACTIVE
```

Therefore, simply changing an organization to `FORMER` would currently make its public fact-check collection/detail URLs return 404.

Existing tests explicitly assert that suspended/unverified organizations are not resolvable through these public Partner routes.

### Related fact-check presentation

`build_related_published_fact_check_payload()` also requires:

- publication status = `PUBLISHED`;
- organization exists;
- `is_public_partner_eligible(partner)`;
- usable organization slug;
- resolvable public publication detail.

Therefore a former partner's published fact-check may remain in the Knowledge Vault but disappear from related-fact-check presentation in Community/extension.

### Required architectural split

We need to separate:

```text
ACTIVE PARTNER DIRECTORY ELIGIBILITY
    !=
HISTORICAL PUBLICATION READABILITY
```

A former partner:

- should disappear from the active Partner Directory;
- should lose operational Partner authority;
- should retain attributable published fact-check pages;
- should remain eligible for valid historical knowledge reuse;
- may be labeled “Former TruthLens Partner” on historical publication surfaces.

Regression tests must cover this before changing public eligibility behavior.

---

## Management Console UX direction

Current UI:

```text
Platform Trust
[Edit platform trust]

Verification status: <dropdown>
Partner status: <dropdown>
[Save changes]
```

Accepted direction:

```text
Organization Governance

Partnership
Active Partner

Verification
Verified

Operational access
Verification Workspace enabled

Governance actions
[ Suspend partnership ]
[ End partnership ]
...
```

Only valid actions for the current lifecycle state should be shown.

High-impact actions should have explicit confirmation text describing effects such as:

- Workspace access revoked;
- memberships ended;
- pending invitations cancelled;
- unfinished investigations relinquished;
- completed adjudications/publications retained;
- historical authorship and provenance retained.

---

## Proposed End Partnership transaction

The intended service is conceptually similar to:

```python
end_partner_organization_partnership(...)
```

It should be Platform-Admin-only and atomic.

Target sequence:

```text
Validate lifecycle transition
        ↓
Lock organization
        ↓
Inspect current operational work
        ↓
Resolve/handoff special correction state
        ↓
Terminate/requeue unfinished investigation ownership
        ↓
End current memberships without deleting history
        ↓
Cancel pending invitations / rotate tokens
        ↓
Set partnership lifecycle → FORMER
        ↓
Disable future operational authority
        ↓
Preserve all completed authoritative records
        ↓
Record accountability event(s)
```

Avoid partial transitions that leave the organization marked former while operational memberships/assignments remain active.

---

## Regression-first implementation strategy

### Phase 0 — baseline

Before changing behavior:

1. Verify feature branch is based on current `main`.
2. Run/establish a focused regression baseline.
3. Add tests for invariants that are currently under-specified.
4. Only then implement lifecycle transitions.

### Existing behavior to protect

Regression coverage should explicitly preserve:

#### Organization onboarding and Admin flows

- new organizations begin `UNVERIFIED + NONE`;
- Organization Admin onboarding invitations work;
- single-current-organization rule remains enforced for truly current memberships;
- multiple Admin behavior remains supported where already designed;
- membership-management restrictions remain intact;
- Admin invitation/member management remains scoped correctly;
- verification specialization/scope administration remains intact for eligible states.

#### Partner Workspace authority

- active verified Partner roles retain exactly their current capabilities;
- factual roles continue to require active verified Partner eligibility;
- Platform Safety remains separate from Partner factual verification;
- organization scoping continues preventing cross-organization authority leakage.

#### Investigation workflow

- ordinary claim/release logic remains unchanged;
- authoritative work cannot be casually released through Partner-side flow;
- completion via publication remains unchanged;
- investigation queues/projections remain correct.

#### Adjudication/publication

- current adjudications remain attributable;
- fact-check drafting/review/publish workflow remains unchanged for active partners;
- sealed publication lineage remains intact;
- factual-correction workflow remains intact;
- published results continue resolving correctly.

#### Public/knowledge surfaces

- active Partner Directory behavior remains correct;
- historical former-partner publications become readable through the intended new contract;
- Knowledge Vault reuse keeps working;
- related fact-check surfaces keep historical publications where policy allows;
- former organizations do not regain current Partner capabilities merely because historical publications remain public.

---

## High-risk code areas identified in impact audit

Backend:

- `api/management_governance_service.py`
- `api/organization_service.py`
- `api/organization_membership_service.py`
- `api/organization_invitation_service.py`
- `api/organization_provisioning_service.py`
- `api/organization_scope_service.py`
- `api/verification_assignment_service.py`
- `api/investigation_workspace_service.py`
- `api/publication_workflow_query_service.py`
- `api/public_publication_query_service.py`
- `api/organization_public_presence_service.py`
- `api/knowledge_reuse_service.py`
- `api/verification_current_state_metrics_service.py`
- `api/views.py`
- organization/management serializers and accountability instrumentation.

Frontend:

- `src/Pages/ManagementOrganizationDetailPage.jsx`
- `src/utils/management.js`
- Workspace authorization/navigation surfaces that consume `MANAGE_ORGANIZATION`
- Partner/public fact-check presentation as needed for former-partner labeling.

Tests with particularly relevant existing coverage:

- `api/tests/management/test_management_governance_service.py`
- `api/tests/management/test_management_api.py`
- `api/tests/workspace/test_access_context.py`
- `api/tests/workspace/test_access_api.py`
- `api/tests/organization/test_membership_service.py`
- `api/tests/organization/test_membership_constraints.py`
- `api/tests/organization/test_invitation_service.py`
- `api/tests/organization/test_invitation_acceptance_api.py`
- `api/tests/organization/test_organization_provisioning_service.py`
- `api/tests/workspace/test_assignment_service.py`
- `api/tests/workspace/test_assignment_api.py`
- `api/tests/workspace/test_assignment_publication.py`
- adjudication transaction/integrity tests;
- publication workflow/correction tests;
- `api/tests/organization/test_public_fact_check_api.py`
- `api/tests/verification/test_published_claim_resolution.py`
- related/published-result verification tests.

---

## Deployment note observed during CSG audit

At the time the production/WS2 CSG audit was run, importing `OrganizationInstitutionAffiliation` failed even though that model exists on current GitHub `main`.

This suggests the running WS2 checkout/process was not yet at the same code level as current `main` at that moment.

Before deploying this lifecycle feature, explicitly verify production:

```bash
git branch --show-current
git rev-parse --short HEAD
git log -1 --oneline
python manage.py showmigrations api
```

Do not assume Vercel frontend deployment implies backend code/migrations are current.

---

## Regression checkpoint commits

The first preservation-only regression tests were added before lifecycle implementation:

- `4303e6d2` — `test: checkpoint workspace partner access invariants`
  - active verified Organization Admin retains the existing organization-management Workspace context;
  - an active Lead Verifier loses factual Workspace access when the organization is suspended.
- `1f24069d` — `test: checkpoint organization onboarding membership invariant`
  - a historical `LEFT` membership in another organization does not block initial Organization Admin provisioning.

These tests intentionally avoid encoding the CSG Admin-access bug as expected behavior.

No lifecycle production logic was changed by these commits.

## Current checkpoint / next step

### Baseline validation completed

Local baseline validation completed successfully after recreating the stale preserved test database:

- 97 focused regression tests passed;
- `python manage.py check` passed;
- `python manage.py makemigrations --check --dry-run` reported no changes.

The initial `--keepdb` failure was caused by a stale test database whose schema still contained `api_platformstaffinvitation` from the pre-reconciled migration state. Recreating only the test database resolved it; production/development data was not implicated.

### First lifecycle implementation slice

The branch now contains a backend-only, not-yet-exposed lifecycle service:

- `e0a4cdd1` — add `end_partner_organization_partnership()`;
- `785ef603` — define end-partnership lifecycle invariants;
- `db7d2c2c` — correct the lifecycle invitation test fixture.
- `926054bd` — scope partnership termination moderation-case row locks to `ModerationCase` itself. PostgreSQL rejects `FOR UPDATE` across the nullable joins used to locate evidence/adjudication cases; `select_for_update(of=("self",))` preserves the intended concurrency protection without locking nullable joined relations.
- Focused lifecycle validation after the row-lock fix: **5/5 tests passed** in `api.tests.management.test_organization_partnership_lifecycle_service`.
- Broader regression gate after the lifecycle service: **all 102 focused tests passed**, `manage.py check` passed, and `makemigrations --check --dry-run` reported no changes.

Current intended behavior:

- Platform Admin only;
- active or suspended partnership may be ended;
- partner status becomes `FORMER`;
- verification history is preserved;
- current non-`LEFT` memberships become `LEFT`;
- pending invitations are cancelled and their token digests rotated;
- ACTIVE verification assignments become historical `RELEASED` rows with `PARTNERSHIP_ENDED` audit reason;
- fresh `AVAILABLE` replacement assignments are created;
- active factual moderation-case ownership is detached so another Partner Organization can claim the work;
- completed assignments and historical provenance remain untouched;
- an ACTIVE factual-correction request currently blocks partnership termination because the correction belongs to an already-published institutional record and requires explicit resolution rather than silent abandonment.

A new assignment enum such as `TERMINATED` has intentionally **not** been added yet. The first slice reuses `RELEASED` with explicit Platform-governance audit metadata to minimize changes to existing assignment queries and state assumptions.

The service is not yet wired to a Management API endpoint or frontend control. Run its focused tests before exposing it.

CSG should remain untouched until this lifecycle path is validated.


### Management lifecycle API slice

The next isolated backend slice is now implemented but still not connected to the frontend:

- `3b3484c3` — derived, read-only organization lifecycle projection;
- `be18ffaf` — expose the lifecycle projection on Management organization detail;
- `013c004d` — add the Platform Admin End Partnership API view;
- `d6fefa27` — route the dedicated End Partnership action;
- `d6d9bd43` — include the action in the Management write-permission regression matrix;
- `ac855027` — dedicated lifecycle API contract tests;
- `b823a20e` — align derived operational access with the existing VERIFIED + ACTIVE partner-authority rule.

Current API route:

```text
POST /management/organizations/<organization_id>/partnership/end/
```

The action accepts an empty body only. Arbitrary raw status fields are rejected.

The Management organization detail now includes a derived `lifecycle` object with:

- lifecycle state;
- operational-access state;
- whether End Partnership is currently allowed;
- explicit End Partnership blockers;
- impact counts for current memberships, pending invitations, active investigations, and active factual corrections.

The End Partnership response returns:

- the refreshed Management organization detail;
- transition counts for memberships ended, invitations cancelled, and investigations requeued.

No frontend behavior has changed yet. The legacy Edit Platform Trust UI remains in place until this API slice passes its focused regression gate.


### Management lifecycle API test-fixture correction

The first 49-test Management API gate produced seven errors before endpoint assertions ran. The lifecycle API test class defined a helper named `client()`, but DRF `APITestCase` already installs `self.client` as an `APIClient` instance. Calling `self.client()` therefore raised:

```text
TypeError: 'APIClient' object is not callable
```

This was a test-fixture naming collision, not an API implementation failure.

- `5d12edb8` — rename the helper to `authenticated_client()`.

No production lifecycle or Management API behavior changed in this correction.


### Legacy retirement compatibility path

Before replacing the Management Console status UI, the CSG production state exposed one more compatibility requirement:

```text
CSG
verification_status = UNVERIFIED
partner_status = NONE
current memberships still present
historical/active verification work present
```

The initial lifecycle service only allowed `ACTIVE` or `SUSPENDED` partnerships to transition to `FORMER`, which would have prevented CSG from using the new lifecycle path.

The backend now distinguishes a brand-new onboarding organization from a legacy organization that was manually deactivated but still has Partner-work provenance.

- `a7d823f0` — allow a `NONE` organization to enter the retirement path only when it has persisted prior Partner work (verification assignments or Official Fact Checks), and project it as `RETIREMENT_REQUIRED`.
- `f33e56d5` — service regression coverage for the legacy retirement path and for preserving the non-endable state of a new onboarding organization.
- `ab425835` — Management API projection coverage for `RETIREMENT_REQUIRED`.

Derived behavior:

```text
UNVERIFIED + NONE + no prior Partner work
→ ONBOARDING / SETUP_ONLY / not endable

NONE + persisted Partner verification work
→ RETIREMENT_REQUIRED / operational access disabled / endable
   unless another lifecycle blocker exists
```

An ACTIVE factual-correction request remains an explicit blocker. Therefore CSG will project as retirement-required but still cannot complete End Partnership until its active factual correction is resolved or an explicit correction-handoff policy is implemented.

This compatibility logic intentionally avoids treating every `UNVERIFIED + NONE` organization as retired, which preserves the Organization Admin onboarding flow.
