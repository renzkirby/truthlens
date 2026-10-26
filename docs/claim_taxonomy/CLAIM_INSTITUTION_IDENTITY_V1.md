# Claim institution identity v1

## Purpose

This contract adds authoritative canonical institution identity to claim
investigation context. It is the second half of the identity foundation needed
for future Student Publication institution-wide routing.

This phase does **not** change partner eligibility or assignment routing.

## Why claims may have multiple institutions

A factual proposition can concern one institution, several institutions, or no
specific institution even when Campus Affairs relevance is confirmed.

Examples:

- "Example University clinic suspended vaccinations."
  - Campus: `CONFIRMED`
  - Institutions: Example University
- "Example University and Second University suspended classes."
  - Campus: `CONFIRMED`
  - Institutions: Example University + Second University
- "Several universities will move classes online next week."
  - Campus: `CONFIRMED`
  - Institutions: none until specific canonical identities are established
- "Walang pasok sa Bacoor sa October 30, 2026."
  - Campus: `NOT_APPLICABLE`
  - Institutions: none

A broader geographic claim does not become institution-specific merely because a
university is located in the affected area.

## Persistence

`ClaimInstitutionAssociation` links an authoritative
`ClaimInvestigationClassification` to a canonical `Institution`.

Each association stores:

- canonical institution
- association rationale
- platform actor that assigned the institution
- assignment timestamp
- update timestamp

The pair `(classification, institution)` is unique.

Institution associations are deleted automatically when the authoritative
classification is deleted.

## Campus-context review metadata

`ClaimInvestigationClassification` also stores platform-specific review
metadata:

- `campus_context_rationale`
- `campus_context_reviewed_by`
- `campus_context_reviewed_at`

These fields are separate from the subject-classification `rationale` and
`classified_by` fields so a later campus review does not rewrite attribution
for the subject classification.

Existing rows are not backfilled. Legacy non-null campus states may therefore
have null review metadata until explicitly reviewed through this contract.

## State rules

The Management write operation replaces Campus state and institution identity
atomically.

### CONFIRMED

`CONFIRMED` may have zero or more active canonical institutions.

Zero institutions means campus relevance is authoritative but the exact
institution identity has not yet been established.

### NOT_APPLICABLE

Must have zero institution associations.

### UNCERTAIN

Must have zero institution associations.

### Unassessed / null

Must have zero institution associations and clears platform campus-review
metadata.

## Management authority

Only Platform Management Admin authority may update this context through:

`PUT /management/claims/<claim_id>/institution-context/`

The same endpoint supports read-only inspection with `GET`.

A non-null campus state requires a campus-context rationale. Each institution
association also requires its own rationale.

The write is an atomic replace operation. Institutions omitted from the new
payload are removed.

## Accountability

Every effective change records:

`CLAIM_INSTITUTION_CONTEXT_UPDATED`

under Platform Governance with the Claim as the audited resource.

No event is emitted for an exact no-op replacement.

## Deliberate non-goals

This phase does not:

- change `eligibility_reason()`;
- bypass `verification_specializations`;
- change verification assignment creation or intake;
- compare claim institutions to Student Publication affiliations;
- change `investigation_classifier.py`;
- change prompts or provider calls;
- change `services.py` or `tasks.py`;
- infer institutions automatically from source URLs, logos, names, authors, or
  article text;
- enable the Campus Affairs Community filter.

## Routing contract

TruthLens can represent both sides of the institution-wide eligibility match:

```text
Claim
  Campus = CONFIRMED
  Institution = University X
            ⇅
Student Publication
  Verified affiliation = University X
  Coverage = INSTITUTION_WIDE
```

The reviewed routing contract now uses that exact verified match, behind the
existing taxonomy `enforce` gate, as the Student Publication authorization
path instead of subject specializations. See
`STUDENT_PUBLICATION_INSTITUTION_ROUTING_V1.md`.
