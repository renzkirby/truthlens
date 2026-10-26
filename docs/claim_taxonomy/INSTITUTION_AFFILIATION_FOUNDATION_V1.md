# Institution affiliation foundation v1

## Purpose

This contract establishes the identity data needed for future campus-specific
verification routing. It does **not** authorize or route claims by itself.

## Canonical institution identity

`Institution` is a platform-managed canonical identity for a university,
college, campus, or other institution unit that TruthLens must distinguish for
campus-specific verification. An institution does not need to be registered as
a TruthLens partner organization.

## Student publication identity

A student publication remains a News Organization:

- `organization_type = NEWS`
- `organization_subtype = STUDENT_PUBLICATION`

The subtype is platform-managed. It is not an organization-self-declared
verification permission.

## Verified affiliation

`OrganizationInstitutionAffiliation` links one student publication to one
canonical institution. The first supported coverage scope is
`INSTITUTION_WIDE`.

Affiliation review states are:

- `PENDING`
- `VERIFIED`
- `REJECTED`

A reviewed decision records the platform reviewer, review time, and rationale.
Institution creation and affiliation changes are recorded in the accountability
log.

## Meaning of INSTITUTION_WIDE

The reviewed routing contract now allows a verified Student Publication to
verify claims specifically **about its affiliated institution** regardless of
the claim's subject category (for example Health, Sports, Elections, Education,
or Technology) when taxonomy routing is in `enforce` mode.

This does not mean that every claim which merely affects students or is posted
by a member of the institution becomes institution-specific.

Examples:

- "Example University clinic suspended vaccinations." -> potentially
  institution-specific.
- "Example University student election moves to Friday." -> potentially
  institution-specific.
- "Walang pasok sa Bacoor sa October 30, 2026." -> city-wide, not automatically
  institution-specific merely because a university in Bacoor is affected.
- A national health claim reposted by a university student -> not automatically
  institution-specific.

## Relationship to later routing

This file documents the affiliation persistence foundation. Claim institution
identity was added separately, and the reviewed routing policy now compares the
two canonical identities when taxonomy routing is in `enforce` mode.

The routing phase still does not:

- change the investigation classifier or provider prompts;
- change `services.py` or `tasks.py`;
- infer institutions from text, logos, authors, or source domains;
- enable the Campus Affairs Community filter.

See `STUDENT_PUBLICATION_INSTITUTION_ROUTING_V1.md` for the active routing
contract.
