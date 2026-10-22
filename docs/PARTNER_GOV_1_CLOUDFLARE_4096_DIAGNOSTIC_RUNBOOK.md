# PARTNER-GOV-1 — Cloudflare-03 single-case 4096-token diagnostic

**Implementation staged 2026-10-22; new mocked tests NOT YET locally run.
Cloudflare-03 is NOT authorized for live inference.**

## Why a different diagnostic is needed

The user ran the *separately authorized* Cloudflare-02 four-case capture,
which stopped after the FIRST case, `cross_spacecraft`:
`PROVIDER_FAILED`, `EMPTY_PROVIDER_RESPONSE`, `finish_reason=length`,
`reasoning_present=true`, `completion_tokens=1024` (exact old cap),
`prompt_tokens=176`, `duration_ms=19465`. No useful JSON was returned.
This is an **output-budget reliability failure**, not a scored subject-
classification error. The provider did not report a reasoning token
count, so the split between reasoning and final output is unknown.

**Never remove or reuse the permanent Cloudflare-02 lock.** A request
was attempted and could have consumed Cloudflare allowance or charges.
Previous authorization does NOT transfer to Cloudflare-03.

## Fixed Cloudflare-03 profile (NO change to production routing)

| Field | Diagnostic |
| --- | --- |
| Model | `@cf/google/gemma-4-26b-a4b-it` |
| Test case | `cross_spacecraft` only |
| Provider attempts | 1 maximum for one *new* private packet |
| Completion token budget | **4096** |
| HTTP | (3 seconds connect, 45 seconds read-inactivity) |
| Temperature | 0.1 |
| Response | JSON object, non-streaming |
| Capacity option | `rejectIfBusy=true` |
| Retries | none |
| Gemini or Groq fallback | never |
| System prompt | Existing, unmodified `classification_system_prompt()` |
| Input | Exact persisted claim text from separately approved local corpus |
| Writes | Local private output files ONLY; no ORM/Celery/database |
| Enforcement | never enabled |

The adapter already allows 256–4096 completion tokens; no change was
needed in `cloudflare_evaluation.py` or production pilot
`cloudflare_pilot.py`, which **still defaults to 1024** for its
separate development classification pilot. The earlier four-case
Cloudflare-02 runner also remains at **1024**. This experiment must not
alter factual-verification max tokens, provider priority, RAG evidence
retrieval, adjudication decisions, or Partner Organization permissions.

45 seconds is a **socket-inactivity timeout, NOT a guaranteed total
wall-clock deadline**. The 4096 token budget is a generation ceiling,
not a quota/spending-limit enforcement mechanism. Cloudflare publishes
`$0.10 / million input tokens` and
`$0.30 / million output tokens` for this model (as checked 2026-10-22;
current rates/account quota should be reconfirmed before any live call).
As a *hypothetical* example, 176 input tokens and 4096 output tokens
would cost about **$0.0012464 USD** nominally, before plan allocations
and without guaranteeing billed usage, timing, or model response.

References:
- https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/
- https://developers.cloudflare.com/workers-ai/platform/pricing/

## Source changes

- `api/verification/cloudflare_classification_diagnostic.py`:
  new immutable `gemma4_one_case_4096_v1` profile, strict local approved
  corpus and profile-bound manifest validation, dry-run-first direct
  capture, and one-use permanent lock. Reuses existing Cloudflare
  adapter and sanitized usage metadata.
- `api/management/commands/prepare_cloudflare_classification_diagnostic.py`:
  **OFFLINE** prepare a new 1-case private packet. Refuses an existing
  directory or non-approved 32-case corpus. No reference labels are
  exported into provider-input manifest.
- `api/management/commands/capture_cloudflare_classification_diagnostic.py`:
  defaults to OFFLINE dry run. All live-use switches are gated,
  independent of Cloudflare-02's. **Do not activate them yet.**
- `api/tests/verification/test_cloudflare_classification_diagnostic.py`:
  **19 new mocked, no-DB tests**, including output-budget exhaustion,
  identical prompt, one adapter request, no fallback, immutable private
  profile, sanitization, independent permission and one-use semantics.

The 4096 profile's own output files are:
- `cloudflare_diagnostic_raw_responses.json`: full returned
  `message.content` strings, even when not valid JSON.
- `cloudflare_diagnostic_predictions.json`: scorer-ready responses
  up to 8000 characters; malformed raw responses are NOT silently
  fixed or converted to abstentions.
- `cloudflare_diagnostic_attempts.json`: sanitized request and
  usage metadata including `reasoning_present`, `reasoning_tokens`
  if provider reports it, finish reason, duration, status and safe errors.
- `cloudflare_diagnostic.lock`: never remove or reuse after live attempt.

The generic initial `predictions.json` remains an **empty template**
after both preparation and any execution. The original Cloudflare-02
private packet remains untouched. Privacy: never paste API tokens,
private raw responses, claim texts, or model reasoning into GitHub or
public logs.

## Offline acceptance only — PowerShell commands

Run from `backend\truthlens_backend` after fast-forwarding a **clean**
local `feat/ai-rq2-provider-hierarchy` branch:

```powershell
$corpus = "$env:USERPROFILE\Downloads\PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json"
$packet03 = "$env:USERPROFILE\Documents\TL-Private-Classification-Cloudflare-03"

# Offline simulated HTTP only (mocked). NO live Cloudflare calls.
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_classification_diagnostic `
  api.tests.verification.test_cloudflare_classification_capture `
  api.tests.verification.test_classification_capture_preparation `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_classification_latency_policy `
  --settings=truthlens_backend.test_settings --keepdb

# New directory must not already exist. This writes only local empty
# templates and the one approved input, without inference.
..\.venv\Scripts\python.exe .\manage.py prepare_cloudflare_classification_diagnostic `
  --corpus "$corpus" `
  --export-dir "$packet03" `
  --json-summary

# Validates package, prompt fingerprint and fixed config; NO requests.
..\.venv\Scripts\python.exe .\manage.py capture_cloudflare_classification_diagnostic `
  --corpus "$corpus" `
  --packet-dir "$packet03" `
  --json-summary

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

Expected prep: `PRIVATE_DIAGNOSTIC_PREPARED_NO_PROVIDER_CALLS`,
`planned_requests=1`, `max_completion_tokens=4096`,
`case_ids=["cross_spacecraft"]`, with the same approved corpus hash
`40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af`.
Expected dry run: `DRY_RUN_READY_NO_PROVIDER_CALLS`, one case, 4096
completion tokens, 45 seconds read-inactivity, `provider_calls=0`,
`fallback_enabled=false`, `retry_enabled=false`,
`enforcement_approved=false`. **No diagnostic lock or output files
are created in a dry run.**

If the folder name already exists, **do not overwrite it**: choose a
fresh private path and update `$packet03`.

## Cloudflare-03 completed; follow-on paired study is OFFLINE ONLY

The user later authorized and executed the one permitted Cloudflare-03
live request. `cross_spacecraft` returned `CAPTURED_VALID`,
`finish_reason=stop`, 829 completion tokens,
`reasoning_present=true`, and an exact SCIENCE + TECHNOLOGY
human-review reference match in ~8.821 seconds. The private offline
audit reported **1 scored, 1 exact match, 31 missing**; full-corpus
accuracy is undefined. The prior Cloudflare-02 1024-cap failure and
Cloudflare-03 4096-cap success are NOT proof of a causal budget effect,
because the successful 4096 request consumed just 829 tokens.
**Cloudflare-03 is permanently used and must never be unlocked.**

The next step is a **separate, no-network, four-case paired 1024 vs
4096 study with two repetitions per arm**. It plans 16 potential
future trials, but creates no live executor or permission. See
`docs/PARTNER_GOV_1_CLOUDFLARE_PAIRED_BUDGET_BENCHMARK.md`.
All live requests require a new explicit authorization following
mocked regression acceptance.

## Gate for an actual Cloudflare-03 request — NOT YET APPROVED

After the 19 new mocked tests, the existing offline suites and the
exact package dry run pass, we must review these outputs and obtain
**fresh, explicit user authorization** for this one 4096-token request.
Only then may the distinct dev-only opt-in and live confirmation be
used. This runbook intentionally contains NO live request invocation.

A 1-case synthetic reliability test, whether successful or not,
does not prove accuracy across the 12 subject domains. Even after
successful capture, the offline 32-case scorer will report 31 missing
references and no complete-corpus accuracy rate. `enforce` remains
NOT APPROVED.
