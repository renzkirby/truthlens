import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

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

const VERDICT_OPTIONS = [
   { value: "FACT", label: "Fact" },
   { value: "FAKE", label: "Fake" },
   { value: "MISLEADING", label: "Misleading" },
   { value: "SATIRE", label: "Satire" },
   { value: "UNVERIFIED", label: "Unverified" },
];

const EMPTY_DECISION_DRAFT = {
   verdict: "",
   canonicalClaim: "",
   rationale: "",
};

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

function identifiersMatch(first, second) {
   return first !== null && first !== undefined && second !== null && second !== undefined && String(first) === String(second);
}

function getSafeHttpUrl(value) {
   if (!value) {
      return null;
   }

   try {
      const parsedUrl = new URL(value);
      return parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:" ? parsedUrl.href : null;
   } catch {
      return null;
   }
}

function MinimalUser({ user, fallback = "Not recorded" }) {
   return user?.username ? `@${user.username}` : fallback;
}

function DecisionRecord({ decision, current = false }) {
   const provenance = decision?.provenance || {};

   return (
      <article className="adjudication-decision-record">
         <div className="adjudication-record-heading">
            <h6>{current ? "Current decision" : `Revision ${decision?.revision_number ?? "unavailable"}`}</h6>
            <span>{decision?.verdict_label || formatLabel(decision?.verdict, "Verdict unavailable")}</span>
         </div>

         <dl className="adjudication-detail-facts compact">
            <div>
               <dt>Revision</dt>
               <dd>{decision?.revision_number ?? "Not recorded"}</dd>
            </div>
            <div>
               <dt>Recorded by</dt>
               <dd>
                  {provenance.is_attributable ? (
                     <MinimalUser user={decision?.decided_by} fallback="Actor not recorded" />
                  ) : (
                     "Attribution unavailable"
                  )}
               </dd>
            </div>
            <div>
               <dt>Organization</dt>
               <dd>{decision?.organization?.name || "Organization not recorded"}</dd>
            </div>
            <div>
               <dt>Decision date</dt>
               <dd><FormattedDateTime value={decision?.decided_at} fallback="Decision date not recorded" /></dd>
            </div>
            <div>
               <dt>Provenance</dt>
               <dd>{formatLabel(provenance.status, "Provenance unavailable")}</dd>
            </div>
            <div>
               <dt>Verification run</dt>
               <dd>{decision?.verification_run_id || "Not recorded"}</dd>
            </div>
         </dl>

         <div className="adjudication-reading-block">
            <strong>Canonical wording</strong>
            <p>{decision?.canonical_claim || "Canonical wording unavailable."}</p>
         </div>
         <div className="adjudication-reading-block">
            <strong>Rationale</strong>
            <p>{decision?.rationale || "Rationale unavailable."}</p>
         </div>
      </article>
   );
}

function SafeExternalLink({ value, children, className = "" }) {
   const safeUrl = getSafeHttpUrl(value);

   if (!safeUrl) {
      return null;
   }

   return (
      <a href={safeUrl} target="_blank" rel="noopener noreferrer" className={className}>
         {children}
         <Icons name="external-link" size={13} aria-hidden="true" />
      </a>
   );
}

function EvidenceRecord({ evidence }) {
   const safeEvidenceUrl = getSafeHttpUrl(evidence?.evidence_url);
   const rejected = evidence?.evidence_status === "REJECTED";
   const evidenceStatusTone =
      evidence?.evidence_status === "VERIFIED"
         ? "verified"
         : rejected
           ? "rejected"
           : evidence?.evidence_status === "UNVERIFIED"
             ? "unreviewed"
             : "neutral";

   return (
      <li className="adjudication-evidence-record">
         <div className="adjudication-record-heading">
            <h6>{evidence?.evidence_caption || "Untitled evidence submission"}</h6>
            <span className={`adjudication-evidence-status adjudication-evidence-status--${evidenceStatusTone}`}>
               {evidence?.evidence_status_label || formatLabel(evidence?.evidence_status)}
            </span>
         </div>

         <dl className="adjudication-detail-facts compact">
            <div>
               <dt>Evidence type</dt>
               <dd>{evidence?.evidence_type_label || formatLabel(evidence?.evidence_type)}</dd>
            </div>
            <div>
               <dt>Submitted</dt>
               <dd><FormattedDateTime value={evidence?.submitted_at} /></dd>
            </div>
            <div>
               <dt>Contributor</dt>
               <dd><MinimalUser user={evidence?.contributor} /></dd>
            </div>
            <div>
               <dt>Reviewed by</dt>
               <dd><MinimalUser user={evidence?.reviewed_by} fallback="Reviewer not recorded" /></dd>
            </div>
            <div>
               <dt>Reviewed</dt>
               <dd><FormattedDateTime value={evidence?.reviewed_at} fallback="Review date not recorded" /></dd>
            </div>
            <div>
               <dt>Evidence ID</dt>
               <dd>{evidence?.id || "Unavailable"}</dd>
            </div>
         </dl>

         {evidence?.is_current_user_contributor && (
            <p className="adjudication-inline-warning">
               You contributed this evidence. The authoritative action state accounts for direct-contribution conflicts.
            </p>
         )}

         <div className="adjudication-source-row">
            <span className="adjudication-url-text">{evidence?.evidence_url || "Source URL unavailable"}</span>
            {safeEvidenceUrl && (
               <SafeExternalLink value={safeEvidenceUrl} className="adjudication-external-link">
                  Open evidence source
               </SafeExternalLink>
            )}
         </div>
         {!safeEvidenceUrl && evidence?.evidence_url && (
            <p className="adjudication-inline-warning">This source cannot be opened because it is not a supported HTTP(S) address.</p>
         )}

         <div className="adjudication-review-outcome">
            {rejected && (
               <p>
                  <strong>Rejection reason:</strong>{" "}
                  {evidence?.rejection_reason_label || formatLabel(evidence?.rejection_reason, "Not recorded")}
                  {evidence?.rejection_reason && ` (${evidence.rejection_reason})`}
               </p>
            )}
            <p><strong>Review notes:</strong> {evidence?.review_notes || "No review notes were recorded."}</p>
         </div>
      </li>
   );
}

function EventRecord({ event }) {
   const hasTransition = event?.from_status || event?.to_status;

   return (
      <li className="adjudication-event-record">
         <span className="adjudication-event-marker" aria-hidden="true" />
         <div>
            <div className="adjudication-event-heading">
               <strong>{event?.event_type_label || formatLabel(event?.event_type, "Case event")}</strong>
               <FormattedDateTime value={event?.created_at} />
            </div>
            <p>Actor: <MinimalUser user={event?.actor} fallback="Actor not displayed" /></p>
            {hasTransition && (
               <p>
                  Case transition: {formatLabel(event?.from_status, "None")} → {formatLabel(event?.to_status, "None")}
               </p>
            )}
            {event?.reason_code && <p>Reason: {formatLabel(event.reason_code)}</p>}
            {event?.notes && <p>Notes: {event.notes}</p>}
         </div>
      </li>
   );
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

function buildAdjudicationCaseUrl(caseId, organizationId, suffix = "") {
   const query = new URLSearchParams({ organization_id: organizationId });
   return `${resolveApiEndpoint("ADJUDICATION_CASES")}${encodeURIComponent(caseId)}/${suffix}?${query.toString()}`;
}

function getFirstDecisionContract(caseDetail, organizationId) {
   const actionState = caseDetail?.action_state || {};
   const preconditions = actionState.preconditions || {};
   const expectedRevisionIsValid = Number.isInteger(actionState.expected_revision) && actionState.expected_revision >= 0;
   const preconditionsAreValid =
      expectedRevisionIsValid &&
      identifiersMatch(preconditions.case_id, caseDetail?.id) &&
      identifiersMatch(preconditions.organization_id, organizationId) &&
      preconditions.expected_revision === actionState.expected_revision;

   return {
      actionState,
      preconditions,
      expectedRevision: actionState.expected_revision,
      preconditionsAreValid,
      ready: actionState.can_issue_first_decision === true && preconditionsAreValid,
   };
}

function normalizeServerMessage(value) {
   if (Array.isArray(value)) {
      return value.map(normalizeServerMessage).filter(Boolean).join(" ");
   }
   if (typeof value === "string") {
      return value;
   }
   if (value && typeof value === "object" && typeof value.detail === "string") {
      return value.detail;
   }
   return "";
}

function getActionValidationErrors(error) {
   const fieldErrors = {};
   const fieldMap = {
      moderator_verdict: "verdict",
      canonical_claim: "canonicalClaim",
      moderator_notes: "rationale",
   };

   Object.entries(fieldMap).forEach(([serverField, localField]) => {
      const message = normalizeServerMessage(error?.[serverField]);
      if (message) {
         fieldErrors[localField] = message;
      }
   });

   const generalMessage =
      normalizeServerMessage(error?.expected_revision) ||
      normalizeServerMessage(error?.non_field_errors) ||
      error?.message ||
      "The decision could not be submitted. Review the fields and try again.";

   return { fieldErrors, generalMessage };
}

function AdjudicationReviewContent({
   authFetch,
   authIdentity,
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
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(false);
   const [detailError, setDetailError] = useState("");
   const [detailUnavailable, setDetailUnavailable] = useState(false);
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);
   const [detailIdentity, setDetailIdentity] = useState(null);
   const [authorityError, setAuthorityError] = useState("");
   const [decisionDraft, setDecisionDraft] = useState(EMPTY_DECISION_DRAFT);
   const [decisionErrors, setDecisionErrors] = useState({});
   const [decisionFormOpen, setDecisionFormOpen] = useState(false);
   const [confirmation, setConfirmation] = useState(null);
   const [confirmationChecking, setConfirmationChecking] = useState(false);
   const [mutation, setMutation] = useState(null);
   const [actionNotice, setActionNotice] = useState(null);
   const [actionError, setActionError] = useState("");
   const [reconciliationPending, setReconciliationPending] = useState(null);

   const mountedRef = useRef(true);
   const panelRef = useRef(null);
   const authorityGenerationRef = useRef(0);
   const authorityRevokedRef = useRef(false);
   const queueRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const reconciliationRequestIdRef = useRef(0);
   const selectedCaseIdRef = useRef(null);
   const originatingQueueCaseIdRef = useRef(null);
   const returnFocusCaseIdRef = useRef(null);
   const queueRowRefs = useRef(new Map());
   const queueHeadingRef = useRef(null);
   const selectedCaseHeadingRef = useRef(null);
   const authorityErrorRef = useRef(null);
   const detailErrorRef = useRef(null);
   const focusSelectedCaseRef = useRef(false);
   const focusDetailErrorRef = useRef(false);
   const focusQueueAfterReturnRef = useRef(false);
   const focusQueueAfterAuthorityRetryRef = useRef(false);
   const decisionTriggerRef = useRef(null);
   const firstVerdictRef = useRef(null);
   const canonicalClaimRef = useRef(null);
   const rationaleRef = useRef(null);
   const decisionFocusTargetRef = useRef("verdict");
   const confirmationHeadingRef = useRef(null);
   const actionMessageRef = useRef(null);
   const confirmationCandidateRef = useRef(null);
   const focusDecisionFormRef = useRef(false);
   const focusConfirmationRef = useRef(false);
   const focusActionMessageRef = useRef(false);
   const focusDetailAfterMutationRef = useRef(false);
   const restoreDecisionTriggerFocusRef = useRef(false);

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
      reconciliationRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      originatingQueueCaseIdRef.current = null;
      returnFocusCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusDetailErrorRef.current = false;
      focusQueueAfterReturnRef.current = false;
      focusQueueAfterAuthorityRetryRef.current = false;
      confirmationCandidateRef.current = null;
      focusDecisionFormRef.current = false;
      focusConfirmationRef.current = false;
      focusActionMessageRef.current = false;
      focusDetailAfterMutationRef.current = false;
      restoreDecisionTriggerFocusRef.current = false;

      setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
      setQueueLoading(false);
      setQueueError("");
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailIdentity(null);
      setDecisionDraft(EMPTY_DECISION_DRAFT);
      setDecisionErrors({});
      setDecisionFormOpen(false);
      setConfirmation(null);
      setConfirmationChecking(false);
      setMutation(null);
      setActionNotice(null);
      setActionError("");
      setReconciliationPending(null);
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
         detailRequestIdRef.current += 1;
         reconciliationRequestIdRef.current += 1;
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

            // A selected detail remains an explicit case identity even when a
            // same-filter queue refresh no longer includes it.
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
      if (!canAdjudicate || !organizationId || !selectedCaseId || authorityRevokedRef.current) {
         return undefined;
      }

      let cancelled = false;
      const requestId = detailRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      const requestOrganizationId = organizationId;
      const requestCaseId = selectedCaseId;
      const requestPrincipal = authIdentity;
      const detailUrl = buildAdjudicationCaseUrl(requestCaseId, requestOrganizationId);
      detailRequestIdRef.current = requestId;

      authFetch(detailUrl, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               detailRequestIdRef.current !== requestId ||
               !isAuthorityGenerationCurrent(authorityGeneration) ||
               requestPrincipal !== authIdentity ||
               !identifiersMatch(requestOrganizationId, organizationId) ||
               !identifiersMatch(requestCaseId, selectedCaseIdRef.current)
            ) {
               return;
            }

            if (
               !identifiersMatch(data?.id, requestCaseId) ||
               !identifiersMatch(data?.organization?.id, requestOrganizationId)
            ) {
               confirmationCandidateRef.current = null;
               focusDetailErrorRef.current = true;
               setDetail(null);
               setDetailIdentity(null);
               setDetailError("The selected case response did not match the requested organization and case.");
               setDetailUnavailable(false);
               setDetailLoading(false);
               setConfirmationChecking(false);
               return;
            }

            const nextDetailIdentity = {
               principal: requestPrincipal,
               organizationId: requestOrganizationId,
               caseId: requestCaseId,
               authorityGeneration,
               requestId,
            };
            const candidate = confirmationCandidateRef.current;
            setDetail(data);
            setDetailIdentity(nextDetailIdentity);
            setDetailError("");
            setDetailUnavailable(false);
            setDetailLoading(false);

            if (candidate) {
               confirmationCandidateRef.current = null;
               setConfirmationChecking(false);
               const freshContract = getFirstDecisionContract(data, requestOrganizationId);
               const candidateIsCurrent =
                  candidate.principal === requestPrincipal &&
                  candidate.authorityGeneration === authorityGeneration &&
                  identifiersMatch(candidate.organizationId, requestOrganizationId) &&
                  identifiersMatch(candidate.caseId, requestCaseId) &&
                  candidate.expectedRevision === freshContract.expectedRevision;

               if (candidateIsCurrent && freshContract.ready) {
                  setConfirmation({ ...candidate, detailRequestId: requestId });
                  focusConfirmationRef.current = true;
               } else {
                  setDecisionFormOpen(false);
                  setConfirmation(null);
                  focusActionMessageRef.current = true;
                  setActionError(
                     "This case changed while the decision was being prepared. Review the refreshed readiness and begin again.",
                  );
               }
            }
         })
         .catch((error) => {
            if (
               cancelled ||
               detailRequestIdRef.current !== requestId ||
               !isAuthorityGenerationCurrent(authorityGeneration) ||
               requestPrincipal !== authIdentity ||
               !identifiersMatch(requestOrganizationId, organizationId) ||
               !identifiersMatch(requestCaseId, selectedCaseIdRef.current)
            ) {
               return;
            }

            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority(error);
               return;
            }

            const unavailable = error?.status === 404;
            const confirmationAttempt = confirmationCandidateRef.current;
            confirmationCandidateRef.current = null;
            focusDetailErrorRef.current = true;
            setDetailIdentity(null);
            setDetailError(
               unavailable
                  ? "This Adjudication case is no longer available for the selected organization."
                  : (error?.message || "Unable to load the selected Adjudication case."),
            );
            setDetailUnavailable(unavailable);
            setDetailLoading(false);
            setConfirmationChecking(false);
            setConfirmation(null);
            if (confirmationAttempt && !unavailable) {
               setDecisionFormOpen(true);
               setDecisionErrors({
                  general: "Canonical detail could not be refreshed. Retry the case refresh before reviewing this decision again.",
               });
            } else if (unavailable) {
               setDecisionFormOpen(false);
            }

            if (unavailable) {
               setDetail(null);
               queueRequestIdRef.current += 1;
               setQueueLoading(true);
               setQueueError("");
               setQueueRequestVersion((current) => current + 1);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [
      authFetch,
      authIdentity,
      canAdjudicate,
      detailRequestVersion,
      isAuthorityGenerationCurrent,
      organizationId,
      revokeAuthority,
      selectedCaseId,
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

         if ((panelRef.current?.getBoundingClientRect().width || Number.POSITIVE_INFINITY) <= 920) {
            selectedCaseHeadingRef.current?.focus();
         }
         return;
      }

      if (!selectedCaseId && focusQueueAfterReturnRef.current) {
         focusQueueAfterReturnRef.current = false;
         const caseId = returnFocusCaseIdRef.current;
         returnFocusCaseIdRef.current = null;
         const originatingRow = caseId ? queueRowRefs.current.get(String(caseId)) : null;
         (originatingRow || queueHeadingRef.current)?.focus();
      }
   }, [selectedCaseId]);

   useEffect(() => {
      if (detailError && focusDetailErrorRef.current) {
         focusDetailErrorRef.current = false;
         detailErrorRef.current?.focus();
      }
   }, [detailError]);

   useEffect(() => {
      if (decisionFormOpen && focusDecisionFormRef.current) {
         focusDecisionFormRef.current = false;
         const focusTargets = {
            verdict: firstVerdictRef,
            canonicalClaim: canonicalClaimRef,
            rationale: rationaleRef,
         };
         (focusTargets[decisionFocusTargetRef.current] || firstVerdictRef).current?.focus();
      }
   }, [decisionFormOpen]);

   useEffect(() => {
      if (confirmation && focusConfirmationRef.current) {
         focusConfirmationRef.current = false;
         confirmationHeadingRef.current?.focus();
      }
   }, [confirmation]);

   useEffect(() => {
      if (
         !decisionFormOpen &&
         !confirmation &&
         !confirmationChecking &&
         restoreDecisionTriggerFocusRef.current
      ) {
         restoreDecisionTriggerFocusRef.current = false;
         decisionTriggerRef.current?.focus();
      }
   }, [confirmation, confirmationChecking, decisionFormOpen]);

   useEffect(() => {
      if ((actionError || actionNotice) && focusActionMessageRef.current) {
         focusActionMessageRef.current = false;
         actionMessageRef.current?.focus();
      }
   }, [actionError, actionNotice]);

   useEffect(() => {
      if (detail && focusDetailAfterMutationRef.current) {
         focusDetailAfterMutationRef.current = false;
         selectedCaseHeadingRef.current?.focus();
      }
   }, [detail]);

   const resetDecisionWorkflow = ({ clearMessages = true } = {}) => {
      confirmationCandidateRef.current = null;
      focusDecisionFormRef.current = false;
      focusConfirmationRef.current = false;
      setDecisionDraft(EMPTY_DECISION_DRAFT);
      setDecisionErrors({});
      setDecisionFormOpen(false);
      setConfirmation(null);
      setConfirmationChecking(false);
      if (clearMessages) {
         setActionNotice(null);
         setActionError("");
         setReconciliationPending(null);
      }
   };

   const clearSelection = ({ restoreQueueFocus = false } = {}) => {
      const caseId = originatingQueueCaseIdRef.current || selectedCaseIdRef.current;
      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      originatingQueueCaseIdRef.current = null;
      returnFocusCaseIdRef.current = restoreQueueFocus ? caseId : null;
      focusSelectedCaseRef.current = false;
      focusDetailErrorRef.current = false;
      focusQueueAfterReturnRef.current = restoreQueueFocus;
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailIdentity(null);
      resetDecisionWorkflow({ clearMessages: false });
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

   const isOperationContextCurrent = (operation) =>
      operation &&
      operation.principal === authIdentity &&
      identifiersMatch(operation.organizationId, organizationId) &&
      isAuthorityGenerationCurrent(operation.authorityGeneration);

   const reconcileDecisionOperation = async (operation, outcome, serverMessage = "") => {
      if (!isOperationContextCurrent(operation)) {
         return;
      }

      const reconciliationId = reconciliationRequestIdRef.current + 1;
      reconciliationRequestIdRef.current = reconciliationId;
      let selectedDetailRequestId = null;

      if (identifiersMatch(selectedCaseIdRef.current, operation.caseId)) {
         selectedDetailRequestId = detailRequestIdRef.current + 1;
         detailRequestIdRef.current = selectedDetailRequestId;
         setDetailIdentity(null);
         setDetailLoading(true);
         setDetailError("");
         setDetailUnavailable(false);
      }

      setReconciliationPending(null);

      try {
         const canonicalDetail = await authFetch(
            buildAdjudicationCaseUrl(operation.caseId, operation.organizationId),
            { method: "GET" },
         );

         if (
            reconciliationRequestIdRef.current !== reconciliationId ||
            !isOperationContextCurrent(operation)
         ) {
            return;
         }

         if (
            !identifiersMatch(canonicalDetail?.id, operation.caseId) ||
            !identifiersMatch(canonicalDetail?.organization?.id, operation.organizationId)
         ) {
            throw new Error("The canonical case response did not match the submitted decision identity.");
         }

         const selectedCaseIsSubmittedCase =
            identifiersMatch(selectedCaseIdRef.current, operation.caseId) &&
            detailRequestIdRef.current === selectedDetailRequestId;

         if (selectedCaseIsSubmittedCase) {
            setDetail(canonicalDetail);
            setDetailIdentity({
               principal: operation.principal,
               organizationId: operation.organizationId,
               caseId: operation.caseId,
               authorityGeneration: operation.authorityGeneration,
               requestId: selectedDetailRequestId,
            });
            setDetailLoading(false);
            setDetailError("");
            setDetailUnavailable(false);
            focusDetailAfterMutationRef.current = true;
         }

         requestQueueRefresh();

         if (outcome === "success") {
            setActionError("");
            setActionNotice({
               kind: "success",
               caseId: operation.caseId,
               message: selectedCaseIsSubmittedCase
                  ? "The authoritative decision was recorded and the canonical case detail is current."
                  : "The authoritative decision was recorded for the submitted case. Your current selection was not changed.",
               inspectable: !selectedCaseIsSubmittedCase,
            });
         } else if (outcome === "conflict") {
            setActionNotice(null);
            setActionError(
               `Case ${formatCaseReference(operation.caseId)} changed before the decision was submitted. ${serverMessage || "Review its current state before continuing."}`,
            );
         } else {
            const recordedDecisionExists = Boolean(canonicalDetail?.current_decision) || canonicalDetail?.status === "RESOLVED";
            if (recordedDecisionExists) {
               setActionError("");
               setActionNotice({
                  kind: "reconciled",
                  caseId: operation.caseId,
                  message: "The request outcome was initially unclear, but the fresh canonical case now contains a recorded decision.",
                  inspectable: !selectedCaseIsSubmittedCase,
               });
            } else {
               setActionNotice(null);
               setActionError(
                  `The outcome for case ${formatCaseReference(operation.caseId)} was unclear. Fresh canonical detail shows no recorded decision; review it fully before beginning a new attempt.`,
               );
            }
         }
         focusActionMessageRef.current = !selectedCaseIsSubmittedCase;
      } catch (error) {
         if (
            reconciliationRequestIdRef.current !== reconciliationId ||
            !isOperationContextCurrent(operation)
         ) {
            return;
         }

         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority(error);
            return;
         }

         const selectedCaseIsSubmittedCase =
            identifiersMatch(selectedCaseIdRef.current, operation.caseId) &&
            detailRequestIdRef.current === selectedDetailRequestId;
         const pendingMessage =
            outcome === "success"
               ? "The action endpoint recorded the decision, but canonical reconciliation is pending. Do not resubmit the decision."
               : "The request outcome is not confirmed because canonical reconciliation failed. Do not resubmit until the case is reconciled.";

         if (selectedCaseIsSubmittedCase) {
            setDetailIdentity(null);
            setDetailLoading(false);
            setDetailUnavailable(error?.status === 404);
            setDetailError(
               error?.status === 404
                  ? "The submitted Adjudication case is no longer available in this organization."
                  : (error?.message || "Unable to reconcile the submitted case with canonical detail."),
            );
         }

         setReconciliationPending({ operation, outcome, serverMessage });
         setActionNotice(null);
         setActionError(`${pendingMessage} Case ${formatCaseReference(operation.caseId)}.`);
         focusActionMessageRef.current = true;
         requestQueueRefresh();
      }
   };

   const handleBeginDecision = () => {
      if (!readyForFirstDecision || detailLoading || detailError || mutation || reconciliationPending) {
         return;
      }

      setDecisionDraft(EMPTY_DECISION_DRAFT);
      setDecisionErrors({});
      setActionError("");
      setActionNotice(null);
      setConfirmation(null);
      setDecisionFormOpen(true);
      decisionFocusTargetRef.current = "verdict";
      focusDecisionFormRef.current = true;
   };

   const handleDecisionDraftChange = (field, value) => {
      setDecisionDraft((current) => ({ ...current, [field]: value }));
      setDecisionErrors((current) => ({ ...current, [field]: "", general: "" }));
   };

   const handleDecisionReview = (event) => {
      event.preventDefault();
      const errors = {};
      const canonicalClaim = decisionDraft.canonicalClaim.trim();
      const rationale = decisionDraft.rationale.trim();

      if (!VERDICT_OPTIONS.some((option) => option.value === decisionDraft.verdict)) {
         errors.verdict = "Choose one adjudication verdict.";
      }
      if (!canonicalClaim) {
         errors.canonicalClaim = "Enter the canonical claim wording to record.";
      }
      if (!rationale) {
         errors.rationale = "Enter a nonblank rationale for this adjudication.";
      }

      if (Object.keys(errors).length > 0) {
         errors.general = "Review the required decision fields before continuing.";
         setDecisionErrors(errors);
         const firstInvalidField = ["verdict", "canonicalClaim", "rationale"].find((field) => errors[field]);
         const focusTargets = {
            verdict: firstVerdictRef,
            canonicalClaim: canonicalClaimRef,
            rationale: rationaleRef,
         };
         focusTargets[firstInvalidField]?.current?.focus();
         return;
      }

      if (!readyForFirstDecision || !detailIdentityIsCurrent || detailLoading || detailError) {
         setDecisionErrors({ general: "This detail is no longer fresh. Refresh the case and review its readiness again." });
         return;
      }

      confirmationCandidateRef.current = {
         principal: authIdentity,
         organizationId,
         caseId: detail.id,
         authorityGeneration: authorityGenerationRef.current,
         sourceDetailRequestId: detailIdentity.requestId,
         expectedRevision: firstDecisionContract.expectedRevision,
         payload: {
            moderator_verdict: decisionDraft.verdict,
            canonical_claim: canonicalClaim,
            moderator_notes: rationale,
            expected_revision: firstDecisionContract.expectedRevision,
         },
      };
      detailRequestIdRef.current += 1;
      setDetailIdentity(null);
      setDecisionErrors({});
      setDecisionFormOpen(false);
      setConfirmationChecking(true);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailRequestVersion((current) => current + 1);
   };

   const handleCancelDecision = () => {
      restoreDecisionTriggerFocusRef.current = true;
      resetDecisionWorkflow({ clearMessages: false });
   };

   const handleCancelConfirmation = () => {
      setConfirmation(null);
      setDecisionFormOpen(true);
      decisionFocusTargetRef.current = "verdict";
      focusDecisionFormRef.current = true;
   };

   const handleDecisionSubmit = async () => {
      const operation = confirmation;
      if (!operation || mutation || reconciliationPending) {
         return;
      }

      const contract = getFirstDecisionContract(detail, organizationId);
      const isFreshConfirmation =
         detailIdentityIsCurrent &&
         detailIdentity.requestId === operation.detailRequestId &&
         operation.principal === authIdentity &&
         operation.authorityGeneration === authorityGenerationRef.current &&
         identifiersMatch(operation.organizationId, organizationId) &&
         identifiersMatch(operation.caseId, detail?.id) &&
         operation.expectedRevision === contract.expectedRevision &&
         contract.ready;

      if (!isFreshConfirmation) {
         setConfirmation(null);
         focusActionMessageRef.current = true;
         setActionError("This case changed before confirmation. Refresh and review the current decision preconditions.");
         return;
      }

      setMutation(operation);
      setConfirmation(null);
      setActionError("");
      setActionNotice(null);

      try {
         await authFetch(buildAdjudicationCaseUrl(operation.caseId, operation.organizationId, "action/"), {
            method: "POST",
            body: operation.payload,
         });

         if (!isOperationContextCurrent(operation)) {
            return;
         }
         await reconcileDecisionOperation(operation, "success");
      } catch (error) {
         if (!isOperationContextCurrent(operation)) {
            return;
         }

         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority(error);
            return;
         }

         if (error?.status === 400) {
            const validation = getActionValidationErrors(error);
            if (identifiersMatch(selectedCaseIdRef.current, operation.caseId)) {
               setDecisionDraft({
                  verdict: operation.payload.moderator_verdict,
                  canonicalClaim: operation.payload.canonical_claim,
                  rationale: operation.payload.moderator_notes,
               });
               setDecisionErrors({ ...validation.fieldErrors, general: validation.generalMessage });
               setDecisionFormOpen(true);
               decisionFocusTargetRef.current =
                  ["verdict", "canonicalClaim", "rationale"].find((field) => validation.fieldErrors[field]) || "verdict";
               focusDecisionFormRef.current = true;
            } else {
               setActionError(
                  `The decision for case ${formatCaseReference(operation.caseId)} was not accepted: ${validation.generalMessage}`,
               );
               focusActionMessageRef.current = true;
            }
         } else if (error?.status === 404) {
            if (identifiersMatch(selectedCaseIdRef.current, operation.caseId)) {
               detailRequestIdRef.current += 1;
               setDetail(null);
               setDetailIdentity(null);
               setDetailLoading(false);
               setDetailUnavailable(true);
               setDetailError("This Adjudication case is no longer available for the selected organization.");
               focusDetailErrorRef.current = true;
            } else {
               focusActionMessageRef.current = true;
            }
            setActionError(`Case ${formatCaseReference(operation.caseId)} is no longer available.`);
            requestQueueRefresh();
         } else if (error?.status === 409) {
            await reconcileDecisionOperation(operation, "conflict", error?.message);
         } else {
            await reconcileDecisionOperation(operation, "ambiguous", error?.message);
         }
      } finally {
         if (isOperationContextCurrent(operation)) {
            setMutation((current) => (current === operation ? null : current));
         }
      }
   };

   const handleRetryReconciliation = () => {
      if (!reconciliationPending || mutation) {
         return;
      }
      const { operation, outcome, serverMessage } = reconciliationPending;
      setMutation(operation);
      setActionError("");
      reconcileDecisionOperation(operation, outcome, serverMessage).finally(() => {
         if (isOperationContextCurrent(operation)) {
            setMutation((current) => (current === operation ? null : current));
         }
      });
   };

   const replaceQueueScope = ({ status = statusFilter, priority = priorityFilter, nextOffset = 0 }) => {
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      originatingQueueCaseIdRef.current = null;
      returnFocusCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusDetailErrorRef.current = false;
      focusQueueAfterReturnRef.current = false;
      setStatusFilter(status);
      setPriorityFilter(priority);
      setOffset(nextOffset);
      setQueue({ count: 0, limit: PAGE_SIZE, offset: nextOffset, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailIdentity(null);
      resetDecisionWorkflow({ clearMessages: false });
   };

   const handleSelectCase = (caseId) => {
      if (!caseId || identifiersMatch(caseId, selectedCaseIdRef.current)) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedCaseIdRef.current = caseId;
      originatingQueueCaseIdRef.current = caseId;
      returnFocusCaseIdRef.current = null;
      focusSelectedCaseRef.current = true;
      focusDetailErrorRef.current = false;
      setSelectedCaseId(caseId);
      setDetail(null);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailIdentity(null);
      resetDecisionWorkflow({ clearMessages: false });
   };

   const handleInspectSubmittedCase = (caseId) => {
      if (!caseId) {
         return;
      }
      handleSelectCase(caseId);
      setActionNotice(null);
      setActionError("");
   };

   const requestDetailRefresh = () => {
      if (authorityRevokedRef.current || !selectedCaseIdRef.current) {
         return;
      }

      detailRequestIdRef.current += 1;
      confirmationCandidateRef.current = null;
      focusDetailErrorRef.current = false;
      setDetailIdentity(null);
      setConfirmation(null);
      setConfirmationChecking(false);
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailRequestVersion((current) => current + 1);
   };

   const handleAuthorityRetry = () => {
      authorityGenerationRef.current += 1;
      authorityRevokedRef.current = false;
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      reconciliationRequestIdRef.current += 1;
      selectedCaseIdRef.current = null;
      originatingQueueCaseIdRef.current = null;
      returnFocusCaseIdRef.current = null;
      focusSelectedCaseRef.current = false;
      focusDetailErrorRef.current = false;
      focusQueueAfterReturnRef.current = false;
      focusQueueAfterAuthorityRetryRef.current = true;
      setAuthorityError("");
      setQueue({ count: 0, limit: PAGE_SIZE, offset, results: [] });
      setQueueLoading(true);
      setQueueError("");
      setSelectedCaseId(null);
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailUnavailable(false);
      setDetailIdentity(null);
      resetDecisionWorkflow();
      setQueueRequestVersion((current) => current + 1);
   };

   const selectedCase = useMemo(
      () =>
         queue.results.find((caseItem) => identifiersMatch(caseItem?.id, selectedCaseId)) ?? null,
      [queue.results, selectedCaseId],
   );
   const totalPages = Math.max(1, Math.ceil(queue.count / (queue.limit || PAGE_SIZE)));
   const currentPage = queue.count === 0 ? 1 : Math.floor(queue.offset / (queue.limit || PAGE_SIZE)) + 1;
   const hasPreviousPage = offset > 0;
   const hasNextPage = offset + (queue.limit || PAGE_SIZE) < queue.count;
   const emptyCopy = EMPTY_QUEUE_COPY[statusFilter] || EMPTY_QUEUE_COPY.default;
   const activeStatusLabel = STATUS_OPTIONS.find((option) => option.value === statusFilter)?.label || "Active work";
   const detailClaim = detail?.claim || {};
   const evidenceReview = detail?.evidence_review || {};
   const evidenceItems = Array.isArray(evidenceReview.items) ? evidenceReview.items : [];
   const decisionHistory = detail?.decision_history || {};
   const decisionHistoryItems = Array.isArray(decisionHistory.results) ? decisionHistory.results : [];
   const detailEvents = detail?.events || {};
   const eventItems = Array.isArray(detailEvents.results) ? detailEvents.results : [];
   const firstDecisionContract = getFirstDecisionContract(detail, organizationId);
   const { actionState, preconditionsAreValid: actionPreconditionsAreValid } = firstDecisionContract;
   const detailIdentityIsCurrent =
      detailIdentity &&
      detailIdentity.principal === authIdentity &&
      detailIdentity.authorityGeneration === authorityGenerationRef.current &&
      identifiersMatch(detailIdentity.organizationId, organizationId) &&
      identifiersMatch(detailIdentity.caseId, selectedCaseId) &&
      detailIdentity.requestId === detailRequestIdRef.current;
   const readyForFirstDecision = firstDecisionContract.ready && Boolean(detailIdentityIsCurrent);
   const actionBlockers = Array.isArray(actionState.blockers) ? actionState.blockers : [];
   const isResolvedCase = detail?.status === "RESOLVED";
   const viewingOutsideCurrentQueue = Boolean(
      selectedCaseId && detail && !queueLoading && !queueError && !selectedCase,
   );

   if (!canAdjudicate || !organizationId) {
      return (
         <div className="adjudication-review-panel" ref={panelRef}>
            <div className="adjudication-contained-error" role="alert">
               <strong>Adjudication unavailable</strong>
               <span>The selected organization does not grant Adjudication access.</span>
            </div>
         </div>
      );
   }

   return (
      <div className="adjudication-review-panel" ref={panelRef}>
         <div className="adjudication-panel-intro">
            <div>
               <h3>Adjudication review</h3>
               <p>Select a case from the filtered queue, examine its evidence and provenance, then record an authorized human conclusion when the backend permits it.</p>
            </div>
            <span className="adjudication-organization-context">
               Organization: {organizationName || "Unavailable"}
            </span>
         </div>

         <div className="adjudication-boundary-note">
            <Icons name="info" size={17} aria-hidden="true" />
            <div className="adjudication-boundary-copy">
               <strong>Where Adjudication fits</strong>
               <p>
                  Verification Intake establishes the work. Evidence Review assesses source suitability. Adjudication records the authorized human claim-level conclusion.
               </p>
               <p>
                  Evidence counts support triage only; they do not determine claim truth or readiness. Fact-check drafting and publication remain separate workflows.
               </p>
            </div>
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

               {actionNotice && (
                  <div
                      className="adjudication-action-message success"
                      ref={actionMessageRef}
                      tabIndex="-1"
                      role="status"
                  >
                     <Icons name="check-circle" size={18} aria-hidden="true" />
                     <div>
                        <strong>Decision status · Case {formatCaseReference(actionNotice.caseId)}</strong>
                        <span>{actionNotice.message}</span>
                        {actionNotice.inspectable && (
                           <button type="button" onClick={() => handleInspectSubmittedCase(actionNotice.caseId)}>
                              Inspect recorded case
                           </button>
                        )}
                     </div>
                  </div>
               )}

               {actionError && (
                  <div
                      className="adjudication-action-message error"
                      ref={actionMessageRef}
                      tabIndex="-1"
                      role="alert"
                  >
                     <Icons name="alert-circle" size={18} aria-hidden="true" />
                     <div>
                        <strong>Decision workflow needs attention</strong>
                        <span>{actionError}</span>
                        {reconciliationPending && (
                           <button type="button" disabled={Boolean(mutation)} onClick={handleRetryReconciliation}>
                              {mutation ? "Reconciling…" : "Retry canonical reconciliation"}
                           </button>
                        )}
                     </div>
                  </div>
               )}

               {mutation && (
                  <div className="adjudication-action-message pending" role="status">
                     <Icons name="loader" size={18} className="adjudication-spinner" aria-hidden="true" />
                     <div>
                        <strong>Recording case {formatCaseReference(mutation.caseId)}</strong>
                        <span>
                           The submitted request remains in progress even if you inspect another case. It will not be retried automatically.
                        </span>
                     </div>
                  </div>
               )}

               <div className={`adjudication-workspace-grid ${selectedCaseId ? "has-selection" : ""}`}>
                  <section
                     className="adjudication-queue"
                     aria-labelledby="adjudication-queue-heading"
                     aria-busy={queueLoading}
                  >
                     <div className="adjudication-section-heading">
                        <div>
                           <h4 id="adjudication-queue-heading" ref={queueHeadingRef} tabIndex="-1">
                              Filtered case queue
                           </h4>
                           <p>{activeStatusLabel} · Scoped to {organizationName || "the selected organization"}.</p>
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
                                    ref={(node) => {
                                       const caseKey = String(caseItem.id);
                                       if (node) {
                                          queueRowRefs.current.set(caseKey, node);
                                       } else {
                                          queueRowRefs.current.delete(caseKey);
                                       }
                                    }}
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
                     aria-busy={detailLoading}
                  >
                     {selectedCaseId ? (
                        <div className="adjudication-selection-content">
                           <div className="adjudication-detail-actions">
                              <button
                                 type="button"
                                 className="adjudication-return-to-queue"
                                 onClick={() => clearSelection({ restoreQueueFocus: true })}
                              >
                                 <Icons name="arrow-left" size={15} aria-hidden="true" />
                                 Return to queue
                              </button>
                              <button type="button" disabled={detailLoading} onClick={requestDetailRefresh}>
                                 <Icons name="refresh-cw" size={14} aria-hidden="true" />
                                 {detailLoading && detail ? "Refreshing case…" : "Refresh case"}
                              </button>
                           </div>

                           <header className="adjudication-detail-header">
                              <div className="adjudication-selection-heading">
                                 <span>Selected case · {formatCaseReference(selectedCaseId)}</span>
                                 <h4
                                    id="adjudication-selection-heading"
                                    ref={selectedCaseHeadingRef}
                                    tabIndex="-1"
                                 >
                                    {detail ? getClaimContext(detail) : selectedCase ? getClaimContext(selectedCase) : "Selected Adjudication case"}
                                 </h4>
                              </div>
                              {(detail || selectedCase) && (
                                 <div className="adjudication-selection-facts">
                                    <span>{detail?.status_label || selectedCase?.status_label || formatLabel(detail?.status || selectedCase?.status)}</span>
                                    <span>
                                       Priority: {detail?.priority_label || selectedCase?.priority_label || formatLabel(detail?.priority || selectedCase?.priority)}
                                    </span>
                                 </div>
                              )}
                           </header>

                           {viewingOutsideCurrentQueue && (
                              <p className="adjudication-outside-queue-note">
                                 <Icons name="info" size={15} aria-hidden="true" />
                                 Viewing a selected case outside the current queue results. Use the case-status filters to find active or resolved history when applicable.
                              </p>
                           )}

                           {detailLoading && !detail ? (
                              <div className="adjudication-state adjudication-detail-loading" role="status">
                                 <Icons name="loader" size={21} className="adjudication-spinner" aria-hidden="true" />
                                 <p>Loading the selected Adjudication case…</p>
                              </div>
                           ) : detailError && !detail ? (
                              <div
                                 className="adjudication-contained-error"
                                 ref={detailErrorRef}
                                 tabIndex="-1"
                                 role="alert"
                              >
                                 <strong>{detailUnavailable ? "Case unavailable" : "Adjudication detail unavailable"}</strong>
                                 <span>{detailError}</span>
                                 <div className="adjudication-error-actions">
                                    <button type="button" onClick={requestDetailRefresh}>Retry detail</button>
                                    <button type="button" onClick={() => clearSelection({ restoreQueueFocus: true })}>
                                       Return to queue
                                    </button>
                                 </div>
                              </div>
                           ) : detail ? (
                              <div className="adjudication-detail-content">
                                 {detailLoading && (
                                    <p className="adjudication-refresh-notice" role="status">
                                       Refreshing this case while the current detail remains visible.
                                    </p>
                                 )}
                                 {detailError && (
                                    <div
                                       className="adjudication-contained-error"
                                       ref={detailErrorRef}
                                       tabIndex="-1"
                                       role="alert"
                                    >
                                       <strong>Case refresh failed</strong>
                                       <span>{detailError}</span>
                                       <span>The previously loaded case detail remains visible below.</span>
                                       <button type="button" onClick={requestDetailRefresh}>Retry detail</button>
                                    </div>
                                 )}

                                 <div className="adjudication-detail-layout">
                                    <div className="adjudication-primary-surface">
                                       <section className="adjudication-detail-section" aria-labelledby="adjudication-case-context-heading">
                                          <div className="adjudication-subheading-row">
                                             <div>
                                                <h5 id="adjudication-case-context-heading">Case and claim context</h5>
                                                <p>Review the full claim context before interpreting evidence or decision history.</p>
                                             </div>
                                          </div>

                                          <div className="adjudication-reading-block prominent">
                                             <strong>Claim text</strong>
                                             <p>{detailClaim.context_text || "Claim text unavailable."}</p>
                                          </div>

                                          <div className="adjudication-context-links">
                                             <SafeExternalLink value={detailClaim.url_link}>Open original claim</SafeExternalLink>
                                             <SafeExternalLink value={detailClaim.source_link}>Open claim source</SafeExternalLink>
                                             <SafeExternalLink value={detailClaim.media_url}>Open claim media</SafeExternalLink>
                                          </div>
                                          {[detailClaim.url_link, detailClaim.source_link, detailClaim.media_url].some(
                                             (value) => value && !getSafeHttpUrl(value),
                                          ) && (
                                             <p className="adjudication-inline-warning">
                                                One or more recorded claim links cannot be opened because they are not supported HTTP(S) addresses.
                                             </p>
                                          )}

                                          <div className="adjudication-thread-context">
                                             <h6>Related threads</h6>
                                             {Array.isArray(detailClaim.threads) && detailClaim.threads.length > 0 ? (
                                                <ul>
                                                   {detailClaim.threads.map((thread) => (
                                                      <li key={thread.id}>
                                                         <Link to={`/thread/detail/${encodeURIComponent(thread.id)}`}>
                                                            {thread.caption || `Thread ${formatCaseReference(thread.id)}`}
                                                         </Link>
                                                         <span><FormattedDateTime value={thread.created_at} /></span>
                                                      </li>
                                                   ))}
                                                </ul>
                                             ) : (
                                                <p>No related thread reference is available.</p>
                                             )}
                                          </div>
                                       </section>

                                 <section className="adjudication-detail-section" aria-labelledby="adjudication-evidence-heading">
                                    <div className="adjudication-subheading-row">
                                       <div>
                                          <h5 id="adjudication-evidence-heading">Evidence review</h5>
                                          <p>These are current evidence records, not an immutable decision-time snapshot.</p>
                                       </div>
                                       <span className="adjudication-basis-label">
                                          Basis: {formatLabel(evidenceReview.basis, "Unavailable")}
                                       </span>
                                    </div>

                                    <div className="adjudication-evidence-totals">
                                       <span className="adjudication-evidence-metric adjudication-evidence-metric--neutral">
                                          Total <strong>{normalizeNonnegativeNumber(evidenceReview.total)}</strong>
                                       </span>
                                       <span className="adjudication-evidence-metric adjudication-evidence-metric--success">
                                          Verified <strong>{normalizeNonnegativeNumber(evidenceReview.verified)}</strong>
                                       </span>
                                       <span className="adjudication-evidence-metric adjudication-evidence-metric--critical">
                                          Rejected <strong>{normalizeNonnegativeNumber(evidenceReview.rejected)}</strong>
                                       </span>
                                       <span className="adjudication-evidence-metric adjudication-evidence-metric--info">
                                          Unreviewed <strong>{normalizeNonnegativeNumber(evidenceReview.unreviewed)}</strong>
                                       </span>
                                       <span className="adjudication-evidence-metric adjudication-evidence-metric--info">
                                          Active Evidence cases <strong>{normalizeNonnegativeNumber(evidenceReview.active_evidence_cases)}</strong>
                                       </span>
                                       <span
                                          className={`adjudication-evidence-metric adjudication-evidence-metric--${evidenceReview.all_reviewed ? "success" : "info"}`}
                                       >
                                          All reviewed <strong>{evidenceReview.all_reviewed ? "Yes" : "No"}</strong>
                                       </span>
                                    </div>
                                    <p className="adjudication-domain-note">
                                       Evidence verification assesses source suitability. It does not establish whether the claim is true or false.
                                    </p>

                                    {evidenceItems.length > 0 ? (
                                       <ol className="adjudication-evidence-list">
                                          {evidenceItems.map((evidence) => <EvidenceRecord key={evidence.id} evidence={evidence} />)}
                                       </ol>
                                    ) : (
                                       <p className="adjudication-inline-empty">No evidence submissions are attached to this claim.</p>
                                    )}
                                 </section>

                                 <section className="adjudication-detail-section" aria-labelledby="adjudication-readiness-heading">
                                    <div className="adjudication-subheading-row">
                                       <div>
                                          <h5 id="adjudication-readiness-heading">Assignment and readiness</h5>
                                          <p>Readiness is advisory and may change before an authoritative action.</p>
                                       </div>
                                    </div>

                                    <div className={`adjudication-readiness-state ${readyForFirstDecision ? "ready" : "blocked"}`}>
                                       <Icons name={readyForFirstDecision ? "check-circle" : "alert-circle"} size={18} aria-hidden="true" />
                                       <div>
                                          <strong>{readyForFirstDecision ? "Ready for a first decision" : "First decision unavailable"}</strong>
                                          <span>
                                             {readyForFirstDecision
                                                ? "The backend reports valid selected-case, organization, and revision preconditions. Refreshing the case will revalidate them."
                                                : "Review the authoritative blockers below. Refresh before relying on this advisory state."}
                                          </span>
                                       </div>
                                    </div>

                                    {!actionPreconditionsAreValid && actionState.can_issue_first_decision === true && (
                                       <p className="adjudication-inline-warning">
                                          The server marked this case ready, but its returned action preconditions are incomplete or do not match the selected case.
                                       </p>
                                    )}

                                    {isResolvedCase && (
                                       <div className="adjudication-read-only-state">
                                          <Icons name="check-circle" size={18} aria-hidden="true" />
                                          <div>
                                             <strong>Review completed · Read-only</strong>
                                             <span>
                                                What happens next: the decision remains recorded for this case. Fact-check drafting and publication are separate processes; this workbench does not correct, revise, or reopen it.
                                             </span>
                                          </div>
                                       </div>
                                    )}

                                    {actionBlockers.length > 0 && (
                                       <div className="adjudication-blocker-group">
                                          <h6>Decision blockers</h6>
                                          <ul className="adjudication-blocker-list">
                                             {actionBlockers.map((blocker, index) => (
                                                <li key={`${blocker.code || "BLOCKER"}-${index}`}>
                                                   <strong>{formatLabel(blocker.code, "Decision blocker")}</strong>
                                                   <span>{blocker.message || "This case is not currently eligible for a first decision."}</span>
                                                </li>
                                             ))}
                                          </ul>
                                       </div>
                                    )}

                                    <dl className="adjudication-detail-facts compact adjudication-readiness-meta">
                                       <div><dt>Assignment status</dt><dd>{detail.assignment?.status ? formatLabel(detail.assignment.status) : "No active assignment"}</dd></div>
                                       <div><dt>Claimed by</dt><dd><MinimalUser user={detail.assignment?.claimed_by} fallback="Not assigned" /></dd></div>
                                       <div><dt>Expected revision</dt><dd>{actionState.expected_revision ?? "Unavailable"}</dd></div>
                                       <div><dt>Selected case precondition</dt><dd>{actionPreconditionsAreValid ? "Confirmed" : "Unavailable"}</dd></div>
                                    </dl>

                                    {readyForFirstDecision && !decisionFormOpen && !confirmation && !confirmationChecking && (
                                       <div className="adjudication-decision-entry">
                                          <button
                                             type="button"
                                             ref={decisionTriggerRef}
                                             disabled={Boolean(mutation) || Boolean(reconciliationPending) || detailLoading || Boolean(detailError)}
                                             onClick={handleBeginDecision}
                                          >
                                             Begin decision
                                          </button>
                                          <p>
                                             This begins a deliberate first-decision review. It does not draft or publish a fact-check.
                                          </p>
                                       </div>
                                    )}

                                    {confirmationChecking && (
                                       <div className="adjudication-decision-checking" role="status">
                                          <Icons name="loader" size={17} className="adjudication-spinner" aria-hidden="true" />
                                          <span>Refreshing canonical detail before confirmation…</span>
                                       </div>
                                    )}

                                    {decisionFormOpen && (
                                       <form className="adjudication-decision-form" onSubmit={handleDecisionReview} noValidate>
                                          <div className="adjudication-form-heading">
                                             <div>
                                                <h6>Prepare first decision</h6>
                                                <p>
                                                   Case {formatCaseReference(detail.id)} · Enter the institutional wording and rationale intentionally.
                                                </p>
                                             </div>
                                          </div>

                                          {decisionErrors.general && (
                                             <p className="adjudication-form-error summary" role="alert">
                                                {decisionErrors.general}
                                             </p>
                                          )}

                                          <fieldset
                                             className="adjudication-verdict-options"
                                             aria-describedby={decisionErrors.verdict ? "adjudication-verdict-error" : undefined}
                                          >
                                             <legend>Adjudication verdict <span aria-hidden="true">*</span></legend>
                                             <p>Choose the claim-level human decision. Evidence dispositions remain separate.</p>
                                             <div>
                                                {VERDICT_OPTIONS.map((option, index) => (
                                                   <label key={option.value}>
                                                      <input
                                                         ref={index === 0 ? firstVerdictRef : undefined}
                                                         type="radio"
                                                         name="adjudication-verdict"
                                                         value={option.value}
                                                         checked={decisionDraft.verdict === option.value}
                                                         onChange={(event) => handleDecisionDraftChange("verdict", event.target.value)}
                                                         required
                                                      />
                                                      <span>{option.label}</span>
                                                   </label>
                                                ))}
                                             </div>
                                          </fieldset>
                                          {decisionErrors.verdict && (
                                             <p id="adjudication-verdict-error" className="adjudication-form-error">
                                                {decisionErrors.verdict}
                                             </p>
                                          )}

                                          <label className="adjudication-decision-field" htmlFor="adjudication-canonical-claim">
                                             <span>Canonical claim wording <span aria-hidden="true">*</span></span>
                                             <textarea
                                                id="adjudication-canonical-claim"
                                                ref={canonicalClaimRef}
                                                value={decisionDraft.canonicalClaim}
                                                onChange={(event) => handleDecisionDraftChange("canonicalClaim", event.target.value)}
                                                aria-invalid={Boolean(decisionErrors.canonicalClaim)}
                                                aria-describedby={
                                                   decisionErrors.canonicalClaim
                                                      ? "adjudication-canonical-claim-help adjudication-canonical-claim-error"
                                                      : "adjudication-canonical-claim-help"
                                                }
                                                rows={3}
                                                required
                                             />
                                             <small id="adjudication-canonical-claim-help">
                                                The precise, neutral statement this decision formally evaluates. It starts blank by design.
                                             </small>
                                          </label>
                                          {decisionErrors.canonicalClaim && (
                                             <p id="adjudication-canonical-claim-error" className="adjudication-form-error">
                                                {decisionErrors.canonicalClaim}
                                             </p>
                                          )}

                                          <label className="adjudication-decision-field" htmlFor="adjudication-rationale">
                                             <span>Decision rationale <span aria-hidden="true">*</span></span>
                                             <textarea
                                                id="adjudication-rationale"
                                                ref={rationaleRef}
                                                value={decisionDraft.rationale}
                                                onChange={(event) => handleDecisionDraftChange("rationale", event.target.value)}
                                                aria-invalid={Boolean(decisionErrors.rationale)}
                                                aria-describedby={
                                                   decisionErrors.rationale
                                                      ? "adjudication-rationale-help adjudication-rationale-error"
                                                      : "adjudication-rationale-help"
                                                }
                                                rows={5}
                                                required
                                             />
                                             <small id="adjudication-rationale-help">
                                                Explain why the reviewed evidence supports the selected verdict. A nonblank rationale is required.
                                             </small>
                                          </label>
                                          {decisionErrors.rationale && (
                                             <p id="adjudication-rationale-error" className="adjudication-form-error">
                                                {decisionErrors.rationale}
                                             </p>
                                          )}

                                          <div className="adjudication-decision-form-actions">
                                             <button type="button" onClick={handleCancelDecision}>Cancel</button>
                                             <button type="submit">Review decision</button>
                                          </div>
                                       </form>
                                    )}

                                    {confirmation && (
                                       <div className="adjudication-decision-confirmation">
                                          <div
                                             className="adjudication-form-heading"
                                             ref={confirmationHeadingRef}
                                             tabIndex="-1"
                                          >
                                             <div>
                                                <h6>Confirm authoritative adjudication</h6>
                                                <p>Case {formatCaseReference(confirmation.caseId)} · Revision {confirmation.expectedRevision}</p>
                                             </div>
                                          </div>

                                          <p className="adjudication-confirmation-consequence">
                                             Confirming records an authoritative human adjudication and resolves this case. Fact-check drafting and publication remain separate workflows. This is not a correction or reopen action.
                                          </p>

                                          <dl className="adjudication-confirmation-summary">
                                             <div>
                                                <dt>Verdict</dt>
                                                <dd>{VERDICT_OPTIONS.find((option) => option.value === confirmation.payload.moderator_verdict)?.label}</dd>
                                             </div>
                                             <div>
                                                <dt>Canonical wording</dt>
                                                <dd>{confirmation.payload.canonical_claim}</dd>
                                             </div>
                                             <div>
                                                <dt>Rationale</dt>
                                                <dd>{confirmation.payload.moderator_notes}</dd>
                                             </div>
                                          </dl>

                                          <div className="adjudication-decision-form-actions">
                                             <button type="button" disabled={Boolean(mutation)} onClick={handleCancelConfirmation}>
                                                Back to edit
                                             </button>
                                             <button type="button" disabled={Boolean(mutation)} onClick={handleDecisionSubmit}>
                                                {mutation ? "Recording decision…" : "Confirm and record decision"}
                                             </button>
                                          </div>
                                       </div>
                                    )}

                                 </section>

                                 <section className="adjudication-detail-section" aria-labelledby="adjudication-decisions-heading">
                                    <div className="adjudication-subheading-row">
                                       <div>
                                          <h5 id="adjudication-decisions-heading">Decision record</h5>
                                          <p>Only decision records authorized for the selected organization are shown.</p>
                                       </div>
                                    </div>

                                    {detail.current_decision ? (
                                       <DecisionRecord decision={detail.current_decision} current />
                                    ) : (
                                       <p className="adjudication-inline-empty">No current decision record is visible for this case.</p>
                                    )}

                                    <div className="adjudication-history-heading">
                                       <h6>Decision history</h6>
                                       <span>{normalizeNonnegativeNumber(decisionHistory.count)} historical {decisionHistory.count === 1 ? "record" : "records"}</span>
                                    </div>
                                    {decisionHistory.has_restricted_records && (
                                       <p className="adjudication-private-history-notice">
                                          Additional decision history exists but is not available within this organization&apos;s authorized view.
                                       </p>
                                    )}
                                    {decisionHistoryItems.length > 0 ? (
                                       <div className="adjudication-decision-history">
                                          {decisionHistoryItems.map((decision) => <DecisionRecord key={decision.id} decision={decision} />)}
                                       </div>
                                    ) : (
                                       <p className="adjudication-inline-empty">No authorized historical decision records are available.</p>
                                    )}
                                    {decisionHistory.truncated && (
                                       <p className="adjudication-truncation-note">Only the most recent authorized decision records are shown.</p>
                                    )}
                                 </section>

                                       <section className="adjudication-detail-section" aria-labelledby="adjudication-resolution-heading">
                                    <div className="adjudication-subheading-row">
                                       <div>
                                          <h5 id="adjudication-resolution-heading">Resolution and case history</h5>
                                          <p>Resolution and append-only case events belong to this selected case.</p>
                                       </div>
                                    </div>

                                    {detail.resolution ? (
                                       <div className="adjudication-resolution">
                                          <dl className="adjudication-detail-facts compact">
                                             <div><dt>Resolution</dt><dd>{formatLabel(detail.resolution.code, "Not recorded")}</dd></div>
                                             <div><dt>Resolved by</dt><dd><MinimalUser user={detail.resolution.resolved_by} fallback="Actor not recorded" /></dd></div>
                                             <div><dt>Resolved at</dt><dd><FormattedDateTime value={detail.resolution.resolved_at} /></dd></div>
                                          </dl>
                                          <div className="adjudication-reading-block">
                                             <strong>Resolution summary</strong>
                                             <p>{detail.resolution.summary || "No resolution summary was recorded."}</p>
                                          </div>
                                       </div>
                                    ) : (
                                       <p className="adjudication-inline-empty">This case has no recorded resolution.</p>
                                    )}

                                    <div className="adjudication-history-heading">
                                       <h6>Case events</h6>
                                       <span>{normalizeNonnegativeNumber(detailEvents.count)} {detailEvents.count === 1 ? "event" : "events"}</span>
                                    </div>
                                    {eventItems.length > 0 ? (
                                       <ol className="adjudication-event-list">
                                          {eventItems.map((event, index) => (
                                             <EventRecord key={`${event.event_type}-${event.created_at}-${index}`} event={event} />
                                          ))}
                                       </ol>
                                    ) : (
                                       <p className="adjudication-inline-empty">No case events are available.</p>
                                    )}
                                    {detailEvents.truncated && (
                                       <p className="adjudication-truncation-note">Showing the most recent 50 events, in chronological order.</p>
                                    )}
                                       </section>
                                    </div>

                                    <aside
                                       className="adjudication-context-rail"
                                       aria-label="Selected case context"
                                    >
                                       <h5>Case context</h5>
                                       <dl className="adjudication-detail-facts">
                                          <div><dt>Organization</dt><dd>{detail.organization?.name || "Unavailable"}</dd></div>
                                          <div><dt>Claim ID</dt><dd>{detailClaim.id || "Unavailable"}</dd></div>
                                          <div><dt>Claim type</dt><dd>{formatLabel(detailClaim.claim_type)}</dd></div>
                                          <div><dt>Workflow state</dt><dd>{formatLabel(detail.workflow_state)}</dd></div>
                                          <div><dt>Case status</dt><dd>{detail.status_label || formatLabel(detail.status)}</dd></div>
                                          <div><dt>Priority</dt><dd>{detail.priority_label || formatLabel(detail.priority)}</dd></div>
                                          <div><dt>Source</dt><dd>{detail.source_label || formatLabel(detail.source)}</dd></div>
                                          <div><dt>Created</dt><dd><FormattedDateTime value={detail.created_at} /></dd></div>
                                          <div><dt>Updated</dt><dd><FormattedDateTime value={detail.updated_at} /></dd></div>
                                          <div><dt>Resolved</dt><dd><FormattedDateTime value={detail.resolved_at} fallback="Not resolved" /></dd></div>
                                       </dl>
                                       <details className="adjudication-full-id">
                                          <summary>Full case ID</summary>
                                          <span>{detail.id}</span>
                                       </details>
                                    </aside>
                                 </div>
                              </div>
                           ) : null}
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
         authIdentity={authIdentity}
      />
   );
}

export default AdjudicationReviewPanel;
