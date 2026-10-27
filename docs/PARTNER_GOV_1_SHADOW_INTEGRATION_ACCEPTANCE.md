# PARTNER-GOV-1 — Shadow classification integration acceptance

**Checkpoint:** Keep the existing `feat/ai-rq2-provider-hierarchy` branch.
Do not open PRs or merge yet. No production rollout, live requests,
unattested model-accuracy claims, or automatic Partner Organization
authorization are included in this checkpoint.

## Decision

Reuse the **existing** `call_llm_with_fallback` provider hierarchy for
operation `investigation_classification`:

1. Gemini (primary)
2. Cloudflare Workers AI / Gemma 4 (secondary)
3. Groq (last fallback)

When development opt-in flags are enabled, the shared router already
validates strict per-provider JSON and quoted claim snippets before
falling through. A valid `ABSTAIN` is a final, safe answer rather
than a failure that automatically advances to another provider.

**Do not introduce a competing classification router or another
Cloudflare 32-case / 16-case budget experiment.** The one-use live
accuracy packet stopped after two calls, with one overclassified
CIVICS+LAW response and one repeated ELECTIONS response.
Changing token limits cannot be assumed to fix semantic quality.

The historical v3 `classification_system_prompt()` and its private
canaries remain immutable evidence for that older checkpoint. Classifier
`v4-primary-subject` intentionally introduces a new response contract and
prompt requiring `primary_subject`. Historical v3 prompt hashes, captures and
accuracy observations must not be rewritten or presented as v4 evidence. Any
v4 empirical evaluation requires a fresh separately versioned capture and
explicit authorization for provider calls.

## Scoped implementation

- Runtime `api/investigation_classifier.py`: record the distinct
  `reason_code=MODEL_ABSTAINED` for a strictly valid provider
  abstention, `INVALID_CLASSIFICATION_RESPONSE` with
  `status=FAILED` for malformed legacy-boundary JSON, and
  `PROVIDER_UNAVAILABLE` with `status=FAILED` for exhausted
  provider routing. Invalid arbitrary dictionary suggestions remain
  `ABSTAINED` and non-authoritative. The v4 schema adds
  `candidate_primary_subject` for shadow/enforce auditability.
- New mocked task/database integration tests:
  `api.tests.verification.test_investigation_shadow_integration`.
  They exercise the real Celery task function through the shared
  Gemini -> Cloudflare -> Groq router and persisted assessment model,
  with no real HTTP, broker, or model requests.
- Existing code still gates mode `off`, `shadow`, `enforce`;
  **do not enable enforce**. Shadow records candidate domains plus
  `candidate_primary_subject` only and NEVER writes
  `ClaimInvestigationClassification`, system
  classification authorization events, or AI verdict changes.

## Offline local acceptance: PowerShell

Update a CLEAN local checkout of the existing feature branch.
From `backend\truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
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

The **nine new integration tests** are not yet user-locally executed
at the time this runbook is authored. The test suite uses Django's
isolated test database but does not send real LLM requests. The
expected acceptance is ALL PASS, zero Django issues, no migration
changes, and no external provider access.

## Optional read-only existing shadow-canary inspection

After testing, one previously recorded claim was assessed in
`shadow` with a `SUGGESTED` assessment, but without an authoritative
`ClaimInvestigationClassification` row. It can be re-inspected
**without queuing a new task or making a new model call**:

```powershell
..\.venv\Scripts\python.exe .\manage.py shell -c "from api.models import InvestigationClassificationAssessment as A, ClaimInvestigationClassification as C; cid='17111917-5bf3-4d07-bc6c-b3a63047a03f'; print('Shadow assessment:', A.objects.filter(claim_id=cid).values('status','candidate_domains','candidate_primary_subject','reason_code','classifier_version').first()); print('Authoritative classification:', C.objects.filter(claim_id=cid).values('domains','primary_subject','source').first())"
```

The record may be absent if the local database has changed. A
`SUGGESTED` candidate is only a non-authoritative proposal. In
the existing eligibility policy, absent authoritative classification
means `NEEDS_CLASSIFICATION`, regardless of the candidate domains.

## Operational guardrails

- This checkpoint evaluated classifier shadow behavior. Automatic subject
  authority and partner routing are now separate controls. Keep
  `INVESTIGATION_ROUTING_MODE=off` unless routing enforcement receives its own
  approval; classifier `enforce` alone must not grant or deny partner intake.
- The three-provider hierarchy is dev-only; production and staging
  will not activate the Cloudflare classification pilot using flags
  alone. To test live `shadow` in a dev worker, a separate explicit
  authorization is needed for new provider calls and quota use.
- Structural contract validation rejects duplicates, unquoted
  evidence, nonexistent codes, a primary subject outside the selected
  domains, extraneous keys and malformed JSON. It **does not** prove the
  chosen subjects or primary subject are semantically correct. A valid but
  incorrect multi-domain result is stored only as a proposal.
- One full live Cloudflare accuracy packet is permanently locked
  after two attempts. Never unlock/retry it. The earlier Cloudflare-02
  and Cloudflare-03 packets are also permanently locked.
- Failure classifications never fabricate authoritative subject
  assignments, and no factual verdicts are changed by this stage.

## Next decision gate

After offline tests pass, decide whether to manually enable
`shadow` for a **bounded development canary** of newly persisted
claims, separately approving the live model calls. Inspect
`SUGGESTED`, `ABSTAINED`, and `FAILED` status/counts, and confirm
`ClaimInvestigationClassification` remains absent for shadowed
claims. Then decide on review/merge. Do not treat shadow validation
as accuracy evidence for `enforce`; authoritative classification
requires a separate, evidence-backed policy decision.
