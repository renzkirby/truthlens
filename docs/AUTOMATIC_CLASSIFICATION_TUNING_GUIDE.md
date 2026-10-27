# Automatic classification tuning guide

This document is the durable developer handoff for TruthLens investigation-subject
classification. Historical one-use Cloudflare capture, benchmark and canary
scripts were intentionally removed before PR preparation.

## Current role

Automatic classification assigns a submitted claim to one or more supported
investigation subject domains and selects one explicit `primary_subject` from
those domains for public-topic projection. It does **not** change factual
verification and it does **not** define a Partner Organization's expertise.

Partner Organization specializations are managed independently. Subject
classification affects Partner Organization intake only after a separately
approved `enforce` rollout.

## Runtime files

- `api/investigation_classifier.py`
  - classification prompt and persistence
  - mode handling
  - idempotence and failure/abstention semantics
- `api/verification/classification_contract.py`
  - strict provider-response contract
  - allowed domains
  - quotation-backed evidence validation
- `api/verification/provider_hierarchy.py`
  - development-only Gemini -> Cloudflare -> Groq hierarchy policy
- `api/verification/cloudflare_pilot.py`
  - Cloudflare classification eligibility, timeout and token settings
- `api/verification/cloudflare_evaluation.py`
  - Workers AI transport adapter
- `api/verification/classification_quality_audit.py`
  - offline comparison of predictions against reviewed reference labels
- `api/verification/classification_capture_plan.py`
  - offline preparation of bounded evaluation packages; it does not call an LLM
- `api/management/commands/audit_investigation_classification.py`
  - read-only classification quality audit
- `api/management/commands/prepare_investigation_classification_evaluation.py`
  - offline evaluation-package preparation
- `api/management/commands/queue_investigation_classifications.py`
  - controlled backlog scheduling for non-off modes

## Classification modes

`INVESTIGATION_CLASSIFICATION_MODE=off`
- no automatic classification job is authoritative;
- normal Partner Organization intake remains backward-compatible.

`INVESTIGATION_CLASSIFICATION_MODE=shadow`
- model suggestions/abstentions are stored for evaluation;
- suggestions cannot grant or deny Partner Organization eligibility;
- use this mode for prompt/model tuning.

`INVESTIGATION_CLASSIFICATION_MODE=enforce`
- an authoritative classification may participate in Partner Organization
  specialization matching;
- do not enable without separate accuracy and rollout approval.

Tuning must proceed through `shadow` first. A successful unit test or a small
canary is not enough to authorize `enforce`.

## Runtime timing

When classification is enabled, the factual pipeline persists the normalized
claim proposition immediately after the claim gate has accepted it, then queues
subject classification as a separate Celery job **before** evidence retrieval and
final verdict reasoning continue. The factual-verification task does not wait for
classification to finish.

This makes the two operations parallel-capable without coupling their outcomes:
classification failure cannot turn a factual verification into a failure, and a
verdict may be returned before classification finishes. In `off` mode the early
classification persistence/dispatch path is skipped so legacy behavior remains
unchanged.

Published-claim resolution and exact cached-result paths retain safe fallback
classification triggers when the normal claim-gate path is bypassed.

## Strict response contract

Do not weaken the contract to make a provider look more accurate.

A valid provider response has exactly:
- `decision`
- `primary_subject`
- `domains`

`ABSTAIN` requires `primary_subject: null` and an empty domain list.

`CLASSIFY` requires 1-3 distinct supported domain codes and exactly one
`primary_subject` that is also present in the selected domains. Each selected
domain must include evidence accepted by the shared contract: quoted text must
actually occur in the original claim. The primary subject is explicit model
output; it must never be reconstructed from sorting or `domains[0]`. Surplus
fields such as verdict, jurisdiction, confidence or free-form explanations are
rejected.

The strict boundary applies after provider fallback as well; malformed Gemini or
Groq output must not become authoritative merely because Cloudflare was skipped.

## Recommended tuning workflow

1. Work on a fresh branch from the latest integrated `main`.
2. Keep classification in `shadow`.
3. Change one meaningful variable at a time: prompt wording, provider model or a
   bounded inference setting.
4. Run the strict classification unit/integration tests.
5. Prepare predictions using the offline evaluation package workflow.
6. Audit predictions against a human-reviewed reference corpus.
7. Review both domain-set errors and primary-subject errors:
   - an extra domain can wrongly exclude an otherwise qualified organization;
   - a missing domain can wrongly broaden eligibility;
   - a wrong primary subject can place the claim under the wrong public topic;
   - a malformed response must fail closed.
8. Use a small development shadow canary only after offline review.
9. Inspect provider telemetry and stored shadow assessments.
10. Discuss `enforce` only after broader reviewed accuracy and rollout safety
    are acceptable.

## Core regression tests

At minimum, run:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_investigation_shadow_integration `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_classification_latency_policy `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_classification_capture_preparation `
  api.tests.organization.test_verification_scope `
  api.tests.workspace.test_assignment_service `
  api.tests.workspace.test_assignment_api `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

Before merge, also run the full backend regression suite.

## Reference corpus

The repository fixture
`api/verification/fixtures/investigation_subject_review_v1.json` is a synthetic
review fixture and its review state must be respected by the audit tooling.

The 32-case corpus used for the October 22 human-reviewed accuracy work was kept
private. It must not be silently reconstructed from logs or treated as equivalent
to the repository fixture. If exact reproduction is required, obtain the reviewed
corpus separately from the project owner.

Changing the classification prompt, allowed-domain policy, evidence contract, or
normalization rules invalidates evaluation fingerprints tied to the older
configuration. Re-run reviewed evaluation rather than comparing incompatible
scores.

The existing repository quality-audit corpus was designed primarily for
**domain-set** accuracy and does not provide reviewed primary-subject labels for
every multi-domain case. Therefore a passing domain-set audit is not evidence
that `primary_subject` is accurate. Before any `enforce` rollout that makes
automatic primary subjects authoritative for public Community topics, evaluate
primary-subject choices against separately reviewed reference labels as an
additional gate.

## Known observed weaknesses

Previous development evaluation has observed:
- overclassification, for example a CIVICS claim also receiving LAW;
- duplicate-domain output from a model, correctly rejected by the contract;
- deliberate ambiguity that should produce `ABSTAIN`;
- Gemini billing/quota rejection in the development account;
- intermittent Cloudflare read timeouts;
- structurally valid output that can still be semantically wrong.

Provider success therefore is not equivalent to classification quality.

## Factual verification is separate

The factual-verification pipeline can operate normally while classification is
`off`. Development testing has completed a real TEXT verification in which
Gemini failed at claim gate, Groq handled claim gate/evidence assessment, and
Cloudflare successfully produced the final persisted-evidence verdict.

Do not modify factual-verification verdict logic merely to improve subject
classification metrics.

## Co-developer bounded-evidence branch

The existing `fix/bounded-evidence-reasoning` branch was created before the
current integrated AI/governance work and must not be merged mechanically.

Important integration notes:
- its `0081_related_fact_check_decision.py` conflicts with the governance
  migration chain beginning at `0081_partner_verification_scope.py`;
- recreate/renumber that migration from the final integrated `main` instead of
  carrying two independent 0081 leaves;
- its `Claim.relatedness_context` field explains the development-only schema
  drift that previously motivated a temporary repair migration; that repair was
  removed before PR preparation;
- a developer database that previously applied the old co-developer `0081`
  may still contain those physical columns/migration records; use a clean
  development database or explicitly reconcile that local-only schema before
  applying a future renumbered relatedness migration;
- `services.py`, `tasks.py`, `telemetry.py` and verification tests overlap
  materially with the provider hierarchy;
- preserve current Vault relevance gating when integrating asynchronous
  relatedness work;
- bounded evidence selection/truncation changes the current lossless-evidence
  invariant and requires explicit review rather than a conflict-resolution pick.

The safest path is to integrate that work from a fresh branch based on the final
merged `main`.
