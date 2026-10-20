# PARTNER-GOV-1 — owner-managed specializations and subject-only classification

Status: **implementation checkpoint, not accepted or deployed**.
Branch: `feat/partner-governance-eligibility`.

## Approved governance boundaries

- Platform Admin: creates organizations, manages verification/partner lifecycle,
  invites the Primary Admin, and oversees partner status. No authority to set
  an organization's investigation subjects or retry/classify individual claims.
- Primary Admin (OWNER internally): selects any supported investigation subject,
  updates the list immediately, and provides an audited rationale.
- Admin: may view specializations and retains existing organization management
  capabilities but **cannot** edit specializations without a future explicit
  delegation mechanism. Lead Verifier and lower roles cannot change subjects.
- Organization type and descriptive `expertise_areas` never grant work authority.
- Eligible partner intake requires partner status, verifier membership capability,
  authoritative subject classification, and subject coverage. Geographic coverage
  **does not** gate assignments. Existing ACTIVE and COMPLETED ownership is unchanged.
- Management Console displays selected specializations read-only; no approval
  modal, classification exception queue, manual classification, or retry endpoint.

## Forward-only migration and data preservation

Migrations `0081`–`0084` may already be applied on the development database.
**Do not edit, roll back, fake, or remove those applied migrations.**
New `0085_organization_specializations` adds one authoritative JSONB field,
marks `ClaimInvestigationClassification.jurisdiction` optional for new
subject-only classifications, and introduces an organization-scope audit action.
A reversible-schema / no-op-data-reverse `RunPython` copies old effective
domains only where historical active/approved jurisdiction was also nonempty.
It does not alter old requested, approved, active, geographic, publication,
adjudication, or assignment records.

Before running migrations on the remote development Supabase database, verify
that it is the intended isolated development project, confirm a recent backup,
check `showmigrations api`, and inspect `migrate --plan` and
`sqlmigrate api 0085`. Do not migrate production without separate approval.

## Automatic classifier rollout

`INVESTIGATION_CLASSIFICATION_MODE` remains `off` by default.
- `off`: no model calls; unclassified claims remain unclaimable.
- `shadow`: records subject suggestions without creating claim authority.
- `enforce`: applies validated subject classifications; **only** enable after
  independent accuracy evaluation, representative real examples, and approval.

The classification pipeline is distinct from factual-verdict generation and
does not modify factual confidence, evidence, adjudication, publication, or
provenance. Classifier `v2-subject-only` requires exact supporting quotations,
abstains on uncertain/unsupported subjects, and currently processes sufficiently
detailed TEXT context only. Other claim types are not yet eligible for automated
classification. Geographic evidence is neither required nor inferred.
The latest assessment record is retained for internal diagnostics; the platform
does not review or retry individual classifications. A future automated retry
policy for material claim-context changes must be separately tested.

## Required local test gates (Windows)

From `backend\truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run --settings=truthlens_backend.test_settings
..\.venv\Scripts\python.exe .\manage.py check --settings=truthlens_backend.test_settings
..\.venv\Scripts\python.exe .\manage.py test api.tests.organization.test_verification_scope api.tests.organization.test_verification_scope_migration api.tests.verification.test_investigation_classifier api.tests.workspace.test_assignment_service --settings=truthlens_backend.test_settings --keepdb
..\.venv\Scripts\python.exe .\manage.py test api.tests.management api.tests.workspace api.tests.accountability api.tests.organization --settings=truthlens_backend.test_settings --keepdb
```

From `frontend\frontend`:

```powershell
npm run lint
npm run build
```

Manual acceptance: platform superuser cannot mutate subjects or retry claim
classification; active Primary Admin can set and clear subjects; Admin reads
but cannot update; Lead Verifier cannot modify; same-domain subject outside
previous country authorization is claimable; out-of-domain or unclassified
claim remains unclaimable even by direct API; narrowing affects only NEW work;
historical assignments, verdicts, and publication provenance are preserved.

Do not merge until all automated, migration, role-boundary, and manual
acceptance gates pass.
