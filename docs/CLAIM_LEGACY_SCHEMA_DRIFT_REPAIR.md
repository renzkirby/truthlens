# Legacy Claim `relatedness_context` schema repair

## Observed failure

A controlled development TEXT canary on branch
`feat/cloudflare-multistage-provider` failed at
`Claim.objects.create` **before** the AI pipeline could run.
PostgreSQL raised `NotNullViolation` for `api_claim.relatedness_context`.

The user ran a read-only PostgreSQL introspection against the database
actually used by Django:

```text
RELATEDNESS COLUMN: [('relatedness_context', True, None)]
UNMODELED REQUIRED COLUMNS WITHOUT DEFAULTS: ['relatedness_context']
```

The current `api.models.Claim` and all committed Django migration state
do not define `relatedness_context`. `migrate --plan` on the existing
local DB showed no pending operations **before** this repair.

## Targeted, data-preserving repair

Migration `0086_relax_unmodeled_claim_relatedness_not_null` is
dependent on `0085_organization_specializations`. If **PostgreSQL**
has the unmodeled column, it is NOT NULL and has no default, the migration
executes only:

```sql
ALTER TABLE "api_claim" ALTER COLUMN "relatedness_context" DROP NOT NULL;
```

The column remains, and all existing data remains unchanged. A fresh
schema without the column is a no-op. Already nullable columns and columns
with server-side defaults are no-ops. The migration does not alter Django
model state, Cloudflare provider routing, claim verification semantics, or
existing verdicts. SQLite is deliberately a no-op. Its reverse is a no-op
because reimposing NOT NULL after nullable inserts could break data.

**Important:** Unmodeled does not automatically mean unused outside Django.
If a co-developer or direct SQL client owns this column or depends on the
constraint, review that dependency before applying the migration.
Take the project's standard database backup/snapshot before schema changes,
especially outside your disposable local development database.

## Validation

On a clean local branch:

```powershell
git fetch origin
git switch --track origin/fix/claim-legacy-relatedness-nullability
cd backend\truthlens_backend
```

From `backend/truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_claim_legacy_schema_repair `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_cloudflare_multistage_provider `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
..\.venv\Scripts\python.exe .\manage.py migrate --plan
```

After the tests pass and the DB backup/co-developer schema ownership
check, apply the migration **only to the intended local development DB**:

```powershell
..\.venv\Scripts\python.exe .\manage.py migrate
```

Validate the constraint **read-only** using Django:

```powershell
..\.venv\Scripts\python.exe .\manage.py dbshell
```

Then in PostgreSQL:

```sql
SELECT attname, attnotnull
FROM pg_attribute
WHERE attrelid = 'api_claim'::regclass
  AND attname = 'relatedness_context'
  AND NOT attisdropped;
```

Expected on affected DB: `attnotnull = false`. A blank result on
a fresh DB is valid.

Only after this confirmation retry **one** development TEXT claim,
with 2048 final completion tokens unchanged. Do not submit another
live provider request until the DB insert succeeds.

No PR/merge, production rollout or destructive data change is
authorized as part of this checkpoint.
