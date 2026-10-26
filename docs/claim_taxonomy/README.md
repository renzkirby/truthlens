# TruthLens claim taxonomy and Community topics — v1

**Status:** Phase 1 taxonomy rubric plus Phase 2 Community integration. The
subject definitions and synthetic examples remain a design artifact, not an
independently adjudicated benchmark. This branch does not authorize AI
suggestions for partner eligibility and does not change live classifier or
partner-routing authority.

## Goals

Keep public browsing simple without weakening institutional verification rules.
TruthLens retains the existing **12 investigation subjects** and groups them into
**eight public news categories** for the Community feed. **Campus Affairs**
remains a separate planned context dimension, not a thirteenth subject, and is
intentionally withheld from the live Topic control until the reviewed
campus-routing policy is implemented.

The subject rubric and public group mapping live in
`api/verification/subject_taxonomy.py`. The Community API currently projects a
public topic only for authoritative **single-domain** classifications. It does
not guess a primary subject for multi-domain rows.

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

The current Community Topic dropdown exposes **All Topics** plus these eight
groups. **Campus Affairs is not exposed yet.** Unclassified claims and
multi-domain claims without an explicit persisted primary subject remain
discoverable under **All Topics** and must not be assigned a guessed topic.

## Subject classification guidelines

1. Classify the **specific persisted factual proposition**, not the surrounding
   article's every mention or the identity of its publisher.
2. Do **not** infer truthfulness or source reliability from the subject.
3. Select one **explicit primary subject** for future public display when a
   reliable classification is available. The *current* authoritative database
   record holds only an **unordered-by-importance list of required domains**,
   so never derive a primary subject using `domains[0]` or sorting. The
   Community feed may project a public topic from a **single-domain**
   authoritative row because no primary-subject inference is required; a
   multi-domain row remains unresolved until primary-subject persistence exists.
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

The institution-affiliation foundation represents a student publication as
organization type `NEWS` with subtype `STUDENT_PUBLICATION`. A platform-reviewed
`OrganizationInstitutionAffiliation` links it to one canonical `Institution`
with `INSTITUTION_WIDE` coverage.

Claim institution identity is represented separately through
`ClaimInstitutionAssociation`. A claim may have multiple canonical
institutions, but institution associations are permitted only while its
authoritative campus context is `CONFIRMED`. `CONFIRMED` may still have zero
institution associations when campus relevance is clear but the exact
institution is not yet established. `NOT_APPLICABLE`, `UNCERTAIN`, and
unassessed campus context must have no institution associations.

These identity contracts still do not affect partner intake: existing partner
status, capability and all-required-domain checks remain in force until a
separate routing policy is reviewed and merged. Conflict-of-interest review
remains a separate future policy.

## Current Community controls

**Desktop:** Topic · Review · Sort · Filters.

- **Topic:** All Topics plus the eight public news categories above.
- **Review:** All Reviews, Human Review, AI Analysis. Human means attributable
  human adjudication; AI means an actual AI assessment without such an
  authoritative human verdict.
- **Sort:** Latest, Oldest.
- **Filters:** content format (All formats, Text, Images, Videos, Files, Links).
  Clear Filters resets Topic, Review and Content Format while preserving Sort.
- **Mobile:** Topic remains visible and Review, Sort and Content Format are
  grouped under a combined Sort & Filter control.

Filtering happens **on the server before pagination**. Topic query parameters
are preserved in cursor links. The API rejects unsupported topic codes such as
`CAMPUS_AFFAIRS` until campus-context persistence is implemented.

## Fixture and approval limitations

`examples_v1.json` is a collection of **synthetic, proposed classification
expectations** for design review. Its labels are not ground truth, and passing
its unit tests does **not** measure real classifier accuracy, partner eligibility
quality or user experience. Independently adjudicated representative tests,
especially Philippine and campus claims, are needed before an `enforce` rollout.

## Current implementation scope / non-goals

Included in this branch:

- Phase 1 offline taxonomy rubric, public category mapping, Campus Affairs
  boundaries, synthetic fixtures and structural tests.
- Phase 2 Community API projection/filtering for authoritative single-domain
  classifications.
- Phase 2 Community Topic / Review / Sort / Content Format controls.
- AI Analysis filtering that requires an actual AI verdict rather than merely
  the absence of human review.

Persistence added in the follow-up taxonomy contract:

- `ClaimInvestigationClassification.primary_subject` stores an explicit primary
  subject when one has been authoritatively selected; it must also be present
  in `domains`.
- `ClaimInvestigationClassification.campus_context_state` stores
  `CONFIRMED`, `NOT_APPLICABLE`, or `UNCERTAIN`; null means not assessed.
- Existing rows are not guessed or backfilled.
- Community public-topic projection may use an explicit primary subject while
  preserving the legacy single-domain fallback.

Still excluded:

- changes to `api/investigation_classifier.py` or live provider prompts;
- changes to `api/verification_domain_policy.py`, `api/services.py`, or
  `api/tasks.py`;
- partner-routing or authorization changes;
- Campus Affairs filtering before the reviewed campus-routing policy is
  implemented;
- any claim that the synthetic fixture measures real classifier accuracy.
