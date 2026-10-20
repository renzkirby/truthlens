# TruthLens: model quality and efficiency audit (development only)

## Scope

This is an **isolated public-source, reviewed-dossier benchmark**. It does not
change live TruthLens verification, Gemini/Groq fallback, organization
eligibility, classifier enforcement, DB models, source retrieval, or the
published verdict taxonomy.

At audit construction, the source corpus contains 30 cases, of which **10
have human-approved reference labels and 20 are pending**. The 10 already
recorded Cloudflare verdicts agreed with their case-level reference labels
(10/10), but these are correlated, deliberately constructed dossiers with
manually authored evidence, NOT a representative verification accuracy rate.

The new `audit_verification_providers` command intentionally uses TruthLens's
existing `evaluate_claim_with_persisted_evidence` prompt and result parsing.
Models receive **claim text and the provided public evidence dossier only**;
they never receive proposed labels, gold labels, review rationales or reviewer
identifiers.

### Supported evaluation providers

- `cloudflare` — Workers AI
  `@cf/google/gemma-4-26b-a4b-it`, same model from prior benchmarks.
- `mistral` — Mistral Small 4 (`mistral-small-2603`), a **second independent
  provider**, enabled for a user-authorized live comparison only.
- `both` — sends each selected case once to each provider, sequentially.
  This can consume quotas or paid inference at **both providers**.

Both use a low temperature, JSON object response mode, identical factual
evaluation instructions, up to 2,048 completion tokens by default, a bounded
45-second read timeout, no automatic retries, and a safe stop on auth/credit
or rate-limit failures.

Official API documentation:
- [Cloudflare Workers AI OpenAI-compatible Chat Completions](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/)
- [Mistral Chat Completion API](https://docs.mistral.ai/api)
- [Mistral JSON mode](https://docs.mistral.ai/studio/conversations/structured-output/json_mode)
- [Mistral Small 4 model](https://docs.mistral.ai/models/mistral-small-4-0-26-03)

## Provider usage fields and limitations

The audit prints, when the provider returns valid numeric values:

- `prompt_tokens`: provider-reported input tokens
- `completion_tokens`: provider-reported generated tokens, possibly
  including hidden/internal reasoning
- `reasoning_tokens`: **only when explicitly reported** in provider usage
- `finish`: provider finish reason (`stop`, `length`, etc.)
- `ms`: wall-clock call duration in milliseconds
- `valid`, `matched`, and `failures`: JSON contract, approved reference
  verdict agreement, and transport or response failures

Unreported/invalid counts show `n/a` (unknown), **not zero**. No provider
internal reasoning text is printed or recorded. `reasoning_present` is
a boolean and is not a quality judgment. The final evaluation JSON's
`reasoning` is a **user-facing explanation** and may be saved for manual
review; it is not the model's hidden reasoning trace.

Do not interpret provider token counts as invoices. Cloudflare Workers AI
free usage is measured in *Neurons* rather than simply raw token counts.
Mistral's published Small 4 rates were approximately **$0.15 per 1M input
tokens** and **$0.60 per 1M output tokens** when this experiment was set up;
rates, free-tier eligibility, cached-token treatment, and provider billing
can change. For an indicative **token-only** Mistral estimate when both
numbers are reported:

```
(input_tokens * 0.15 + output_tokens * 0.60) / 1_000_000 USD
```

Check the actual provider dashboards for billable quantities and spend.
Do not model-hop merely to chase free quotas.

## Run the offline tests and preview

Working directory: `backend/truthlens_backend`. No provider keys are needed
for the test suite or dry run.

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_provider_quality_audit `
  api.tests.verification.test_cloudflare_provider_evaluation `
  api.tests.verification.test_realworld_verification_benchmark `
  --settings=truthlens_backend.test_settings `
  --keepdb

..\.venv\Scripts\python.exe .\manage.py audit_verification_providers
```

A dry-run preview makes no network calls, writes no report, and does not
access any TruthLens Claim or VerificationRun database records.

## Live development-only audit

Live audit requires **all** of:

1. `APP_ENV=development` and `DEBUG=True`; staging/production are rejected.
2. `ENABLE_PROVIDER_QUALITY_AUDIT=1`; this flag is independent of the earlier
   `ENABLE_CLOUDFLARE_EVALUATION` benchmark flag.
3. Explicit `--live` and one or more **human-approved** `--case` IDs; at most
   ten selected cases, and the `--limit` must cover the selection.
4. Credentials in the local shell, not code or Git:
   `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` (Cloudflare);
   `MISTRAL_API_KEY` (only if requesting Mistral or both).
5. **Opt-in** `--save-review` to create a local JSON worksheet; without it,
   final explanations are not stored and only compact case metrics print.

On Windows PowerShell, with credentials set privately:

```powershell
$env:APP_ENV = "development"
$env:DEBUG = "True"
$env:ENABLE_PROVIDER_QUALITY_AUDIT = "1"

# First, only two reviewed cases; up to 2 Cloudflare requests.
..\.venv\Scripts\python.exe .\manage.py audit_verification_providers `
  --live --provider cloudflare `
  --case civics__support --case environment_coral_contradict `
  --limit 2 --save-review
```

The output contains `REVIEW_REPORT: ...` pointing to a newly created
`backend/truthlens_backend/.provider_audit_reports/audit-...json`.
This directory is gitignored and the file is created without overwriting an
existing report. **Do not add these reports to Git**. They contain public
claims/evidence and external models' unreviewed generated summaries; inspect
before sharing, even though no secrets or hidden reasoning should be present.

### Optional second-provider comparison

Only if you have intentionally enabled Mistral billing/credits and set
`MISTRAL_API_KEY` locally, run:

```powershell
..\.venv\Scripts\python.exe .\manage.py audit_verification_providers `
  --live --provider both `
  --case civics__support --case environment_coral_contradict `
  --limit 2 --save-review
```

This makes up to **four model requests**. It performs no second-pass LLM
grading, no searches, and no model-automatic gold label changes.

## Human audit rubric (fill report worksheet)

For each final model explanation, independently inspect its **claim,
evidence_snapshot, source_urls and approved_reference_verdict**. Compare
explanations with the actual primary source; never assume a matching verdict
means the reasoning is sound. Complete the worksheet in the JSON report,
using these intended scoring rules:

| Field | 0 | 1 | 2 |
|---|---|---|---|
| `evidence_grounded_0_to_2` | Unsupported/invents facts | Partly supported | Every material reason supported |
| `material_context_preserved_0_to_2` | Drops essential time/negation/qualifier | Partially preserves | Preserves all important context |
| `source_independence_respected_0_to_2` | Counts repeats as independent | Unclear | Does not infer independence or authority |
| `confidence_calibrated_0_to_2` | Strong unsupported certainty | Some caution | Confidence fits the evidence |

`unsupported_inference_present`: true or false (true is a red flag).
`reviewer_notes`: briefly describe any unjustified assertions, missed
contradictions or misleading paraphrases. Set `review_completed=true` only
after examining the explanation and the original evidence. These are **human
judgments**, not automatic quality scores. SATIRE is not yet covered by an
approved reviewed case. Extra reviewers may be necessary for controversial
or ambiguous labels.

## Decision gate

No production promotion merely from 10/10 verdict agreement. Only consider
provider routing changes after explanation audits, stable success rates,
quota and cost verification, case-domain breadth, Filipino-language quality,
manual source-grounding inspections, a realistic traffic/latency budget,
and a separate feature-flagged integration review. The cost of multi-stage
inference must be evaluated at pipeline level, not one model call at a time.
