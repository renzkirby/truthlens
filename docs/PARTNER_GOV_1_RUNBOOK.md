# PARTNER-GOV-1 — scope and automatic classification rollout

Status: implementation checkpoint, **not production approved**. Branch:
`feat/partner-governance-eligibility`.

## Role boundaries

- A Partner Organization **Primary Admin** or **Admin** submits requested
  subject specializations/jurisdictions and chooses active subsets.
- A platform superuser separately approves or revokes maximum jurisdiction
  and subject authority; the organization's request never self-approves.
- Active scope is always constrained to platform approval. New approvals
  require organization activation; revocations take effect immediately for
  new work. Previously ACTIVE investigations are not reassigned.
- A Lead Verifier with `CLAIM_VERIFICATION_WORK` may accept only AVAILABLE
  work that has an authoritative classification matching the active scope.
- Legacy `expertise_areas` remain stored for backward compatibility but no
  longer appear as a separate editable profile field in the Partner Workspace.
  They are **not** authorization data.

## Automatic claim classification rollout

Set in backend environment (used by Django **and Celery workers**):

`INVESTIGATION_CLASSIFICATION_MODE=off` (default). No classifier calls are
made. Existing unclassified claims remain unclaimable.

`INVESTIGATION_CLASSIFICATION_MODE=shadow`. Asynchronously call Gemini-first
with Groq fallback when a new community thread is created, record classification
candidates and abstentions, but **do not authorize partner intake**.

`INVESTIGATION_CLASSIFICATION_MODE=enforce`. Explicit opt-in only **after**
an independent accuracy review of representative shadow-mode results, including
correct domain coverage, exact geographic scope, false-positive cases,
ambiguous claims, different media types, and unknown jurisdiction. Structural
quote matching alone is *not* accuracy validation. Successful classifier
results are recorded separately from factual verdicts and become eligible
for matching active partner scope; ambiguous results remain unclassified.

Do not switch straight to enforce merely because unit tests pass.
Provider calls are not part of the existing verification pipeline and should
not delay factual verdicts. Unexpected queue/provider failure leaves the
claim unclassified. The exception queue supports retrying only when the
classifier mode is not off. The old manual classification service remains
for legacy migration compatibility; routine per-claim reviewer approval is
not part of this rollout.

The first classifier version intentionally abstains on unsupported
jurisdictions and image-only content. Its initial country mapping is limited;
geographic and multi-jurisdiction classification require further evaluation.
Never infer `GLOBAL` merely because no location was stated.

## Local acceptance

From `backend/truthlens_backend` using the project venv:

```powershell
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run --settings=truthlens_backend.test_settings
..\.venv\Scripts\python.exe .\manage.py check --settings=truthlens_backend.test_settings
..\.venv\Scripts\python.exe .\manage.py test api.tests.organization.test_verification_scope api.tests.verification.test_investigation_classifier api.tests.workspace.test_assignment_service --settings=truthlens_backend.test_settings --keepdb
..\.venv\Scripts\python.exe .\manage.py test api.tests.management api.tests.workspace api.tests.accountability api.tests.organization --settings=truthlens_backend.test_settings --keepdb
```

Frontend (from `frontend/frontend`):

```powershell
npm run lint
npm run build
```

Before applying migrations to a **local development** database, verify
`DATABASE_URL` and `APP_ENV`, take a backup, and inspect migration plans:

```powershell
..\.venv\Scripts\python.exe .\manage.py showmigrations api
..\.venv\Scripts\python.exe .\manage.py migrate --plan
```

New migrations: `0082_organization_scope_requests`,
`0083_investigation_classification_assessment`. Do not apply to production
until this branch passes acceptance.

Manually verify: superuser approval modal; organization OWNERS/ADMINS request
and activate; non-management roles denied; unapproved and inactive work
cannot be claimed through POST even if intake UI is bypassed; classification
exception queue; a later revocation does not alter existing ACTIVE assignments;
legacy published fact checks preserve provenance. Confirm no new factual
verdicts or evidence writes are performed by the classifier.
