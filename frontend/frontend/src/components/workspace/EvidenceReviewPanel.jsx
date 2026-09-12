import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import Icons from "../Icons.jsx";

import "./EvidenceReviewPanel.css";

const PAGE_SIZE = 20;
const ACTIVE_CASE_STATUSES = new Set(["OPEN", "IN_REVIEW", "ESCALATED", "REOPENED"]);
const RECORDED_DISPOSITIONS = new Set(["VERIFIED", "REJECTED"]);

const DISPOSITION_OPTIONS = [
   { value: "UNVERIFIED", label: "Pending" },
   { value: "VERIFIED", label: "Verified" },
   { value: "REJECTED", label: "Rejected" },
];

const REJECTION_REASONS = [
   { value: "IRRELEVANT", label: "Irrelevant" },
   { value: "UNRELIABLE_SOURCE", label: "Unreliable Source" },
   { value: "INACCESSIBLE_SOURCE", label: "Inaccessible Source" },
   { value: "DUPLICATE", label: "Duplicate" },
   { value: "OUTDATED", label: "Outdated" },
   { value: "MISREPRESENTS_SOURCE", label: "Misrepresents Source" },
   { value: "INSUFFICIENT_CONTEXT", label: "Insufficient Context" },
   { value: "FABRICATED", label: "Fabricated" },
   { value: "OTHER", label: "Other" },
];

const DECISION_COPY = {
   VERIFIED: {
      label: "Verify evidence",
      heading: "Accept this evidence into the reviewed set?",
      consequence:
         "The evidence will be accepted into the reviewed evidence set. This does not determine the claim's final verdict.",
   },
   REJECTED: {
      label: "Reject evidence",
      heading: "Reject this evidence from the reviewed set?",
      consequence:
         "The evidence will be rejected from the reviewed evidence set for the selected reason. This does not determine the claim's final verdict.",
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

function getEvidenceTitle(caseItem) {
   return caseItem?.evidence?.evidence_caption || "Evidence caption unavailable";
}

function getClaimContext(caseItem) {
   return caseItem?.thread?.claim?.context_text || caseItem?.thread?.caption || "Claim context unavailable";
}

function safeExternalUrl(value) {
   if (!value) {
      return null;
   }

   try {
      const url = new URL(value);
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
   } catch {
      return null;
   }
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

function getDispositionLabel(evidence) {
   if (evidence?.evidence_status_label) {
      return evidence.evidence_status_label;
   }

   if (evidence?.evidence_status) {
      return formatLabel(evidence.evidence_status);
   }

   return "Historical review outcome unavailable";
}

function getQueueEmptyCopy(disposition) {
   if (disposition === "VERIFIED") {
      return {
         heading: "No verified evidence history",
         body: "No verified Evidence cases are available for this organization on this page.",
      };
   }

   if (disposition === "REJECTED") {
      return {
         heading: "No rejected evidence history",
         body: "No rejected Evidence cases are available for this organization on this page.",
      };
   }

   return {
      heading: "No evidence awaiting review",
      body: "There are no pending Evidence cases for this organization on this page.",
   };
}

function getReadOnlyDecisionState(caseDetail, evidence) {
   if (caseDetail?.status === "CANCELLED") {
      return {
         heading: "Case cancelled",
         body: "This case was cancelled without recording an Evidence Review disposition.",
      };
   }

   if (!RECORDED_DISPOSITIONS.has(evidence?.evidence_status)) {
      return {
         heading: "Historical review outcome unavailable",
         body: "This case is read-only, but a recorded evidence disposition is not available.",
      };
   }

   return {
      heading: "Review recorded",
      body: "This case is read-only and retains its case-specific historical outcome.",
   };
}

function EvidenceReviewContent({
   authFetch,
   authIdentity,
   organizationId,
   organizationName,
   canReviewEvidence,
}) {

   const [disposition, setDisposition] = useState("UNVERIFIED");
   const [offset, setOffset] = useState(0);
   const [queue, setQueue] = useState({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
   const [queueLoading, setQueueLoading] = useState(true);
   const [queueError, setQueueError] = useState("");
   const [queueRequestVersion, setQueueRequestVersion] = useState(0);

   const [selectedCaseId, setSelectedCaseId] = useState(null);
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(false);
   const [detailError, setDetailError] = useState("");
   const [detailUnavailable, setDetailUnavailable] = useState(false);
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);

   const [decision, setDecision] = useState(null);
   const [moderatorNotes, setModeratorNotes] = useState("");
   const [rejectionReason, setRejectionReason] = useState("");
   const [validationError, setValidationError] = useState("");
   const [mutation, setMutation] = useState(null);
   const [notice, setNotice] = useState("");
   const [actionError, setActionError] = useState("");
   const [authorityError, setAuthorityError] = useState("");

   const mountedRef = useRef(true);
   const authorityGenerationRef = useRef(0);
   const authorityRevokedRef = useRef(false);
   const queueRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const selectedCaseIdRef = useRef(null);
   const detailHeadingRef = useRef(null);
   const detailErrorRef = useRef(null);
   const actionErrorRef = useRef(null);
   const authorityErrorRef = useRef(null);
   const queueHeadingRef = useRef(null);
   const decisionTriggerRef = useRef(null);
   const decisionNotesRef = useRef(null);
   const rejectionReasonRef = useRef(null);
   const focusDetailAfterLoadRef = useRef(false);
   const focusDetailAfterRetryRef = useRef(false);
   const focusDetailAfterMutationRef = useRef(false);
   const focusDetailErrorRef = useRef(false);
   const focusActionErrorRef = useRef(false);
   const restoreDecisionFocusRef = useRef(false);
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
      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      focusDetailAfterLoadRef.current = false;
      focusDetailAfterRetryRef.current = false;
      focusDetailAfterMutationRef.current = false;
      focusDetailErrorRef.current = false;
      focusActionErrorRef.current = false;
      restoreDecisionFocusRef.current = false;
      focusQueueAfterReturnRef.current = false;
      focusQueueAfterAuthorityRetryRef.current = false;

      setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
      setQueueLoading(false);
      setQueueError("");
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDecision(null);
      setModeratorNotes("");
      setRejectionReason("");
      setValidationError("");
      setMutation(null);
      setNotice("");
      setActionError("");
      setAuthorityError(
         error?.status === 401
            ? "Your session is no longer available. Sign in again or retry after authentication is restored."
            : "You no longer have Evidence Review permission for this organization.",
      );
   }, []);

   useEffect(() => {
      mountedRef.current = true;

      return () => {
         mountedRef.current = false;
         authorityGenerationRef.current += 1;
         queueRequestIdRef.current += 1;
         detailRequestIdRef.current += 1;
      };
   }, []);

   const queueUrl = useMemo(() => {
      const query = new URLSearchParams({
         organization_id: organizationId,
         evidence_status: disposition,
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });

      return `${resolveApiEndpoint("EVIDENCE_CASES")}?${query.toString()}`;
   }, [disposition, offset, organizationId]);

   useEffect(() => {
      let cancelled = false;
      const requestId = queueRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      queueRequestIdRef.current = requestId;

      authFetch(queueUrl, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               queueRequestIdRef.current !== requestId ||
               !isAuthorityGenerationCurrent(authorityGeneration)
            ) {
               return;
            }

            const count = Number(data?.count ?? 0);
            const results = Array.isArray(data?.results) ? data.results : [];
            const validOffset = count > 0 ? Math.floor((count - 1) / PAGE_SIZE) * PAGE_SIZE : 0;

            if (results.length === 0 && offset > validOffset) {
               setOffset(validOffset);
               return;
            }

            setQueue({
               count,
               limit: Number(data?.limit ?? PAGE_SIZE),
               offset: Number(data?.offset ?? offset),
               results,
            });
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

            const authorityLost = error?.status === 401 || error?.status === 403;
            if (authorityLost) {
               revokeAuthority(error);
               return;
            }
            setQueueError(
               error?.status === 403
                  ? "You no longer have permission to review evidence for this organization."
                  : (error?.message || "Unable to load the Evidence Review queue."),
            );
            setQueueLoading(false);
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, isAuthorityGenerationCurrent, offset, queueRequestVersion, queueUrl, revokeAuthority]);

   useEffect(() => {
      if (!selectedCaseId) {
         return undefined;
      }

      let cancelled = false;
      const requestId = detailRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      detailRequestIdRef.current = requestId;
      const query = new URLSearchParams({ organization_id: organizationId });
      const url = `${resolveApiEndpoint("EVIDENCE_CASE_DETAIL", selectedCaseId)}?${query.toString()}`;

      authFetch(url, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               detailRequestIdRef.current !== requestId ||
               selectedCaseIdRef.current !== selectedCaseId ||
               !isAuthorityGenerationCurrent(authorityGeneration)
            ) {
               return;
            }

            setDetail(data);
            setDetailError("");
            setDetailUnavailable(false);
            setDetailLoading(false);
         })
         .catch((error) => {
            if (
               cancelled ||
               detailRequestIdRef.current !== requestId ||
               selectedCaseIdRef.current !== selectedCaseId ||
               !isAuthorityGenerationCurrent(authorityGeneration)
            ) {
               return;
            }

            const unavailable = error?.status === 404;
            const authorityLost = error?.status === 401 || error?.status === 403;

            if (authorityLost) {
               revokeAuthority(error);
               return;
            }
            setDetail(null);
            setDetailLoading(false);
            setDetailUnavailable(unavailable);
            setDetailError(
               unavailable
                  ? "This Evidence case is no longer available."
                  : (error?.message || "Unable to load this Evidence case."),
            );
            setDecision(null);
            setActionError("");
            focusDetailAfterLoadRef.current = false;
            focusDetailAfterRetryRef.current = false;
            focusDetailErrorRef.current = true;

            if (unavailable) {
               setQueueLoading(true);
               setQueueRequestVersion((current) => current + 1);
            }

         });

      return () => {
         cancelled = true;
      };
   }, [
      authFetch,
      detailRequestVersion,
      isAuthorityGenerationCurrent,
      organizationId,
      revokeAuthority,
      selectedCaseId,
   ]);

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

      if (focusDetailAfterRetryRef.current) {
         focusDetailAfterRetryRef.current = false;
         focusDetailAfterLoadRef.current = false;
         detailHeadingRef.current?.focus();
         return;
      }

      if (focusDetailAfterLoadRef.current) {
         focusDetailAfterLoadRef.current = false;
         if (window.matchMedia("(max-width: 1180px)").matches) {
            detailHeadingRef.current?.focus();
         }
      }
   }, [detail]);

   useEffect(() => {
      if (decision) {
         if (decision === "REJECTED") {
            rejectionReasonRef.current?.focus();
         } else {
            decisionNotesRef.current?.focus();
         }
         return;
      }

      if (restoreDecisionFocusRef.current) {
         restoreDecisionFocusRef.current = false;
         decisionTriggerRef.current?.focus();
      }
   }, [decision]);

   useEffect(() => {
      if (detailError && focusDetailErrorRef.current) {
         focusDetailErrorRef.current = false;
         detailErrorRef.current?.focus();
      }
   }, [detailError]);

   useEffect(() => {
      if (actionError && focusActionErrorRef.current && actionErrorRef.current) {
         focusActionErrorRef.current = false;
         actionErrorRef.current.focus();
      }
   }, [actionError, detail]);

   useEffect(() => {
      if (!selectedCaseId && focusQueueAfterReturnRef.current) {
         focusQueueAfterReturnRef.current = false;
         queueHeadingRef.current?.focus();
      }
   }, [selectedCaseId]);

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

   const clearSelection = ({ restoreQueueFocus = false } = {}) => {
      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      focusDetailAfterLoadRef.current = false;
      focusDetailAfterRetryRef.current = false;
      focusDetailAfterMutationRef.current = false;
      focusDetailErrorRef.current = false;
      focusActionErrorRef.current = false;
      restoreDecisionFocusRef.current = false;
      focusQueueAfterReturnRef.current = restoreQueueFocus;
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDecision(null);
      setModeratorNotes("");
      setRejectionReason("");
      setValidationError("");
      setActionError("");
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

   const requestDetailRefresh = (caseId) => {
      if (authorityRevokedRef.current || !caseId || selectedCaseIdRef.current !== caseId) {
         return;
      }

      detailRequestIdRef.current += 1;
      setDetail(null);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailRequestVersion((current) => current + 1);
   };

   const handleDispositionChange = (event) => {
      queueRequestIdRef.current += 1;
      setDisposition(event.target.value);
      setOffset(0);
      setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setNotice("");
      clearSelection();
   };

   const handlePageChange = (nextOffset) => {
      if (mutation) {
         return;
      }

      queueRequestIdRef.current += 1;
      setOffset(nextOffset);
      setQueue({ count: 0, limit: PAGE_SIZE, offset: nextOffset, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setNotice("");
      clearSelection();
   };

   const handleSelectCase = (caseId) => {
      if (mutation || caseId === selectedCaseIdRef.current) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = caseId;
      focusDetailAfterLoadRef.current = true;
      focusDetailAfterRetryRef.current = false;
      setSelectedCaseId(caseId);
      setDetail(null);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setDecision(null);
      setModeratorNotes("");
      setRejectionReason("");
      setValidationError("");
      setActionError("");
      setNotice("");
   };

   const handleOpenDecision = (nextDecision, trigger) => {
      decisionTriggerRef.current = trigger;
      restoreDecisionFocusRef.current = false;
      setDecision(nextDecision);
      setModeratorNotes("");
      setRejectionReason("");
      setValidationError("");
      setActionError("");
   };

   const handleCancelDecision = () => {
      restoreDecisionFocusRef.current = true;
      setDecision(null);
      setModeratorNotes("");
      setRejectionReason("");
      setValidationError("");
      setActionError("");
   };

   const reconcileMutationConflict = (caseId, error) => {
      setDecision(null);
      setModeratorNotes("");
      setRejectionReason("");
      setValidationError("");
      requestQueueRefresh();

      if (selectedCaseIdRef.current === caseId) {
         focusActionErrorRef.current = true;
         setActionError(
            error?.message ||
               "This case changed before your decision was submitted. Review its current state before continuing.",
         );
         requestDetailRefresh(caseId);
      } else {
         setNotice(`Case ${formatCaseReference(caseId)} changed before its decision completed.`);
      }
   };

   const handleDecisionSubmit = async (event) => {
      event.preventDefault();

      if (authorityRevokedRef.current || !detail?.id || !decision || mutation) {
         return;
      }

      if (decision === "REJECTED" && !rejectionReason) {
         setValidationError("Choose a rejection reason before confirming this decision.");
         rejectionReasonRef.current?.focus();
         return;
      }

      const operation = {
         organizationId,
         caseId: detail.id,
         decision,
         authIdentity,
         authorityGeneration: authorityGenerationRef.current,
      };
      const payload = {
         decision,
         expected_status: "UNVERIFIED",
         moderator_notes: moderatorNotes.trim(),
      };

      if (decision === "REJECTED") {
         payload.rejection_reason = rejectionReason;
      }

      setMutation(operation);
      setValidationError("");
      setActionError("");
      setNotice("");

      try {
         const query = new URLSearchParams({ organization_id: operation.organizationId });
         const url = `${resolveApiEndpoint("EVIDENCE_CASE_ACTION", operation.caseId)}?${query.toString()}`;
         const updatedCase = await authFetch(url, { method: "POST", body: payload });

         if (
            operation.authIdentity !== authIdentity ||
            !isAuthorityGenerationCurrent(operation.authorityGeneration)
         ) {
            return;
         }

         if (selectedCaseIdRef.current === operation.caseId) {
            focusDetailAfterMutationRef.current = true;
            setDetail(updatedCase);
            setDetailError("");
            setDetailUnavailable(false);
            setDecision(null);
            setModeratorNotes("");
            setRejectionReason("");
         }

         setNotice(
            `Case ${formatCaseReference(operation.caseId)} was ${
               operation.decision === "VERIFIED" ? "verified" : "rejected"
            }. Claim-level adjudication remains a separate decision.`,
         );
         requestQueueRefresh();
      } catch (error) {
         if (
            !mountedRef.current ||
            operation.authIdentity !== authIdentity ||
            !isAuthorityGenerationCurrent(operation.authorityGeneration)
         ) {
            return;
         }

         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority(error);
            return;
         }
         if (error?.status === 409) {
            reconcileMutationConflict(operation.caseId, error);
         } else if (error?.status === 404) {
            setDecision(null);
            setActionError("Case unavailable. It may have moved or changed since it was opened.");
            setDetail(null);
            setDetailUnavailable(true);
            setDetailError("This Evidence case is no longer available.");
            focusDetailErrorRef.current = true;
            requestQueueRefresh();
         } else {
            focusActionErrorRef.current = true;
            setActionError(error?.message || `Unable to ${DECISION_COPY[operation.decision].label.toLowerCase()}.`);
         }
      } finally {
         if (
            mountedRef.current &&
            operation.authIdentity === authIdentity &&
            isAuthorityGenerationCurrent(operation.authorityGeneration)
         ) {
            setMutation(null);
         }
      }
   };

   const handleAuthorityRetry = () => {
      authorityGenerationRef.current += 1;
      authorityRevokedRef.current = false;
      focusQueueAfterAuthorityRetryRef.current = true;
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      setAuthorityError("");
      setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDecision(null);
      setMutation(null);
      setNotice("");
      setActionError("");
      setQueueRequestVersion((current) => current + 1);
   };

   const evidence = detail?.evidence;
   const claim = detail?.thread?.claim;
   const isActiveCase = ACTIVE_CASE_STATUSES.has(detail?.status);
   const totalPages = Math.max(1, Math.ceil(queue.count / PAGE_SIZE));
   const currentPage = queue.count === 0 ? 1 : Math.floor(offset / PAGE_SIZE) + 1;
   const hasPreviousPage = offset > 0;
   const hasNextPage = offset + PAGE_SIZE < queue.count;
   const emptyCopy = getQueueEmptyCopy(disposition);
   const evidenceUrl = safeExternalUrl(evidence?.evidence_url);
   const claimUrl = safeExternalUrl(claim?.url_link);
   const sourceUrl = safeExternalUrl(claim?.source_link);
   const mediaUrl = safeExternalUrl(claim?.media_url);
   const selectedDecisionCopy = decision ? DECISION_COPY[decision] : null;
   const isMutatingSelectedCase = mutation?.caseId === detail?.id;
   const readOnlyDecisionState = detail ? getReadOnlyDecisionState(detail, evidence) : null;

   return (
      <div className="evidence-review-panel">
         <div className="evidence-panel-intro">
            <div>
               <h3>Evidence review</h3>
               <p>Assess submitted sources before they become part of a professionally reviewed evidence set.</p>
            </div>
            <span className="evidence-organization-context">Organization: {organizationName || "Unavailable"}</span>
         </div>

         <div className="evidence-boundary-note">
            <Icons name="info" size={17} aria-hidden="true" />
            <p>
               Evidence review evaluates source suitability. Claim-level factual decisions are made separately during
               Adjudication.
            </p>
         </div>

         {authorityError ? (
            <div
               className="evidence-contained-error evidence-authority-error"
               ref={authorityErrorRef}
               tabIndex="-1"
               role="alert"
            >
               <strong>Evidence Review unavailable</strong>
               <span>{authorityError}</span>
               <button type="button" onClick={handleAuthorityRetry}>
                  Retry access
               </button>
            </div>
         ) : (
            <>
               <div className="evidence-toolbar">
            <label htmlFor="evidence-disposition-filter">
               Review history
               <select
                  id="evidence-disposition-filter"
                  value={disposition}
                  disabled={Boolean(mutation)}
                  onChange={handleDispositionChange}
               >
                  {DISPOSITION_OPTIONS.map((option) => (
                     <option key={option.value} value={option.value}>
                        {option.label}
                     </option>
                  ))}
               </select>
            </label>

            <div className="evidence-toolbar-actions">
               <span aria-live="polite">
                  {queue.count} {queue.count === 1 ? "case" : "cases"}
               </span>
               <button
                  type="button"
                  disabled={queueLoading || Boolean(mutation)}
                  onClick={() => requestQueueRefresh()}
               >
                  <Icons name="refresh-cw" size={15} aria-hidden="true" />
                  {queueLoading && queue.results.length > 0 ? "Refreshing…" : "Refresh"}
               </button>
            </div>
         </div>

         {notice && (
            <div className="evidence-notice" role="status" aria-live="polite">
               <Icons name="check-circle" size={17} aria-hidden="true" />
               <span>{notice}</span>
            </div>
         )}

               <div className={`evidence-workspace-grid ${selectedCaseId ? "has-selection" : ""}`}>
            <section className="evidence-queue" aria-labelledby="evidence-queue-heading" aria-busy={queueLoading}>
               <div className="evidence-section-heading">
                  <div>
                     <h4 id="evidence-queue-heading" ref={queueHeadingRef} tabIndex="-1">
                        {DISPOSITION_OPTIONS.find((option) => option.value === disposition)?.label} evidence
                     </h4>
                     <p>Cases are scoped to {organizationName || "the selected organization"}.</p>
                  </div>
               </div>

               {queueError && (
                  <div className="evidence-contained-error" role="alert">
                     <strong>Evidence queue unavailable</strong>
                     <span>{queueError}</span>
                     <button
                        type="button"
                        onClick={() => {
                           queueHeadingRef.current?.focus();
                           requestQueueRefresh({ preserveRows: false });
                        }}
                     >
                        Retry
                     </button>
                  </div>
               )}

               {queueLoading && queue.results.length === 0 ? (
                  <div className="evidence-state" role="status">
                     <Icons name="loader" size={21} className="evidence-spinner" aria-hidden="true" />
                     <p>Loading Evidence cases…</p>
                  </div>
               ) : !queueError && queue.results.length === 0 ? (
                  <div className="evidence-state">
                     <Icons name="paperclip" size={24} aria-hidden="true" />
                     <h5>{emptyCopy.heading}</h5>
                     <p>{emptyCopy.body}</p>
                  </div>
               ) : (
                  <ul className="evidence-case-list">
                     {queue.results.map((caseItem) => {
                        const selected = selectedCaseId === caseItem.id;
                        return (
                           <li key={caseItem.id} className="evidence-case-item">
                              <button
                                 type="button"
                                 className={`evidence-case-row ${selected ? "selected" : ""}`}
                                 aria-pressed={selected}
                                 disabled={Boolean(mutation)}
                                 onClick={() => handleSelectCase(caseItem.id)}
                              >
                                 <span className="evidence-case-row-top">
                                    <span className={`evidence-disposition disposition-${caseItem.evidence?.evidence_status?.toLowerCase() || "unknown"}`}>
                                       {getDispositionLabel(caseItem.evidence)}
                                    </span>
                                    <span className="evidence-case-status">Case: {formatLabel(caseItem.status)}</span>
                                    {selected && <span className="evidence-selected-label">Selected</span>}
                                 </span>
                                 <strong>{getEvidenceTitle(caseItem)}</strong>
                                 <span className="evidence-type">{caseItem.evidence?.evidence_type_label || "Evidence type unavailable"}</span>
                                 <span className="evidence-claim-preview">{getClaimContext(caseItem)}</span>
                                 <span className="evidence-case-row-meta">
                                    <span>
                                       Submitted <FormattedDateTime value={caseItem.evidence?.submitted_at} />
                                    </span>
                                    <span>
                                       {caseItem.evidence?.contributor?.username
                                          ? `Contributor @${caseItem.evidence.contributor.username}`
                                          : "Contributor not recorded"}
                                    </span>
                                    <span>Case {formatCaseReference(caseItem.id)}</span>
                                 </span>
                              </button>
                           </li>
                        );
                     })}
                  </ul>
               )}

               <nav className="evidence-pagination" aria-label="Evidence queue pagination">
                  <button
                     type="button"
                     disabled={!hasPreviousPage || queueLoading || Boolean(mutation)}
                     onClick={() => handlePageChange(Math.max(0, offset - PAGE_SIZE))}
                  >
                     <Icons name="chevron-left" size={15} aria-hidden="true" />
                     Previous
                  </button>
                  <span>
                     Page {currentPage} of {totalPages}
                  </span>
                  <button
                     type="button"
                     disabled={!hasNextPage || queueLoading || Boolean(mutation)}
                     onClick={() => handlePageChange(offset + PAGE_SIZE)}
                  >
                     Next
                     <Icons name="chevron-right" size={15} aria-hidden="true" />
                  </button>
               </nav>
            </section>

            <section className="evidence-detail" aria-labelledby="evidence-detail-heading" aria-busy={detailLoading}>
               {selectedCaseId && (
                  <button
                     type="button"
                     className="evidence-return-to-queue"
                     disabled={Boolean(mutation)}
                     onClick={() => clearSelection({ restoreQueueFocus: true })}
                  >
                     <Icons name="arrow-left" size={15} aria-hidden="true" />
                     Return to queue
                  </button>
               )}

               {!selectedCaseId ? (
                  <div className="evidence-state evidence-detail-empty">
                     <Icons name="file-text" size={25} aria-hidden="true" />
                     <h4 id="evidence-detail-heading">Select submitted evidence</h4>
                     <p>Choose a case to inspect its source, claim context, provenance, and review history.</p>
                  </div>
               ) : detailLoading ? (
                  <div className="evidence-state" role="status">
                     <Icons name="loader" size={21} className="evidence-spinner" aria-hidden="true" />
                     <h4 id="evidence-detail-heading">Loading evidence detail</h4>
                     <p>Retrieving the authoritative case record…</p>
                  </div>
               ) : detailError ? (
                  <div className="evidence-contained-error" ref={detailErrorRef} tabIndex="-1" role="alert">
                     <strong id="evidence-detail-heading">{detailUnavailable ? "Case unavailable" : "Evidence detail unavailable"}</strong>
                     <span>{detailError}</span>
                     <div className="evidence-error-actions">
                        {!detailUnavailable && (
                           <button
                              type="button"
                              onClick={() => {
                                 focusDetailAfterRetryRef.current = true;
                                 requestDetailRefresh(selectedCaseId);
                              }}
                           >
                              Retry detail
                           </button>
                        )}
                        <button type="button" className="secondary" onClick={() => clearSelection({ restoreQueueFocus: true })}>
                           Return to queue
                        </button>
                     </div>
                  </div>
               ) : detail ? (
                  <div className="evidence-detail-content">
                     <header className="evidence-detail-header">
                        <div>
                           <span className="evidence-detail-eyebrow">Evidence case {formatCaseReference(detail.id)}</span>
                           <h4 id="evidence-detail-heading" ref={detailHeadingRef} tabIndex="-1">
                              {getEvidenceTitle(detail)}
                           </h4>
                           <span className="evidence-full-case-id">Case ID: {detail.id}</span>
                        </div>
                        <div className="evidence-detail-badges">
                           <span className={`evidence-disposition disposition-${evidence?.evidence_status?.toLowerCase() || "unknown"}`}>
                              Evidence: {getDispositionLabel(evidence)}
                           </span>
                           <span className="evidence-case-status">Case: {formatLabel(detail.status)}</span>
                        </div>
                     </header>

                     {actionError && (
                        <div className="evidence-action-error" ref={actionErrorRef} tabIndex="-1" role="alert">
                           <Icons name="alert-circle" size={17} aria-hidden="true" />
                           <span>{actionError}</span>
                        </div>
                     )}

                     <section className="evidence-detail-section" aria-labelledby="submitted-evidence-heading">
                        <div className="evidence-subheading-row evidence-major-section-heading">
                           <div>
                              <h5 id="submitted-evidence-heading">Submitted evidence</h5>
                              <p>Review the submitted source directly and assess its suitability.</p>
                           </div>
                           {evidenceUrl && (
                              <a href={evidenceUrl} target="_blank" rel="noopener noreferrer" className="evidence-external-link">
                                 Open submitted source
                                 <Icons name="external-link" size={13} aria-hidden="true" />
                              </a>
                           )}
                        </div>

                        <p className="evidence-reading-text">{evidence?.evidence_caption || "No evidence caption was provided."}</p>
                        <dl className="evidence-source-record">
                           <div>
                              <dt>Source</dt>
                              <dd className="evidence-url-text">{evidence?.evidence_url || "Source URL unavailable"}</dd>
                           </div>
                        </dl>
                        {!evidenceUrl && evidence?.evidence_url && (
                           <p className="evidence-inline-warning">The submitted URL cannot be opened because it is not a supported HTTP(S) address.</p>
                        )}
                        <dl className="evidence-provenance">
                           <div>
                              <dt>Submitted by</dt>
                              <dd>{evidence?.contributor?.username ? `@${evidence.contributor.username}` : "Not recorded"}</dd>
                           </div>
                           <div>
                              <dt>Submitted</dt>
                              <dd><FormattedDateTime value={evidence?.submitted_at} /></dd>
                           </div>
                        </dl>
                        <details className="evidence-record-disclosure">
                           <summary>Evidence details</summary>
                           <dl className="evidence-record-details">
                              <div>
                                 <dt>Evidence type</dt>
                                 <dd>{evidence?.evidence_type_label || "Unavailable"}</dd>
                              </div>
                           </dl>
                        </details>
                     </section>

                     <section className="evidence-detail-section" aria-labelledby="claim-context-heading">
                        <div className="evidence-subheading-row evidence-major-section-heading">
                           <div>
                              <h5 id="claim-context-heading">Claim context</h5>
                              <p>Evidence suitability is reviewed in the context of this investigation.</p>
                           </div>
                           {detail.thread?.id && (
                              <Link to={`/thread/detail/${detail.thread.id}`} className="evidence-thread-link">
                                 View full thread
                                 <Icons name="arrow-right" size={13} aria-hidden="true" />
                              </Link>
                           )}
                        </div>
                        <p className="evidence-reading-text">{claim?.context_text || detail.thread?.caption || "Claim context unavailable"}</p>
                        <div className="evidence-context-links">
                           {claimUrl && <a href={claimUrl} target="_blank" rel="noopener noreferrer">Open original claim URL <Icons name="external-link" size={12} aria-hidden="true" /></a>}
                           {sourceUrl && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Open claim source <Icons name="external-link" size={12} aria-hidden="true" /></a>}
                           {mediaUrl && <a href={mediaUrl} target="_blank" rel="noopener noreferrer">Open claim media <Icons name="external-link" size={12} aria-hidden="true" /></a>}
                        </div>
                        <details className="evidence-record-disclosure">
                           <summary>Claim details</summary>
                           <dl className="evidence-record-details">
                              <div>
                                 <dt>Claim type</dt>
                                 <dd>{formatLabel(claim?.claim_type)}</dd>
                              </div>
                              <div>
                                 <dt>Thread caption</dt>
                                 <dd>{detail.thread?.caption || "Unavailable"}</dd>
                              </div>
                           </dl>
                        </details>
                     </section>

                     <section className="evidence-detail-section" aria-labelledby="review-state-heading">
                        <div className="evidence-subheading-row evidence-major-section-heading">
                           <div>
                              <h5 id="review-state-heading">Review state</h5>
                              <p>Evidence disposition and case lifecycle are separate records.</p>
                           </div>
                        </div>
                        <dl className="evidence-review-status">
                           <div>
                              <dt>Evidence disposition</dt>
                              <dd>
                                 <span className={`evidence-disposition disposition-${evidence?.evidence_status?.toLowerCase() || "unknown"}`}>
                                    {getDispositionLabel(evidence)}
                                 </span>
                              </dd>
                           </div>
                           <div>
                              <dt>Case lifecycle</dt>
                              <dd><span className="evidence-case-status">{formatLabel(detail.status)}</span></dd>
                           </div>
                        </dl>
                        <dl className="evidence-review-provenance">
                           <div>
                              <dt>Reviewer</dt>
                              <dd>{detail.verified_by?.username ? `@${detail.verified_by.username}` : "Reviewer not recorded"}</dd>
                           </div>
                           <div>
                              <dt>Review date</dt>
                              <dd>
                                 <FormattedDateTime
                                    value={detail.verified_at}
                                    fallback="Review date not recorded"
                                 />
                              </dd>
                           </div>
                        </dl>
                        {evidence?.evidence_status === "REJECTED" && (
                           <dl className="evidence-review-outcome">
                              <div>
                                 <dt>Rejection reason</dt>
                                 <dd>{detail.rejection_reason_label || "Historical rejection reason unavailable"}</dd>
                              </div>
                           </dl>
                        )}
                        <div className="evidence-review-notes">
                           <strong>Moderator notes</strong>
                           <p>{detail.moderator_notes || "No review notes were recorded."}</p>
                        </div>
                     </section>

                     <section className="evidence-decision-section" aria-labelledby="evidence-decision-heading">
                        <div className="evidence-subheading-row evidence-major-section-heading">
                           <div>
                              <h5 id="evidence-decision-heading">Evidence decision</h5>
                              <p>Decide source suitability only. Adjudication determines the claim-level conclusion later.</p>
                           </div>
                        </div>

                        {!isActiveCase || evidence?.evidence_status !== "UNVERIFIED" ? (
                           <div className="evidence-readonly-state" role="status">
                              <Icons
                                 name={
                                    detail.status === "CANCELLED" || !evidence?.evidence_status
                                       ? "alert-circle"
                                       : "check-circle"
                                 }
                                 size={18}
                                 aria-hidden="true"
                              />
                              <div>
                                 <strong>{readOnlyDecisionState.heading}</strong>
                                 <span>{readOnlyDecisionState.body}</span>
                              </div>
                           </div>
                        ) : evidence?.is_self_submission ? (
                           <div className="evidence-readonly-state">
                              <Icons name="lock" size={18} aria-hidden="true" />
                              <div>
                                 <strong>Self-submission is read-only</strong>
                                 <span>You cannot review evidence that you submitted.</span>
                              </div>
                           </div>
                        ) : !canReviewEvidence ? (
                           <div className="evidence-readonly-state">
                              <Icons name="lock" size={18} aria-hidden="true" />
                              <div>
                                 <strong>Review permission required</strong>
                                 <span>This organization membership does not grant Evidence Review authority.</span>
                              </div>
                           </div>
                        ) : !decision ? (
                           <div className="evidence-decision-options">
                              <button
                                 type="button"
                                 disabled={Boolean(mutation)}
                                 onClick={(event) => handleOpenDecision("VERIFIED", event.currentTarget)}
                              >
                                 Verify evidence
                              </button>
                              <button
                                 type="button"
                                 className="danger"
                                 disabled={Boolean(mutation)}
                                 onClick={(event) => handleOpenDecision("REJECTED", event.currentTarget)}
                              >
                                 Reject evidence
                              </button>
                           </div>
                        ) : (
                           <form className="evidence-decision-form" onSubmit={handleDecisionSubmit} aria-busy={isMutatingSelectedCase}>
                              <div className="evidence-decision-summary">
                                 <span>Case {formatCaseReference(detail.id)}</span>
                                 <strong>{selectedDecisionCopy.heading}</strong>
                                 <p id="evidence-decision-consequence">{selectedDecisionCopy.consequence}</p>
                              </div>

                              {decision === "REJECTED" && (
                                 <label htmlFor="evidence-rejection-reason">
                                    Rejection reason
                                    <select
                                       ref={rejectionReasonRef}
                                       id="evidence-rejection-reason"
                                       value={rejectionReason}
                                       required
                                       disabled={isMutatingSelectedCase}
                                       aria-invalid={Boolean(validationError)}
                                       aria-describedby={
                                          validationError
                                             ? "evidence-decision-consequence evidence-rejection-reason-error"
                                             : "evidence-decision-consequence"
                                       }
                                       onChange={(event) => {
                                          setRejectionReason(event.target.value);
                                          setValidationError("");
                                       }}
                                    >
                                       <option value="">Choose a reason</option>
                                       {REJECTION_REASONS.map((reason) => (
                                          <option key={reason.value} value={reason.value}>{reason.label}</option>
                                       ))}
                                    </select>
                                 </label>
                              )}

                              <label htmlFor="evidence-moderator-notes">
                                 Moderator notes <span>(optional)</span>
                                 <textarea
                                    ref={decisionNotesRef}
                                    id="evidence-moderator-notes"
                                    value={moderatorNotes}
                                    rows={5}
                                    maxLength={2000}
                                    disabled={isMutatingSelectedCase}
                                    aria-describedby="evidence-decision-consequence evidence-notes-count"
                                    onChange={(event) => setModeratorNotes(event.target.value)}
                                 />
                              </label>
                              <span id="evidence-notes-count" className="evidence-notes-count">{moderatorNotes.length}/2000</span>

                              {validationError && (
                                 <p
                                    id="evidence-rejection-reason-error"
                                    className="evidence-form-error"
                                    role="alert"
                                 >
                                    {validationError}
                                 </p>
                              )}

                              <div className="evidence-decision-controls">
                                 <button type="button" className="secondary" disabled={isMutatingSelectedCase} onClick={handleCancelDecision}>
                                    Cancel
                                 </button>
                                 <button type="submit" className={decision === "REJECTED" ? "danger" : "primary"} disabled={isMutatingSelectedCase}>
                                    {isMutatingSelectedCase ? "Submitting…" : `Confirm ${selectedDecisionCopy.label.toLowerCase()}`}
                                 </button>
                              </div>
                           </form>
                        )}
                     </section>

                     <section className="evidence-detail-section" aria-labelledby="evidence-history-heading">
                        <div className="evidence-subheading-row evidence-major-section-heading">
                           <div>
                              <h5 id="evidence-history-heading">Audit history</h5>
                              <p>Recent case events supplied by the authoritative Evidence Review record.</p>
                           </div>
                        </div>
                        {Array.isArray(detail.events) && detail.events.length > 0 ? (
                           <details className="evidence-history-disclosure">
                              <summary>
                                 <span>Case events</span>
                                 <span>{detail.events.length} {detail.events.length === 1 ? "event" : "events"}</span>
                              </summary>
                              <ol className="evidence-event-list">
                                 {detail.events.map((event, index) => (
                                    <li key={`${event.event_type}-${event.created_at}-${index}`}>
                                       <span className="evidence-event-marker" aria-hidden="true" />
                                       <div>
                                          <div className="evidence-event-heading">
                                             <strong>{formatLabel(event.event_type)}</strong>
                                             <FormattedDateTime value={event.created_at} />
                                          </div>
                                          <p>Actor: {event.actor?.username ? `@${event.actor.username}` : "Actor not displayed"}</p>
                                          {(event.from_status || event.to_status) && (
                                             <p>Case transition: {formatLabel(event.from_status, "None")} → {formatLabel(event.to_status, "None")}</p>
                                          )}
                                          {event.reason_code && <p>Reason: {formatLabel(event.reason_code)}</p>}
                                          {event.notes && <p>Notes: {event.notes}</p>}
                                       </div>
                                    </li>
                                 ))}
                              </ol>
                           </details>
                        ) : (
                           <p className="evidence-inline-empty">No case audit history is available.</p>
                        )}
                     </section>
                  </div>
               ) : null}
            </section>
               </div>
            </>
         )}
      </div>
   );
}

function EvidenceReviewPanel(props) {
   const { authFetch, token, user } = useAuth();
   const authIdentity = getAuthIdentity(user, token);

   return (
      <EvidenceReviewContent
         key={`${props.organizationId}:${authIdentity}`}
         {...props}
         authFetch={authFetch}
         authIdentity={authIdentity}
      />
   );
}

export default EvidenceReviewPanel;
