# PARTNER-GOV-1 — Offline subject-classification accuracy and eligibility acceptance

**Checkpoint:** implementation in `feat/ai-rq2-provider-hierarchy`; final
manual acceptance is **PENDING**, not granted by synthetic tests.

## Why this separate gate is required

The previously approved live Europa Clipper `shadow` task completed
`SUGGESTED`, with `candidate_domains=["SCIENCE","TECHNOLOGY"]` and **no**
authoritative `ClaimInvestigationClassification` row. Gemini returned 402,
Cloudflare timed out after ~15.337s, and Groq supplied the accepted
suggestion. A separately approved direct Cloudflare-only inference, with
classification read-inactivity timeout 30s and `rejectIfBusy=1`, returned
the same domain codes in ~16.132s. This is evidence of fallback behavior
and a plausible result on **one claim**, not evidence of model
classification accuracy across the supported taxonomy.

The persisted `InvestigationClassificationAssessment` stores approved
**candidate domain codes**, reason/status, version and input fingerprint,
but does **not** retain the model's per-domain quoted evidence or a
reviewer-approved reference label. Do **not** reconstruct or invent those
quotations. Without separately captured complete model responses, the
existing database cannot answer whether the model's quotations
supported each assigned subject.

## What this offline-only checkpoint adds

- `api/verification/fixtures/investigation_subject_review_v1.json`:
  **32 synthetic illustrative cases** spanning the **12 actual domain
  codes**, including explicit single subjects, cross-domain subjects,
  ambiguous/weak-evidence claims, geography traps, contradictory
  reports, prompt-injection strings and unsupported/out-of-scope cases.
  Every label is explicitly `review.status="PENDING"` and every
  classification is a **draft reference proposal**, not ground truth.
- `api/verification/classification_quality_audit.py`: a pure parser
  and descriptive scorer. It reuses the **existing strict provider
  response contract** and the existing conservative all-subject
  `eligibility_reason` check for a counterfactual eligibility risk
  calculation. It does not modify either policy.
- `python manage.py audit_investigation_classification`: a local
  **read-only, no-network** management command that scans the corpus
  or compares *already captured* raw JSON responses to individually
  reviewed references. Never submits AI requests, reads claims from
  the application database, schedules Celery, writes files, or
  authorizes investigations. Output shows aggregate metrics and
  non-sensitive case IDs only.
- `api/tests/verification/test_classification_quality_audit.py`:
  regression cases for 12-domain coverage, reviewer gating, malformed
  inputs, missing predictions, hallucinated quotes, overclassification,
  incorrect abstentions, and both potential overauthorization and
  overexclusion under the all-domains-must-match rule.

These are **audit tooling tests**, not model-accuracy test results.

## Review protocol before producing a score

1. Have qualified reviewers inspect and, where needed, correct the
   draft domain labels based on the **subject explicitly expressed**
   in each claim; do not use truth status, geopolitical jurisdiction,
   evidence source credibility, brand, or organization expertise as
   a substitute for subject evidence.
2. For every case, document whether it supports **1–3 distinct
   subject domains** or genuinely requires `ABSTAIN`. Both a
   multi-domain classification and a deliberate abstention are valid
   when justified. Reviewers should discuss disagreements, especially
   SCIENCE-vs-TECHNOLOGY overlap and geography-only cases.
3. Only after a reference is actually reviewed, change
   `review.status` from `PENDING` to `APPROVED`, providing nonempty
   `review.reviewer` and `review.notes`. These fields are a local
   provenance claim, **not cryptographic attestation**. For eventual
   rollout, require a separately accepted independent-review protocol;
   the script cannot validate reviewer qualifications or consensus.
4. Evaluate only **previously captured**, approved provider responses
   from a separately authorized process or an existing consented,
   local archive. Do **not** call providers to populate predictions
   under the guise of an offline audit.
5. Review the scorer's case IDs for invalid quotes, missing outputs,
   overclassification, incorrect labels, abstention behavior and
   counterfactual organization eligibility. Compare quotations
   manually with the original text, not just substring presence.

### Corpus format (illustrative)

```json
{
  "schema_version": 1,
  "cases": [
    {
      "id": "science_telescope",
      "claim_text": "Astronomers published telescope observations describing water vapor in the atmosphere of a distant planet.",
      "tags": ["single_domain"],
      "draft_expected": {
        "decision": "CLASSIFY",
        "domains": ["SCIENCE"]
      },
      "review": {
        "status": "PENDING",
        "reviewer": "",
        "notes": ""
      }
    }
  ]
}
```

Once genuinely reviewed, the `draft_expected` label should reflect
what reviewers approved; it retains its field name because the
bundled default corpus remains a draft.

### Prediction format (local input only; never in Git)

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

`raw_response` must be the **unaltered complete JSON text** previously
returned by a provider, including the per-domain quote evidence.
No fallback reconstruction is permitted from persisted
`candidate_domains`. Capture provider name/model, flags, input
revision, time, selection method and reviewer provenance separately
in secure experiment notes; do not commit credentials, personal
claims or full production prompts to the repository.

The scorer accepts up to 120 cases and rejects duplicate/unknown
prediction IDs. Missing predictions for approved cases prevent a
complete accuracy rate. Draft-only corpus **never reports accuracy**.

## Eligibility and risk semantics

True organization intake authorization remains governed by the
authoritative `ClaimInvestigationClassification` and the existing
all-subjects-subset specialization rule, alongside organization
status, membership/capability and assignment conditions.

The audit simulates *hypothetical* outcomes only:

- **Potential scope leak:** a predicted CLASSIFY domain set could
  qualify an organization that would not qualify for the reviewed
  reference. Example: reference SCIENCE+TECHNOLOGY, model predicts
  only SCIENCE; a SCIENCE-only partner would be incorrectly allowed.
  A CLASSIFY output on a reviewer-ABSTAIN reference also counts.
- **Potential scope exclusion:** a model adds unsupported domain(s),
  excluding a partner covering all reviewer-reference subjects;
  or ABSTAINS when the reviewed reference requires classification.
- **Invalid JSON/quotation:** excluded from exact matches and reported
  separately; deterministic validation must reject unsupported
  codes, duplicated domains and claim-absent quotations.
- **Exact match:** validated subject-domain set **or** approved
  ABSTAIN exactly equals reviewed reference. This does not measure
  human linguistic judgment beyond the approved rubric.

No metric is a grant of permission. The report always contains
`eligible_for_automatic_enforcement=false` and the CLI always
prints `enforcement_approved=false`.

## Commands (offline; zero provider requests)

From `backend/truthlens_backend` after pulling the existing branch:

```powershell
# Safe baseline: coverage only. All built-in labels are pending review.
..\\.venv\\Scripts\\python.exe .\\manage.py audit_investigation_classification

# Optional sanitized machine-readable summary:
..\\.venv\\Scripts\\python.exe .\\manage.py audit_investigation_classification --json-summary

# Only AFTER qualified human approvals and capture of provider responses:
# Use local untracked/private files, not database rows or invented responses.
..\\.venv\\Scripts\\python.exe .\\manage.py audit_investigation_classification `
  --corpus "C:\\private\\approved_subject_corpus.json" `
  --predictions "C:\\private\\captured_classifications.json" `
  --json-summary
```

## Test gate (no database writes by this command; tests use normal test DB)

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_classification_fallback `
  api.tests.verification.test_classification_latency_policy `
  api.tests.organization.test_verification_scope `
  --settings=truthlens_backend.test_settings --keepdb

..\\.venv\\Scripts\\python.exe .\\manage.py check
..\\.venv\\Scripts\\python.exe .\\manage.py makemigrations --check --dry-run
```

No live AI calls are authorized by these tests or documentation.
All collected actual predictions require independent review and
separate user authorization before any further provider requests.

## Acceptance decision and blockers

**Offline auditing infrastructure:** pending user-local test output.

**Actual automatic classification accuracy:** **NOT MEASURED**.
The included 32 synthetic draft cases have zero reviewer-approved
references, and no captured predictions have been provided.

**PARTNER-GOV-1 `enforce` authorization:** **NOT APPROVED**.
Before proposing a transition, require:
- Human-approved, representative references covering every supported
  domain, cross-domain/ambiguous, hallucination/prompt-injection and
  abstention cases. Review methodology, sample size and acceptable
  error thresholds must be agreed with the team.
- Full captured model responses and configuration provenance on those
  references, evaluated without conflating one successful Groq and
  Cloudflare canary with a benchmark.
- **No unresolved cases of potential overauthorization**; discuss
  any overexclusion under the conservative multi-domain policy.
- Evidence that shadow-mode suggestions never create authoritative
  classifications or partner intake rights, including claim
  fingerprint/idempotency, assignment races, and membership
  capability regressions.
- A separate explicit governance/engineering decision on whether to
  retain ALL-subjects matching for cross-disciplinary claims.
- Stable worker/config hygiene and acceptable provider-outage and
  latency behavior. This audit does not address Cloudflare
  evidence-assessment reliability.
- No stacked-branch PR or merge until co-development dependencies
  are reviewed and accepted.

**Default policy stays** `INVESTIGATION_CLASSIFICATION_MODE=off`.
No partner permissions or existing AI/RAG verdict logic changed.
