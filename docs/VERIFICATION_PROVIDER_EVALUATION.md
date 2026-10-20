# TruthLens development-only LLM provider evaluation

This is a **synthetic prompt-quality evaluation**, not a production provider
switch and not proof that any external claim is true. Its eight clearly
fictional/synthetic samples each have a human-authored expected result. Actual
performance must subsequently be checked with labeled real-world cases,
Tagalog/English inputs, source integrity, and blinded review.

## Source of truth and isolation

- Branch: `feat/verification-provider-evaluation`, based on existing
  `feat/partner-governance-eligibility`.
- Production factual pipeline still uses Gemini 2.5 Flash → Groq GPT-OSS 120B.
- No changes to `api/services.py`, claim storage, retry semantics, FactCheck
  API, evidence sources, model verdict authority, or partner eligibility.
- No DB writes. The command uses the **existing**
  `evaluate_claim_with_persisted_evidence` prompt and validator and swaps
  just the *transport* for the duration of an offline comparison.
- No network calls unless both `--live` and
  `ENABLE_CLOUDFLARE_EVALUATION=1` are provided in DEBUG development.
- Do **not** send real claims, user accounts, private records, or protected
  evidence to a third-party model in this evaluation. Use only synthetic
  fixtures and ensure Cloudflare's data handling is approved first.

## Cloudflare setup (development only)

Cloudflare Workers AI requires an account ID and a token authorized to use
Workers AI. See [official model page](https://developers.cloudflare.com/ai/models/%40cf/google/gemma-4-26b-a4b-it/)
and [OpenAI-compatible endpoint](https://developers.cloudflare.com/workers-ai/configuration/open-ai-compatibility/).
`@cf/google/gemma-4-26b-a4b-it` is available on Workers Free as of October 2026.
The allocation is 10,000 Neurons/day; requests can still receive 429 from
daily exhaustion or capacity, and this command **never** retries 429.
Pricing/limits can change.

From `backend/truthlens_backend` in a development PowerShell:

```powershell
# Dry-run first: no credentials or network needed.
..\.venv\Scripts\python.exe .\manage.py evaluate_verification_providers

# In a disposable development shell, set your own secret locally.
$env:ENABLE_CLOUDFLARE_EVALUATION = "1"
$env:CLOUDFLARE_ACCOUNT_ID = "YOUR_ACCOUNT_ID"
$env:CLOUDFLARE_API_TOKEN = "YOUR_PRIVATE_WORKERS_AI_TOKEN"

# Cap the first live check to two API calls.
..\.venv\Scripts\python.exe .\manage.py evaluate_verification_providers --live --limit 2

# Only if you explicitly wish to spend existing Gemini/Groq quota:
..\.venv\Scripts\python.exe .\manage.py evaluate_verification_providers --live --provider both --limit 2
```

With `--provider both`, two providers receive the same original production
evidence-evaluator prompts. The current route means Gemini with Groq fallback
as implemented today, and may fail due to exhausted billing/quota.
Cloudflare credentials are never printed or saved by this command.

## What to inspect

One line per case/provider reports the synthetic case ID, provider, predicted
verdict, expected verdict, strict JSON-contract check, exact verdict match,
and elapsed milliseconds. It does not report evidence bodies or raw model
outputs, and does not change any verification runs or claim verdicts.
`matching` is only a small synthetic benchmark count, **not** a defensible
population accuracy estimate.

Do not allow a model to invent factual conclusions when sources are missing.
Failures and JSON/schema violations must remain distinct from legitimate
`UNVERIFIED`. Compare model score with Gemini/Groq on the same cases, plus
latency, quota incidence, contextual negation, Tagalog, source independence
and human citation audit. Only then propose a separately reviewed,
feature-flagged integration into the factual pipeline. Classification remains
in off/shadow until explicitly approved for enforcement.

To test code offline:

```powershell
..\.venv\Scripts\python.exe .\manage.py test api.tests.verification.test_cloudflare_provider_evaluation --settings=truthlens_backend.test_settings --keepdb
```
