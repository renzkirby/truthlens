# PARTNER-GOV-1 — Human subject-domain consensus and sign-off checkpoint

**Date:** 2026-10-22 (Asia/Manila)
**Branch:** `feat/ai-rq2-provider-hierarchy`
**Status:** **32 aligned proposed references / 0 formally APPROVED**. Source
reviews and follow-up answers were supplied conversationally and in two
private Excel workbooks. Neither reviewer has been identified or
independently attested in the repository.

## What was reported

Reviewer 1 supplied a completed 32-case blind review and an 11-case
reconciliation workbook. Reviewer 2 (co-developer) independently provided
a list of entries and follow-up corrections. Both reportedly **agreed
`cross_school_sport = CLASSIFY: [EDUCATION]`**, superseding the
second reviewer's initial `EDUCATION + SPORT` proposal. The disputed
claim is **an education board approving a scholarship program for students**;
a sports-specific claim is not independently established by the words
“sports scholarship” alone.

Reviewer 2's follow-ups clarified four other cases:

| Case ID | Reviewer 2 clarification |
|---|---|
| `disasters_evacuation` | Correct domain **DISASTERS**, not initial SPORTS |
| `health_vaccine` | **HEALTH** |
| `environment_water` | **ENVIRONMENT**; original list omitted this case; CLASSIFY inferred |
| `sports_match` | **SPORTS**; original list omitted this case; CLASSIFY inferred |

The locally maintained comparison workbook records **27 directly aligned
or explicitly clarified cases** and **5 provisionally aligned cases**.
All 32 have a proposed reference. **Agreement is not the same as audit
approval or empirical classifier accuracy.**

## Five pending normalization confirmations (all should be confirmed by Reviewer 2)

| Canonical case | Original second-review entry | Proposed interpretation requiring confirmation |
|---|---|---|
| `elections_ballot` | `election_ballot: CLASSIFY, ELECTIONS` | `election_ballot` means `elections_ballot` |
| `cross_campaign_ai` | `cross_campaign: CLASSIFY, (ELECTION, TECHNOLOGY)` | `cross_campaign` means `cross_campaign_ai`; `ELECTION` means `ELECTIONS` |
| `cross_school_environment` | `cross_school_environment: (EDUCATION, ENVIRONMENT)` | Omitted decision means `CLASSIFY` |
| `geography_not_scope` | `geography_not_scope: CLASSIFY, TECHONOLOGY` | `TECHONOLOGY` means `TECHNOLOGY` |
| `out_of_scope_none` | `out_of_scope: ABSTAIN` | `out_of_scope` means `out_of_scope_none` |

These are plausible typos/abbreviations, but **not independently confirmed
from reviewer 2**. Preserve the original entries and their mapping
rather than silently reinterpreting a source record.

## Proposed sign-off sequence

1. Reviewer 2 explicitly confirms or corrects **all five proposed
   interpretations** using the table above. A single written response
   naming all five is sufficient; record any correction.
2. Reviewers 1 and 2 each explicitly confirm that the final 32
   canonical classifications represent their reviewed consensus.
   Record their chosen reviewer identifiers, review date and
   agreement reference (e.g. tracked review message, private signed
   workbook). **Never invent reviewer identities or confirmations**.
3. Record the exact version of the canonical synthetic claim texts and
   the source decisions, corrections and any unreconciled disputes.
   `cross_school_sport` now has the agreed **EDUCATION-only draft
   reference**, but **`review.status` remains `PENDING`** until
   explicit acceptance.
4. After real sign-off, prepare a **separate reviewed corpus copy**
   matching the existing audit schema with `review.status="APPROVED"`,
   the real reviewer identifier/provenance, and meaningful notes
   (max 2,000 characters). Keep originals and source-review evidence.
   Do not use assistant-generated statements as proof of human review.
   Prefer a private local corpus for evaluation and do not inadvertently
   publish personal reviewer information in GitHub.
5. Run `python manage.py audit_investigation_classification --corpus
   <approved-local-file>` **without `--predictions` first** to check
   count and schema. This is an offline, read-only action: it does not
   submit AI requests, write DB rows, or grant partner eligibility.
6. Only then review a bounded, separately authorized plan for capturing
   complete *real* provider responses for all cases, including
   model/prompt/config provenance and API costs. Existing shadow
   assessment records retain domain codes but lack full quoted
   response text, so they are insufficient for this score. Scoring
   must follow the tool's strict quotation contract and report
   potential scope leaks/exclusions. **Do not enable `enforce`**.

### Minimal reviewer-2 confirmation script

> I confirm the following mappings for my prior review:
> `election_ballot=elections_ballot`;
> `cross_campaign=cross_campaign_ai` and `ELECTION=ELECTIONS`;
> `cross_school_environment=CLASSIFY [EDUCATION, ENVIRONMENT]`;
> `TECHONOLOGY=TECHNOLOGY` for `geography_not_scope`;
> `out_of_scope=out_of_scope_none`.
> I also confirm our shared final decision for
> `cross_school_sport=CLASSIFY [EDUCATION]`.
> **My reviewer identifier:** ________.
> **I approve the final set of 32 subject-domain reference labels:** yes/no.
> **Review date:** ________.

This is a **template, not a review response**. Reviewer 1 must also
confirm final labels under the same sign-off protocol.

## Current branch contents and preserved invariants

- `api/verification/fixtures/investigation_subject_review_v1.json`
  still contains **32 PENDING / 0 APPROVED** cases. Only the *draft*
  domains of `cross_school_sport` changed from
  `[EDUCATION, SPORTS]` to `[EDUCATION]`, reflecting reported joint
  human consensus. The `cross_domain` tag is retained deliberately
  because the claim tests a plausible secondary-domain temptation,
  not because two domains must be assigned.
- No new model/field/migration, no runtime classifier change,
  no provider calls or DB writes, no organization permission changes.
- Strict JSON/quoted evidence checks, runtime contract parity,
  real-world accuracy measurement, and development-only provider
  reliability remain separate acceptance gates.
- `INVESTIGATION_CLASSIFICATION_MODE` defaults to `off`.
  `shadow` is nonauthoritative; `enforce` has not been approved.

## Source references

- Internal private workbooks: `Blind Review.xlsx`,
  `Final Review.xlsx`,
  `PARTNER_GOV1_Two_Reviewer_Reconciliation_CONSENSUS_PENDING.xlsx`.
  These are **not** in GitHub and require explicit private sharing
  with the team where needed.
- `docs/PARTNER_GOV_1_CLASSIFICATION_ACCURACY_ACCEPTANCE.md`
- `docs/PARTNER_GOV_1_SUBJECT_DOMAIN_REVIEW_WORKSHEET.md`
- GitHub issue **#128** is the project-level classification checkpoint.
