# PARTNER-GOV-1 — Paired Cloudflare classification budget study

**Status: OFFLINE DESIGN + SCORER STAGED, NOT LIVE AUTHORIZATION.**
All prior Cloudflare-02 and Cloudflare-03 packets remain permanently
locked. This benchmark creates a separate experiment design and no live
executor. The production factual-verification and organization eligibility
pipelines are unchanged. `INVESTIGATION_CLASSIFICATION_MODE=enforce`
is **not approved**.

## Motivation: two previous single-case attempts are not causal proof

Historical direct Cloudflare trials (same synthetic `cross_spacecraft`):
- Cloudflare-02, max completion 1024: empty visible output,
  `finish_reason=length`, 1024 completion tokens,
  `reasoning_present=true`, ~19.465s; no scoreable classification.
- Cloudflare-03, max completion 4096: valid quoted JSON, exact
  human-review domain match, `finish_reason=stop`, 829 completion
  tokens, `reasoning_present=true`, ~8.821s.

**The successful 4096-arm response used fewer than 1024 tokens, so
the evidence does NOT establish that the raised cap caused success.**
Generation variability, inference load and other uncontrolled factors
may matter. These historical packets were not balanced, replicated, or
conducted as a contemporaneous controlled trial; **exclude both from
the new paired analysis**. Neither may be re-executed or unlocked.

## Pre-registered offline study design

`gemma4_paired_budget_v1` defines 4 user-and-co-dev-reviewed synthetic
claims, 2 token budgets and 2 repetitions: **16 potential future
single-request observations** (8 per budget). These are **not**
permissions or queued API calls.

| Approved claim ID | Required reference | Main risk category |
| --- | --- | --- |
| `cross_spacecraft` | CLASSIFY SCIENCE + TECHNOLOGY | Two-domain accuracy |
| `cross_school_sport` | CLASSIFY EDUCATION | Unsupported extra SPORTS domain |
| `ambiguous_plan` | ABSTAIN | Unwarranted classification |
| `injection_civic` | CLASSIFY CIVICS | Prompt-injection resistance |

The model, exact classification prompt SHA-256 and approved corpus
fingerprint are pinned in the manifest. The strict reference SHA-256
is `40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af`.
If the approved file or reviewer metadata changes, plan creation
**fails closed** rather than silently replacing the reference.

Arms: **1024 vs 4096 max completion tokens**, with all other
intended adapter settings held constant:
`@cf/google/gemma-4-26b-a4b-it`, JSON-object mode,
`temperature=0.1`, `stream=false`, `rejectIfBusy=true`,
`3s connect / 45s read-inactivity`, direct Cloudflare-only,
no retries/fallback. The read timeout is a socket-inactivity limit,
**not a wall-clock cap**. Model/provider stochasticity remains.
Budget order reverses within each case between repetitions to reduce
simple order confounding; this is NOT a statistically powerful design.

Real-model outcomes will later be assessed for provider failure,
empty or unparseable content, strict quotation and response-contract
compliance, exact human-reviewed domain agreement, potentially
unauthorized Partner Organization specialization matches, abstentions,
token counts, and duration. Invalid captures and provider failures
are **not** silently converted to safe abstentions; missing trials
are **never** excluded from trial counts.

## Implemented files — all offline only

- `api/verification/cloudflare_budget_benchmark.py`: pure plan,
  immutable manifest validation, private no-network export, strict
  observation schema and descriptive per-budget/per-case scorer.
- `api/management/commands/prepare_cloudflare_budget_benchmark.py`:
  validates review fingerprint and prints a safe design summary;
  `--export-dir` explicitly creates a fresh private folder OUTSIDE Git.
- `api/management/commands/score_cloudflare_budget_benchmark.py`:
  loads only local captures and reports per-arm observed, missing,
  provider-failed, invalid JSON/quotes, wrong domains, scope leaks/
  exclusions, exact matches, and latency/token descriptive statistics.
- `api/tests/verification/test_cloudflare_budget_benchmark.py`:
  **15 new no-HTTP/no-ORM mocked regression tests**, including consent
  scope, strict provenance, pair order, missing vs failure distinctions,
  raw-response validation and scope-leak diagnostics.

These scripts contain **NO provider request operation, HTTP client
call, API credential handling, model SDK use, ORM access or Celery
task**. `live_execution_implemented=false` and
`enforcement_approved=false` are always reported.

### Offline local acceptance (PowerShell)

From `backend\truthlens_backend` after fast-forwarding a CLEAN
local `feat/ai-rq2-provider-hierarchy` branch:

```powershell
$corpus = "$env:USERPROFILE\Downloads\PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json"
$campaign = "$env:USERPROFILE\Documents\TL-Private-Cloudflare-Budget-Study-01"

# 60 previously passing selected regressions + 15 new benchmark tests.
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_budget_benchmark `
  api.tests.verification.test_cloudflare_classification_diagnostic `
  api.tests.verification.test_cloudflare_classification_capture `
  api.tests.verification.test_classification_capture_preparation `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_classification_latency_policy `
  --settings=truthlens_backend.test_settings --keepdb

# Read-only; no API, no files.
..\.venv\Scripts\python.exe .\manage.py prepare_cloudflare_budget_benchmark `
  --corpus "$corpus" --json-summary

# Explicitly create a NEW private plan (not a live runner).
..\.venv\Scripts\python.exe .\manage.py prepare_cloudflare_budget_benchmark `
  --corpus "$corpus" `
  --export-dir "$campaign" --json-summary

# Read-only scorer. Initially 0 observed, 16 NOT ATTEMPTED.
..\.venv\Scripts\python.exe .\manage.py score_cloudflare_budget_benchmark `
  --corpus "$corpus" `
  --campaign-dir "$campaign" --json-summary

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

The folder must not preexist; do not overwrite a previous study.
Expected initial score:
`planned_trials=16`, `observed_trials=0`,
`unobserved_trials=16`, `all_trials_observed=false`,
`complete_case_pairs=0`. Both arms should have 8 planned,
0 observed, 8 missing, and no exact-match rate.

The private folder contains:
- `benchmark_manifest.json`: exact claim input, case IDs,
  trial IDs, fixed budget/repetition/order and hashes. **Never
  commit or publish it**. It has no reference labels.
- `benchmark_observations.json`: initially `observations=[]`
  (NOT fabricated model outputs). When an independently authorized
  future capture is performed, only original, unmodified model
  responses and trusted sanitized adapter metadata belong here.
- `README.txt`: private capture and live-approval warning.

An observation has the strict shape:
`{trial_id,status,raw_response,error_code,duration_ms,usage}`.
Status is `CAPTURED` (complete original provider message.content as
raw_response; error_code=null) or `PROVIDER_FAILED`
(raw_response=null; one known sanitized error code).
The usage object must include exactly
`{finish_reason,prompt_tokens,completion_tokens,total_tokens,
reasoning_tokens,reasoning_present}` with reported safe values or
null where unavailable. No `NOT_ATTEMPTED` observations should be
manufactured: **absence is represented by absence**.

The scorer validates trial IDs, duplicates, schema, manifest hash,
corpus provenance, nonnegative integer durations/tokens, raw response
limits and sanitized error-code shapes. It does not certify capture
authenticity, detect answer leakage in a malicious external process,
or itself execute model requests.

## Future engineering/authorization gate (NOT GRANTED)

**No live benchmark requests are authorized by creating this plan.**
The prior one-call consent was fully consumed by Cloudflare-03.

Before any new paid requests:
1. Review the local offline test/manifest results and current
   provider account quotas/prices (a per-request generation cap
   is NOT a daily/monthly spend cap).
2. Implement a **separately reviewed direct-only, single-use capture
   path** with each individual trial bound to the manifest ID and
   exact approved input, hard execution/attempt limits, replay locks,
   preserved original model responses and sanitized usage. Avoid an
   unsafe bulk runner that silently executes all 16 requests.
3. Obtain **fresh explicit authorization** for a named subset and
   bounded maximum number of new calls. Keep all other entries
   unattempted; abort future calls on transport/quota failures.
4. Run offline scoring without submitting private raw results to
   GitHub, then review both statistical limitations and scope risks.

Even 16 synthetic trials (4 claims) are only a preliminary reliability
comparison. A larger independently reviewed **held-out real-world**
corpus and full 12-domain coverage are necessary before even
considering `INVESTIGATION_CLASSIFICATION_MODE=enforce`, which
remains **NOT APPROVED**.
