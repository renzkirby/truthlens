# TruthLens — Cloudflare end-to-end text & URL acceptance

**Status: Prepared, not yet executed live. Branch:
`feat/cloudflare-verification-pilot`.**

Goal: observe **one new TEXT claim and one new URL claim** in the local
development app, from submission through actual live retrieval/evidence
processing, persisted-evidence verdict evaluation (if reached), and terminal
VerificationRun/claim storage. This is intentionally different from the
previous shell test that called the final evaluator alone.

### Safety boundaries

- Use **only a local development database** and test accounts. This process
  creates real development claim/run/evidence records, may schedule
  classification and notifications, and consumes upstream API quotas
  (Cloudflare, Gemini/Groq, Tavily, GFC, and others depending on path).
- **Do not run with staging/production credentials or databases.**
- Never submit private claims, user-specific data, or real unreviewed
  allegations for this test. Use ordinary public-source factual claims.
- Max **one new TEXT** and **one new URL** submission in this initial
  manual canary; don't auto-retry or bulk-submit.
- `APP_ENV=development`, `DEBUG=True` and
  `ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1` must be in the **Celery worker's
  environment before that worker starts**. Setting the flag only in a
  separate Django shell does **not** update an already running worker.
- Gemini/Groq remain the original providers for upstream AI operations,
  and the fail-safe fallback for this one final verdict stage.
- Never interpret a skipped Cloudflare call as a Cloudflare failure: prior
  authoritative fact checks, cache hits, out-of-scope or missing evidence
  can bypass the persisted-evidence evaluator completely.
- Cloudflare uses a single call, 2,048 completion-token allowance and
  (5s connect, 45s read) timeout. If it fails, Gemini then Groq may be
  called, so an end-to-end test can greatly exceed 45 seconds.
- No source-grounding or provider promotion decision follows from two
  tests alone; preserve the documented 10 reviewed source-dossier cases.

## Cloudflare 0 ms failure diagnostics (Oct 21, 2026)

The first live TEXT canary after duplicate-worker cleanup recorded an
immediate Cloudflare failure (duration 0 ms), then a successful Groq
fallback; the workflow itself completed. The developer shell subsequently
showed development mode and pilot enabled, a valid-format account ID and a
present token; a read-only reconstruction of the stored evidence was
10,456 characters versus the 28,000-character adapter limit. Those shell
observations **do not prove the effective worker environment**.

From this branch onward, the development Celery worker logs a safe startup
line (no network calls or key values), for example:

```text
CLOUDFLARE_PILOT_WORKER_READY pid=12345 enabled=True account_id_valid=True api_token_present=True
```

Check the **actual worker's INFO log** after restarting it with the pilot
flag; if any status is false, resolve worker launch configuration before
spending any API quota. The flags show presence/format only, not token
authorization or quota availability.

New Cloudflare failures are categorized through a finite safe-code
allowlist: e.g. `MISSING_API_TOKEN`, `PROMPT_TOO_LONG`, `HTTP_429`,
`TRANSPORT_ReadTimeout`, `INVALID_EVALUATION_JSON`. The run inspector
prints `reason=<code>` on a failed Cloudflare event. Exception bodies,
provider response text, claim content, credentials and raw error details
are **never forwarded**. Previous telemetry cannot be retroactively
decoded: those runs will show `reason=not_recorded`.

The worker startup status confirms flags/credentials in the effective
worker process, and the next **separately approved, single** live canary
can reveal the sanitized failure reason if Cloudflare fails again. Do
not run repeated claim attempts merely to fill telemetry.

## Offline Celery runtime probe — for startup/runtime configuration disagreement

A subsequent live TEXT task (2026-10-21 01:57–01:58 local) showed a
startup worker log with account ID valid and API token present, but the
Cloudflare adapter rejected the account ID locally about 37 seconds
after the task started. Groq then returned a rate-limit response and
the final evaluator raised `LLMProviderUnavailableError`.

**Do not retry claims or spend provider quota to investigate this.**
The original adapter validates `os.getenv("CLOUDFLARE_ACCOUNT_ID", "")`
at request time, and a startup status does not guarantee its value
remains unchanged. The reason for this mismatch is not yet known.

An explicit, development-only Celery task now captures the **actual
worker process's current configuration status**, independent of any
verification claim and with no AI-provider HTTP calls, DB writes, or
sensitive environment values. After pulling the latest pilot branch
and running the new offline tests, stop the idle worker and restart
exactly one `start_celery` worker. With that worker running, in a
**separate PowerShell window** under the normal development settings:

```powershell
..\.venv\Scripts\python.exe .\manage.py shell
```

```python
from api.tasks import inspect_cloudflare_pilot_worker_environment

task = inspect_cloudflare_pilot_worker_environment.delay()
print(task.get(timeout=15))
```

The `.delay()` is essential: calling `.run()` directly would inspect
the Django shell process instead of the Celery worker. Results show
only `diagnostics_available`, `worker_pid`, `pilot_enabled`,
`account_id_valid`, `api_token_present` booleans/IDs. Example:

```text
{'diagnostics_available': True, 'worker_pid': 57800,
 'pilot_enabled': True, 'account_id_valid': False, 'api_token_present': True}
```

Compare `worker_pid` against the startup readiness PID, and interpret
a false account-ID result as evidence of changed/missing runtime
credentials in *that* process. If the runtime values are still true,
the earlier failure was transient or from another context; investigate
before submitting another claim. No evidence of Cloudflare billing
can be inferred from rejected local preflight.

Then exit the shell. Use `inspect_verification_run_telemetry` for the
failed run ID to verify terminal `FAILED` and
`failure_code=LLM_UNAVAILABLE`, not a user-facing fabricated verdict.

## Dev-pilot only: oversized persisted evidence without source loss

Live TEXT canary run `9c4d0ad2-ebbc-47b6-8e45-cd7043f7fc5e` failed at
the final evaluator: persisted SECONDARY dossier **7 identity groups /
12 evidence items**, all stances tagged SUPPORTS (not independently
confirmed); original dossier **27,732 chars** and reconstructed prompt
**29,606 chars**, exceeding Cloudflare's **self-imposed 28,000-char
adapter preflight** by **1,606 chars**. Cloudflare did not send HTTP,
and Groq then hit 429 and 413 limits. The original SOURCE IDENTITY
GROUP renderer deliberately preserves all source evidence, so **do not**
simply truncate or omit a contradictory/independent source.

An optional dev-pilot-only formatting path in `api/tasks.py` now
checks the full system+user prompt size **before** provider routing.
If under the limit, it returns the byte-identical original dossier,
so unaffected runs and production behave exactly as before. If over,
it uses `render_compact_reasoning_evidence_dossier`, which retains
every evidence item and each `content` string, source-group boundary,
source URL/canonical URL, title, provider, publisher, source type,
stance, evidence role, dates, and scores. Only the repeated metadata
field labels become a once-only positional JSON-array schema.
There is no source deletion, summarization, source reordering, or
source-stored-record mutation. If neither the positional compact dossier nor the second lossless
shared-metadata rendering fits, it **fails closed** with `LLMProviderUnavailableError` before
attempting any over-budget final provider request. Keep the pilot
disabled in staging/production.

The second-stage format retains all original source text and metadata. It
references repeated string/date values through explicit numbered DEFAULTS,
and represents a canonical URL equal to its own URL with an unambiguous
numeric reference. Scores remain literal. Its source-group and evidence-item
markers are identical to the first compact format. This format is only
attempted if the positional compact format still exceeds the pilot budget.
Reference decoding and mixed-stance preservation have focused offline tests.
This is not evidence of model-level interpretation accuracy.

Before another live TEXT/URL canary, first run offline regression tests
and a read-only check using this exact existing failed run. From
`backend/truthlens_backend` after pulling, run:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_pilot_evidence_budget `
  api.tests.verification.test_evidence_dossier `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  --settings=truthlens_backend.test_settings --keepdb
```

For the read-only probe (no model calls, no claim/evidence writes),
open Django shell, then:

```python
from unittest.mock import patch
from django.test import override_settings
from api.models import VerificationRun, VerificationEvidence
from api.services import build_persisted_evidence_prompt, LLMProviderUnavailableError
from api.verification.evidence_dossier import (
    load_reasoning_evidence_dossier_for_run,
    filter_reasoning_evidence_dossier_by_role,
    render_reasoning_evidence_dossier,
)
from api.tasks import _render_bounded_persisted_evidence_context

run = VerificationRun.objects.get(pk="9c4d0ad2-ebbc-47b6-8e45-cd7043f7fc5e")
groups = filter_reasoning_evidence_dossier_by_role(
    load_reasoning_evidence_dossier_for_run(run),
    VerificationEvidence.EvidenceRole.SECONDARY,
)
original = render_reasoning_evidence_dossier(groups)
claim_text = run.claim.context_text or ""
system, user = build_persisted_evidence_prompt(claim_text, original, "NEUTRAL")
print("original_full_prompt_chars", len(system) + len(user))
try:
    with (
        patch.dict("os.environ", {"ENABLE_CLOUDFLARE_VERIFICATION_PILOT": "1"}),
        override_settings(APP_ENV="development", DEBUG=True),
    ):
        compact = _render_bounded_persisted_evidence_context(
            groups, claim_text, "NEUTRAL",
        )
    system, user = build_persisted_evidence_prompt(claim_text, compact, "NEUTRAL")
    print("budgeted_full_prompt_chars", len(system) + len(user))
    print("all_item_contents_present", all(
        compact.count(item.content) >= 1
        for group in groups for item in group.evidence
        if item.content is not None
    ))
    print("source_group_markers", compact.count("=== SOURCE IDENTITY GROUP "))
    print("item_markers", compact.count("--- EVIDENCE ITEM "))
except LLMProviderUnavailableError:
    print("NO_LOSSLESS_FIT: fail closed; do not retry live verification")
```

The original cleaned text/stance from the live run may differ
slightly from the persisted claim context/NEUTRAL used above.
**Acceptance:** budgeted prompt at most 28,000 chars, all group/item
markers present (7/12), every original source content present,
and relevant unchanged/compacted runtime tests green. The probe
does NOT measure model accuracy or imply that all SUPPORTS
classifications are correct. If budget still fails, do not adjust
provider routing or hide contrary evidence; evaluate further
lossless transport/metadata options with human review first.

## Controlled Cloudflare-only single-request worker smoke

**Purpose:** Establish whether the actual current Celery worker can perform
one Workers AI inference and return the reviewed verdict. Do this **before**
another complete text or URL verification while Gemini 402 and Groq 429
remain unresolved. This is not evidence of production accuracy.

The test uses the exact persisted-evidence production prompt from a
side-effect-free `build_persisted_evidence_prompt` constructor and the
fixed, reviewed **public** `civics__support` case from the existing
`realworld_verification_cases.json` corpus. Expected label: `FACT`.
It performs no claim/evidence DB queries or writes, web searches,
Gemini/Groq fallback or other provider calls. Raw prompt, evidence,
reasoning, HTTP errors and credentials are not returned or logged.
The task is configured with no automatic retries and `acks_late=False`.
An explicit command launches **exactly one** Celery task and a task
attempts zero or one Cloudflare HTTP request (5s connect/45s read timeout).

### Prepare

1. On the pilot branch, wait for existing tasks to complete; stop the
   old development Celery worker so it reloads the latest code.
2. Pull/fast-forward the branch. In `backend/truthlens_backend`, run:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_worker_smoke `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_cloudflare_verification_pilot `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

3. Make sure local `.env` contains Cloudflare account ID and token,
   **never paste or commit their values**. Keep the existing
   pilot flag temporary. In the shell starting **one** Celery worker:

```powershell
$env:APP_ENV = "development"
$env:DEBUG = "True"
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"
..\.venv\Scripts\python.exe .\manage.py start_celery
```

Verify startup shows `enabled=True account_id_valid=True
api_token_present=True` (only presence/format, not authorization),
and check the registered task list includes
`api.tasks.cloudflare_single_request_smoke`. No duplicate workers.

### Dry run then one authorized request

In a separate PowerShell session, from `backend/truthlens_backend`:

```powershell
$env:APP_ENV = "development"
$env:DEBUG = "True"
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"

..\.venv\Scripts\python.exe .\manage.py cloudflare_worker_smoke
```

Dry run returns `DRY RUN` without enqueuing anything or using quota.

Only after the new offline tests pass and Celery readiness is confirmed,
run **once**:

```powershell
..\.venv\Scripts\python.exe .\manage.py cloudflare_worker_smoke `
  --live --confirm-one-request
```

This sends exactly one Celery job (one or zero provider requests)
and waits up to 70s for a result. The output is limited to
worker PID, boolean account/token readiness, pilot status, fixed
case ID, attempt count, latency, status, safe error code or validated
verdict/confidence and whether it matches the preapproved label.

If the command waits 70s and times out, do **not** requeue it:
inspect the task ID and current worker output; the original task
may still be running. If `account_id_valid=False` at request time,
Cloudflare HTTP is never sent; investigate environment drift across
processes. If `HTTP_402`, `HTTP_403` or `HTTP_429`, stop and
resolve quota/authorization; no blind retries. If the model emits
invalid JSON, record the sanitised failure and review locally.
A single matching verdict is a smoke-test result, **not a production
quality conclusion**. Do not enable staging/production.

## 1. Offline test gate — flag OFF

In PowerShell from repository root, on a clean branch:

```powershell
git fetch origin
git switch feat/cloudflare-verification-pilot
git merge --ff-only origin/feat/cloudflare-verification-pilot
```

In `backend/truthlens_backend`:

```powershell
Remove-Item Env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT -ErrorAction SilentlyContinue

..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_verification_run_telemetry_inspection `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_llm_reliability `
  --settings=truthlens_backend.test_settings `
  --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

The new text/URL tests use mocked upstream retrieval but the actual
persisted-evidence evaluator and Cloudflare routing. They assert that
successful JSON produces one completed run, persisted AI verdict and
sanitized provider telemetry; a simulated all-provider outage fails the
run with `failure_stage=final_evaluator`,
`failure_code=LLM_UNAVAILABLE`, and **no AI verdict**.
These tests are not live end-to-end calls.

## 2. One controlled live TEXT claim

After all tests pass and with the local development stack ready:

1. Confirm the **development database** and test user are selected.
2. Stop the *development Celery worker*, set the three environment
   variables in its launch shell, then restart that worker with its usual
   project-specific startup command:

   ```powershell
   $env:APP_ENV = "development"
   $env:DEBUG = "True"
   $env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"
   ```

   Set `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` privately in
   that worker environment if not already present. **Do not share keys.**
   Other stack services (Django, Redis/broker, frontend, etc.) follow
   your existing local run procedure. Do not invent new service commands.
3. From the development app's normal verification entry point submit
   **one newly worded public-source text claim**, for example:
   `Apple announced the original iPhone in January 2007, with US
   availability planned for June 2007.` The official Apple 2007
   newsroom release may be consulted as a source:
   <https://www.apple.com/uk/newsroom/2007/01/09Apple-Reinvents-the-Phone-with-iPhone/>.
   Do not assume a particular verdict if the retrieved evidence differs.
4. Record the returned/new claim UUID and the **actual VerificationRun
   UUID**. If a cache/previous verified result short-circuits retrieval,
   do not repeatedly submit variants: record as a bypass and discuss.

## 3. One controlled live URL claim

After reviewing the TEXT result, use the app's URL submission flow
with **one stable public-source article URL**, for example the Apple
newsroom page above. URL extraction is upstream of Cloudflare; it may
fail, use an authoritative publication, or resolve without entering the
persisted-evidence evaluator. Record such a result accurately rather
than forcing the verdict stage.

Do not test arbitrary paywalled/private/profile URLs, local network URLs,
or untrusted user-specific material. Record claim/run IDs separately
from the text case. Stop after this single URL attempt.

## 4. Read-only lifecycle/provider timing inspection

For either claim, get its latest run ID using Django shell in the
development backend (do not print claim text or account details):

```python
from api.models import VerificationRun

claim_id = "REPLACE_WITH_SUBMITTED_CLAIM_UUID"
run = VerificationRun.objects.filter(claim_id=claim_id).order_by("-created_at").first()
print("run_id:", str(run.pk) if run else "no run")
```

Exit Django shell. From `backend/truthlens_backend` with normal
development settings (NOT the test settings), inspect each run ID:

```powershell
..\.venv\Scripts\python.exe .\manage.py inspect_verification_run_telemetry `
  --run-id REPLACE_WITH_VERIFICATION_RUN_UUID
```

This **reads** run metadata and telemetry only. It prints status,
total lifecycle duration when available, failure stage/code, and each
sanitized `STAGE` and `PROVIDER` duration. The stage spans can be
nested/overlapping and **should not be added together**.
No URLs, evidence contents, prompts, claim text, provider reasoning, user
profiles, credentials, or raw provider errors are printed.

Check the output:

- If `PROVIDER name=persisted_evidence_evaluation provider=cloudflare
  outcome=success`: Cloudflare handled the final persisted verdict call.
- If `cloudflare ... failed` followed by `gemini` or `groq ...
  success`: safe fallback was used; measure combined latency.
- If no `cloudflare` provider event appears: the persisted-evidence
  stage may not have been reached (or the worker never had the pilot
  flag). Inspect stage names and worker environment before concluding.
- `FAILED`, `failure_stage=final_evaluator`,
  `failure_code=LLM_UNAVAILABLE` indicates all final-stage providers
  failed. Confirm the claim has no fabricated substantive AI verdict.
- `ABSTAINED` with no provider error may represent a genuine
  insufficient-evidence or out-of-scope outcome, **not** an outage.
- Evaluate source provenance and explanation quality separately; one
  generated verdict is never proof of factual accuracy.

## 5. Roll back immediately after the two-case pilot

Stop the development Celery worker. In its original launch shell run:

```powershell
Remove-Item Env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT -ErrorAction SilentlyContinue
```

Restart the worker in its normal development configuration and make sure
no earlier process still has the flag. Likewise clear the flag from any
Django-shell/test PowerShell process. **Do not set it in .env files** or
shared deployment configuration.

The pilot does not require migrations or data rollback; completed dev
claim records remain as normal test artifacts. Do not erase records
blindly. Production routing remains Gemini -> Groq.

## 6. Stop / follow-up criteria

Stop and report if a timeout sends total run duration beyond the
acceptable user experience; if the API returns 402/429; if an
unexpected error causes a user-visible false `UNVERIFIED`; if a claim
is marked COMPLETED without a valid saved substantive verdict; if
source citations are untraceable; if provider timing is missing; or if
the URL pipeline fails to extract the source.

Before any merge, staging or production proposal: verify live full
workflow parity including **image verification where applicable**,
request/Neurons budgets, cross-worker rate limiting and circuit breakers,
scoped retries, resilience to upstream Gemini/Groq outages, privacy and
telemetry boundaries, reviewer adjudication, and operational rollback.
This initial two-case pilot is NOT that full acceptance.
