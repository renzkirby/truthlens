# PARTNER-GOV-1 — Three-claim development shadow canary

**Authorized 2026-10-22:** user approved preparing and executing one
fresh, bounded development-only shadow canary after the 87-test offline
shadow integration checkpoint passed.

This canary does **not** authorize `INVESTIGATION_CLASSIFICATION_MODE=enforce`,
production rollout, a PR/merge, replaying sealed Cloudflare evaluation
packets, or arbitrary additional model testing.

## Architecture exercised

Automatic investigation classification now uses the same job-scoped
provider architecture as the main verification pipeline:

1. Gemini
2. Cloudflare Workers AI / Gemma 4
3. Groq

The classification Celery task is wrapped in
`verification_telemetry_scope()` and `llm_provider_scope()`.
This gives each classification job fresh provider-degradation state and
keeps provider telemetry sanitized. The existing shared
`call_llm_with_fallback(..., operation="investigation_classification")`
still owns routing. No parallel classification router was added.

The task remains asynchronous in normal product use. The canary invokes
the task body synchronously only so a developer can stop immediately if
a shadow-authority invariant is violated.

## Fixed synthetic cases

The command owns exactly three synthetic claim inputs. Reference labels
are used only for after-response reporting and are never included in the
model prompt.

| Case | Expected |
| --- | --- |
| `single_science` | SCIENCE |
| `cross_health_economy` | ECONOMY + HEALTH |
| `ambiguous_plan` | ABSTAIN |

Live rows are marked with
`source_type=CLASSIFICATION_SHADOW_CANARY_2026_10_22` and
`is_ai_generated=True` so they are distinguishable from user claims.

## Safety / cost bounds

- Command is **dry-run by default**.
- Live execution requires `APP_ENV=development`, `DEBUG=True`,
  `INVESTIGATION_CLASSIFICATION_MODE=shadow`, the shared hierarchy flag,
  and the Cloudflare classification fallback flag.
- Exact confirmation:
  `I_APPROVE_THREE_CLAIM_SHADOW_CANARY`.
- At routing level there are at most **9 provider-stage attempts**:
  three providers × three claims. Valid earlier-provider output skips
  later providers. The underlying service SDK/provider may have its own
  transport behavior; do not interpret 9 as a financial cost guarantee.
- Groq SDK retries are disabled in the opt-in hierarchy. Existing
  provider code remains unchanged.
- If all three providers are exhausted for one claim, the canary stops
  and does not create/call the remaining cases.
- If a valid but semantically wrong response is returned, it is retained
  as a **shadow suggestion** for quality review; it is not automatically
  corrected.
- Any authoritative `ClaimInvestigationClassification`, or any mutation
  to `ai_verdict` / `final_verdict`, is treated as a safety invariant
  violation.
- Existing canary rows make the command refuse replay.
- The command never uses prior Cloudflare-02, Cloudflare-03, or the
  sealed 32-case accuracy packet.

## Offline regression before live execution

From `backend\truthlens_backend` on a clean
`feat/ai-rq2-provider-hierarchy` checkout:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_investigation_shadow_canary `
  api.tests.verification.test_investigation_shadow_integration `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_classification_latency_policy `
  api.tests.verification.test_classification_backlog_command `
  api.tests.organization.test_verification_scope `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

The new canary test module adds **9 mocked tests**, including dry-run
read-only behavior, full three-case shadow persistence, all-provider
exhaustion fail-stop, production/mode/flag denial, replay prevention,
and verification that the Celery classification task initializes and
restores the shared provider job scope.

## Read-only canary preflight (zero provider calls)

The live command relies on settings loaded at process start. Temporarily
set the development flags in the PowerShell process:

```powershell
$oldAppEnv = $env:APP_ENV
$oldDebug = $env:DEBUG
$oldMode = $env:INVESTIGATION_CLASSIFICATION_MODE
$oldHierarchy = $env:ENABLE_AI_RQ2_PROVIDER_HIERARCHY
$oldCfPilot = $env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT
$oldCfClassification = $env:ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT

$env:APP_ENV = "development"
$env:DEBUG = "True"
$env:INVESTIGATION_CLASSIFICATION_MODE = "shadow"
$env:ENABLE_AI_RQ2_PROVIDER_HIERARCHY = "1"
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = "1"
$env:ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT = "1"

..\.venv\Scripts\python.exe .\manage.py run_investigation_classification_shadow_canary `
  --json-summary
```

Dry run must report `SHADOW_CANARY_DRY_RUN_NO_PROVIDER_CALLS`,
`planned_claims=3`, `max_provider_stage_attempts=9`,
`provider_calls=0`, and `db_writes=0`. The preflight booleans should
show all required provider credentials present. Never paste credentials.

## One authorized live execution

Only after offline tests and preflight pass:

```powershell
..\.venv\Scripts\python.exe .\manage.py run_investigation_classification_shadow_canary `
  --execute-live `
  --confirm-live "I_APPROVE_THREE_CLAIM_SHADOW_CANARY" `
  --json-summary
```

Then restore the temporary settings:

```powershell
$env:APP_ENV = $oldAppEnv
$env:DEBUG = $oldDebug
$env:INVESTIGATION_CLASSIFICATION_MODE = $oldMode
$env:ENABLE_AI_RQ2_PROVIDER_HIERARCHY = $oldHierarchy
$env:ENABLE_CLOUDFLARE_VERIFICATION_PILOT = $oldCfPilot
$env:ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT = $oldCfClassification
```

Do not run the live command a second time. Share only the JSON summary;
it contains case IDs, generated claim UUIDs, candidate domain codes,
reason codes, sanitized provider/outcome/duration metadata, and no
claim text, model response text, prompt, credential, or hidden
reasoning.

## Acceptance interpretation

A healthy **integration** canary has:
- zero authoritative classification rows,
- zero factual-verdict changes,
- shadow `SUGGESTED` or `ABSTAINED` records,
- provider traces in intended hierarchy order,
- no more than nine provider-stage attempts.

Subject-quality review is separate:
- `all_exact=true` means all three synthetic canaries matched their
  predeclared labels on this one run; it is encouraging but cannot
  establish general accuracy or authorize `enforce`.
- `all_exact=false` with a valid `SUGGESTED` result demonstrates a
  model-quality mismatch, not an authority leak.
- `FAILED` means provider exhaustion/invalid final routing and triggers
  early stop.

After reviewing the one live summary, inspect the three retained rows
if needed, then remove the synthetic canary records before any
production-data review. Do not enable `enforce` as part of cleanup.
