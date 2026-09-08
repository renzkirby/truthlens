import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import Icons from "../Icons.jsx";

import "./AdjudicationReviewPanel.css";

const PAGE_SIZE = 20;

const STATUS_OPTIONS = [
   { value: "", label: "Active work" },
   { value: "OPEN", label: "Open" },
   { value: "IN_REVIEW", label: "In review" },
   { value: "ESCALATED", label: "Escalated" },
   { value: "REOPENED", label: "Reopened" },
   { value: "RESOLVED", label: "Resolved" },
   { value: "CANCELLED", label: "Cancelled" },
];

const PRIORITY_OPTIONS = [
   { value: "", label: "All priorities" },
   { value: "LOW", label: "Low" },
   { value: "NORMAL", label: "Normal" },
   { value: "HIGH", label: "High" },
   { value: "URGENT", label: "Urgent" },
];

const EMPTY_QUEUE_COPY = {
   RESOLVED: {
      heading: "No resolved Adjudication cases",
      body: "No resolved cases match the selected priority for this organization.",
   },
   CANCELLED: {
      heading: "No cancelled Adjudication cases",
      body: "No cancelled cases match the selected priority for this organization.",
   },
   default: {
      heading: "No Adjudication cases",
      body: "No cases match the selected queue filters for this organization.",
   },
};

function formatLabel(value, fallback = "Unavailable") {
   if (!value) {
      return fallback;
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDateTime(value, fallback = "Not recorded") {
   if (!value) {
      return fallback;
   }

   const date = new Date(value);

   if (Number.isNaN(date.getTime())) {
      return fallback;
   }

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function FormattedDateTime({ value, fallback = "Not recorded" }) {
   const formattedValue = formatDateTime(value, fallback);
   const date = value ? new Date(value) : null;

   if (!date || Number.isNaN(date.getTime())) {
      return formattedValue;
   }

   return <time dateTime={date.toISOString()}>{formattedValue}</time>;
}

function formatCaseReference(caseId) {
   return String(caseId || "").slice(0, 8);
}

function getClaimContext(caseItem) {
   return caseItem?.claim?.context_text || "Claim context unavailable";
}

function getAuthIdentity(user, token) {
   if (!token) {
      return "session:anonymous";
   }

   try {
      const encodedPayload = token.split(".")[1];
      const normalizedPayload = encodedPayload.replaceAll("-", "+").replaceAll("_", "/");
      const paddedPayload = normalizedPayload.padEnd(Math.ceil(normalizedPayload.length / 4) * 4, "=");
      const payload = JSON.parse(window.atob(paddedPayload));
      const tokenUserId = payload?.user_id ?? payload?.sub;

      if (tokenUserId !== undefined && tokenUserId !== null) {
         return `user:${tokenUserId}`;
      }
   } catch {
      // Fall through to the authenticated user or opaque-token identity.
   }

   if (user?.id !== undefined && user?.id !== null) {
      return `user:${user.id}:token:${token}`;
   }

   return `token:${token}`;
}

function normalizeNonnegativeNumber(value, fallback = 0) {
   const number = Number(value);
   return Number.isFinite(number) && number >= 0 ? number : fallback;
}

function AdjudicationReviewContent({
   authFetch,
   organizationId,
   organizationName,
   canAdjudicate,
}) {
   const [statusFilter, setStatusFilter] = useState("");
   const [priorityFilter, setPriorityFilter] = useState("");
   const [offset, setOffset] = useState(0);
   const [queue, setQueue] = useState({
      count: 0,
      limit: PAGE_SIZE,
      offset: 0,
      results: [],
   });
   const [queueLoading, setQueueLoading] = useState(true);
   const [queueError, setQueueError] = useState("");
   const [queueRequestVersion, setQueueRequestVersion] = useState(0);
   const [selectedCaseId, setSelectedCaseId] = useState(null);
   const [authorityError, setAuthorityError] = useState("");

   const mountedRef = useRef(true);
   const authorityGenerationRef = useRef(0);
   const authorityRevokedRef = useRef(false);
   const queueRequestIdRef = useRef(0);
   const selectedCaseIdRef = useRef(null);
   const queueHeadingRef = useRef(null);
   const selectedCaseHeadingRef = useRef(null);
   const authorityErrorRef = useRef(null);
   const focusSelectedCaseRef = useRef(false);
   const focusQueueAfterReturnRef = useRef(false);
   const focusQueueAfterAuthorityRetryRef = useRef(false);

   const isAuthorityGenerationCurrent = useCallback(
      (generation) =>
         mountedRef.current &&
         !authorityRevokedRef.current &&
         authorityGenerationRef.current === generation,
      [],
   );

   const revokeAuthority = useCallback((error) => {
      authorityRevokedRef.current = true;
      authorityGenerationRef.current += 1;
      queueRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusQueueAfterReturnRef.current = false;
      focusQueueAfterAuthorityRetryRef.current = false;

      setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
      setQueueLoading(false);
      setQueueError("");
      setSelectedCaseId(null);
      setAuthorityError(
         error?.status === 401
            ? "Your session is no longer available. Sign in again or retry after authentication is restored."
            : "You no longer have Adjudication permission for this organization.",
      );
   }, []);

   useEffect(() => {
      mountedRef.current = true;

      return () => {
         mountedRef.current = false;
         authorityGenerationRef.current += 1;
         queueRequestIdRef.current += 1;
      };
   }, []);

   const queueUrl = useMemo(() => {
      const query = new URLSearchParams({
         organization_id: organizationId,
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });

      if (statusFilter) {
         query.set("status", statusFilter);
      }

      if (priorityFilter) {
         query.set("priority", priorityFilter);
      }

      return `${resolveApiEndpoint("ADJUDICATION_CASES")}?${query.toString()}`;
   }, [offset, organizationId, priorityFilter, statusFilter]);

   useEffect(() => {
      if (!canAdjudicate || !organizationId) {
         return undefined;
      }

      let cancelled = false;
      const requestId = queueRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      const requestIdentity = queueUrl;
      queueRequestIdRef.current = requestId;

      authFetch(requestIdentity, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               queueRequestIdRef.current !== requestId ||
               !isAuthorityGenerationCurrent(authorityGeneration)
            ) {
               return;
            }

            const count = normalizeNonnegativeNumber(data?.count);
            const results = Array.isArray(data?.results) ? data.results : [];
            const limit = normalizeNonnegativeNumber(data?.limit, PAGE_SIZE) || PAGE_SIZE;
            const responseOffset = normalizeNonnegativeNumber(data?.offset, offset);
            const validOffset = count > 0 ? Math.floor((count - 1) / PAGE_SIZE) * PAGE_SIZE : 0;

            if (results.length === 0 && offset > validOffset) {
               setOffset(validOffset);
               return;
            }

            if (
               selectedCaseIdRef.current &&
               !results.some((caseItem) => String(caseItem?.id) === String(selectedCaseIdRef.current))
            ) {
               selectedCaseIdRef.current = null;
               setSelectedCaseId(null);
            }

            setQueue({ count, limit, offset: responseOffset, results });
            setQueueError("");
            setQueueLoading(false);
         })
         .catch((error) => {
            if (
               cancelled ||
               queueRequestIdRef.current !== requestId ||
               !isAuthorityGenerationCurrent(authorityGeneration)
            ) {
               return;
            }

            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority(error);
               return;
            }

            setQueueError(
               error?.status === 404
                  ? "The Adjudication queue is unavailable for the selected organization."
                  : (error?.message || "Unable to load the Adjudication queue."),
            );
            setQueueLoading(false);
         });

      return () => {
         cancelled = true;
      };
   }, [
      authFetch,
      canAdjudicate,
      isAuthorityGenerationCurrent,
      offset,
      organizationId,
      queueRequestVersion,
      queueUrl,
      revokeAuthority,
   ]);

   useEffect(() => {
      if (authorityError) {
         authorityErrorRef.current?.focus();
         return;
      }

      if (focusQueueAfterAuthorityRetryRef.current) {
         focusQueueAfterAuthorityRetryRef.current = false;
         queueHeadingRef.current?.focus();
      }
   }, [authorityError]);

   useEffect(() => {
      if (selectedCaseId && focusSelectedCaseRef.current) {
         focusSelectedCaseRef.current = false;

         if (window.matchMedia("(max-width: 1180px)").matches) {
            selectedCaseHeadingRef.current?.focus();
         }
         return;
      }

      if (!selectedCaseId && focusQueueAfterReturnRef.current) {
         focusQueueAfterReturnRef.current = false;
         queueHeadingRef.current?.focus();
      }
   }, [selectedCaseId]);

   const clearSelection = ({ restoreQueueFocus = false } = {}) => {
      selectedCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusQueueAfterReturnRef.current = restoreQueueFocus;
      setSelectedCaseId(null);
   };

   const requestQueueRefresh = ({ preserveRows = true } = {}) => {
      if (authorityRevokedRef.current) {
         return;
      }

      queueRequestIdRef.current += 1;
      if (!preserveRows) {
         setQueue({ count: 0, limit: PAGE_SIZE, offset, results: [] });
      }
      setQueueLoading(true);
      setQueueError("");
      setQueueRequestVersion((current) => current + 1);
   };

   const replaceQueueScope = ({ status = statusFilter, priority = priorityFilter, nextOffset = 0 }) => {
      queueRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusQueueAfterReturnRef.current = false;
      setStatusFilter(status);
      setPriorityFilter(priority);
      setOffset(nextOffset);
      setQueue({ count: 0, limit: PAGE_SIZE, offset: nextOffset, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setSelectedCaseId(null);
   };

   const handleSelectCase = (caseId) => {
      if (!caseId || String(caseId) === String(selectedCaseIdRef.current)) {
         return;
      }

      selectedCaseIdRef.current = caseId;
      focusSelectedCaseRef.current = true;
      setSelectedCaseId(caseId);
   };

   const handleAuthorityRetry = () => {
      authorityGenerationRef.current += 1;
      authorityRevokedRef.current = false;
      queueRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusQueueAfterReturnRef.current = false;
      focusQueueAfterAuthorityRetryRef.current = true;
      setAuthorityError("");
      setQueue({ count: 0, limit: PAGE_SIZE, offset, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setSelectedCaseId(null);
      setQueueRequestVersion((current) => current + 1);
   };

   const selectedCase = useMemo(
      () =>
         queue.results.find((caseItem) => String(caseItem?.id) === String(selectedCaseId)) ?? null,
      [queue.results, selectedCaseId],
   );
   const totalPages = Math.max(1, Math.ceil(queue.count / (queue.limit || PAGE_SIZE)));
   const currentPage = queue.count === 0 ? 1 : Math.floor(queue.offset / (queue.limit || PAGE_SIZE)) + 1;
   const hasPreviousPage = offset > 0;
   const hasNextPage = offset + (queue.limit || PAGE_SIZE) < queue.count;
   const emptyCopy = EMPTY_QUEUE_COPY[statusFilter] || EMPTY_QUEUE_COPY.default;
   const activeStatusLabel = STATUS_OPTIONS.find((option) => option.value === statusFilter)?.label || "Active work";

   if (!canAdjudicate || !organizationId) {
      return (
         <div className="adjudication-review-panel">
            <div className="adjudication-contained-error" role="alert">
               <strong>Adjudication unavailable</strong>
               <span>The selected organization does not grant Adjudication access.</span>
            </div>
         </div>
      );
   }

   return (
      <div className="adjudication-review-panel">
         <div className="adjudication-panel-intro">
            <div>
               <h3>Adjudication queue</h3>
               <p>Review organization-scoped Adjudication work and case history.</p>
            </div>
            <span className="adjudication-organization-context">
               Organization: {organizationName || "Unavailable"}
            </span>
         </div>

         <div className="adjudication-boundary-note">
            <Icons name="info" size={17} aria-hidden="true" />
            <p>
               Evidence counts support triage only. They do not determine claim truth or whether a case is ready for a
               decision.
            </p>
         </div>

         {authorityError ? (
            <div
               className="adjudication-contained-error adjudication-authority-error"
               ref={authorityErrorRef}
               tabIndex="-1"
               role="alert"
            >
               <strong>Adjudication unavailable</strong>
               <span>{authorityError}</span>
               <button type="button" onClick={handleAuthorityRetry}>
                  Retry access
               </button>
            </div>
         ) : (
            <>
               <div className="adjudication-toolbar">
                  <div className="adjudication-filter-grid">
                     <label htmlFor="adjudication-status-filter">
                        <span>Case status</span>
                        <select
                           id="adjudication-status-filter"
                           value={statusFilter}
                           onChange={(event) =>
                              replaceQueueScope({ status: event.target.value, nextOffset: 0 })
                           }
                        >
                           {STATUS_OPTIONS.map((option) => (
                              <option key={option.value || "ACTIVE"} value={option.value}>
                                 {option.label}
                              </option>
                           ))}
                        </select>
                     </label>

                     <label htmlFor="adjudication-priority-filter">
                        <span>Priority</span>
                        <select
                           id="adjudication-priority-filter"
                           value={priorityFilter}
                           onChange={(event) =>
                              replaceQueueScope({ priority: event.target.value, nextOffset: 0 })
                           }
                        >
                           {PRIORITY_OPTIONS.map((option) => (
                              <option key={option.value || "ALL"} value={option.value}>
                                 {option.label}
                              </option>
                           ))}
                        </select>
                     </label>
                  </div>

                  <div className="adjudication-toolbar-actions">
                     <span aria-live="polite">
                        {queueLoading && queue.results.length === 0
                           ? "Loading cases…"
                           : `${queue.count} ${queue.count === 1 ? "case" : "cases"}`}
                     </span>
                     <button
                        type="button"
                        disabled={queueLoading}
                        onClick={() => requestQueueRefresh()}
                     >
                        <Icons name="refresh-cw" size={15} aria-hidden="true" />
                        {queueLoading && queue.results.length > 0 ? "Refreshing…" : "Refresh"}
                     </button>
                  </div>
               </div>

               <div className={`adjudication-workspace-grid ${selectedCaseId ? "has-selection" : ""}`}>
                  <section
                     className="adjudication-queue"
                     aria-labelledby="adjudication-queue-heading"
                     aria-busy={queueLoading}
                  >
                     <div className="adjudication-section-heading">
                        <div>
                           <h4 id="adjudication-queue-heading" ref={queueHeadingRef} tabIndex="-1">
                              {activeStatusLabel}
                           </h4>
                           <p>Cases are scoped to {organizationName || "the selected organization"}.</p>
                        </div>
                     </div>

                     {queueError && (
                        <div className="adjudication-contained-error" role="alert">
                           <strong>Adjudication queue unavailable</strong>
                           <span>{queueError}</span>
                           {queue.results.length > 0 && <span>Previously loaded results remain visible below.</span>}
                           <button type="button" onClick={() => requestQueueRefresh({ preserveRows: false })}>
                              Retry
                           </button>
                        </div>
                     )}

                     {queueLoading && queue.results.length === 0 ? (
                        <div className="adjudication-state">
                           <Icons name="loader" size={21} className="adjudication-spinner" aria-hidden="true" />
                           <p>Loading Adjudication cases…</p>
                        </div>
                     ) : queueError && queue.results.length === 0 ? null : queue.results.length === 0 ? (
                        <div className="adjudication-state">
                           <Icons name="list-checks" size={24} aria-hidden="true" />
                           <h5>{emptyCopy.heading}</h5>
                           <p>{emptyCopy.body}</p>
                        </div>
                     ) : (
                        <div className="adjudication-case-list">
                           {queue.results.map((caseItem) => {
                              const selected = String(selectedCaseId) === String(caseItem.id);
                              const evidence = caseItem.evidence_review || {};

                              return (
                                 <button
                                    key={caseItem.id}
                                    type="button"
                                    className={`adjudication-case-row ${selected ? "selected" : ""}`}
                                    aria-pressed={selected}
                                    onClick={() => handleSelectCase(caseItem.id)}
                                 >
                                    <span className="adjudication-case-row-top">
                                       <span className="adjudication-case-status">
                                          {caseItem.status_label || formatLabel(caseItem.status)}
                                       </span>
                                       <span className="adjudication-priority">
                                          Priority: {caseItem.priority_label || formatLabel(caseItem.priority)}
                                       </span>
                                       {selected && <span className="adjudication-selected-label">Selected</span>}
                                    </span>

                                    <strong>{getClaimContext(caseItem)}</strong>
                                    <span className="adjudication-claim-type">
                                       Claim type: {formatLabel(caseItem.claim?.claim_type)}
                                    </span>

                                    <span className="adjudication-evidence-summary">
                                       <span>Total evidence: {normalizeNonnegativeNumber(evidence.total)}</span>
                                       <span>Verified: {normalizeNonnegativeNumber(evidence.verified)}</span>
                                       <span>Rejected: {normalizeNonnegativeNumber(evidence.rejected)}</span>
                                       <span>Unreviewed: {normalizeNonnegativeNumber(evidence.unreviewed)}</span>
                                       <span>
                                          Active Evidence cases: {normalizeNonnegativeNumber(evidence.active_evidence_cases)}
                                       </span>
                                    </span>

                                    <span className="adjudication-case-row-meta">
                                       <span>Source: {formatLabel(caseItem.source)}</span>
                                       <span>
                                          Created <FormattedDateTime value={caseItem.created_at} />
                                       </span>
                                       <span>
                                          Updated <FormattedDateTime value={caseItem.updated_at} />
                                       </span>
                                       {caseItem.resolved_at && (
                                          <span>
                                             Resolved <FormattedDateTime value={caseItem.resolved_at} />
                                          </span>
                                       )}
                                       <span>Case {formatCaseReference(caseItem.id)}</span>
                                    </span>

                                    {caseItem.adjudication_blocked && (
                                       <span className="adjudication-history-indicator">
                                          <Icons name="clock" size={13} aria-hidden="true" />
                                          Decision history exists
                                       </span>
                                    )}
                                 </button>
                              );
                           })}
                        </div>
                     )}

                     <nav className="adjudication-pagination" aria-label="Adjudication queue pagination">
                        <button
                           type="button"
                           disabled={!hasPreviousPage || queueLoading}
                           onClick={() =>
                              replaceQueueScope({ nextOffset: Math.max(0, offset - (queue.limit || PAGE_SIZE)) })
                           }
                        >
                           <Icons name="chevron-left" size={15} aria-hidden="true" />
                           Previous
                        </button>
                        <span>
                           Page {currentPage} of {totalPages}
                        </span>
                        <button
                           type="button"
                           disabled={!hasNextPage || queueLoading}
                           onClick={() =>
                              replaceQueueScope({ nextOffset: offset + (queue.limit || PAGE_SIZE) })
                           }
                        >
                           Next
                           <Icons name="chevron-right" size={15} aria-hidden="true" />
                        </button>
                     </nav>
                  </section>

                  <section
                     className="adjudication-selection"
                     aria-labelledby="adjudication-selection-heading"
                  >
                     {selectedCaseId ? (
                        <div className="adjudication-selection-content">
                           <button
                              type="button"
                              className="adjudication-return-to-queue"
                              onClick={() => clearSelection({ restoreQueueFocus: true })}
                           >
                              <Icons name="arrow-left" size={15} aria-hidden="true" />
                              Return to queue
                           </button>

                           <div className="adjudication-selection-heading">
                              <span>Selected case {formatCaseReference(selectedCaseId)}</span>
                              <h4
                                 id="adjudication-selection-heading"
                                 ref={selectedCaseHeadingRef}
                                 tabIndex="-1"
                              >
                                 {selectedCase ? getClaimContext(selectedCase) : "Selected Adjudication case"}
                              </h4>
                           </div>

                           {selectedCase && (
                              <div className="adjudication-selection-facts">
                                 <span>{selectedCase.status_label || formatLabel(selectedCase.status)}</span>
                                 <span>
                                    Priority: {selectedCase.priority_label || formatLabel(selectedCase.priority)}
                                 </span>
                                 <span>Claim type: {formatLabel(selectedCase.claim?.claim_type)}</span>
                              </div>
                           )}

                           <p>
                              This case is selected from the organization&apos;s authoritative Adjudication queue.
                           </p>
                        </div>
                     ) : (
                        <div className="adjudication-state adjudication-selection-empty">
                           <Icons name="file-text" size={25} aria-hidden="true" />
                           <h4 id="adjudication-selection-heading">Select an Adjudication case</h4>
                           <p>Choose a queue item to establish the exact case identity for review.</p>
                        </div>
                     )}
                  </section>
               </div>
            </>
         )}
      </div>
   );
}

function AdjudicationReviewPanel(props) {
   const { authFetch, token, user } = useAuth();
   const authIdentity = getAuthIdentity(user, token);

   return (
      <AdjudicationReviewContent
         key={`${props.organizationId}:${authIdentity}`}
         {...props}
         authFetch={authFetch}
      />
   );
}

export default AdjudicationReviewPanel;
