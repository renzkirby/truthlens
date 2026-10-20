# TruthLens — Cloudflare persisted-evidence verification pilot

## Scope and authorization

**Development-only feature-flagged code; disabled by default.** This branch
prepares a Cloudflare Workers AI Gemma 4 26B alternative for the **final
persisted-evidence evaluation stage**. It does **not** turn Cloudflare into
the production provider, change earlier claim-gate/evidence classification,
alter retrieval or persistence, migrate database tables, or bypass
reviewer/partner-organization authorization.

Branch: `feat/cloudflare-verification-pilot`, forked from
`feat/verification-provider-evaluation`. That parent branch contains
the previously reported evaluation fixtures, review documentation and audit
code; no merge into `main` is authorized by this work.

The original model pathway remains:

```
claim/evidence processing
  -> call_llm_with_fallback(operation)
     -> Gemini -> Groq if Gemini fails
```

The opt-in development-only **persisted-evidence** pilot inserts a single
bounded alternative:

```
only if APP_ENV=development AND DEBUG=True
AND ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1
AND operation=persisted_evidence_evaluation

  -> Cloudflare Gemma 4 (one attempt, JSON object, 2048 completion tokens)
       | valid final evaluation: return to unchanged verifier/parser
       | timeout, rate/credit error, malformed JSON, invalid verdict:
       v
     existing Gemini -> Groq routing
       | if either returns valid final JSON: return to unchanged verifier
       | if neither is available or responses are malformed:
       v
     LLMProviderUnavailableError (NOT fabricated UNVERIFIED)
```

The previous Cloudflare model default is fixed at
`@cf/google/gemma-4-26b-a4b-it`. The adapter uses the same model
prompt, source-identity constraints, evidence context and verdict rules
as the existing persisted-evidence evaluator. It validates nonempty
`reasoning`, `summary`, and `score_context`, canonical verdict and
finite confidence from 0 to 100 before allowing the response. The pilot
also applies this stricter contract to Gemini/Groq fallback responses,
**only when opted in**, to prevent silently treating malformed model
outputs as UNVERIFIED. Legacy behavior with the pilot off is unchanged.

### Development-only guardrails

- `APP_ENV=development` and `DEBUG=True` are mandatory. A flag set
  in staging or production has **no effect**.
- The default `ENABLE_CLOUDFLARE_VERIFICATION_PILOT` is unset/disabled.
  Only the literal value `1` enables it when the other guards hold.
- No automatic retries, no parallel provider requests, no cross-run
  quota/circuit-break state or silent provider promotion.
- After Cloudflare fails, a scoped verification job does not call it
  again in that job; the existing Gemini/Groq state is preserved. A new
  job starts fresh. This is **not** a fleet-wide rate limiter.
- Cloudflare client uses the already-reviewed evaluation adapter:
  one HTTP request, `(connect=5s, read=45s)` timeout, 2048 output tokens.
  The overall call duration can be **much longer than 45 seconds**
  when fallback providers are also attempted.
- Provider telemetry explicitly permits sanitized `cloudflare` labels,
  uses the existing per-call ID, duration, success/failure and **exception
  type only**, never provider error bodies, prompts, evidence,
  credentials, final answers or internal model reasoning.
- Production mode cannot activate this pilot in this implementation.
  A future staging or production enablement requires a separate design
  review, explicit user approval, independent regression and rollback.
- **Do not** switch off Gemini/Groq in the same experiment: they are the
  current fallback for this development-only pilot.

## Offline acceptance commands

From repo root in PowerShell, with a clean worktree:

```powershell
git fetch origin
git switch --track origin/feat/cloudflare-verification-pilot
git log -1 --oneline
```

If the tracking branch already exists locally, instead use:

```powershell
git switch feat/cloudflare-verification-pilot
git merge --ff-only origin/feat/cloudflare-verification-pilot
```

Then from `backend/truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_llm_reliability `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_provider_quality_audit `
  api.tests.verification.test_realworld_verification_benchmark `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_run_url_runtime `
  --settings=truthlens_backend.test_settings `
  --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

These are mock/offline tests, not live provider calls. Add focused
end-to-end text and URL live verification tests under explicit human
supervision later, only after regression checks succeed. Image pipeline
parity is **not** demonstrated by these persisted-evidence cases.

## Configuration and controlled testing

A pilot requires **three separate, explicit conditions**:

```powershell
$env:APP_ENV = "development"
$env:DEBUG = "True"
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"
```

Also configure Cloudflare account and token **locally only** in environment,
not in Git or chat:

```text
CLOUDFLARE_ACCOUNT_ID=(your account ID)
CLOUDFLARE_API_TOKEN=(your private Workers AI token)
```

The earlier `ENABLE_CLOUDFLARE_EVALUATION=1` and
`ENABLE_PROVIDER_QUALITY_AUDIT=1` flags do **not** enable this pilot.
Start with ordinary test runs while keeping the pilot OFF. Don't submit
new live claims until the offline tests pass and a bounded real-world
pilot is explicitly approved.

Immediate rollback in the same development shell:

```powershell
Remove-Item Env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT -ErrorAction SilentlyContinue
```

If running worker processes, restart them after turning off the flag
so their environments are updated. Database migrations or client-side
changes are not required for rollback.

## Acceptance criteria before any staging/production consideration

1. Existing Gemini/Groq tests and run lifecycle pass unchanged with the
   flag **off**. The new test module covers the **on** state using mocks.
2. Cloudflare returns structured, evidence-grounded final verdicts under
   realistic (and adversarial) persisted evidence. No substantive claim
   verdict is invented by invalid provider responses or outages.
3. Measure end-to-end text/URL/image workflow impact, including recovery
   time when Cloudflare times out **and** Gemini/Groq is degraded.
4. Audit real usage via Cloudflare Neurons dashboard; model token counts
   are not billing totals and free-tier allocations have limits.
5. Add a deliberate request budget, circuit breaker shared by workers,
   monitoring/alerts and rollback strategy before a production canary.
   The present scope-level skip is not such a circuit breaker.
6. Human evidence-grounding audits and model parity beyond 10 deliberately
   constructed reviewed dossiers remain required.

**Current status:** Implemented on isolated branch; no automatic live tests,
production provider switch, database migration, merge or PR. Updated
regression tests require local user execution before acceptance.
