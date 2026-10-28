# Student Publication institution-wide routing v1

## Purpose

This contract activates the reviewed `INSTITUTION_WIDE` routing rule for
verified Student Publications.

It connects the two persisted identity foundations already in TruthLens:

```text
Claim
  campus_context_state = CONFIRMED
  canonical institution = University X
            ⇅
Student Publication
  verified affiliation = University X
  coverage = INSTITUTION_WIDE
```

This is a deterministic backend authorization policy. It does not ask an AI
model to decide which organization may accept a claim.

## Ordinary partner authorization

Organizations that are not Student Publications keep the existing subject
specialization rule:

```text
all authoritative claim domains
        ⊆
organization verification_specializations
        ↓
eligible
```

Geographic fields and historical verification-scope approvals remain
non-authoritative.

## Student Publication authorization

A Student Publication uses verified institutional scope as its primary intake
authorization. Subject specializations do not expand a Student Publication
beyond its affiliated institution.

The institution-wide path requires all of the following:

- organization subtype is `STUDENT_PUBLICATION`;
- organization type is `NEWS`;
- affiliation verification status is `VERIFIED`;
- affiliation coverage scope is `INSTITUTION_WIDE`;
- affiliated canonical institution is active;
- claim has an authoritative subject classification;
- claim campus context is `CONFIRMED`;
- at least one canonical claim institution is persisted;
- the publication's affiliated institution appears in the claim institution
  associations.

When all conditions match, the Student Publication is eligible regardless of
the claim's subject category.

Examples include institution-specific Health, Sports, Elections, Education,
Technology, Governance, Science, or other supported subjects.

## What does not qualify

### Broader geographic event

> Walang pasok sa Bacoor sa October 30, 2026.

This remains outside institution-wide Student Publication scope when the
proposition is Bacoor-wide rather than specifically about the affiliated
university.

### Generic national claim

> DOH changed the national vaccination schedule.

A university student or student publication reposting the claim does not make
it institution-specific.

### Different university

A publication affiliated with University X cannot use `INSTITUTION_WIDE`
authority for a claim whose canonical institution identity contains only
University Y.

### Missing exact institution identity

`campus_context_state = CONFIRMED` with no canonical institution associations
is not enough to authorize a Student Publication. It remains unresolved for
institution routing.

## Multiple institutions

A claim may contain several canonical institutions.

For example:

> University X and University Y suspended classes.

A verified Student Publication affiliated with either University X or
University Y may satisfy the institution-wide scope test.

The existing assignment model is unchanged: one AVAILABLE assignment can still
be accepted by only one organization. This phase does not create parallel
organization-specific assignments.

## Refusal reasons

The organization-aware policy returns stable reasons:

- `NEEDS_CLASSIFICATION` — no authoritative subject classification;
- `NEEDS_INSTITUTION_IDENTITY` — Student Publication routing still lacks
  confirmed usable institution identity;
- `INSTITUTION_AFFILIATION_NOT_VERIFIED` — the Student Publication does not
  have a valid verified active institution-wide affiliation;
- `OUTSIDE_INSTITUTION_SCOPE` — the claim is not about the publication's
  verified institution;
- `OUTSIDE_SPECIALIZATIONS` — an ordinary partner lacks one or more required
  subject specializations.

## Enforcement surfaces

The same organization-aware policy is used for:

1. verification intake visibility; and
2. direct assignment claiming.

This prevents clients from bypassing intake filtering by manually submitting a
known assignment ID.

The direct claiming transaction locks the authoritative classification while
evaluating scope so a concurrent platform campus-context update cannot race the
authorization decision.

## Rollout gate

Partner-routing authorization is controlled independently from automatic subject
classification:

- `INVESTIGATION_ROUTING_MODE=off` — preserve pre-routing intake behavior;
- `INVESTIGATION_ROUTING_MODE=enforce` — organization-aware
  subject/institution routing is authoritative.

`INVESTIGATION_CLASSIFICATION_MODE` controls whether automatic subject
classification is off, shadow-only, or persisted authoritatively; it no longer
implicitly turns partner routing on.

## Deliberate non-goals

This phase does not:

- change the investigation classifier;
- change AI prompts or provider calls;
- change `services.py` or `tasks.py`;
- infer institution identity automatically;
- create or rewrite claim classifications;
- create multiple verification assignments;
- change organization membership or capabilities;
- change factual verdict reasoning.

The Campus Affairs Community filter is implemented separately as a public
browsing projection of confirmed campus context. It does not grant or modify
partner routing authority.

## AI reasoning boundary

After this contract, the backend routing target is stable enough for the paused
AI Reasoning work to resume.

Future AI/classifier work may propose or produce the authoritative subject,
Campus context, and institution identity inputs only after its own reviewed
reliability gates. The deterministic routing policy remains responsible for
organization authorization.


## Interim Intake browsing behavior

Before institution-aware routing is enabled, Student Publication workspaces may
default the Verification Intake browsing filter to **Campus Affairs**. This is a
presentation preference only:

- Campus Affairs maps to authoritative `campus_context_state=CONFIRMED`;
- it is shown in the same flat Intake filter list as subject filters;
- the UI does not expose a separate "Context" heading;
- verifiers may switch to All classifications or any other filter;
- the filter is applied after routing eligibility and does not grant or deny
  authorization;
- `INVESTIGATION_ROUTING_MODE` remains the only switch that enables
  authoritative intake routing policy.

This interim behavior does not replace automatic campus detection, canonical
institution resolution, or institution-aware routing. Those remain separate
future rollout steps.
