# VERIFY-URL-QA-2 — URL article-body fidelity (offline acceptance)

**Branch:** `fix/url-article-body-fidelity`

**Parent:** `fix/url-claim-integrity-provenance` (unmerged) so its proven
report/evaluator consistency changes and the existing Cloudflare pilot remain
intact. **No PR/merge/promotion is authorized as part of this checkpoint.**

## Root cause / targeted change

Previously `clean_extracted_text()` removed only Markdown links and short
lines and passed the **first 3,000 characters** of Tavily raw content to
ClaimGate. A long Apple-style navigation section could occupy the whole
input, obscuring the actual article or quote. The URL report now separately
displays the normalized evaluated claim (parent branch), but this alone did
not guarantee that the extraction input was usable.

`api/verification/url_article_context.py` is now a deterministic,
Markdown-focused selector:

- Recognizes explicit navigation heading sections, including multiple
  headings merged onto a single line by extraction; it avoids treating those
  sections as article passages.
- Keeps original title and publication date where present, and copies
  complete original article sentences without generating a new assertion.
- Keeps short complete statements, quoted attributions, dates, negations,
  planned versus occurred qualifiers, and multi-line wrapped passages.
- Examines content after the old 3,000-character cutoff, then assembles up
  to 3,000 characters of selected text *at complete sentence boundaries*.
- When the extraction supplies **no usable factual passage**, returns
  empty. The URL task records `url_content_insufficient` and terminates
  `ABSTAINED` (without a fabricated AI verdict), **before** ClaimGate,
  Google Fact Check, Tavily search, persisted assessment or final evaluation.

The existing request to Tavily Extract, evidence storage/selection, GFC
precedence, provider fallback, Cloudflare budgets and lifecycle transitions
for other cases are unchanged. The raw original URL remains available in
`Claim.url_link`.

## Limits / quality gates

This is a conservative article-context selector, **not** a machine proof of
claim entailment or full multilingual HTML readability. The subsequent LLM
can still misinterpret an article or produce an unsupported paraphrase.
The heuristic can deliberately abstain on some true headlines or passages
without punctuation rather than invent a proposition from navigation.
No assertion of factual-quality acceptance follows from passing unit tests.

Do not add a keyword-only entailment check, silently change a model verdict,
hardcode the Apple website, or broaden to a claim-ranking redesign in this
phase. Coordinate deeper claim-grounding and metadata-context improvements
with #131; see #135 for the URL report issue and #134 for source provenance.

## Offline commands

From project root:

```powershell
git fetch origin
git switch --track origin/fix/url-article-body-fidelity
```

If it already exists locally, use `git switch fix/url-article-body-fidelity`
then `git pull --ff-only origin fix/url-article-body-fidelity`.

From `backend/truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_url_article_context `
  api.tests.verification.test_run_url_runtime `
  api.tests.verification.test_evidence_presentation `
  api.tests.verification.test_run_text_runtime `
  api.tests.verification.test_persisted_evidence_reasoning `
  api.tests.verification.test_pilot_evidence_budget `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

Do not start Celery or run a live verification to validate this change.
This test selection uses synthetic and mocked fixtures only.

## Acceptance checkpoints

1. Navigation-heavy body appears in ClaimGate input even when it occurs
   beyond the raw extractor's former 3,000-character prefix.
2. Nav-only page yields `ABSTAINED` with `url_content_insufficient`, no
   GFC/Tavily/final evaluator calls, and no saved AI verdict.
3. Material negation, allegation, quote attribution, location, planning
   modality, and dates survive the preprocessing text unchanged.
4. Source records and evaluator input remain untouched by display-source
   projection from the previous phase; no new migrations.
5. Existing URL, TEXT, and Cloudflare pilot offline regressions pass.
6. A separate manual review of representative real HTML/Markdown
   extraction cases is still necessary before accepting model-level
   extraction fidelity or merging any branch.

**State when authored:** committed on GitHub, local automated test run pending.
