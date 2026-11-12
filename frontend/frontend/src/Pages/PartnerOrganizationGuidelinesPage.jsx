import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import {
   partnerGovernanceDocuments,
   resolvePartnerGovernanceDocumentKey,
} from "../data/partnerGovernanceDocuments";
import { canAccessManagementConsole } from "../utils/management";
import { canAccessWorkspace } from "../utils/workspace";

import "./PartnerOrganizationGuidelinesPage.css";

function PolicyBlock({ block }) {
   if (block.type === "paragraph") {
      return <p>{block.text}</p>;
   }

   if (block.type === "list") {
      const ListTag = block.ordered ? "ol" : "ul";
      return (
         <ListTag>
            {block.items.map((item) => <li key={item}>{item}</li>)}
         </ListTag>
      );
   }

   if (block.type === "definitions") {
      return (
         <dl className="partner-guidelines-definitions">
            {block.items.map(({ term, description }) => (
               <div key={term}>
                  <dt>{term}</dt>
                  <dd>{description}</dd>
               </div>
            ))}
         </dl>
      );
   }

   if (block.type === "table") {
      return (
         <div className="partner-guidelines-table-wrap">
            <table className="partner-guidelines-table">
               <caption>{block.caption}</caption>
               <thead>
                  <tr>
                     {block.columns.map((column) => <th scope="col" key={column}>{column}</th>)}
                  </tr>
               </thead>
               <tbody>
                  {block.rows.map((row, rowIndex) => (
                     <tr key={`${block.caption}-${rowIndex}`}>
                        {row.map((cell, cellIndex) => (
                           <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                        ))}
                     </tr>
                  ))}
               </tbody>
            </table>
         </div>
      );
   }

   if (block.type === "callout") {
      return (
         <aside className="partner-guidelines-callout">
            <strong>{block.title}</strong>
            <p>{block.text}</p>
         </aside>
      );
   }

   return null;
}

function PolicySection({ section }) {
   return (
      <section
         className="partner-guidelines-section"
         id={section.anchor}
         data-policy-section-id={section.id}
      >
         <h2>{section.title}</h2>
         {section.blocks.map((block, index) => (
            <PolicyBlock block={block} key={`${section.id}-${index}`} />
         ))}
      </section>
   );
}

function PolicyMetadata({ document }) {
   const metadata = document.metadata || {};
   return (
      <div className="partner-guidelines-policy-meta">
         <dl>
            <div>
               <dt>Version</dt>
               <dd>{metadata.version || "Not recorded"}</dd>
            </div>
            <div>
               <dt>Status</dt>
               <dd>{metadata.status || "Not recorded"}</dd>
            </div>
            <div>
               <dt>Effective date</dt>
               <dd>{metadata.effectiveDate || "Pending approval and publication"}</dd>
            </div>
            <div>
               <dt>Last updated</dt>
               <dd>{metadata.lastUpdated || "Not recorded"}</dd>
            </div>
         </dl>

         {document.changeHistory?.length ? (
            <details className="partner-guidelines-change-history">
               <summary>Change history</summary>
               <div>
                  {document.changeHistory.map((entry) => (
                     <article key={`${entry.version}-${entry.date}`}>
                        <strong>{entry.version} · {entry.date}</strong>
                        <p>{entry.summary}</p>
                     </article>
                  ))}
               </div>
            </details>
         ) : null}
      </div>
   );
}

function PartnerOrganizationGuidelinesPage() {
   const { user } = useAuth();
   const [searchParams] = useSearchParams();
   const requestedDocument = searchParams.get("document") || "guidelines";
   const resolvedDocumentKey = resolvePartnerGovernanceDocumentKey(requestedDocument);
   const currentDocument = useMemo(
      () => partnerGovernanceDocuments.find((item) => item.key === resolvedDocumentKey)
         || partnerGovernanceDocuments[0],
      [resolvedDocumentKey],
   );
   const currentSections = currentDocument.sections || [];
   const [activeSection, setActiveSection] = useState(currentSections[0]?.anchor || "");
   const resolvedActiveSection = currentSections.some((section) => section.anchor === activeSection)
      ? activeSection
      : (currentSections[0]?.anchor || "");
   const [showFloatingBack, setShowFloatingBack] = useState(false);
   const lastScrollYRef = useRef(0);
   const upwardDistanceRef = useRef(0);

   const location = useLocation();
   const isPlatformAdmin = canAccessManagementConsole(user);
   const professionalIdentity = user?.community_identity?.professional_identity || null;
   const canView = isPlatformAdmin || Boolean(professionalIdentity);
   const managementView = location.pathname.startsWith("/management/");

   useEffect(() => {
      lastScrollYRef.current = window.scrollY;
      upwardDistanceRef.current = 0;

      const handleScroll = () => {
         const currentY = Math.max(window.scrollY, 0);
         const previousY = lastScrollYRef.current;
         const delta = currentY - previousY;

         if (currentY <= 96) {
            setShowFloatingBack(false);
            upwardDistanceRef.current = 0;
         } else if (delta < 0) {
            upwardDistanceRef.current += Math.abs(delta);
            if (upwardDistanceRef.current >= 28) {
               setShowFloatingBack(true);
            }
         } else if (delta > 0) {
            upwardDistanceRef.current = 0;
            setShowFloatingBack(false);
         }

         lastScrollYRef.current = currentY;
      };

      window.addEventListener("scroll", handleScroll, { passive: true });
      return () => window.removeEventListener("scroll", handleScroll);
   }, []);

   useEffect(() => {
      const sectionNodes = currentSections
         .map((section) => document.getElementById(section.anchor))
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
   }, [currentSections]);

   if (!canView) {
      return <Navigate to="/community" replace />;
   }

   if (requestedDocument === "framework" || requestedDocument === "enforcement") {
      return <Navigate to={`${location.pathname}?document=governance`} replace />;
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

            <Link
               className={`partner-guidelines-floating-back ${showFloatingBack ? "is-visible" : ""}`}
               to={backTo}
               aria-hidden={!showFloatingBack}
               tabIndex={showFloatingBack ? 0 : -1}
            >
               ← {backLabel}
            </Link>

            <div className="partner-guidelines-layout">
               <aside className="partner-guidelines-sidebar partner-guidelines-sidebar--toc" aria-label="On this page">
                  <div className="partner-guidelines-sidebar__sticky">
                     <span className="partner-guidelines-sidebar__eyebrow">On this page</span>
                     <nav className="partner-guidelines-toc">
                        {currentSections.map((section) => (
                           <a
                              href={`#${section.anchor}`}
                              key={section.id}
                              className={resolvedActiveSection === section.anchor ? "is-active" : ""}
                              aria-current={resolvedActiveSection === section.anchor ? "location" : undefined}
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
                           {currentDocument.key === "guidelines"
                              ? "These Guidelines define the professional and organizational standards expected of Partner Organizations and members using professional privileges."
                              : "This Policy defines how TruthLens classifies and handles material Partner governance concerns. It reflects the current implemented governance model and its documented limitations."}
                        </p>
                     </div>
                     <PolicyMetadata document={currentDocument} />
                  </header>

                  <article className="partner-guidelines-document">
                     {currentSections.map((section) => (
                        <PolicySection section={section} key={section.id} />
                     ))}
                  </article>
               </div>

               <aside className="partner-guidelines-sidebar partner-guidelines-sidebar--documents" aria-label="Partner governance documents">
                  <div className="partner-guidelines-sidebar__sticky">
                     <span className="partner-guidelines-sidebar__eyebrow">Governance documents</span>
                     <div className="partner-governance-documents">
                        {partnerGovernanceDocuments.map((item) => {
                           const documentHref = item.key === "guidelines"
                              ? location.pathname
                              : `${location.pathname}?document=${item.key}`;
                           const isCurrent = currentDocument.key === item.key;
                           return (
                              <Link
                                 key={item.key}
                                 to={documentHref}
                                 className={`partner-governance-document-card ${isCurrent ? "is-current" : ""}`}
                              >
                                 <div className="partner-governance-document-card__title-row">
                                    <strong>{item.title}</strong>
                                 </div>
                                 <p>{item.description}</p>
                              </Link>
                           );
                        })}
                     </div>
                     <p className="partner-guidelines-sidebar__note">
                        The Guidelines define Partner standards. The Governance & Enforcement Policy defines how material concerns are handled.
                     </p>
                  </div>
               </aside>
            </div>
         </div>
      </main>
   );
}

export default PartnerOrganizationGuidelinesPage;
