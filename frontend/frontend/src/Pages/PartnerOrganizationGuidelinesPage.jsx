import { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { canAccessManagementConsole } from "../utils/management";
import { canAccessWorkspace } from "../utils/workspace";

import "./PartnerOrganizationGuidelinesPage.css";

const sections = [
   {
      id: "purpose",
      title: "1. Purpose",
      paragraphs: [
         "The TruthLens Partner Organization Guidelines establish the professional and organizational standards expected of organizations granted Partner Organization status within TruthLens.",
         "Partner Organizations are entrusted with professional verification responsibilities and access to the TruthLens Verification Workspace. These responsibilities require standards beyond those applicable to ordinary Community Platform participation.",
         "These Guidelines are intended to promote accurate, transparent, impartial, accountable, and secure professional verification while preserving confidence in the TruthLens verification process.",
      ],
   },
   {
      id: "scope",
      title: "2. Scope",
      paragraphs: ["These Guidelines apply to:"],
      bullets: [
         "recognized TruthLens Partner Organizations;",
         "their authorized organization administrators;",
         "Lead Verifiers;",
         "Researchers; and",
         "other organization members acting through professional TruthLens privileges where applicable.",
      ],
      after: [
         "Individual members remain independently subject to applicable TruthLens Community Guidelines and account policies.",
         "An organization's partnership status and an individual member's personal TruthLens account status are separate matters unless the circumstances independently justify action against both.",
      ],
   },
   {
      id: "verification-integrity",
      title: "3. Professional Verification Integrity",
      paragraphs: ["Partner Organizations must perform verification work carefully, honestly, and using reasonable evidentiary standards.", "Organizations are expected to:"],
      bullets: [
         "evaluate claims based on available evidence rather than a preferred outcome;",
         "use authoritative and primary sources when reasonably available;",
         "accurately represent the contents and limitations of sources;",
         "consider relevant evidence both supporting and contradicting a claim;",
         "distinguish evidence from speculation or unsupported inference;",
         "avoid knowingly misleading conclusions;",
         "ensure that published conclusions are reasonably supported by the evidence reviewed; and",
         "maintain professional review practices appropriate to their verification responsibilities.",
      ],
      after: [
         "A Partner Organization must not manipulate evidence, suppress material contradictory evidence, fabricate sources, or intentionally publish a verdict that it knows is unsupported.",
      ],
   },
   {
      id: "impartiality",
      title: "4. Impartiality and Fair Treatment",
      paragraphs: [
         "Partner Organizations must apply substantially equivalent standards of evidence and verification regardless of the person, organization, political group, institution, or viewpoint associated with a claim.",
         "TruthLens professional verification must not be used to:",
      ],
      bullets: [
         "promote partisan interests;",
         "target individuals or groups using intentionally unequal verification standards;",
         "protect favored individuals or organizations from legitimate scrutiny;",
         "manipulate verdicts for political, commercial, personal, or organizational advantage; or",
         "allow an undisclosed conflict of interest to determine a verification outcome.",
      ],
      after: [
         "Where a material conflict of interest may reasonably affect professional independence, the organization should disclose or appropriately manage that conflict.",
      ],
   },
   {
      id: "source-transparency",
      title: "5. Source and Evidence Transparency",
      paragraphs: [
         "Partner Organizations should maintain sufficient evidentiary transparency to allow professional verification decisions to be understood and reviewed.",
         "Where appropriate, professional verification should:",
      ],
      bullets: [
         "identify significant sources used;",
         "link to accessible sources when possible;",
         "favor suitable primary evidence over weaker secondary reporting;",
         "explain material limitations in available evidence;",
         "avoid presenting unreliable evidence as authoritative;",
         "identify relevant conflicts or interests affecting important sources when known; and",
         "retain enough evidence and reasoning to support subsequent review of the decision.",
      ],
      after: [
         "Source confidentiality, privacy, security, copyright, legal restrictions, and legitimate safety concerns may limit what can be made public.",
         "Such limitations do not remove the organization's responsibility to maintain an adequate internal evidentiary basis.",
      ],
   },
   {
      id: "honest-representation",
      title: "6. Honest Organizational Representation",
      paragraphs: [
         "Partner Organizations must provide materially accurate information concerning their identity and relationship with TruthLens.",
         "Organizations must not deliberately misrepresent:",
      ],
      bullets: [
         "their legal or organizational identity;",
         "authorized representatives;",
         "professional credentials;",
         "ownership or controlling relationships where relevant;",
         "eligibility information supplied to TruthLens;",
         "organizational status;",
         "their current TruthLens partnership status; or",
         "other information material to their recognition as a Partner Organization.",
      ],
      after: [
         "Deliberate concealment or falsification of material partnership information may constitute a serious integrity violation.",
      ],
   },
   {
      id: "corrections",
      title: "7. Corrections and Professional Accountability",
      paragraphs: [
         "Partner Organizations are expected to respond responsibly when credible evidence demonstrates that professional verification work contains a material error.",
         "Where correction is warranted, the organization should:",
      ],
      bullets: [
         "acknowledge the error;",
         "correct the affected professional record or publication using the mechanisms provided by TruthLens;",
         "ensure that the corrected conclusion is clearly distinguishable from the previous conclusion where applicable;",
         "document the basis for a material correction; and",
         "take reasonable measures to reduce recurrence when the problem reveals a process weakness.",
      ],
      after: [
         "The existence of an error alone does not necessarily establish misconduct.",
         "TruthLens should distinguish between:",
      ],
      afterBullets: [
         "an isolated good-faith error that is appropriately corrected;",
         "repeated negligent failures;",
         "refusal to address substantiated errors;",
         "concealment of known errors; and",
         "deliberate falsification or manipulation.",
      ],
   },
   {
      id: "workspace-use",
      title: "8. Responsible Use of the Verification Workspace",
      paragraphs: [
         "Professional TruthLens capabilities must be used only for authorized verification and organizational purposes.",
         "Partner Organization members must not:",
      ],
      bullets: [
         "intentionally access professional functionality they are not authorized to use;",
         "misuse investigation information;",
         "circumvent role or organization restrictions;",
         "impersonate another professional user;",
         "manipulate assignment, evidence, review, adjudication, or publication mechanisms;",
         "exploit vulnerabilities or security weaknesses;",
         "provide unauthorized persons with professional account access; or",
         "use the Verification Workspace for malicious, fraudulent, or unrelated purposes.",
      ],
      after: [
         "Professional access credentials must be appropriately protected.",
         "Suspected compromise of a professional account should be reported and addressed promptly.",
      ],
   },
   {
      id: "governance-capacity",
      title: "9. Organizational Governance and Capacity",
      paragraphs: [
         "A Partner Organization must retain sufficient organizational capacity to responsibly exercise its TruthLens partnership privileges.",
         "The organization should maintain:",
      ],
      bullets: [
         "identifiable responsible leadership;",
         "appropriate administration of member access and roles;",
         "reasonable internal accountability;",
         "the ability to perform professional verification responsibilities;",
         "current means for TruthLens to communicate material partnership matters; and",
         "sufficient organizational continuity to support its active partnership status.",
      ],
      after: [
         "Temporary organizational difficulties do not automatically constitute violations.",
         "Governance or capacity becomes a partnership concern when it materially prevents the organization from fulfilling its responsibilities or creates a significant integrity, security, or accountability risk.",
      ],
   },
   {
      id: "security-integrity",
      title: "10. Security, Legal, and Institutional Integrity",
      paragraphs: ["Partner Organizations must not knowingly use TruthLens to facilitate:"],
      bullets: [
         "fraud;",
         "malicious activity;",
         "unlawful access;",
         "intentional system abuse;",
         "falsification of professional records;",
         "serious deception concerning partnership activities; or",
         "other conduct materially incompatible with the integrity or security of the TruthLens verification environment.",
      ],
      after: [
         "A suspected security compromise is not automatically treated as misconduct by the affected organization.",
         "TruthLens may temporarily restrict professional privileges where necessary to protect the system while the incident is investigated.",
      ],
   },
   {
      id: "responsiveness",
      title: "11. Responsiveness and Active Partnership",
      paragraphs: [
         "Partner Organizations are expected to maintain reasonable communication concerning material partnership obligations.",
         "Organizations should respond within a reasonable period to matters involving:",
      ],
      bullets: [
         "serious verification concerns;",
         "professional access or security issues;",
         "required remediation;",
         "organizational-status inquiries;",
         "partnership compliance; and",
         "other material governance communications.",
      ],
      after: [
         "Temporary inactivity or delayed communication does not automatically justify enforcement.",
         "However, prolonged inactivity, abandonment of partnership responsibilities, or persistent non-responsiveness to necessary governance communications may affect continued active Partner status.",
      ],
   },
   {
      id: "cooperation",
      title: "12. Cooperation With Governance Reviews",
      paragraphs: [
         "When TruthLens has a reasonable basis to review a possible partnership issue, the Partner Organization is expected to cooperate in good faith.",
         "Depending on the issue, cooperation may include:",
      ],
      bullets: [
         "responding to identified concerns;",
         "providing relevant non-privileged information;",
         "clarifying professional decisions;",
         "identifying corrective measures;",
         "addressing security concerns;",
         "completing reasonable remediation requirements; or",
         "updating material organizational information.",
      ],
      after: [
         "A request for information should be proportionate to the matter being reviewed.",
         "TruthLens should not require disclosure of information unrelated to the governance concern.",
      ],
   },
   {
      id: "organizational-responsibility",
      title: "13. Organizational Responsibility and Individual Conduct",
      paragraphs: [
         "TruthLens should distinguish misconduct attributable to an individual member from misconduct attributable to the Partner Organization.",
         "An isolated action by one organization member should not automatically be considered institutional misconduct.",
         "Factors relevant to organizational responsibility may include whether:",
      ],
      bullets: [
         "organization leadership authorized the conduct;",
         "the conduct resulted from an organizational policy or established practice;",
         "multiple members engaged in similar conduct;",
         "leadership knew of the problem and failed to reasonably address it;",
         "the organization attempted to conceal the conduct;",
         "the issue demonstrates a systemic organizational failure; or",
         "the organization appropriately investigated and corrected the individual misconduct.",
      ],
      after: [
         "This distinction protects Partner Organizations from disproportionate institutional penalties for isolated unauthorized conduct while preserving accountability for systemic failures.",
      ],
   },
   {
      id: "professional-identity",
      title: "14. Professional Identity and Public Representation",
      paragraphs: [
         "Authorized Partner Organization members may be identified through their professional organizational affiliation within supported TruthLens interfaces.",
         "Professional identity must accurately reflect:",
      ],
      bullets: [
         "the member's current Partner Organization;",
         "the member's current professional role where displayed; and",
         "the organization's current partnership status.",
      ],
      after: [
         "Former or suspended status must not be represented as active partnership.",
         "Historical verification work should preserve the affiliation that was valid when that work was performed.",
      ],
   },
   {
      id: "published-work",
      title: "15. Published Work and Institutional Provenance",
      paragraphs: [
         "TruthLens preserves the historical integrity of completed professional work.",
         "If an organization is later suspended or its partnership ends:",
      ],
      bullets: [
         "previously completed legitimate reviews are not automatically deleted;",
         "published fact-checks are not automatically invalidated;",
         "historical authorship and institutional attribution remain preserved;",
         "governance history does not retroactively alter who performed prior professional work; and",
         "subsequent corrections or governance actions should be recorded without rewriting historical provenance.",
      ],
      after: [
         "A specific published fact-check may still be corrected, revised, withdrawn, or otherwise handled through the appropriate editorial process when independently justified.",
      ],
   },
   {
      id: "partnership-status",
      title: "16. Partnership Status",
      paragraphs: [
         "A Partner Organization may hold a lifecycle status reflecting its current relationship with TruthLens.",
         "Relevant states may include:",
      ],
      definitions: [
         ["Active Partner", "The organization currently holds professional partnership privileges."],
         ["Suspended Partner", "Active partnership privileges are temporarily restricted while a governance, remediation, security, or administrative matter is addressed."],
         ["Former Partner", "The organization's active partnership has ended."],
      ],
      after: [
         "Suspension is temporary and distinct from partnership termination.",
         "Former Partner status preserves historical attribution while accurately indicating that the organization no longer holds current professional authority.",
      ],
   },
   {
      id: "violations",
      title: "17. Violations of These Guidelines",
      paragraphs: [
         "Potential violations are evaluated according to the TruthLens Partnership Enforcement Policy.",
         "TruthLens considers the circumstances of each case, including:",
      ],
      bullets: [
         "the applicable standard;",
         "available evidence;",
         "seriousness;",
         "actual or potential harm;",
         "intent;",
         "scope;",
         "relevant history;",
         "correctability;",
         "response of the organization;",
         "effectiveness of prior remediation; and",
         "urgency of the risk.",
      ],
      after: [
         "TruthLens does not use a rule under which a fixed number of violations automatically results in partnership termination.",
      ],
   },
   {
      id: "governance-actions",
      title: "18. Governance Actions",
      paragraphs: ["Depending on the circumstances, governance responses may include:"],
      bullets: [
         "guidance or notice;",
         "formal corrective action;",
         "required remediation;",
         "temporary suspension;",
         "reinstatement;",
         "continued monitoring;",
         "administrative conclusion of partnership; or",
         "termination for cause.",
      ],
      after: [
         "Serious or urgent circumstances may justify temporary protective action before a final determination is made.",
      ],
   },
   {
      id: "eligibility-changes",
      title: "19. Changes Affecting Partnership Eligibility",
      paragraphs: [
         "A Partner Organization should inform TruthLens of material changes that substantially affect its ability to satisfy partnership responsibilities.",
         "Examples may include:",
      ],
      bullets: [
         "dissolution;",
         "cessation of verification operations;",
         "material organizational restructuring affecting responsible leadership;",
         "loss of the organization's ability to operate;",
         "serious security compromise affecting professional access; or",
         "a voluntary decision to end the partnership.",
      ],
      after: [
         "Routine organizational changes do not require governance action unless they materially affect the partnership.",
      ],
   },
   {
      id: "voluntary-withdrawal",
      title: "20. Voluntary Withdrawal",
      paragraphs: [
         "A Partner Organization may request to conclude its relationship with TruthLens.",
         "Voluntary withdrawal is not considered misconduct and should not be recorded as termination for a policy violation.",
         "Historical professional work and attribution remain preserved after withdrawal.",
         "The organization becomes a Former Partner once the partnership-ending process is completed.",
      ],
   },
   {
      id: "other-policies",
      title: "21. Relationship to Other TruthLens Policies",
      paragraphs: ["These Guidelines should be interpreted together with applicable TruthLens policies, including:"],
      bullets: [
         "the Partnership Enforcement Policy;",
         "Verification Standards;",
         "Community Guidelines;",
         "Safety and Reporting Guidelines; and",
         "applicable privacy, security, and account policies.",
      ],
      after: [
         "Where organization members participate as ordinary community users, Community Platform rules continue to apply independently of their professional affiliation.",
      ],
   },
   {
      id: "guiding-principle",
      title: "22. Guiding Principle",
      paragraphs: [
         "TruthLens Partner status represents an ongoing professional relationship based on evidence-based verification, impartiality, transparency, accountability, responsible platform use, organizational integrity, and continued capacity to fulfill professional responsibilities.",
         "The purpose of these Guidelines is not to punish good-faith mistakes.",
         "Their purpose is to protect the reliability of professional verification while giving Partner Organizations clear standards by which their participation can be understood, evaluated, corrected, and, when necessary, restricted or concluded.",
      ],
   },
];

function GuidelineSection({ section }) {
   return (
      <section className="partner-guidelines-section" id={section.id}>
         <h2>{section.title}</h2>
         {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
         {section.bullets?.length ? (
            <ul>
               {section.bullets.map((item) => <li key={item}>{item}</li>)}
            </ul>
         ) : null}
         {section.after?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
         {section.afterBullets?.length ? (
            <ul>
               {section.afterBullets.map((item) => <li key={item}>{item}</li>)}
            </ul>
         ) : null}
         {section.definitions?.length ? (
            <dl className="partner-guidelines-definitions">
               {section.definitions.map(([term, description]) => (
                  <div key={term}>
                     <dt>{term}</dt>
                     <dd>{description}</dd>
                  </div>
               ))}
            </dl>
         ) : null}
      </section>
   );
}

const frameworkSections = [
   "1. Purpose",
   "2. Core Governance Principles",
   "3. Partner Organization Standards",
   "4. Partnership Violation Factors",
   "5. Severity Assessment",
   "6. Severity Levels",
   "7. Enforcement Lifecycle",
   "8. Suspension",
   "9. Required Suspension Record",
   "10. Effects of Suspension",
   "11. Remediation",
   "12. Reinstatement",
   "13. Ending a Partnership",
   "14. Grounds for Ending Partnership",
   "15. Required Partnership-Ending Record",
   "16. Reason / Rationale Standard",
   "17. Notice to the Partner Organization",
   "18. Review, Reconsideration, and Reinstatement",
   "19. Public, Partner, and Internal Information",
   "20. Historical Preservation",
   "21. Automated Signals and Human Decisions",
   "22. Administrative Authority",
   "23. Governance Auditability",
   "24. Guiding Enforcement Rule",
];

const enforcementSections = [
   "1. Purpose",
   "2. Scope",
   "3. Decision Authority",
   "4. Enforcement Principles",
   "5. Partnership Factors",
   "6. Other Factor",
   "7. Severity Assessment",
   "8. Severity Levels",
   "9. No Automatic Strike Rule",
   "10. Governance Action Ladder",
   "11. Guidance or Notice",
   "12. Formal Corrective Action",
   "13. Suspension",
   "13.1 Remedial Suspension",
   "13.2 Precautionary Suspension",
   "13.3 Administrative Suspension",
   "14. Required Suspension Information",
   "15. Suspension Effects",
   "16. Remediation Plan",
   "17. Reinstatement",
   "18. Continued Monitoring or Probation",
   "19. Ending Partnership",
   "19.1 Voluntary Withdrawal",
   "19.2 Administrative Conclusion",
   "19.3 Termination for Cause",
   "20. Factors Supporting Partnership Termination",
   "21. Required Partnership-Ending Information",
   "22. Emergency or Immediate Action",
   "23. Notice",
   "24. Reconsideration",
   "25. Review of Serious Decisions",
   "26. Governance Information Visibility",
   "27. Historical Preservation",
   "28. Governance Audit Trail",
   "29. Automated Indicators",
   "30. Enforcement Decision Rule",
   "31. Policy Review",
];

const governanceDocuments = [
   {
      key: "guidelines",
      title: "Partner Organization Guidelines",
      description: "Professional and organizational standards for recognized Partner Organizations.",
      intro: "Professional and organizational standards for recognized TruthLens Partner Organizations and members acting through professional TruthLens privileges.",
   },
   {
      key: "framework",
      title: "Partnership Governance Framework",
      description: "Governance principles, lifecycle standards, decision factors, and administrative safeguards.",
      intro: "Standards, decision factors, enforcement principles, and lifecycle procedures governing Partner Organizations.",
      sectionTitles: frameworkSections,
   },
   {
      key: "enforcement",
      title: "Partnership Enforcement Policy",
      description: "Enforcement factors, severity, suspension, reinstatement, partnership ending, and review standards.",
      intro: "Policy governing proportionate, documented, and human-controlled enforcement involving Partner Organizations.",
      sectionTitles: enforcementSections,
   },
];

function PartnerOrganizationGuidelinesPage() {
   const { user } = useAuth();
   const [searchParams] = useSearchParams();
   const requestedDocument = searchParams.get("document") || "guidelines";
   const currentDocument = governanceDocuments.find((document) => document.key === requestedDocument)
      || governanceDocuments[0];
   const currentSections = currentDocument.key === "guidelines"
      ? sections
      : (currentDocument.sectionTitles || []).map((title, index) => ({
         id: `policy-section-${index + 1}`,
         title,
      }));
   const [activeSection, setActiveSection] = useState(currentSections[0]?.id || "");

   const location = useLocation();
   const isPlatformAdmin = canAccessManagementConsole(user);
   const professionalIdentity = user?.community_identity?.professional_identity || null;
   const canView = isPlatformAdmin || Boolean(professionalIdentity);
   const managementView = location.pathname.startsWith("/management/");

   useEffect(() => {
      setActiveSection(currentSections[0]?.id || "");
      const sectionNodes = currentSections
         .map((section) => document.getElementById(section.id))
         .filter(Boolean);
      if (!sectionNodes.length) return undefined;

      const observer = new IntersectionObserver(
         (entries) => {
            const visibleEntries = entries
               .filter((entry) => entry.isIntersecting)
               .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
            if (visibleEntries.length) {
               setActiveSection(visibleEntries[0].target.id);
            }
         },
         {
            rootMargin: "-96px 0px -68% 0px",
            threshold: [0, 0.1, 0.4],
         },
      );

      sectionNodes.forEach((node) => observer.observe(node));
      return () => observer.disconnect();
   }, [requestedDocument]);

   if (!canView) {
      return <Navigate to="/community" replace />;
   }

   const backTo = managementView
      ? "/management"
      : canAccessWorkspace(user)
         ? "/workspace"
         : "/community";
   const backLabel = managementView
      ? "Management Console"
      : canAccessWorkspace(user)
         ? "Verification Workspace"
         : "Community";

   return (
      <main className={`partner-guidelines-page ${managementView ? "partner-guidelines-page--management" : ""}`}>
         <div className="partner-guidelines-page__content">
            <Link className="partner-guidelines-back" to={backTo}>
               ← {backLabel}
            </Link>

            <div className="partner-guidelines-layout">
               <aside className="partner-guidelines-sidebar partner-guidelines-sidebar--toc" aria-label="On this page">
                  <div className="partner-guidelines-sidebar__sticky">
                     <span className="partner-guidelines-sidebar__eyebrow">On this page</span>
                     <nav className="partner-guidelines-toc">
                        {currentSections.map((section) => (
                           <a
                              href={`#${section.id}`}
                              key={section.id}
                              className={activeSection === section.id ? "is-active" : ""}
                              aria-current={activeSection === section.id ? "location" : undefined}
                           >
                              {section.title}
                           </a>
                        ))}
                     </nav>
                  </div>
               </aside>

               <div className="partner-guidelines-main">
                  <header className="partner-guidelines-header">
                     <span>TruthLens Partner Governance</span>
                     <h1>{currentDocument.title}</h1>
                     <p>{currentDocument.intro}</p>
                     <div className="partner-guidelines-access-note">
                        <strong>Read-only policy</strong>
                        <p>
                           These Guidelines apply to Partner Organizations, Organization Administrators,
                           Lead Verifiers, Researchers, and other members using professional privileges.
                        </p>
                     </div>
                  </header>

                  {currentDocument.key === "guidelines" ? (
                     <article className="partner-guidelines-document">
                        {sections.map((section) => <GuidelineSection section={section} key={section.id} />)}
                     </article>
                  ) : (
                     <article className="partner-guidelines-document partner-guidelines-document--index">
                        <div className="partner-guidelines-policy-note">
                           <strong>Read-only governance document</strong>
                           <p>
                              This view exposes the document structure from the authoritative TruthLens policy source.
                              The policy text itself is not rewritten or summarized here.
                           </p>
                        </div>
                        {currentSections.map((section) => (
                           <section className="partner-guidelines-section partner-guidelines-section--index" id={section.id} key={section.id}>
                              <h2>{section.title}</h2>
                           </section>
                        ))}
                     </article>
                  )}
               </div>

               <aside className="partner-guidelines-sidebar partner-guidelines-sidebar--documents" aria-label="Partner governance documents">
                  <div className="partner-guidelines-sidebar__sticky">
                     <span className="partner-guidelines-sidebar__eyebrow">Governance documents</span>
                     <div className="partner-governance-documents">
                        {governanceDocuments.map((document) => {
                           const documentHref = document.key === "guidelines"
                              ? location.pathname
                              : `${location.pathname}?document=${document.key}`;
                           const isCurrent = currentDocument.key === document.key;
                           return (
                              <Link
                                 key={document.key}
                                 to={documentHref}
                                 className={`partner-governance-document-card ${isCurrent ? "is-current" : ""}`}
                              >
                                 <div className="partner-governance-document-card__title-row">
                                    <strong>{document.title}</strong>
                                    {isCurrent ? <span>Current</span> : null}
                                 </div>
                                 <p>{document.description}</p>
                              </Link>
                           );
                        })}
                     </div>
                     <p className="partner-guidelines-sidebar__note">
                        These documents are read together as the Partner Governance reference set.
                     </p>
                  </div>
               </aside>
            </div>
         </div>
      </main>
   );
}

export default PartnerOrganizationGuidelinesPage;
