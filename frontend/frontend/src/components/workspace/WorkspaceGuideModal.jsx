import { useEffect, useMemo, useRef, useState } from "react";

import Icons from "../Icons.jsx";

import "./WorkspaceGuideModal.css";

const GUIDE_DETAILS = {
   intake: {
      eyebrow: "Start here",
      title: "Intake",
      summary: "Choose eligible community investigations your Partner Organization is ready to verify.",
      actions: [
         "Review the claim and its verification context.",
         "Choose an investigation that fits your organization's scope.",
         "Claim it to begin professional verification work.",
      ],
      visual: ["Community claim", "Check scope", "Claim investigation"],
   },
   workload: {
      eyebrow: "Investigation work",
      title: "Investigations",
      summary: "Resume organization-owned investigations and keep verification work moving.",
      actions: [
         "See the investigations currently owned by your organization.",
         "Open a case to review its context, evidence, and progress.",
         "Continue the next available verification step.",
      ],
      visual: ["Owned case", "Research & review", "Ready for next step"],
   },
   evidence: {
      eyebrow: "Establish the evidence basis",
      title: "Evidence Review",
      summary: "Review submitted evidence before it can support an authoritative decision.",
      actions: [
         "Open and inspect submitted sources.",
         "Verify suitable evidence or reject evidence that should not be relied on.",
         "Build the reviewed evidence basis used during adjudication.",
      ],
      visual: ["Submitted source", "Verify or reject", "Reviewed evidence"],
   },
   adjudication: {
      eyebrow: "Authoritative decision",
      title: "Adjudication",
      summary: "Evaluate the reviewed record and issue your Partner Organization's factual determination.",
      actions: [
         "Review the evidence that passed professional review.",
         "Choose Fact, Fake, Misleading, or Satire.",
         "Record the rationale and confirm the authoritative decision.",
      ],
      visual: ["Reviewed evidence", "Choose verdict", "Confirm decision"],
   },
   drafting: {
      eyebrow: "Prepare the fact-check",
      title: "Drafting",
      summary: "Turn completed verification work into a clear public-facing institutional fact-check.",
      actions: [
         "Start from an adjudicated investigation.",
         "Write the explanation and organize the supporting sources.",
         "Prepare the draft for publication review.",
      ],
      visual: ["Adjudication", "Write fact-check", "Draft ready"],
   },
   publishing: {
      eyebrow: "Editorial release",
      title: "Publishing",
      summary: "Review completed drafts and publish approved fact-checks on behalf of the organization.",
      actions: [
         "Review the final draft and its supporting record.",
         "Confirm that the publication is ready for the public.",
         "Publish the institutional fact-check.",
      ],
      visual: ["Final draft", "Publication review", "Publish"],
   },
   publications: {
      eyebrow: "Institutional record",
      title: "Publications",
      summary: "Browse published fact-checks and their retained institutional history.",
      actions: [
         "Find fact-checks your organization has published.",
         "Open the publication and its version history.",
         "Start an allowed revision or correction workflow when needed.",
      ],
      visual: ["Published fact-check", "Version history", "Institutional record"],
   },
   "factual-corrections": {
      eyebrow: "Post-publication integrity",
      title: "Factual Corrections",
      summary: "Correct published factual errors through a dedicated, auditable workflow.",
      actions: [
         "Review the correction request and supporting evidence.",
         "Prepare and approve the factual correction proposal.",
         "Publish the correction while preserving prior history.",
      ],
      visual: ["Correction request", "Review & proposal", "Corrected publication"],
   },
   organization: {
      eyebrow: "Organization administration",
      title: "Organization",
      summary: "Manage the Partner Organization settings and member access available to your role.",
      actions: [
         "Review organization details and verification settings.",
         "Manage eligible members and roles.",
         "Keep organization access aligned with current responsibilities.",
      ],
      visual: ["Organization", "Members & roles", "Workspace access"],
   },
   analytics: {
      eyebrow: "Verification insights",
      title: "Analytics",
      summary: "Understand observed verification activity, resolution, completion, and participation.",
      actions: [
         "Review verification activity over time.",
         "Inspect completion and resolution indicators.",
         "Use observed metrics to understand organization workflow.",
      ],
      visual: ["Activity", "Resolution metrics", "Insights"],
   },
   accountability: {
      eyebrow: "Professional history",
      title: "Accountability History",
      summary: "Review attributable actions and important changes affecting the organization.",
      actions: [
         "See who performed recorded professional actions.",
         "Review changes to important organization or verification records.",
         "Use the retained history for institutional accountability.",
      ],
      visual: ["Professional action", "Recorded change", "Audit history"],
   },
};

function VisualFlow({ labels, compact = false }) {
   return (
      <div className={`workspace-guide-visual-flow ${compact ? "is-compact" : ""}`} aria-hidden="true">
         {labels.map((label, index) => (
            <div className="workspace-guide-visual-step-wrap" key={label}>
               <div className="workspace-guide-visual-step">
                  <span>{index + 1}</span>
                  <strong>{label}</strong>
               </div>
               {index < labels.length - 1 ? (
                  <span className="workspace-guide-visual-arrow">→</span>
               ) : null}
            </div>
         ))}
      </div>
   );
}

function WorkflowVisual({ sections }) {
   const coreOrder = ["intake", "workload", "evidence", "adjudication", "drafting", "publishing"];
   const visible = coreOrder
      .map((id) => sections.find((section) => section.id === id))
      .filter(Boolean);

   return (
      <div className="workspace-guide-workflow-visual" aria-label="Verification workflow">
         <div className="workspace-guide-workflow-track" aria-hidden="true">
            {visible.map((section, index) => (
               <div className="workspace-guide-workflow-node-wrap" key={section.id}>
                  <div className="workspace-guide-workflow-node">
                     <span className="workspace-guide-workflow-icon">
                        <Icons name={section.icon} size={18} />
                     </span>
                     <strong>{section.label}</strong>
                  </div>
                  {index < visible.length - 1 ? <span className="workspace-guide-workflow-arrow">→</span> : null}
               </div>
            ))}
            <span className="workspace-guide-workflow-pulse" />
         </div>
      </div>
   );
}

export default function WorkspaceGuideModal({
   firstVisit = false,
   organizationName,
   roleLabel,
   sectionGroups,
   onDismiss,
}) {
   const dialogRef = useRef(null);
   const sections = useMemo(
      () => sectionGroups.flatMap((group) => group.sections),
      [sectionGroups],
   );
   const sequence = useMemo(
      () => [
         { key: "welcome", kind: "welcome" },
         { key: "workflow", kind: "workflow" },
         ...sections.map((section) => ({ key: section.id, kind: "section", section })),
         { key: "ready", kind: "ready" },
      ],
      [sections],
   );
   const [activeKey, setActiveKey] = useState(firstVisit ? "welcome" : "contents");

   useEffect(() => {
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      window.requestAnimationFrame(() => dialogRef.current?.focus());

      const handleKeyDown = (event) => {
         if (event.key === "Escape") {
            onDismiss(firstVisit ? "skip" : "close");
         }
      };
      document.addEventListener("keydown", handleKeyDown);

      return () => {
         document.body.style.overflow = previousOverflow;
         document.removeEventListener("keydown", handleKeyDown);
      };
   }, [firstVisit, onDismiss]);

   const sequenceIndex = sequence.findIndex((item) => item.key === activeKey);
   const current = sequenceIndex >= 0 ? sequence[sequenceIndex] : null;
   const progress = sequenceIndex >= 0 ? sequenceIndex + 1 : null;

   const goPrevious = () => {
      if (sequenceIndex > 0) {
         setActiveKey(sequence[sequenceIndex - 1].key);
      }
   };

   const goNext = () => {
      if (sequenceIndex < sequence.length - 1) {
         setActiveKey(sequence[sequenceIndex + 1].key);
      }
   };

   const renderContents = () => (
      <div className="workspace-guide-panel workspace-guide-contents">
         <div className="workspace-guide-panel-heading">
            <span className="workspace-guide-eyebrow">Workspace Guide</span>
            <h2>What would you like to review?</h2>
            <p>Jump directly to any Workspace area available to your role.</p>
         </div>

         <button
            type="button"
            className="workspace-guide-contents-overview"
            onClick={() => setActiveKey("workflow")}
         >
            <span className="workspace-guide-contents-icon"><Icons name="scan-line" size={19} /></span>
            <span>
               <strong>How verification moves through the Workspace</strong>
               <small>See the core investigation-to-publication workflow.</small>
            </span>
            <span aria-hidden="true">→</span>
         </button>

         <div className="workspace-guide-contents-groups">
            {sectionGroups.map((group) => (
               <section key={group.id}>
                  <h3>{group.label}</h3>
                  <div>
                     {group.sections.map((section) => (
                        <button
                           type="button"
                           key={section.id}
                           onClick={() => setActiveKey(section.id)}
                        >
                           <span><Icons name={section.icon} size={17} /></span>
                           <strong>{section.label}</strong>
                        </button>
                     ))}
                  </div>
               </section>
            ))}
         </div>
      </div>
   );

   const renderCurrent = () => {
      if (!current) return renderContents();

      if (current.kind === "welcome") {
         return (
            <div className="workspace-guide-panel workspace-guide-welcome">
               <div className="workspace-guide-hero-illustration" aria-hidden="true">
                  <div className="workspace-guide-hero-orbit">
                     <span><Icons name="scan-line" size={22} /></span>
                     <span><Icons name="paperclip" size={22} /></span>
                     <span><Icons name="list-checks" size={22} /></span>
                  </div>
                  <div className="workspace-guide-hero-center">
                     <Icons name="shield-user" size={34} />
                  </div>
               </div>

               <div className="workspace-guide-panel-heading">
                  <span className="workspace-guide-eyebrow">Welcome to professional verification</span>
                  <h2>Welcome to the Verification Workspace</h2>
                  <p>
                     This is where {organizationName || "your Partner Organization"} investigates claims,
                     reviews evidence, makes authoritative decisions, and publishes institutional fact-checks.
                  </p>
               </div>

               <div className="workspace-guide-identity">
                  <span><Icons name="shield-user" size={16} /></span>
                  <div>
                     <small>Your Workspace role</small>
                     <strong>{roleLabel || "Partner member"}</strong>
                  </div>
               </div>
            </div>
         );
      }

      if (current.kind === "workflow") {
         return (
            <div className="workspace-guide-panel">
               <div className="workspace-guide-panel-heading">
                  <span className="workspace-guide-eyebrow">The big picture</span>
                  <h2>How verification moves through TruthLens</h2>
                  <p>
                     Investigation work establishes what the evidence supports. Publication work turns that
                     determination into an institutional fact-check.
                  </p>
               </div>

               <WorkflowVisual sections={sections} />

               <div className="workspace-guide-workflow-legend">
                  <div>
                     <strong>Investigation work</strong>
                     <span>Determine what the reviewed evidence establishes.</span>
                  </div>
                  <div>
                     <strong>Publication</strong>
                     <span>Explain and publish the organization's completed determination.</span>
                  </div>
               </div>
            </div>
         );
      }

      if (current.kind === "ready") {
         return (
            <div className="workspace-guide-panel workspace-guide-ready">
               <div className="workspace-guide-ready-icon"><Icons name="check-circle" size={34} /></div>
               <div className="workspace-guide-panel-heading">
                  <span className="workspace-guide-eyebrow">Guide complete</span>
                  <h2>You're ready to use the Workspace</h2>
                  <p>
                     You can reopen this guide anytime from the <strong>Workspace Guide</strong> button in the
                     Workspace header.
                  </p>
               </div>
            </div>
         );
      }

      const detail = GUIDE_DETAILS[current.section.id] || {
         eyebrow: current.section.label,
         title: current.section.label,
         summary: current.section.description,
         actions: [current.section.description],
         visual: [current.section.label],
      };

      return (
         <div className="workspace-guide-panel">
            <div className="workspace-guide-panel-heading">
               <span className="workspace-guide-eyebrow">{detail.eyebrow}</span>
               <h2>{detail.title}</h2>
               <p>{detail.summary}</p>
            </div>

            <div className="workspace-guide-section-visual">
               <div className="workspace-guide-section-icon" aria-hidden="true">
                  <Icons name={current.section.icon} size={26} />
               </div>
               <VisualFlow labels={detail.visual} />
            </div>

            <ul className="workspace-guide-actions">
               {detail.actions.map((action) => (
                  <li key={action}>
                     <span aria-hidden="true">✓</span>
                     <span>{action}</span>
                  </li>
               ))}
            </ul>
         </div>
      );
   };

   return (
      <div className="workspace-guide-overlay" onMouseDown={(event) => {
         if (event.target === event.currentTarget) {
            onDismiss(firstVisit ? "skip" : "close");
         }
      }}>
         <section
            ref={dialogRef}
            className="workspace-guide-dialog"
            role="dialog"
            aria-modal="true"
            aria-label="Verification Workspace Guide"
            tabIndex={-1}
         >
            <header className="workspace-guide-header">
               <div>
                  <span>TruthLens</span>
                  <strong>Workspace Guide</strong>
               </div>

               <div className="workspace-guide-header-actions">
                  {activeKey !== "contents" ? (
                     <button type="button" onClick={() => setActiveKey("contents")}>
                        Guide contents
                     </button>
                  ) : null}
                  <button
                     type="button"
                     className="workspace-guide-close"
                     aria-label="Close Workspace Guide"
                     onClick={() => onDismiss(firstVisit ? "skip" : "close")}
                  >
                     ×
                  </button>
               </div>
            </header>

            <div className="workspace-guide-body">{activeKey === "contents" ? renderContents() : renderCurrent()}</div>

            {activeKey !== "contents" ? (
               <footer className="workspace-guide-footer">
                  <div className="workspace-guide-progress">
                     <span>{progress} of {sequence.length}</span>
                     <div aria-hidden="true">
                        {sequence.map((item, index) => (
                           <span
                              key={item.key}
                              className={index <= sequenceIndex ? "is-complete" : ""}
                           />
                        ))}
                     </div>
                  </div>

                  <div className="workspace-guide-footer-actions">
                     {firstVisit && current?.kind !== "ready" ? (
                        <button
                           type="button"
                           className="workspace-guide-skip"
                           onClick={() => onDismiss("skip")}
                        >
                           Skip guide
                        </button>
                     ) : null}

                     {sequenceIndex > 0 ? (
                        <button type="button" className="workspace-guide-secondary" onClick={goPrevious}>
                           Back
                        </button>
                     ) : null}

                     {current?.kind === "ready" ? (
                        <button
                           type="button"
                           className="workspace-guide-primary"
                           onClick={() => onDismiss(firstVisit ? "finish" : "close")}
                        >
                           Start using the Workspace
                        </button>
                     ) : (
                        <button type="button" className="workspace-guide-primary" onClick={goNext}>
                           Next
                        </button>
                     )}
                  </div>
               </footer>
            ) : (
               <footer className="workspace-guide-footer workspace-guide-footer--contents">
                  <span>Only areas available to your current Workspace role are shown.</span>
                  <button type="button" className="workspace-guide-primary" onClick={() => onDismiss("close")}>
                     Close guide
                  </button>
               </footer>
            )}
         </section>
      </div>
   );
}
