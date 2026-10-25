# TruthLens claim subjects and Campus Affairs — v1 draft

**Status:** proposal and offline test fixtures, **not** a production rollout or an
independently adjudicated benchmark. This document does not authorize use of AI
suggestions for partner eligibility.

## Goals

Keep public browsing simple without weakening institutional verification rules.
The already deployed classification vocabulary has **12 investigation subjects**;
this proposal groups them into **eight public news categories** and offers a
**ninth visible browsing choice, Campus Affairs**. The ninth option is a filter
for separate campus relevance, **not a thirteenth subject**. The draft rubric and
public group mapping live in `api/verification/subject_taxonomy.py`.

### Public category mapping

| Public category | Existing investigation subject codes |
| --- | --- |
| Politics, Governance & Law | `CIVICS`, `ELECTIONS`, `LAW` |
| Business & Economy | `ECONOMY` |
| Health & Medicine | `HEALTH` |
| Science & Technology | `SCIENCE`, `TECHNOLOGY` |
| Education | `EDUCATION` |
| Environment & Public Safety | `ENVIRONMENT`, `DISASTERS` |
| Sports | `SPORTS` |
| Culture & Entertainment | `CULTURE` |

**Campus Affairs** is separately discoverable in the Topic dropdown. Readers
can select **Campus Affairs** across subjects, or choose **Education + Campus
only** in Additional Filters. Unclassified claims must remain discoverable in
**All Topics**; a guessed topic must not be displayed as authoritative.

## Subject classification guidelines

1. Classify the **specific persisted factual proposition**, not the surrounding
   article's every mention or the identity of its publisher.
2. Do **not** infer truthfulness or source reliability from the subject.
3. Select one **explicit primary subject** for future public display when a
   reliable classification is available. The *current* authoritative database
   record holds only an **unordered-by-importance list of required domains**,
   so never derive a primary subject using `domains[0]` or sorting. The helper
   in this patch maps only an *explicitly supplied* primary subject.
4. Add another **required** domain only if verifying the material proposition
   genuinely needs that specialist expertise. Incidental mentions do not
   impose extra partner permissions. For now the existing backend still checks
   **all authoritative required domains**. No change to that rule is proposed
   in this patch.
5. When the proposition or subject is too vague, abstain. Do not present a
   suggested label as authoritative merely because it satisfies a JSON/quote
   structure check.
6. The draft definitions, positive cases and exclusions in
   `subject_taxonomy.py` are for review. They must be evaluated against
   independently reviewed cases before being inserted into live AI prompts.

### Primary subject versus required expertise

A multi-domain claim still has **one explicit primary subject** for the public
category, while `required_subjects` records the specialist coverage needed for
partner verification. Do not expose one public category per required subject.

Example:

- Claim: “Election officials investigated AI-generated campaign advertisements.”
- Primary subject: `ELECTIONS`
- Public category: **Politics, Governance & Law**
- Required expertise: `ELECTIONS` + `TECHNOLOGY`
- Campus Affairs: `NOT_APPLICABLE`

The primary subject is not a shortcut around authorization: the existing
all-required-domain partner check remains unchanged until a separate reviewed
policy says otherwise.

### Boundary cases to review

- **Student council election date** → `ELECTIONS`, not automatically `EDUCATION`.
- **Student-government funding rule** → `CIVICS` when the proposition is about formal student governance; ordinary university administration does not automatically become `CIVICS`.
- **Tuition change at a university** → `EDUCATION`, not automatically `ECONOMY`.
- **Sports scholarship eligibility** → likely `EDUCATION` if the disputed fact
  concerns scholarship eligibility, rather than a competition result.
- **Scientific discovery by university researchers** → `SCIENCE`, without
  automatic Campus Affairs context.
- **Campus clinic changes vaccination rules** → `HEALTH` with Campus Affairs
  relevance, not automatically `EDUCATION`.
- **Classes cancelled because of flooding** → `EDUCATION` when the proposition
  being checked is the class-cancellation decision; a campus evacuation caused
  by the flood is instead `DISASTERS`.
- **Government policy involving school computers** → primary subject depends on
  the *actual factual proposition*, not a keyword count. Specialist
  requirements should be reviewed rather than guessed.

## Campus Affairs context

A campus-context assessment can be:

- `CONFIRMED`: The asserted proposition **directly concerns** a university,
  college, campus community, campus policy, campus institution, student
  governance, institutional service, or event affecting campus members.
- `NOT_APPLICABLE`: The source merely mentions, quotes, or is authored by a
  university/researcher, or the assertion is general and not institution-specific.
- `UNCERTAIN`: Campus relevance cannot be responsibly established from the
  submitted factual proposition. Do not assume relevance from a logo or name.

`CONFIRMED` means **campus relevance**, *not* that the factual proposition is
true. University-specific partner matching additionally needs a separate,
**verified canonical institution ID**. A text `institution_hint` in examples is
illustrative only and **must not authorize intake**.

For the first implementation, a student publication may be represented as
organization type `NEWS` with a proposed `STUDENT_PUBLICATION` subtype. Its
`Own Institution` coverage may only match an independently verified institution
association. Do not enable partner routing on tentative campus or identity
matches. Existing partner status, capability and all-required-domain checks
still apply. Conflict-of-interest review is a separate future policy.

## Public controls approved for future Community UI

**Single compact row (desktop):** Topic · Review · Sort · Additional Filters.

- **Topic:** All Topics, the eight news categories, Campus Affairs.
- **Review:** All Reviews, Human Review, AI Analysis. Human means attributable
  human adjudication; AI means an actual AI assessment without such an
  authoritative human verdict (not merely absence of a human decision).
- **Sort:** Latest, Oldest. Do not invent a relevance ranking.
- **Additional Filters:** content type and Campus Affairs only.
- **Mobile:** Topic plus a combined Sort & Filter sheet.

Filtering must happen **on the server before pagination**. Keep existing
content-type and assessment-source filters working; add new topics without
reinterpreting them as claim media formats. The database, API serializer,
client UI and rollout are **out of scope for this draft**.

## Fixture and approval limitations

`examples_v1.json` is a collection of **synthetic, proposed classification
expectations** for design review. Its labels are not ground truth, and passing
its unit tests does **not** measure real classifier accuracy, partner eligibility
quality or user experience. Independently adjudicated representative tests,
especially Philippine and campus claims, are needed before an `enforce` rollout.

## Phase 1 scope / non-goals

Included: offline draft rubric, public category mapping, Campus Affairs
boundaries, synthetic examples and structural tests that cross-check the 12
existing codes. **No live network requests.**

Excluded: changing `api/investigation_classifier.py`, provider prompts,
`api/verification_domain_policy.py`, `api/services.py`, `api/tasks.py`,
database models/migrations, community endpoints, organization eligibility or
production flags. Do not commit, push or merge without separate review.
