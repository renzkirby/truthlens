# Universal LLM provider hierarchy

TruthLens can route supported runtime AI operations through the following order:

1. Gemini
2. Cloudflare Workers AI / Gemma
3. Groq

The policy is **off by default**. Merging the implementation does not activate it.

## Activation

Set the following environment variable on the backend worker/runtime:

```
ENABLE_UNIVERSAL_LLM_HIERARCHY=1
```

Cloudflare also requires its existing credentials:

```
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_API_TOKEN=<API token>
```

Gemini and Groq continue to use their existing provider credentials and model
configuration.

Do not commit credentials to the repository.

## Runtime scope

The universal hierarchy applies to the production runtime AI operations that
have explicit response validation, including:

- ClaimGate claim extraction and retrieval-query generation
- claim equivalence
- fact-check relevance
- investigation subject classification
- evidence assessment
- persisted-evidence verdict evaluation
- Google Fact Check verdict evaluation
- Tavily verdict evaluation
- related published-fact-check contextual classification

The offline Phase 3 semantic benchmark executor remains intentionally
Gemini-only so historical paired evaluations stay comparable.

## Failure behavior

A provider response is accepted only after the operation-specific contract
passes. Empty, malformed, incomplete, contradictory, or structurally invalid
responses fall through to the next provider.

The router does not convert provider failure into an authoritative verdict.
When every eligible provider fails, the existing operation-specific failure or
abstention behavior remains in effect.

Cloudflare is attempted at most once for a routed operation. Existing
job-scoped degradation behavior prevents repeatedly calling a failed provider
within one verification execution.

## Rollback

Remove or unset:

```
ENABLE_UNIVERSAL_LLM_HIERARCHY
```

and restart the backend/Celery workers that loaded the old environment.

The legacy development-only AI-RQ-2 pilot flags remain supported separately.
They are not required when the universal hierarchy is explicitly enabled.

## Validation before deployment

Run the focused provider, Cloudflare, verdict-contract, and relatedness tests
before enabling the flag. Production activation should happen only after the
feature branch has been merged and the deployed workers have the Cloudflare
credentials available.
