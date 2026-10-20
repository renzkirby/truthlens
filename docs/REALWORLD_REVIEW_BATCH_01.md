# TruthLens real-world provider benchmark — source review batch 01

**Status: FOUR HUMAN-CONFIRMED REFERENCE LABELS (20 October 2026).**

This started as an assistant-prepared review aid for the first four claim
candidates in `api/tests/fixtures/realworld_verification_cases.json`.
After reviewing the source materials, the TruthLens project reviewer
**explicitly approved all four proposed verdicts in the project conversation
on 20 October 2026**. Those four case records are now APPROVED with a
pseudonymous reviewer identifier, sourced rationales drafted by the assistant,
and `source_checked=true` based on the reviewer confirming that the source
materials were reviewed. The human confirmation covered the four verdicts;
it did not constitute separate verbatim approval of the assistant-drafted
rationale text. No inference has yet been run for this reviewed batch and
no claim records or databases were modified.

## Source checks (20 October 2026)

### Constitutional source — both CIVICS cases
- Corpus citation: [Official Gazette — 1987 Constitution](https://officialgazette.gov.ph/constitutions/1987-constitution/)
- Accessible government cross-check:
  [Supreme Court E-Library, 1987 Constitution](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/3/353)
- Independently published institution source:
  [Philippine Senate — Composition of the Senate](https://web.senate.gov.ph/senators/composition.asp)
- Relevant provision: Article VI, Section 2 sets the chamber at **24 senators**.
- Review note: The source content also provides six-year terms in Section 4,
  but these two claims concern only the chamber's authorized composition.
  The term detail in the evidence snapshot is unnecessary and can be removed
  for a tighter claim-specific dossier.
- Link caveat: Some automated clients receive HTTP 403 when fetching the
  Official Gazette directly. A human reviewer should open it in a browser;
  the Supreme Court and Senate links are fallbacks.

### Death-penalty source — both LAW cases
- Corpus citation: [Lawphil — Republic Act No. 9346](https://lawphil.net/statutes/repacts/ra2006/ra_9346_2006.html)
- Authoritative cross-check:
  [Supreme Court E-Library — Republic Act No. 9346](https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/2/245)
- Relevant provision: Section 1 expressly prohibits the imposition of the
  death penalty. Section 2 prescribes reclusion perpetua or life imprisonment
  instead, depending on the applicable law.
- Date caveat: June 24, 2006 is the Act's **approval date**, not necessarily
  its effective date. Section 5 conditions effectiveness on publication.
  The benchmark claim does not assert that it took effect on June 24.
- Reviewer must confirm the as-of-date statutory and interpretive context.

## Human-confirmed reference decisions

| Case ID | Claim summary | Approved label | Direct textual basis |
|---|---|---|---|
| `civics__support` | 1987 Constitution sets Philippine Senate at 24 | **FACT** | Article VI, Section 2 explicitly says 24 |
| `civics__contradict` | Constitution requires 48 senators | **FAKE** | Same section explicitly sets 24, not 48 |
| `law_death_penalty_support` | RA 9346 prohibits imposing the death penalty | **FACT** | RA 9346 Section 1 expressly prohibits imposition |
| `law_death_penalty_contradict` | RA 9346 reinstated death penalty | **FAKE** | RA 9346 Section 1 expressly prohibits and amends/repeals death-penalty measures |

The reviewer confirmed all four labels after reviewing the cited sources.
The four examples are derived from just **two** primary authorities, so they
should not be treated as four independent information sources. The remaining
26 cases are PENDING, and no model accuracy score has been calculated yet.

## Reviewer checklist for additional cases

For each remaining case, an independent human reviewer should:
1. Visit the indicated primary source; verify section, text, date and claim wording.
2. Confirm the recorded evidence snapshot accurately reflects the source.
3. Determine the reference verdict independently under TruthLens's existing
   verdict rubric and record any disagreement.
4. Complete `review.status=APPROVED`, `approved_verdict`, reviewer identifier,
   review date, a substantive rationale, and `source_checked=true`; alternatively
   leave PENDING or mark REJECTED with a reason.
5. Commit reviewer decisions separately, without including sensitive identity
   or private evidence.

**Do not** bulk-approve the remaining 26 cases based on assistant proposals.
Use `docs/REALWORLD_VERIFICATION_PROVIDER_BENCHMARK.md` for the full review
protocol and opt-in scoring instructions.

## First scored Cloudflare comparison (after local regression tests)

From `backend/truthlens_backend` in development, with the previously
configured Cloudflare evaluation credentials and opt-in flags:

```powershell
..\.venv\Scripts\python.exe .\manage.py evaluate_realworld_verification_providers `
  --live --provider cloudflare `
  --case civics__support --case civics__contradict `
  --case law_death_penalty_support --case law_death_penalty_contradict `
  --limit 4
```

Only four explicitly approved claim/evidence dossier records will be sent.
The maximum is four Cloudflare inference calls, sequentially, with 2,048
completion tokens each unless explicitly overridden. This remains an
evidence-dossier benchmark, NOT full retrieval or a general accuracy study.
Four cases are drawn from two sources and lack diversity. Inspect individual
verdicts, contract validity, latency and failures before considering further
review work or provider routing changes.
