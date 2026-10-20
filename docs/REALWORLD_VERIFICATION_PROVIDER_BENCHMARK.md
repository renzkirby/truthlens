# TruthLens — review-gated real-world evidence benchmark

## Purpose and limits

This is a **source-linked claim/dossier evaluation**, not a full live
fact-check. The 30 candidate claims cover 12 subjects, real public sources,
English and Filipino. Some assertions are intentionally wrong variants of
documented facts; **do not present those variants as actual circulating posts**.
Evidence is a concise, manually authored, dated snapshot with source URLs, not
a scraped webpage or fresh live retrieval. Multiple cases reuse a source, so
the 30 observations are **not independent** and no population accuracy
confidence intervals are justified.

The proposed labels were created by an assistant based on identified primary
public sources. Four labels (two 1987 Constitution and two RA 9346 variants)
were subsequently **explicitly approved by the TruthLens project reviewer
after reviewing source materials on 20 October 2026**; the other 26 remain
PENDING. Approved-label rationales are assistant-drafted source explanations,
not quotations from the reviewer. See `docs/REALWORLD_REVIEW_BATCH_01.md`
for the approval record. An approved reviewed label is a reference for this
bounded case, not proof of model correctness. In particular,
`UNVERIFIED` describes lack of support **in the supplied dossier**, not a
claim that no answer exists in the world.

## Review protocol (required before scoring)

Open `api/tests/fixtures/realworld_verification_cases.json`. For each case:

1. Open the `sources[].url`, confirm the page/publisher, date (if supplied),
   specific support or contradiction and whether the evidence summary is fair.
   If a link is stale, ambiguous, or requires other sources, replace/revise
   the case and note why; do not approve an unsupported label.
2. Independently decide `FACT`, `FAKE`, `MISLEADING`, `UNVERIFIED` or
   `SATIRE` **from the recorded evidence only**, not from `proposed_verdict`.
   Source absence must not be treated as disproof. Record disagreements,
   context limitations, and confidence in the rationale. For a disputed
   MISLEADING versus FAKE label, obtain an independent second review.
3. If the case meets the evidence standard, update the JSON review object:

```json
"review": {
  "status": "APPROVED",
  "reviewer": "reviewer-identifier",
  "reviewed_at": "2026-10-20",
  "approved_verdict": "FACT",
  "rationale": "Independent review of the specified source provision and wording.",
  "source_checked": true
}
```

   Otherwise leave PENDING or set REJECTED with rationale. Do not simply
   bulk-copy `proposed_verdict` into the review decision. The first four
   have already received explicit reviewer approval; only those four
   reference labels are currently eligible for scored comparisons. Review changes
   should be submitted as a separate traceable Git commit. Do not embed user
   identifiers, sensitive evidence, credentials, or nonpublic claims.
4. Keep evaluation models blind to the proposed/approved labels. The command
   sends only the authored claim and evidence snapshot.

## Safe commands (PowerShell)

From `backend/truthlens_backend`:

```powershell
..\\.venv\\Scripts\\python.exe .\\manage.py test `
  api.tests.verification.test_realworld_verification_benchmark `
  api.tests.verification.test_cloudflare_provider_evaluation `
  --settings=truthlens_backend.test_settings --keepdb

# Default: dry run, NO inference, no database writes, approval summary.
..\\.venv\\Scripts\\python.exe .\\manage.py evaluate_realworld_verification_providers

# After independent approvals, and local development-only credentials/flags:
..\\.venv\\Scripts\\python.exe .\\manage.py evaluate_realworld_verification_providers `
  --live --limit 4

# For a small reviewed case selection:
..\\.venv\\Scripts\\python.exe .\\manage.py evaluate_realworld_verification_providers `
  --live --case civics__support --limit 1
```

The illustrated case flag above must exactly match a case ID in the JSON file;
inspect the file before selecting it.

Requires `DEBUG=True`, `ENABLE_CLOUDFLARE_EVALUATION=1`, and the
development-only `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` for
Cloudflare. The default output allowance is **2048 completion tokens** from
the prior reasoning-truncation diagnostic; 256–4096 is accepted.
`--provider both` optionally executes both Cloudflare and existing
Gemini/Groq routing, potentially consuming 2x provider calls. Avoid using
the current route while Gemini returns HTTP 402 and Groq rate-limits.

A scored `--live` call is forbidden until **all selected** cases have
complete independent approval metadata. Request limits are 1–30 cases,
sequential only, with no retries. HTTP 402/403/429 barriers stop additional
calls to the affected provider. There are no DB writes, no claim verdict
updates, no changes to Community, institutional publication, or
classification enforcement.

## Evaluation decision gate

The command reports case-wise reviewed-label matches, raw JSON-contract
validity, provider failures, execution time, median duration, and
expected/predicted confusion pairs. Separately record billable usage from
vendor dashboards; this command currently does **not** know actual pricing,
prompt token counts, or reasoning-token expenses, and should not guess.
Re-run a stratified reviewed sample for stability, with human review of
evidence-grounding and content (not only verdict labels), then test alternate
budget models. One source is not independent verification of itself.

Approval to switch *live* provider routing would require a separate
production design review: rate/credit limits, bounded retry/circuit breaker,
fail-safe verdict handling, performance budget, and quality parity on
real-world and adversarial cases. No live model promotion is authorized.

## Special label adjudication

Two provisional mixed-context cases (`technology_iphone_contradict` and
`environment_coral_contradict`) intentionally test disputed `MISLEADING`
versus `FAKE` boundaries. They are **not settled reference labels**: the
reviewer should inspect the Apple and NOAA sources, explicitly decide whether
a partly correct but materially false compound statement is MISLEADING or
FAKE under TruthLens's actual rubric, and document that reasoning. Consider
separate second-review adjudication before including these cases in accuracy
statistics. The corpus does not yet contain independently verified SATIRE cases.
