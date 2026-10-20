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
