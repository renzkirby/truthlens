import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import { resolveApiEndpoint } from "../../utils/api";
import { getAuthSessionIdentity } from "../../utils/authIdentity";
import { showWorkspaceSuccess, WORKSPACE_LONG_TOAST_DURATION } from "../../utils/workspaceToast";
import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";
import Textarea from "../ui/Textarea.jsx";

import "./PublishingPanel.css";

const PAGE_SIZE = 20;
const VERDICT_CLASSES = {
   FACT: "fact",
   FAKE: "fake",
   MISLEADING: "misleading",
   SATIRE: "satire",
   UNVERIFIED: "unverified",
   OUT_OF_SCOPE: "outofscope",
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

function FormattedDateTime({ value, fallback }) {
   const formatted = formatDateTime(value, fallback);
   const date = value ? new Date(value) : null;

   if (!date || Number.isNaN(date.getTime())) {
      return formatted;
   }

   return <time dateTime={date.toISOString()}>{formatted}</time>;
}

function actorName(actor, fallback = "Not recorded") {
   return actor?.username ? `@${actor.username}` : fallback;
}

function sourceOriginLabel(sourceOrigin) {
   const labels = {
      DECISION_EVIDENCE: "Decision evidence",
      ORGANIZATION_EDITORIAL: "Organization editorial source",
      LEGACY_IMPORT: "Legacy imported source",
   };

   return labels[sourceOrigin] || "Source origin unavailable";
}

function sourceSelectionLabel(isSelected) {
   if (isSelected === true) {
      return "Cited in article";
   }
   if (isSelected === false) {
      return "Not cited in article";
   }
   return "Citation history unavailable";
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

function VerdictBadge({ verdict }) {
   const normalized = String(verdict || "").toUpperCase();
   const tone = VERDICT_CLASSES[normalized] || "neutral";

   return <span className={`publishing-verdict publishing-verdict--${tone}`}>{formatLabel(verdict)}</span>;
}

function HumanJudgment({ detail }) {
   const decision = detail?.decision || {};

   return (
      <section className="publishing-review-section" aria-labelledby="publishing-human-judgment-heading">
         <div className="publishing-section-heading">
            <div>
               <h4 id="publishing-human-judgment-heading">Human factual judgment</h4>
               <p>The factual adjudication is authoritative and remains separate from this publication decision.</p>
            </div>
            <VerdictBadge verdict={decision.verdict || detail?.verdict} />
         </div>

         <dl className="publishing-metadata-grid">
            <div className="publishing-metadata-wide">
               <dt>Claim reviewed</dt>
               <dd>{decision.canonical_claim || detail?.canonical_claim || "Not recorded"}</dd>
            </div>
            <div className="publishing-metadata-wide">
               <dt>Rationale</dt>
               <dd>{decision.rationale || "No rationale was recorded."}</dd>
            </div>
            <div>
               <dt>Decision revision</dt>
               <dd>{decision.revision_number ?? detail?.concurrency?.decision_revision ?? "Not recorded"}</dd>
            </div>
            <div>
               <dt>Adjudicator</dt>
               <dd>{actorName(decision.decided_by)}</dd>
            </div>
            <div>
               <dt>Decision time</dt>
               <dd>
                  <FormattedDateTime value={decision.decided_at} />
               </dd>
            </div>
         </dl>
      </section>
   );
}

function EditorialRevisionContext({ revision }) {
   if (!revision) {
      return null;
   }

   return (
      <section className="publishing-review-section" aria-labelledby="publishing-revision-context-heading">
         <div className="publishing-section-heading">
            <div>
               <h4 id="publishing-revision-context-heading">Editorial revision</h4>
               <p>Review the requested editorial change against its preserved predecessor publication.</p>
            </div>
         </div>
         <dl className="publishing-metadata-grid">
            <div className="publishing-metadata-wide">
               <dt>Revision reason</dt>
               <dd>{revision.reason || "No revision reason recorded."}</dd>
            </div>
            <div className="publishing-metadata-wide">
               <dt>Predecessor</dt>
               <dd>
                  {revision.predecessor?.headline || "Untitled publication"} · Article v
                  {revision.predecessor?.version ?? "–"}
               </dd>
            </div>
            <div>
               <dt>Requested by</dt>
               <dd>{actorName(revision.requested_by)}</dd>
            </div>
            <div>
               <dt>Requested</dt>
               <dd>
                  <FormattedDateTime value={revision.requested_at} />
               </dd>
            </div>
         </dl>
      </section>
   );
}

function PublicationSources({ sourceItems }) {
   const sources = Array.isArray(sourceItems) ? sourceItems : [];

   return (
      <section className="publishing-review-section" aria-labelledby="publishing-sources-heading">
         <div className="publishing-section-heading">
            <div>
               <h4 id="publishing-sources-heading">Publication sources</h4>
               <p>
                  Publication sources show where each source entered the publication record. Citing a source in the
                  article does not change the evidence preserved for the human decision.
               </p>
            </div>
            <span className="publishing-count-label">{sources.length} sources</span>
         </div>

         {sources.length === 0 ? (
            <p className="publishing-inline-empty">No publication sources are attached.</p>
         ) : (
            <ul className="publishing-source-list">
               {sources.map((source, index) => {
                  const externalUrl = safeExternalUrl(source?.url);
                  const isDecisionEvidence = source?.source_origin === "DECISION_EVIDENCE";
                  const isOrganizationEditorial = source?.source_origin === "ORGANIZATION_EDITORIAL";
                  const addedBy = isOrganizationEditorial && source?.added_by?.username
                     ? `Added by @${source.added_by.username}`
                     : null;

                  return (
                     <li key={source?.id || `${source?.url}-${index}`}>
                        <div className="publishing-source-main">
                           {externalUrl ? (
                              <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                                 {source?.title || source?.url}
                                 <Icons name="external-link" size={14} />
                              </a>
                           ) : (
                              <strong>{source?.title || source?.url || "Source unavailable"}</strong>
                           )}
                           {source?.title && source?.url ? <span>{source.url}</span> : null}
                        </div>
                        <div className="publishing-source-flags">
                           <span>{sourceOriginLabel(source?.source_origin)}</span>
                           {isDecisionEvidence ? <span>Decision evidence</span> : null}
                           {isOrganizationEditorial ? <span>Editorial source</span> : null}
                           {addedBy ? <span>{addedBy}</span> : null}
                           <span>{sourceSelectionLabel(source?.is_editorially_selected)}</span>
                        </div>
                     </li>
                  );
               })}
            </ul>
         )}
      </section>
   );
}

function SealedEvidence({ sealedEvidence }) {
   const entries = Array.isArray(sealedEvidence?.entries) ? sealedEvidence.entries : [];

   return (
      <section className="publishing-review-section" aria-labelledby="publishing-sealed-evidence-heading">
         <div className="publishing-section-heading">
            <div>
               <h4 id="publishing-sealed-evidence-heading">Evidence used for this decision</h4>
               <p>Evidence preserved from when the human decision was made. Evidence added later does not change this historical record.</p>
            </div>
            <span className="publishing-count-label">{sealedEvidence?.count ?? entries.length} records</span>
         </div>

         {!sealedEvidence ? (
            <p className="publishing-inline-empty">No preserved evidence record is available for this decision.</p>
         ) : entries.length === 0 ? (
            <p className="publishing-inline-empty">No evidence records were preserved for this decision.</p>
         ) : (
            <ol className="publishing-evidence-list">
               {entries.map((entry, index) => {
                  const externalUrl = safeExternalUrl(entry?.evidence_url);

                  return (
                     <li key={entry?.id || index}>
                        <div className="publishing-evidence-heading">
                           <strong>{entry?.evidence_caption || `Evidence record ${index + 1}`}</strong>
                           <span>{formatLabel(entry?.evidence_status)}</span>
                        </div>
                        <p>{formatLabel(entry?.evidence_type, "Evidence type not recorded")}</p>
                        <dl className="publishing-compact-metadata">
                           <div>
                              <dt>Contributor record</dt>
                              <dd>{entry?.contributor_id || "Not recorded"}</dd>
                           </div>
                           <div>
                              <dt>Reviewer record</dt>
                              <dd>{entry?.reviewer_id || "Not recorded"}</dd>
                           </div>
                           <div>
                              <dt>Submitted</dt>
                              <dd>
                                 <FormattedDateTime value={entry?.submitted_at} />
                              </dd>
                           </div>
                           <div>
                              <dt>Reviewed</dt>
                              <dd>
                                 <FormattedDateTime value={entry?.reviewed_at} />
                              </dd>
                           </div>
                        </dl>
                        {entry?.moderator_notes ? (
                           <p className="publishing-evidence-note">
                              <strong>Review notes:</strong> {entry.moderator_notes}
                           </p>
                        ) : null}
                        {entry?.rejection_reason ? (
                           <p className="publishing-evidence-note">
                              <strong>Rejection reason:</strong> {entry.rejection_reason}
                           </p>
                        ) : null}
                        {externalUrl ? (
                           <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                              Open captured source <Icons name="external-link" size={14} />
                           </a>
                        ) : entry?.evidence_url ? (
                           <span className="publishing-invalid-url">Captured URL is not a safe http/https link.</span>
                        ) : null}
                     </li>
                  );
               })}
            </ol>
         )}

         {sealedEvidence ? (
            <p className="publishing-snapshot-note">
               Record {String(sealedEvidence.decision_snapshot_id || "unavailable").slice(0, 8)} · Schema version{" "}
               {sealedEvidence.schema_version ?? "unavailable"} · Preserved{" "}
               <FormattedDateTime value={sealedEvidence.captured_at} />
            </p>
         ) : null}
      </section>
   );
}

function Readiness({ detail }) {
   const blockers = Array.isArray(detail?.blockers) ? detail.blockers : [];

   return (
      <section className="publishing-review-section publishing-readiness" aria-labelledby="publishing-readiness-heading">
         <div className="publishing-section-heading">
            <div>
               <h4 id="publishing-readiness-heading">Decision readiness</h4>
               <p>Server-defined workflow conditions determine which publication actions are available.</p>
            </div>
         </div>

         {blockers.length > 0 ? (
            <ul className="publishing-blocker-list">
               {blockers.map((blocker, index) => (
                  <li key={`${blocker?.code || "blocker"}-${index}`}>
                     <Icons name="alert-circle" size={16} />
                     <span>
                        <strong>{formatLabel(blocker?.code, "Publication blocker")}</strong>
                        {blocker?.detail || "This item is not ready for the requested action."}
                     </span>
                  </li>
               ))}
            </ul>
         ) : (
            <div className="publishing-ready-state" role="status">
               <Icons name="check-circle" size={18} />
               <div>
                  <strong>Ready for a publication decision</strong>
                  <p>No publication blockers are reported by the workflow.</p>
               </div>
            </div>
         )}
      </section>
   );
}

function PublishingReferenceMaterial({ detail, isEditorialReview }) {
   const decision = detail?.decision || {};
   const sealedEvidence = detail?.sealed_evidence || null;
   const actions = Array.isArray(detail?.allowed_actions) ? detail.allowed_actions : [];

   return (
      <details className="publishing-reference-material">
         <summary>
            <span>
               <strong>Reference material</strong>
               <small>Revision context, publication sources, decision evidence, and technical details</small>
            </span>
            <Icons name="chevron-down" size={16} aria-hidden="true" />
         </summary>

         <div className="publishing-reference-content">
            {isEditorialReview ? <EditorialRevisionContext revision={detail?.revision} /> : null}
            <PublicationSources sourceItems={detail?.source_items} />
            <SealedEvidence sealedEvidence={sealedEvidence} />

            <details className="publishing-technical-details">
               <summary>Technical details</summary>
               <dl className="publishing-compact-metadata">
                  <div>
                     <dt>Allowed review actions</dt>
                     <dd>{actions.length > 0 ? actions.map((action) => formatLabel(action)).join(", ") : "None"}</dd>
                  </div>
                  <div>
                     <dt>Edit generation</dt>
                     <dd>{detail?.concurrency?.edit_generation ?? detail?.edit_generation ?? "Not recorded"}</dd>
                  </div>
                  <div>
                     <dt>Decision revision</dt>
                     <dd>{detail?.concurrency?.decision_revision ?? decision.revision_number ?? "Not recorded"}</dd>
                  </div>
                  {isEditorialReview ? (
                     <div>
                        <dt>Predecessor version</dt>
                        <dd>{detail?.concurrency?.predecessor_version ?? "Not recorded"}</dd>
                     </div>
                  ) : null}
                  {sealedEvidence ? (
                     <>
                        <div>
                           <dt>Preserved evidence record</dt>
                           <dd>{String(sealedEvidence.decision_snapshot_id || "Not recorded")}</dd>
                        </div>
                        <div>
                           <dt>Record schema</dt>
                           <dd>{sealedEvidence.schema_version ?? "Not recorded"}</dd>
                        </div>
                     </>
                  ) : null}
               </dl>
            </details>
         </div>
      </details>
   );
}

function PublishingDecisionDialog({
   open,
   processing,
   title,
   description,
   onClose,
   children,
}) {
   const dialogRef = useRef(null);
   const triggerRef = useRef(null);
   const processingRef = useRef(processing);
   const closeRef = useRef(onClose);

   useEffect(() => {
      processingRef.current = processing;
   }, [processing]);

   useEffect(() => {
      closeRef.current = onClose;
   }, [onClose]);

   useEffect(() => {
      if (!open) {
         return undefined;
      }

      triggerRef.current = document.activeElement;
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";

      requestAnimationFrame(() => {
         dialogRef.current
            ?.querySelector('button:not([disabled]), textarea:not([disabled]), input:not([disabled])')
            ?.focus();
      });

      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !processingRef.current) {
            event.preventDefault();
            closeRef.current?.();
            return;
         }

         if (event.key !== "Tab") {
            return;
         }

         const focusable = dialogRef.current?.querySelectorAll(
            'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href]:not([aria-disabled="true"]), [tabindex]:not([tabindex="-1"])',
         );
         if (!focusable?.length) {
            return;
         }

         const first = focusable[0];
         const last = focusable[focusable.length - 1];
         if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
         } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
         }
      };

      document.addEventListener("keydown", handleKeyDown);
      return () => {
         document.removeEventListener("keydown", handleKeyDown);
         document.body.style.overflow = previousOverflow;
         requestAnimationFrame(() => triggerRef.current?.focus?.());
      };
   }, [open]);

   if (!open) {
      return null;
   }

   return (
      <div
         className="publishing-dialog-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !processing) {
               onClose();
            }
         }}
      >
         <section
            ref={dialogRef}
            className="publishing-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="publishing-dialog-title"
            aria-describedby="publishing-dialog-description"
            aria-busy={processing || undefined}
         >
            <div className="publishing-dialog-copy">
               <h3 id="publishing-dialog-title">{title}</h3>
               <p id="publishing-dialog-description">{description}</p>
            </div>
            {children}
         </section>
      </div>
   );
}

function PublishingContent({
   authFetch,
   authIdentity,
   organizationId,
   organizationName,
   onPublicationPublished,
   initialFactCheckId,
}) {
   const { addToast } = useNotification();
   const initialFactCheckKey = initialFactCheckId ? String(initialFactCheckId) : null;
   const [offset, setOffset] = useState(0);
   const [queue, setQueue] = useState({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
   const [queueLoading, setQueueLoading] = useState(true);
   const [queueRefreshing, setQueueRefreshing] = useState(false);
   const [queueError, setQueueError] = useState("");
   const [queueRequestVersion, setQueueRequestVersion] = useState(0);

   const [selectedId, setSelectedId] = useState(initialFactCheckKey);
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(Boolean(initialFactCheckKey));
   const [detailError, setDetailError] = useState("");
   const [detailUnavailable, setDetailUnavailable] = useState(false);
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);

   const [authorityError, setAuthorityError] = useState("");
   const [authorityRetrying, setAuthorityRetrying] = useState(false);
   const [actionError, setActionError] = useState("");
   const [conflict, setConflict] = useState(null);
   const [mutation, setMutation] = useState(null);
   const [confirmation, setConfirmation] = useState(null);
   const [reworkReason, setReworkReason] = useState("");

   const mountedRef = useRef(true);
   const authorityGenerationRef = useRef(0);
   const queueRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const mutationRequestIdRef = useRef(0);
   const selectedIdRef = useRef(initialFactCheckKey);
   const hasLoadedQueueRef = useRef(false);
   const detailHeadingRef = useRef(null);
   const detailErrorRef = useRef(null);
   const conflictRef = useRef(null);
   const queueHeadingRef = useRef(null);
   const actionMessageRef = useRef(null);
   const focusDetailAfterLoadRef = useRef(Boolean(initialFactCheckKey));
   const focusQueueAfterMutationRef = useRef(false);
   const focusActionMessageRef = useRef(false);

   const allowedActions = Array.isArray(detail?.allowed_actions) ? detail.allowed_actions : [];
   const isInitialReview = detail?.workflow_kind === "INITIAL";
   const isEditorialReview = detail?.workflow_kind === "EDITORIAL_REVISION";
   const publishAction = isEditorialReview ? "PUBLISH_REPLACEMENT" : "PUBLISH";
   const authorityBlocked = Boolean(authorityError) || authorityRetrying || detailLoading;

   const queueUrl = useMemo(() => {
      const query = new URLSearchParams({
         organization_id: organizationId,
         queue: "REVIEW",
         workflow_kind: "ALL",
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });
      return `${resolveApiEndpoint("PUBLICATION_WORK_ITEMS")}?${query.toString()}`;
   }, [offset, organizationId]);

   const isOperationContextCurrent = useCallback(
      (operation) =>
         mountedRef.current &&
         operation.authIdentity === authIdentity &&
         String(operation.organizationId) === String(organizationId) &&
         operation.authorityGeneration === authorityGenerationRef.current,
      [authIdentity, organizationId],
   );

   const isOperationCurrent = useCallback(
      (operation) =>
         isOperationContextCurrent(operation) && String(selectedIdRef.current) === String(operation.factCheckId),
      [isOperationContextCurrent],
   );

   const isMutationContextCurrent = useCallback(
      (operation) => isOperationContextCurrent(operation) && mutationRequestIdRef.current === operation.requestId,
      [isOperationContextCurrent],
   );

   const revokeAuthority = useCallback(() => {
      authorityGenerationRef.current += 1;
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      mutationRequestIdRef.current += 1;
      setAuthorityRetrying(false);
      setMutation(null);
      setConfirmation(null);
      setQueueLoading(false);
      setQueueRefreshing(false);
      setDetailLoading(false);
      setActionError("");
      setConflict(null);
      setAuthorityError("Your publication access for this organization is no longer available.");
      focusActionMessageRef.current = true;
   }, []);

   useEffect(() => {
      mountedRef.current = true;
      return () => {
         mountedRef.current = false;
         authorityGenerationRef.current += 1;
         queueRequestIdRef.current += 1;
         detailRequestIdRef.current += 1;
         mutationRequestIdRef.current += 1;
      };
   }, []);

   useEffect(() => {
      selectedIdRef.current = selectedId;
   }, [selectedId]);

   useEffect(() => {
      if (focusActionMessageRef.current && (actionError || authorityError)) {
         focusActionMessageRef.current = false;
         if (!confirmation) {
            actionMessageRef.current?.focus();
         }
      }
   }, [actionError, authorityError, confirmation]);

   useEffect(() => {
      if (conflict) {
         requestAnimationFrame(() => conflictRef.current?.focus());
      }
   }, [conflict]);

   useEffect(() => {
      if (detailError && !detail) {
         requestAnimationFrame(() => detailErrorRef.current?.focus());
      }
   }, [detail, detailError]);

   useEffect(() => {
      if (focusQueueAfterMutationRef.current && !selectedId) {
         focusQueueAfterMutationRef.current = false;
         queueHeadingRef.current?.focus();
      }
   }, [selectedId]);

   useEffect(() => {
      let cancelled = false;
      const requestId = queueRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      queueRequestIdRef.current = requestId;

      if (!hasLoadedQueueRef.current) {
         setQueueLoading(true);
      } else {
         setQueueRefreshing(true);
      }

      authFetch(queueUrl, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               queueRequestIdRef.current !== requestId ||
               authorityGenerationRef.current !== authorityGeneration
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

            hasLoadedQueueRef.current = true;
            setAuthorityError("");
            setAuthorityRetrying(false);
            setQueue({
               count,
               limit: Number(data?.limit ?? PAGE_SIZE),
               offset: Number(data?.offset ?? offset),
               results,
            });
            setQueueError("");
            setQueueLoading(false);
            setQueueRefreshing(false);
         })
         .catch((error) => {
            if (
               cancelled ||
               !mountedRef.current ||
               queueRequestIdRef.current !== requestId ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }

            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }

            setAuthorityRetrying(false);
            setQueueError(error?.message || "Unable to load the publication Review queue.");
            setQueueLoading(false);
            setQueueRefreshing(false);
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, offset, queueRequestVersion, queueUrl, revokeAuthority]);

   useEffect(() => {
      if (!selectedId) {
         return undefined;
      }

      let cancelled = false;
      const requestId = detailRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      const requestSelection = selectedId;
      detailRequestIdRef.current = requestId;
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);

      const query = new URLSearchParams({
         organization_id: organizationId,
         workflow_kind: "ALL",
      });
      const url = `${resolveApiEndpoint("PUBLICATION_WORK_ITEM_DETAIL", "FACT_CHECK", selectedId)}?${query.toString()}`;

      authFetch(url, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== requestId ||
               String(selectedIdRef.current) !== String(requestSelection) ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }

            const leftReview = data?.publication_status !== "IN_REVIEW";
            setDetail(data);
            setDetailLoading(false);
            setDetailUnavailable(leftReview);
            setDetailError(leftReview ? "This fact check is no longer waiting in the publication Review queue." : "");
            setActionError("");
            setConflict(null);
            setConfirmation(null);
            setReworkReason("");

            if (focusDetailAfterLoadRef.current && window.matchMedia("(max-width: 920px)").matches) {
               focusDetailAfterLoadRef.current = false;
               requestAnimationFrame(() => detailHeadingRef.current?.focus());
            } else {
               focusDetailAfterLoadRef.current = false;
            }
         })
         .catch((error) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== requestId ||
               String(selectedIdRef.current) !== String(requestSelection) ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }

            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }

            const unavailable = error?.status === 404;
            setDetail(null);
            setDetailLoading(false);
            setDetailUnavailable(unavailable);
            setDetailError(
               unavailable
                  ? "This publication review item is no longer available."
                  : error?.message || "Unable to load this publication review item.",
            );

            if (unavailable) {
               setQueueRefreshing(true);
               setQueueRequestVersion((current) => current + 1);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, detailRequestVersion, organizationId, revokeAuthority, selectedId]);

   const requestQueueRefresh = useCallback(() => {
      setQueueRefreshing(true);
      setQueueRequestVersion((current) => current + 1);
   }, []);

   const makeOperation = useCallback(
      () => ({
         authIdentity,
         organizationId,
         authorityGeneration: authorityGenerationRef.current,
         requestId: mutationRequestIdRef.current + 1,
         factCheckId: selectedIdRef.current,
         workflowKind: detail?.workflow_kind,
      }),
      [authIdentity, detail?.workflow_kind, organizationId],
   );

   const refreshAfterConflict = useCallback(
      async (operation, error) => {
         const requestId = detailRequestIdRef.current + 1;
         detailRequestIdRef.current = requestId;
         const query = new URLSearchParams({
            organization_id: operation.organizationId,
            workflow_kind: "ALL",
         });
         const url = `${resolveApiEndpoint(
            "PUBLICATION_WORK_ITEM_DETAIL",
            "FACT_CHECK",
            operation.factCheckId,
         )}?${query.toString()}`;

         try {
            const latest = await authFetch(url, { method: "GET" });
            if (
               !isOperationCurrent(operation) ||
               detailRequestIdRef.current !== requestId ||
               String(selectedIdRef.current) !== String(operation.factCheckId)
            ) {
               return;
            }

            const remainsInReview = latest?.publication_status === "IN_REVIEW";
            setDetail(latest);
            setDetailUnavailable(!remainsInReview);
            setDetailError(
               remainsInReview ? "" : "This review item changed and has left the publication Review queue.",
            );
            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The publication action was not applied.",
               remainsInReview,
            });
         } catch (refreshError) {
            if (
               !isOperationCurrent(operation) ||
               detailRequestIdRef.current !== requestId ||
               String(selectedIdRef.current) !== String(operation.factCheckId)
            ) {
               return;
            }

            if (refreshError?.status === 401 || refreshError?.status === 403) {
               revokeAuthority();
               return;
            }

            setDetail(null);
            setDetailUnavailable(true);
            setDetailError(
               refreshError?.status === 404
                  ? "This review item changed and has left the publication Review queue."
                  : "The latest review state could not be loaded.",
            );
            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The publication action was not applied.",
               remainsInReview: false,
            });
         }
      },
      [authFetch, isOperationCurrent, revokeAuthority],
   );

   const handleMutationError = useCallback(
      (error, operation, fallbackMessage) => {
         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority();
            return;
         }

         if (error?.status === 409) {
            requestQueueRefresh();
            if (!isOperationCurrent(operation)) {
               return;
            }

            setConfirmation(null);
            setReworkReason("");
            setActionError("");
            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The publication action was not applied.",
               remainsInReview: null,
            });
            refreshAfterConflict(operation, error);
            return;
         }

         if (error?.status === 404) {
            requestQueueRefresh();
            if (!isOperationCurrent(operation)) {
               return;
            }

            setDetailUnavailable(true);
            setDetailError("This publication review item is no longer available.");
            return;
         }

         if (!isOperationCurrent(operation)) {
            return;
         }

         setActionError(error?.message || fallbackMessage);
         focusActionMessageRef.current = true;
      },
      [isOperationCurrent, refreshAfterConflict, requestQueueRefresh, revokeAuthority],
   );

   const handlePublish = async () => {
      if (
         mutation ||
         authorityBlocked ||
         conflict ||
         !(isInitialReview || isEditorialReview) ||
         !allowedActions.includes(publishAction)
      ) {
         return;
      }

      const operation = makeOperation();
      mutationRequestIdRef.current = operation.requestId;
      setMutation("publish");
      setActionError("");

      try {
         const endpoint =
            operation.workflowKind === "EDITORIAL_REVISION" ? "EDITORIAL_REVISION_PUBLISH" : "FACT_CHECK_PUBLISH";
         const body =
            operation.workflowKind === "EDITORIAL_REVISION"
               ? {
                    organization_id: operation.organizationId,
                    expected_predecessor_version: detail?.concurrency?.predecessor_version,
                    expected_revision_version: detail?.concurrency?.article_version,
                    expected_edit_generation: detail?.concurrency?.edit_generation ?? detail?.edit_generation,
                    expected_decision_revision:
                       detail?.concurrency?.decision_revision ?? detail?.decision?.revision_number,
                 }
               : {
                    organization_id: operation.organizationId,
                    expected_edit_generation: detail?.concurrency?.edit_generation ?? detail?.edit_generation,
                    expected_decision_revision:
                       detail?.concurrency?.decision_revision ?? detail?.decision?.revision_number,
                 };
         const published = await authFetch(resolveApiEndpoint(endpoint, operation.factCheckId), {
            method: "POST",
            body,
         });

         if (!isMutationContextCurrent(operation)) {
            return;
         }

         requestQueueRefresh();
         if (!isOperationCurrent(operation)) {
            return;
         }

         const version = published?.article?.version ?? published?.version ?? detail?.version;
         selectedIdRef.current = null;
         setSelectedId(null);
         setDetail(null);
         setConfirmation(null);
         showWorkspaceSuccess(addToast, {
            title: operation.workflowKind === "EDITORIAL_REVISION" ? "Replacement published" : "Fact-check published",
            message:
               operation.workflowKind === "EDITORIAL_REVISION"
                  ? version
                     ? `Article v${version} is now the current published version.`
                     : "The replacement article is now the current published version."
                  : version
                    ? `Article v${version} is now published.`
                    : "The fact-check article is now published.",
            duration: WORKSPACE_LONG_TOAST_DURATION,
         });
         focusQueueAfterMutationRef.current = true;
         if (operation.workflowKind === "EDITORIAL_REVISION") {
            onPublicationPublished?.(published);
         }
      } catch (error) {
         if (isMutationContextCurrent(operation)) {
            handleMutationError(error, operation, "Unable to publish this fact check.");
         }
      } finally {
         if (isMutationContextCurrent(operation)) {
            setMutation(null);
         }
      }
   };

   const handleReturnForRework = async (event) => {
      event.preventDefault();
      const reason = reworkReason.trim();
      if (!reason) {
         setActionError("A nonblank rework reason is required.");
         focusActionMessageRef.current = true;
         return;
      }
      if (reason.length > 2000) {
         setActionError("Rework reason must be 2000 characters or fewer.");
         focusActionMessageRef.current = true;
         return;
      }
      if (
         mutation ||
         authorityBlocked ||
         conflict ||
         !(isInitialReview || isEditorialReview) ||
         !allowedActions.includes("RETURN_FOR_REWORK")
      ) {
         return;
      }

      const operation = makeOperation();
      mutationRequestIdRef.current = operation.requestId;
      setMutation("return");
      setActionError("");

      try {
         const endpoint =
            operation.workflowKind === "EDITORIAL_REVISION"
               ? "EDITORIAL_REVISION_RETURN_FOR_REWORK"
               : "FACT_CHECK_RETURN_FOR_REWORK";
         await authFetch(resolveApiEndpoint(endpoint, operation.factCheckId), {
            method: "POST",
            body: {
               organization_id: operation.organizationId,
               expected_edit_generation: detail?.concurrency?.edit_generation ?? detail?.edit_generation,
               reason,
            },
         });

         if (!isMutationContextCurrent(operation)) {
            return;
         }

         requestQueueRefresh();
         if (!isOperationCurrent(operation)) {
            return;
         }

         selectedIdRef.current = null;
         setSelectedId(null);
         setDetail(null);
         setConfirmation(null);
         setReworkReason("");
         showWorkspaceSuccess(addToast, {
            title: "Returned for rework",
            message: "The article has been returned to Drafting for revision.",
         });
         focusQueueAfterMutationRef.current = true;
      } catch (error) {
         if (isMutationContextCurrent(operation)) {
            handleMutationError(error, operation, "Unable to return this article for rework.");
         }
      } finally {
         if (isMutationContextCurrent(operation)) {
            setMutation(null);
         }
      }
   };

   const handleSelect = (item) => {
      if (mutation) {
         return;
      }

      const factCheckId = item?.resource_id;
      if (!factCheckId || String(factCheckId) === String(selectedIdRef.current)) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedIdRef.current = String(factCheckId);
      setSelectedId(String(factCheckId));
      setDetail(null);
      setDetailError("");
      setDetailUnavailable(false);
      setConflict(null);
      setActionError("");
      setConfirmation(null);
      setReworkReason("");
      focusDetailAfterLoadRef.current = true;
   };

   const returnToQueue = () => {
      if (mutation) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedIdRef.current = null;
      setSelectedId(null);
      setDetail(null);
      setDetailError("");
      setDetailUnavailable(false);
      setConflict(null);
      setActionError("");
      setConfirmation(null);
      setReworkReason("");
      focusQueueAfterMutationRef.current = true;
   };

   const handleRefresh = () => {
      requestQueueRefresh();
      if (selectedId && !conflict) {
         setDetailRequestVersion((current) => current + 1);
      }
   };

   const handleAuthorityRetry = () => {
      authorityGenerationRef.current += 1;
      setAuthorityRetrying(true);
      setQueueError("");
      setQueueRequestVersion((current) => current + 1);
      if (selectedId && !conflict) {
         setDetailRequestVersion((current) => current + 1);
      }
   };

   const pageStart = queue.count === 0 ? 0 : queue.offset + 1;
   const pageEnd = Math.min(queue.offset + queue.results.length, queue.count);
   const hasPrevious = offset > 0;
   const hasNext = offset + queue.limit < queue.count;

   return (
      <div className="publishing-panel">
         <div className="publishing-boundary-note">
            <Icons name="landmark" size={18} />
            <p>
               Publication is an organization-scoped institutional action. It does not replace or rewrite the recorded
               human adjudication.
            </p>
         </div>

         <div ref={actionMessageRef} className="publishing-operation-messages" tabIndex={-1} aria-live="polite">
            {authorityError ? (
               <div className="publishing-message publishing-message--critical" role="alert">
                  <Icons name="lock" size={18} />
                  <div>
                     <strong>Publication access unavailable</strong>
                     <p>{authorityError}</p>
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        loading={authorityRetrying}
                        loadingLabel="Retrying…"
                        onClick={handleAuthorityRetry}
                     >
                        Retry access
                     </Button>
                  </div>
               </div>
            ) : null}
            {actionError ? (
               <div className="publishing-message publishing-message--critical" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{actionError}</p>
               </div>
            ) : null}
         </div>

         {authorityError ? null : (
            <div className={`publishing-workbench ${selectedId ? "has-selection" : ""}`}>
               <section className="publishing-queue" aria-labelledby="publishing-queue-heading">
                  <div className="publishing-queue-header">
                     <div>
                        <h3 id="publishing-queue-heading" ref={queueHeadingRef} tabIndex={-1}>
                           Publication review
                        </h3>
                        <p>{queue.count} fact checks waiting</p>
                     </div>
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        leadingIcon={<Icons name="refresh-cw" size={15} />}
                        loading={queueRefreshing}
                        loadingLabel="Refreshing…"
                        onClick={handleRefresh}
                     >
                        Refresh
                     </Button>
                  </div>

                  {queueLoading ? (
                     <div className="publishing-state" role="status">
                        <Icons name="loader" size={22} className="publishing-spinner" />
                        <strong>Loading publication reviews…</strong>
                     </div>
                  ) : queueError && queue.results.length === 0 ? (
                     <div className="publishing-state publishing-state--error" role="alert">
                        <Icons name="alert-circle" size={22} />
                        <strong>Review queue unavailable</strong>
                        <p>{queueError}</p>
                        <Button type="button" variant="secondary" density="compact" onClick={requestQueueRefresh}>
                           Try again
                        </Button>
                     </div>
                  ) : queue.results.length === 0 ? (
                     <div className="publishing-state">
                        <Icons name="check-circle" size={24} />
                        <strong>Review queue clear</strong>
                        <p>No fact checks are waiting for publication review.</p>
                     </div>
                  ) : (
                     <>
                        {queueError ? (
                           <div className="publishing-queue-warning" role="alert">
                              {queueError} Existing results remain available.
                           </div>
                        ) : null}
                        <ul className="publishing-queue-list">
                           {queue.results.map((item) => {
                              const selected = String(item?.resource_id) === String(selectedId);
                              const isRevisionItem = item?.workflow_kind === "EDITORIAL_REVISION";
                              return (
                                 <li key={item?.resource_id}>
                                    <button
                                       type="button"
                                       className={`publishing-queue-row ${selected ? "is-selected" : ""}`}
                                       aria-current={selected ? "true" : undefined}
                                       disabled={Boolean(mutation)}
                                       onClick={() => handleSelect(item)}
                                    >
                                       <span className="publishing-row-topline">
                                          <span>{isRevisionItem ? "Editorial revision" : "Initial publication"}</span>
                                          <VerdictBadge verdict={item?.decision?.verdict} />
                                       </span>
                                       <strong>{item?.article?.headline || "Untitled fact check"}</strong>
                                       <span className="publishing-row-claim">
                                          {item?.decision?.canonical_claim ||
                                             item?.claim?.context_text ||
                                             "Claim context unavailable"}
                                       </span>
                                       <span className="publishing-row-metadata">
                                          Article v{item?.article?.version ?? "–"} ·{" "}
                                          {actorName(item?.lifecycle?.drafted_by, "Drafter unavailable")}
                                       </span>
                                       <span className="publishing-row-metadata">
                                          Submitted {formatDateTime(item?.lifecycle?.submitted_for_review_at)}
                                       </span>
                                       {isRevisionItem ? (
                                          <>
                                             <span className="publishing-row-metadata">
                                                Revision reason: {item?.revision?.reason || "Not recorded"}
                                             </span>
                                             <span className="publishing-row-metadata">
                                                Predecessor: {item?.revision?.predecessor?.headline || "Untitled"} · v
                                                {item?.revision?.predecessor?.version ?? "–"}
                                             </span>
                                          </>
                                       ) : null}
                                    </button>
                                 </li>
                              );
                           })}
                        </ul>
                     </>
                  )}

                  {!queueLoading && queue.count > 0 ? (
                     <div className="publishing-pagination" aria-label="Publication review pagination">
                        <Button
                           type="button"
                           variant="secondary"
                           density="compact"
                           disabled={!hasPrevious || queueRefreshing}
                           onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                        >
                           Previous
                        </Button>
                        <span>
                           {pageStart}–{pageEnd} of {queue.count}
                        </span>
                        <Button
                           type="button"
                           variant="secondary"
                           density="compact"
                           disabled={!hasNext || queueRefreshing}
                           onClick={() => setOffset(offset + PAGE_SIZE)}
                        >
                           Next
                        </Button>
                     </div>
                  ) : null}
               </section>

               <section className="publishing-detail" aria-labelledby="publishing-detail-heading">
                  {!selectedId ? (
                     <div className="publishing-state publishing-state--detail">
                        <Icons name="landmark" size={25} />
                        <h3 id="publishing-detail-heading">Select a review item</h3>
                        <p>Inspect the human judgment, submitted article, sources, and readiness before acting.</p>
                     </div>
                  ) : (
                     <>
                        <Button
                           type="button"
                           variant="ghost"
                           density="compact"
                           className="publishing-return-to-queue"
                           leadingIcon={<Icons name="arrow-left" size={15} />}
                           disabled={Boolean(mutation)}
                           onClick={returnToQueue}
                        >
                           Back to Publishing
                        </Button>

                        {detailLoading && !detail ? (
                           <div className="publishing-state" role="status">
                              <Icons name="loader" size={22} className="publishing-spinner" />
                              <strong>Loading canonical review…</strong>
                           </div>
                        ) : detailError && !detail ? (
                           <div className="publishing-state publishing-state--error" role="alert">
                              <Icons name={detailUnavailable ? "eye-off" : "alert-circle"} size={22} />
                              <h3 id="publishing-detail-heading" ref={detailErrorRef} tabIndex={-1}>
                                 {detailUnavailable ? "Review item unavailable" : "Unable to load review item"}
                              </h3>
                              <p>{detailError}</p>
                              <div className="publishing-state-actions">
                                 {!detailUnavailable ? (
                                    <Button
                                       type="button"
                                       variant="secondary"
                                       density="compact"
                                       onClick={() => setDetailRequestVersion((current) => current + 1)}
                                    >
                                       Try again
                                    </Button>
                                 ) : null}
                                 <Button
                                    type="button"
                                    variant="ghost"
                                    density="compact"
                                    disabled={Boolean(mutation)}
                                    onClick={returnToQueue}
                                 >
                                    Return to queue
                                 </Button>
                              </div>
                           </div>
                        ) : detail ? (
                           <div className="publishing-detail-content">
                              <header className="publishing-detail-header">
                                 <div>
                                    <span className="publishing-status-label">
                                       {detailUnavailable
                                          ? "Left review queue"
                                          : isEditorialReview
                                            ? "Editorial replacement review"
                                            : "Initial publication review"}
                                    </span>
                                    <h3 id="publishing-detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                                       {detail.headline || "Untitled fact check"}
                                    </h3>
                                    <p>
                                       {detail.decision?.canonical_claim ||
                                          detail.canonical_claim ||
                                          "Claim unavailable"}
                                    </p>
                                 </div>
                                 <span className="publishing-version-label">Article v{detail.version ?? "–"}</span>
                              </header>

                              {!isInitialReview && !isEditorialReview ? (
                                 <div className="publishing-message publishing-message--warning" role="alert">
                                    <Icons name="alert-triangle" size={18} />
                                    <p>This publication workflow is not available in Publishing.</p>
                                 </div>
                              ) : null}

                              {conflict ? (
                                 <div ref={conflictRef} className="publishing-conflict" role="alert" tabIndex={-1}>
                                    <Icons name="alert-triangle" size={19} />
                                    <div>
                                       <strong>{conflict.code}</strong>
                                       <p>{conflict.detail}</p>
                                       <p>
                                          {conflict.remainsInReview === null
                                             ? "Loading the latest server state…"
                                             : conflict.remainsInReview
                                               ? "This review item changed. The latest server state has been loaded."
                                               : "This item is no longer available in the publication Review queue."}
                                       </p>
                                       {conflict.remainsInReview ? (
                                          <Button
                                             type="button"
                                             variant="secondary"
                                             density="compact"
                                             onClick={() => setConflict(null)}
                                          >
                                             Review latest state
                                          </Button>
                                       ) : null}
                                    </div>
                                 </div>
                              ) : null}

                              {detailUnavailable ? (
                                 <div className="publishing-message publishing-message--warning" role="status">
                                    <Icons name="info" size={18} />
                                    <div>
                                       <strong>Review item changed</strong>
                                       <p>{detailError}</p>
                                       <Button
                                          type="button"
                                          variant="secondary"
                                          density="compact"
                                          disabled={Boolean(mutation)}
                                          onClick={returnToQueue}
                                       >
                                          Return to review queue
                                       </Button>
                                    </div>
                                 </div>
                              ) : null}

                              <section
                                 className="publishing-review-section publishing-context"
                                 aria-labelledby="publishing-context-heading"
                              >
                                 <div className="publishing-section-heading">
                                    <div>
                                       <h4 id="publishing-context-heading">Publication context</h4>
                                       <p>Institutional scope and submitted article lifecycle.</p>
                                    </div>
                                 </div>
                                 <dl className="publishing-context-grid">
                                    <div>
                                       <dt>Organization</dt>
                                       <dd>
                                          {organizationName || detail.organization?.name || "Selected organization"}
                                       </dd>
                                    </div>
                                    <div>
                                       <dt>Status</dt>
                                       <dd>{formatLabel(detail.publication_status)}</dd>
                                    </div>
                                    <div>
                                       <dt>Article version</dt>
                                       <dd>{detail.version ?? "Not recorded"}</dd>
                                    </div>
                                    <div>
                                       <dt>Drafter</dt>
                                       <dd>{actorName(detail.drafted_by)}</dd>
                                    </div>
                                    <div>
                                       <dt>Submitted</dt>
                                       <dd>
                                          <FormattedDateTime value={detail.submitted_for_review_at} />
                                       </dd>
                                    </div>
                                 </dl>
                              </section>

                              <HumanJudgment detail={detail} />

                              <section
                                 className="publishing-review-section publishing-article-review"
                                 aria-labelledby="publishing-article-heading"
                              >
                                 <div className="publishing-section-heading">
                                    <div>
                                       <h4 id="publishing-article-heading">Article under review</h4>
                                       <p>
                                          Review the submitted editorial content against the recorded factual judgment.
                                          Publication does not alter that judgment.
                                       </p>
                                    </div>
                                 </div>
                                 <h5 className="publishing-article-headline">
                                    {detail.headline || "Untitled fact check"}
                                 </h5>
                                 <p className="publishing-article-summary">
                                    {detail.summary || "No summary recorded."}
                                 </p>
                                 <div className="publishing-article-body">
                                    {detail.article_body || "No article body recorded."}
                                 </div>
                              </section>

                              <Readiness detail={detail} />

                              <PublishingReferenceMaterial
                                 detail={detail}
                                 isEditorialReview={isEditorialReview}
                              />

                              {!detailUnavailable &&
                              (isInitialReview || isEditorialReview) &&
                              !conflict &&
                              (allowedActions.includes("RETURN_FOR_REWORK") || allowedActions.includes(publishAction)) ? (
                                 <section
                                    className="publishing-action-gate"
                                    aria-labelledby="publishing-action-gate-heading"
                                 >
                                    <div className="publishing-section-heading">
                                       <div>
                                          <h4 id="publishing-action-gate-heading">Publication decision</h4>
                                          <p>
                                             Approve the submitted article for institutional publication, or return it
                                             to Drafting with a specific rework reason.
                                          </p>
                                       </div>
                                    </div>
                                    <div className="publishing-primary-actions">
                                       {allowedActions.includes("RETURN_FOR_REWORK") ? (
                                          <Button
                                             type="button"
                                             variant="secondary"
                                             density="standard"
                                             disabled={Boolean(mutation) || authorityBlocked}
                                             onClick={() => {
                                                setConfirmation("return");
                                                setActionError("");
                                                setReworkReason("");
                                             }}
                                             leadingIcon={<Icons name="arrow-left" size={16} />}
                                          >
                                             Return for rework
                                          </Button>
                                       ) : null}
                                       {allowedActions.includes(publishAction) ? (
                                          <Button
                                             type="button"
                                             variant="primary"
                                             density="standard"
                                             disabled={Boolean(mutation) || authorityBlocked}
                                             onClick={() => {
                                                setConfirmation("publish");
                                                setActionError("");
                                             }}
                                             leadingIcon={<Icons name="check-circle" size={16} />}
                                          >
                                             {isEditorialReview ? "Publish replacement" : "Publish article"}
                                          </Button>
                                       ) : null}
                                    </div>
                                 </section>
                              ) : null}
                           </div>
                        ) : null}
                     </>
                  )}
               </section>
            </div>
         )}

         <PublishingDecisionDialog
            open={confirmation === "publish" && Boolean(detail)}
            processing={mutation === "publish"}
            title={
               isEditorialReview
                  ? `Publish this replacement article for ${organizationName || detail?.organization?.name || "this organization"}?`
                  : `Publish this article for ${organizationName || detail?.organization?.name || "this organization"}?`
            }
            description={
               isEditorialReview
                  ? "Confirm the replacement version and preserved factual authority before publishing."
                  : "Confirm the exact institutional publication record before publishing."
            }
            onClose={() => {
               if (!mutation) {
                  setConfirmation(null);
               }
            }}
         >
            {actionError ? (
               <div className="publishing-dialog-error" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{actionError}</p>
               </div>
            ) : null}
            <div className="publishing-confirmation publishing-confirmation--publish">
               <div className="publishing-confirmation-heading">
                  <Icons name="landmark" size={20} />
                  <div>
                     <h5>{isEditorialReview ? "Replacement publication" : "Institutional publication"}</h5>
                     <p>
                        This is a consequential publication action. Review the record below before confirming.
                     </p>
                  </div>
               </div>
               <dl className="publishing-confirmation-facts">
                  <div>
                     <dt>Headline</dt>
                     <dd>{detail?.headline || "Untitled fact check"}</dd>
                  </div>
                  <div>
                     <dt>Factual verdict</dt>
                     <dd>{formatLabel(detail?.verdict || detail?.decision?.verdict)}</dd>
                  </div>
                  <div>
                     <dt>Article version</dt>
                     <dd>{detail?.version ?? "Not recorded"}</dd>
                  </div>
               </dl>
               {isEditorialReview ? (
                  <ul>
                     <li>This publishes a replacement editorial version.</li>
                     <li>The previous publication remains preserved in version history.</li>
                     <li>The human factual verdict and adjudication decision do not change.</li>
                     <li>This action is an editorial revision, not a factual correction.</li>
                  </ul>
               ) : (
                  <ul>
                     <li>Publication seals this article version.</li>
                     <li>
                        {organizationName || detail?.organization?.name || "The selected organization"} becomes the
                        institutional publisher.
                     </li>
                     <li>The verification assignment completes only after successful publication.</li>
                     <li>
                        The published article cannot be edited directly; later replacement requires a separate
                        revision or correction workflow.
                     </li>
                  </ul>
               )}
               <div className="publishing-confirmation-actions">
                  <Button
                     type="button"
                     variant="secondary"
                     density="standard"
                     disabled={Boolean(mutation)}
                     onClick={() => setConfirmation(null)}
                  >
                     Cancel
                  </Button>
                  <Button
                     type="button"
                     variant="primary"
                     density="standard"
                     loading={mutation === "publish"}
                     loadingLabel="Publishing…"
                     disabled={Boolean(mutation)}
                     onClick={handlePublish}
                  >
                     {isEditorialReview ? "Publish replacement" : "Publish article"}
                  </Button>
               </div>
            </div>
         </PublishingDecisionDialog>

         <PublishingDecisionDialog
            open={confirmation === "return" && Boolean(detail)}
            processing={mutation === "return"}
            title={`Return this ${isEditorialReview ? "editorial revision" : "article"} to Drafting?`}
            description="The factual adjudication remains unchanged. The submitted article returns to Drafting with your recorded reason."
            onClose={() => {
               if (!mutation) {
                  setConfirmation(null);
                  setReworkReason("");
               }
            }}
         >
            {actionError ? (
               <div className="publishing-dialog-error" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{actionError}</p>
               </div>
            ) : null}
            <form className="publishing-confirmation publishing-confirmation--rework" onSubmit={handleReturnForRework}>
               <div className="publishing-confirmation-heading">
                  <Icons name="arrow-left" size={20} />
                  <div>
                     <h5>Return for rework</h5>
                     <p>Give the drafter a clear reason for why this article should not be published yet.</p>
                  </div>
               </div>
               <div className="publishing-field">
                  <label htmlFor="publishing-rework-reason">Reason for rework</label>
                  <Textarea
                     id="publishing-rework-reason"
                     rows={5}
                     value={reworkReason}
                     maxLength={2000}
                     required
                     disabled={Boolean(mutation)}
                     onChange={(event) => setReworkReason(event.target.value)}
                  />
                  <span>{reworkReason.length}/2000</span>
               </div>
               <div className="publishing-confirmation-actions">
                  <Button
                     type="button"
                     variant="secondary"
                     density="standard"
                     disabled={Boolean(mutation)}
                     onClick={() => {
                        setConfirmation(null);
                        setReworkReason("");
                     }}
                  >
                     Keep in review
                  </Button>
                  <Button
                     type="submit"
                     variant="destructive"
                     density="standard"
                     loading={mutation === "return"}
                     loadingLabel="Returning…"
                     disabled={!reworkReason.trim() || Boolean(mutation)}
                  >
                     Return for rework
                  </Button>
               </div>
            </form>
         </PublishingDecisionDialog>
      </div>
   );
}

function PublishingPanel(props) {
   const { authFetch, token, user } = useAuth();
   const authIdentity = getAuthSessionIdentity(user, token);

   return (
      <PublishingContent
         key={`${props.organizationId}:${authIdentity}`}
         {...props}
         authFetch={authFetch}
         authIdentity={authIdentity}
      />
   );
}

export default PublishingPanel;
