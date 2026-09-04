import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import Icons from "../Icons.jsx";

import { resolveApiEndpoint } from "../../utils/api";

import "./OrganizationWorkloadPanel.css";

const PAGE_SIZE = 10;

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

function formatLabel(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function OrganizationWorkloadPanel({ organizationId, organizationName, canReleaseInvestigation = false }) {
   const { authFetch } = useAuth();

   const [offset, setOffset] = useState(0);

   const [requestVersion, setRequestVersion] = useState(0);

   const [workload, setWorkload] = useState({
      count: 0,
      results: [],
   });

   const [loading, setLoading] = useState(true);

   const [errorMessage, setErrorMessage] = useState("");

   const [notice, setNotice] = useState("");

   const [actionError, setActionError] = useState("");

   const [confirmingReleaseId, setConfirmingReleaseId] = useState(null);

   const [releasingId, setReleasingId] = useState(null);

   const workloadUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      const query = new URLSearchParams({
         organization_id: String(organizationId),
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });

      return `${resolveApiEndpoint("VERIFICATION_WORKLOAD")}?${query.toString()}`;
   }, [organizationId, offset]);

   useEffect(() => {
      if (!workloadUrl) {
         return undefined;
      }

      let cancelled = false;

      authFetch(workloadUrl, {
         method: "GET",
      })
         .then((data) => {
            if (cancelled) {
               return;
            }

            setWorkload({
               count: Number(data?.count ?? 0),
               results: Array.isArray(data?.results) ? data.results : [],
            });

            setErrorMessage("");
         })
         .catch((error) => {
            if (cancelled) {
               return;
            }

            setErrorMessage(error?.message || "Unable to load organization workload.");

            setWorkload({
               count: 0,
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
   }, [authFetch, workloadUrl, requestVersion]);

   const refresh = () => {
      setLoading(true);
      setErrorMessage("");
      setNotice("");
      setActionError("");
      setConfirmingReleaseId(null);

      setRequestVersion((current) => current + 1);
   };

   const handlePreviousPage = () => {
      setLoading(true);
      setErrorMessage("");
      setNotice("");
      setActionError("");
      setConfirmingReleaseId(null);

      setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_SIZE));
   };

   const handleNextPage = () => {
      setLoading(true);
      setErrorMessage("");
      setNotice("");
      setActionError("");
      setConfirmingReleaseId(null);

      setOffset((currentOffset) => currentOffset + PAGE_SIZE);
   };

   if (loading) {
      return (
         <div className="workload-state">
            <Icons name="loader" size={21} className="workload-spinner" />

            <span>Loading organization workload...</span>
         </div>
      );
   }

   if (errorMessage) {
      return (
         <div className="workload-error" role="alert">
            <Icons name="alert-circle" size={18} />

            <div>
               <strong>Workload unavailable</strong>

               <span>{errorMessage}</span>
            </div>
         </div>
      );
   }

   const hasPrevious = offset > 0;

   const hasNext = offset + workload.results.length < workload.count;

   const rangeStart = workload.count === 0 ? 0 : offset + 1;

   const rangeEnd = Math.min(offset + workload.results.length, workload.count);

   const removeReleasedAssignmentFromWorkload = (assignmentId) => {
      const remainingResults = workload.results.filter((assignment) => assignment.id !== assignmentId);

      setWorkload((current) => ({
         ...current,
         count: Math.max(0, Number(current.count ?? 0) - 1),
         results: current.results.filter((assignment) => assignment.id !== assignmentId),
      }));

      // If releasing the final investigation on
      // a later page makes that page invalid,
      // move to the previous valid page.
      if (offset > 0 && remainingResults.length === 0) {
         setLoading(true);

         setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_SIZE));
      }
   };

   const handleRelease = async (assignmentId) => {
      if (!assignmentId || !canReleaseInvestigation) {
         return;
      }

      setReleasingId(assignmentId);
      setActionError("");
      setNotice("");

      try {
         await authFetch(resolveApiEndpoint("VERIFICATION_ASSIGNMENT_RELEASE", assignmentId), {
            method: "POST",
         });

         setConfirmingReleaseId(null);

         removeReleasedAssignmentFromWorkload(assignmentId);

         setNotice(
            `Investigation released by ${
               organizationName || "your organization"
            }. It has returned to shared Verification Intake.`,
         );
      } catch (error) {
         setConfirmingReleaseId(null);

         if (error?.status === 409) {
            setActionError(error?.message || "This investigation can no longer be released.");

            // Reconcile silently with the server.
            // Do not replace the whole workload with
            // another loading screen.
            setRequestVersion((current) => current + 1);
         } else {
            setActionError(error?.message || "Unable to release this investigation.");
         }
      } finally {
         setReleasingId(null);
      }
   };

   return (
      <div className="organization-workload">
         <div className="workload-toolbar">
            <div>
               <strong>Active investigations</strong>

               <span>
                  {workload.count} currently owned by {organizationName || "this organization"}
               </span>
            </div>

            <button type="button" onClick={refresh}>
               <Icons name="refresh-cw" size={15} />
               Refresh
            </button>
         </div>

         {notice && (
            <div className="workload-notice" role="status" aria-live="polite">
               <Icons name="info" size={17} />

               <span>{notice}</span>
            </div>
         )}

         {actionError && (
            <div className="workload-action-error" role="alert">
               <Icons name="alert-circle" size={17} />

               <div>
                  <strong>Release unavailable</strong>

                  <span>{actionError}</span>
               </div>
            </div>
         )}

         {workload.results.length === 0 ? (
            <div className="workload-state">
               <Icons name="inbox" size={25} />

               <h3>No active investigations</h3>

               <p>
                  Claimed investigations will appear here once your organization accepts work from Verification Intake.
               </p>
            </div>
         ) : (
            <>
               <div className="workload-list">
                  {workload.results.map((assignment) => {
                     const claim = assignment?.claim ?? {};
                     const isConfirmingRelease = confirmingReleaseId === assignment.id;

                     const isReleasing = releasingId === assignment.id;

                     return (
                        <article key={assignment.id} className="workload-card">
                           <div className="workload-card-header">
                              <div>
                                 <span className="workload-status">Active</span>

                                 <span className="workload-type">{formatLabel(claim.claim_type)}</span>
                              </div>

                              <span>Claimed {formatDateTime(assignment.claimed_at)}</span>
                           </div>

                           <h3>{claim.context_text || "Claim text unavailable"}</h3>

                           <div className="workload-meta">
                              <div>
                                 <span>Claimed by</span>

                                 <strong>
                                    {assignment?.claimed_by?.username
                                       ? `@${assignment.claimed_by.username}`
                                       : "Unknown"}
                                 </strong>
                              </div>

                              <div>
                                 <span>AI assessment</span>

                                 <strong>{formatLabel(claim.ai_verdict || "UNVERIFIED")}</strong>
                              </div>

                              <div>
                                 <span>Last updated</span>

                                 <strong>{formatDateTime(claim.last_updated)}</strong>
                              </div>
                           </div>
                           {canReleaseInvestigation && (
                              <div className="workload-card-actions">
                                 {isConfirmingRelease ? (
                                    <div className="workload-release-confirm">
                                       <div className="workload-release-warning">
                                          <Icons name="alert-triangle" size={17} />

                                          <span>
                                             Release this investigation back to shared intake? This is only permitted
                                             before authoritative review work begins.
                                          </span>
                                       </div>

                                       <div className="workload-release-controls">
                                          <button
                                             type="button"
                                             className="workload-action-button secondary"
                                             disabled={isReleasing}
                                             onClick={() => setConfirmingReleaseId(null)}
                                          >
                                             Cancel
                                          </button>

                                          <button
                                             type="button"
                                             className="workload-action-button primary"
                                             disabled={isReleasing}
                                             onClick={() => handleRelease(assignment.id)}
                                          >
                                             {isReleasing ? (
                                                <>
                                                   <Icons name="loader" size={14} className="workload-spinner" />
                                                   Releasing...
                                                </>
                                             ) : (
                                                "Confirm release"
                                             )}
                                          </button>
                                       </div>
                                    </div>
                                 ) : (
                                    <button
                                       type="button"
                                       className="workload-release-button"
                                       disabled={Boolean(releasingId)}
                                       onClick={() => setConfirmingReleaseId(assignment.id)}
                                    >
                                       <Icons name="logout" size={15} />
                                       Release investigation
                                    </button>
                                 )}
                              </div>
                           )}
                        </article>
                     );
                  })}
               </div>

               <div className="workload-pagination">
                  <span>
                     Showing {rangeStart}–{rangeEnd} of {workload.count}
                  </span>

                  <div>
                     <button type="button" disabled={!hasPrevious} onClick={handlePreviousPage}>
                        <Icons name="chevron-left" size={15} />
                        Previous
                     </button>

                     <button type="button" disabled={!hasNext} onClick={handleNextPage}>
                        Next
                        <Icons name="chevron-right" size={15} />
                     </button>
                  </div>
               </div>
            </>
         )}
      </div>
   );
}

export default OrganizationWorkloadPanel;
