# AI-RQ-2 classification latency and fallback decision record

> **2026-10-28 v4 note:** The latency observations below are historical v3
> measurements. Classifier `v4-primary-subject` changes the response contract
> to require explicit `primary_subject`; old v3 captures remain useful only as
> latency/provider-history evidence, not as valid v4 classification responses or
> v4 accuracy evidence. The provider order/timeout policy itself is unchanged by
> the v4 primary-subject work.
>
> **2026-10-28 v5 note:** Classifier `v5-primary-unique-domains` keeps the v4
> schema but makes the prompt explicitly require 1-3 unique domain objects and
> one evidence quote per selected domain. Historical v4 responses remain useful
> for provider/latency evidence but are not v5 prompt-quality evidence.


**Status (2026-10-22):** Development-only candidate; offline tests required.
**Scope:** The *subject classification* operation only. Not the authoritative
fact-check verdict, evidence assessment, partner organization permissions,
assignment matching, or any currently enabled production feature.

## Observations versus conclusions

- The authorized direct classification using Cloudflare Gemma 4, a
  15-second read-inactivity timeout and capacity fast-fail returned
  `TRANSPORT_ReadTimeout` after **15,295ms**, with no response metrics.
- A second **separately authorized single request** used the same proposition,
  exact prompt and model, capacity fast-fail still enabled, and a 30-second
  read-inactivity timeout. It completed after **16,132ms**, returning a valid
  `CLASSIFY` result with domains `SCIENCE` and `TECHNOLOGY`.
  Provider-reported usage: prompt 188, completion 867, total 1055 tokens,
  finish `stop`, `reasoning_present=true`, no reasoning token count.
- A separate earlier background classification timed out at **15,337ms**
  and then successfully fell back to Groq. Cloudflare final evaluation,
  with a different prompt and a 45-second timeout, previously succeeded
  after **22,313ms**.

These are individual requests, **not** a calibrated latency distribution.
Their timing supports the finding that the 15-second Cloudflare
read-inactivity limit can prematurely reject some valid classification
responses. It does **not** prove that 30 seconds is a reliable SLA or
identify whether capacity queueing, reasoning generation, connection,
or provider/network variability dominated.

Official reference:
- Requests timeouts are socket-inactivity limits, **not total request
  deadlines**: https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts
- Cloudflare Workers AI supports top-level `options.rejectIfBusy` on
  synchronous Chat Completions, with HTTP 429/internal 3040 on capacity
  rejection: https://developers.cloudflare.com/workers-ai/features/reject-if-busy/

No explicit HTTP 429 capacity response was observed in the approved
diagnostics; **absence of that code is not proof of spare capacity**.

## Candidate policy — explicit development-only opt-in

| Property | Existing/default | Candidate pilot |
| --- | --- | --- |
| Gemini primary | unchanged | unchanged |
| Cloudflare classification | dev-only when all pilot gates hold | same |
| Cloudflare model | `@cf/google/gemma-4-26b-a4b-it` | unchanged |
| Connect timeout | 3 seconds | 3 seconds |
| Read-inactivity timeout | **15 seconds** | **30 seconds** |
| `rejectIfBusy` | absent | true, independently opted in |
| Classification completion cap | 1024 tokens | unchanged |
| Cloudflare HTTP attempts | 1 per operation | unchanged, no retry |
| Fallback after failure | Groq | unchanged, with `max_retries=0` in hierarchy |
| JSON/subject contract | quote-grounded subject-domain or ABSTAIN | unchanged |
| All providers exhausted | `LLMProviderUnavailableError` | unchanged |
| `off`/`shadow`/`enforce` | off by default | unchanged |
| Evidence assessment | 15-second read timeout | unchanged |
| Final Cloudflare evaluation | 45-second default read timeout | unchanged |

To select the candidate **only in an already authorized local
development environment**, all of the following must apply:
- `APP_ENV=development` and `DEBUG=True`;
- `ENABLE_AI_RQ2_PROVIDER_HIERARCHY=1`;
- `ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1`;
- `ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT=1`;
- `CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC=30`;
- `CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY=1`.

Both diagnostic flags remain **off by default**. Only the exact strings
`30` and `1` enable their respective behaviors. The 30-second
read timeout is a bounded *per-socket-idle interval*; it is **not**
a hard wall-clock classification budget. The total worker task may
also wait for Gemini and, if needed, Groq.

**We are not introducing a hard end-to-end deadline.** Implementing
one would require coordinated cancellation/timeout behavior across
provider SDKs, Celery workers and HTTP IO; simply adding a stopwatch
or background thread would not terminate an in-flight paid request.
That is a separate design/acceptance task.

## Failure/authorization requirements

- Successful Gemini JSON short-circuits Cloudflare/Groq.
- Cloudflare's valid CLASSIFY or explicit ABSTAIN short-circuits Groq.
- Invalid JSON, unquoted/unsupported domains, transport timeout, capacity
  429, allocation 429 and other sanitized errors may fall through to
  Groq. No fabricated success or unvalidated result is allowed.
- Cloudflare has exactly one attempt per requested operation. The
  existing job-scoped breaker avoids repeated Cloudflare requests
  after a genuine failure in the same scoped job.
- With hierarchy enabled, Groq SDK retries remain disabled. If every
  provider fails, the classifier records an appropriate failure status
  rather than creating an authoritative subject classification.
- `shadow` may record `SUGGESTED`, `ABSTAINED`, or `FAILED` assessments,
  but never a `ClaimInvestigationClassification`. A persisted shadow
  suggestion is idempotent and is **not** auto-promoted on mode change.
- `enforce` is explicitly **not authorized** by this timeout policy.
  Empirical model accuracy, classification rationale/quotes, partner
  scope matching, and signed-off governance remain prerequisites.
- The existing all-domains-subset organization specialization rule
  is unchanged, including its conservative treatment of cross-domain
  `SCIENCE`+`TECHNOLOGY` claims.

## Latency and rollout gates

Before considering a different default, **do not** use repeated ad-hoc
live requests or infer a percentile from these two samples. Agree on:
1. An approved, finite, representative case corpus including abstentions,
   ambiguous, harmful/unsupported, cross-domain and out-of-scope cases;
   preserve model inputs and stable result contracts.
2. A total **cost/request-count** budget and a separate latency
   service-level objective measured at the Celery task boundary
   (Gemini + Cloudflare + Groq), not merely the Cloudflare HTTP call.
3. Tail behavior for a Cloudflare 30-second read timeout followed by
   Groq retry-free fallback, and for all-provider exhaustion.
4. A minimum accuracy/abstention threshold and manual adjudication
   comparing quoted evidence with each subject domain. The current
   persisted assessment stores domain codes, not per-domain model
   quotations, so quote review requires a **separately approved offline
   evaluation harness** with controlled access to synthetic or approved
   test inputs. Do not claim that the stored candidate_domains list
   independently proves the model's rationale.
5. Consistent worker version and flags; restart development workers after
   configuration changes and avoid duplicate workers with stale identities.
6. Explicit written rollout/rollback approval before changing defaults
   or permitting enforce mode.

**Rollback:** remove the two classification diagnostic environment
variables and restart any previously configured development worker.
The default reverts to 15s with no `rejectIfBusy`; classification mode
still defaults to off. Do not modify the final-verdict or assessment
pipelines as a shortcut.

## Offline regression gate

From `backend/truthlens_backend`, after pulling the existing AI
working branch:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_classification_latency_policy `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_cloudflare_provider_evaluation `
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

`test_classification_latency_policy` exercises the **real adapter**
against mocked `requests.post`, with Gemini/Groq mocks: 30s / 1024
budget / fast-fail header body, accepted quoted result, valid abstention,
timeout and sanitized capacity-429 fallback, invalid JSON fallback,
all-provider exhaustion, bad-flag default/rollback and
production/staging safeguards. No actual Cloudflare, Gemini or Groq
request is part of this test gate.

**Local regression status: not yet run on the updated branch.** The
previous 224/224 offline suite and Django checks passed before this
checkpoint. No new live AI call, branch, PR, merge, model switch,
database migration, partner scope authorization change or production
activation was performed during this policy review.


## Regression-suite environment isolation (2026-10-22 follow-up)

The user's first run of the extended matrix reported **232 tests, four
failures**. All four were **legacy TEXT and URL runtime Cloudflare-pilot
tests** expecting Cloudflare → Gemini → Groq ordering when
`ENABLE_AI_RQ2_PROVIDER_HIERARCHY` is off. The previous live diagnostic
instructions had explicitly set this flag to `1` in the local
PowerShell session, and clearing only the classification timeout and
capacity flags **did not clear the hierarchy flag**. The actual observed
Gemini → Cloudflare → Groq ordering is the correct opt-in hierarchy.
No failure pointed to the new Cloudflare 30-second adapter integration
tests.

Rather than change production routing or make legacy tests depend on
the invoking shell, the two relevant cases in *each* of
`test_run_text_runtime.py` and `test_run_url_runtime.py` now explicitly
use `@patch.dict(os.environ, {"ENABLE_AI_RQ2_PROVIDER_HIERARCHY": "0"})`
while their original `@override_settings(APP_ENV="development", DEBUG=True)`
remains. This pins the expected **legacy** route for the test duration
and restores the caller's environment automatically. Separate
hierarchy-specific tests continue to assert Gemini → Cloudflare → Groq
when explicitly enabled. No runtime implementation changed.

Local follow-up rerun is **pending**. To avoid leaking an opt-in
development setting into unrelated manual commands, after diagnostics
users may additionally clear the environment flag in their current
PowerShell session:

```powershell
Remove-Item Env:ENABLE_AI_RQ2_PROVIDER_HIERARCHY -ErrorAction SilentlyContinue
Remove-Item Env:ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT -ErrorAction SilentlyContinue
Remove-Item Env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT -ErrorAction SilentlyContinue
```

This cleanup is operational hygiene, **not required for the repaired
tests to pass**. Environment variables set persistently or in
`.env` require separate user review. Do not change app settings or
worker flags during a live test without an explicit authorization.
