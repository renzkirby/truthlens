import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import Icons from "../Icons.jsx";

import { resolveApiEndpoint } from "../../utils/api";

import { VERDICT_CONFIG } from "../../utils/constants";

import "./VerificationIntakePanel.css";

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

function formatConsensus(value) {
   const number = Number(value);

   if (!Number.isFinite(number)) {
      return "Not available";
   }

   return `${number.toFixed(1)}%`;
}

function getVerdictMeta(verdict) {
   const normalizedVerdict = String(verdict || "UNVERIFIED").toUpperCase();

   return VERDICT_CONFIG[normalizedVerdict] ?? VERDICT_CONFIG.UNVERIFIED;
}

function getClaimSourceUrl(claim) {
   return claim?.url_link || claim?.source_link || null;
}

function VerificationIntakePanel({ organizationId, organizationName }) {
   const { authFetch } = useAuth();

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

   const handleClaim = async (assignmentId) => {
      if (!assignmentId || !organizationId) {
         return;
      }

      setClaimingId(assignmentId);
      setErrorMessage("");
      setNotice("");

      try {
         await authFetch(resolveApiEndpoint("VERIFICATION_ASSIGNMENT_CLAIM", assignmentId), {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: {
               organization_id: String(organizationId),
            },
         });

         setConfirmingId(null);

         setNotice(
            `Investigation claimed for ${
               organizationName || "your organization"
            }. It is now part of the organization workload.`,
         );

         refreshFromFirstPage();
      } catch (error) {
         setConfirmingId(null);

         if (error?.status === 409) {
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

   return (
      <div className="verification-intake">
         <div className="intake-toolbar">
            <div>
               <strong>Available investigations</strong>

               <span>{intake.count} waiting for professional verification</span>
            </div>

            <button type="button" className="intake-refresh-button" onClick={refreshCurrentPage} disabled={loading}>
               <Icons name="refresh-cw" size={15} />
               Refresh
            </button>
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
               </div>
            </div>
         )}

         {loading ? (
            <div className="intake-loading" aria-live="polite">
               <Icons name="loader" size={20} className="intake-spinner" />

               <span>Loading available investigations...</span>
            </div>
         ) : intake.results.length === 0 && !errorMessage ? (
            <div className="intake-empty-state">
               <Icons name="check-circle" size={26} />

               <h3>Intake is clear</h3>

               <p>There are currently no available investigations waiting to be claimed.</p>
            </div>
         ) : !errorMessage ? (
            <>
               <div className="intake-list">
                  {intake.results.map((assignment) => {
                     const claim = assignment?.claim ?? {};

                     const verdictMeta = getVerdictMeta(claim.ai_verdict);

                     const sourceUrl = getClaimSourceUrl(claim);

                     const isConfirming = confirmingId === assignment.id;

                     const isClaiming = claimingId === assignment.id;

                     return (
                        <article key={assignment.id} className="intake-card">
                           <div className="intake-card-top">
                              <div className="intake-card-labels">
                                 <span className="intake-status-badge">Available</span>

                                 <span className="intake-type-badge">{formatLabel(claim.claim_type)}</span>
                              </div>

                              <span className="intake-updated">Updated {formatDateTime(claim.last_updated)}</span>
                           </div>

                           <h3 className="intake-claim-text">{claim.context_text || "Claim text unavailable"}</h3>

                           {claim.ai_summary && <p className="intake-ai-summary">{claim.ai_summary}</p>}

                           <div className="intake-signals">
                              <div>
                                 <span className="intake-signal-label">AI assessment</span>

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
                              </div>

                              <div>
                                 <span className="intake-signal-label">Community consensus</span>

                                 <strong>{formatConsensus(claim.consensus_score)}</strong>
                              </div>

                              <div>
                                 <span className="intake-signal-label">Source type</span>

                                 <strong>{formatLabel(claim.source_type)}</strong>
                              </div>
                           </div>

                           <div className="intake-card-footer">
                              <div className="intake-source-area">
                                 {sourceUrl ? (
                                    <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                                       <Icons name="external-link" size={14} />
                                       View source
                                    </a>
                                 ) : (
                                    <span>No external source attached</span>
                                 )}
                              </div>

                              {isConfirming ? (
                                 <div className="intake-confirm">
                                    <span>
                                       Claim for <strong>{organizationName}</strong>?
                                    </span>

                                    <button
                                       type="button"
                                       className="intake-button secondary"
                                       disabled={isClaiming}
                                       onClick={() => setConfirmingId(null)}
                                    >
                                       Cancel
                                    </button>

                                    <button
                                       type="button"
                                       className="intake-button primary"
                                       disabled={isClaiming}
                                       onClick={() => handleClaim(assignment.id)}
                                    >
                                       {isClaiming ? (
                                          <>
                                             <Icons name="loader" size={14} className="intake-spinner" />
                                             Claiming...
                                          </>
                                       ) : (
                                          "Confirm claim"
                                       )}
                                    </button>
                                 </div>
                              ) : (
                                 <button
                                    type="button"
                                    className="intake-button primary"
                                    disabled={Boolean(claimingId)}
                                    onClick={() => setConfirmingId(assignment.id)}
                                 >
                                    <Icons name="inbox" size={15} />
                                    Claim investigation
                                 </button>
                              )}
                           </div>
                        </article>
                     );
                  })}
               </div>

               <div className="intake-pagination">
                  <span>
                     Showing {rangeStart}–{rangeEnd} of {intake.count}
                  </span>

                  <div>
                     <button type="button" disabled={!hasPrevious || loading} onClick={handlePreviousPage}>
                        <Icons name="chevron-left" size={15} />
                        Previous
                     </button>

                     <button type="button" disabled={!hasNext || loading} onClick={handleNextPage}>
                        Next
                        <Icons name="chevron-right" size={15} />
                     </button>
                  </div>
               </div>
            </>
         ) : null}
      </div>
   );
}

export default VerificationIntakePanel;
