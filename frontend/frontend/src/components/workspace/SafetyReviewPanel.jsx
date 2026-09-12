import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import Icons from "../Icons.jsx";

import "./SafetyReviewPanel.css";

const ACTIVE_CASE_STATUSES = new Set(["OPEN", "IN_REVIEW", "ESCALATED", "REOPENED"]);

const STATUS_OPTIONS = ["", "OPEN", "IN_REVIEW", "ESCALATED", "REOPENED"];
const PRIORITY_OPTIONS = ["", "LOW", "NORMAL", "HIGH", "URGENT"];
const ASSIGNMENT_OPTIONS = [
   { value: "", label: "All assignments" },
   { value: "me", label: "My cases" },
   { value: "unassigned", label: "Unassigned" },
];

const ACTION_DETAILS = {
   DISMISS: {
      label: "Dismiss case",
      confirmation: "No policy violation found",
      consequence: "The case will be resolved, its reports closed, and the thread will remain visible.",
      notesRequired: false,
   },
   REMOVE: {
      label: "Remove content",
      confirmation: "Confirm policy violation",
      consequence: "The case will be resolved and the thread will be removed from active circulation.",
      notesRequired: true,
   },
   ESCALATE: {
      label: "Escalate review",
      confirmation: "Escalate for further Safety review",
      consequence: "The case will remain active and its reports will remain unresolved for deeper review.",
      notesRequired: true,
   },
};

function formatLabel(value, fallback = "Unknown") {
   if (!value) {
      return fallback;
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

function getCaseTitle(caseItem) {
   return (
      caseItem?.thread?.claim?.context_text ||
      caseItem?.thread?.caption ||
      "Thread context unavailable"
   );
}

function getAssignmentLabel(caseItem, currentUserId) {
   const assignedTo = caseItem?.assigned_to;

   if (!assignedTo) {
      return "Unassigned";
   }

   if (String(assignedTo.id) === String(currentUserId)) {
      return "Assigned to you";
   }

   return assignedTo.username ? `Assigned to @${assignedTo.username}` : "Assigned to another moderator";
}

function requiresServerReconciliation(error) {
   return error?.status === 404 || error?.status === 409;
}

function formatCaseReference(caseId) {
   return String(caseId || "").slice(0, 8);
}

function SafetyReviewPanel() {
   const { authFetch, user } = useAuth();

   const [filters, setFilters] = useState({
      status: "",
      priority: "",
      assigned: "",
   });
   const [queue, setQueue] = useState({ count: 0, results: [] });
   const [queueLoading, setQueueLoading] = useState(true);
   const [queueError, setQueueError] = useState("");
   const [queueRequestVersion, setQueueRequestVersion] = useState(0);

   const [selectedCaseId, setSelectedCaseId] = useState(null);
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(false);
   const [detailError, setDetailError] = useState("");
   const [detailUnavailable, setDetailUnavailable] = useState(false);
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);

   const [notice, setNotice] = useState("");
   const [actionError, setActionError] = useState("");
   const [pendingOperation, setPendingOperation] = useState(null);
   const [confirmingRelease, setConfirmingRelease] = useState(false);
   const [decisionAction, setDecisionAction] = useState(null);
   const [decisionNotes, setDecisionNotes] = useState("");

   const queueRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const selectedCaseIdRef = useRef(null);
   const queueHeadingRef = useRef(null);
   const detailRegionRef = useRef(null);
   const detailHeadingRef = useRef(null);
   const focusDetailAfterLoadRef = useRef(false);
   const focusDetailAfterMutationRef = useRef(false);
   const focusDetailErrorRef = useRef(false);
   const detailErrorRef = useRef(null);
   const decisionNotesRef = useRef(null);
   const dismissActionRef = useRef(null);
   const removeActionRef = useRef(null);
   const escalateActionRef = useRef(null);
   const decisionReturnFocusRef = useRef(null);
   const releaseTriggerRef = useRef(null);
   const releaseCancelRef = useRef(null);
   const restoreReleaseFocusRef = useRef(false);

   const queueUrl = useMemo(() => {
      const query = new URLSearchParams();

      if (filters.status) {
         query.set("status", filters.status);
      }

      if (filters.priority) {
         query.set("priority", filters.priority);
      }

      if (filters.assigned) {
         query.set("assigned", filters.assigned);
      }

      const queryString = query.toString();
      const endpoint = resolveApiEndpoint("SAFETY_CASES");

      return queryString ? `${endpoint}?${queryString}` : endpoint;
   }, [filters]);

   useEffect(() => {
      let cancelled = false;
      const requestId = queueRequestIdRef.current + 1;
      queueRequestIdRef.current = requestId;

      authFetch(queueUrl, { method: "GET" })
         .then((data) => {
            if (cancelled || queueRequestIdRef.current !== requestId) {
               return;
            }

            setQueue({
               count: Number(data?.count ?? 0),
               results: Array.isArray(data?.results) ? data.results : [],
            });
            setQueueError("");
         })
         .catch((error) => {
            if (cancelled || queueRequestIdRef.current !== requestId) {
               return;
            }

            setQueueError(error?.message || "Unable to load the Platform Safety queue.");
         })
         .finally(() => {
            if (!cancelled && queueRequestIdRef.current === requestId) {
               setQueueLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, queueRequestVersion, queueUrl]);

   useEffect(() => {
      if (!selectedCaseId) {
         return undefined;
      }

      let cancelled = false;
      const requestId = detailRequestIdRef.current + 1;
      detailRequestIdRef.current = requestId;

      authFetch(resolveApiEndpoint("SAFETY_CASE_DETAIL", selectedCaseId), {
         method: "GET",
      })
         .then((data) => {
            if (cancelled || detailRequestIdRef.current !== requestId) {
               return;
            }

            setDetail(data);
            setDetailError("");
            setDetailUnavailable(false);
         })
         .catch((error) => {
            if (cancelled || detailRequestIdRef.current !== requestId) {
               return;
            }

            const isUnavailable = error?.status === 404;

            setDetail(null);
            focusDetailAfterLoadRef.current = false;
            focusDetailAfterMutationRef.current = false;
            focusDetailErrorRef.current = true;
            setDetailError(
               isUnavailable
                  ? "This Safety case is no longer available. The queue has been refreshed."
                  : (error?.message || "Unable to load this Safety case."),
            );
            setDetailUnavailable(isUnavailable);

            if (isUnavailable) {
               selectedCaseIdRef.current = null;
               setSelectedCaseId(null);
               setActionError("");
               setQueueLoading(true);
               setQueueRequestVersion((current) => current + 1);
            }
         })
         .finally(() => {
            if (!cancelled && detailRequestIdRef.current === requestId) {
               setDetailLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, detailRequestVersion, selectedCaseId]);

   useEffect(() => {
      if (!detail) {
         return;
      }

      if (focusDetailAfterMutationRef.current) {
         focusDetailAfterMutationRef.current = false;
         focusDetailAfterLoadRef.current = false;
         detailHeadingRef.current?.focus();
         return;
      }

      if (!focusDetailAfterLoadRef.current) {
         return;
      }

      focusDetailAfterLoadRef.current = false;

      if (window.matchMedia("(max-width: 760px)").matches) {
         detailHeadingRef.current?.focus();
      }
   }, [detail]);

   useEffect(() => {
      if (decisionAction) {
         decisionNotesRef.current?.focus();
         return;
      }

      const returnAction = decisionReturnFocusRef.current;

      if (!returnAction) {
         return;
      }

      decisionReturnFocusRef.current = null;

      if (returnAction === "DISMISS") {
         dismissActionRef.current?.focus();
      } else if (returnAction === "REMOVE") {
         removeActionRef.current?.focus();
      } else if (returnAction === "ESCALATE") {
         escalateActionRef.current?.focus();
      }
   }, [decisionAction]);

   useEffect(() => {
      if (confirmingRelease) {
         releaseCancelRef.current?.focus();
         return;
      }

      if (restoreReleaseFocusRef.current) {
         restoreReleaseFocusRef.current = false;
         releaseTriggerRef.current?.focus();
      }
   }, [confirmingRelease]);

   useEffect(() => {
      if (detailError && focusDetailErrorRef.current) {
         focusDetailErrorRef.current = false;
         detailErrorRef.current?.focus();
      }
   }, [detailError]);

   const requestQueueRefresh = ({ clearMessages = false } = {}) => {
      setQueueLoading(true);
      setQueueError("");

      if (clearMessages) {
         setNotice("");
         setActionError("");
      }

      setQueueRequestVersion((current) => current + 1);
   };

   const requestDetailRefresh = (caseId) => {
      if (!caseId || selectedCaseIdRef.current !== caseId) {
         return;
      }

      setDetail(null);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailRequestVersion((current) => current + 1);
   };

   const handleQueueRetry = () => {
      requestQueueRefresh();
      queueHeadingRef.current?.focus();
   };

   const handleDetailRetry = () => {
      requestDetailRefresh(selectedCaseId);
      detailRegionRef.current?.focus();
   };

   const handleReturnToQueue = () => {
      setDetailError("");
      setDetailUnavailable(false);
      queueHeadingRef.current?.focus();
   };

   const reconcileConflict = (caseId, error) => {
      setNotice("");
      requestQueueRefresh();

      if (selectedCaseIdRef.current === caseId) {
         setActionError(error?.message || "This Safety case changed before the request completed.");
         setConfirmingRelease(false);
         decisionReturnFocusRef.current = null;
         restoreReleaseFocusRef.current = false;
         focusDetailAfterMutationRef.current = true;
         setDecisionAction(null);
         requestDetailRefresh(caseId);
      } else {
         setNotice(
            `Case ${formatCaseReference(caseId)}: ${
               error?.message || "The case changed before the request completed."
            }`,
         );
      }
   };

   const reportMutationFailure = (caseId, message) => {
      if (selectedCaseIdRef.current === caseId) {
         setActionError(message);
      } else {
         setNotice(`Case ${formatCaseReference(caseId)}: ${message}`);
      }
   };

   const updateQueueCase = (updatedCase) => {
      setQueue((current) => ({
         ...current,
         results: current.results.map((caseItem) =>
            caseItem.id === updatedCase.id ? { ...caseItem, ...updatedCase } : caseItem,
         ),
      }));
   };

   const removeCompletedQueueCase = (caseId) => {
      setQueue((current) => {
         const remainsInQueue = current.results.some((caseItem) => caseItem.id === caseId);

         return {
            count: remainsInQueue ? Math.max(0, current.count - 1) : current.count,
            results: current.results.filter((caseItem) => caseItem.id !== caseId),
         };
      });
   };

   const handleFilterChange = (filterName, value) => {
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      focusDetailAfterLoadRef.current = false;
      focusDetailAfterMutationRef.current = false;
      focusDetailErrorRef.current = false;
      decisionReturnFocusRef.current = null;
      restoreReleaseFocusRef.current = false;

      setFilters((current) => ({ ...current, [filterName]: value }));
      setQueue({ count: 0, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setNotice("");
      setActionError("");
      setConfirmingRelease(false);
      setDecisionAction(null);
      setDecisionNotes("");
   };

   const handleSelectCase = (caseId) => {
      selectedCaseIdRef.current = caseId;
      focusDetailAfterLoadRef.current = true;
      focusDetailAfterMutationRef.current = false;
      focusDetailErrorRef.current = false;
      decisionReturnFocusRef.current = null;
      restoreReleaseFocusRef.current = false;
      setSelectedCaseId(caseId);
      setDetail(null);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setNotice("");
      setActionError("");
      setConfirmingRelease(false);
      setDecisionAction(null);
      setDecisionNotes("");
   };

   const handleOpenReleaseConfirmation = () => {
      restoreReleaseFocusRef.current = false;
      setConfirmingRelease(true);
   };

   const handleCancelReleaseConfirmation = () => {
      restoreReleaseFocusRef.current = true;
      setConfirmingRelease(false);
   };

   const handleOpenDecision = (action) => {
      decisionReturnFocusRef.current = action;
      setActionError("");
      setDecisionAction(action);
   };

   const handleCancelDecision = () => {
      setDecisionAction(null);
      setDecisionNotes("");
      setActionError("");
   };

   const handleClaim = async () => {
      if (!detail?.id || pendingOperation) {
         return;
      }

      const caseId = detail.id;
      setPendingOperation({ caseId, kind: "claim" });
      setActionError("");
      setNotice("");

      try {
         const updatedCase = await authFetch(resolveApiEndpoint("SAFETY_CASE_CLAIM", caseId), {
            method: "POST",
         });

         updateQueueCase(updatedCase);

         if (selectedCaseIdRef.current === caseId) {
            focusDetailAfterMutationRef.current = true;
            setDetail(updatedCase);
         }

         setNotice(`Case ${formatCaseReference(caseId)} claimed. It is now assigned to you.`);
         requestQueueRefresh();
      } catch (error) {
         if (requiresServerReconciliation(error)) {
            reconcileConflict(caseId, error);
         } else {
            reportMutationFailure(caseId, error?.message || "Unable to claim this Safety case.");
         }
      } finally {
         setPendingOperation(null);
      }
   };

   const handleRelease = async () => {
      if (!detail?.id || pendingOperation) {
         return;
      }

      const caseId = detail.id;
      setPendingOperation({ caseId, kind: "release" });
      setActionError("");
      setNotice("");

      try {
         const updatedCase = await authFetch(resolveApiEndpoint("SAFETY_CASE_RELEASE", caseId), {
            method: "POST",
         });

         updateQueueCase(updatedCase);

         if (selectedCaseIdRef.current === caseId) {
            focusDetailAfterMutationRef.current = true;
            setDetail(updatedCase);
         }

         restoreReleaseFocusRef.current = false;
         setConfirmingRelease(false);
         setNotice(
            `Case ${formatCaseReference(caseId)} released. It is available for another Safety moderator to claim.`,
         );
         requestQueueRefresh();
      } catch (error) {
         if (requiresServerReconciliation(error)) {
            reconcileConflict(caseId, error);
         } else {
            reportMutationFailure(caseId, error?.message || "Unable to release this Safety case.");
         }
      } finally {
         setPendingOperation(null);
      }
   };

   const handleDecisionSubmit = async (event) => {
      event.preventDefault();

      const action = decisionAction;
      const actionDetail = action ? ACTION_DETAILS[action] : null;
      const notes = decisionNotes.trim();

      if (!detail?.id || !actionDetail || pendingOperation) {
         return;
      }

      if (actionDetail.notesRequired && !notes) {
         setActionError("Moderator notes are required for this Safety action.");
         return;
      }

      const caseId = detail.id;
      setPendingOperation({ caseId, kind: "action", action });
      setActionError("");
      setNotice("");

      try {
         const updatedCase = await authFetch(resolveApiEndpoint("SAFETY_CASE_ACTION", caseId), {
            method: "POST",
            body: {
               action,
               notes,
            },
         });

         if (selectedCaseIdRef.current === caseId) {
            focusDetailAfterMutationRef.current = true;
            setDetail(updatedCase);
         }

         decisionReturnFocusRef.current = null;
         restoreReleaseFocusRef.current = false;
         setDecisionAction(null);
         setDecisionNotes("");
         setConfirmingRelease(false);

         if (action === "ESCALATE") {
            updateQueueCase(updatedCase);
            setNotice(`Case ${formatCaseReference(caseId)} escalated for further Platform Safety review.`);
         } else {
            removeCompletedQueueCase(caseId);
            setNotice(
               action === "REMOVE"
                  ? `Case ${formatCaseReference(caseId)} completed. The reported content was removed from active circulation.`
                  : `Case ${formatCaseReference(caseId)} completed. No policy violation was found and the thread remains visible.`,
            );
         }

         requestQueueRefresh();
      } catch (error) {
         if (requiresServerReconciliation(error)) {
            reconcileConflict(caseId, error);
         } else {
            reportMutationFailure(caseId, error?.message || "Unable to complete this Safety action.");
         }
      } finally {
         setPendingOperation(null);
      }
   };

   const currentUserId = user?.id;
   const isActiveCase = ACTIVE_CASE_STATUSES.has(detail?.status);
   const isAssignedToCurrentUser =
      Boolean(detail?.assigned_to?.id) && String(detail.assigned_to.id) === String(currentUserId);
   const isAssignedToAnother = Boolean(detail?.assigned_to) && !isAssignedToCurrentUser;
   const isBusy = Boolean(pendingOperation);
   const selectedActionDetail = decisionAction ? ACTION_DETAILS[decisionAction] : null;
   const hasQueueResults = queue.results.length > 0;
   const isInitialQueueLoading = queueLoading && !hasQueueResults && !queueError;

   return (
      <div className="safety-review-panel">
         <div className="safety-toolbar">
            <div className="safety-toolbar-summary" role="status" aria-live="polite">
               <strong>
                  {isInitialQueueLoading
                     ? "Loading active cases"
                     : `${queue.count} active ${queue.count === 1 ? "case" : "cases"}`}
               </strong>
               <span>{queueLoading ? "Updating queue…" : "Platform-wide Safety queue"}</span>
            </div>

            <div className="safety-filter-grid">
               <label>
                  <span>Status</span>
                  <select
                     value={filters.status}
                     disabled={queueLoading}
                     onChange={(event) => handleFilterChange("status", event.target.value)}
                  >
                     {STATUS_OPTIONS.map((value) => (
                        <option key={value || "ALL"} value={value}>
                           {value ? formatLabel(value) : "All statuses"}
                        </option>
                     ))}
                  </select>
               </label>

               <label>
                  <span>Priority</span>
                  <select
                     value={filters.priority}
                     disabled={queueLoading}
                     onChange={(event) => handleFilterChange("priority", event.target.value)}
                  >
                     {PRIORITY_OPTIONS.map((value) => (
                        <option key={value || "ALL"} value={value}>
                           {value ? formatLabel(value) : "All priorities"}
                        </option>
                     ))}
                  </select>
               </label>

               <label>
                  <span>Assignment</span>
                  <select
                     value={filters.assigned}
                     disabled={queueLoading}
                     onChange={(event) => handleFilterChange("assigned", event.target.value)}
                  >
                     {ASSIGNMENT_OPTIONS.map((option) => (
                        <option key={option.value || "ALL"} value={option.value}>
                           {option.label}
                        </option>
                     ))}
                  </select>
               </label>

               <button
                  type="button"
                  className="safety-refresh-button"
                  disabled={queueLoading}
                  onClick={() => requestQueueRefresh({ clearMessages: true })}
               >
                  <Icons name="refresh-cw" size={15} />
                  Refresh
               </button>
            </div>
         </div>

         {notice && (
            <div className="safety-notice" role="status" aria-live="polite">
               <Icons name="info" size={17} />
               <span>{notice}</span>
            </div>
         )}

         {actionError && (
            <div className="safety-error" role="alert">
               <Icons name="alert-circle" size={17} />
               <div>
                  <strong>Action unavailable</strong>
                  <span>{actionError}</span>
               </div>
            </div>
         )}

         <div className="safety-workspace-grid">
            <section className="safety-queue" aria-labelledby="safety-queue-heading" aria-busy={queueLoading}>
               <div className="safety-section-heading">
                  <div>
                     <h3 id="safety-queue-heading" ref={queueHeadingRef} tabIndex="-1">
                        Active cases
                     </h3>
                     <p>Select a case to load its reports, history, and available actions.</p>
                  </div>
               </div>

               {queueError && (
                  <div className="safety-contained-error" role="alert">
                     <strong>Safety queue unavailable</strong>
                     <span>{queueError}</span>
                     <button type="button" onClick={handleQueueRetry}>
                        Retry
                     </button>
                  </div>
               )}

               {isInitialQueueLoading ? (
                  <div className="safety-state" role="status">
                     <Icons name="loader" size={20} className="safety-spinner" />
                     <span>Loading active Safety cases…</span>
                  </div>
               ) : !queueError && !hasQueueResults ? (
                  <div className="safety-state">
                     <Icons name="shield-check" size={23} />
                     <h4>No active cases</h4>
                     <p>No Platform Safety cases match the current filters.</p>
                  </div>
               ) : (
                  <ul className="safety-case-list">
                     {queue.results.map((caseItem) => {
                        const isSelected = selectedCaseId === caseItem.id;
                        const reasonSummary = Array.isArray(caseItem.report_reason_summary)
                           ? caseItem.report_reason_summary
                           : [];

                        return (
                           <li key={caseItem.id} className="safety-case-item">
                              <button
                                 type="button"
                                 className={`safety-case-row ${isSelected ? "selected" : ""}`}
                                 aria-pressed={isSelected}
                                 aria-controls="safety-case-detail"
                                 onClick={() => handleSelectCase(caseItem.id)}
                              >
                                 <span className="safety-case-row-top">
                                    <span className={`safety-status status-${String(caseItem.status).toLowerCase()}`}>
                                       {formatLabel(caseItem.status)}
                                    </span>
                                    <span className={`safety-priority priority-${String(caseItem.priority).toLowerCase()}`}>
                                       {formatLabel(caseItem.priority)} priority
                                    </span>
                                    {isSelected && <span className="safety-selected-label">Selected</span>}
                                 </span>

                                 <strong>{getCaseTitle(caseItem)}</strong>

                                 <span className="safety-case-context">
                                    By {caseItem?.thread?.author?.username ? `@${caseItem.thread.author.username}` : "Unknown author"}
                                 </span>

                                 <span className="safety-reason-summary">
                                    {reasonSummary.length > 0
                                       ? reasonSummary
                                            .map((reason) => `${reason.reason_label}: ${reason.count}`)
                                            .join(" · ")
                                       : "No unresolved report reasons"}
                                 </span>

                                 <span className="safety-case-row-meta">
                                    <span>{caseItem.report_count} {caseItem.report_count === 1 ? "report" : "reports"}</span>
                                    <span>{getAssignmentLabel(caseItem, currentUserId)}</span>
                                    <span>Created {formatDateTime(caseItem.created_at)}</span>
                                    <span>Updated {formatDateTime(caseItem.updated_at)}</span>
                                 </span>
                              </button>
                           </li>
                        );
                     })}
                  </ul>
               )}
            </section>

            <section
               ref={detailRegionRef}
               id="safety-case-detail"
               className="safety-detail"
               aria-label="Safety case detail"
               aria-busy={detailLoading}
               tabIndex="-1"
            >
               {detailError ? (
                  <div
                     ref={detailErrorRef}
                     className="safety-contained-error"
                     role="alert"
                     tabIndex="-1"
                  >
                     <strong>Case detail unavailable</strong>
                     <span>{detailError}</span>
                     {detailUnavailable ? (
                        <button
                           type="button"
                           onClick={handleReturnToQueue}
                        >
                           Return to queue
                        </button>
                     ) : (
                        <button
                           type="button"
                           onClick={handleDetailRetry}
                        >
                           Retry
                        </button>
                     )}
                  </div>
               ) : !selectedCaseId ? (
                  <div className="safety-state safety-detail-empty">
                     <Icons name="shield" size={24} />
                     <h3>No case selected</h3>
                     <p>Select an active case from the queue to begin review.</p>
                  </div>
               ) : detailLoading ? (
                  <div className="safety-state" role="status">
                     <Icons name="loader" size={20} className="safety-spinner" />
                     <span>Loading Safety case detail…</span>
                  </div>
               ) : detail ? (
                  <div className="safety-detail-content">
                     <header className="safety-detail-header">
                        <div className="safety-detail-heading-copy">
                           <span className="safety-detail-eyebrow">Platform Safety case</span>
                           <h3 id="safety-case-detail-heading" ref={detailHeadingRef} tabIndex="-1">
                              {getCaseTitle(detail)}
                           </h3>
                           <span className="safety-case-id">Case {detail.id}</span>
                        </div>

                        <div className="safety-detail-badges">
                           <span className={`safety-status status-${String(detail.status).toLowerCase()}`}>
                              Status: {formatLabel(detail.status)}
                           </span>
                           <span className={`safety-priority priority-${String(detail.priority).toLowerCase()}`}>
                              Priority: {formatLabel(detail.priority)}
                           </span>
                        </div>
                     </header>

                     <dl className="safety-case-facts">
                        <div>
                           <dt>Assignment</dt>
                           <dd>{getAssignmentLabel(detail, currentUserId)}</dd>
                        </div>
                        <div>
                           <dt>Source</dt>
                           <dd>{formatLabel(detail.source)}</dd>
                        </div>
                        <div>
                           <dt>Created</dt>
                           <dd>{formatDateTime(detail.created_at)}</dd>
                        </div>
                        <div>
                           <dt>Last updated</dt>
                           <dd>{formatDateTime(detail.updated_at)}</dd>
                        </div>
                     </dl>

                     <section className="safety-detail-section">
                        <div className="safety-subheading-row safety-major-section-heading">
                           <div>
                              <h4>Thread context</h4>
                              <p>Context associated with the reported community thread.</p>
                           </div>
                           {detail.thread?.id && (
                              <Link to={`/thread/detail/${detail.thread.id}`} className="safety-thread-link">
                                 Open thread
                                 <Icons name="arrow-right" size={14} />
                              </Link>
                           )}
                        </div>

                        <div className="safety-thread-context">
                           <span>{formatLabel(detail.thread?.claim?.claim_type, "Claim type unavailable")}</span>
                           <p>{detail.thread?.claim?.context_text || detail.thread?.caption || "Thread context unavailable"}</p>
                           <small>
                              Author: {detail.thread?.author?.username ? `@${detail.thread.author.username}` : "Unknown"}
                              {detail.thread?.created_at ? ` · Posted ${formatDateTime(detail.thread.created_at)}` : ""}
                           </small>
                        </div>
                     </section>

                     <section className="safety-detail-section">
                        <div className="safety-subheading-row safety-major-section-heading">
                           <div>
                              <h4>Reports</h4>
                              <p>{detail.report_count} case-specific {detail.report_count === 1 ? "report" : "reports"}</p>
                           </div>
                        </div>

                        {Array.isArray(detail.reports) && detail.reports.length > 0 ? (
                           <ul className="safety-report-list">
                              {detail.reports.map((report) => (
                                 <li key={report.id}>
                                    <div>
                                       <strong>{report.reason_label || formatLabel(report.reason)}</strong>
                                       <time dateTime={report.flagged_at}>{formatDateTime(report.flagged_at)}</time>
                                    </div>
                                    <p>{report.notes || "No additional report notes were provided."}</p>
                                 </li>
                              ))}
                           </ul>
                        ) : (
                           <p className="safety-inline-empty">No report details are associated with this case.</p>
                        )}
                     </section>

                     <section className="safety-detail-section">
                        <div className="safety-subheading-row safety-major-section-heading">
                           <div>
                              <h4>Moderation history</h4>
                              <p>Recent case events supplied by the Safety audit history.</p>
                           </div>
                        </div>

                        {Array.isArray(detail.events) && detail.events.length > 0 ? (
                           <ol className="safety-event-list">
                              {detail.events.map((event, index) => (
                                 <li key={`${event.event_type}-${event.created_at}-${index}`}>
                                    <span className="safety-event-marker" aria-hidden="true" />
                                    <div>
                                       <div className="safety-event-heading">
                                          <strong>{formatLabel(event.event_type)}</strong>
                                          <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                                       </div>
                                       <p>
                                          Actor: {event.actor?.username ? `@${event.actor.username}` : "Actor not displayed"}
                                       </p>
                                       {(event.from_status || event.to_status) && (
                                          <p>
                                             Transition: {formatLabel(event.from_status, "None")} → {formatLabel(event.to_status, "None")}
                                          </p>
                                       )}
                                       {event.reason_code && <p>Reason: {formatLabel(event.reason_code)}</p>}
                                       {event.notes && <p>Notes: {event.notes}</p>}
                                    </div>
                                 </li>
                              ))}
                           </ol>
                        ) : (
                           <p className="safety-inline-empty">No moderation history is available.</p>
                        )}
                     </section>

                     <section className="safety-action-section" aria-labelledby="safety-actions-heading">
                        <div className="safety-subheading-row safety-major-section-heading">
                           <div>
                              <h4 id="safety-actions-heading">Safety actions</h4>
                              <p>Actions apply to this Platform Safety case, not a factual verdict.</p>
                           </div>
                        </div>

                        {!isActiveCase ? (
                           <div className="safety-complete-state" role="status">
                              <Icons name="check-circle" size={18} />
                              <div>
                                 <strong>Review completed</strong>
                                 <span>This case is no longer active and has no further Safety controls.</span>
                              </div>
                           </div>
                        ) : !detail.assigned_to ? (
                           <div className="safety-assignment-action">
                              <p>Claim this case before recording a Safety decision.</p>
                              <button type="button" disabled={isBusy} onClick={handleClaim}>
                                 {pendingOperation?.kind === "claim" ? "Claiming…" : "Claim case"}
                              </button>
                           </div>
                        ) : isAssignedToAnother ? (
                           <div className="safety-assignment-locked">
                              <Icons name="lock" size={17} />
                              <span>{getAssignmentLabel(detail, currentUserId)}. Only the assignee can act on this case.</span>
                           </div>
                        ) : (
                           <>
                              <div className="safety-owner-row">
                                 <span>
                                    <Icons name="user-check" size={16} />
                                    Assigned to you
                                 </span>

                                 {confirmingRelease ? (
                                    <div className="safety-release-confirm">
                                       <span>Release this case?</span>
                                       <button
                                          ref={releaseCancelRef}
                                          type="button"
                                          className="secondary"
                                          disabled={isBusy}
                                          onClick={handleCancelReleaseConfirmation}
                                       >
                                          Cancel
                                       </button>
                                       <button type="button" disabled={isBusy} onClick={handleRelease}>
                                          {pendingOperation?.kind === "release" ? "Releasing…" : "Release case"}
                                       </button>
                                    </div>
                                 ) : (
                                    <button
                                       ref={releaseTriggerRef}
                                       type="button"
                                       className="safety-release-trigger"
                                       disabled={isBusy || Boolean(decisionAction)}
                                       onClick={handleOpenReleaseConfirmation}
                                    >
                                       Release case
                                    </button>
                                 )}
                              </div>

                              {!decisionAction ? (
                                 <div className="safety-decision-options">
                                    <button
                                       ref={dismissActionRef}
                                       type="button"
                                       disabled={isBusy || confirmingRelease}
                                       onClick={() => handleOpenDecision("DISMISS")}
                                    >
                                       Dismiss case
                                    </button>
                                    <button
                                       ref={removeActionRef}
                                       type="button"
                                       className="danger"
                                       disabled={isBusy || confirmingRelease}
                                       onClick={() => handleOpenDecision("REMOVE")}
                                    >
                                       Remove content
                                    </button>
                                    {detail.status !== "ESCALATED" && (
                                       <button
                                          ref={escalateActionRef}
                                          type="button"
                                          className="warning"
                                          disabled={isBusy || confirmingRelease}
                                          onClick={() => handleOpenDecision("ESCALATE")}
                                       >
                                          Escalate review
                                       </button>
                                    )}
                                 </div>
                              ) : (
                                 <form className="safety-decision-form" onSubmit={handleDecisionSubmit}>
                                    <div className="safety-decision-summary">
                                       <strong>{selectedActionDetail.confirmation}</strong>
                                       <p id="safety-decision-consequence">{selectedActionDetail.consequence}</p>
                                    </div>

                                    <label htmlFor="safety-moderator-notes">
                                       Moderator notes {selectedActionDetail.notesRequired ? "(required)" : "(optional)"}
                                    </label>
                                    <textarea
                                       ref={decisionNotesRef}
                                       id="safety-moderator-notes"
                                       value={decisionNotes}
                                       maxLength={2000}
                                       required={selectedActionDetail.notesRequired}
                                       aria-describedby="safety-decision-consequence safety-notes-count"
                                       disabled={isBusy}
                                       rows={5}
                                       onChange={(event) => setDecisionNotes(event.target.value)}
                                    />
                                    <span id="safety-notes-count" className="safety-notes-count">
                                       {decisionNotes.length}/2000
                                    </span>

                                    <div className="safety-decision-controls">
                                       <button
                                          type="button"
                                          className="secondary"
                                          disabled={isBusy}
                                          onClick={handleCancelDecision}
                                       >
                                          Cancel
                                       </button>
                                       <button
                                          type="submit"
                                          className={decisionAction === "REMOVE" ? "danger" : "primary"}
                                          disabled={isBusy}
                                       >
                                          {pendingOperation?.kind === "action"
                                             ? "Submitting…"
                                             : `Confirm ${selectedActionDetail.label.toLowerCase()}`}
                                       </button>
                                    </div>
                                 </form>
                              )}
                           </>
                        )}
                     </section>
                  </div>
               ) : null}
            </section>
         </div>
      </div>
   );
}

export default SafetyReviewPanel;
