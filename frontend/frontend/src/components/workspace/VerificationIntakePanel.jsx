import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";

import { resolveApiEndpoint } from "../../utils/api";
import { showWorkspaceSuccess, WORKSPACE_LONG_TOAST_DURATION } from "../../utils/workspaceToast";

import { VERDICT_CONFIG } from "../../utils/constants";

import "./VerificationIntakePanel.css";
import InvestigationContextLinks from "./InvestigationContextLinks.jsx";

const PAGE_SIZE = 10;

function formatLabel(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDateTime(value) {
   if (!value) {
      return "Unknown";
   }

   const date = new Date(value);

   if (Number.isNaN(date.getTime())) {
      return "Unknown";
   }

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function formatConfidence(value) {
   if (value === null || value === undefined || value === "") {
      return null;
   }

   const number = Number(value);

   if (!Number.isFinite(number)) {
      return null;
   }

   return `${Math.round(number)}%`;
}

function getVerdictMeta(verdict) {
   if (!verdict) {
      return null;
   }

   const normalizedVerdict = String(verdict).toUpperCase();

   return VERDICT_CONFIG[normalizedVerdict] ?? null;
}

function formatAvailableInvestigations(count) {
   const normalizedCount = Number(count ?? 0);

   return `${normalizedCount} available ${normalizedCount === 1 ? "investigation" : "investigations"}`;
}

function VerificationIntakePanel({ organizationId, organizationName, onInvestigationClaimed }) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();

   const [offset, setOffset] = useState(0);

   const [requestVersion, setRequestVersion] = useState(0);

   const [intake, setIntake] = useState({
      count: 0,
      limit: PAGE_SIZE,
      offset: 0,
      results: [],
   });

   const [loading, setLoading] = useState(true);

   const [errorMessage, setErrorMessage] = useState("");

   const [notice, setNotice] = useState("");

   const [confirmingId, setConfirmingId] = useState(null);

   const [claimingId, setClaimingId] = useState(null);

   const confirmCancelRef = useRef(null);
   const claimTriggerRefs = useRef(new Map());

   useEffect(() => {
      if (!confirmingId) {
         return undefined;
      }

      const frame = window.requestAnimationFrame(() => {
         confirmCancelRef.current?.focus();
      });

      return () => window.cancelAnimationFrame(frame);
   }, [confirmingId]);

   const intakeUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      const query = new URLSearchParams({
         organization_id: String(organizationId),
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });

      return `${resolveApiEndpoint("VERIFICATION_INTAKE")}?${query.toString()}`;
   }, [organizationId, offset]);

   useEffect(() => {
      if (!intakeUrl) {
         return undefined;
      }

      let cancelled = false;

      authFetch(intakeUrl, {
         method: "GET",
      })
         .then((data) => {
            if (cancelled) {
               return;
            }

            setIntake({
               count: Number(data?.count ?? 0),
               limit: Number(data?.limit ?? PAGE_SIZE),
               offset: Number(data?.offset ?? offset),
               results: Array.isArray(data?.results) ? data.results : [],
            });

            setErrorMessage("");
         })
         .catch((error) => {
            if (cancelled) {
               return;
            }

            setErrorMessage(error?.message || "Unable to load verification intake.");

            setIntake({
               count: 0,
               limit: PAGE_SIZE,
               offset,
               results: [],
            });
         })
         .finally(() => {
            if (!cancelled) {
               setLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, intakeUrl, offset, requestVersion]);

   const refreshCurrentPage = () => {
      setLoading(true);
      setErrorMessage("");
      setNotice("");
      setConfirmingId(null);

      setRequestVersion((current) => current + 1);
   };

   const refreshFromFirstPage = () => {
      setLoading(true);
      setErrorMessage("");
      setConfirmingId(null);

      if (offset === 0) {
         setRequestVersion((current) => current + 1);

         return;
      }

      setOffset(0);
   };

   const handlePreviousPage = () => {
      const nextOffset = Math.max(0, offset - PAGE_SIZE);

      setLoading(true);
      setErrorMessage("");
      setNotice("");
      setConfirmingId(null);
      setOffset(nextOffset);
   };

   const handleNextPage = () => {
      setLoading(true);
      setErrorMessage("");
      setNotice("");
      setConfirmingId(null);

      setOffset(offset + PAGE_SIZE);
   };

   const removeClaimedAssignmentFromIntake = (assignmentId) => {
      const remainingResults = intake.results.filter((assignment) => assignment.id !== assignmentId);

      setIntake((current) => ({
         ...current,
         count: Math.max(0, Number(current.count ?? 0) - 1),
         results: current.results.filter((assignment) => assignment.id !== assignmentId),
      }));

      // If the claimed investigation was the only
      // item on a later page, return to the previous
      // valid page instead of displaying a false
      // "Intake is clear" state.
      if (offset > 0 && remainingResults.length === 0) {
         setLoading(true);

         setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_SIZE));
      }
   };

   const closeClaimConfirmation = (assignmentId) => {
      setConfirmingId(null);

      window.requestAnimationFrame(() => {
         claimTriggerRefs.current.get(assignmentId)?.focus();
      });
   };

   const handleClaim = async (assignmentId) => {
      if (!assignmentId || !organizationId) {
         return;
      }

      setClaimingId(assignmentId);
      setErrorMessage("");
      setNotice("");

      try {
         const claimedAssignment = await authFetch(resolveApiEndpoint("VERIFICATION_ASSIGNMENT_CLAIM", assignmentId), {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: {
               organization_id: String(organizationId),
            },
         });

         setConfirmingId(null);

         removeClaimedAssignmentFromIntake(assignmentId);

         showWorkspaceSuccess(addToast, {
            title: "Investigation claimed",
            message: `Assigned to ${organizationName || "your organization"}. Opening the investigation workspace.`,
         });
         onInvestigationClaimed?.(claimedAssignment);
      } catch (error) {
         if (error?.status === 409) {
            setConfirmingId(null);
            setNotice(
               "This investigation was claimed by another organization before your request completed. The intake has been refreshed.",
            );

            refreshFromFirstPage();
         } else {
            setErrorMessage(error?.message || "Unable to claim this investigation.");
         }
      } finally {
         setClaimingId(null);
      }
   };

   if (!organizationId) {
      return (
         <div className="intake-empty-state">
            <Icons name="inbox" size={24} />

            <h3>No organization selected</h3>

            <p>Select a partner organization before viewing verification intake.</p>
         </div>
      );
   }

   const hasPrevious = offset > 0;

   const hasNext = offset + intake.results.length < intake.count;

   const rangeStart = intake.count === 0 ? 0 : offset + 1;

   const rangeEnd = Math.min(offset + intake.results.length, intake.count);

   const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
   const totalPages = Math.max(1, Math.ceil(intake.count / PAGE_SIZE));

   return (
      <div className="verification-intake" aria-busy={loading ? "true" : undefined}>
         <div className="intake-overview">
            <div>
               <strong>{formatAvailableInvestigations(intake.count)}</strong>
               <p>Choose new community investigations for {organizationName || "your organization"} to verify.</p>
            </div>

            <Button
               type="button"
               variant="secondary"
               density="compact"
               className="intake-refresh-action"
               leadingIcon={<Icons name="refresh-cw" size={14} />}
               onClick={refreshCurrentPage}
               disabled={loading}
            >
               Refresh
            </Button>
         </div>

         <div className="intake-guidance" role="note">
            <Icons name="info" size={16} />
            <span>
               Claiming assigns the investigation to your organization. AI assessment is context only and does not
               represent an institutional verdict.
            </span>
         </div>

         {notice && (
            <div className="intake-notice" role="status" aria-live="polite">
               <Icons name="info" size={17} />
               <span>{notice}</span>
            </div>
         )}

         {errorMessage && (
            <div className="intake-error" role="alert">
               <Icons name="alert-circle" size={17} />
               <div>
                  <strong>Intake unavailable</strong>
                  <span>{errorMessage}</span>
                  <Button
                     type="button"
                     variant="secondary"
                     density="compact"
                     leadingIcon={<Icons name="refresh-cw" size={14} />}
                     onClick={refreshCurrentPage}
                     disabled={loading}
                  >
                     Try again
                  </Button>
               </div>
            </div>
         )}

         {loading ? (
            <div className="intake-loading" role="status" aria-live="polite">
               <Icons name="loader" size={20} className="intake-spinner" />
               <span>Loading available investigations…</span>
            </div>
         ) : intake.results.length === 0 && !errorMessage ? (
            <div className="intake-empty-state">
               <Icons name="check-circle" size={26} />
               <h3>Intake is clear</h3>
               <p>There are currently no available investigations waiting to be claimed.</p>
            </div>
         ) : !errorMessage ? (
            <>
               <div className="intake-list-heading">
                  <span>
                     Showing {rangeStart}–{rangeEnd} of {intake.count}
                  </span>
                  <span>Review the claim context before assigning work to your organization.</span>
               </div>

               <ul className="intake-list">
                  {intake.results.map((assignment) => {
                     const claim = assignment?.claim ?? {};
                     const claimText = claim.context_text || "Claim text unavailable";
                     const hasLongClaimText = claimText.length > 360;
                     const verdictMeta = getVerdictMeta(claim.ai_verdict);
                     const confidence = formatConfidence(claim.consensus_score);
                     const evidenceCount = Number(assignment.evidence_count || 0);
                     const isConfirming = confirmingId === assignment.id;
                     const isClaiming = claimingId === assignment.id;
                     const claimHeadingId = `intake-claim-${assignment.id}`;
                     const confirmationId = `intake-confirm-${assignment.id}`;

                     return (
                        <li key={assignment.id} className="intake-list-item">
                           <article className="intake-item" aria-labelledby={claimHeadingId}>
                              <div className="intake-item-main">
                                 <div className="intake-item-kicker">
                                    <span className="intake-status-badge">Available</span>
                                    <span className="intake-type-badge">{formatLabel(claim.claim_type)}</span>
                                 </div>

                                 <h3 id={claimHeadingId} className={`intake-claim-text ${hasLongClaimText ? "is-truncated" : ""}`}>
                                    {claimText}
                                 </h3>

                                 {hasLongClaimText ? (
                                    <details className="intake-claim-details">
                                       <summary>Show full claim text</summary>
                                       <p>{claimText}</p>
                                    </details>
                                 ) : null}

                                 {claim.ai_summary ? <p className="intake-ai-summary">{claim.ai_summary}</p> : null}

                                 <dl className="intake-signals">
                                    <div className="intake-evidence-signal">
                                       <dt>Submitted evidence</dt>
                                       <dd>
                                          {evidenceCount} {evidenceCount === 1 ? "item" : "items"}
                                       </dd>
                                    </div>

                                    <div>
                                       <dt>AI assessment</dt>
                                       <dd>
                                          {verdictMeta ? (
                                             <span
                                                className="intake-verdict"
                                                style={{
                                                   color: verdictMeta.color,
                                                   background: verdictMeta.bg,
                                                   borderColor: verdictMeta.border,
                                                }}
                                             >
                                                {verdictMeta.label}
                                             </span>
                                          ) : claim.ai_verdict ? (
                                             formatLabel(claim.ai_verdict)
                                          ) : (
                                             "No AI assessment"
                                          )}
                                       </dd>
                                    </div>

                                    {confidence ? (
                                       <div>
                                          <dt>AI confidence</dt>
                                          <dd>{confidence}</dd>
                                       </div>
                                    ) : null}

                                    <div>
                                       <dt>Source</dt>
                                       <dd>{claim.source_type ? formatLabel(claim.source_type) : "Not recorded"}</dd>
                                    </div>
                                 </dl>

                                 <InvestigationContextLinks claim={claim} />
                              </div>

                              <div className="intake-item-actions">
                                 {claim.last_updated ? (
                                    <time className="intake-updated" dateTime={claim.last_updated}>
                                       Updated {formatDateTime(claim.last_updated)}
                                    </time>
                                 ) : (
                                    <span className="intake-updated">Updated date unavailable</span>
                                 )}

                                 {!isConfirming ? (
                                    <Button
                                       ref={(node) => {
                                          if (node) claimTriggerRefs.current.set(assignment.id, node);
                                          else claimTriggerRefs.current.delete(assignment.id);
                                       }}
                                       type="button"
                                       variant="primary"
                                       density="standard"
                                       className="intake-claim-action"
                                       trailingIcon={<Icons name="arrow-right" size={15} />}
                                       aria-expanded="false"
                                       aria-controls={confirmationId}
                                       disabled={Boolean(claimingId)}
                                       onClick={() => setConfirmingId(assignment.id)}
                                    >
                                       Claim investigation
                                    </Button>
                                 ) : null}
                              </div>

                              {isConfirming ? (
                                 <div
                                    id={confirmationId}
                                    className="intake-confirm"
                                    role="group"
                                    aria-label="Confirm investigation claim"
                                 >
                                    <div className="intake-confirm-copy">
                                       <Icons name="inbox" size={17} />
                                       <div>
                                          <strong>Claim this investigation?</strong>
                                          <span>
                                             It will move from shared intake to {organizationName || "your organization"}’s
                                             active Investigations queue.
                                          </span>
                                       </div>
                                    </div>

                                    <div className="intake-confirm-actions">
                                       <Button
                                          ref={confirmCancelRef}
                                          type="button"
                                          variant="secondary"
                                          density="compact"
                                          disabled={isClaiming}
                                          onClick={() => closeClaimConfirmation(assignment.id)}
                                       >
                                          Cancel
                                       </Button>

                                       <Button
                                          type="button"
                                          variant="primary"
                                          density="compact"
                                          loading={isClaiming}
                                          loadingLabel="Claiming…"
                                          disabled={isClaiming}
                                          onClick={() => handleClaim(assignment.id)}
                                       >
                                          Confirm claim
                                       </Button>
                                    </div>
                                 </div>
                              ) : null}
                           </article>
                        </li>
                     );
                  })}
               </ul>

               <div className="intake-pagination">
                  <span>
                     Page {currentPage} of {totalPages}
                  </span>

                  <div className="intake-pagination-controls">
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        leadingIcon={<Icons name="chevron-left" size={15} />}
                        disabled={!hasPrevious || loading}
                        onClick={handlePreviousPage}
                     >
                        Previous
                     </Button>

                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        trailingIcon={<Icons name="chevron-right" size={15} />}
                        disabled={!hasNext || loading}
                        onClick={handleNextPage}
                     >
                        Next
                     </Button>
                  </div>
               </div>
            </>
         ) : null}
      </div>
   );
}

export default VerificationIntakePanel;
