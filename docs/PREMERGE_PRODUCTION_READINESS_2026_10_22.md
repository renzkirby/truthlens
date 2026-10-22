# TruthLens pre-merge production-readiness review — 2026-10-22

Branch: `feat/ai-rq2-provider-hierarchy`

This review is intentionally broader than the AI-RQ-2 / PARTNER-GOV-1
classification work because merging this branch causes Vercel to deploy the
frontend while the production Django backend does not automatically update.

## Current source relationship

At review start, the feature branch was ahead of `main` and not behind it.
The branch changes 147 files, including 13 frontend files, 104 backend files,
the finalized backend/frontend changes and five sequential Django migrations (0081-0085).
There are no extension changes in this branch.

A clean Git merge is not sufficient evidence of deployment safety. Frontend,
web backend, database schema, and Celery workers must be considered as separate
runtime versions.

## Live classification status

The bounded development shadow canary passed all three fixed cases:
- SCIENCE: Gemini HTTP 402 -> Cloudflare success.
- ECONOMY + HEALTH: Gemini HTTP 402 -> Cloudflare timeout -> Groq success.
- ambiguous claim: Gemini HTTP 402 -> Cloudflare success -> valid ABSTAIN.

The canary observed 3/3 exact reference matches, 7 provider-stage attempts,
zero authoritative classification rows, and zero factual-verdict mutations.
The synthetic canary rows were subsequently verified and deleted.

This proves integration/fallback/shadow isolation for that canary. It does not
establish general model accuracy and does not authorize `enforce`.

## Release blocker found and corrected: partner intake

Before this review, the branch filtered partner intake and rejected assignment
claims whenever an authoritative `ClaimInvestigationClassification` was
missing, regardless of classification mode. Production defaults to
`INVESTIGATION_CLASSIFICATION_MODE=off`, and there is no independent
production write path that populates authoritative classification rows while
automatic enforcement remains unapproved. Deploying that behavior would have
made normal new partner intake effectively empty/unclaimable.

Corrected policy:
- `off`: preserve pre-classification production intake/claim behavior.
- `shadow`: preserve pre-classification intake/claim behavior; suggestions are
  diagnostic and can neither grant nor deny work.
- `enforce`: classification + organization specialization matching becomes
  authoritative and is rechecked under transaction locks.

Regression coverage was added to both the assignment service and intake API.
The existing conservative `eligibility_reason()` contract is unchanged once
enforcement is enabled.

## Release blocker found and corrected: backend-first old-client compatibility

The deployed management frontend currently submits
`verification_status=UNVERIFIED` and `partner_status=NONE` when creating an
organization. The feature-branch backend had removed those request fields
entirely, so deploying the backend first would have returned HTTP 400 to the
currently deployed client.

The create serializer now accepts those two legacy fields only as normal
choices; the governance service still enforces that creation values are exactly
UNVERIFIED/NONE. Non-default trust escalation at creation remains rejected.

This intentionally does not preserve the old UI's ability to select a
non-default trust value during creation. During a backend-first rollout window,
platform administrators must not use old create-form trust selectors; the new
frontend removes them.

## Frontend-first compatibility result: NOT SAFE

The new frontend contains a new endpoint dependency:
`organizations/<organization_id>/verification-scope/`.
That endpoint does not exist on `main`.

The new public partner pages also use the additive
`authorized_verification_domains` response field, which is absent from the
old backend. The UI safely treats the absent array as empty, but that would make
existing public profiles appear to have no selected verification
specializations. The organization workspace scope tab would receive a 404.

Therefore do not merge while production backend is still on the old release.
Vercel must not be allowed to become the first upgraded runtime.

## Backend-first compatibility result: acceptable subject to tests

No existing API URL was removed in the reviewed branch delta. Public profile
update still accepts the legacy `expertise_areas` field and public partner
responses still include `expertise_areas`, so the old frontend can continue
using the descriptive profile field after backend upgrade. New response fields
are additive.

The old management create client's safe defaults are now accepted. Normal
partner intake is preserved while classification is off/shadow. These are the
two branch changes that otherwise prevented a safe backend-first sequence.

There is still a short management-console behavior mismatch if an old frontend
administrator tries to create an organization with VERIFIED/ACTIVE (or other
non-default trust states): the hardened backend rejects it. This is deliberate
governance behavior. Avoid organization creation during the backend/frontend
cutover window or deploy the frontend immediately after backend smoke checks.

## Migrations 0081-0085

The migration chain is linear from main's existing migration history.

- 0081 adds legacy governed scope fields and the authoritative claim subject
  classification table.
- 0082 adds historical request/active scope fields.
- 0083 adds the shadow assessment table and classification source.
- 0084 makes the classification actor optional for automatic results.
- 0085 adds Primary-Admin-managed verification specializations and performs a
  forward-only backfill from historically effective governed scope.

The former development-only 0086 repair for an unmodeled
`api_claim.relatedness_context` column was removed before PR preparation.
That column belongs to the co-developer's unmerged bounded-evidence branch and
was not part of current `main`; shipping a production repair for that
branch-switch development schema state would have been incorrect.

No migration removes a Django-managed production field in this chain.

Important rollout implication: 0081-0085 have not previously existed on
production together. Existing organizations that have no previously populated
approved/active scope data will receive an empty
`verification_specializations` list. This is safe while classification
enforcement remains off. Primary Admins must configure specializations before
a future `enforce` rollout.

0085 iterates through Organization rows during migration. Organization volume
should be checked before production migration; with the expected small partner
organization population this is low risk, but the production database should
still be backed up first.

## AI/provider production behavior

Cloudflare hierarchy/pilot activation remains development-gated. Classification
mode defaults to `off`. Merging code alone does not enable Cloudflare
classification or authoritative automatic classification in production.

Production must retain:
`INVESTIGATION_CLASSIFICATION_MODE=off`
until a separately approved rollout decision.

Do not add development Cloudflare pilot flags to production. Gemini's local
HTTP 402 condition from the canary is an account/quota issue and should be
resolved separately; it did not invalidate fallback integration.

## Web backend / Celery compatibility

Automatic classification introduces a new Celery task that does not exist on
`main`. With production classification mode `off`, normal persistence does
not dispatch that task, so a brief old-worker/new-web overlap is not expected to
enqueue an unknown task. Nevertheless, web backend and Celery workers should be
deployed/restarted from the same release before any future shadow/enforce mode
is enabled.

For a normal release, restart both components together after migrations so
verification-provider behavior and telemetry match the deployed web code.

## Required local acceptance after compatibility fixes

Backend focused release tests:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.workspace.test_assignment_service `
  api.tests.workspace.test_assignment_api `
  api.tests.management.test_management_api `
  api.tests.management.test_management_governance_service `
  api.tests.organization.test_verification_scope `
  api.tests.organization.test_verification_scope_migration `
  api.tests.verification.test_investigation_shadow_integration `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_classification_fallback `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

Then run the full backend test suite before PR/merge.

Frontend acceptance from `frontend\frontend`:

```powershell
npm run build
npm run lint
npm run test:auth
```

Any existing lint baseline failures must be separated from newly introduced
errors before approval.

## Required deployment order

1. Do not merge yet.
2. Back up the production database.
3. Confirm production environment keeps classification `off` and does not
   enable development Cloudflare flags.
4. Deploy the feature-branch backend release first, including migrations
   0081-0085, and restart the web backend + Celery workers on the same code.
5. Smoke-test old production frontend against the new backend: authentication,
   verification submission/status polling, community, partner intake/claim,
   public partner pages, organization public profile, and management read paths.
6. During this temporary old-frontend/new-backend window, avoid using the old
   organization-create trust selectors.
7. Only after backend smoke tests pass, merge the reviewed branch so Vercel
   deploys the new frontend.
8. Smoke-test the new frontend against the already upgraded backend, especially
   organization verification scope and public partner specialization display.
9. Keep automatic classification enforcement off.
10. PR/merge authorization remains a separate user decision.

If the production hosting process cannot deploy this backend commit before the
Vercel-triggering merge, split the release so backend/migrations are deployed
first and frontend changes land only after backend readiness is confirmed.
