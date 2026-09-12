# TruthLens Design Standard

This document is the durable UI/UX design standard for TruthLens.

It is influenced by the quality methodology of Impeccable, but it does **not** ask TruthLens to imitate Impeccable's demos, visual taste, or any other product. TruthLens product truth, existing brand identity, approved behavior, and user needs take precedence.

Use this document for design, redesign, critique, audit, layout, hardening, responsive adaptation, and polish work across the web application and public site.

---

## 1. Design Thesis

TruthLens should feel:

- credible without feeling bureaucratic
- calm without feeling passive
- modern without chasing trends
- evidence-oriented without becoming visually technical for its own sake
- institutional enough to support accountable verification
- approachable enough for ordinary community users
- restrained enough that claims, evidence, sources, and human decisions remain visually primary

The interface should help users answer three questions quickly:

1. Where am I?
2. What matters most here?
3. What can I safely do next?

Visual novelty must never make those questions harder to answer.

---

## 2. Product Truth Overrides Visual Novelty

The interface must preserve TruthLens domain boundaries.

Never use design, labels, badges, or visual emphasis to imply authority that the backend/domain model does not grant.

Examples:

- Trust score does not equal institutional authority.
- Public partner presence does not equal institutional fact-check attribution.
- Partner presence does not equal publication authority.
- A partner logo does not imply endorsement of all TruthLens content.
- Platform moderation is not the same as factual verification.
- AI assistance does not replace accountable human judgment.

When UI polish and product truth conflict, product truth wins.

### Authority and provenance hierarchy

TruthLens must communicate not only where information came from, but also what review occurred and which actor or institution is accountable for the result.

The UI must visually and verbally distinguish:

- AI-generated analysis
- AI-assisted evidence discovery
- community-submitted evidence
- reviewed evidence
- human adjudication
- institutional publication

These concepts may participate in one workflow, but they must not share visual language in a way that falsely implies equal authority. Labels, hierarchy, status treatment, and provenance must preserve this relationship:

`AI-assisted result != human adjudication != institutional publication`

AI may assist with analysis and evidence discovery. A human remains accountable for adjudication, and institutional publication authority comes only from the authorized partner organization and publication workflow. Neither a person's trust score nor the mere presence of a partner supplies that authority.

---

## 3. Refinement vs. Redesign

### Refinement

Refinement preserves:

- TruthLens identity
- product semantics
- factual copy unless correction is approved
- route purpose
- workflow meaning
- existing successful interaction patterns
- established tokens and visual conventions when they are still sound

Refinement may improve:

- hierarchy
- spacing
- rhythm
- alignment
- typography
- responsive behavior
- accessibility
- state design
- component reuse
- visual consistency
- micro-interactions
- perceived quality

### Redesign

A redesign may replace the incumbent visual system or interaction model, but only when the task explicitly authorizes it.

Do not smuggle a redesign into a "polish" or "cleanup" task.

---

## 4. Surface Modes

TruthLens contains different kinds of surfaces. The mode of the surface determines how expressive the design may be.

### Public / persuasive surfaces

Examples:

- Landing page
- Public partner directory
- Public partner profile
- Future public About, Privacy, Terms, Contact pages

Goals:

- establish trust
- explain clearly
- help users discover the product or public information
- provide confident but restrained calls to action

These pages may be more expressive than application screens, but they should still feel evidence-aware and credible rather than campaign-like or decorative.

### Operational surfaces

Examples:

- Community application shell
- Verification workspace
- Organization administration
- Settings
- User Hub
- Deep Analysis tools

Goals:

- make tasks obvious
- make status legible
- reduce cognitive load
- preserve stable navigation and density
- prioritize accuracy over visual spectacle

Brand expression here should come through precise details, not large decorative treatments.

### Reading / evidence surfaces

Examples:

- Thread detail
- Claim analysis
- Evidence review
- Published fact-check reading experiences

Goals:

- comprehension
- source legibility
- claim/evidence hierarchy
- readable measures
- clear provenance

Long-form reading should never be squeezed into dashboard-style card density.

---

## 5. One TruthLens, Two Shells

TruthLens intentionally has two primary navigation contexts.

### Public Site Shell

Used for anonymous or public informational pages.

Representative destinations:

- Landing
- Partners
- Partner profiles
- future public informational/legal pages

The public shell should share:

- the same TruthLens brand presentation
- the same navigation height and container rhythm
- the same public CTA language
- the same mobile menu behavior
- the same focus treatment
- the same public color vocabulary

A feature should not invent its own public navbar.

### Authenticated Application Shell

Used for logged-in product work.

Representative destinations:

- Community
- Verify
- Workspace
- Dashboard/User Hub
- Profile
- Settings

This shell may include product-specific search, notifications, account controls, and capability-aware navigation.

Do not reuse the authenticated application navbar unchanged on anonymous public pages simply for visual consistency. Consistency comes from a coherent design system, not from forcing one navigation model into every context.

Specialized layouts belong within these broader product contexts; they are not additional product identities:

- Public Site Shell
- Authenticated Application Shell
  - Workspace operational layout

Authentication may use a specialized, task-focused layout while preserving the TruthLens identity and a clear relationship to the public entry and authenticated destination. Verification Workspace may use a more spatially efficient operational layout inside the authenticated context. Do not turn these variations into four unrelated visual applications.

---

## 6. Current Brand Foundation

The existing design system already establishes important TruthLens primitives.

### Canonical token direction

New design-system work should use canonical, TruthLens-namespaced tokens with the `--tl-*` prefix. Semantic names should describe durable roles rather than individual components or temporary visual values.

Representative canonical tokens include:

- `--tl-color-brand-primary`
- `--tl-color-brand-primary-hover`
- `--tl-color-brand-dark`
- `--tl-color-bg-app`
- `--tl-color-bg-surface`
- `--tl-color-text-main`
- `--tl-color-border-default`

This checkpoint establishes naming direction; it does not change underlying brand color values.

During migration, these existing variables remain temporary compatibility aliases:

- `--brand-primary`
- `--brand-primary-hover`
- `--brand-dark`
- `--bg-app`
- `--bg-surface`
- `--bg-subtle`
- `--text-main`
- `--text-body`
- `--text-muted`
- `--text-inverse`
- `--border-default`
- `--border-light`
- `--verdict-*`
- `--primary-blue`
- `--border-color`
- `--text-white`
- `--bg-dark`

Do not remove these aliases immediately. Migrate consumers deliberately as canonical tokens are introduced and mapped. Do not invent compatibility aliases for values that are not currently defined merely to make the naming families appear complete.

### Design-system migration discipline

Design-foundation work must preserve product behavior. Keep visual redesign and functional or domain changes separable whenever practical so each checkpoint has a clear scope and review boundary.

- Migrate surfaces in bounded checkpoints rather than attempting a broad visual-system rewrite.
- Keep the compatibility aliases documented above until their consumers have migrated.
- Fix genuinely shared causes at the shared layer before duplicating local fixes across surfaces.
- Do not use design-system cleanup as justification for unrelated refactors.
- Preserve established interaction, authority, and workflow semantics while foundations change.

### Color semantics

TruthLens uses color according to durable roles:

- **Trust indigo:** TruthLens brand identity, generic primary actions, selected or active navigation, ordinary interactive emphasis, links where appropriate, and the canonical focus treatment.
- **Green:** factual-positive or verified semantic states, and success or completed-positive feedback.
- **Red:** false verdicts, destructive actions, and errors.
- **Amber:** misleading verdicts, warnings, and caution.
- **Violet:** satire semantic states.
- **Neutrals:** structure, ordinary surfaces, secondary controls, and metadata.

Verdict colors are semantic and must remain consistent across fact/verified, fake/false, misleading, unverified, out-of-scope, and satire states. They must not be reused as generic decorative or action colors when doing so could confuse verdict meaning with interactivity, brand emphasis, success, warning, or authority.

### Public-site accent

The public site should use trust indigo—not verdict green—as its generic CTA, active-navigation, interactive-emphasis, and focus direction. Green remains available for verified/factual-positive meaning and success feedback.

This reconciles the previous public-green convention without changing color values in this documentation checkpoint. The goal remains a restrained palette in which primary actions, focus, trust cues, and factual semantics are unmistakably distinct.

---

## 7. Color Rules

- Use semantic tokens first.
- Do not introduce random hex colors into component files when an existing token expresses the role.
- If a new reusable role genuinely requires a token, add one deliberately rather than duplicating one-off values.
- Do not use verdict colors decoratively when users could interpret them as claim status.
- Maintain sufficient contrast in every state, including muted text, disabled controls, colored surfaces, and focus rings.
- Avoid decorative gradients unless a specific approved visual direction calls for them.
- Avoid decorative glass/blur effects. Blur is acceptable when it serves a real layered navigation or focus context, such as the established sticky public navbar.

---

## 8. Typography

TruthLens typography should prioritize clarity and hierarchy.

### Hierarchy

Each page should have one obvious primary heading.

Use clear scale and weight differences between:

- page title
- section title
- body copy
- labels
- metadata

Do not create hierarchy by making everything bold.

### Reading measure

Long-form descriptive or evidence text should stay within a comfortable reading width. Avoid very wide paragraph lines simply because the viewport allows them.

### Wrapping

Always test:

- long organization names
- long usernames
- long URLs
- long expertise labels
- verbose error messages
- localized/expanded copy

Text should wrap naturally without causing page overflow.

### Font policy

Do not change the product font as a side effect of unrelated UI work.

A typography redesign requires explicit approval and must consider performance, accessibility, existing layout metrics, and brand continuity.

---

## 9. Layout and Spatial Rhythm

Layout turns product priority into reading order.

Before changing structure, identify:

- the primary task or reading path
- the main information group
- secondary/supporting information
- which elements belong tightly together
- which sections require stronger separation

### Rules

- Use proximity before adding containers.
- Use `gap` for sibling relationships when appropriate.
- Prefer a small, documented spacing scale over repeated one-off values.
- Related items should be tighter than unrelated sections.
- Give major headings more space above than below.
- Do not repeat one spacing value everywhere until the page loses rhythm.
- Use whitespace to create hierarchy, not emptiness.
- Do not create giant hero blocks on utility or directory pages unless the content genuinely warrants them.

### Containers

Connected public pages should use compatible maximum widths and page gutters so navigation and content feel part of one site.

Operational app pages may use different density, but shared app-shell regions should align consistently.

### Information density

Consistency does not require every TruthLens surface to use identical spacing. Density must follow task type while typography, tokens, interaction patterns, and spacing relationships remain coherent.

TruthLens supports three broad density levels:

#### Comfortable

Typical surfaces:

- landing
- public partner pages
- authentication

Use generous reading rhythm and clear narrative separation where comprehension, orientation, and trust-building matter more than simultaneous controls or data.

#### Standard

Typical surfaces:

- community
- dashboard
- verify
- settings
- profiles

Balance scanability, content comprehension, and routine interaction without creating either marketing-page expansiveness or workbench compression.

#### Compact / operational

Typical surfaces:

- Verification Workspace
- queues
- filters
- evidence review
- adjudication
- drafting
- publishing

Use tighter, intentional spacing to keep related evidence, controls, and workflow status in view. Compact does not mean cramped: legibility, touch targets, focus visibility, and clear grouping remain mandatory.

---

## 10. Cards and Containers

Cards are not the default solution for grouping.

Use a card when it represents a meaningful bounded object or interaction, such as:

- a partner result
- a claim
- a thread
- a membership record
- a discrete status object

Do not:

- wrap every section in a card
- nest cards inside cards without a strong information-model reason
- use rounded rectangles merely to make empty space feel designed
- add decorative borders to compensate for weak spacing/grouping

Prefer semantic sections, lists, dividers, and proximity when content is not truly a bounded object.

### Component architecture

Use the smallest component boundary that preserves meaning, reuse, and maintainability.

- **Reusable primitive:** a low-level control or visual role with stable semantics across surfaces, such as a button, form control, status treatment, or layout primitive.
- **Reusable composite:** a recurring arrangement of primitives that represents the same product object or task pattern in multiple places.
- **Page-specific composition:** the assembly of primitives and composites for one route or workflow; keep it local when its structure is unique to that surface.

The role inventories below are architectural targets, not claims that the components already exist. Introduce them only when a bounded implementation checkpoint actually needs them. When a role is shared, surfaces should converge on the same semantic contract rather than create parallel local versions.

#### Generic design-system roles

- `Button`
- `IconButton`
- `Input`
- `Select`
- `Textarea`
- `Checkbox`
- `Badge`
- `Divider`
- `Tooltip`
- `StatusMessage`
- `EmptyState`
- `Dialog`
- `Drawer`
- `Tabs`
- `DataTable`
- `FilterBar`
- `MetadataList`

#### TruthLens domain roles

- `VerdictBadge`
- `ClaimSummary`
- `EvidenceRecord`
- `AuthorityBadge`
- `ProvenanceSummary`
- `OrganizationIdentity`
- `TrustIndicator`
- `RevisionTimeline`
- `CorrectionNotice`

Other concepts may exist elsewhere in future architecture when justified, but they are not replacements for this approved domain-role contract.

These domain roles must preserve TruthLens meaning:

- `TrustIndicator != AuthorityBadge`.
- `OrganizationIdentity != personal trust or reputation`.
- `VerdictBadge` must communicate the verdict using meaningful text and/or iconography in addition to semantic color. Color alone is insufficient.
- `AuthorityBadge` must preserve the distinction between AI assistance, human adjudication, and institutional publication. It must not visually represent those as equivalent forms of authority.
- `ProvenanceSummary` must communicate source, review, and accountability context without granting authority that the underlying domain model does not grant.
- `CorrectionNotice` and `RevisionTimeline` must preserve the distinction between editorial revision and factual correction established later in this document.

Do not invent one universal component intended to serve every route, shell, density, and state. Shared foundations should enable coherent composition without erasing meaningful surface differences.

Extract a shared primitive or composite when the same semantic role or interaction pattern genuinely recurs, or when accessibility and behavioral consistency require one authoritative implementation. Do not extract solely because markup looks similar, and do not build speculative abstractions for reuse that has not materialized.

Prefer composition over prop-heavy abstractions. If a component requires many mode flags, unrelated optional regions, or route-specific branches, its boundary is probably hiding distinct concepts. Split by stable responsibility rather than expanding one component to serve every possible context.

Preserve semantic HTML, accessible names, keyboard behavior, and TruthLens domain terminology through component boundaries. A shared component must not flatten meaningful distinctions such as AI assistance, human adjudication, institutional publication, platform moderation, or factual verification.

Local styles are appropriate for truly unique surface needs when they use canonical tokens and do not reimplement a shared role. New one-off colors, controls, spacing systems, status treatments, or interaction patterns are architectural debt unless a specific surface requirement justifies and documents the exception.

---

## 11. Navigation Continuity

Navigation is part of product identity.

Connected pages should preserve:

- brand placement
- navigation height
- container alignment
- link treatment
- CTA treatment
- breakpoint behavior
- focus behavior
- menu interaction model

Active location should be visually understandable without relying only on color.

On partner profile routes, the Partners section may remain active because the profile belongs to that public section.

Landing anchors from other public pages should route back to the relevant landing section rather than becoming dead or context-dependent links.

---

## 12. Interaction Design

Every interactive control must communicate:

- default state
- hover state where hover exists
- focus state
- active/pressed state where relevant
- disabled state
- loading/busy state where relevant
- error/recovery state where relevant

Controls should name the action they perform.

Destructive or authority-changing actions require deliberate wording and interaction.

Avoid hidden interactions that only reveal themselves on hover.

Do not rely on color alone to communicate status.

---

## 13. Motion

Motion should explain change, relationship, or hierarchy.

Appropriate uses include:

- menu opening/closing
- state transitions
- subtle hover feedback
- loading/progress communication
- spatial relationship between views

Avoid:

- animation on every section
- bounce/elastic motion for serious operational workflows
- motion whose only purpose is to make polish visible
- long transitions that delay task completion

Always support `prefers-reduced-motion`.

---

## 14. Images and Logos

- Keep image dimensions bounded to prevent layout shift.
- Provide meaningful alt text for informative images.
- Decorative images/icons should not add redundant screen-reader noise.
- Broken images must fall back cleanly.
- Organization logos are public only when the backend returns them through the public contract.
- Do not reconstruct or infer hidden logo URLs in the frontend.
- Logos are identity aids, not proof of endorsement or authority.

---

## 15. States Are Part of the Design

A surface is not finished if only the happy path is designed.

Where applicable, account for:

- initial loading
- background/refetch loading
- empty data
- filtered empty data
- recoverable request error
- unavailable/not-found state
- permission-limited state
- disabled state
- destructive confirmation
- optimistic update
- rollback failure
- success feedback
- long content
- missing optional content
- broken media
- narrow viewport
- reduced motion

Error copy should identify the problem and provide the next recovery action without leaking private system state.

---

## 16. Accessibility Quality Floor

Accessibility is part of craft.

Required baseline:

- semantic landmarks and headings
- one logical page `h1`
- keyboard-operable controls
- visible `:focus-visible` treatment
- logical tab order
- labels associated with controls
- meaningful button/link names
- no color-only status
- sufficient contrast
- accessible loading and error messaging
- reduced-motion support
- bounded dialogs with correct focus management where dialogs are appropriate
- correct menu semantics when using menu patterns
- images with useful alt behavior

Do not add ARIA roles merely to make markup sound more accessible. Prefer native semantic elements first.

---

## 17. Responsive Design

Responsive behavior is structural, not cosmetic shrinking.

Representative web checks:

- wide desktop around 1440px
- desktop/laptop around 1024px
- intermediate/tablet around 760px
- phone around 375px
- narrow phone around 320px

At smaller sizes, decide what should:

- stack
- wrap
- collapse
- reorder
- remain fixed
- become scrollable only when truly necessary

Requirements:

- no accidental horizontal page overflow
- usable touch targets
- readable controls
- coherent DOM/focus order
- bounded media
- long labels and URLs do not break layout

### Workspace responsive behavior

Verification Workspace should adapt its operational structure by viewport rather than compressing every region into narrow columns.

On large screens:

- workspace navigation may remain visible
- queue and detail may coexist
- context may dock when the active task justifies it

On medium screens:

- context should generally become an overlay or drawer
- queue and detail must remain usable without horizontal squeezing

On tablet and small screens:

- navigation may collapse
- queue, work surface, and context should become focused, sequential views where needed
- reading order, focus return, and task state must remain coherent across transitions

---

## 18. Public Partner Surface Rules

Public partner pages are a public informational experience, not an administrative experience.

They should feel connected to the TruthLens public site.

### Directory

Priorities:

1. Understand what TruthLens partners are.
2. Search/filter public organizations.
3. Scan credible organization identities.
4. Open a public partner profile.

Do not overload cards with controls or internal metadata.

### Partner profile

Priorities:

1. Organization identity.
2. Public description.
3. Expertise.
4. Official external website when provided.
5. Clear partnership-context disclaimer.

Never expose or imply:

- internal verification status
- partner administration status
- member identities/roles
- capabilities
- trust score
- publication authority
- institutional attribution for claims that have not explicitly been attributed

### Public shell continuity

Partner pages should share the same public-site header as the landing page rather than maintain a feature-specific navbar.

The shared public header should preserve the landing-page public identity while adding Partners as a first-class public destination.

Broader discoverability, footer integration, and cross-product surfacing may be handled in later discovery/polish phases.

---

## 19. Factual Conclusions, Public Reading, and Provenance

Important factual conclusions should use progressive disclosure so the current answer is immediately legible while evidence and accountability remain available.

### Progressive-disclosure levels

#### Level 1 — Answer

- verdict
- institutional authority where applicable
- current status

#### Level 2 — Why

- short rationale
- key evidence and sources
- publication or decision context

#### Level 3 — Evidence

- complete reviewed evidence
- source provenance
- adjudication and revision lineage
- correction information

#### Level 4 — Audit

- detailed event and history information
- immutable record identifiers where appropriate
- snapshots and technical provenance
- internal operational history subject to authorization

Different surfaces expose different levels according to audience, purpose, and authorization:

- Community usually prioritizes Level 1 plus selected Level 2 context.
- Public fact-check reading surfaces should expose Levels 1–3.
- Authorized Workspace operators may need Levels 1–4.

Progressive disclosure is not permission escalation. Internal, private, or organization-scoped information must not become public merely because a deeper conceptual level exists.

### Public fact-check reading hierarchy

Future published fact-check surfaces should prefer this reading order:

1. Claim
2. Verdict
3. Institutional attribution
4. Short rationale
5. Key evidence
6. Full analysis
7. Sources
8. Provenance / revision history

When the publication contract authorizes institutional attribution, prioritize the public form `Published / Verified by <Partner Organization>`. Do not use this language for mere partner presence, or invent partner endorsement or publication claims.

Human approver or publisher details may appear in deeper provenance where appropriate. Their presentation must not imply that a personal trust score grants institutional authority.

### Editorial revision vs. factual correction

An **editorial revision**:

- is communicated as an update
- leaves the adjudicated verdict unchanged
- has lower visual prominence than a factual correction
- keeps revision history available

A **factual correction**:

- is explicitly communicated as a correction
- receives high visibility near the current verdict or publication state
- makes the previous and current factual states understandable
- keeps correction and revision lineage available

In both cases, preserve distinct provenance for:

- the original human approver
- the publisher executing the publication or correction handoff
- the partner organization providing institutional publication authority

Do not collapse these identities into one generic author, verifier, or publisher label.

---

## 20. Authenticated Operational Surface Rules

Operational screens should prioritize scanability and stable task completion.

- Keep primary actions obvious but not oversized.
- Use dense layouts only where the task benefits from density.
- Preserve stable navigation between related workflows.
- Separate organization management authority from factual verification authority visually and conceptually.
- Do not use public-marketing copy inside operational workflows.
- Avoid decorative effects that compete with evidence, queues, decisions, or audit information.

### Verification Workspace workbench

The preferred desktop mental model is:

- **Queue —** What needs my attention?
- **Work surface —** What am I evaluating, deciding, drafting, or publishing?
- **Context —** What evidence, provenance, history, or organization context do I need without leaving my task?

Preferred composition:

`queue | primary work surface | optional contextual drawer/panel`

The Workspace should use available desktop viewport space more effectively than public or editorial pages. Do not impose arbitrary centered maximum-width constraints on a professional workbench when the task benefits from additional working area.

Avoid:

- cards inside cards
- unnecessary outer content cards
- excessive nested padding
- arbitrary centered max-width constraints for professional workbenches
- permanently visible context panels when the task does not need them

Use structural separators, proximity, lists, tables, toolbars, drawers, and semantic sections before introducing more cards. Context should dock only when it materially supports the current task; otherwise it should remain optional and available on demand.

---

## 21. Anti-Patterns to Challenge

These are not absolute bans in every possible future design, but they require a specific reason rather than habit:

- feature-specific public navbars
- nested cards
- giant empty heroes on task-oriented pages
- gradient text
- decorative glassmorphism
- repeated rounded icon tiles above every heading
- excessive shadows
- excessive borders
- hardcoded component colors when tokens exist
- monospace used merely to feel technical
- decorative verdict colors
- animation on every section
- hover-only discoverability
- generic dashboard grids used for non-dashboard content
- static metrics presented as meaningful product evidence
- copy that overstates partner authority or endorsement

---

## 22. UI Review Workflow

For a nontrivial UI change:

### 1. Establish the incumbent truth

Inspect:

- neighboring pages
- shared components
- global tokens
- current public/app shell
- current route/interaction behavior
- real content and states

### 2. Name the design problem

Describe the actual issue before changing code.

Examples:

- disconnected public-site continuity
- weak hierarchy
- repeated one-off controls
- poor responsive grouping
- excessive containers
- inconsistent action language

### 3. Define the smallest correct design change

Prefer fixing the cause at the shared level when the problem is truly shared.

Example:

A different navbar on every public page should be solved with a shared public-site header, not by manually matching three separate navbars.

### 4. Implement within the approved visual world

Preserve TruthLens identity unless redesign is authorized.

### 5. Verify the complete path

Check:

- desktop
- intermediate width
- mobile
- keyboard
- focus
- loading
- empty
- error
- long content
- broken media
- reduced motion

### 6. Stop polishing

Use bounded passes. Once the identified issues are resolved and the quality floor is met, stop rather than creating endless micro-churn.

---

## 23. Working With Impeccable Guidance

Impeccable is used as a methodology for stronger design reasoning and finishing quality.

Apply its ideas selectively through the TruthLens brief.

Use it to challenge:

- weak hierarchy
- monotonous spacing
- generic layouts
- incomplete states
- inaccessible interactions
- brittle responsive behavior
- disconnected journeys
- unnecessary containers
- inconsistent visual roles

Do not use it to justify:

- replacing the TruthLens identity without approval
- introducing a new font because another style guide dislikes the incumbent font
- forcing visual novelty where operational clarity is more important
- copying another product's color palette or composition
- rewriting factual product copy without approval

The standard is successful when the result feels unmistakably more intentional **and still unmistakably TruthLens**.

---

## 24. Shipping Checklist for UI Work

Before UI work is considered ready for human acceptance, the implementation should be able to answer yes to these questions:

- Does this still look and feel like TruthLens?
- Does the page's primary task/read path remain obvious when visually squinted?
- Are shared roles using shared patterns rather than local reinventions?
- Does the density match the task rather than force one spacing model everywhere?
- Are related items grouped by proximity before decoration?
- Are spacing and typography deliberate rather than uniform?
- Are all important states designed?
- Is keyboard navigation complete?
- Are focus states visible?
- Does the page work at 1440, 1024, ~760, 375, and 320px where applicable?
- Does long or missing content remain stable?
- Is motion purposeful and reduced-motion safe?
- Is there any accidental authority, endorsement, or verification implication?
- Are AI assistance, human adjudication, and institutional publication clearly distinguished?
- Are revisions and factual corrections communicated with the right prominence and provenance?
- Is new design-system work using canonical `--tl-*` tokens while migration aliases remain supported?
- Did the task remain refinement rather than silently becoming redesign?
- Did the complete user journey remain visually connected?
