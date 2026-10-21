# Cloudflare multistage pilot and final-evaluation latency — acceptance

**Branch:** `feat/cloudflare-multistage-provider`, based on the unmerged
`fix/url-article-body-fidelity`. Preserve its URL claim/report fidelity,
full persisted evidence and the original model/provider fallback paths.

**Status when authored:** GitHub implementation committed; offline local
tests NOT yet reported. No production routing change, PR, merge, migrations,
or live Cloudflare requests were made by this implementation.

## What changes

The existing `ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1` remains the
development-only opt-in for `persisted_evidence_evaluation`.

A **separate, additional** flag allows opt-in testing of
`evidence_assessment`:

```text
APP_ENV=development
DEBUG=True
ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1
ENABLE_CLOUDFLARE_EVIDENCE_ASSESSMENT_PILOT=1
```

Restart **one** Celery worker with the desired environment. Never change
flags on a live production worker, pass credentials in chat or enable pilot
in staging or production. The second flag alone cannot activate the pilot.
`claim_gate`, `claim_equivalence` and other operations continue the
existing Gemini/Groq routing.

Evidence assessment uses the same independent keyed evidence prompt and
the same original input items. Cloudflare results must contain a complete
`assessments` list with **exactly one** item per expected key, legal stances,
numeric finite relevance/directness scores in [0,1] and no unexpected keys
or fields. Incomplete or malformed Cloudflare output triggers the existing
Gemini -> Groq fallback rather than persisting partial or invented stances.
If no provider supplies a usable assessment, the existing UNKNOWN/unavailable
path remains in force. No independent editorial identity or source authority
is inferred from stance.

The existing Cloudflare 28,000-character local preflight remains. **No
evidence content is removed to fit the assessment request**. Over-budget
pilot requests fail locally and fall back; this is not a claim that Gemini
or Groq support arbitrarily large requests. The final verdict still uses
the complete persisted evidence dossier with its existing lossless budget
rules.

## Latency investigation — preserve quality as default

The two prior real development final-evaluator calls took **24,610 ms**
(TEXT) and **17,102 ms** (URL), which are not directly comparable inputs.

The default final generation ceiling remains **2048 tokens**. To allow an
explicit A/B *development-only* test, a separate environment override is
supported:

```text
CLOUDFLARE_PILOT_FINAL_MAX_TOKENS=1536
```

Only exact `1536` opts into the smaller ceiling, and only in
`APP_ENV=development` with `DEBUG=True`. Missing or unrecognized values
retain 2048. Do NOT assume that reducing a *maximum* token allowance reduces
actual generation latency. It might instead increase invalid/truncated
responses and fallback latency, especially for a reasoning model.

Cloudflare provider events now store only **sanitized** metadata when
reported by the provider: `prompt_tokens`, `completion_tokens`,
`reasoning_tokens`, `total_tokens`, a known `finish_reason` and
`reasoning_present`. Missing metrics stay missing; no estimates are
invented. Raw prompts, text, credentials, hidden reasoning and unapproved
vendor response fields are never stored.

Read these via:

```powershell
..\.venv\Scripts\python.exe .\manage.py inspect_verification_run_telemetry `
  --run-id YOUR_RUN_UUID --show-usage
```

Default inspector output remains unchanged without `--show-usage`.
The safe worker probe also reports `evidence_assessment_pilot_enabled` as
one boolean, so the running worker's stage opt-in can be checked.
Existing older runs have no usage metadata and should not be backfilled
by guessing.

Do not make a latency decision from two non-identical runs. For a controlled
subsequent test, compare the same reviewed public claims and equivalent
persisted evidence across both budgets **only after** offline acceptance
and user approval for additional live calls. Avoid cached runs that bypass
the final evaluator. Evaluate end-to-end time, final-provider time,
completion tokens, finish status, malformed JSON, fallback count, verdict,
source accuracy and preserved uncertainty; reject the 1536 ceiling if any
quality or reliability regression is observed. Do not alter model, prompt
or input evidence in the A/B arm.

## Offline regression gate

From project root, fetch and switch the branch after a clean `git status`:

```powershell
git fetch origin
git switch --track origin/feat/cloudflare-multistage-provider
cd backend\truthlens_backend
```

If already present, use `git switch feat/cloudflare-multistage-provider`
and `git pull --ff-only origin feat/cloudflare-multistage-provider`.

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_multistage_provider `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_cloudflare_worker_readiness `
  api.tests.verification.test_evidence_assessment `
  api.tests.verification.test_verification_run_telemetry_inspection `
  api.tests.verification.test_pipeline_telemetry `
  api.tests.verification.test_pilot_evidence_budget `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_url_article_context `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

No live provider calls are required by this test gate. Mocked exception
messages may be printed and are not evidence of live outages. Share the
final test count and any failures, if present.

## No-go

- Fail closed or use legacy fallback if stage JSON is invalid; never
  interpret a final-verdict JSON as an evidence assessment.
- Never silently truncate source evidence to fit Cloudflare.
- Keep official human decisions and publication authority unchanged.
- Keep Cloudflare disabled outside local development until a separate
  quality, cost, reliability and rollback review.
- No PR or merge without separately granted approval.
