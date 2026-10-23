
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import { getWorkspaceMembership } from "../utils/workspace";
import Button from "../components/ui/Button.jsx";
import Icons from "../components/Icons.jsx";
import AdjudicationReviewPanel from "../components/workspace/AdjudicationReviewPanel.jsx";
import EvidenceReviewPanel from "../components/workspace/EvidenceReviewPanel.jsx";
import InvestigationContextLinks from "../components/workspace/InvestigationContextLinks.jsx";
import VerificationIntelligencePanel from "../components/workspace/VerificationIntelligencePanel.jsx";

import "./InvestigationWorkspacePage.css";

function formatDateTime(value) {
   if (!value) return "Not recorded";
   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Not recorded";
   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function formatLabel(value) {
   if (!value) return "Not available";
   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

const STATE_ICON = {
   ACTIVE_NO_EVIDENCE: "clock",
   EVIDENCE_REVIEW: "paperclip",
   ADJUDICATION_READY: "list-checks",
   ADJUDICATION: "list-checks",
   DRAFTING_READY: "file-text",
   DRAFTING: "file-text",
   PUBLICATION_REVIEW: "check-circle",
};

function buildActionDestination(action, organizationId, assignmentId) {
   const targetId = action?.target?.id;
   if (!targetId || !organizationId) return null;

   const query = new URLSearchParams({
      organization_id: String(organizationId),
      from_assignment: String(assignmentId),
   });

   if (action.code === "REVIEW_EVIDENCE") {
      query.set("section", "evidence");
      query.set("case_id", targetId);
      return "/workspace?" + query.toString();
   }

   if (action.code === "ADJUDICATE") {
      query.set("section", "adjudication");
      query.set("case_id", targetId);
      return "/workspace?" + query.toString();
   }

   if (action.code === "CREATE_DRAFT" || action.code === "CONTINUE_DRAFT") {
      query.set("section", "drafting");
      query.set("resource_type", action.target.type);
      query.set("resource_id", targetId);
      return "/workspace?" + query.toString();
   }

   if (action.code === "REVIEW_PUBLICATION") {
      query.set("section", "publishing");
      query.set("fact_check_id", targetId);
      return "/workspace?" + query.toString();
   }

   return null;
}

function InvestigationWorkspacePage() {
   const { user, authFetch } = useAuth();
   const { assignmentId } = useParams();
   const location = useLocation();
   const navigate = useNavigate();
   const routeQuery = useMemo(() => new URLSearchParams(location.search), [location.search]);
   const organizationId = routeQuery.get("organization_id");
   const membership = useMemo(
      () => getWorkspaceMembership(user, organizationId),
      [organizationId, user],
   );

   const [requestVersion, setRequestVersion] = useState(0);
   const [contextOpen, setContextOpen] = useState(false);
   const [guidedAction, setGuidedAction] = useState(null);
   const stageRef = useRef(null);
   const guidedWorkRef = useRef(null);
   const requestKey =
      assignmentId && organizationId && membership
         ? `${assignmentId}:${organizationId}:${requestVersion}`
         : null;
   const [result, setResult] = useState({
      requestKey: null,
      data: null,
      error: "",
   });

   useEffect(() => {
      if (!requestKey) {
         return undefined;
      }

      let cancelled = false;

      const query = new URLSearchParams({ organization_id: organizationId });
      const url =
         resolveApiEndpoint("VERIFICATION_INVESTIGATION_DETAIL", assignmentId) +
         "?" +
         query.toString();

      authFetch(url, { method: "GET" })
         .then((data) => {
            if (cancelled) return;

            const identityMatches =
               data?.schema_version === "1.0" &&
               String(data?.assignment?.id ?? "") === String(assignmentId) &&
               String(data?.organization?.id ?? "") === String(organizationId);

            if (!identityMatches) {
               setResult({
                  requestKey,
                  data: null,
                  error:
                     "The investigation response did not match this workspace link. Return to Investigations and open it again.",
               });
               return;
            }

            setResult({ requestKey, data, error: "" });
         })
         .catch((error) => {
            if (cancelled) return;
            const message =
               error?.status === 404
                  ? "This active investigation is no longer available for the selected organization."
                  : error?.message || "Unable to load this investigation.";

            setResult((current) => {
               const currentDataMatchesRoute =
                  String(current.data?.assignment?.id ?? "") === String(assignmentId) &&
                  String(current.data?.organization?.id ?? "") === String(organizationId);

               return {
                  requestKey,
                  data: currentDataMatchesRoute ? current.data : null,
                  error: message,
               };
            });
         });

      return () => {
         cancelled = true;
      };
   }, [assignmentId, authFetch, membership, organizationId, requestKey]);

   const resultIsCurrent = Boolean(requestKey && result.requestKey === requestKey);
   const resultDataMatchesRoute =
      String(result.data?.assignment?.id ?? "") === String(assignmentId) &&
      String(result.data?.organization?.id ?? "") === String(organizationId);
   const isLoading = Boolean(requestKey && !resultIsCurrent && !resultDataMatchesRoute);
   const isRefreshing = Boolean(requestKey && !resultIsCurrent && resultDataMatchesRoute);
   const data = resultDataMatchesRoute ? result.data : resultIsCurrent ? result.data : null;
   const resultError = resultIsCurrent ? result.error : "";
   const fatalError = Boolean(resultError && !data);
   const refreshError = data && resultError ? resultError : "";
   const actions = Array.isArray(data?.allowed_actions) ? data.allowed_actions : [];
   const progressAction = actions.find((action) => action.code !== "RELEASE_INVESTIGATION") ?? null;
   const progressDestination = progressAction
      ? buildActionDestination(progressAction, organizationId, assignmentId)
      : null;
   const pending = Array.isArray(data?.pending) ? data.pending : [];

   const backToInvestigations = () => {
      const query = organizationId
         ? "?" + new URLSearchParams({ organization_id: organizationId }).toString()
         : "";
      navigate("/workspace/investigations" + query);
   };

   const scrollToRef = (ref) => {
      requestAnimationFrame(() => {
         const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
         ref.current?.scrollIntoView({
            behavior: reduceMotion ? "auto" : "smooth",
            block: "start",
         });
      });
   };

   const isInlineGuidedAction = (action) =>
      action?.code === "REVIEW_EVIDENCE" || action?.code === "ADJUDICATE";

   const handleProgressAction = (action) => {
      if (!action) {
         return;
      }

      if (isInlineGuidedAction(action)) {
         setContextOpen(false);
         setGuidedAction(action);
         scrollToRef(guidedWorkRef);
         return;
      }

      const destination = buildActionDestination(action, organizationId, assignmentId);
      if (destination) {
         navigate(destination);
      }
   };

   const handleGuidedWorkflowChanged = () => {
      setRequestVersion((value) => value + 1);
   };

   const handleContinueInvestigation = () => {
      setGuidedAction(null);
      scrollToRef(stageRef);
   };

   if (!organizationId) {
      return (
         <div className="investigation-workspace-page">
            <div className="investigation-workspace-state">
               <Icons name="alert-circle" size={26} />
               <h1>Organization context required</h1>
               <p>
                  Open the investigation from your organization’s Investigations list so TruthLens can preserve its
                  authorization context.
               </p>
               <Button variant="secondary" leadingIcon={<Icons name="arrow-left" />} onClick={() => navigate("/workspace")}>
                  Back to Workspace
               </Button>
            </div>
         </div>
      );
   }

   if (!membership) {
      return (
         <div className="investigation-workspace-page">
            <div className="investigation-workspace-state">
               <Icons name="lock" size={26} />
               <h1>Investigation unavailable</h1>
               <p>Your current account does not have an active membership for the organization in this link.</p>
               <Button variant="secondary" leadingIcon={<Icons name="arrow-left" />} onClick={() => navigate("/workspace")}>
                  Back to Workspace
               </Button>
            </div>
         </div>
      );
   }

   if (isLoading) {
      return (
         <div className="investigation-workspace-page">
            <div className="investigation-workspace-state" role="status" aria-live="polite">
               <Icons name="loader" size={24} className="investigation-workspace-spinner" />
               <h1>Opening investigation</h1>
               <p>Loading the persisted workflow state for this organization.</p>
            </div>
         </div>
      );
   }

   if (fatalError || !data) {
      return (
         <div className="investigation-workspace-page">
            <div className="investigation-workspace-state" role="alert">
               <Icons name="alert-circle" size={26} />
               <h1>Investigation unavailable</h1>
               <p>{fatalError ? resultError : "The investigation could not be loaded."}</p>
               <div className="investigation-workspace-state-actions">
                  <Button variant="secondary" leadingIcon={<Icons name="arrow-left" />} onClick={backToInvestigations}>
                     Back to investigations
                  </Button>
                  <Button leadingIcon={<Icons name="refresh-cw" />} onClick={() => setRequestVersion((value) => value + 1)}>
                     Try again
                  </Button>
               </div>
            </div>
         </div>
      );
   }

   const evidence = data.evidence || {};
   const adjudication = data.adjudication || {};
   const publication = data.publication;
   const state = data.state || {};
   const claim = data.claim || {};

   return (
      <div className="investigation-workspace-page">
         <header className="investigation-workspace-header">
            <button type="button" className="investigation-workspace-back" onClick={backToInvestigations}>
               <Icons name="arrow-left" size={16} />
               <span>Investigations</span>
            </button>

            <div className="investigation-workspace-heading">
               <div>
                  <p className="investigation-workspace-eyebrow">
                     Verification Workspace · {data.organization.name}
                  </p>
                  <h1>{claim.context_text || "Investigation"}</h1>
               </div>
               <div className="investigation-workspace-heading-actions">
                  <span className="investigation-workspace-active-status">
                     <Icons name="activity" size={14} />
                     Active investigation
                  </span>
                  <Button
                     variant="secondary"
                     density="compact"
                     leadingIcon={<Icons name="paperclip" size={14} />}
                     aria-expanded={contextOpen}
                     aria-controls="investigation-workspace-context"
                     onClick={() => setContextOpen((open) => !open)}
                  >
                     {contextOpen ? "Hide context" : "Show context"}
                  </Button>
               </div>
            </div>

            <div className="investigation-workspace-meta" aria-label="Investigation identity">
               <span>Claimed {formatDateTime(data.assignment.claimed_at)}</span>
               <span>
                  {data.assignment.claimed_by?.username
                     ? "Claimed by @" + data.assignment.claimed_by.username
                     : "Claimed by organization"}
               </span>
               <span>{formatLabel(claim.claim_type)}</span>
            </div>

            <InvestigationContextLinks claim={claim} />
         </header>

         <div className={`investigation-workspace-layout ${contextOpen ? "has-context" : ""}`}>
            <main className="investigation-workspace-main">
               {isRefreshing ? (
                  <div className="investigation-refresh-status" role="status" aria-live="polite">
                     <Icons name="loader" size={15} className="investigation-workspace-spinner" />
                     Refreshing investigation state…
                  </div>
               ) : refreshError ? (
                  <div className="investigation-refresh-error" role="alert">
                     <Icons name="alert-circle" size={16} />
                     <span>{refreshError}</span>
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        onClick={() => setRequestVersion((value) => value + 1)}
                     >
                        Retry
                     </Button>
                  </div>
               ) : null}

               <section ref={stageRef} className="investigation-stage" aria-labelledby="investigation-stage-heading">
                  <div className="investigation-stage-heading">
                     <span className="investigation-stage-icon" aria-hidden="true">
                        <Icons name={STATE_ICON[state.code] || "activity"} size={20} />
                     </span>
                     <div>
                        <span className="investigation-section-label">Current stage</span>
                        <h2 id="investigation-stage-heading">{state.label || "Investigation"}</h2>
                        <p>{state.detail}</p>
                     </div>
                  </div>

                  {pending.length > 0 ? (
                     <div className="investigation-pending">
                        <h3>What still needs to happen</h3>
                        <ul>
                           {pending.map((item) => (
                              <li key={item.code}>
                                 <Icons name="clock" size={15} aria-hidden="true" />
                                 <span>
                                    {item.detail}
                                    {Number.isInteger(item.count) && item.count > 0 ? " (" + item.count + ")" : ""}
                                 </span>
                              </li>
                           ))}
                        </ul>
                     </div>
                  ) : null}

                  <div className="investigation-next-action">
                     <div>
                        <span className="investigation-section-label">Next action</span>
                        <strong>
                           {progressAction
                              ? progressAction.label
                              : state.code === "ACTIVE_NO_EVIDENCE"
                                ? "Waiting for evidence"
                                : "Waiting for the next authorized action"}
                        </strong>
                        <p>
                           {progressAction
                              ? "Continue this investigation without leaving its workflow context."
                              : "TruthLens will keep this investigation active. Another authorized role or a new evidence submission may be required before it can progress."}
                        </p>
                     </div>
                     {progressAction && (isInlineGuidedAction(progressAction) || progressDestination) ? (
                        <Button
                           variant="primary"
                           density="comfortable"
                           trailingIcon={<Icons name="arrow-right" size={15} />}
                           onClick={() => handleProgressAction(progressAction)}
                        >
                           {progressAction.label}
                        </Button>
                     ) : null}
                  </div>
               </section>

               {guidedAction ? (
                  <section
                     ref={guidedWorkRef}
                     className="investigation-guided-work"
                     aria-labelledby="investigation-guided-work-heading"
                  >
                     <div className="investigation-guided-work-heading">
                        <div>
                           <span className="investigation-section-label">Working in this investigation</span>
                           <h2 id="investigation-guided-work-heading">
                              {guidedAction.code === "REVIEW_EVIDENCE" ? "Evidence review" : "Adjudication"}
                           </h2>
                           <p>
                              The work item below belongs to this investigation. Completing it refreshes the persisted
                              investigation state without sending you to a separate queue.
                           </p>
                        </div>
                        <Button
                           type="button"
                           variant="secondary"
                           density="compact"
                           leadingIcon={<Icons name="x" size={14} />}
                           onClick={handleContinueInvestigation}
                        >
                           Close work surface
                        </Button>
                     </div>

                     {guidedAction.code === "REVIEW_EVIDENCE" ? (
                        <EvidenceReviewPanel
                           key={`guided-evidence-${guidedAction.target?.id}`}
                           organizationId={organizationId}
                           organizationName={data.organization.name}
                           canReviewEvidence
                           initialCaseId={guidedAction.target?.id}
                           guidedMode
                           onWorkflowChanged={handleGuidedWorkflowChanged}
                           onReturnToInvestigation={handleContinueInvestigation}
                        />
                     ) : (
                        <AdjudicationReviewPanel
                           key={`guided-adjudication-${guidedAction.target?.id}`}
                           organizationId={organizationId}
                           organizationName={data.organization.name}
                           canAdjudicate
                           initialCaseId={guidedAction.target?.id}
                           guidedMode
                           onWorkflowChanged={handleGuidedWorkflowChanged}
                           onReturnToInvestigation={handleContinueInvestigation}
                        />
                     )}
                  </section>
               ) : null}

               <section className="investigation-progress" aria-labelledby="investigation-progress-heading">
                  <div className="investigation-section-heading">
                     <div>
                        <span className="investigation-section-label">Investigation status</span>
                        <h2 id="investigation-progress-heading">What has happened so far</h2>
                     </div>
                     <span>High-level status · cases may return for additional review</span>
                  </div>

                  <div className="investigation-progress-grid">
                     <article>
                        <span>Evidence</span>
                        <strong>
                           {evidence.total
                              ? String(evidence.verified || 0) +
                                " reviewed · " +
                                String(evidence.unreviewed || 0) +
                                " waiting"
                              : "No evidence yet"}
                        </strong>
                        <small>
                           {evidence.rejected || 0} rejected · {evidence.active_case_count || 0} active review cases
                        </small>
                     </article>

                     <article>
                        <span>Adjudication</span>
                        <strong>
                           {adjudication.current_decision
                              ? "Decision recorded"
                              : adjudication.case
                                ? formatLabel(adjudication.case.status)
                                : "Not started"}
                        </strong>
                        <small>
                           {adjudication.current_decision
                              ? "Human decision revision " + adjudication.current_decision.revision_number
                              : "No authoritative human decision is displayed unless attributable."}
                        </small>
                     </article>

                     <article>
                        <span>Publication</span>
                        <strong>{publication ? formatLabel(publication.publication_status) : "Not started"}</strong>
                        <small>
                           {publication
                              ? "Last updated " + formatDateTime(publication.updated_at)
                              : "Publication work begins only after attributable adjudication."}
                        </small>
                     </article>
                  </div>
               </section>

               {Array.isArray(data.actor_blockers) && data.actor_blockers.length > 0 ? (
                  <section className="investigation-role-notes" aria-labelledby="investigation-role-notes-heading">
                     <h2 id="investigation-role-notes-heading">Action requirements</h2>
                     <ul>
                        {data.actor_blockers.map((blocker, index) => (
                           <li key={(blocker?.code || "blocker") + "-" + index}>
                              <strong>{formatLabel(blocker?.code || "Requirement")}</strong>
                              <span>{blocker?.detail || "This action is not currently available."}</span>
                           </li>
                        ))}
                     </ul>
                  </section>
               ) : null}
            </main>

            {contextOpen ? (
               <aside
                  id="investigation-workspace-context"
                  className="investigation-workspace-context"
                  aria-label="Investigation context"
               >
                  <div className="investigation-context-summary">
                     <span className="investigation-section-label">Context</span>
                     <h2>Evidence & provenance</h2>
                     <p>
                        Review supporting context without losing the investigation you are working on. Automated
                        analysis remains non-authoritative.
                     </p>
                  </div>

                  <VerificationIntelligencePanel organizationId={organizationId} claimId={claim.id} />
               </aside>
            ) : null}
         </div>
      </div>
   );
}

export default InvestigationWorkspacePage;
