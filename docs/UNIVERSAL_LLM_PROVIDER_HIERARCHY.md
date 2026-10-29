# Universal LLM provider hierarchy

TruthLens can route supported runtime AI operations through the following order:

1. Gemini
2. Cloudflare Workers AI / Gemma
3. Groq

The policy is **credential-aware and automatic**. After this code is deployed,
the universal hierarchy turns on automatically when the backend has a valid
Cloudflare account ID and a non-empty Cloudflare API token.

No separate `=1` deployment step is required for normal activation.

## Activation and override

Automatic activation requires the existing Cloudflare credentials:

```
CLOUDFLARE_ACCOUNT_ID=<account id>
CLOUDFLARE_API_TOKEN=<API token>
```

Gemini and Groq continue to use their existing provider credentials and model
configuration.

When those Cloudflare credentials are present and
`ENABLE_UNIVERSAL_LLM_HIERARCHY` is unset, TruthLens automatically uses the
universal hierarchy.

Optional explicit overrides:

```
ENABLE_UNIVERSAL_LLM_HIERARCHY=1
```

forces the hierarchy on for controlled diagnostics, while:

```
ENABLE_UNIVERSAL_LLM_HIERARCHY=0
```

is the emergency kill switch and disables automatic activation even when
Cloudflare credentials are configured.

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

Set:

```
ENABLE_UNIVERSAL_LLM_HIERARCHY=0
```

and restart the backend/Celery workers that loaded the old environment.

Leaving the variable unset allows automatic activation whenever valid
Cloudflare credentials are present.

The legacy development-only AI-RQ-2 pilot flags remain supported separately.

## Validation before deployment

Run the focused provider, Cloudflare, verdict-contract, and relatedness tests
before deployment. After merge, automatic activation occurs on the first
backend/Celery process start that sees valid Cloudflare credentials, unless the
kill switch is set to `0`.
