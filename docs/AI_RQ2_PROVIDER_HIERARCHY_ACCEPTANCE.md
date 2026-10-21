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


## AI-RQ-2 follow-up — subject classification provider fallback (offline checkpoint)

The completed Europa Clipper verification was **not classified**:
`INVESTIGATION_CLASSIFICATION_MODE=off`, with neither an assessment
nor an authoritative classification row. Verification completion alone
does not validate PARTNER-GOV-1 (#128). Additionally, when Gemini
returns 402 and Groq is 429-limited, subject classification had no
third provider, because the earlier Cloudflare pilot only covered
evidence assessment and final verdict. That **separate** missing
operation is now addressed behind an independent, default-OFF
development flag.

### Strict contract, minimal permitted authority

`ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT=1` has effect only when
**all** conditions are true:

- `APP_ENV=development`, `DEBUG=True`;
- `ENABLE_AI_RQ2_PROVIDER_HIERARCHY=1`;
- `ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1`;
- `ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT=1`.

Cloudflare classification does **not** require the assessment pilot,
chunking, or `rejectIfBusy` flags. The approved model stays
`@cf/google/gemma-4-26b-a4b-it`, with a new classification-specific
1,024-token maximum and `(3,15)` connection/read-inactivity timeout.
The original final verdict stays at 2,048 tokens with unchanged
thinking/evidence inputs and original timeout. The classification
input must be 20–2,400 characters, matching the existing local
classifier's text-input range.

In the opt-in routing path, **Gemini → classification-eligible
Cloudflare → Groq** must all satisfy the same strict JSON contract
before any response is accepted. The only permitted shapes are:

```json
{"decision":"ABSTAIN","domains":[]}
```

or:

```json
{"decision":"CLASSIFY","domains":[{"code":"SCIENCE","evidence":"science experiment"}]}
```

The example evidence text must be an exact substring of the original
persisted claim. A valid `CLASSIFY` contains 1–3 **distinct**
recognized subject domain codes, with each `evidence` a real
quoted claim substring of at least four characters. No unknown
domains, verdict, confidence, geographic authorization, extra
fields, fabricated quotes or duplicate domains are allowed.
A valid `ABSTAIN` remains an accepted answer and creates **no**
classification. Invalid output causes fallback, never unreviewed
permission; exhausting all configured providers raises the existing
provider-unavailable error.

The existing `classify_investigation_claim` continues to check the
persisted claim fingerprint, active/completed assignments, domain
quote integrity, transactional locking, provenance and authority.
This work makes **no changes** to organization verification scope,
partner eligibility, adjudication, GFC/Tavily ingestion, or stored
evidence. It does not turn a fact-checking AI verdict into a subject
classification.

Crucially, `INVESTIGATION_CLASSIFICATION_MODE` remains independently
`off` by default. **Do not** enable `enforce` simply because these
offline contract tests pass. `shadow` first records proposals without
making them claimable; only separately approved accuracy and
authorization acceptance can justify an `enforce` trial.

The sanitized read-only Celery readiness probe now reports
`classification_pilot_enabled` and
`investigation_classification_mode` alongside the worker PID
and provider routing flags. The earlier canary's mismatched worker
PID and older readiness payload mean we must confirm **one
up-to-date worker** and consistent Django/worker settings before
any further approved live requests.

### Required offline test gate

From `backend/truthlens_backend` after pulling the **existing**
`feat/ai-rq2-provider-hierarchy` branch:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_provider_hierarchy `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_cloudflare_multistage_provider `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_assessment_latency_guardrails `
  api.tests.verification.test_cloudflare_assessment_chunking `
  api.tests.verification.test_evidence_assessment `
  api.tests.verification.test_pipeline_telemetry `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  --settings=truthlens_backend.test_settings --keepdb

..\\.venv\\Scripts\\python.exe .\\manage.py check
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
```

All new tests use mocked providers. They include accepted domain
quotations, valid abstentions, malformed/surplus JSON and geographic
field rejection; Gemini 402; Cloudflare 429/timeout; Groq 429 with
no SDK retries/model carousel; development-only stage gates; no
raw claim in telemetry; unchanged actual application classifier
modes; and sanitized worker-readiness disclosure. These tests do
**not** prove model-generated domain accuracy or guarantee a
cloud inference completes within the timeout.

No new branch, PR, merge, paid call, worker setting change, schema
migration or live claim submission is part of this checkpoint.


## Phase 2 latency follow-up — classification short-timeout investigation (offline checkpoint)

### Evidence and diagnosis boundaries

The last real, approved `shadow` classification used a **clean dedicated
worker** (same startup and readiness PID **70360**, queue
`tl_shadow_canary`), returned `SUGGESTED` with the candidate domains
`SCIENCE`, `TECHNOLOGY`, and created **no authoritative classification**.

Observed provider sequence on that one task:
- Gemini claim subject classifier: HTTP **402**, **744ms**.
- Cloudflare Gemma 4 subject classifier: `TRANSPORT_ReadTimeout`, **15,337ms**.
- Groq subject classifier: HTTP **200**, **1,351ms**.
- Celery task: **20.704s**.

Previously, Cloudflare **one-item evidence assessment** timed out after
**15.256s**, and an older **9-item assessment** timed out after
**46.924s**. A **final verdict**, a different prompt and operation,
succeeded in **22.313s** with the original **45-second** read timeout.

All timeouts are HTTP **read-inactivity**, not hard wall-clock budgets.
We **cannot tell** whether these read timeouts resulted from Workers AI
capacity queuing, slow model generation, network latency, or some other
cause. The final success at 22 seconds does **not** prove that a
15-second classification response would succeed if extended. The prior
one-item assessment timeout cautions against assuming smaller input
alone guarantees a response.

Cloudflare officially supports top-level
`{"options":{"rejectIfBusy":true}}` on
`/ai/v1/chat/completions`, with a capacity reject surfaced as
HTTP 429 / internal code 3040:
https://developers.cloudflare.com/workers-ai/features/reject-if-busy/
The existing adapter already recognizes capacity versus allocation
429 subcodes without exposing response bodies.
Cloudflare also documents Gemma 4 thinking; the existing OpenAI-compatible
route does not have a validated stage-specific thinking toggle in our
code. **Do not disable thinking, trim classification input/evidence,
change the model, or reduce the validated final-verdict budget in this
diagnosis.**

### Two independent, disabled-by-default classification-only diagnostic flags

1. `CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY=1`: adds
   `options.rejectIfBusy=true` **only** to the classification-stage
   Cloudflare request. The original evidence-assessment capacity flag
   and the final-verdict request are unaffected.
2. `CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC=30`: changes
   the classification **read-inactivity** timeout from 15 to **30**
   seconds, retaining the 3-second connection limit. Only the exact
   string `30` opts in. Invalid or absent values retain 15s. The
   assessment per-chunk 15s and final evaluator 45s remain unchanged.

Both have **no effect** unless the established classification pilot is
enabled: `APP_ENV=development`, `DEBUG=True`,
`ENABLE_AI_RQ2_PROVIDER_HIERARCHY=1`,
`ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1`, and
`ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT=1`. Other stages are unchanged;
classification's 1,024-token budget, strict domain quote contract,
Gemma 4 model, provider order, disabled SDK retry, and fallback safety
are preserved. These are **diagnostic controls**, not fixes or
production-ready defaults. With `rejectIfBusy` enabled, the fast-fail
429 can identify capacity rejection but the absence of such a 429
does **not** prove that queueing was impossible.

The safe development Celery probe additionally exposes:
`classification_reject_if_busy_enabled` and
`classification_read_timeout_seconds`, alongside the already existing
classification pilot flag, mode, credentials-present booleans and PID.
It emits no tokens, prompts, raw provider bodies or private claim text.

**No live inference is approved by this offline checkpoint.** A later
*separately approved* controlled comparison could use the existing
dedicated-worker procedure, but only if it is needed and all security,
cost and output-quality gates are reviewed. Never automatically retry
a previous classification or override an already persisted suggestion.
These flags are not sufficient evidence to enable `enforce`.

### Domain eligibility decision — deliberate non-change

The current authoritative
`api.verification_domain_policy.eligibility_reason` requires **every**
classified subject to be covered by a partner's declared
specializations:

- `SCIENCE` + `TECHNOLOGY` claim vs `SCIENCE`-only partner:
  `OUTSIDE_SPECIALIZATIONS`.
- Same claim vs `TECHNOLOGY`-only partner:
  `OUTSIDE_SPECIALIZATIONS`.
- Same claim vs `SCIENCE`+`TECHNOLOGY` partner: eligible *only if*
  a separate **authoritative** classification exists and all other
  assignment gates pass.
- A shadow `SUGGESTED` domain proposal is not an authoritative
  classification and must not grant eligibility regardless of overlap.

This is conservative and may over-exclude experts who can assess a
cross-domain claim. A simple ANY-domain rule may over-authorize an
organization without expertise in a material area. Do not replace ALL
with ANY without determining whether a separate **primary domain**,
multi-expert review, or narrowly scoped per-claim review is needed;
those are distinct domain-policy changes requiring user and
co-developer review. This checkpoint adds only regression coverage
asserting the existing all-domains behavior.

### Offline test instructions

From `backend/truthlens_backend` after pulling the same working
branch:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_ai_rq2_provider_hierarchy `
  api.tests.verification.test_cloudflare_assessment_latency_guardrails `
  api.tests.verification.test_cloudflare_assessment_chunking `
  api.tests.verification.test_investigation_classifier `
  api.tests.organization.test_verification_scope `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  --settings=truthlens_backend.test_settings --keepdb

..\\.venv\\Scripts\\python.exe .\\manage.py check
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
```

New tests exercise default unchanged behavior; 15/30 timeout choice;
capacity-option pass-through only in classification; unchanged
assessment/final call settings; ignored malformed flags; disabled
production/staging flags; safe no-network worker probe; and explicit
all-domain authorization protection. Existing negative-path provider
tests cover Cloudflare 429 error classification, fake JSON, stage
fallbacks and no unsafe verdicts.

**Status: changes committed; local offline checks have NOT been run;
no live calls, PR, merge, branch creation, schema migration, or
authority policy change.**
