# PARTNER-GOV-1 — Automatic claim-classification pre-merge acceptance

> **Superseded contract note (2026-10-28):** This document records the earlier
> v3 behavioral gate. The current `v4-primary-subject` branch adds an explicit
> `primary_subject`, persists `candidate_primary_subject` in shadow/enforce
> assessments, and introduces migration `0098`. Historical v3 model captures
> that omit `primary_subject` must not be scored as v4 predictions or used to
> authorize v4 `enforce`.


**2026-10-22. This gate precedes any PR/merge or authorization of
automatic partner eligibility.** It does not reopen Cloudflare budget
experiments or turn on real provider inference.

## Two different acceptance questions

1. **Behavioral safety (code/tests):** Does the background claim
   classifier produce strict source-quoted domain responses, preserve
   factual-verdict outputs, operate after saved claim text, store only
   non-authoritative suggestions in shadow mode, handle provider outage
   and assignment races, and reject malformed or unsupported output
   even when an older provider route is active?
2. **Real model quality (human references):** Does the *actual selected
   classification provider route* produce correct subject/ABSTAIN
   decisions when compared with separately human-approved cases,
   without creating hypothetical Partner Organization scope leaks?

Behavioral safety can be tested with no external inference. Model
accuracy **cannot** be established by mocking model outputs or
merely comparing the one previously successful Cloudflare response.
The complete reference corpus has 32 approved synthetic cases and
12 subject codes, but only one scoreable direct Cloudflare response
has been measured; the other 31 were not captured.

## Code hardening added for this gate

- `api/investigation_classifier.py` now applies the strict,
  provider-independent `validate_classification_response` contract
  to every raw provider reply in `_query_classifier`, even if
  development-only Cloudflare/hierarchy flags are disabled.
  Unsupported shape/quotes fail closed; raw provider data cannot
  contain extra subject, jurisdiction, verdict or confidence fields.
- `validate_model_suggestion` reuses that same contract for every
  candidate dictionary, protecting both `shadow` and `enforce`
  against future direct entry-point callers bypassing the wrapper.
- Four focused tests cover strict payload fields, the all-modes
  provider boundary, no creation of authoritative classifications
  from loose responses, and shadow candidates never granting
  eligibility via the existing authoritative matching policy.

This is structural/evidence-contract safety, **not domain correctness**:
the AI can quote a real substring and still choose the wrong domain.
No change to provider order, retry policy, evidence/RAG verdicts,
organization specializations, migration files or UI.

## Last scoped local behavioral regression (no AI requests)

From a clean `feat/ai-rq2-provider-hierarchy` checkout, in
`backend\truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_classification_latency_policy `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_classification_backlog_command `
  api.tests.organization.test_verification_scope `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check

..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

This is a targeted, mocked regression, **NOT** an accuracy benchmark.
No database writes are made by the *audit commands*, but Django
`TestCase` creates/uses its isolated test DB during tests.
Cloudflare-02 and Cloudflare-03 remain locked and must never be
replayed.

## Human-approved reference quality gate

The privately stored
`PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json` must
be loaded from the user-local machine. It has 32 user-confirmed
two-reviewer consensus cases (co-reviewer assent user-relayed), not
independently verified reviewer identity. The public repository
fixture intentionally remains 32 PENDING.

The no-network audit command already exists:

```powershell
$corpus = "$env:USERPROFILE\Downloads\PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json"

..\.venv\Scripts\python.exe .\manage.py audit_investigation_classification `
  --corpus "$corpus" --json-summary
```

For a genuine quality measurement, separately capture complete
unaltered model JSON strings for all 32 case IDs **under an explicitly
approved bounded evaluation plan**, with provider/model/prompt version,
token cap and usage/failure provenance. Do not fabricate quotations
from persisted `candidate_domains` or reconstruct from reference
answers. Evaluate:

```powershell
..\.venv\Scripts\python.exe .\manage.py audit_investigation_classification `
  --corpus "$corpus" `
  --predictions "<PRIVATE_UNALTERED_CAPTURED_PREDICTIONS_JSON>" `
  --json-summary
```

The existing audit reports approved, predicted, missing,
exact_matches, wrong_domains, invalid_json_or_quotes,
missed_classifications, overclassified_abstentions,
potential_scope_leaks, potential_scope_exclusions,
coverage_complete and exact_match_rate (only with complete capture).
It **always** sets `eligible_for_automatic_enforcement=false`;
passing it does not itself authorize production activation.

Before any new live model calls, the owner must separately approve
the chosen provider route, number of billable requests, cap/budget
and failure behavior. **No such new call approval is inferred from
this document or the user's instruction to validate.**

## Conservative release interpretation

- **Pass behavioral regressions + shadow trial**: may consider
  enabling `INVESTIGATION_CLASSIFICATION_MODE=shadow` in an explicitly
  controlled, authorized development environment and verify private
  `InvestigationClassificationAssessment` statuses. Shadow
  suggestions are *not* authoritative
  `ClaimInvestigationClassification` rows. No auto eligibility.
- **Poor/incomplete quality score**: retain shadow/off; fix genuine
  classification blockers only. Do not silently promote suggestions.
- **Good quality score**: review individual false positives,
  omissions, weak-evidence and prompt-injection cases and define an
  accepted evaluation policy before any `enforce` mode decision.
  This synthetic corpus alone is not representative of all real
  claims, and a zero-leak result in 32 cases is not a guarantee.
- **No production rollout is authorized** by this gate; Cloudflare
  pilot itself remains development-only.

The acceptance sequence is intentionally short:
**focused regressions -> one independently authorized real output
capture + score -> one decision on shadow vs enforce -> PR review.**
No additional token-budget study or repeated four-call canaries.
