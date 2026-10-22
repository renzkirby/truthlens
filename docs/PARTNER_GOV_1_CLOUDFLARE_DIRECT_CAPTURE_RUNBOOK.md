# PARTNER-GOV-1 — Cloudflare direct classification capture runner (PENDING LOCAL TESTS)

**Prepared 2026-10-22, branch `feat/ai-rq2-provider-hierarchy`.**
No real provider calls have been run or authorized in this implementation.
There is **NO** model accuracy result, `enforce` is **NOT** authorized,
and the default bundled 32-case corpus remains **PENDING**.

The user approved **32 local review references** and generated
`Documents\\TL-Private-Classification-Cloudflare-02` with:
- `provider=cloudflare`
- `model_id=@cf/google/gemma-4-26b-a4b-it`
- `case_ids=[cross_spacecraft,cross_school_sport,ambiguous_plan,injection_civic]`
- `approved_references_in_source=32`
- `corpus_sha256=40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af`
- `provider_calls=0`, `db_writes=0`, `predictions_captured=0`.

## Implementation scope

- `api/investigation_classifier.py::classification_system_prompt`:
  extracted the existing exact prompt into a pure helper; runtime
  `_query_classifier` calls the same helper. The prompt words and
  code list are **unchanged**; no different benchmark-only prompt.
- `api/verification/cloudflare_classification_capture.py`:
  deterministic private-packet validation, offline dry run, explicit
  dev-only opt-in, **fixed MAX_LIVE_CALLS=4** and a direct call to
  `cloudflare_evaluation.generate_evaluation_json`, bypassing
  `call_llm_with_fallback` entirely. No Gemini, Groq, Celery, ORM,
  factual verdict or Partner Organization permission logic.
- `api/management/commands/capture_investigation_classification_cloudflare.py`:
  dry-run CLI by default; **live path is separately gated and not
  authorized for use yet**.
- `api/tests/verification/test_cloudflare_classification_capture.py`:
  12 new mocked tests (some exercise the real adapter with mocked
  `requests.post`). **Local execution is pending.**

## Safeguards and limitations

**Before any request**, the runner requires a local independently
approved 32-case review JSON, the exact pristine four-case private
Cloudflare-02 packet, one exact model ID, identical claim text and
SHA-256 digests, matching normalized approved-corpus SHA-256, unchanged
case order, and a still-empty `predictions.json` template.
It rejects changes, missing/unknown case IDs, the pending GitHub
fixture, and reused/interrupted packets; all result files must not
exist yet. A private packet must be outside the Git checkout.

**Default is an offline dry run**: it validates the packet and
reuses the exact production system prompt without contacting Cloudflare.
The live function **only executes** when all three distinct conditions
are met: `APP_ENV=development` and `DEBUG=True`; an exact separate
environment opt-in to allow this capture; and the CLI's explicit
live-execution flag plus exact confirmation phrase. The command will
never set these gates for you. Do **not** turn them on without a
new, clear user authorization for live requests.

A live run has **no retries** and no Gemini/Groq fallback. The
single-provider adapter uses `model=@cf/google/gemma-4-26b-a4b-it`,
`temperature=0.1`, `response_format=json_object`,
`max_tokens=1024`, `stream=False`, `options.rejectIfBusy=True`,
and `http_timeout=(3,30)`. A socket read timeout **is not a hard
wall-clock deadline**. There is one potential request per selected case
and a hard **four-call ceiling per packet**; using a different
new packet is a separate experiment requiring separate authorization.

**One-time packet use:** An exclusive lock is created BEFORE calling
any provider. It remains after success, failure, power loss or process
interruption. Never delete that lock to replay an interrupted packet;
a billable request might have already reached Cloudflare. The runner
creates private output files before its first request and journals
`STARTED` before each one. A failure or invalid response stops the
remaining requests. An OS crash during a request can still cause an
uncertain charge; the lock prevents automatic repeat attempts.

**Unaltered provider text:** The adapter's original returned
`message.content` string is stored as `raw_response` exactly,
including invalid JSON and unsupported quotations. Do not fabricate
or normalize missing outcomes into `ABSTAIN`. Three private
packet-local output files are produced only on a separately authorized
live run:
- `cloudflare_raw_responses.json`: complete, original returned JSON
  content strings, including malformed or oversized outputs.
- `cloudflare_captured_predictions.json`: valid existing offline
  scorer format for captured responses of at most 8,000 characters;
  invalid-but-bounded JSON remains unmodified for scorer diagnostics.
- `cloudflare_capture_attempts.json`: attempted case IDs, input
  digests, prompt hash, request settings, elapsed milliseconds,
  sanitized adapter usage metrics, safe error codes, and stop status.

The original `predictions.json` template is left **EMPTY**.
Error bodies, authorization tokens, claim text and model responses
are never written to logs or printed by the command.
Raw response files are **sensitive** and must remain private.
Do not commit or upload these files to GitHub.
The runner intentionally does not measure model accuracy itself;
use the existing offline scorer later after separate live authorization.

## First acceptance: Run ONLY the dry-run and mocked tests

From `backend\\truthlens_backend` with your existing approved
reference corpus in Downloads and the existing Cloudflare-02 packet:

```powershell
$corpus = "$env:USERPROFILE\\Downloads\\PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json"
$packet = "$env:USERPROFILE\\Documents\\TL-Private-Classification-Cloudflare-02"

..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_cloudflare_classification_capture `
  api.tests.verification.test_classification_capture_preparation `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_classification_latency_policy `
  --settings=truthlens_backend.test_settings --keepdb

..\\.venv\\Scripts\\python.exe .\\manage.py capture_investigation_classification_cloudflare `
  --corpus "$corpus" `
  --packet-dir "$packet" `
  --json-summary

..\\.venv\\Scripts\\python.exe .\\manage.py check
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
```

Expected for the dry-run: `status=DRY_RUN_READY_NO_PROVIDER_CALLS`,
`planned_requests=4`, the same four case IDs, pinned model, and
`enforcement_approved=false`. **The dry run does not create the
capture lock or any `cloudflare_*` output files**.

The `test_cloudflare_classification_capture` unit test module uses
a **separate synthetic temporary approved corpus** and mocks the
transport; tests do not invoke actual Cloudflare.

## Future gate (NOT PART OF CURRENT USER APPROVAL)

Only after the mocked suite and packet dry run pass should a reviewer
inspect exact configuration, price/rate limits, desired stop policy,
Cloudflare access permissions, and capture privacy and explicitly
authorize **up to four** real direct-provider calls on that packet.
Only at that time should a separate operational command showing the
live opt-in and confirmation be provided. This document intentionally
does **not** provide a ready-to-run live command.

Existing assessment/final verdict pipeline and workspace authorization
must not change. A small synthetic safety canary is not an independent
real-claim accuracy study or authorization to enable
`INVESTIGATION_CLASSIFICATION_MODE=enforce`.
