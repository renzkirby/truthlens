# Verification Workspace — Deep HCI / UI-UX Research

Status: approved research basis for WORKSPACE-UX-1 (#129)

This document extends `WORKSPACE_UX_LEARNABILITY_RESEARCH.md` after manual review of the Phase A/B Workspace and Adjudication/Evidence screens.

## Research question

How should TruthLens present a large amount of necessary professional verification information without overwhelming Partner Organization users, while preserving learnability, traceability, evidence provenance, and expert efficiency?

## 1. Task suitability before feature visibility

ISO 9241-110 states that interaction should be based on characteristics of the user's task rather than the technology used to perform it. It also links suitability for the task to avoiding unnecessary steps and unnecessary information.

TruthLens implication:
- do not treat every backend capability or record type as a peer UI destination or permanently visible region;
- optimize each screen around the user's current verification task;
- retain complete information, but stage it according to when it becomes useful.

Sources:
- ISO 9241-110:2020, Interaction principles: https://www.iso.org/obp/ui?_escaped_fragment_=iso%3Astd%3Aiso%3A9241%3A-110%3Adis%3Aed-2%3Av1%3Aen
- ISO overview: https://www.iso.org/standard/75258.html

## 2. Cognitive load: preserve domain complexity, remove interface complexity

Sweller's Cognitive Load Theory distinguishes the mental effort inherent in the problem from avoidable processing imposed by how information/tasks are presented.

For TruthLens:
- factual adjudication is intrinsically cognitively demanding;
- provenance, conflicting evidence, role restrictions, and decision accountability are legitimate complexity;
- searching for the current case, deciding which panel matters, remembering where the action lives, interpreting flat groups of equally weighted metadata, or scrolling past irrelevant history are avoidable interface complexity.

Recent HCI evidence strengthens this application:
- a 2026 Human Factors systematic review of 87 usability studies treats cognitive load as an explicit software-usability outcome and catalogs performance measures, NASA-TLX, eye fixation, and other methods;
- a 2025/2026 study of 564 physicians found that higher system usability reduced extraneous cognitive load by aligning interface design with workflow and reducing navigation effort; information overload partly mediated these relationships.

Sources:
- Sweller (1988), Cognitive Load During Problem Solving: https://doi.org/10.1207/s15516709cog1202_4
- Darejeh et al. (2026), Cognitive Load Measurement Methods for Usability Testing: https://pubmed.ncbi.nlm.nih.gov/41849193/
- EHR data/system usability and physicians' cognitive load: https://pubmed.ncbi.nlm.nih.gov/41535720/

## 3. Situation awareness: design for perceive → comprehend → act

Endsley's situation-awareness model is highly relevant to professional verification work. Attention and working memory are limiting factors in dynamic decision environments; mental models and goal-directed behavior help operators cope with those limits.

TruthLens should make three levels obvious:

### Perceive
What case am I on? What is its current state? What evidence/status changed?

### Comprehend
Why is it in this state? What evidence is accepted/rejected/unreviewed? What blocker matters?

### Project / act
What can happen next? What action can *I* take? What role or condition must act next if I cannot?

This maps directly to our existing product questions:
- Where am I?
- What has happened?
- What still needs to happen?
- What do I do next?

Source:
- Endsley (1995), Toward a Theory of Situation Awareness in Dynamic Systems: https://doi.org/10.1518/001872095779049543

## 4. Progressive disclosure: necessary information does not need equal immediacy

Nielsen Norman Group describes progressive disclosure as a way to reduce interface complexity by showing primary options first and deferring secondary/advanced details. Its key constraint is that frequently needed information must remain up front, and moving to secondary information must be obvious.

For TruthLens:
- do not delete provenance, audit, history, metadata, or evidence details;
- show a concise summary first;
- reveal full source metadata, technical IDs, event history, revision history, and secondary evidence details on demand;
- normally use no more than two disclosure levels; deeper nesting risks users becoming lost.

Important nuance: staged disclosure is harmful when users need to compare/interact with information continuously. Evidence summary + decision controls that must be consulted together should remain in the same work context.

Source:
- Nielsen Norman Group, Progressive Disclosure: https://www.nngroup.com/articles/progressive-disclosure/

## 5. Overview + focus + details on demand

Shneiderman's visual information-seeking mantra — overview first, zoom/filter, details on demand — provides a useful structural principle for high-information professional interfaces. Cockburn, Karlson, and Bederson's ACM review distinguishes overview+detail, zooming, focus+context, and cue-based approaches.

TruthLens adaptation:

### Overview
Case identity, current stage, readiness, evidence counts, important blocker, current decision/publication state.

### Focus
The one current work object: selected evidence case, adjudication decision form, draft, publication review.

### Details on demand
Full evidence metadata, verification intelligence, provenance, history, technical identifiers, audit events.

This should not be interpreted as a visualization rule only; it is a useful hierarchy for the professional workbench.

Sources:
- Shneiderman (1996), The Eyes Have It: https://doi.org/10.1109/VL.1996.545307
- Cockburn, Karlson & Bederson, Overview+Detail / Focus+Context review: https://doi.org/10.1145/1456650.1456652

## 6. Recognition over recall

Users should not have to remember:
- which investigation a global case belongs to;
- which stage follows Evidence Review;
- what the current blocker was after scrolling;
- whether a visible AI analysis is authoritative;
- where a completed action moved the case.

Keep case identity, current stage, role, and next action visible/retrievable in context.

Source:
- Nielsen Norman Group, Recognition Rather Than Recall: https://www.nngroup.com/articles/recognition-and-recall/

## 7. Information scent: navigation labels must predict the destination

Information Foraging Theory models navigation choices using "information scent": proximal cues that indicate whether a path is likely to satisfy the user's goal.

TruthLens implication:
- "Investigations" should clearly signal resumable case work;
- "Evidence Review" and "Adjudication" should signal stage/task meaning, not implementation-module meaning;
- queue vs investigation-context behavior must be visually and linguistically distinguishable;
- buttons should say what happens next ("Review 2 evidence items", "Open adjudication") rather than generic "Open" where possible.

Sources:
- Pirolli & Card, Information Foraging in Information Access Environments: https://chi1995.acm.org/proceedings/papers/ppp_bdy.htm
- Pirolli (2005), Rational Analyses of Information Foraging on the Web: https://doi.org/10.1207/s15516709cog0000_20

## 8. Visual hierarchy and Gestalt grouping

W3C cognitive-accessibility guidance recommends:
- logical sections;
- visually differentiated regions;
- headings and cues defining purpose;
- clear relationships between regions;
- borders, whitespace, and background changes used to communicate grouping.

Fluent 2 similarly treats spacing/proximity as a semantic tool: close items are perceived as related, while too much dense information is disorienting; whitespace should create logical sections and areas of focus.

TruthLens implication:
- whitespace must express grouping, not create unexplained empty voids;
- repeated cards with equal visual weight flatten hierarchy;
- nested cards should be minimized;
- sections should have a clear header, purpose, and internal rhythm;
- high-priority action/state gets stronger contrast; historical/technical content gets quieter treatment.

Sources:
- W3C, Clear and Understandable Page Structure: https://www.w3.org/WAI/WCAG2/supplemental/patterns/o2p03-page-structure/
- Microsoft Fluent 2, Layout: https://fluent2.microsoft.design/layout
- NN/g, Visual Hierarchy: https://www.nngroup.com/videos/visual-hierarchy/

## 9. Orientation through long professional workflows

W3C recommends making completed, current, and pending steps/choices visible so users can reorient after distraction.

TruthLens should show lifecycle orientation without falsely implying a rigid wizard:
- Evidence review — current / complete / needs attention;
- Adjudication — waiting / current / complete;
- Drafting — not started / in progress / returned;
- Publication — not started / in review / published.

Branching and revision loops must be represented honestly.

Source:
- W3C, Make Each Step Clear: https://www.w3.org/WAI/WCAG2/supplemental/patterns/o1p04-clear-steps/

## 10. High-stakes decision-support lessons

Clinical decision-support research is not a direct domain substitute for fact-checking, but it is useful analogous evidence because both involve professional users making consequential judgments from complex information.

Recent reviews emphasize:
- workflow fit;
- visibility;
- explainability;
- user control;
- avoiding alert/information overload;
- organizing information around decision needs rather than maximizing raw data exposure.

These findings support a TruthLens design where provenance remains available but the default screen privileges decision-relevant cues.

Sources:
- Systematic review of HCI elements in CDSS: https://pubmed.ncbi.nlm.nih.gov/40327851/
- Interface/information/interaction review for CDSS: https://pubmed.ncbi.nlm.nih.gov/29126196/
- 2025 systematic review of user-centered CDSS design: https://pubmed.ncbi.nlm.nih.gov/40540451/

## 11. Choice complexity: do not misuse Hick's Law

Reducing options can help, but Hick's Law should not be used as a simplistic "fewer buttons is always better" justification. CHI 2020 work argues that Hick's Law is often misapplied to HCI and that visual search and decision processes are more useful to analyze.

TruthLens implication:
- reduce competing *simultaneous* choices because they have low task relevance, not because of an arbitrary maximum count;
- retain necessary alternatives when users genuinely need them.

Source:
- Liu et al. (CHI 2020), How Relevant is Hick's Law for HCI?: https://doi.org/10.1145/3313831.3376878

## 12. UI UX Pro Max role

UI UX Pro Max remains useful as a secondary design-intelligence layer:
- its navigation guidance emphasizes nav hierarchy and Back behavior;
- its data-dense patterns emphasize drill-down and scanability;
- its rules include focus management, responsive behavior, accessibility, visible state, and reduced motion.

Its design-style catalog should not dictate the TruthLens visual identity. In particular:
- generic bento-card aesthetics are not appropriate for dense adjudication records;
- "data-dense dashboard" patterns are more relevant than marketing/SaaS showcase styles;
- its recommendations remain subordinate to TruthLens domain authority, `DESIGN.md`, and the HCI research above.

Repository:
https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

---

# Research conclusion

TruthLens's current problem is not "too much data" in the database or even "too much necessary information."

The problem is **too much necessary information presented with equal immediacy and insufficient hierarchy**.

The redesign should therefore apply:

1. **Task-first hierarchy** — current task/state/action dominates.
2. **Overview before detail** — summary of case/evidence/readiness first.
3. **Progressive disclosure** — provenance/history/technical detail remains available on demand.
4. **Focus + context** — primary work surface plus optional contextual support.
5. **Situation awareness** — always answer where/why/what-next.
6. **Semantic whitespace** — spacing communicates grouping, not emptiness.
7. **Strong section distinctions** — related content grouped; unrelated content visibly separated.
8. **Role-aware actions** — only relevant authorized action receives primary emphasis.
9. **Persistent orientation** — claim/stage/status survive scroll and stage transitions.
10. **Usability measurement** — validate cognitive load and first-time task performance, not aesthetics alone.
