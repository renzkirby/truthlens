# AI-RQ-2 / PARTNER-GOV-1 — Cloudflare implementation closeout

**Scope: close the existing development-only Cloudflare pilot, not a
production launch or automatic Partner Organization classification.**
No further token-budget research or live-provider batch is needed to
complete this implementation checkpoint.

## Why we are stopping the budget experiments

Prior authorized, private direct single-case tests:
- Cloudflare-02, 1024 max completion tokens: `cross_spacecraft`
  yielded empty provider content after consuming 1024 tokens,
  `finish_reason=length`, `reasoning_present=true`.
- Cloudflare-03, 4096 max completion tokens: same case produced valid
  JSON and an exact approved SCIENCE + TECHNOLOGY match, using
  **829** completion tokens, 8.821s, `finish_reason=stop`,
  `reasoning_present=true`.

This is evidence that the model **can** work, not that 4096 caused
the improvement or that the model is accurate across all 12 subjects.
No all-domain accuracy conclusion is warranted. Both packets are
permanently locked; never reuse them. The separate, prepared 16-trial
offline budget study is archived as **optional future research**:
nothing will automatically execute it.

## Final integration configuration

Existing verification fallback (development-only opt-in) remains:
**Gemini -> Cloudflare Workers AI -> Groq**. The original legacy
behavior applies when flags are off. No changes to provider order,
persistent evidence dossier, final verdict prompts or inference
quality gates, and no Partner Organization permission changes.

Cloudflare classification now supports a deliberate **4096-token
development-only opt-in**, rather than a global default increase.
The baseline remains **1024**. The original 15s socket-read-inactivity
timeout, and existing optional 30s arm, remain valid. A 45s
read-inactivity timeout is allowed **only when the 4096-token opt-in
is active**, so other classification calls do not automatically stall.

Settings for a development test worker's environment (these opt into
the pilot and may result in real provider requests when the normal
verification/classification operations are invoked):

```text
APP_ENV=development
DEBUG=True
ENABLE_AI_RQ2_PROVIDER_HIERARCHY=1
ENABLE_CLOUDFLARE_VERIFICATION_PILOT=1
ENABLE_CLOUDFLARE_CLASSIFICATION_PILOT=1
CLOUDFLARE_PILOT_CLASSIFICATION_MAX_TOKENS=4096
CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC=45
```

The pre-existing
`CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY=1` optional
capacity-fast-fail can remain enabled only for this operation,
independently of assessment/final verdicts.

**Do not turn these flags on for production or as a substitute for
fresh authorization of paid live calls.** Cloudflare is still
prohibited by code from running its pilot unless
`settings.APP_ENV == "development"` and `DEBUG is True`.
`INVESTIGATION_CLASSIFICATION_MODE=off` stays unchanged. Enabling
`enforce`, approving classifications to gate partner investigation
permissions, or a production provider launch is OUT OF SCOPE.

Unlike a token-per-minute provider rate limit, the
`max_completion_tokens` parameter bounds one completion; it does
not guarantee a spend cap, response length/quality, latency or
server-side quota. 45 seconds is a *read-inactivity* limit, not an
end-to-end time deadline.

## Final local acceptance, once

After fast-forwarding a CLEAN
`feat/ai-rq2-provider-hierarchy` checkout, from
`backend\truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_classification_latency_policy `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_ai_rq2_provider_hierarchy `
  api.tests.verification.test_cloudflare_multistage_provider `
  api.tests.verification.test_cloudflare_verification_pilot `
  api.tests.verification.test_cloudflare_budget_benchmark `
  api.tests.verification.test_cloudflare_classification_diagnostic `
  api.tests.verification.test_cloudflare_classification_capture `
  api.tests.verification.test_classification_capture_preparation `
  api.tests.verification.test_classification_quality_audit `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check

..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

This is **one final mocked, NO-NETWORK regression/integration pass**.
The ten suites contain **164 targeted tests** based on the known
repository test inventory: 75 previously passing checks, five new
tests in `test_classification_latency_policy`, plus 84 established
provider-hierarchy/multistage/classification fallback tests.
Only the user-local test result confirms actual acceptance.

The five new mocked checks prove:
- The default still uses 1024 tokens.
- The **real** `_query_classifier` prompt and entry point use one
  exactly pinned Cloudflare JSON request with the 4096/45s dev flags;
  successful JSON is strictly classified without invoking Groq.
- Empty visible content after reasoning/length exhaustion does NOT
  fabricate a classification; it falls back to the existing
  validated Groq path with safe error telemetry and no Cloudflare
  retry.
- Unrecognized budget/timeout flags fail closed.
- Staging/production do not get the pilot even with flags set.

Earlier tests also cover billing/quota failures and fallback,
assessment and final-verdict stage independence, raw evidence
retention and existing strict JSON contracts. No database migration
was necessary or intended. DO NOT run another paid Cloudflare trial
for this checkpoint.

## Closeout decision

When user-local tests and Django/migration checks pass:
1. Mark **Cloudflare development pilot implemented and integrated**.
2. Prepare the existing branch for code review/PR/merge; inspect the
   overall branch diff before merge. Do not merge on the basis of
   this README alone.
3. Return to core TruthLens priorities; leave the optional paired
   budget benchmark and any 32-case held-out accuracy research
   explicitly non-blocking.
4. Record limitations: **No claim of production rollout, global
   latency/accuracy guarantees, 12-domain accuracy certification,
   or Partner Organization enforcement authorization.**

Failing tests should be treated as blockers to closeout and fixed
directly—without opening another large exploratory study.
