import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import { getAuthSessionIdentity } from "../../utils/authIdentity";
import Icons from "../Icons.jsx";
import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";
import Input from "../ui/Input.jsx";
import Select from "../ui/Select.jsx";
import Textarea from "../ui/Textarea.jsx";

import "./FactualCorrectionPanel.css";

const PAGE_SIZE = 20;
const COLLECTION_STATUSES = ["ACTIVE", "COMPLETED", "CANCELLED", "ALL"];
const VERDICTS = ["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"];
const REJECTION_REASONS = [
   "IRRELEVANT",
   "UNRELIABLE_SOURCE",
   "INACCESSIBLE_SOURCE",
   "DUPLICATE",
   "OUTDATED",
   "MISREPRESENTS_SOURCE",
   "INSUFFICIENT_CONTEXT",
   "FABRICATED",
   "OTHER",
];

const ACTION_LABELS = {
   REVIEW_CORRECTION_EVIDENCE: "Review correction evidence",
   SAVE_CORRECTION_PROPOSAL: "Save proposal",
   PREPARE_CORRECTION_PROPOSAL: "Prepare proposal",
   PUBLISH_FACTUAL_CORRECTION: "Publish factual correction",
   CANCEL_FACTUAL_CORRECTION: "Cancel factual correction",
};

const EMPTY_EDITOR = Object.freeze({
   proposed_verdict: "",
   proposed_canonical_claim: "",
   proposed_rationale: "",
   headline: "",
   summary: "",
   article_body: "",
   source_urls: [""],
   verification_run_id: "",
});

const dirtyProposalSnapshots = new Map();

function proposalSnapshotKey(authIdentity, organizationId, requestId) {
   return requestId ? `${authIdentity}:${organizationId}:${requestId}` : null;
}

function cloneEditor(editor) {
   return {
      ...editor,
      source_urls: Array.isArray(editor?.source_urls) ? [...editor.source_urls] : [""],
   };
}

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

function actorName(actor, fallback = "Not recorded") {
   return actor?.username ? `@${actor.username}` : fallback;
}

function verificationRunLabel(run) {
   const evidenceCount = run?.evidence_count;
   const evidenceSummary = Number.isInteger(evidenceCount)
      ? `${evidenceCount} ${evidenceCount === 1 ? "evidence item" : "evidence items"}`
      : "Evidence count unavailable";
   const pipelineVersion = String(run?.pipeline_version || "").trim();
   const isNumericPipelineVersion = /^\d+(?:\.\d+)*$/.test(pipelineVersion);
   const pipelineLabel = pipelineVersion
      ? `Pipeline ${isNumericPipelineVersion ? `v${pipelineVersion}` : pipelineVersion}`
      : "Pipeline version unavailable";

   return `Completed ${formatDateTime(run?.completed_at)} · ${pipelineLabel} · ${evidenceSummary}`;
}

function resolveEligibleVerificationRun(eligibleRuns, verificationRunId) {
   if (!Array.isArray(eligibleRuns) || !verificationRunId) {
      return null;
   }

   return eligibleRuns.find((run) => String(run?.id) === String(verificationRunId)) || null;
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

function proposalToEditor(proposal) {
   if (!proposal) {
      return { ...EMPTY_EDITOR, source_urls: [""] };
   }

   const sources = Array.isArray(proposal.source_urls) ? proposal.source_urls : [];
   return {
      proposed_verdict: proposal.proposed_verdict || "",
      proposed_canonical_claim: proposal.proposed_canonical_claim || "",
      proposed_rationale: proposal.proposed_rationale || "",
      headline: proposal.headline || "",
      summary: proposal.summary || "",
      article_body: proposal.article_body || "",
      source_urls: sources.length > 0 ? sources : [""],
      verification_run_id: proposal.verification_run_id || "",
   };
}

function sameEditor(left, right) {
   return JSON.stringify(left) === JSON.stringify(right);
}

function fieldError(errors, name) {
   const value = errors?.[name];
   if (Array.isArray(value)) {
      return value.join(" ");
   }
   return value ? String(value) : "";
}

function StatusBadge({ value }) {
   const tone = value === "COMPLETED" ? "success" : value === "CANCELLED" ? "critical" : "info";
   return <Badge tone={tone}>{formatLabel(value)}</Badge>;
}

function StageBadge({ stage }) {
   const tone =
      stage === "COMPLETED"
         ? "success"
         : stage === "CANCELLED"
           ? "critical"
           : stage === "PREPARED"
             ? "warning"
             : "info";
   return <Badge tone={tone}>{stage || "Unavailable"}</Badge>;
}

export function CorrectionDialog({
   open,
   title,
   description,
   confirmLabel,
   cancelLabel = "Keep editing",
   confirmVariant = "primary",
   processing = false,
   onConfirm,
   onClose,
   children,
}) {
   const dialogRef = useRef(null);
   const cancelRef = useRef(null);
   const triggerRef = useRef(null);
   const processingRef = useRef(processing);
   const closeRef = useRef(onClose);

   useEffect(() => {
      processingRef.current = processing;
      closeRef.current = onClose;
   }, [onClose, processing]);

   useEffect(() => {
      if (!open) {
         return undefined;
      }

      triggerRef.current = document.activeElement;
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      requestAnimationFrame(() => cancelRef.current?.focus());

      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !processingRef.current) {
            event.preventDefault();
            closeRef.current();
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
         className="correction-dialog-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !processing) {
               onClose();
            }
         }}
      >
         <section
            ref={dialogRef}
            className="correction-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="correction-dialog-title"
            aria-describedby="correction-dialog-description"
            aria-busy={processing || undefined}
         >
            <div className="correction-dialog-copy">
               <h3 id="correction-dialog-title">{title}</h3>
               <p id="correction-dialog-description">{description}</p>
            </div>
            {children}
            <div className="correction-dialog-actions">
               <Button ref={cancelRef} type="button" variant="secondary" disabled={processing} onClick={onClose}>
                  {cancelLabel}
               </Button>
               <Button
                  type="button"
                  variant={confirmVariant}
                  loading={processing}
                  loadingLabel="Processing…"
                  onClick={onConfirm}
               >
                  {confirmLabel}
               </Button>
            </div>
         </section>
      </div>
   );
}

function DecisionCard({ title, decision, current = false, emptyMessage }) {
   if (!decision) {
      return (
         <article className="correction-decision">
            <div className="correction-decision-heading">
               <h5>{title}</h5>
               <Badge tone="neutral">Not created</Badge>
            </div>
            <p className="correction-decision-empty">
               {emptyMessage || "No human decision is available in this response."}
            </p>
         </article>
      );
   }

   return (
      <article className={`correction-decision ${current ? "correction-decision--current" : ""}`}>
         <div className="correction-decision-heading">
            <h5>{title}</h5>
            <Badge tone={current ? "success" : "neutral"}>{formatLabel(decision?.verdict)}</Badge>
         </div>
         <dl className="correction-metadata-grid">
            <div className="correction-metadata-wide">
               <dt>Canonical claim</dt>
               <dd>{decision?.canonical_claim || "Not recorded"}</dd>
            </div>
            <div className="correction-metadata-wide">
               <dt>Human rationale</dt>
               <dd>{decision?.rationale || "Not recorded"}</dd>
            </div>
            <div>
               <dt>Decision revision</dt>
               <dd>{decision?.revision_number ?? "Not recorded"}</dd>
            </div>
            <div>
               <dt>Decided by</dt>
               <dd>{actorName(decision?.decided_by)}</dd>
            </div>
            <div>
               <dt>Decided at</dt>
               <dd>{formatDateTime(decision?.decided_at)}</dd>
            </div>
         </dl>
      </article>
   );
}

function decisionIdentity(decision) {
   const value = decision?.id ?? decision?.decision_id;
   return value === null || value === undefined ? null : String(value);
}

function hasMeaningfulReplacementDecision(detail) {
   if (detail?.stage !== "COMPLETED" || !detail?.current_decision) {
      return false;
   }

   const current = detail.current_decision;
   const hasDecisionContent = Boolean(
      decisionIdentity(current) ||
      current.verdict ||
      current.canonical_claim ||
      current.rationale ||
      (current.revision_number !== null && current.revision_number !== undefined),
   );
   if (!hasDecisionContent) {
      return false;
   }

   const predecessorId = decisionIdentity(detail.predecessor_decision);
   const currentId = decisionIdentity(current);
   return !(predecessorId && currentId && predecessorId === currentId);
}

function Blockers({ blockers }) {
   const groups = Object.entries(blockers || {}).filter(([, values]) => Array.isArray(values) && values.length > 0);
   if (groups.length === 0) {
      return <p className="correction-inline-empty">The server has not reported any current action blockers.</p>;
   }

   return (
      <div className="correction-blocker-groups">
         {groups.map(([action, values]) => (
            <section key={action} className="correction-blocker-group">
               <h5>{ACTION_LABELS[action] || formatLabel(action)}</h5>
               <ul>
                  {values.map((blocker, index) => (
                     <li key={`${action}-${blocker?.code || "blocker"}-${index}`}>
                        <Icons name="alert-circle" size={16} />
                        <span>
                           <strong>{formatLabel(blocker?.code, "Action blocker")}</strong>
                           {blocker?.detail || "This action is not currently available."}
                        </span>
                     </li>
                  ))}
               </ul>
            </section>
         ))}
      </div>
   );
}

function ProposalSummary({ proposal, eligibleVerificationRuns }) {
   if (!proposal) {
      return <p className="correction-inline-empty">No correction proposal has been recorded.</p>;
   }

   const verificationRunId = proposal.verification_run_id || "";
   const linkedVerificationRun = resolveEligibleVerificationRun(eligibleVerificationRuns, verificationRunId);
   const verificationRunSummary = !verificationRunId
      ? "Not linked"
      : linkedVerificationRun
        ? verificationRunLabel(linkedVerificationRun)
        : "Linked verification run metadata unavailable";

   return (
      <div className="correction-proposal-readonly">
         <div className="correction-proposal-title">
            <div>
               <h5>{proposal.headline || "Untitled correction proposal"}</h5>
               <p>
                  Proposal v{proposal.version} · {formatLabel(proposal.status)}
               </p>
            </div>
            <Badge tone={proposal.status === "PREPARED" ? "warning" : "info"}>
               {formatLabel(proposal.proposed_verdict)}
            </Badge>
         </div>
         <dl className="correction-metadata-grid">
            <div className="correction-metadata-wide">
               <dt>Proposed canonical claim</dt>
               <dd>{proposal.proposed_canonical_claim}</dd>
            </div>
            <div className="correction-metadata-wide">
               <dt>Proposed rationale</dt>
               <dd>{proposal.proposed_rationale}</dd>
            </div>
            <div className="correction-metadata-wide">
               <dt>Article summary</dt>
               <dd>{proposal.summary}</dd>
            </div>
            <div className="correction-metadata-wide">
               <dt>Article body</dt>
               <dd className="correction-article-body">{proposal.article_body}</dd>
            </div>
            <div>
               <dt>Prepared by</dt>
               <dd>{actorName(proposal.prepared_by)}</dd>
            </div>
            <div>
               <dt>Prepared at</dt>
               <dd>{formatDateTime(proposal.prepared_at)}</dd>
            </div>
            <div>
               <dt>Supporting verification run</dt>
               <dd>{verificationRunSummary}</dd>
            </div>
            <div>
               <dt>Proposal created</dt>
               <dd>{formatDateTime(proposal.created_at)}</dd>
            </div>
            <div>
               <dt>Proposal updated</dt>
               <dd>{formatDateTime(proposal.updated_at)}</dd>
            </div>
         </dl>
         <div className="correction-source-list">
            <strong>Proposal sources</strong>
            <ul>
               {proposal.source_urls.map((url) => {
                  const safeUrl = safeExternalUrl(url);
                  return (
                     <li key={url}>
                        {safeUrl ? (
                           <a href={safeUrl} target="_blank" rel="noopener noreferrer">
                              {url} <Icons name="external-link" size={14} />
                           </a>
                        ) : (
                           <span>{url}</span>
                        )}
                     </li>
                  );
               })}
            </ul>
         </div>
      </div>
   );
}

function FactualCorrectionContent({
   authFetch,
   authIdentity,
   organizationId,
   organizationName,
   requestId,
   status,
   offset,
   onNavigate,
   onDirtyChange,
   onOpenPublication,
}) {
   const dirtySnapshotKey = proposalSnapshotKey(authIdentity, organizationId, requestId);
   const initialDirtySnapshotRef = useRef(dirtySnapshotKey ? dirtyProposalSnapshots.get(dirtySnapshotKey) : null);
   const [queue, setQueue] = useState({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
   const [queueLoading, setQueueLoading] = useState(true);
   const [queueRefreshing, setQueueRefreshing] = useState(false);
   const [queueError, setQueueError] = useState("");
   const [queueRequestVersion, setQueueRequestVersion] = useState(0);
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(Boolean(requestId));
   const [detailError, setDetailError] = useState("");
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);
   const [authorityError, setAuthorityError] = useState("");
   const [notice, setNotice] = useState(() => initialDirtySnapshotRef.current?.notice || "");
   const [actionError, setActionError] = useState(() => initialDirtySnapshotRef.current?.actionError || "");
   const [fieldErrors, setFieldErrors] = useState(() => initialDirtySnapshotRef.current?.fieldErrors || {});
   const [conflict, setConflict] = useState(() => initialDirtySnapshotRef.current?.conflict || null);
   const [mutation, setMutation] = useState(null);
   const [editor, setEditor] = useState(() =>
      initialDirtySnapshotRef.current ? cloneEditor(initialDirtySnapshotRef.current.editor) : proposalToEditor(null),
   );
   const [editorBase, setEditorBase] = useState(() =>
      initialDirtySnapshotRef.current
         ? cloneEditor(initialDirtySnapshotRef.current.editorBase)
         : proposalToEditor(null),
   );
   const [evidenceDrafts, setEvidenceDrafts] = useState({});
   const [dialog, setDialog] = useState(null);
   const [cancellationReason, setCancellationReason] = useState("");
   const [publishedPublication, setPublishedPublication] = useState(null);

   const mountedRef = useRef(true);
   const authorityGenerationRef = useRef(0);
   const queueRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const mutationRequestIdRef = useRef(0);
   const selectedRequestIdRef = useRef(requestId || null);
   const loadedRequestIdRef = useRef(null);
   const dirtyOwnerKeyRef = useRef(initialDirtySnapshotRef.current ? dirtySnapshotKey : null);
   const preserveEditorOnNextLoadRef = useRef(Boolean(initialDirtySnapshotRef.current));
   const hasLoadedQueueRef = useRef(false);
   const queueStatusRef = useRef(COLLECTION_STATUSES.includes(status) ? status : "ACTIVE");
   const detailHeadingRef = useRef(null);
   const queueHeadingRef = useRef(null);
   const messageRef = useRef(null);
   const focusDetailAfterLoadRef = useRef(Boolean(requestId));
   const focusQueueAfterReturnRef = useRef(false);
   const proposalRefs = {
      proposed_verdict: useRef(null),
      proposed_canonical_claim: useRef(null),
      proposed_rationale: useRef(null),
      headline: useRef(null),
      summary: useRef(null),
      article_body: useRef(null),
      source_urls: useRef(null),
      verification_run_id: useRef(null),
      cancellation_reason: useRef(null),
   };

   const normalizedStatus = COLLECTION_STATUSES.includes(status) ? status : "ACTIVE";
   const allowedActions = Array.isArray(detail?.allowed_actions) ? detail.allowed_actions : [];
   const isDirty = !sameEditor(editor, editorBase);
   const canEditProposal = allowedActions.includes("SAVE_CORRECTION_PROPOSAL");
   const completedHasReplacementDecision = hasMeaningfulReplacementDecision(detail);
   const eligibleVerificationRuns = Array.isArray(detail?.eligible_verification_runs)
      ? detail.eligible_verification_runs
      : null;
   const selectedVerificationRunId = editor.verification_run_id.trim();
   const selectedVerificationRun = resolveEligibleVerificationRun(
      eligibleVerificationRuns,
      selectedVerificationRunId,
   );
   const hasUnresolvedLinkedVerificationRun = Boolean(selectedVerificationRunId && !selectedVerificationRun);
   const showVerificationRunSelect = Boolean(
      eligibleVerificationRuns && (eligibleVerificationRuns.length > 0 || selectedVerificationRunId),
   );

   const queueUrl = useMemo(() => {
      const query = new URLSearchParams({
         organization_id: organizationId,
         status: normalizedStatus,
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });
      return `${resolveApiEndpoint("FACTUAL_CORRECTION_COLLECTION")}?${query.toString()}`;
   }, [normalizedStatus, offset, organizationId]);

   const applyCanonicalDetail = useCallback(
      (nextDetail, { preserveEditor = false } = {}) => {
         setDetail(nextDetail);
         loadedRequestIdRef.current = nextDetail?.request?.id ? String(nextDetail.request.id) : null;
         if (!preserveEditor) {
            const nextEditor = proposalToEditor(nextDetail?.proposal);
            const nextSnapshotKey = proposalSnapshotKey(authIdentity, organizationId, nextDetail?.request?.id);
            if (nextSnapshotKey) {
               dirtyProposalSnapshots.delete(nextSnapshotKey);
               if (dirtyOwnerKeyRef.current === nextSnapshotKey) {
                  dirtyOwnerKeyRef.current = null;
               }
            }
            setEditor(nextEditor);
            setEditorBase(nextEditor);
            setFieldErrors({});
         }
      },
      [authIdentity, organizationId],
   );

   const invalidateRequests = useCallback(() => {
      authorityGenerationRef.current += 1;
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      mutationRequestIdRef.current += 1;
   }, []);

   const revokeAuthority = useCallback(() => {
      invalidateRequests();
      const snapshotKey = dirtyOwnerKeyRef.current || dirtySnapshotKey;
      if (snapshotKey) {
         dirtyProposalSnapshots.delete(snapshotKey);
      }
      dirtyOwnerKeyRef.current = null;
      setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
      setDetail(null);
      setQueueLoading(false);
      setQueueRefreshing(false);
      setDetailLoading(false);
      setMutation(null);
      setDialog(null);
      setNotice("");
      setActionError("");
      setConflict(null);
      setEditor(proposalToEditor(null));
      setEditorBase(proposalToEditor(null));
      setAuthorityError("Your factual-correction access for this organization is no longer available.");
   }, [dirtySnapshotKey, invalidateRequests]);

   useEffect(() => {
      mountedRef.current = true;
      return () => {
         mountedRef.current = false;
         invalidateRequests();
      };
   }, [invalidateRequests]);

   useEffect(() => {
      selectedRequestIdRef.current = requestId || null;
      if (focusQueueAfterReturnRef.current && !requestId) {
         focusQueueAfterReturnRef.current = false;
         requestAnimationFrame(() => queueHeadingRef.current?.focus());
      }
   }, [requestId]);

   const discardDirtyDraft = useCallback(() => {
      const snapshotKey = dirtyOwnerKeyRef.current || dirtySnapshotKey;
      if (snapshotKey) {
         dirtyProposalSnapshots.delete(snapshotKey);
      }
      dirtyOwnerKeyRef.current = null;
      setEditor(cloneEditor(editorBase));
   }, [dirtySnapshotKey, editorBase]);

   useEffect(() => {
      if (!dirtySnapshotKey || String(loadedRequestIdRef.current) !== String(requestId)) {
         return;
      }

      if (isDirty) {
         dirtyOwnerKeyRef.current = dirtySnapshotKey;
         dirtyProposalSnapshots.set(dirtySnapshotKey, {
            editor: cloneEditor(editor),
            editorBase: cloneEditor(editorBase),
            conflict,
            fieldErrors,
            actionError,
            notice,
         });
         return;
      }

      dirtyProposalSnapshots.delete(dirtySnapshotKey);

      if (dirtyOwnerKeyRef.current === dirtySnapshotKey) {
         dirtyOwnerKeyRef.current = null;
      }
   }, [actionError, conflict, dirtySnapshotKey, editor, editorBase, fieldErrors, isDirty, notice, requestId]);

   useEffect(() => {
      onDirtyChange?.(isDirty, isDirty ? discardDirtyDraft : null);
      return () => onDirtyChange?.(false, null);
   }, [discardDirtyDraft, isDirty, onDirtyChange]);

   useEffect(() => {
      if (!isDirty) {
         return undefined;
      }
      const warnBeforeUnload = (event) => {
         event.preventDefault();
         event.returnValue = "";
      };
      window.addEventListener("beforeunload", warnBeforeUnload);
      return () => window.removeEventListener("beforeunload", warnBeforeUnload);
   }, [isDirty]);

   useEffect(() => {
      if (notice || actionError || authorityError || conflict) {
         requestAnimationFrame(() => messageRef.current?.focus());
      }
   }, [actionError, authorityError, conflict, notice]);

   useEffect(() => {
      let cancelled = false;
      const sequence = queueRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      queueRequestIdRef.current = sequence;
      const statusChanged = queueStatusRef.current !== normalizedStatus;
      queueStatusRef.current = normalizedStatus;
      if (statusChanged) {
         hasLoadedQueueRef.current = false;
         setQueue({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
         setQueueLoading(true);
         setQueueRefreshing(false);
      } else if (hasLoadedQueueRef.current) {
         setQueueRefreshing(true);
      } else {
         setQueueLoading(true);
      }

      authFetch(queueUrl, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               queueRequestIdRef.current !== sequence ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }
            const count = Number(data?.count ?? 0);
            const results = Array.isArray(data?.results) ? data.results : [];
            const lastOffset = count > 0 ? Math.floor((count - 1) / PAGE_SIZE) * PAGE_SIZE : 0;
            if (results.length === 0 && offset > lastOffset) {
               onNavigate({
                  requestId: selectedRequestIdRef.current || null,
                  status: normalizedStatus,
                  offset: lastOffset,
                  replace: true,
               });
               return;
            }
            hasLoadedQueueRef.current = true;
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
               queueRequestIdRef.current !== sequence ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }
            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }
            setQueueError(error?.message || "Unable to load this organization's factual corrections.");
            setQueueLoading(false);
            setQueueRefreshing(false);
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, normalizedStatus, offset, onNavigate, queueRequestVersion, queueUrl, revokeAuthority]);

   useEffect(() => {
      if (!requestId) {
         setDetail(null);
         setDetailError("");
         setConflict(null);
         setPublishedPublication(null);
         return undefined;
      }

      const requestedId = String(requestId);
      const operationAuthIdentity = authIdentity;
      const isNewSelection = loadedRequestIdRef.current !== requestedId;
      const requestedSnapshotKey = proposalSnapshotKey(authIdentity, organizationId, requestedId);
      const restoredSnapshot = requestedSnapshotKey ? dirtyProposalSnapshots.get(requestedSnapshotKey) : null;
      if (isNewSelection) {
         setDetail(null);
         if (restoredSnapshot) {
            dirtyOwnerKeyRef.current = requestedSnapshotKey;
            setEditor(cloneEditor(restoredSnapshot.editor));
            setEditorBase(cloneEditor(restoredSnapshot.editorBase));
            setFieldErrors(restoredSnapshot.fieldErrors || {});
            setConflict(restoredSnapshot.conflict || null);
            setActionError(restoredSnapshot.actionError || "");
            setNotice(restoredSnapshot.notice || "");
         } else {
            setEditor(proposalToEditor(null));
            setEditorBase(proposalToEditor(null));
            setFieldErrors({});
            setConflict(null);
            setActionError("");
            setNotice("");
         }
         setEvidenceDrafts({});
         setDialog(null);
         setCancellationReason("");
         setPublishedPublication(null);
      } else if (restoredSnapshot) {
         dirtyOwnerKeyRef.current = requestedSnapshotKey;
         setEditor(cloneEditor(restoredSnapshot.editor));
         setEditorBase(cloneEditor(restoredSnapshot.editorBase));
         setFieldErrors(restoredSnapshot.fieldErrors || {});
         setConflict(restoredSnapshot.conflict || null);
         setActionError(restoredSnapshot.actionError || "");
         setNotice(restoredSnapshot.notice || "");
      }

      let cancelled = false;
      const sequence = detailRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      const preserveEditor = Boolean(restoredSnapshot) || (preserveEditorOnNextLoadRef.current && !isNewSelection);
      preserveEditorOnNextLoadRef.current = false;
      detailRequestIdRef.current = sequence;
      setDetailLoading(true);
      setDetailError("");

      const query = new URLSearchParams({ organization_id: organizationId });
      const url = `${resolveApiEndpoint("FACTUAL_CORRECTION_DETAIL", requestedId)}?${query.toString()}`;
      authFetch(url, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== sequence ||
               authorityGenerationRef.current !== authorityGeneration ||
               String(selectedRequestIdRef.current) !== requestedId ||
               operationAuthIdentity !== authIdentity
            ) {
               return;
            }
            applyCanonicalDetail(data, { preserveEditor });
            setDetailLoading(false);
            setDetailError("");
            if (focusDetailAfterLoadRef.current && window.matchMedia("(max-width: 980px)").matches) {
               requestAnimationFrame(() => detailHeadingRef.current?.focus());
            }
            focusDetailAfterLoadRef.current = false;
         })
         .catch((error) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== sequence ||
               authorityGenerationRef.current !== authorityGeneration ||
               String(selectedRequestIdRef.current) !== requestedId
            ) {
               return;
            }
            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }
            setDetailLoading(false);
            setDetailError(
               error?.status === 404
                  ? "This correction request is unavailable in the selected organization."
                  : error?.message || "Unable to load this factual correction.",
            );
         });

      return () => {
         cancelled = true;
      };
   }, [
      applyCanonicalDetail,
      authFetch,
      authIdentity,
      detailRequestVersion,
      organizationId,
      requestId,
      revokeAuthority,
   ]);

   const refreshQueue = useCallback(() => {
      setQueueRefreshing(true);
      setQueueRequestVersion((current) => current + 1);
   }, []);

   const refreshDetail = useCallback((preserveEditor = false) => {
      preserveEditorOnNextLoadRef.current = preserveEditor;
      setDetailRequestVersion((current) => current + 1);
   }, []);

   const requestDiscard = (continuation) => {
      if (!isDirty) {
         continuation();
         return;
      }
      setDialog({ type: "discard", continuation });
   };

   const selectRequest = (nextRequestId) => {
      if (!nextRequestId || mutation || String(nextRequestId) === String(requestId)) {
         return;
      }
      requestDiscard(() => {
         detailRequestIdRef.current += 1;
         focusDetailAfterLoadRef.current = true;
         onNavigate({ requestId: String(nextRequestId), status: normalizedStatus, offset });
      });
   };

   const returnToQueue = () => {
      if (mutation) {
         return;
      }
      requestDiscard(() => {
         detailRequestIdRef.current += 1;
         focusQueueAfterReturnRef.current = true;
         onNavigate({ requestId: null, status: normalizedStatus, offset });
      });
   };

   const runMutation = async ({ kind, endpoint, method = "POST", body, preserveEditor = false, onSuccess }) => {
      if (mutation || !detail || !requestId) {
         return;
      }

      const operation = {
         authIdentity,
         organizationId,
         correctionRequestId: String(requestId),
         authorityGeneration: authorityGenerationRef.current,
         sequence: mutationRequestIdRef.current + 1,
      };
      mutationRequestIdRef.current = operation.sequence;
      setMutation(kind);
      setActionError("");
      setNotice("");
      setFieldErrors({});
      setConflict(null);

      const operationIsCurrent = () =>
         mountedRef.current &&
         mutationRequestIdRef.current === operation.sequence &&
         authorityGenerationRef.current === operation.authorityGeneration &&
         operation.authIdentity === authIdentity &&
         String(operation.organizationId) === String(organizationId) &&
         String(selectedRequestIdRef.current) === operation.correctionRequestId;

      try {
         const response = await authFetch(endpoint, { method, body });
         if (!operationIsCurrent()) {
            return;
         }
         await onSuccess(response);
      } catch (error) {
         if (!operationIsCurrent()) {
            return;
         }
         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority();
            return;
         }
         if (error?.status === 400) {
            if (kind === "prepare-proposal" || kind === "publish-correction") {
               setDialog(null);
            }
            setFieldErrors(error?.errors || {});
            setActionError(
               `${error?.code || "INVALID_INPUT"}: ${error?.message || "Review the highlighted fields and try again."}`,
            );
            const firstInvalid = Object.keys(error?.errors || {}).find((name) => proposalRefs[name]);
            if (firstInvalid) {
               requestAnimationFrame(() => proposalRefs[firstInvalid].current?.focus());
            }
            return;
         }
         if (error?.status === 404) {
            if (kind === "prepare-proposal" || kind === "publish-correction" || kind === "cancel-correction") {
               setDialog(null);
            }
            setActionError("This correction request is no longer available in the selected organization.");
            refreshQueue();
            refreshDetail(preserveEditor || isDirty);
            return;
         }
         if (error?.status === 409) {
            if (kind === "prepare-proposal" || kind === "publish-correction" || kind === "cancel-correction") {
               setDialog(null);
            }
            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The correction changed before this action completed.",
               blockers: error?.blockers,
               current: error?.current,
            });
            refreshQueue();
            refreshDetail(preserveEditor || isDirty);
            return;
         }
         if (kind === "prepare-proposal" || kind === "publish-correction" || kind === "cancel-correction") {
            setDialog(null);
         }
         setActionError(error?.message || "The factual-correction action could not be completed.");
      } finally {
         if (mountedRef.current && mutationRequestIdRef.current === operation.sequence) {
            setMutation(null);
         }
      }
   };

   const updateEditor = (name, value) => {
      setEditor((current) => ({ ...current, [name]: value }));
      setFieldErrors((current) => ({ ...current, [name]: undefined }));
   };

   const validateProposal = () => {
      const errors = {};
      [
         "proposed_verdict",
         "proposed_canonical_claim",
         "proposed_rationale",
         "headline",
         "summary",
         "article_body",
      ].forEach((name) => {
         if (!String(editor[name] || "").trim()) {
            errors[name] = "This field is required.";
         }
      });
      if (editor.headline.trim().length > 300) {
         errors.headline = "Headline must be 300 characters or fewer.";
      }
      const sources = editor.source_urls.map((value) => value.trim()).filter(Boolean);
      if (sources.length === 0) {
         errors.source_urls = "Add at least one HTTP or HTTPS source URL.";
      } else if (sources.some((value) => !safeExternalUrl(value))) {
         errors.source_urls = "Each source must be a valid HTTP or HTTPS URL.";
      }
      setFieldErrors(errors);
      const firstInvalid = Object.keys(errors)[0];
      if (firstInvalid) {
         requestAnimationFrame(() => proposalRefs[firstInvalid]?.current?.focus());
      }
      return { valid: Object.keys(errors).length === 0, sources };
   };

   const saveProposal = async (event) => {
      event.preventDefault();
      if (!canEditProposal) {
         return;
      }
      const validation = validateProposal();
      if (!validation.valid) {
         setActionError("Review the highlighted proposal fields before saving.");
         return;
      }

      await runMutation({
         kind: "save-proposal",
         endpoint: resolveApiEndpoint("FACTUAL_CORRECTION_PROPOSAL", requestId),
         method: "PUT",
         preserveEditor: true,
         body: {
            organization_id: organizationId,
            expected_predecessor_version: detail.concurrency?.expected_predecessor_version,
            expected_decision_revision: detail.concurrency?.expected_decision_revision,
            expected_proposal_version: detail.concurrency?.expected_proposal_version,
            proposed_verdict: editor.proposed_verdict,
            proposed_canonical_claim: editor.proposed_canonical_claim.trim(),
            proposed_rationale: editor.proposed_rationale.trim(),
            headline: editor.headline.trim(),
            summary: editor.summary.trim(),
            article_body: editor.article_body.trim(),
            source_urls: validation.sources,
            verification_run_id: editor.verification_run_id.trim() || null,
         },
         onSuccess: async (response) => {
            applyCanonicalDetail(response);
            setNotice("Correction proposal saved. It remains non-authoritative until final publication succeeds.");
            refreshQueue();
         },
      });
   };

   const prepareProposal = () => {
      if (!allowedActions.includes("PREPARE_CORRECTION_PROPOSAL") || isDirty) {
         return;
      }
      setDialog({ type: "prepare" });
   };

   const confirmPrepare = async () => {
      await runMutation({
         kind: "prepare-proposal",
         endpoint: resolveApiEndpoint("FACTUAL_CORRECTION_PROPOSAL_PREPARE", requestId),
         body: {
            organization_id: organizationId,
            expected_predecessor_version: detail.concurrency?.expected_predecessor_version,
            expected_decision_revision: detail.concurrency?.expected_decision_revision,
            expected_proposal_version: detail.concurrency?.expected_proposal_version,
         },
         onSuccess: async (response) => {
            applyCanonicalDetail(response);
            setDialog(null);
            setNotice("Proposal prepared and frozen. It has not been published and is not authoritative.");
            refreshQueue();
         },
      });
   };

   const confirmPublish = async () => {
      await runMutation({
         kind: "publish-correction",
         endpoint: resolveApiEndpoint("FACTUAL_CORRECTION_PUBLISH", requestId),
         body: {
            organization_id: organizationId,
            expected_predecessor_version: detail.concurrency?.expected_predecessor_version,
            expected_decision_revision: detail.concurrency?.expected_decision_revision,
            expected_proposal_version: detail.concurrency?.expected_proposal_version,
         },
         onSuccess: async (response) => {
            applyCanonicalDetail(response?.correction);
            setPublishedPublication(response?.publication || null);
            setDialog(null);
            setNotice(
               hasMeaningfulReplacementDecision(response?.correction)
                  ? "Factual correction published. The returned replacement decision and publication are now the current institutional authority."
                  : "Factual correction published. The returned decision payload does not distinguish replacement factual authority; review the neutral authority comparison.",
            );
            refreshQueue();
         },
      });
   };

   const confirmCancel = async () => {
      const reason = cancellationReason.trim();
      if (!reason) {
         setFieldErrors((current) => ({ ...current, cancellation_reason: "A cancellation reason is required." }));
         requestAnimationFrame(() => proposalRefs.cancellation_reason.current?.focus());
         return;
      }
      await runMutation({
         kind: "cancel-correction",
         endpoint: resolveApiEndpoint("FACTUAL_CORRECTION_CANCEL", requestId),
         body: {
            organization_id: organizationId,
            expected_predecessor_version: detail.concurrency?.expected_predecessor_version,
            expected_decision_revision: detail.concurrency?.expected_decision_revision,
            expected_proposal_version: detail.concurrency?.expected_proposal_version,
            cancellation_reason: reason,
         },
         onSuccess: async (response) => {
            applyCanonicalDetail(response);
            setCancellationReason("");
            setDialog(null);
            setNotice(
               "Factual correction cancelled. Its historical evidence and proposal remain available for inspection.",
            );
            refreshQueue();
         },
      });
   };

   const reviewEvidence = async (item) => {
      const draft = evidenceDrafts[item.evidence_id] || {
         evidence_status: "VERIFIED",
         moderator_notes: "",
         rejection_reason: "",
      };
      if (draft.evidence_status === "REJECTED" && !draft.rejection_reason) {
         setActionError("Select a rejection reason for this correction evidence review.");
         return;
      }
      await runMutation({
         kind: `review-evidence:${item.evidence_id}`,
         endpoint: resolveApiEndpoint("FACTUAL_CORRECTION_EVIDENCE_REVIEW", requestId, item.evidence_id),
         body: {
            organization_id: organizationId,
            evidence_status: draft.evidence_status,
            expected_evidence_status: item.evidence_status,
            expected_case_id: item.evidence_case_id || null,
            moderator_notes: draft.moderator_notes.trim(),
            rejection_reason: draft.evidence_status === "REJECTED" ? draft.rejection_reason : null,
            expected_predecessor_version: detail.concurrency?.expected_predecessor_version,
            expected_decision_revision: detail.concurrency?.expected_decision_revision,
         },
         onSuccess: async (response) => {
            applyCanonicalDetail(response);
            setEvidenceDrafts((current) => {
               const next = { ...current };
               delete next[item.evidence_id];
               return next;
            });
            setNotice("Correction evidence review recorded with its human reviewer provenance.");
            refreshQueue();
         },
      });
   };

   const pageStart = queue.count === 0 ? 0 : queue.offset + 1;
   const pageEnd = Math.min(queue.offset + queue.results.length, queue.count);
   const hasPrevious = offset > 0;
   const hasNext = offset + queue.limit < queue.count;
   const evidenceItems = Array.isArray(detail?.evidence_review?.items) ? detail.evidence_review.items : [];

   const renderEvidence = () => (
      <section className="correction-section" aria-labelledby="correction-evidence-heading">
         <div className="correction-section-heading">
            <div>
               <h4 id="correction-evidence-heading">Dedicated correction evidence review</h4>
               <p>
                  These reviews belong only to this factual correction and do not enter the ordinary Evidence Review
                  workspace.
               </p>
            </div>
            <Badge tone={detail.evidence_review?.is_complete ? "success" : "warning"}>
               {detail.evidence_review?.reviewed_count ?? 0} of {detail.evidence_review?.count ?? evidenceItems.length}{" "}
               reviewed
            </Badge>
         </div>
         {evidenceItems.length === 0 ? (
            <p className="correction-inline-empty">No correction evidence is currently returned by the server.</p>
         ) : (
            <ol className="correction-evidence-list">
               {evidenceItems.map((item, index) => {
                  const externalUrl = safeExternalUrl(item.evidence_url);
                  const itemActions = Array.isArray(item.allowed_actions) ? item.allowed_actions : [];
                  const canReview = itemActions.includes("REVIEW_CORRECTION_EVIDENCE");
                  const draft = evidenceDrafts[item.evidence_id] || {
                     evidence_status: "VERIFIED",
                     moderator_notes: "",
                     rejection_reason: "",
                  };
                  return (
                     <li key={item.evidence_id}>
                        <div className="correction-evidence-title">
                           <div>
                              <strong>{item.evidence_caption || `Evidence record ${index + 1}`}</strong>
                              <span>{formatLabel(item.evidence_type, "Evidence type unavailable")}</span>
                           </div>
                           <Badge tone={item.has_qualifying_correction_review ? "success" : "neutral"}>
                              {formatLabel(item.evidence_status)}
                           </Badge>
                        </div>
                        {externalUrl ? (
                           <a
                              className="correction-external-link"
                              href={externalUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                           >
                              {item.evidence_url} <Icons name="external-link" size={14} />
                           </a>
                        ) : item.evidence_url ? (
                           <p className="correction-invalid-url">The recorded source URL cannot be opened safely.</p>
                        ) : null}
                        <dl className="correction-metadata-grid correction-evidence-metadata">
                           <div>
                              <dt>Contributor</dt>
                              <dd>{actorName(item.contributor)}</dd>
                           </div>
                           <div>
                              <dt>Submitted</dt>
                              <dd>{formatDateTime(item.submitted_at)}</dd>
                           </div>
                           <div>
                              <dt>Qualifying correction review</dt>
                              <dd>{item.has_qualifying_correction_review ? "Recorded" : "Not recorded"}</dd>
                           </div>
                           <div>
                              <dt>Reaffirmation</dt>
                              <dd>{item.is_reaffirmation ? "Yes" : "No"}</dd>
                           </div>
                        </dl>
                        {item.correction_review ? (
                           <div className="correction-review-provenance">
                              <strong>Correction review provenance</strong>
                              <p>
                                 {formatLabel(item.correction_review.previous_evidence_status)} →{" "}
                                 {formatLabel(item.correction_review.new_evidence_status)} by{" "}
                                 {actorName(item.correction_review.reviewed_by)} ·{" "}
                                 {formatDateTime(item.correction_review.reviewed_at)}
                              </p>
                              {item.correction_review.moderator_notes ? (
                                 <p>{item.correction_review.moderator_notes}</p>
                              ) : null}
                              {item.correction_review.rejection_reason ? (
                                 <p>Rejection reason: {formatLabel(item.correction_review.rejection_reason)}</p>
                              ) : null}
                           </div>
                        ) : null}
                        {canReview ? (
                           <div
                              className="correction-evidence-form"
                              aria-label={`Review ${item.evidence_caption || `evidence record ${index + 1}`}`}
                           >
                              <div className="correction-field">
                                 <label htmlFor={`correction-evidence-status-${item.evidence_id}`}>
                                    Correction review outcome
                                 </label>
                                 <Select
                                    id={`correction-evidence-status-${item.evidence_id}`}
                                    value={draft.evidence_status}
                                    disabled={Boolean(mutation)}
                                    onChange={(event) =>
                                       setEvidenceDrafts((current) => ({
                                          ...current,
                                          [item.evidence_id]: {
                                             ...draft,
                                             evidence_status: event.target.value,
                                             rejection_reason:
                                                event.target.value === "REJECTED" ? draft.rejection_reason : "",
                                          },
                                       }))
                                    }
                                 >
                                    <option value="VERIFIED">Verified</option>
                                    <option value="REJECTED">Rejected</option>
                                 </Select>
                              </div>
                              {draft.evidence_status === "REJECTED" ? (
                                 <div className="correction-field">
                                    <label htmlFor={`correction-rejection-${item.evidence_id}`}>Rejection reason</label>
                                    <Select
                                       id={`correction-rejection-${item.evidence_id}`}
                                       required
                                       value={draft.rejection_reason}
                                       disabled={Boolean(mutation)}
                                       onChange={(event) =>
                                          setEvidenceDrafts((current) => ({
                                             ...current,
                                             [item.evidence_id]: { ...draft, rejection_reason: event.target.value },
                                          }))
                                       }
                                    >
                                       <option value="">Select a reason</option>
                                       {REJECTION_REASONS.map((reason) => (
                                          <option key={reason} value={reason}>
                                             {formatLabel(reason)}
                                          </option>
                                       ))}
                                    </Select>
                                 </div>
                              ) : null}
                              <div className="correction-field correction-field--wide">
                                 <label htmlFor={`correction-notes-${item.evidence_id}`}>Reviewer notes</label>
                                 <Textarea
                                    id={`correction-notes-${item.evidence_id}`}
                                    rows={3}
                                    maxLength={2000}
                                    value={draft.moderator_notes}
                                    disabled={Boolean(mutation)}
                                    onChange={(event) =>
                                       setEvidenceDrafts((current) => ({
                                          ...current,
                                          [item.evidence_id]: { ...draft, moderator_notes: event.target.value },
                                       }))
                                    }
                                 />
                              </div>
                              <Button
                                 type="button"
                                 variant="primary"
                                 loading={mutation === `review-evidence:${item.evidence_id}`}
                                 loadingLabel="Recording review…"
                                 disabled={Boolean(mutation)}
                                 onClick={() => reviewEvidence(item)}
                              >
                                 Record correction review
                              </Button>
                           </div>
                        ) : null}
                     </li>
                  );
               })}
            </ol>
         )}
      </section>
   );

   const renderProposalEditor = () => (
      <form className="correction-proposal-form" onSubmit={saveProposal} noValidate>
         <div className="correction-form-grid">
            <div className="correction-field">
               <label htmlFor="correction-proposed-verdict">Proposed verdict</label>
               <Select
                  ref={proposalRefs.proposed_verdict}
                  id="correction-proposed-verdict"
                  required
                  value={editor.proposed_verdict}
                  disabled={!canEditProposal || Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "proposed_verdict"))}
                  aria-describedby={
                     fieldError(fieldErrors, "proposed_verdict") ? "correction-proposed-verdict-error" : undefined
                  }
                  onChange={(event) => updateEditor("proposed_verdict", event.target.value)}
               >
                  <option value="">Select a verdict</option>
                  {VERDICTS.map((verdict) => (
                     <option key={verdict} value={verdict}>
                        {formatLabel(verdict)}
                     </option>
                  ))}
               </Select>
               {fieldError(fieldErrors, "proposed_verdict") ? (
                  <span id="correction-proposed-verdict-error" className="correction-field-error">
                     {fieldError(fieldErrors, "proposed_verdict")}
                  </span>
               ) : null}
            </div>
            <div className="correction-field correction-field--wide">
               <label htmlFor="correction-proposed-claim">Proposed canonical claim</label>
               <Textarea
                  ref={proposalRefs.proposed_canonical_claim}
                  id="correction-proposed-claim"
                  rows={3}
                  required
                  value={editor.proposed_canonical_claim}
                  disabled={!canEditProposal || Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "proposed_canonical_claim"))}
                  aria-describedby={
                     fieldError(fieldErrors, "proposed_canonical_claim") ? "correction-proposed-claim-error" : undefined
                  }
                  onChange={(event) => updateEditor("proposed_canonical_claim", event.target.value)}
               />
               {fieldError(fieldErrors, "proposed_canonical_claim") ? (
                  <span id="correction-proposed-claim-error" className="correction-field-error">
                     {fieldError(fieldErrors, "proposed_canonical_claim")}
                  </span>
               ) : null}
            </div>
            <div className="correction-field correction-field--wide">
               <label htmlFor="correction-proposed-rationale">Proposed human rationale</label>
               <Textarea
                  ref={proposalRefs.proposed_rationale}
                  id="correction-proposed-rationale"
                  rows={5}
                  required
                  value={editor.proposed_rationale}
                  disabled={!canEditProposal || Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "proposed_rationale"))}
                  aria-describedby="correction-proposed-rationale-help"
                  onChange={(event) => updateEditor("proposed_rationale", event.target.value)}
               />
               <span
                  id="correction-proposed-rationale-help"
                  className={
                     fieldError(fieldErrors, "proposed_rationale") ? "correction-field-error" : "correction-field-help"
                  }
               >
                  {fieldError(fieldErrors, "proposed_rationale") ||
                     "This proposal assists accountable human publication; it is not itself factual authority."}
               </span>
            </div>
            <div className="correction-field correction-field--wide">
               <label htmlFor="correction-headline">Correction headline</label>
               <Input
                  ref={proposalRefs.headline}
                  id="correction-headline"
                  required
                  maxLength={300}
                  value={editor.headline}
                  disabled={!canEditProposal || Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "headline"))}
                  aria-describedby="correction-headline-meta"
                  onChange={(event) => updateEditor("headline", event.target.value)}
               />
               <span
                  id="correction-headline-meta"
                  className={fieldError(fieldErrors, "headline") ? "correction-field-error" : "correction-field-help"}
               >
                  {fieldError(fieldErrors, "headline") || `${editor.headline.length}/300`}
               </span>
            </div>
            <div className="correction-field correction-field--wide">
               <label htmlFor="correction-summary">Article summary</label>
               <Textarea
                  ref={proposalRefs.summary}
                  id="correction-summary"
                  rows={4}
                  required
                  value={editor.summary}
                  disabled={!canEditProposal || Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "summary"))}
                  aria-describedby={fieldError(fieldErrors, "summary") ? "correction-summary-error" : undefined}
                  onChange={(event) => updateEditor("summary", event.target.value)}
               />
               {fieldError(fieldErrors, "summary") ? (
                  <span id="correction-summary-error" className="correction-field-error">
                     {fieldError(fieldErrors, "summary")}
                  </span>
               ) : null}
            </div>
            <div className="correction-field correction-field--wide">
               <label htmlFor="correction-article-body">Article body</label>
               <Textarea
                  ref={proposalRefs.article_body}
                  id="correction-article-body"
                  rows={12}
                  required
                  value={editor.article_body}
                  disabled={!canEditProposal || Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "article_body"))}
                  aria-describedby={
                     fieldError(fieldErrors, "article_body") ? "correction-article-body-error" : undefined
                  }
                  onChange={(event) => updateEditor("article_body", event.target.value)}
               />
               {fieldError(fieldErrors, "article_body") ? (
                  <span id="correction-article-body-error" className="correction-field-error">
                     {fieldError(fieldErrors, "article_body")}
                  </span>
               ) : null}
            </div>
            <fieldset className="correction-source-editor correction-field--wide">
               <legend>Source URLs</legend>
               <p>Only HTTP and HTTPS URLs can be submitted. Server validation remains authoritative.</p>
               {editor.source_urls.map((url, index) => (
                  <div key={index} className="correction-source-row">
                     <label className="sr-only" htmlFor={`correction-source-${index}`}>
                        Source URL {index + 1}
                     </label>
                     <Input
                        ref={index === 0 ? proposalRefs.source_urls : undefined}
                        id={`correction-source-${index}`}
                        type="url"
                        maxLength={2000}
                        value={url}
                        disabled={!canEditProposal || Boolean(mutation)}
                        invalid={Boolean(fieldError(fieldErrors, "source_urls"))}
                        aria-describedby={
                           fieldError(fieldErrors, "source_urls") ? "correction-source-error" : undefined
                        }
                        onChange={(event) => {
                           setEditor((current) => ({
                              ...current,
                              source_urls: current.source_urls.map((item, itemIndex) =>
                                 itemIndex === index ? event.target.value : item,
                              ),
                           }));
                           setFieldErrors((current) => ({ ...current, source_urls: undefined }));
                        }}
                     />
                     <Button
                        type="button"
                        variant="ghost"
                        density="compact"
                        aria-label={`Remove source URL ${index + 1}`}
                        disabled={!canEditProposal || Boolean(mutation) || editor.source_urls.length === 1}
                        onClick={() =>
                           setEditor((current) => ({
                              ...current,
                              source_urls: current.source_urls.filter((_, itemIndex) => itemIndex !== index),
                           }))
                        }
                     >
                        Remove
                     </Button>
                  </div>
               ))}
               {fieldError(fieldErrors, "source_urls") ? (
                  <span id="correction-source-error" className="correction-field-error">
                     {fieldError(fieldErrors, "source_urls")}
                  </span>
               ) : null}
               <Button
                  type="button"
                  variant="secondary"
                  density="compact"
                  disabled={!canEditProposal || Boolean(mutation)}
                  onClick={() => setEditor((current) => ({ ...current, source_urls: [...current.source_urls, ""] }))}
               >
                  Add source
               </Button>
            </fieldset>
            <div className="correction-field correction-field--wide">
               <label htmlFor={showVerificationRunSelect ? "correction-verification-run" : undefined}>
                  Supporting verification run <span>(optional)</span>
               </label>

               {eligibleVerificationRuns === null ? (
                  <span className="correction-field-help">Supporting verification run choices are unavailable.</span>
               ) : eligibleVerificationRuns.length === 0 && !selectedVerificationRunId ? (
                  <span className="correction-field-help">
                     No completed verification runs are available for this claim.
                  </span>
               ) : (
                  <Select
                     ref={proposalRefs.verification_run_id}
                     id="correction-verification-run"
                     value={editor.verification_run_id}
                     disabled={!canEditProposal || Boolean(mutation)}
                     invalid={Boolean(fieldError(fieldErrors, "verification_run_id"))}
                     aria-describedby="correction-verification-run-help"
                     onChange={(event) => updateEditor("verification_run_id", event.target.value)}
                  >
                     <option value="">No supporting verification run</option>
                     {hasUnresolvedLinkedVerificationRun ? (
                        <option value={editor.verification_run_id} disabled>
                           Linked verification run metadata unavailable
                        </option>
                     ) : null}
                     {eligibleVerificationRuns.map((run) => (
                        <option key={run.id} value={run.id}>
                           {verificationRunLabel(run)}
                        </option>
                     ))}
                  </Select>
               )}

               <span
                  id="correction-verification-run-help"
                  className={
                     fieldError(fieldErrors, "verification_run_id")
                        ? "correction-field-error"
                        : "correction-field-help"
                  }
               >
                  {fieldError(fieldErrors, "verification_run_id") ||
                     "Optional AI-assisted verification provenance. It does not determine or replace the human factual decision."}
               </span>
            </div>
         </div>
         <div className="correction-editor-footer">
            <span
               className={isDirty ? "correction-dirty-indicator is-dirty" : "correction-dirty-indicator"}
               role="status"
            >
               {isDirty ? "Unsaved proposal changes" : "Proposal matches the saved server version"}
            </span>
            <div className="correction-action-row">
               {allowedActions.includes("SAVE_CORRECTION_PROPOSAL") ? (
                  <Button
                     type="submit"
                     variant="primary"
                     loading={mutation === "save-proposal"}
                     loadingLabel="Saving proposal…"
                     disabled={!isDirty || Boolean(mutation)}
                  >
                     Save proposal
                  </Button>
               ) : null}
            </div>
         </div>
         {allowedActions.includes("PREPARE_CORRECTION_PROPOSAL") && isDirty ? (
            <p className="correction-action-note">Save the current changes before preparing the proposal.</p>
         ) : null}
      </form>
   );

   const renderProposalSection = ({ preserved = false } = {}) => (
      <section
         className="correction-section"
         aria-labelledby={preserved ? "correction-preserved-proposal-heading" : "correction-proposal-heading"}
      >
         <div className="correction-section-heading">
            <div>
               <h4 id={preserved ? "correction-preserved-proposal-heading" : "correction-proposal-heading"}>
                  {preserved ? "Preserved correction proposal" : "Factual correction proposal"}
               </h4>
               <p>
                  {preserved
                     ? "Terminal requests retain their proposal history for accountable inspection."
                     : "The proposal is working material. Human adjudication and final institutional publication remain separate authority."}
               </p>
            </div>
            {detail.proposal ? <Badge tone="info">Proposal v{detail.proposal.version}</Badge> : null}
         </div>
         {conflict && detail.proposal ? (
            <div className="correction-canonical-proposal">
               <h5>Current saved server proposal after conflict</h5>
               <p>Compare this canonical version with the preserved local editor before explicitly submitting again.</p>
               <ProposalSummary
                  proposal={detail.proposal}
                  eligibleVerificationRuns={eligibleVerificationRuns}
               />
            </div>
         ) : null}
         {canEditProposal ? (
            renderProposalEditor()
         ) : (
            <ProposalSummary
               proposal={detail.proposal}
               eligibleVerificationRuns={eligibleVerificationRuns}
            />
         )}
      </section>
   );

   const renderStageWork = () => {
      if (detail.stage === "EVIDENCE_REVIEW") {
         return (
            <>
               {renderEvidence()}
               {detail.proposal || canEditProposal ? renderProposalSection() : null}
            </>
         );
      }
      if (detail.stage === "PROPOSAL_DRAFT") {
         return (
            <>
               {renderProposalSection()}
               {renderEvidence()}
            </>
         );
      }
      if (detail.stage === "PREPARED") {
         return (
            <>
               <section
                  className="correction-section correction-prepared"
                  aria-labelledby="correction-prepared-heading"
               >
                  <div className="correction-prepared-banner" role="status">
                     <Icons name="lock" size={20} />
                     <div>
                        <h4 id="correction-prepared-heading">
                           Prepared for publication — not yet published or authoritative.
                        </h4>
                        <p>
                           The proposal is frozen. Only successful final publication creates the new current decision
                           and article authority.
                        </p>
                     </div>
                  </div>
               </section>
               {renderProposalSection()}
            </>
         );
      }
      if (detail.stage === "COMPLETED") {
         const publication = publishedPublication || detail.completed_publication;
         const publicationArticle = publication?.article || publication;
         const publicationTime = publication?.published_at || publicationArticle?.published_at;
         return (
            <section
               className="correction-section correction-terminal correction-terminal--completed"
               aria-labelledby="correction-completed-heading"
            >
               <div className="correction-terminal-heading">
                  <Icons name="check-circle" size={22} />
                  <div>
                     <h4 id="correction-completed-heading">Factual correction completed</h4>
                     <p>
                        {completedHasReplacementDecision
                           ? "Final publication succeeded. The returned replacement human decision and institutional article are now current authority."
                           : "Final publication succeeded, but this response does not distinguish a replacement human decision. The authority comparison below remains neutral."}
                     </p>
                  </div>
               </div>
               {publication ? (
                  <div className="correction-completed-publication">
                     <div>
                        <strong>{publicationArticle?.headline || "Completed factual correction"}</strong>
                        <span>
                           Article v{publicationArticle?.version ?? "–"} · {formatDateTime(publicationTime)}
                        </span>
                     </div>
                     <Button type="button" variant="secondary" onClick={() => onOpenPublication?.(publication)}>
                        Open completed publication
                     </Button>
                  </div>
               ) : (
                  <p className="correction-inline-empty">
                     The completed publication record is not available in this response.
                  </p>
               )}
            </section>
         );
      }
      return (
         <section
            className="correction-section correction-terminal correction-terminal--cancelled"
            aria-labelledby="correction-cancelled-heading"
         >
            <div className="correction-terminal-heading">
               <Icons name="alert-circle" size={22} />
               <div>
                  <h4 id="correction-cancelled-heading">Factual correction cancelled</h4>
                  <p>
                     This request is terminal and read-only. Cancellation created no replacement factual authority; the
                     existing human decision remains current. Historical evidence and proposal material remain
                     inspectable below.
                  </p>
               </div>
            </div>
         </section>
      );
   };

   return (
      <div className="correction-panel">
         <div className="correction-authority-note">
            <Icons name="shield" size={19} />
            <p>
               <strong>Accountable authority stays explicit.</strong> AI may assist analysis, but human adjudication
               owns factual judgment and institutional publication owns the published article version.
            </p>
         </div>

         <div ref={messageRef} className="correction-messages" tabIndex={-1} aria-live="polite">
            {authorityError ? (
               <div className="correction-message correction-message--critical" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <div>
                     <strong>Permission changed</strong>
                     <p>{authorityError}</p>
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        onClick={() => {
                           authorityGenerationRef.current += 1;
                           setAuthorityError("");
                           setQueueRequestVersion((value) => value + 1);
                           if (requestId) setDetailRequestVersion((value) => value + 1);
                        }}
                     >
                        Retry access
                     </Button>
                  </div>
               </div>
            ) : null}
            {notice ? (
               <div className="correction-message correction-message--success" role="status">
                  <Icons name="check-circle" size={18} />
                  <div>
                     <strong>Correction workspace updated</strong>
                     <p>{notice}</p>
                  </div>
               </div>
            ) : null}
            {actionError ? (
               <div className="correction-message correction-message--critical" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <div>
                     <strong>Action not completed</strong>
                     <p>{actionError}</p>
                  </div>
               </div>
            ) : null}
            {conflict ? (
               <div className="correction-message correction-message--warning" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <div>
                     <strong>{conflict.code}</strong>
                     <p>
                        {conflict.detail} Canonical server state has been reloaded; no mutation was repeated. Reconcile
                        your preserved proposal text before submitting again.
                     </p>
                     {Array.isArray(conflict.blockers) && conflict.blockers.length > 0 ? (
                        <ul className="correction-server-errors">
                           {conflict.blockers.map((blocker, index) => (
                              <li key={`${blocker?.code || "blocker"}-${index}`}>
                                 <strong>{formatLabel(blocker?.code, "Conflict blocker")}</strong>
                                 {blocker?.detail || "The server rejected this state transition."}
                              </li>
                           ))}
                        </ul>
                     ) : null}
                     {conflict.current ? <pre>{JSON.stringify(conflict.current, null, 2)}</pre> : null}
                     {isDirty ? (
                        <details className="correction-local-snapshot">
                           <summary>View preserved local proposal text</summary>
                           <pre>{JSON.stringify(editor, null, 2)}</pre>
                        </details>
                     ) : null}
                  </div>
               </div>
            ) : null}
            {Object.entries(fieldErrors).some(([, value]) => Boolean(value)) ? (
               <div className="correction-message correction-message--critical" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <div>
                     <strong>Validation details</strong>
                     <ul className="correction-server-errors">
                        {Object.entries(fieldErrors)
                           .filter(([, value]) => Boolean(value))
                           .map(([name, value]) => (
                              <li key={name}>
                                 <strong>{formatLabel(name)}</strong>
                                 {Array.isArray(value) ? value.join(" ") : String(value)}
                              </li>
                           ))}
                     </ul>
                  </div>
               </div>
            ) : null}
         </div>

         <div className={`correction-workbench ${requestId ? "has-selection" : ""}`}>
            <section
               className="correction-queue"
               aria-labelledby="correction-queue-heading"
               aria-busy={queueLoading || queueRefreshing || undefined}
            >
               <div className="correction-queue-heading">
                  <div>
                     <h3 id="correction-queue-heading" ref={queueHeadingRef} tabIndex={-1}>
                        Correction requests
                     </h3>
                     <p>{organizationName || "Selected organization"} · server-scoped work</p>
                  </div>
                  <Button
                     type="button"
                     variant="ghost"
                     density="compact"
                     leadingIcon={<Icons name="refresh-cw" size={15} />}
                     loading={queueRefreshing}
                     loadingLabel="Refreshing…"
                     disabled={queueLoading || Boolean(mutation)}
                     onClick={refreshQueue}
                  >
                     Refresh
                  </Button>
               </div>
               <div className="correction-status-filter">
                  <label htmlFor="correction-status">Request status</label>
                  <Select
                     id="correction-status"
                     value={normalizedStatus}
                     disabled={queueLoading || queueRefreshing || Boolean(mutation)}
                     onChange={(event) =>
                        requestDiscard(() => onNavigate({ requestId: null, status: event.target.value, offset: 0 }))
                     }
                  >
                     {COLLECTION_STATUSES.map((value) => (
                        <option key={value} value={value}>
                           {formatLabel(value)}
                        </option>
                     ))}
                  </Select>
               </div>
               {queueLoading && !hasLoadedQueueRef.current ? (
                  <div className="correction-state" role="status">
                     <Icons name="loader" size={22} className="correction-spinner" />
                     <strong>Loading correction requests…</strong>
                  </div>
               ) : queueError && queue.results.length === 0 ? (
                  <div className="correction-state correction-state--error" role="alert">
                     <Icons name="alert-circle" size={22} />
                     <strong>Unable to load corrections</strong>
                     <p>{queueError}</p>
                     <Button type="button" variant="secondary" density="compact" onClick={refreshQueue}>
                        Try again
                     </Button>
                  </div>
               ) : queue.results.length === 0 ? (
                  <div className="correction-state">
                     <Icons name="file-text" size={23} />
                     <strong>
                        No {normalizedStatus === "ALL" ? "" : formatLabel(normalizedStatus).toLowerCase()} correction
                        requests
                     </strong>
                     <p>Requests matching this server status will appear here.</p>
                  </div>
               ) : (
                  <>
                     {queueError ? (
                        <div className="correction-queue-warning" role="alert">
                           {queueError} Existing results remain available.
                        </div>
                     ) : null}
                     <ul className="correction-queue-list">
                        {queue.results.map((item) => {
                           const selected = String(item.request_id) === String(requestId);
                           const actions = Array.isArray(item.allowed_actions) ? item.allowed_actions : [];
                           return (
                              <li key={item.request_id}>
                                 <button
                                    type="button"
                                    className={`correction-queue-row ${selected ? "is-selected" : ""}`}
                                    aria-current={selected ? "true" : undefined}
                                    disabled={Boolean(mutation)}
                                    onClick={() => selectRequest(item.request_id)}
                                 >
                                    <span className="correction-queue-top">
                                       <StatusBadge value={item.request_status} />
                                       <StageBadge stage={item.stage} />
                                    </span>
                                    <strong className="correction-queue-reason">{item.correction_reason}</strong>
                                    <span className="correction-queue-claim">
                                       {item.claim?.context_text ||
                                          item.predecessor_decision?.canonical_claim ||
                                          "Claim context unavailable"}
                                    </span>
                                    <span>
                                       Article v{item.predecessor_publication?.version ?? "–"} · predecessor verdict{" "}
                                       {formatLabel(item.predecessor_decision?.verdict)}
                                    </span>
                                    <span>
                                       Requested by {actorName(item.requested_by)} · {formatDateTime(item.requested_at)}
                                    </span>
                                    <span className="correction-queue-actions">
                                       {actions.length > 0
                                          ? actions
                                               .map((action) => ACTION_LABELS[action] || formatLabel(action))
                                               .join(" · ")
                                          : "Read-only inspection"}
                                    </span>
                                 </button>
                              </li>
                           );
                        })}
                     </ul>
                  </>
               )}
               {!queueLoading && queue.count > 0 ? (
                  <div className="correction-pagination" aria-label="Correction request pagination">
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        disabled={!hasPrevious || queueRefreshing || Boolean(mutation)}
                        onClick={() =>
                           requestDiscard(() =>
                              onNavigate({
                                 requestId: null,
                                 status: normalizedStatus,
                                 offset: Math.max(0, offset - PAGE_SIZE),
                              }),
                           )
                        }
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
                        disabled={!hasNext || queueRefreshing || Boolean(mutation)}
                        onClick={() =>
                           requestDiscard(() =>
                              onNavigate({ requestId: null, status: normalizedStatus, offset: offset + PAGE_SIZE }),
                           )
                        }
                     >
                        Next
                     </Button>
                  </div>
               ) : null}
            </section>

            <section
               className="correction-detail"
               aria-labelledby="correction-detail-heading"
               aria-busy={detailLoading || Boolean(mutation) || undefined}
            >
               {!requestId ? (
                  <div className="correction-state correction-state--detail">
                     <Icons name="file-text" size={25} />
                     <h3 id="correction-detail-heading">Select a factual correction</h3>
                     <p>
                        Open a request to inspect its server-defined stage, human judgment, correction evidence,
                        proposal, and provenance.
                     </p>
                  </div>
               ) : (
                  <>
                     <Button
                        type="button"
                        variant="ghost"
                        density="compact"
                        className="correction-back"
                        leadingIcon={<Icons name="arrow-left" size={15} />}
                        disabled={Boolean(mutation)}
                        onClick={returnToQueue}
                     >
                        Back to corrections
                     </Button>
                     {detailLoading && !detail ? (
                        <div className="correction-state" role="status">
                           <Icons name="loader" size={22} className="correction-spinner" />
                           <strong>Loading factual correction…</strong>
                        </div>
                     ) : detailError && !detail ? (
                        <div className="correction-state correction-state--error" role="alert">
                           <Icons name="alert-circle" size={22} />
                           <h3 id="correction-detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                              Correction unavailable
                           </h3>
                           <p>{detailError}</p>
                           <div className="correction-action-row">
                              <Button type="button" variant="secondary" onClick={() => refreshDetail(isDirty)}>
                                 Try again
                              </Button>
                              <Button type="button" variant="ghost" onClick={returnToQueue}>
                                 Return to queue
                              </Button>
                           </div>
                        </div>
                     ) : detail ? (
                        <article className="correction-detail-content">
                           <header className="correction-detail-header">
                              <div>
                                 <div className="correction-detail-badges">
                                    <StatusBadge value={detail.request?.status} />
                                    <StageBadge stage={detail.stage} />
                                 </div>
                                 <h3 id="correction-detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                                    {detail.request?.correction_reason || "Factual correction request"}
                                 </h3>
                                 <p>
                                    Requested by {actorName(detail.request?.requested_by)} ·{" "}
                                    {formatDateTime(detail.request?.requested_at)}
                                 </p>
                              </div>
                              <Button
                                 type="button"
                                 variant="ghost"
                                 density="compact"
                                 leadingIcon={<Icons name="refresh-cw" size={15} />}
                                 loading={detailLoading}
                                 loadingLabel="Refreshing…"
                                 disabled={Boolean(mutation) || isDirty}
                                 onClick={() => refreshDetail(false)}
                              >
                                 Refresh
                              </Button>
                           </header>

                           <section className="correction-section" aria-labelledby="correction-context-heading">
                              <div className="correction-section-heading">
                                 <div>
                                    <h4 id="correction-context-heading">Claim and predecessor publication</h4>
                                    <p>
                                       {detail.stage === "COMPLETED"
                                          ? "This article is the historical predecessor to the completed factual correction publication."
                                          : detail.stage === "CANCELLED"
                                            ? "Cancellation left the existing factual decision and publication authority unchanged."
                                            : "The current published article remains authoritative until final correction publication succeeds."}
                                    </p>
                                 </div>
                              </div>
                              <dl className="correction-metadata-grid">
                                 <div className="correction-metadata-wide">
                                    <dt>Claim context</dt>
                                    <dd>{detail.claim?.context_text || "Not recorded"}</dd>
                                 </div>
                                 <div>
                                    <dt>Predecessor article</dt>
                                    <dd>Article v{detail.predecessor_publication?.version ?? "–"}</dd>
                                 </div>
                                 <div>
                                    <dt>Headline</dt>
                                    <dd>{detail.predecessor_publication?.headline || "Untitled publication"}</dd>
                                 </div>
                                 <div>
                                    <dt>Publication status</dt>
                                    <dd>{formatLabel(detail.predecessor_publication?.publication_status)}</dd>
                                 </div>
                                 <div>
                                    <dt>Published at</dt>
                                    <dd>{formatDateTime(detail.predecessor_publication?.published_at)}</dd>
                                 </div>
                              </dl>
                              <div className="correction-context-links">
                                 {[
                                    ["Open claim URL", detail.claim?.url_link],
                                    ["Open claim source", detail.claim?.source_link],
                                    ["Open claim media", detail.claim?.media_url],
                                 ]
                                    .filter(
                                       ([, value], index, values) =>
                                          value && values.findIndex(([, candidate]) => candidate === value) === index,
                                    )
                                    .map(([label, value]) => {
                                       const externalUrl = safeExternalUrl(value);
                                       return externalUrl ? (
                                          <a key={value} href={externalUrl} target="_blank" rel="noopener noreferrer">
                                             {label} <Icons name="external-link" size={14} />
                                          </a>
                                       ) : null;
                                    })}
                              </div>
                           </section>

                           <section className="correction-section" aria-labelledby="correction-authority-heading">
                              <div className="correction-section-heading">
                                 <div>
                                    <h4 id="correction-authority-heading">Human factual authority</h4>
                                    <p>
                                       {detail.stage === "COMPLETED"
                                          ? completedHasReplacementDecision
                                             ? "Human adjudication owns factual judgment. The completed publication handoff created the distinct current decision shown here."
                                             : "Human adjudication owns factual judgment. This completed response does not safely distinguish a replacement decision, so no new authority is asserted below."
                                          : detail.stage === "CANCELLED"
                                            ? "Cancellation created no replacement factual authority. The predecessor decision remains the current human judgment."
                                            : "The predecessor decision remains the current factual authority. No replacement human decision has been created; proposal content is non-authoritative."}
                                    </p>
                                 </div>
                              </div>
                              {detail.stage === "COMPLETED" ? (
                                 <div className="correction-decision-grid">
                                    <DecisionCard
                                       title="Historical predecessor human decision"
                                       decision={detail.predecessor_decision}
                                    />
                                    <DecisionCard
                                       title={
                                          completedHasReplacementDecision
                                             ? "New current human decision"
                                             : "Reported current human decision"
                                       }
                                       decision={detail.current_decision}
                                       current={completedHasReplacementDecision}
                                       emptyMessage="No meaningful current human decision was returned. Replacement factual authority cannot be confirmed from this response."
                                    />
                                 </div>
                              ) : (
                                 <div className="correction-decision-grid">
                                    <DecisionCard
                                       title={
                                          detail.stage === "CANCELLED"
                                             ? "Current human decision (unchanged)"
                                             : "Current human decision (predecessor)"
                                       }
                                       decision={detail.predecessor_decision || detail.current_decision}
                                       emptyMessage="No current human decision is available in this response; no replacement factual authority is asserted."
                                    />
                                 </div>
                              )}
                           </section>

                           {renderStageWork()}

                           <section className="correction-section" aria-labelledby="correction-actions-heading">
                              <div className="correction-section-heading">
                                 <div>
                                    <h4 id="correction-actions-heading">Available server actions and blockers</h4>
                                    <p>
                                       Action availability and lifecycle conditions are supplied by the correction
                                       service.
                                    </p>
                                 </div>
                              </div>
                              <div className="correction-action-row">
                                 {allowedActions.includes("PREPARE_CORRECTION_PROPOSAL") ? (
                                    <Button
                                       type="button"
                                       variant="secondary"
                                       disabled={isDirty || Boolean(mutation)}
                                       onClick={prepareProposal}
                                    >
                                       Prepare correction proposal
                                    </Button>
                                 ) : null}
                                 {allowedActions.includes("PUBLISH_FACTUAL_CORRECTION") ? (
                                    <Button
                                       type="button"
                                       variant="primary"
                                       disabled={Boolean(mutation)}
                                       onClick={() => setDialog({ type: "publish" })}
                                    >
                                       Publish factual correction
                                    </Button>
                                 ) : null}
                                 {allowedActions.includes("CANCEL_FACTUAL_CORRECTION") ? (
                                    <Button
                                       type="button"
                                       variant="destructive"
                                       disabled={Boolean(mutation)}
                                       onClick={() => {
                                          setFieldErrors((current) => ({ ...current, cancellation_reason: undefined }));
                                          setDialog({ type: "cancel" });
                                       }}
                                    >
                                       Cancel factual correction
                                    </Button>
                                 ) : null}
                              </div>
                              {allowedActions.length === 0 ? (
                                 <p className="correction-inline-empty">
                                    This correction is currently available for read-only inspection.
                                 </p>
                              ) : null}
                              <Blockers blockers={detail.blockers} />
                           </section>

                           {detail.stage !== "EVIDENCE_REVIEW" && detail.stage !== "PROPOSAL_DRAFT"
                              ? renderEvidence()
                              : null}
                           {detail.stage === "COMPLETED" || detail.stage === "CANCELLED"
                              ? renderProposalSection({ preserved: true })
                              : null}

                           <section className="correction-section" aria-labelledby="correction-provenance-heading">
                              <div className="correction-section-heading">
                                 <div>
                                    <h4 id="correction-provenance-heading">Correction and publication provenance</h4>
                                    <p>
                                       Request, case, proposal, and sealed predecessor evidence remain distinct
                                       historical records.
                                    </p>
                                 </div>
                              </div>
                              <dl className="correction-metadata-grid">
                                 <div>
                                    <dt>Request ID</dt>
                                    <dd>{detail.request?.id}</dd>
                                 </div>
                                 <div>
                                    <dt>Request updated</dt>
                                    <dd>{formatDateTime(detail.request?.updated_at)}</dd>
                                 </div>
                                 <div>
                                    <dt>Correction case</dt>
                                    <dd>{detail.correction_case?.id}</dd>
                                 </div>
                                 <div>
                                    <dt>Case status</dt>
                                    <dd>{formatLabel(detail.correction_case?.status)}</dd>
                                 </div>
                                 <div>
                                    <dt>Case priority</dt>
                                    <dd>{formatLabel(detail.correction_case?.priority)}</dd>
                                 </div>
                                 <div>
                                    <dt>Resolved by</dt>
                                    <dd>{actorName(detail.correction_case?.resolved_by)}</dd>
                                 </div>
                                 <div>
                                    <dt>Resolution</dt>
                                    <dd>{formatLabel(detail.correction_case?.resolution_code, "Not resolved")}</dd>
                                 </div>
                                 <div className="correction-metadata-wide">
                                    <dt>Resolution summary</dt>
                                    <dd>{detail.correction_case?.resolution_summary || "Not recorded"}</dd>
                                 </div>
                              </dl>
                              <div className="correction-sealed-evidence">
                                 <strong>Sealed predecessor evidence</strong>
                                 <p>
                                    This immutable snapshot is historical factual provenance for the predecessor human
                                    decision.
                                 </p>
                                 <dl className="correction-metadata-grid">
                                    <div>
                                       <dt>Basis</dt>
                                       <dd>{formatLabel(detail.sealed_predecessor_evidence?.basis)}</dd>
                                    </div>
                                    <div>
                                       <dt>Captured</dt>
                                       <dd>{formatDateTime(detail.sealed_predecessor_evidence?.captured_at)}</dd>
                                    </div>
                                    <div>
                                       <dt>Records</dt>
                                       <dd>{detail.sealed_predecessor_evidence?.count ?? 0}</dd>
                                    </div>
                                    <div>
                                       <dt>Schema</dt>
                                       <dd>{detail.sealed_predecessor_evidence?.schema_version ?? "Not recorded"}</dd>
                                    </div>
                                 </dl>
                                 {Array.isArray(detail.sealed_predecessor_evidence?.entries) &&
                                 detail.sealed_predecessor_evidence.entries.length > 0 ? (
                                    <ol className="correction-evidence-list correction-sealed-list">
                                       {detail.sealed_predecessor_evidence.entries.map((entry, index) => {
                                          const externalUrl = safeExternalUrl(entry?.evidence_url);
                                          return (
                                             <li key={entry?.id || index}>
                                                <div className="correction-evidence-title">
                                                   <div>
                                                      <strong>
                                                         {entry?.evidence_caption || `Sealed evidence ${index + 1}`}
                                                      </strong>
                                                      <span>{formatLabel(entry?.evidence_type)}</span>
                                                   </div>
                                                   <Badge tone="neutral">{formatLabel(entry?.evidence_status)}</Badge>
                                                </div>
                                                <p>
                                                   Submitted {formatDateTime(entry?.submitted_at)} · reviewed{" "}
                                                   {formatDateTime(entry?.reviewed_at)}
                                                </p>
                                                {entry?.moderator_notes ? <p>{entry.moderator_notes}</p> : null}
                                                {entry?.rejection_reason ? (
                                                   <p>Rejection reason: {formatLabel(entry.rejection_reason)}</p>
                                                ) : null}
                                                {externalUrl ? (
                                                   <a
                                                      className="correction-external-link"
                                                      href={externalUrl}
                                                      target="_blank"
                                                      rel="noopener noreferrer"
                                                   >
                                                      Open captured source <Icons name="external-link" size={14} />
                                                   </a>
                                                ) : null}
                                             </li>
                                          );
                                       })}
                                    </ol>
                                 ) : null}
                              </div>
                           </section>
                        </article>
                     ) : null}
                  </>
               )}
            </section>
         </div>

         <CorrectionDialog
            open={dialog?.type === "discard"}
            title="Discard unsaved proposal changes?"
            description="Your saved server proposal will remain, but the unsaved text in this editor will be lost."
            confirmLabel="Discard changes"
            confirmVariant="destructive"
            onClose={() => setDialog(null)}
            onConfirm={() => {
               const continuation = dialog?.continuation;
               discardDirtyDraft();
               setDialog(null);
               continuation?.();
            }}
         >
            {" "}
         </CorrectionDialog>
         <CorrectionDialog
            open={dialog?.type === "prepare"}
            title="Prepare and freeze this proposal?"
            description="Preparation makes the proposal immutable and ready for final publication handoff. It does not publish the correction or make it factual authority."
            confirmLabel="Prepare proposal"
            cancelLabel="Return to proposal"
            processing={mutation === "prepare-proposal"}
            onClose={() => !mutation && setDialog(null)}
            onConfirm={confirmPrepare}
         >
            {" "}
         </CorrectionDialog>
         <CorrectionDialog
            open={dialog?.type === "publish"}
            title="Publish this factual correction?"
            description="This atomic action creates a new current human decision and institutional publication version. Review the frozen proposal before continuing."
            confirmLabel="Publish factual correction"
            cancelLabel="Return to review"
            processing={mutation === "publish-correction"}
            onClose={() => !mutation && setDialog(null)}
            onConfirm={confirmPublish}
         >
            {" "}
         </CorrectionDialog>
         <CorrectionDialog
            open={dialog?.type === "cancel"}
            title="Cancel this factual correction?"
            description="Cancellation is terminal. The request, correction evidence, and proposal remain available as historical provenance."
            confirmLabel="Cancel factual correction"
            cancelLabel="Keep request"
            confirmVariant="destructive"
            processing={mutation === "cancel-correction"}
            onClose={() => !mutation && setDialog(null)}
            onConfirm={confirmCancel}
         >
            <div className="correction-field">
               <label htmlFor="correction-cancellation-reason">Cancellation reason</label>
               <Textarea
                  ref={proposalRefs.cancellation_reason}
                  id="correction-cancellation-reason"
                  rows={4}
                  maxLength={2000}
                  required
                  value={cancellationReason}
                  disabled={Boolean(mutation)}
                  invalid={Boolean(fieldError(fieldErrors, "cancellation_reason"))}
                  aria-describedby="correction-cancellation-help"
                  onChange={(event) => {
                     setCancellationReason(event.target.value);
                     setFieldErrors((current) => ({ ...current, cancellation_reason: undefined }));
                  }}
               />
               <span
                  id="correction-cancellation-help"
                  className={
                     fieldError(fieldErrors, "cancellation_reason") ? "correction-field-error" : "correction-field-help"
                  }
               >
                  {fieldError(fieldErrors, "cancellation_reason") || `${cancellationReason.length}/2000`}
               </span>
            </div>
         </CorrectionDialog>
      </div>
   );
}

function FactualCorrectionPanel(props) {
   const { authFetch, token, user } = useAuth();
   const authIdentity = getAuthSessionIdentity(user, token);
   return (
      <FactualCorrectionContent
         key={`${props.organizationId}:${authIdentity}`}
         {...props}
         authFetch={authFetch}
         authIdentity={authIdentity}
      />
   );
}

export default FactualCorrectionPanel;
