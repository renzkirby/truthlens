# URL claim/report integrity — developer acceptance

Scope: GitHub issue #135 (URL claim/report mismatch) and URL-side source
provenance from #134. Branch `fix/url-claim-integrity-provenance` is based
on the isolated Cloudflare pilot, **not main**. Do not merge this phase
without manual approval. Do not run live AI requests for these checks.

## Behavior

- The same `cleaned_claim` sent to URL evidence assessment and the final
  persisted-evidence evaluator is now written to `Claim.context_text`
  on normal URL GFC/Tavily results and handled Tavily failure paths.
- Blank/invalid gated claims abstain before expensive GFC/Tavily verification,
  without writing any verdict.
- The submitted original URL remains a separate `Claim.url_link` source.
  The raw article extraction is not substituted for the evaluated claim.
- URL report `ai_sources` for persisted runs is projected from the
  **same evidence role used by that final evaluator**:
  FACT_CHECK for GFC or SECONDARY for Tavily. Every distinct safe public
  URL is represented once for display, preserving persisted item/group order.
  Evidence itself is **not truncated, re-ranked, or discarded**.
- Existing no-run compatibility retains the legacy source selection.
  Older saved reports are not retroactively changed; avoid re-running
  claims solely to update their source cards.
- Deep Analysis explicitly distinguishes persisted-evidence source links
  from legacy report links and avoids claiming editorial independence.

## Local validation (offline)

From the project root:

```powershell
git fetch origin
git switch fix/url-claim-integrity-provenance
git pull --ff-only origin fix/url-claim-integrity-provenance
cd backend/truthlens_backend
```

Then:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_evidence_presentation `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_evidence_dossier `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_pilot_evidence_budget `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

From `frontend/frontend`, run the existing frontend checks appropriate
to the project. Tests with simulated unavailable providers may log failures
deliberately; judge by the final test result, not individual mock logs.

## Review gate

1. Confirm normal URL GFC and Tavily paths display precisely the
   normalized proposition evaluated (including attribution, dates, and
   prospective vs retrospective wording), rather than scraped navigation.
2. Confirm Source cards correspond to the persisted links for the
   evaluated evidence role; missing evidence does not create guessed links.
3. Confirm original source URL is still shown separately.
4. Confirm URL OUT_OF_SCOPE/missing claim cases do not call retrieval or
   fabricate a verdict; evaluator outage still follows established
   terminal lifecycle behavior.
5. Review an article with extensive navigation and an ambiguous article.
   **The current cleaning/claim-gate method is not yet a demonstrated
   boilerplate-resistant extractor**; this patch fixes report consistency,
   not the truth of the extracted proposition. Do not claim QA #135 fully
   resolved until a separate claim-fidelity inspection is completed.
6. Recheck TEXT and Cloudflare pilot offline regressions.

No PR, merge, live provider call, or production flag change is part of
this phase's implementation.
