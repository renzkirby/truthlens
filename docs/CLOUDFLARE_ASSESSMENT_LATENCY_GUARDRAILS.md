# Cloudflare evidence-assessment latency guardrails

**Branch:** `fix/cloudflare-assessment-latency-guardrails`, derived from
`fix/claim-legacy-relatedness-nullability`. **No deployment, live API
call, PR, or merge was made to develop this change.** The local offline
test gate must be run before a new live canary.

## The actual 2026-10-21 development canary

VerificationRun `e745ae96-847b-49fe-8798-40029277940c` completed,
but Cloudflare Workers AI **did not successfully evaluate either stage**.
Its nine-item evidence assessment timed out at **46,924 ms**, and the
existing job-scoped Cloudflare circuit breaker correctly suppressed a
further Cloudflare final-evaluation request. Groq completed the evidence
assessment in **4,128 ms** and the final evaluation in **15,563 ms**
(including an observed HTTP 429 and a vendor SDK retry). Total run
lifecycle duration was **125,935 ms**; Tavily retrieval was **36,422 ms**.
These are different/nested measurements, not additive steps. Gemini
claim_gate returned HTTP 402 and Groq completed claim_gate.

One timeout cannot establish Cloudflare model quality or normal speed.
The completed FACT verdict belonged to Groq.

## What this patch does, and does not do

When `APP_ENV=development`, `DEBUG=True`, and both existing Cloudflare
pilot flags are `1`:

- For the `evidence_assessment` stage only, **at most four evidence
  passages** per original batch may call Cloudflare. Larger batches
  **bypass Cloudflare** without changing their prompt, order, item keys
  or content. All evidence goes to the normal Gemini -> Groq route, with
  the existing strict stage-specific schema validation.
- A local bypass (too many items, malformed assessment envelope, or
  Cloudflare's 28,000-character input preflight) does **not** mark
  Cloudflare degraded in the job. The subsequent **final** evaluation
  remains eligible for Cloudflare. Its input dossier is unchanged.
- A genuine attempted Cloudflare request failure (read timeout, 429,
  malformed JSON, etc.) still trips the existing **job-scoped circuit
  breaker**. Do not automatically spend more provider time retrying
  Cloudflare during the same job.
- **Small** Cloudflare assessment requests use Requests'
  `(connect=3, read=15)` timeout tuple instead of `(5, 45)`. Note:
  Requests' connect/read timeouts are inactivity limits, **not a strict
  15-second total job deadline**; DNS, streaming responses, and other
  work can still increase elapsed time.
- Cloudflare final evaluation keeps `(5, 45)`, the original default
  **2048-token maximum**, its schema contract, original provider model
  and complete persisted evidence. The optional 1536-token experiment
  is **not enabled** or modified by this patch.
- The inspector `inspect_verification_run_telemetry --show-usage` now
  shows a sanitized `reason=ASSESSMENT_BATCH_TOO_LARGE` for intentional
  `outcome=skipped` assessment entries. It does not log user claims,
  evidence passages, API tokens, or error response bodies.

There is no source dropping, summarization, new evidence ranking,
parallel duplicate Cloudflare call, provider change in production or
staging, or mutation of final verdict authority.

**Quality tradeoff:** this is a **fail-fast routing safeguard**, not a
claim that Gemma is faster or has improved assessment accuracy. The
four-item threshold is a conservative initial development policy,
not a validated ideal model batch size. It prevents the already-observed
nine-item stall and allows quality review on smaller batches later.
A Cloudflare small-batch request may still be slower or fail; its strict
validator and fallback remain authoritative.

## Local offline gate

Run from `C:\Users\Lenovo\Desktop\TruthLens\truthlens` after checking
for uncommitted changes:

```powershell
git status -sb
git fetch origin
git switch --track origin/fix/cloudflare-assessment-latency-guardrails
cd backend\truthlens_backend
```

If already tracking this branch locally, use `git switch` plus a
`git pull --ff-only`.

Run this selected no-network/mock regression suite from the Django root:

```powershell
..\.venv\Scripts\python.exe .\manage.py test api.tests.verification.test_cloudflare_assessment_latency_guardrails api.tests.verification.test_cloudflare_multistage_provider api.tests.verification.test_cloudflare_verification_pilot api.tests.verification.test_cloudflare_provider_evaluation api.tests.verification.test_evidence_assessment api.tests.verification.test_verification_run_telemetry_inspection api.tests.verification.test_pipeline_telemetry api.tests.verification.test_run_text_runtime api.tests.verification.test_pilot_evidence_budget --settings=truthlens_backend.test_settings --keepdb
..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
..\.venv\Scripts\python.exe .\manage.py migrate --plan
```

A `--keepdb` test may print mocked provider failures and HuggingFace
model warnings; final suite summary, assertions, and zero new migrations
are the acceptance indicators. **No new migration is part of this patch.**

## Controlled follow-up (only after separate approval)

Keep `ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT=0` until local
offline acceptance. Stop duplicate `celery@Renz` worker instances
and confirm the actual process receives environment flags. The earlier
`DuplicateNodenameWarning` does not prove misrouting, but makes clean
single-worker diagnostics important.

After offline acceptance and explicit permission for another live provider
request, use one **uncached** reviewed public claim and record the
stage and provider sequence, source stances, full claim verdict,
fallbacks, requests' errors, 2048-token final budget and total duration.
For batches of 5+ items, `outcome=skipped` is the expected Cloudflare
**assessment** event; the final Cloudflare verdict can still be attempted
if no genuine provider failure occurred. For batches of 1–4, Cloudflare
assessment is attempted with a shorter read timeout and its output must
pass exact keyed JSON validation.

Also separately track **36-second Tavily search**, Gemini **402**, Groq
**429**, and embedding cold-start/network checks. They are outside this
isolated Cloudflare assessment patch and can dominate end-to-end latency.

Do not merge to main/pilot or enable production Cloudflare without a
separate measured rollout and approval.
