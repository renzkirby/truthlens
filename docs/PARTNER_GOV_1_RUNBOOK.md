# PARTNER-GOV-1 — owner-managed specializations and subject-only classification

Status: **development rollout and classifier shadow evaluation pending**.
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
provenance. Classifier `v3-persisted-subject` requires exact supporting quotations,
abstains on uncertain/unsupported subjects, and reads persisted `Claim.context_text`
from TEXT, URL, IMAGE, and FILE claims. URL/IMAGE/FILE inputs are eligible only
after the existing verification/extraction pipeline stores usable claim text:
URLs, image links, bare filenames, AI verdicts, and arbitrary article content
are NOT treated as classification evidence. Input outside 20–2400 characters
abstains. Geographic evidence is neither required nor inferred.

Classification is **claim-level**, not dependent on a community thread. Once
the factual-verification pipeline persists claim text/results, it queues the
separate subject-classification Celery task **after database commit**. This
includes ordinary saved factual analysis and early authoritative publication
resolutions that persist claim text. Verification, caching, and publication
never wait for the classifier. A community thread can additionally trigger
an idempotent fallback for a previously analyzed claim, but is not required.
For URL/IMAGE/FILE claims, wait until usable extraction/OCR text is persisted.
Repeated assessment of identical claim text/version is idempotent and will
not consume extra provider tokens. A shadow candidate is **never automatically promoted**
to authoritative status merely by switching to enforce. Changed claim text
can be assessed anew, subject to claim/assignment locks; existing
authoritative classification is preserved rather than silently overwritten.
No manual platform-level classification/retry workflow has been reintroduced.

For existing claims, `queue_investigation_classifications` is a bounded,
operator-triggered batch queue command. It is dry-run by default and includes
claims with stored text **even when they have no thread or assignment**. It
skips already classified and ACTIVE/COMPLETED assigned claims. Bulk enqueue
is intentionally permitted only in `shadow` mode to prevent unreviewed
retroactive authority. It does not itself assign subjects.

### Shadow evaluation before enforcement

1. Set `INVESTIGATION_CLASSIFICATION_MODE=shadow` in the isolated development
   environment (web server **and** Celery worker), and restart both. Keep
   production `off`. Ensure Redis/Celery and existing Gemini/Groq API keys
   are configured; classification is a separate provider operation.
2. Analyze a fresh TEXT claim **without creating a thread** and inspect its
   `InvestigationClassificationAssessment`. For supported claims, expect
   `SUGGESTED` with candidate subject codes, an explicit
   `candidate_primary_subject` contained in those codes, and
   `candidate_jurisdiction=""`;
   for insufficient/ambiguous claims expect `ABSTAINED` or `FAILED`.
   There must be **no** `ClaimInvestigationClassification` row in shadow and
   no new eligibility in partner intake.
3. Test URL, IMAGE, and FILE claims without community discussions after their
   extraction pipeline stores claim text. Missing extraction should safely abstain.
   Confirm claim verdict and publishing state remain unchanged.
4. Preview historical claims with `python manage.py queue_investigation_classifications
   --limit 10`. To enqueue a SMALL development sample in shadow mode only,
   use `python manage.py queue_investigation_classifications --enqueue --limit 10`.
   A running worker is required; this may invoke paid LLM APIs.
5. Independently label a representative held-out sample of factual claims
   across all 12 subjects, multi-subject claims, ambiguous/nonfactual inputs,
   adversarial prompt-injection content, Philippine and international
   examples, and all persisted input types. Compare exact subject-set match,
   explicit primary-subject accuracy, per-subject precision/recall,
   unsupported quote rate, and abstention and
   provider-failure rates. Record disagreements and model version. **Do not
   infer classifier accuracy from mocked unit tests or a few demos.**
6. Require a separate explicit accuracy-review and rollout decision before
   switching any environment to `enforce`. Enforcement creates system-audited
   authoritative subject classifications only on successful quoted-evidence
   validation, and still checks partner specialization authorization.

The latest assessment record is retained for internal diagnostics. A
separate policy is needed before automatically reclassifying authoritative
records on material claim-context changes; this rollout does not silently
rewrite historical classifications or adjudications.

## Required local test gates (Windows)

From `backend\truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run --settings=truthlens_backend.test_settings
..\.venv\Scripts\python.exe .\manage.py check --settings=truthlens_backend.test_settings
..\.venv\Scripts\python.exe .\manage.py test api.tests.organization.test_verification_scope api.tests.organization.test_verification_scope_migration api.tests.verification.test_investigation_classifier api.tests.verification.test_classification_backlog_command api.tests.workspace.test_assignment_service --settings=truthlens_backend.test_settings --keepdb
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
