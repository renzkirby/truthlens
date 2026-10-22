# PARTNER-GOV-1 — Offline evaluation capture preparation (NO LIVE CALLS)

**Status:** Development-only preparatory command and regression tests;
**not** authorization to run paid provider inference or enable automatic
partner claim classification. Existing classification remains
`INVESTIGATION_CLASSIFICATION_MODE=off` by default.

The user locally verified:
- Default synthetic GitHub fixture: **32 cases, 0 approved, 32 pending,
  NOT SCORED**.
- Separately approved **private** reference JSON:
  **32 cases, 32 approved, 0 pending, NOT SCORED** without real predictions.
  Two-reviewer agreement was user-reported and reviewer-2 approval was
  relayed by the first reviewer, **not independently authenticated**.
- The preceding classification quality audit had **12/12** tests passing.
  The **new tests for this preparation command still require local execution**.

## What was implemented

- `api/verification/classification_capture_plan.py` —
  bounded, pure offline planning from the existing strict approved-case
  parser. No HTTP SDK, Gemini, Cloudflare or Groq requests; no ORM,
  migrations or Celery tasks.
- `python manage.py prepare_investigation_classification_evaluation` —
  CLI wrapper. **Requires** an approved local `--corpus` and exactly one
  named `--provider` (`gemini`, `cloudflare`, `groq`).
- `api/tests/verification/test_classification_capture_preparation.py` —
  nine no-database offline tests including fail-closed pending labels,
  duplicate/unknown cases, limits, private export, no fabricated
  predictions, no checkout export and illustrative cost handling.

### Behavioral/safety contract

1. **Default plan: four safety canaries** in fixed order:
   `cross_spacecraft` (multi-domain),
   `cross_school_sport` (consensus EDUCATION-only; overclassification),
   `ambiguous_plan` (correct abstention), and
   `injection_civic` (prompt injection).
   These are **not a statistically representative sample**.
2. `--limit 1..32` is a bound on **PLANNED** evaluations **for one
   provider per command**, not an execution quota or server/API cap.
   `--case-ids` can select any known approved cases explicitly.
   Each additional provider's command is a **separate** plan:
   four cases across three providers is **up to 12 prospective requests**,
   and all 32 for each is **up to 96** prospective requests.
3. Require **all** cases in the supplied corpus to be APPROVED,
   fail closed on malformed reviews and unknown/duplicate IDs, and
   output only aggregate plan info, case IDs and hashes by default.
   Never print private claim texts, reviewer notes, classifications,
   raw model results or credentials.
4. By default the command is **read-only**. Only the explicit
   `--export-dir` option creates a **new**, private folder **outside
   the repository checkout**. Existing folders cannot be overwritten.
   It writes:
   - `capture_inputs.json`: selected exact claim texts, case IDs,
     SHA-256 input digests, provider, stated model ID (not executable
     config), approved corpus fingerprint and plan details;
     **does not include expected labels or reviewer records**.
   - `predictions.json`: the valid expected schema, initially
     `{"schema_version":1,"predictions":[]}`; this is an **empty**
     capture destination, **not** fabricated model output.
   - `README.txt`: privacy and provenance precautions.
5. The command **cannot execute inference**. There is intentionally no
   `--execute`, `--live`, API key, HTTP request, Celery task or
   database read/write path. Exporting a packet **does not grant**
   permission to run providers in another tool/process.
6. Cost is **UNKNOWN** until the operator supplies **both current
   USD/million input/output rates** and **both assumed token counts**.
   The optional output is an **illustrative** calculation, not a
   guaranteed bill, spending cap, SLA, enforced input-token bound,
   or verified current provider price.
7. The provider field identifies an **isolated direct provider plan**;
   it does **not** measure full Gemini → Cloudflare → Groq routing.
   `model_id` records an intended model label only. Prompt/template
   version, exact request parameters, model variants, token accounting,
   observed latency, errors/retries and quoted-evidence response
   provenance **must be pinned and recorded separately** in an
   authorized evaluation.
8. The approved synthetic corpus remains a small, constructed dataset.
   Before a production enforcement decision, add a separately reviewed
   held-out **real-world** set, all persisted claim input types and
   meaningful domain coverage. Assess factual-verification quality
   separately; do not change the live RAG pipeline for benchmarking.

## Local commands (PowerShell, no AI calls)

From `backend\truthlens_backend`, with your private approved JSON in
Downloads:

```powershell
$corpus = "$env:USERPROFILE\Downloads\PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json"

# Read-only: single-provider, four case IDs, no files written.
..\.venv\Scripts\python.exe .\manage.py prepare_investigation_classification_evaluation `
  --corpus "$corpus" --provider cloudflare --json-summary

# Read-only: specific cases selected, at most the declared limit.
..\.venv\Scripts\python.exe .\manage.py prepare_investigation_classification_evaluation `
  --corpus "$corpus" --provider groq --model-id "MODEL_ID_NOT_YET_CHOSEN" `
  --limit 2 --case-ids cross_school_sport ambiguous_plan

# Optional: create EMPTY private templates, outside Git; nothing executes.
# Choose a new folder name each time. Claim text is saved in this folder.
..\.venv\Scripts\python.exe .\manage.py prepare_investigation_classification_evaluation `
  --corpus "$corpus" --provider gemini `
  --export-dir "$env:USERPROFILE\Documents\TL-Private-Classification-Gemini-01"

# Illustrative price arithmetic ONLY: update rates from provider invoices/docs;
# these sample values are NOT provider price quotes or spending caps.
..\.venv\Scripts\python.exe .\manage.py prepare_investigation_classification_evaluation `
  --corpus "$corpus" --provider cloudflare `
  --input-price-per-million 2 --output-price-per-million 4 `
  --assumed-input-tokens 1000 --assumed-output-tokens 500
```

Do **not** place `capture_inputs.json` or response files in GitHub,
commit them, paste private credentials into arguments, or import production
user content without consent.

### New offline regression checks

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_classification_capture_preparation `
  api.tests.verification.test_classification_quality_audit `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

## Cloudflare-02 — model pinned, priced evaluation review (2026-10-22)

The user created a fresh private package
`Documents\\TL-Private-Classification-Cloudflare-02` successfully:
`provider=cloudflare`,
`model_id=@cf/google/gemma-4-26b-a4b-it`,
`approved=32`, `planned_requests=4`, selected
`[cross_spacecraft,cross_school_sport,ambiguous_plan,injection_civic]`,
`corpus_sha256=40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af`.
The command confirmed **no provider calls, no predictions and no DB writes**.
The earlier private `Cloudflare-01` package still has
`model_id=NOT_SELECTED`; retain it as history, do not overwrite it.

Cloudflare's official **Workers AI pricing** documentation, checked on
2026-10-22, currently lists **$0.10 per million input tokens and
$0.30 per million output tokens** for Gemma 4 26B A4B. Workers AI
provides a **10,000 Neurons/day** free allocation, with plan and
capacity limits; billed usage depends on account and actual token
accounting. Sources:
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://developers.cloudflare.com/workers-ai/models/gemma-4-26b-a4b-it/
- https://developers.cloudflare.com/changelog/post/2026-07-28-models-require-workers-paid/

**Hypothetical planning math, not measured usage:** Four calls with
**1,000 input tokens and 1,024 output tokens EACH** at those rates would
have a **$0.0016288 nominal token value** before any free allocation
or ancillary costs. This estimate has no enforcement power and is not
a guarantee: actual output may include substantial model reasoning.
The existing offline planning command may calculate this estimate
using `--input-price-per-million 0.10 --output-price-per-million 0.30
--assumed-input-tokens 1000 --assumed-output-tokens 1024` (without
`--export-dir`, to leave existing private files untouched).

**Adapter source review:** Current development Cloudflare adapter uses
`model=@cf/google/gemma-4-26b-a4b-it`, `temperature=0.1`,
`response_format={"type":"json_object"}`, `stream=false`,
and `max_tokens=1024`, **single attempt and no retries**.
The classification default HTTP timeouts are **(3s connect, 15s
read-inactivity)**; optional explicit dev flag
`CLOUDFLARE_PILOT_CLASSIFICATION_READ_TIMEOUT_SEC=30` yields
**(3,30)** with the dev-only pilot gates enabled, and
`CLOUDFLARE_PILOT_CLASSIFICATION_REJECT_IF_BUSY=1` optionally requests
fast capacity rejection. Neither socket timeout is a hard total-runtime
limit. Prior one-case 15s timeout / 30s success does not imply
reliability or accuracy.

**Important:** The offline plan's `--model-id` is **metadata only**.
The actual classification system instruction must match
`api/investigation_classifier.py::_query_classifier`, and the
original user prompt must be exactly the selected persisted
`claim_text`. No such live runner exists in this checkpoint:
the production `call_llm_with_fallback` may use Gemini and Groq
before/after Cloudflare and must **not** be used for isolated
provider-accuracy measurements. A future separately approved capture
implementation must be direct Cloudflare-only, reuse the exact
classification instructions/strict validator, avoid Celery/DB,
record original raw outputs and errors privately (including invalid
JSON rather than rewriting), impose its own hard call budget
and no retries, and never activate `enforce`.

**Next authorization gate:** A future direct live evaluator should first
receive a separate code/contract review and offline mocked tests,
then explicit user approval for **no more than four** Cloudflare
requests on the four approved synthetic claims; only afterward may
any actual provider request or token spend occur.

## Eventually scoring real, captured responses

Only **after separate explicit authorization**, use a controlled capture
process that invokes the identical classification system prompt and uses
each input's **exact supplied claim text**, provider/model/config
provenance, and the complete original model JSON response.

Add rows to the *appropriate provider-specific private*
`predictions.json` **without changing the responses**:

```json
{
  "schema_version": 1,
  "predictions": [
    {
      "case_id": "science_telescope",
      "raw_response": "{\"decision\":\"CLASSIFY\",\"domains\":[{\"code\":\"SCIENCE\",\"evidence\":\"telescope observations\"}]}"
    }
  ]
}
```

The example is **a shape illustration, not captured inference**. Missing
provider responses are **missing**, not fabricated `ABSTAIN`. If a
provider fails, record the failure/timeout and status in separate private
provenance notes; **do not** replace it with guessed output.

Once real responses exist, use the pre-existing **read-only** scorer:

```powershell
..\.venv\Scripts\python.exe .\manage.py audit_investigation_classification `
  --corpus "$corpus" `
  --predictions "$env:USERPROFILE\Documents\TL-Private-Classification-Gemini-01\predictions.json" `
  --json-summary
```

It enforces strict response JSON and verbatim quotation substring checks;
it reports missed/extra subject domains, invalid outputs,
incorrect abstentions, potential partner-authorization leakage/exclusion
and incomplete coverage. **Quotation presence is not semantic grounding**
and must be checked by human reviewers for major decisions.

None of the output metrics is a permit to enable
`INVESTIGATION_CLASSIFICATION_MODE=enforce`. Provider reliability,
strict contract parity outside development, observed costs/latencies,
shadow anti-authority checks, production migration integration and
independent real-claim acceptance remain separate gates.
