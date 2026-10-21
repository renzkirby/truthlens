# AI-RQ-2 — Unified provider hierarchy (development-only checkpoint)

**Branch:** `feat/ai-rq2-provider-hierarchy` (based on unmerged
`fix/cloudflare-assessment-latency-guardrails`; includes preserved
PostgreSQL claim nullability repair). **No PR/merge, production rollout,
paid/live provider requests, or Django migration** were performed.

The separate October 19 panel remediation program remains **#126**
(AUTH-1 #127, PARTNER-GOV-1 #128, WORKSPACE-UX-1 #129,
WORKSPACE-GOV-1 #130, VERIFY-CLAIM-1 #131). Issue **#137** on
Google Fact Check metadata coverage/verdict integrity is delegated
separately to the verification-pipeline co-developer. This branch
must not change co-developer-owned retrieval, evidence content,
publication priority, or adjudication workflows.

## Why

Earlier Cloudflare-only development pilots started with Cloudflare for
eligible stages, sometimes waiting for a failed evidence-assessment
request before Gemini/Groq. We want an opt-in **Gemini -> Cloudflare
Workers AI (Gemma 4) -> Groq** route with strict per-operation
contracts, quota-aware job-scoped routing, and no model carousel.

The live Gemini 402 indicates a payment/credit problem until the user
restores the provider's availability. Do not increase billing
automatically or treat 402 as a recoverable rapid retry. Groq 429
may be rate-limit related to the account/model; automatically trying
multiple Groq models could make it worse. Our existing Groq default is
`openai/gpt-oss-120b`; this phase does not switch models or assume
one is more factually accurate.

## Activation (do not enable until offline tests pass)

The **new** flag defaults off and is honored **only** with
`APP_ENV=development` and `DEBUG=True`:

```powershell
$env:ENABLE_AI_RQ2_PROVIDER_HIERARCHY = "1"
```

Cloudflare remains separately gated to `persisted_evidence_evaluation`
and `evidence_assessment` with existing flags:

```powershell
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"
$env:ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT = "0"
Remove-Item Env:CLOUDFLARE_PILOT_FINAL_MAX_TOKENS -ErrorAction SilentlyContinue
```

**Recommended initial configuration** keeps Cloudflare evidence
assessment off because it has timed out on 9-item and **one-item**
live workloads. This does not turn it on in staging or production.
With Gemini 402, the new hierarchy may call Cloudflare for the
**final** persisted-evidence evaluation, if eligible. Other operations
continue Gemini -> Groq until Cloudflare's stage-specific contract
is implemented and tested.

Restart one correctly identified Celery worker after changing flags.
The sanitized `inspect_cloudflare_pilot_worker_environment`
task returns `ai_rq2_hierarchy_enabled` alongside the two
Cloudflare stage flags. This probe performs no provider request.

**When the new flag is OFF**, existing routing (including Cloudflare-first
development pilot) is deliberately unchanged. No backward
compatibility or legacy pilot settings need alteration.

## Contract and failure behavior

- Gemini is tried **first**, and its validated response is used when
  acceptable; no redundant Cloudflare/Groq call.
- Gemini HTTP **402/429** marks Gemini unavailable **only for that
  one scoped verification job**. This is not a global cooldown or
  billable provider health monitor. Other failures fall through normally.
- Cloudflare is tried **second only if that operation is already
  explicitly enabled**; strict schema checks must pass. Its existing
  scoped circuit breaker, no-duplicate-request design, <5-item
  assessment limit, strict keyed evidence batch, 28k-character
  preflight, and `(3,15)` small-batch connection/read timeout are
  retained. Final evaluation still has `(5,45)`, its original
  2048 output-token default, and a full persisted evidence dossier.
- The local Cloudflare assessment bypass retains **all evidence**
  unchanged for fallback and does not disable a later Cloudflare
  final evaluation. Genuine vendor errors do disable further
  Cloudflare attempts in that job.
- Groq is the **last** provider. In the new lane it uses
  `groq_client.with_options(max_retries=0)` to disable the SDK's
  automatic 429/5xx retries. One selected `GROQ_MODEL` is used;
  there is **no automatic model hopping**. The preexisting default
  `openai/gpt-oss-120b` remains unchanged.
- In the opt-in lane, **Gemini and Groq** must satisfy the existing
  final-verdict or evidence-assessment operation-specific response
  schema **even if Cloudflare was skipped/disabled**. Empty outputs
  are not treated as provider success. Claim-gate and other operations
  do not get a new Cloudflare route or unreviewed JSON schema.
- All attempted providers unavailable or contract-invalid produces
  `LLMProviderUnavailableError`, preserving the existing task
  failure/abstention behavior rather than fabricating `UNVERIFIED`
  or returning an incomplete JSON object.
- Logs and persisted telemetry contain safe provider names/outcomes,
  stage labels, numeric HTTP status where available, elapsed times,
  and previous sanitized Cloudflare token counts. **Never** log
  provider response bodies, raw prompts, credentials, user evidence,
  hidden reasoning, or account details.

This is a routing and reliability improvement, **not a claim that
a different LLM can correct incomplete Google Fact Check evidence**.
The observed true DART claim labeled MISLEADING is tracked in #137.
Issue #137 needs source-coverage fixes and independent quality
acceptance before the pipeline can be considered reliable.

## Required offline regression gate

From the project root, after checking for local changes:

```powershell
git status -sb
git fetch origin
git switch --track origin/feat/ai-rq2-provider-hierarchy
cd backend\truthlens_backend
```

If the local branch exists, switch and pull with
`git pull --ff-only origin feat/ai-rq2-provider-hierarchy`.

From the backend Django root:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_ai_rq2_provider_hierarchy `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_cloudflare_multistage_provider `
  api.tests.verification.test_cloudflare_assessment_latency_guardrails `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_evidence_assessment `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_verification_run_telemetry_inspection `
  api.tests.verification.test_pipeline_telemetry `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_pilot_evidence_budget `
  api.tests.verification.test_claim_legacy_schema_repair `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
..\.venv\Scripts\python.exe .\manage.py migrate --plan
```

The new hierarchy is mocked in tests: **no live Cloudflare/Gemini/Groq
requests needed**. Its tests assert 402/429 job-scope handling, Gemini
priority, Cloudflare secondary only in approved stages, Groq final
fallback with no SDK retries, strict output validation, unchanged
evidence payload, production/staging deny, and the real worker
flag probe. Existing Cloudflare-pilot tests explicitly disable the
new hierarchy flag to test legacy behavior independently.

## Acceptance gates not included in this branch

1. Local tests must pass; if a test fails, fix the failure on the
   same isolated branch before enabling the hierarchy in a worker.
2. Separately review co-developer's #137 work; do not equate source
   metadata with full article evidence.
3. Confirm Gemini 402 account status and Groq 429 rate-limit budget
   without paying or rotating credentials automatically.
4. Benchmark alternative Groq models **later**, against the same
   persisted dossiers and known good/contradictory/ambiguous cases,
   with explicit live-call approval. Do not auto-switch models
   after a rate-limit event.
5. Manual browser extension, claimability, and workspace acceptance
   remain in #126 and are not changed here.
6. Any actual live canary, staging/production activation, PR, merge,
   or promotion requires a separate decision.


## Phase 2 checkpoint — assessment-only capacity queue experiment

This phase is deliberately implemented on the **same** active AI-RQ-2
branch, not a ninth stacked branch. Changes have **not been locally
tested yet**. Do not merge the inherited 154-commit history directly
into main. The outstanding PARTNER-GOV-1 #128 manual verification
gate is blocked by provider reliability; no automatic governance
acceptance is implied by any new AI tests. Continue isolated review
until the dependencies are ready for appropriately scoped PRs.

Cloudflare documents `options.rejectIfBusy: true` in the **OpenAI
compatible Chat Completions** request body:
https://developers.cloudflare.com/workers-ai/features/reject-if-busy/

Cloudflare also documents numeric 429 error codes:
`3040` out of capacity and `3036` exhausted daily allowance:
https://developers.cloudflare.com/workers-ai/platform/errors/

**Important:** capacity queueing is only a *hypothesis* for the
observed 46.9s and 15.3s evidence assessment read timeouts. Faster
refusal is **not** successful reasoning, and this experimental option
does not guarantee reduced end-to-end latency. The smaller second
canary had only one fact-check evidence item and still timed out.
Existing final evaluations on different runs succeeded, but their
quality remains independently subject to evidence-source review.

### Phase 2 opt-in — not for production

Leave Cloudflare evidence assessment **off by default**. To later run
a separately approved **development-only** assessment experiment
requires *all* of these flags, and Django
`APP_ENV=development` + `DEBUG=True`:

```powershell
$env:ENABLE_AI_RQ2_PROVIDER_HIERARCHY = "1"
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"
$env:ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT = "1"
$env:CLOUDFLARE_PILOT_ASSESSMENT_REJECT_IF_BUSY = "1"
```

The experiment is not enabled by merely reading this document or
having these variables stored in a different, non-worker terminal.
Restart and inspect the worker flags if a live run is **separately
authorized**. Never auto-run a provider canary or rotate credentials.

With these flags on, *only eligible Cloudflare evidence assessment*
requests add the documented JSON field
`"options":{"rejectIfBusy":true}`. Other request JSON and the
`(3,15)` connect/read inactivity timeout are unchanged. Gemini remains
first; Cloudflare is attempted only if Gemini is unavailable or its
stage response violates the strict schema. Existing complete-batch
preflight and one-job Cloudflare breaker remain unchanged.

The **final verdict stage never** adds `options.rejectIfBusy`, never
alters Gemma 4 thinking mode, still uses its existing 2048-token
default and `(5,45)` timeout, and still validates exactly the
persisted-evidence JSON contract. This phase does not silently
disable thinking or shorten evidence to accelerate a model.

A response with Cloudflare 429/internal `3040` now produces the
sanitized error label `HTTP_429_CAPACITY`; internal `3036` produces
`HTTP_429_ALLOCATION`. A malformed, missing or unknown internal
code stays `HTTP_429`. No body, account details, raw prompts or
request ID are logged. **No retry** is added for either 429 case.

When a failed validated Cloudflare response has already supplied
safe `prompt_tokens`, `completion_tokens`, `total_tokens`,
`reasoning_tokens`, `finish_reason` or `reasoning_present`,
the telemetry records only those allowlisted counts/flags.
Transport timeouts may not provide any usage metadata: do not
invent numbers or infer why a timeout occurred from their absence.
The `inspect_verification_run_telemetry --show-usage` command can
display sanitized persisted usage, if actually supplied. No hidden
thinking content is ever copied into a verdict, event or diagnostic.

### Offline acceptance for Phase 2

From `backend/truthlens_backend`, after pulling the active
`feat/ai-rq2-provider-hierarchy` branch:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_ai_rq2_provider_hierarchy `
  api.tests.verification.test_cloudflare_assessment_latency_guardrails `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_multistage_provider `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_evidence_assessment `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_verification_run_telemetry_inspection `
  api.tests.verification.test_pipeline_telemetry `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_pilot_evidence_budget `
  api.tests.verification.test_claim_legacy_schema_repair `
  --settings=truthlens_backend.test_settings --keepdb

..\\.venv\\Scripts\\python.exe .\\manage.py check
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
```

Mocked coverage verifies no network, strict flag/scope validation,
unchanged full evidence and final budget, documented request shape,
structured numeric 429 distinctions, unknown-error fallback,
reasoning-text privacy, and allowlisted failure telemetry.

**Not yet demonstrated:** that real Gemma 4 respects fast-fail on
the currently configured Cloudflare account; live latency improvement;
whether any thinking/output tuning is quality-neutral; or a resolved
real TEXT/URL claim-verification workflow that will unblock #128.
Require explicit new approval for a live model call and inspect both
quality and provider timing before further adjustments.


## Phase 2 follow-up — lossless Cloudflare evidence assessment over four items

The October 22 authorized live TEXT canary `6ab50cb5-0fdf-478a-bb83-d32fa85785f2`
completed in 74,035 ms with Cloudflare final evaluator success (22,313 ms,
1,115 output tokens, `finish_reason=stop`). But **Cloudflare
assessment was skipped** for 12 eligible items
(`ASSESSMENT_BATCH_TOO_LARGE`), leaving Groq to assess them.
The independent `rejectIfBusy` experiment **was not exercised**.
Gemini still returned HTTP 402. This exposes a real failover gap if
Groq becomes rate-limited.

### Opt-in, bounded, lossless assessment chunking

The additional `CLOUDFLARE_PILOT_ASSESSMENT_CHUNKING=1` flag
defaults OFF and is effective only when **all** of these are true:
- `APP_ENV=development` and `DEBUG=True`;
- `ENABLE_AI_RQ2_PROVIDER_HIERARCHY=1`;
- `ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1`;
- `ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT=1`.

**Do not enable it for another live call without separate approval.**
On the existing single AI working branch, the implementation retains
the four-item **per-request** limit and independently gates a maximum
of **three** sequential Cloudflare assessment chunks (at most 12
original evidence items). Chunks are built **before** network access
from the original structured assessment envelope, in original order,
with all original item keys and unmodified evidence passage contents.
The planner accounts for the existing 28,000-character envelope cap;
if any evidence item cannot fit on its own or needs more than three
chunks, **all** Cloudflare assessment is skipped locally and the
unchanged original full batch is offered to Groq. There is no
selection, re-ranking, clipping or truncation.

Each chunk must independently satisfy the *existing* exact keyed
assessment schema, independent-isolation rubric and 2,048-output-token
ceiling. Once **every chunk** succeeds, the exact original keys are
reassembled and the full combined response is validated again. A
timeout, 429, malformed chunk, duplicate key or missing result stops
the sequence immediately, discards any partial Cloudflare assessment,
and falls back to Groq with the **original complete** user prompt.
No retry or alternate model carousel is introduced.

The provider telemetry records the bounded
`assessment_chunks_attempted` count, including incomplete sequences,
along with sanitized aggregate token usage when actually reported.
A `finish_reason=stop` for the combined response is allowed **only**
when all chunks have validated. There are no prompt/evidence passages,
hidden thinking text, raw provider bodies or credentials in events.

**This is resilience coverage, not proof of lower latency or solved
timeouts.** A previous **one-item** Cloudflare evidence assessment
timed out after 15.256 seconds. Three sequential chunks may be more
expensive and slower. The existing `(3,15)` inactivity timeout
applies **per chunk**, not as a total wall-clock SLA. A genuine
Cloudflare assessment failure still trips the existing job-wide
Cloudflare breaker, so a subsequent Cloudflare final verdict may be
unavailable within the same job. That larger breaker redesign is
**outside** this guarded checkpoint. No provider can truthfully
guarantee completion when all configured services are unavailable.

### PARTNER-GOV-1 manual acceptance is a separate gate

The same canary's classification inspection returned:
`Mode: off`, `Assessment: None`, `Classification: None`.
This is consistent with the default
`INVESTIGATION_CLASSIFICATION_MODE=off`, not a demonstrated
classifier failure. A safe manual progression is `shadow`
(proposal-only, not eligible for partner claiming), followed by
`enforce` **only after** automatic domain accuracy and authority
boundaries have passed manual review. Restart and align Django and
the **single intended Celery worker** when changing these settings;
the earlier canary startup/probe PIDs differed, and the queued probe
omitted the current hierarchy field.

**Additional uncovered dependency:** The separate
`investigation_classification` provider operation is not currently
Cloudflare-approved. It still uses Gemini → Groq. With Gemini 402 and
Groq quota exhaustion, classification could still fail even if
Cloudflare final verdict and evidence assessment succeed. Do not
silently authorize a new model operation without a strict schema
and classification QA suite.

### Offline tests (no provider network)

Pull the existing branch, then from
`backend/truthlens_backend`:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_cloudflare_assessment_chunking `
  api.tests.verification.test_cloudflare_assessment_latency_guardrails `
  api.tests.verification.test_ai_rq2_provider_hierarchy `
  api.tests.verification.test_cloudflare_multistage_provider `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_evidence_assessment `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_verification_run_telemetry_inspection `
  api.tests.verification.test_pipeline_telemetry `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_pilot_evidence_budget `
  api.tests.verification.test_claim_legacy_schema_repair `
  --settings=truthlens_backend.test_settings --keepdb

..\\.venv\\Scripts\\python.exe .\\manage.py check
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
```

Expected behavior in the new tests: 12 items → three validated
Cloudflare assessment chunks (no Groq), 13 items → zero Cloudflare
chunks + full Groq fallback, oversized individual passage →
Cloudflare local bypass without data loss, second-chunk
timeout/invalid JSON → no partial Cloudflare verdict and full
Groq fallback, all providers exhausted → explicit provider-unavailable
error rather than fabricated successful assessment. Existing legacy
routing tests explicitly keep chunking disabled.

**Status:** implementation committed to the existing branch;
**new offline suite not yet run**. No second live request,
PR, merge, or additional working branch.
