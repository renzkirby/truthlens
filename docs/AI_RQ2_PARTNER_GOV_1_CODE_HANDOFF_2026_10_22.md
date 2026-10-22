# TruthLens — AI-RQ-2 + PARTNER-GOV-1 co-developer handoff

**Date:** 2026-10-22 (Philippines).
**Source branch:** `feat/ai-rq2-provider-hierarchy`.
**Handoff status:** Ready for continued implementation and review, **not approved for
production rollout, partner classification `enforce`, or immediate merge into
`main`**.
**Integration principle:** do not weaken the existing fact-check verdict,
source-dossier quality, assignment controls, or publication provenance to make
the new classifier/provider tests pass.

## Current repository relationship (verified at handoff preparation)

GitHub source HEAD before this handoff-only documentation commit:
`09d6708fe64908363c60cf7b4293c91723092301`.

At inspection, `main` HEAD was
`1210061b99d4bec7e4c13efad193c58e27f1ffde`.
GitHub reported the source as **213 commits ahead, zero behind** `main`;
the branch covers 115 modified/added files across AI routing, migrations,
organization governance, and UI. **This is an accumulated integration branch,
not a minimal AI-only patch.** These snapshots can change; verify remote
heads before merging.

Current `main` has Django `api` migrations through
`0080_verificationtelemetryevent`. This source branch adds a linear
`0081`–`0086` chain. There is **no direct migration filename
collision with the checked `main`**, but the co-developer's *own branch*
and *target database migration history* must be checked separately.

### The six additional migrations

| Name | Purpose | Integration note |
|---|---|---|
| `0081_partner_verification_scope` | Historic approval-domain/geographic fields + authoritative claim classification | New models/fields and accountability choices |
| `0082_organization_scope_requests` | Prior request/activation scope fields | Retained as historical fields, **no longer intake authority** |
| `0083_investigation_classification_assessment` | Persisted shadow assessment, classification source | `SUGGESTED` is **not** claim authority |
| `0084_claim_classification_actor_optional` | Optional classification actor | Support system-produced classifications |
| `0085_organization_specializations` | Primary Admin-managed subject specializations and jurisdiction-optional classifications | **RunPython backfill** uses historically effective approved/active domains only when geographic authorization was nonempty; reverse data migration is **no-op** |
| `0086_relax_unmodeled_claim_relatedness_not_null` | Conditional PostgreSQL-only legacy Claim column repair | Repairs an unmapped `relatedness_context` NOT NULL constraint only if present and default-less; fresh/non-PostgreSQL DBs are no-ops |

**Never delete/rename/edit an already applied migration, hand-renumber
history, run `--fake` to conceal a collision, or blindly regenerate
`0081`–`0086`.** If the co-developer has migrations also based on
`0080`, inspect file identities, DAG ancestry, migration effects and
historical DB state *before* deciding between a valid merge migration or
reconstructing an unapplied private migration. Django
`makemigrations --merge` only fixes graph topology and does **not**
prove conflicting schema/data operations safe.

## AI-RQ-2: what is working

- **Development-only opt-in** Gemini → Cloudflare Workers AI Gemma 4 →
  Groq provider hierarchy. When the flag is off, pre-existing routing
  remains in place. `provider_hierarchy.py` requires `APP_ENV=development`,
  `DEBUG=True`, and `ENABLE_AI_RQ2_PROVIDER_HIERARCHY=1`.
- In the opt-in hierarchy, Gemini 402/429 can trip a job-scoped skip.
  Cloudflare failures use a job-scoped breaker; Groq fallback disables
  automatic SDK HTTP retries. Strict provider-independent JSON
  classification response validation requires exact quotation of the
  claim, allowed domains and no extraneous fields in the strict lane.
- A **single approved direct Cloudflare** Europa Clipper classification
  returned `SCIENCE`+`TECHNOLOGY` after **16,132 ms** with dev-only
  `CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC=30` and
  `CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY=1`.
  An otherwise comparable direct request with 15-second read timeout
  failed after **15,295 ms**. These are individual requests, **not**
  a reliable p95/SLA or proof of broad success.
- The completion cap remains 1024 tokens for classification; read-inactivity
  timeout is **not** a hard end-to-end Celery-job deadline. Final-verdict
  and evidence-assessment Cloudflare timeouts were **not** raised
  indiscriminately. The 30s + fast-fail overrides remain **off by default**.
- User-reported acceptance: prior 232-test integration matrix passed
  after fixing four ambient environment-dependent legacy routing tests;
  subsequently **75/75 focused offline classification audit/eligibility
  tests passed** in **3.489 seconds**, `manage.py check` reported no
  issues and `makemigrations --check --dry-run` showed no changes.
  These are user-run tests, not a complete CI/production reliability audit.

### AI-RQ-2 outstanding work (not optional for production)

1. **Cloudflare evidence-assessment reliability**: short assessment calls
   have timed out at ~15s in prior probes; classify/final successes do not
   establish multistage reliability. No new paid/real provider calls without
   explicit approval and a bounded test/cost plan.
2. **End-to-end latency budgets** across Gemini, Cloudflare and Groq,
   worker retries/cancellation behavior, failure-rate and cost measurement.
   Current read timeouts do **not** enforce a total deadline.
3. **Empirical factual-verification quality and regression**: preserve
   persisted-evidence reasoning, citation/source independence, and
   abstention/authoritative publication precedence; compare against a
   reviewed corpus before a broad provider rollout.
4. **Classification strict-contract parity** outside opt-in AI-RQ-2:
   legacy `validate_model_suggestion` validates quoted codes but is less
   strict about extra response fields than
   `verification/classification_contract.py`. Decide and test a
   provider-independent fail-closed rule before enabling enforcement.
5. **Staging/production enablement** is deliberately blocked by dev-only
   guards and requires separate design and approval, not simply flag
   toggles.

## PARTNER-GOV-1: what is working

- **Primary Admin (OWNER internally) alone** may manage organization
  subject specializations; ADMIN can view but cannot set them. Platform
  Admin cannot set an organization's verification subjects.
- New assignments require an **authoritative**
  `ClaimInvestigationClassification` and **all** classified domains to
  be covered by the organization's declared specializations, in
  addition to partner/membership/capability constraints. No geographic
  authority is inferred. Existing ACTIVE/COMPLETED assignments preserved.
- `INVESTIGATION_CLASSIFICATION_MODE=off` remains the default.
  `shadow` only records candidate `InvestigationClassificationAssessment`
  without making a claim claimable; identical claims are idempotent and
  cannot silently promote shadow results upon a later mode change.
  `enforce` is **not authorized**.
- The 32-case synthetic subject-domain corpus covers 12 supported
  domains/8 test categories, including multi-domain, ambiguous,
  geographic and prompt-injection cases. User confirmed:
  `CORPUS cases=32 approved=0 pending=32`, `NOT SCORED`;
  the read-only audit command made **no provider calls or DB writes**.
- The first user reviewer separately completed a Blind Review and
  Final Review. **Both were done by the same person**, and therefore
  constitute **one**, not two independent reviews. The prior
  reconciliation identified the main substantive proposal:
  `cross_school_sport` to `EDUCATION` only instead of the synthetic
  draft `EDUCATION + SPORTS`; several other cross-domain cases need
  deliberate domain-boundary adjudication.
- **Important:** the submitted Excel review files and any provisional
  consolidated JSON are not part of this GitHub branch. Receive them
  directly and retain them privately; do not assume the 32 Git fixture
  labels have been approved. The canonical fixture on the branch was
  intentionally left **32 PENDING, 0 APPROVED**.
- Review sheets:
  `docs/PARTNER_GOV_1_BLIND_REVIEW_SHEET.md` (no label hints);
  `docs/PARTNER_GOV_1_SUBJECT_DOMAIN_REVIEW_WORKSHEET.md`
  (AI-assisted, **not** human adjudication);
  `docs/PARTNER_GOV_1_CLASSIFICATION_ACCURACY_ACCEPTANCE.md`.
- The command `python manage.py audit_investigation_classification`
  loads synthetic cases without network calls; it can score **only
  separately approved human references** against **previously captured
  unaltered raw model responses**. The persisted shadow record stores
  domain codes, **not** source quotations or model response text.
  No measurable model-accuracy corpus has yet been produced.

### PARTNER-GOV-1 outstanding work

1. Obtain an **independent second human blind review** of the 32 cases,
   without showing that reviewer the first review or AI proposal first.
   Define stable boundary rules, reconcile disagreements, preserve
   reviewer rationale and mark labels APPROVED **only** after consented,
   documented human adjudication.
2. Agree on actual-classifier accuracy thresholds and an explicit
   finite, authorized provider-evaluation/capture plan (or existing
   previously captured outputs). No invented result, no full provider
   response reconstructed from `candidate_domains`.
3. Check cross-domain under- and over-classification for possible
   partner **overauthorization** and **overexclusion** under the
   all-domains-must-match rule; do not casually relax that rule.
4. Review provider/contract parity, remaining text/URL/image/file claim
   shadow scenarios, assignment races and scoped workbench UI
   acceptance. **Do not enable `enforce`** before a separate written
   authorization decision.

## Recommended safe repository handoff

### If continuing directly from this branch (preferred)

From a **clean** working tree:

```powershell
git status -sb
git fetch origin
git switch -c feat/partner-gov-classification-continuation origin/feat/ai-rq2-provider-hierarchy
git log -1 --oneline
git status -sb
```

This inherits the already linear `0081`–`0086` chain. If the
co-developer builds new schema changes **on top**, the next API migration
normally depends on `0086`; let Django generate it from the actual
graph rather than manually choosing a number.

### If integrating with separate co-developer changes

**Do not merge to `main` as the first step.** Preserve both branches
and use a new disposable integration branch based on the handoff branch
*or* the agreed co-development target; choose direction only after
comparing code and migration ancestry.

```powershell
git fetch origin
git log --oneline --decorate origin/main..origin/feat/ai-rq2-provider-hierarchy
git diff --name-status origin/main...origin/feat/ai-rq2-provider-hierarchy -- backend/truthlens_backend/api/migrations
git diff --name-status origin/main...origin/YOUR_CO_DEV_BRANCH -- backend/truthlens_backend/api/migrations
```

Replace `YOUR_CO_DEV_BRANCH` with the **actual** branch name.
Independent `0081` filenames/operations or multiple Django migration
graph leaves can conflict even without a Git textual merge conflict.

In a **disposable integration working branch only**, attempt
`git merge --no-commit --no-ff origin/YOUR_CO_DEV_BRANCH`. If unresolved
or semantically conflicting, `git merge --abort`, inspect the DAG,
and agree on a non-destructive migration reconciliation. Only after
Git conflicts are resolved, inspect `showmigrations api`,
`makemigrations --check --dry-run`, `migrate --plan` and relevant
`sqlmigrate`; then test on a **backup/throwaway development DB**.
No `migrate` on the shared Supabase DB before confirming backups and
permissions; no production migration without deployment approval.

### Minimum verification gates on the integration result

From `backend/truthlens_backend`:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py showmigrations api
..\\.venv\\Scripts\\python.exe .\\manage.py migrate --plan
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
..\\.venv\\Scripts\\python.exe .\\manage.py check

..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_classification_latency_policy `
  api.tests.organization.test_verification_scope `
  api.tests.organization.test_verification_scope_migration `
  api.tests.verification.test_claim_legacy_schema_repair `
  api.tests.workspace.test_assignment_service `
  --settings=truthlens_backend.test_settings --keepdb
```

Use the broader TEXT/URL/provider/organization/workspace regression
matrices, frontend lint/build, manual extension+organization workspace
checks, Django migration graph checks and an isolated PostgreSQL
migration rehearsal before claiming merge readiness. Successful
`makemigrations --check` only means Django's **model state** matches;
it does not guarantee no DB-only legacy column issues like `0086`.

## Branch / issue context

- Branch source: `feat/ai-rq2-provider-hierarchy`
- AI routing and pilot notes:
  `docs/AI_RQ2_PROVIDER_HIERARCHY_ACCEPTANCE.md`,
  `docs/AI_RQ2_CLASSIFICATION_LATENCY_POLICY.md`.
- Partner governance:
  `docs/PARTNER_GOV_1_RUNBOOK.md`,
  `docs/PARTNER_GOV_1_CLASSIFICATION_ACCURACY_ACCEPTANCE.md`.
- Issues: `#128` partner governance, `#138` AI-RQ-2, and `#139`
  Cloudflare reliability.
- Do not create a PR or merge the broad source branch into `main`
  merely because focused offline tests passed. Obtain co-developer
  confirmation of migration integration strategy, review scope,
  held-out model quality, and staged rollout requirements first.
