import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";
import Input from "../ui/Input.jsx";
import Textarea from "../ui/Textarea.jsx";

import "./DraftingPanel.css";

const PAGE_SIZE = 20;
const EMPTY_EDITOR = {
   headline: "",
   summary: "",
   articleBody: "",
   sourceUrls: "",
};

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

function getAuthIdentity(user, token) {
   if (!token) {
      return "session:anonymous";
   }

   try {
      const encodedPayload = token.split(".")[1];
      const normalizedPayload = encodedPayload.replaceAll("-", "+").replaceAll("_", "/");
      const paddedPayload = normalizedPayload.padEnd(Math.ceil(normalizedPayload.length / 4) * 4, "=");
      const payload = JSON.parse(window.atob(paddedPayload));
      const userId = payload?.user_id ?? payload?.sub;

      if (userId !== undefined && userId !== null) {
         return `user:${userId}`;
      }
   } catch {
      // Fall through to the authenticated user or opaque-token identity.
   }

   if (user?.id !== undefined && user?.id !== null) {
      return `user:${user.id}:token:${token}`;
   }

   return `token:${token}`;
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

function parseSourceUrls(value) {
   const urls = [];
   const invalid = [];
   const seen = new Set();

   String(value || "")
      .split(/\r?\n/)
      .map((entry) => entry.trim())
      .filter(Boolean)
      .forEach((entry) => {
         let parsed;

         try {
            parsed = new URL(entry);
         } catch {
            invalid.push(entry);
            return;
         }

         if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
            invalid.push(entry);
            return;
         }

         if (!seen.has(entry)) {
            seen.add(entry);
            urls.push(entry);
         }
      });

   return { urls, invalid };
}

function detailToEditor(detail) {
   const sourceUrls = Array.isArray(detail?.source_items)
      ? detail.source_items
           .filter((source) => source?.is_editorially_selected === true)
           .map((source) => source.url)
           .filter(Boolean)
           .join("\n")
      : "";

   return {
      headline: detail?.headline ?? detail?.article?.headline ?? "",
      summary: detail?.summary ?? detail?.article?.summary ?? "",
      articleBody: detail?.article_body ?? detail?.article?.article_body ?? "",
      sourceUrls,
   };
}

function selectionKey(resourceType, resourceId) {
   return resourceType && resourceId ? `${resourceType}:${resourceId}` : "";
}

function getEditGeneration(detail) {
   return detail?.concurrency?.edit_generation ?? detail?.edit_generation ?? null;
}

function getItemState(item) {
   if (item?.resource_type === "ELIGIBLE_CLAIM") {
      return "Ready to draft";
   }

   if (item?.article?.publication_status === "IN_REVIEW") {
      return "In review";
   }

   return "Draft";
}

function getClaimText(item) {
   return item?.decision?.canonical_claim || item?.claim?.context_text || "Claim context unavailable";
}

function VerdictBadge({ verdict }) {
   const normalized = String(verdict || "").toUpperCase();
   const tone = VERDICT_CLASSES[normalized] || "neutral";

   return <span className={`drafting-verdict drafting-verdict--${tone}`}>{formatLabel(verdict)}</span>;
}

function BlockerList({ blockers }) {
   if (!Array.isArray(blockers) || blockers.length === 0) {
      return null;
   }

   return (
      <section className="drafting-blockers" aria-labelledby="drafting-blockers-heading">
         <div className="drafting-section-heading">
            <div>
               <h4 id="drafting-blockers-heading">Current blockers</h4>
               <p>These readiness conditions come directly from the publication workflow.</p>
            </div>
         </div>

         <ul>
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
      </section>
   );
}

function HumanAdjudication({ detail }) {
   const decision = detail?.decision || {};

   return (
      <section className="drafting-provenance-section" aria-labelledby="drafting-adjudication-heading">
         <div className="drafting-section-heading">
            <div>
               <h4 id="drafting-adjudication-heading">Human adjudication</h4>
               <p>Authoritative, read-only factual judgment. These are not editable article fields.</p>
            </div>
            <VerdictBadge verdict={decision.verdict || detail?.verdict} />
         </div>

         <dl className="drafting-metadata-grid">
            <div className="drafting-metadata-wide">
               <dt>Canonical claim</dt>
               <dd>{decision.canonical_claim || detail?.canonical_claim || "Not recorded"}</dd>
            </div>
            <div className="drafting-metadata-wide">
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

function SealedEvidence({ sealedEvidence }) {
   const entries = Array.isArray(sealedEvidence?.entries) ? sealedEvidence.entries : [];

   return (
      <section className="drafting-provenance-section" aria-labelledby="drafting-sealed-evidence-heading">
         <div className="drafting-section-heading">
            <div>
               <h4 id="drafting-sealed-evidence-heading">Decision-time evidence</h4>
               <p>Immutable provenance captured for the human adjudication decision.</p>
            </div>
            <span className="drafting-count-label">{sealedEvidence?.count ?? entries.length} records</span>
         </div>

         {!sealedEvidence ? (
            <p className="drafting-inline-empty">No valid sealed evidence snapshot is available.</p>
         ) : entries.length === 0 ? (
            <p className="drafting-inline-empty">The sealed decision snapshot contains no evidence records.</p>
         ) : (
            <ol className="drafting-evidence-list">
               {entries.map((entry, index) => {
                  const externalUrl = safeExternalUrl(entry?.evidence_url);

                  return (
                     <li key={entry?.id || index}>
                        <div className="drafting-evidence-heading">
                           <strong>{entry?.evidence_caption || `Evidence record ${index + 1}`}</strong>
                           <span>{formatLabel(entry?.evidence_status)}</span>
                        </div>
                        <p>{formatLabel(entry?.evidence_type, "Evidence type not recorded")}</p>
                        <dl className="drafting-compact-metadata">
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
                           <p className="drafting-evidence-note">
                              <strong>Review notes:</strong> {entry.moderator_notes}
                           </p>
                        ) : null}
                        {entry?.rejection_reason ? (
                           <p className="drafting-evidence-note">
                              <strong>Rejection reason:</strong> {entry.rejection_reason}
                           </p>
                        ) : null}
                        {externalUrl ? (
                           <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                              Open captured source <Icons name="external-link" size={14} />
                           </a>
                        ) : entry?.evidence_url ? (
                           <span className="drafting-invalid-url">Captured URL is not a safe http/https link.</span>
                        ) : null}
                     </li>
                  );
               })}
            </ol>
         )}

         {sealedEvidence ? (
            <p className="drafting-snapshot-note">
               Snapshot {String(sealedEvidence.decision_snapshot_id || "unavailable").slice(0, 8)} · Schema version{" "}
               {sealedEvidence.schema_version ?? "unavailable"} · Captured{" "}
               <FormattedDateTime value={sealedEvidence.captured_at} />
            </p>
         ) : null}
      </section>
   );
}

function PublicationSources({ sourceItems }) {
   const sources = Array.isArray(sourceItems) ? sourceItems : [];

   return (
      <section className="drafting-provenance-section" aria-labelledby="drafting-publication-sources-heading">
         <div className="drafting-section-heading">
            <div>
               <h4 id="drafting-publication-sources-heading">Publication sources</h4>
               <p>
                  Publication sources show where each source entered the publication record. Citing a source in the
                  article does not change the sealed decision evidence.
               </p>
            </div>
            <span className="drafting-count-label">{sources.length} sources</span>
         </div>

         {sources.length === 0 ? (
            <p className="drafting-inline-empty">No publication sources are currently attached.</p>
         ) : (
            <ul className="drafting-source-list">
               {sources.map((source, index) => {
                  const externalUrl = safeExternalUrl(source?.url);
                  const isDecisionEvidence = source?.source_origin === "DECISION_EVIDENCE";
                  const isOrganizationEditorial = source?.source_origin === "ORGANIZATION_EDITORIAL";
                  const addedBy = isOrganizationEditorial && source?.added_by?.username
                     ? `Added by @${source.added_by.username}`
                     : null;

                  return (
                     <li key={source?.id || `${source?.url}-${index}`}>
                        <div className="drafting-source-main">
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
                        <div className="drafting-source-flags">
                           <span>{sourceOriginLabel(source?.source_origin)}</span>
                           {isDecisionEvidence ? <span>Sealed evidence</span> : null}
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

function sourceRowsFromValue(value) {
   const rows = String(value ?? "").split(/\r?\n/);
   return rows.length > 0 ? rows : [""];
}

function getSourceRowIssue(value, rows, index) {
   const trimmed = value.trim();

   if (!trimmed) {
      return "";
   }

   let parsed;

   try {
      parsed = new URL(trimmed);
   } catch {
      return "Enter a complete http:// or https:// URL.";
   }

   if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "Enter a complete http:// or https:// URL.";
   }

   const firstMatch = rows.findIndex((row) => row.trim() === trimmed);

   if (firstMatch !== index) {
      return "This source has already been added.";
   }

   return "";
}

function EditorialSourceEditor({ idPrefix, value, disabled, onChange }) {
   const rows = sourceRowsFromValue(value);

   const updateRow = (index, nextValue) => {
      const nextRows = [...rows];
      nextRows[index] = nextValue;
      onChange(nextRows.join("\n"));
   };

   const addRow = () => {
      const nextRows = [...rows, ""];
      onChange(nextRows.join("\n"));

      requestAnimationFrame(() => {
         document.getElementById(`${idPrefix}-${nextRows.length - 1}`)?.focus();
      });
   };

   const removeRow = (index) => {
      const nextRows = rows.filter((_, rowIndex) => rowIndex !== index);

      onChange((nextRows.length > 0 ? nextRows : [""]).join("\n"));
   };

   const canAddAnother = !disabled && rows.every((row, index) => row.trim() && !getSourceRowIssue(row, rows, index));

   return (
      <div className="drafting-source-editor" role="group" aria-labelledby={`${idPrefix}-heading`}>
         <div className="drafting-source-editor-header">
            <div>
               <strong id={`${idPrefix}-heading`}>Sources for this article</strong>
               <p>
                  Add sources your organization used to support or explain this article. These do not change the
                  verified claim, verdict, or decision-time evidence.
               </p>
            </div>
         </div>

         <div className="drafting-source-input-list">
            {rows.map((row, index) => {
               const issue = getSourceRowIssue(row, rows, index);
               const inputId = `${idPrefix}-${index}`;

               return (
                  <div className="drafting-source-input-item" key={inputId}>
                     <label htmlFor={inputId}>Source {index + 1}</label>

                     <div className="drafting-source-input-row">
                        <Input
                           id={inputId}
                           type="url"
                           inputMode="url"
                           value={row}
                           placeholder="https://example.com/source"
                           autoCapitalize="none"
                           autoCorrect="off"
                           spellCheck={false}
                           disabled={disabled}
                           aria-invalid={Boolean(issue)}
                           aria-describedby={issue ? `${inputId}-error` : undefined}
                           onChange={(event) => updateRow(index, event.target.value)}
                        />

                        <Button
                           type="button"
                           variant="ghost"
                           density="compact"
                           disabled={disabled}
                           onClick={() => removeRow(index)}
                           aria-label={`Remove source ${index + 1}`}
                        >
                           Remove
                        </Button>
                     </div>

                     {issue ? (
                        <span id={`${inputId}-error`} className="drafting-source-input-error">
                           {issue}
                        </span>
                     ) : null}
                  </div>
               );
            })}
         </div>

         <div className="drafting-source-editor-footer">
            <Button
               type="button"
               variant="secondary"
               density="compact"
               disabled={!canAddAnother}
               leadingIcon={<Icons name="circle-plus" size={15} />}
               onClick={addRow}
            >
               Add another source
            </Button>

            <span>Sources are optional. Each source must use a complete http:// or https:// URL.</span>
         </div>
      </div>
   );
}

function ServerConflict({ conflict, editor, focusRef, onUseLatest, onContinue }) {
   const server = conflict?.serverDetail;
   const latestEditor = server ? detailToEditor(server) : null;
   const canContinue = server?.allowed_actions?.includes("UPDATE_DRAFT");

   return (
      <section
         ref={focusRef}
         className="drafting-conflict"
         role="alert"
         tabIndex={-1}
         aria-labelledby="drafting-conflict-heading"
      >
         <div>
            <Icons name="alert-triangle" size={19} />
            <div>
               <h4 id="drafting-conflict-heading">
                  {conflict?.code === "STALE_EDIT_GENERATION"
                     ? "The server draft changed after this editor was opened."
                     : "This publication work changed on the server."}
               </h4>
               <p>
                  <strong>{conflict?.code || "CONFLICT"}</strong> · {conflict?.detail || "The update was not applied."}
               </p>
            </div>
         </div>

         {conflict?.loading ? (
            <p className="drafting-conflict-loading">Loading the latest server version…</p>
         ) : server ? (
            <div className="drafting-conflict-comparison">
               <section>
                  <h5>My unsaved editor</h5>
                  <dl>
                     <div>
                        <dt>Headline</dt>
                        <dd>{editor.headline || "Blank"}</dd>
                     </div>
                     <div>
                        <dt>Summary</dt>
                        <dd>{editor.summary || "Blank"}</dd>
                     </div>
                     <div>
                        <dt>Article body</dt>
                        <dd>{editor.articleBody || "Blank"}</dd>
                     </div>
                     <div>
                        <dt>Editorial source selection</dt>
                        <dd>{editor.sourceUrls || "No URLs selected"}</dd>
                     </div>
                  </dl>
               </section>
               <section>
                  <h5>Latest server version</h5>
                  <dl>
                     <div>
                        <dt>Edit generation</dt>
                        <dd>{server?.concurrency?.edit_generation ?? server?.edit_generation ?? "Unavailable"}</dd>
                     </div>
                     <div>
                        <dt>Headline</dt>
                        <dd>{latestEditor.headline || "Blank"}</dd>
                     </div>
                     <div>
                        <dt>Summary</dt>
                        <dd>{latestEditor.summary || "Blank"}</dd>
                     </div>
                     <div>
                        <dt>Article body</dt>
                        <dd>{latestEditor.articleBody || "Blank"}</dd>
                     </div>
                     <div>
                        <dt>Editorial source selection</dt>
                        <dd>{latestEditor.sourceUrls || "No URLs selected"}</dd>
                     </div>
                  </dl>
               </section>
            </div>
         ) : (
            <p>Your local text remains visible for recovery, but the latest server item could not be loaded.</p>
         )}

         {server ? (
            <div className="drafting-conflict-actions">
               <Button type="button" variant="secondary" density="compact" onClick={onUseLatest}>
                  Use latest server version
               </Button>
               {conflict?.code === "STALE_EDIT_GENERATION" && canContinue ? (
                  <Button type="button" variant="primary" density="compact" onClick={onContinue}>
                     Continue with my edits after reviewing latest
                  </Button>
               ) : null}
            </div>
         ) : null}

         {server && !canContinue ? (
            <p className="drafting-conflict-readonly">
               The latest server state no longer allows draft updates. Your local text remains available to copy.
            </p>
         ) : null}
      </section>
   );
}

function DraftingContent({ authFetch, authIdentity, organizationId, organizationName }) {
   const [offset, setOffset] = useState(0);
   const [queue, setQueue] = useState({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
   const [queueLoading, setQueueLoading] = useState(true);
   const [queueRefreshing, setQueueRefreshing] = useState(false);
   const [queueError, setQueueError] = useState("");
   const [queueRequestVersion, setQueueRequestVersion] = useState(0);

   const [selectedWork, setSelectedWork] = useState(null);
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(false);
   const [detailError, setDetailError] = useState("");
   const [detailUnavailable, setDetailUnavailable] = useState(false);
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);

   const [editor, setEditor] = useState(EMPTY_EDITOR);
   const [editorBase, setEditorBase] = useState(EMPTY_EDITOR);
   const [forceDirty, setForceDirty] = useState(false);
   const [validationError, setValidationError] = useState("");
   const [mutation, setMutation] = useState(null);
   const [notice, setNotice] = useState("");
   const [actionError, setActionError] = useState("");
   const [authorityError, setAuthorityError] = useState("");
   const [authorityRetrying, setAuthorityRetrying] = useState(false);
   const [conflict, setConflict] = useState(null);
   const [abandonOpen, setAbandonOpen] = useState(false);
   const [abandonReason, setAbandonReason] = useState("");

   const mountedRef = useRef(true);
   const authorityGenerationRef = useRef(0);
   const queueRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const mutationRequestIdRef = useRef(0);
   const selectedKeyRef = useRef("");
   const hasLoadedQueueRef = useRef(false);
   const skipNextDetailLoadRef = useRef("");
   const authorityRetryRef = useRef(null);
   const isDirtyRef = useRef(false);
   const editorBaseGenerationRef = useRef(null);
   const detailHeadingRef = useRef(null);
   const detailErrorRef = useRef(null);
   const conflictRef = useRef(null);
   const queueHeadingRef = useRef(null);
   const actionMessageRef = useRef(null);
   const focusDetailAfterLoadRef = useRef(false);
   const focusQueueAfterReturnRef = useRef(false);
   const focusActionMessageRef = useRef(false);

   const selectedKey = selectionKey(selectedWork?.resourceType, selectedWork?.resourceId);
   const isDirty = forceDirty || JSON.stringify(editor) !== JSON.stringify(editorBase);
   const authorityBlocked = Boolean(authorityError) || authorityRetrying;
   const allowedActions = Array.isArray(detail?.allowed_actions) ? detail.allowed_actions : [];
   const isInitialWork = !detail || detail.workflow_kind === "INITIAL";
   const isDraft = detail?.resource_type === "FACT_CHECK" && detail?.publication_status === "DRAFT";
   const isInReview = detail?.resource_type === "FACT_CHECK" && detail?.publication_status === "IN_REVIEW";

   isDirtyRef.current = isDirty;

   const queueUrl = useMemo(() => {
      const query = new URLSearchParams({
         organization_id: organizationId,
         queue: "DRAFTING",
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
      (operation) => isOperationContextCurrent(operation) && selectedKeyRef.current === operation.selectionKey,
      [isOperationContextCurrent],
   );

   const isMutationContextCurrent = useCallback(
      (operation) => isOperationContextCurrent(operation) && mutationRequestIdRef.current === operation.requestId,
      [isOperationContextCurrent],
   );

   const completeAuthorityRetryPart = useCallback((generation, part, detailKey = "") => {
      const retry = authorityRetryRef.current;

      if (!retry || retry.generation !== generation) {
         return;
      }

      if (part === "queue") {
         retry.queueComplete = true;
      } else if (part === "detail" && retry.detailKey === detailKey) {
         retry.detailComplete = true;
      }

      if (retry.queueComplete && retry.detailComplete) {
         authorityRetryRef.current = null;
         setAuthorityError("");
         setAuthorityRetrying(false);
      }
   }, []);

   const stopAuthorityRetry = useCallback((generation) => {
      if (authorityRetryRef.current?.generation !== generation) {
         return;
      }

      authorityRetryRef.current = null;
      setAuthorityRetrying(false);
   }, []);

   const revokeAuthority = useCallback(() => {
      authorityGenerationRef.current += 1;
      authorityRetryRef.current = null;
      queueRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      mutationRequestIdRef.current += 1;
      setAuthorityRetrying(false);
      setMutation(null);
      setQueueLoading(false);
      setQueueRefreshing(false);
      setDetailLoading(false);
      setNotice("");
      setActionError("");
      setValidationError("");
      setConflict(null);
      setAbandonOpen(false);
      setAuthorityError("Your publication access for this organization is no longer available.");
      focusActionMessageRef.current = true;
   }, []);

   const applyEditorFromDetail = useCallback((canonicalDetail) => {
      const nextEditor =
         canonicalDetail?.resource_type === "FACT_CHECK" && canonicalDetail?.publication_status === "DRAFT"
            ? detailToEditor(canonicalDetail)
            : EMPTY_EDITOR;

      setEditor(nextEditor);
      setEditorBase(nextEditor);
      editorBaseGenerationRef.current = getEditGeneration(canonicalDetail);
      setForceDirty(false);
      setValidationError("");
   }, []);

   useEffect(() => {
      mountedRef.current = true;

      return () => {
         mountedRef.current = false;
         authorityRetryRef.current = null;
         authorityGenerationRef.current += 1;
         queueRequestIdRef.current += 1;
         detailRequestIdRef.current += 1;
         mutationRequestIdRef.current += 1;
      };
   }, []);

   useEffect(() => {
      selectedKeyRef.current = selectedKey;

      const retry = authorityRetryRef.current;
      if (!retry || retry.generation !== authorityGenerationRef.current) {
         return;
      }

      retry.detailKey = selectedKey;
      retry.detailComplete = !selectedKey;
      if (!selectedKey) {
         completeAuthorityRetryPart(retry.generation, "detail", "");
      }
   }, [completeAuthorityRetryPart, selectedKey]);

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
      if (focusActionMessageRef.current && (notice || actionError || validationError || authorityError)) {
         focusActionMessageRef.current = false;
         actionMessageRef.current?.focus();
      }
   }, [actionError, authorityError, notice, validationError]);

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
      if (focusQueueAfterReturnRef.current && !selectedWork) {
         focusQueueAfterReturnRef.current = false;
         queueHeadingRef.current?.focus();
      }
   }, [selectedWork]);

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
            setQueue({
               count,
               limit: Number(data?.limit ?? PAGE_SIZE),
               offset: Number(data?.offset ?? offset),
               results,
            });
            setQueueError("");
            setQueueLoading(false);
            setQueueRefreshing(false);

            if (authorityRetryRef.current?.generation === authorityGeneration) {
               completeAuthorityRetryPart(authorityGeneration, "queue");
            }
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

            stopAuthorityRetry(authorityGeneration);
            setQueueError(error?.message || "Unable to load the publication Drafting queue.");
            setQueueLoading(false);
            setQueueRefreshing(false);
         });

      return () => {
         cancelled = true;
      };
   }, [
      authFetch,
      completeAuthorityRetryPart,
      offset,
      queueRequestVersion,
      queueUrl,
      revokeAuthority,
      stopAuthorityRetry,
   ]);

   useEffect(() => {
      if (!selectedWork) {
         return undefined;
      }

      if (skipNextDetailLoadRef.current === selectedKey) {
         skipNextDetailLoadRef.current = "";
         return undefined;
      }

      let cancelled = false;
      const requestId = detailRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      const requestKey = selectedKey;
      detailRequestIdRef.current = requestId;
      setDetailLoading(true);
      setDetailError("");
      setDetailUnavailable(false);

      const query = new URLSearchParams({ organization_id: organizationId });
      const url = `${resolveApiEndpoint(
         "PUBLICATION_WORK_ITEM_DETAIL",
         selectedWork.resourceType,
         selectedWork.resourceId,
      )}?${query.toString()}`;

      authFetch(url, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== requestId ||
               selectedKeyRef.current !== requestKey ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }

            const authorityRetry = authorityRetryRef.current;
            const isAuthorityRetryDetail =
               authorityRetry?.generation === authorityGeneration && authorityRetry.detailKey === requestKey;
            const preserveDirtyEditor = isAuthorityRetryDetail && isDirtyRef.current;

            setDetail(data);
            setDetailError("");
            setDetailUnavailable(false);
            setDetailLoading(false);
            setActionError("");
            setAbandonOpen(false);
            setAbandonReason("");

            if (preserveDirtyEditor) {
               const freshGeneration = getEditGeneration(data);
               const baseGeneration = editorBaseGenerationRef.current;
               const isEditableDraft = data?.resource_type === "FACT_CHECK" && data?.publication_status === "DRAFT";
               const canUpdateDraft = data?.allowed_actions?.includes("UPDATE_DRAFT");

               if (freshGeneration !== baseGeneration || !isEditableDraft || !canUpdateDraft) {
                  setConflict({
                     code:
                        freshGeneration !== baseGeneration ? "STALE_EDIT_GENERATION" : "DRAFT_UPDATE_NO_LONGER_ALLOWED",
                     detail:
                        freshGeneration !== baseGeneration
                           ? "The draft changed while publication authority was being revalidated."
                           : "The latest server state no longer allows this draft to be updated.",
                     blockers: Array.isArray(data?.blockers) ? data.blockers : [],
                     serverDetail: data,
                     loading: false,
                  });
               } else {
                  setConflict(null);
               }
            } else {
               setConflict(null);
               applyEditorFromDetail(data);
            }

            if (isAuthorityRetryDetail) {
               completeAuthorityRetryPart(authorityGeneration, "detail", requestKey);
            }
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
               selectedKeyRef.current !== requestKey ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }

            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }

            stopAuthorityRetry(authorityGeneration);

            const unavailable = error?.status === 404;
            setDetail(null);
            setDetailLoading(false);
            setDetailUnavailable(unavailable);
            setDetailError(
               unavailable
                  ? "This publication work item is no longer available."
                  : error?.message || "Unable to load this publication work item.",
            );

            if (unavailable) {
               setQueueRefreshing(true);
               setQueueRequestVersion((current) => current + 1);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [
      applyEditorFromDetail,
      authFetch,
      completeAuthorityRetryPart,
      detailRequestVersion,
      organizationId,
      revokeAuthority,
      selectedKey,
      selectedWork,
      stopAuthorityRetry,
   ]);

   const requestQueueRefresh = useCallback(() => {
      setQueueRefreshing(true);
      setQueueRequestVersion((current) => current + 1);
   }, []);

   const refreshDetailAfterConflict = useCallback(
      async (operation, error) => {
         const requestId = detailRequestIdRef.current + 1;
         detailRequestIdRef.current = requestId;
         const requestKey = operation.selectionKey;
         const query = new URLSearchParams({ organization_id: operation.organizationId });
         const url = `${resolveApiEndpoint(
            "PUBLICATION_WORK_ITEM_DETAIL",
            operation.resourceType,
            operation.resourceId,
         )}?${query.toString()}`;

         try {
            const latest = await authFetch(url, { method: "GET" });
            if (
               !isOperationCurrent(operation) ||
               detailRequestIdRef.current !== requestId ||
               selectedKeyRef.current !== requestKey
            ) {
               return;
            }

            setDetail(latest);
            setDetailUnavailable(false);
            setDetailError("");
            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The update was not applied.",
               blockers: Array.isArray(error?.blockers) ? error.blockers : [],
               serverDetail: latest,
               loading: false,
            });
         } catch (refreshError) {
            if (
               !isOperationCurrent(operation) ||
               detailRequestIdRef.current !== requestId ||
               selectedKeyRef.current !== requestKey
            ) {
               return;
            }

            if (refreshError?.status === 401 || refreshError?.status === 403) {
               revokeAuthority();
               return;
            }

            const unavailable = refreshError?.status === 404;
            setDetailUnavailable(unavailable);
            setDetailError(
               unavailable ? "This publication work item is no longer available." : "Latest server state unavailable.",
            );
            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The update was not applied.",
               blockers: Array.isArray(error?.blockers) ? error.blockers : [],
               serverDetail: null,
               loading: false,
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

            setConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The update was not applied.",
               blockers: Array.isArray(error?.blockers) ? error.blockers : [],
               serverDetail: null,
               loading: true,
            });
            setActionError("");
            refreshDetailAfterConflict(operation, error);
            return;
         }

         if (error?.status === 404) {
            requestQueueRefresh();
            if (!isOperationCurrent(operation)) {
               return;
            }

            setDetailUnavailable(true);
            setDetail(null);
            setDetailError("This publication work item is no longer available.");
            return;
         }

         if (!isOperationCurrent(operation)) {
            return;
         }

         setActionError(error?.message || fallbackMessage);
         focusActionMessageRef.current = true;
      },
      [isOperationCurrent, refreshDetailAfterConflict, requestQueueRefresh, revokeAuthority],
   );

   const makeOperation = useCallback(
      () => ({
         authIdentity,
         organizationId,
         authorityGeneration: authorityGenerationRef.current,
         requestId: mutationRequestIdRef.current + 1,
         selectionKey: selectedKeyRef.current,
         resourceType: selectedWork?.resourceType,
         resourceId: selectedWork?.resourceId,
      }),
      [authIdentity, organizationId, selectedWork],
   );

   const validateEditor = () => {
      if (!editor.headline.trim()) {
         return { message: "Headline is required." };
      }
      if (editor.headline.length > 300) {
         return { message: "Headline must be 300 characters or fewer." };
      }
      if (!editor.summary.trim()) {
         return { message: "Summary is required." };
      }

      const parsedSources = parseSourceUrls(editor.sourceUrls);
      if (parsedSources.invalid.length > 0) {
         return {
            message: `Use only valid http/https source URLs. Check: ${parsedSources.invalid.join(", ")}`,
         };
      }

      return { sourceUrls: parsedSources.urls };
   };

   const handleCreateDraft = async (event) => {
      event.preventDefault();
      if (mutation || authorityBlocked || conflict || !allowedActions.includes("CREATE_DRAFT")) {
         return;
      }

      const validation = validateEditor();
      if (validation.message) {
         setValidationError(validation.message);
         focusActionMessageRef.current = true;
         return;
      }

      const operation = makeOperation();
      mutationRequestIdRef.current = operation.requestId;
      setMutation("create");
      setValidationError("");
      setActionError("");
      setNotice("");

      try {
         const created = await authFetch(resolveApiEndpoint("FACT_CHECK_DRAFT_CREATE", operation.resourceId), {
            method: "POST",
            body: {
               organization_id: operation.organizationId,
               expected_decision_revision: detail?.decision?.revision_number ?? detail?.concurrency?.decision_revision,
               headline: editor.headline.trim(),
               summary: editor.summary.trim(),
               article_body: editor.articleBody,
               source_urls: validation.sourceUrls,
            },
         });

         if (!isMutationContextCurrent(operation)) {
            return;
         }

         requestQueueRefresh();
         if (!isOperationCurrent(operation)) {
            return;
         }

         const factCheckId = created?.fact_check_id || created?.id || created?.resource_id;
         const nextKey = selectionKey("FACT_CHECK", factCheckId);
         skipNextDetailLoadRef.current = nextKey;
         selectedKeyRef.current = nextKey;
         setSelectedWork({ resourceType: "FACT_CHECK", resourceId: String(factCheckId) });
         setDetail(created);
         setDetailUnavailable(false);
         setDetailError("");
         applyEditorFromDetail(created);
         setNotice("Draft created from the current human adjudication decision.");
         focusActionMessageRef.current = true;
      } catch (error) {
         if (isMutationContextCurrent(operation)) {
            handleMutationError(error, operation, "Unable to create this fact-check draft.");
         }
      } finally {
         if (isMutationContextCurrent(operation)) {
            setMutation(null);
         }
      }
   };

   const handleSaveDraft = async (event) => {
      event.preventDefault();
      if (mutation || authorityBlocked || conflict || !allowedActions.includes("UPDATE_DRAFT")) {
         return;
      }

      const validation = validateEditor();
      if (validation.message) {
         setValidationError(validation.message);
         focusActionMessageRef.current = true;
         return;
      }

      const operation = makeOperation();
      mutationRequestIdRef.current = operation.requestId;
      setMutation("save");
      setValidationError("");
      setActionError("");
      setNotice("");

      try {
         const updated = await authFetch(resolveApiEndpoint("FACT_CHECK_DRAFT_UPDATE", operation.resourceId), {
            method: "PATCH",
            body: {
               organization_id: operation.organizationId,
               expected_edit_generation: detail?.concurrency?.edit_generation ?? detail?.edit_generation,
               expected_decision_revision: detail?.concurrency?.decision_revision ?? detail?.decision?.revision_number,
               headline: editor.headline.trim(),
               summary: editor.summary.trim(),
               article_body: editor.articleBody,
               source_urls: validation.sourceUrls,
            },
         });

         if (!isMutationContextCurrent(operation)) {
            return;
         }

         requestQueueRefresh();
         if (!isOperationCurrent(operation)) {
            return;
         }

         setDetail(updated);
         applyEditorFromDetail(updated);
         setNotice("Draft saved.");
         focusActionMessageRef.current = true;
      } catch (error) {
         if (isMutationContextCurrent(operation)) {
            handleMutationError(error, operation, "Unable to save this draft.");
         }
      } finally {
         if (isMutationContextCurrent(operation)) {
            setMutation(null);
         }
      }
   };

   const handleSubmit = async () => {
      if (mutation || authorityBlocked || conflict || isDirty || !allowedActions.includes("SUBMIT")) {
         return;
      }

      const operation = makeOperation();
      mutationRequestIdRef.current = operation.requestId;
      setMutation("submit");
      setActionError("");
      setNotice("");

      try {
         const submitted = await authFetch(resolveApiEndpoint("FACT_CHECK_SUBMIT", operation.resourceId), {
            method: "POST",
            body: {
               organization_id: operation.organizationId,
               expected_edit_generation: detail?.concurrency?.edit_generation ?? detail?.edit_generation,
               expected_decision_revision: detail?.concurrency?.decision_revision ?? detail?.decision?.revision_number,
            },
         });

         if (!isMutationContextCurrent(operation)) {
            return;
         }

         requestQueueRefresh();
         if (!isOperationCurrent(operation)) {
            return;
         }

         setDetail(submitted);
         applyEditorFromDetail(submitted);
         setNotice("Submitted for publication review.");
         focusActionMessageRef.current = true;
      } catch (error) {
         if (isMutationContextCurrent(operation)) {
            handleMutationError(error, operation, "Unable to submit this draft for publication review.");
         }
      } finally {
         if (isMutationContextCurrent(operation)) {
            setMutation(null);
         }
      }
   };

   const handleAbandon = async (event) => {
      event.preventDefault();
      const reason = abandonReason.trim();
      if (!reason) {
         setValidationError("An abandonment reason is required.");
         focusActionMessageRef.current = true;
         return;
      }
      if (reason.length > 2000) {
         setValidationError("Abandonment reason must be 2000 characters or fewer.");
         focusActionMessageRef.current = true;
         return;
      }
      if (mutation || authorityBlocked || conflict || !allowedActions.includes("ABANDON")) {
         return;
      }

      const operation = makeOperation();
      mutationRequestIdRef.current = operation.requestId;
      setMutation("abandon");
      setValidationError("");
      setActionError("");
      setNotice("");

      try {
         await authFetch(resolveApiEndpoint("FACT_CHECK_ABANDON", operation.resourceId), {
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

         selectedKeyRef.current = "";
         setSelectedWork(null);
         setDetail(null);
         applyEditorFromDetail(null);
         setAbandonOpen(false);
         setAbandonReason("");
         setNotice("Draft abandoned. The claim remains available for future publication work.");
         focusActionMessageRef.current = true;
         focusQueueAfterReturnRef.current = true;
      } catch (error) {
         if (isMutationContextCurrent(operation)) {
            handleMutationError(error, operation, "Unable to abandon this draft.");
         }
      } finally {
         if (isMutationContextCurrent(operation)) {
            setMutation(null);
         }
      }
   };

   const confirmDiscard = () =>
      !isDirty || window.confirm("Discard your unsaved draft changes and open another work item?");

   const handleSelectWork = (item) => {
      const nextKey = selectionKey(item?.resource_type, item?.resource_id);
      if (!nextKey || nextKey === selectedKeyRef.current || !confirmDiscard()) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedKeyRef.current = nextKey;
      setSelectedWork({ resourceType: item.resource_type, resourceId: String(item.resource_id) });
      setDetail(null);
      setDetailError("");
      setDetailUnavailable(false);
      setConflict(null);
      setActionError("");
      setValidationError("");
      setNotice("");
      setAbandonOpen(false);
      setAbandonReason("");
      setEditor(EMPTY_EDITOR);
      setEditorBase(EMPTY_EDITOR);
      setForceDirty(false);
      focusDetailAfterLoadRef.current = true;
   };

   const handleReturnToQueue = () => {
      if (!confirmDiscard()) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedKeyRef.current = "";
      setSelectedWork(null);
      setDetail(null);
      setDetailError("");
      setDetailUnavailable(false);
      setConflict(null);
      setActionError("");
      setValidationError("");
      setAbandonOpen(false);
      setAbandonReason("");
      setEditor(EMPTY_EDITOR);
      setEditorBase(EMPTY_EDITOR);
      setForceDirty(false);
      focusQueueAfterReturnRef.current = true;
   };

   const handleRefresh = () => {
      requestQueueRefresh();
   };

   const handleAuthorityRetry = () => {
      authorityGenerationRef.current += 1;
      const generation = authorityGenerationRef.current;
      const retrySelectionKey = selectedKeyRef.current;
      authorityRetryRef.current = {
         generation,
         queueComplete: false,
         detailKey: retrySelectionKey,
         detailComplete: !retrySelectionKey,
      };
      setAuthorityRetrying(true);
      setQueueError("");
      setQueueRequestVersion((current) => current + 1);
      if (retrySelectionKey) {
         setDetailRequestVersion((current) => current + 1);
      }
   };

   const useLatestServerVersion = () => {
      if (!conflict?.serverDetail) {
         return;
      }

      setDetail(conflict.serverDetail);
      applyEditorFromDetail(conflict.serverDetail);
      setConflict(null);
      setActionError("");
   };

   const continueWithLocalEdits = () => {
      if (!conflict?.serverDetail?.allowed_actions?.includes("UPDATE_DRAFT")) {
         return;
      }

      setDetail(conflict.serverDetail);
      setEditorBase(detailToEditor(conflict.serverDetail));
      setForceDirty(true);
      setConflict(null);
      setActionError("");
   };

   const pageStart = queue.count === 0 ? 0 : queue.offset + 1;
   const pageEnd = Math.min(queue.offset + queue.results.length, queue.count);
   const hasPrevious = offset > 0;
   const hasNext = offset + queue.limit < queue.count;

   return (
      <div className="drafting-panel">
         <div className="drafting-boundary-note">
            <Icons name="shield-check" size={18} />
            <p>
               Drafts interpret an existing human adjudication. Editing article content never changes the factual
               verdict or its sealed evidence basis.
            </p>
         </div>

         <div ref={actionMessageRef} className="drafting-operation-messages" tabIndex={-1} aria-live="polite">
            {authorityError ? (
               <div className="drafting-message drafting-message--critical" role="alert">
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
            {notice ? (
               <div className="drafting-message drafting-message--success" role="status">
                  <Icons name="check-circle" size={18} />
                  <p>{notice}</p>
               </div>
            ) : null}
            {actionError || validationError ? (
               <div className="drafting-message drafting-message--critical" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{validationError || actionError}</p>
               </div>
            ) : null}
         </div>

         {authorityError ? null : (
            <div className={`drafting-workbench ${selectedWork ? "has-selection" : ""}`}>
               <section className="drafting-queue" aria-labelledby="drafting-queue-heading">
                  <div className="drafting-queue-header">
                     <div>
                        <h3 id="drafting-queue-heading" ref={queueHeadingRef} tabIndex={-1}>
                           Drafting queue
                        </h3>
                        <p>{queue.count} publication work items</p>
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
                     <div className="drafting-state" role="status">
                        <Icons name="loader" size={22} className="drafting-spinner" />
                        <strong>Loading publication work…</strong>
                     </div>
                  ) : queueError && queue.results.length === 0 ? (
                     <div className="drafting-state drafting-state--error" role="alert">
                        <Icons name="alert-circle" size={22} />
                        <strong>Drafting queue unavailable</strong>
                        <p>{queueError}</p>
                        <Button type="button" variant="secondary" density="compact" onClick={requestQueueRefresh}>
                           Try again
                        </Button>
                     </div>
                  ) : queue.results.length === 0 ? (
                     <div className="drafting-state">
                        <Icons name="file-text" size={24} />
                        <strong>No drafting work</strong>
                        <p>No publication drafting work is available for this organization.</p>
                     </div>
                  ) : (
                     <>
                        {queueError ? (
                           <div className="drafting-queue-warning" role="alert">
                              {queueError} Existing results remain available.
                           </div>
                        ) : null}
                        <ul className="drafting-queue-list">
                           {queue.results.map((item) => {
                              const itemKey = selectionKey(item.resource_type, item.resource_id);
                              const selected = itemKey === selectedKey;
                              const status = getItemState(item);

                              return (
                                 <li key={itemKey}>
                                    <button
                                       type="button"
                                       className={`drafting-queue-row ${selected ? "is-selected" : ""}`}
                                       aria-current={selected ? "true" : undefined}
                                       onClick={() => handleSelectWork(item)}
                                    >
                                       <span className="drafting-row-topline">
                                          <span>{status}</span>
                                          <VerdictBadge verdict={item?.decision?.verdict} />
                                       </span>
                                       <strong>{item?.article?.headline || getClaimText(item)}</strong>
                                       {item?.article?.headline ? (
                                          <span className="drafting-row-claim">{getClaimText(item)}</span>
                                       ) : null}
                                       <span className="drafting-row-metadata">
                                          {item?.resource_type === "ELIGIBLE_CLAIM"
                                             ? `Decision revision ${item?.decision?.revision_number ?? "unavailable"}`
                                             : `Article v${item?.article?.version ?? "–"} · ${formatDateTime(
                                                  item?.article?.publication_status === "IN_REVIEW"
                                                     ? item?.lifecycle?.submitted_for_review_at
                                                     : item?.lifecycle?.actionable_at,
                                               )}`}
                                       </span>
                                       {Array.isArray(item?.blockers) && item.blockers.length > 0 ? (
                                          <span className="drafting-row-blockers">
                                             {item.blockers.length} readiness blocker
                                             {item.blockers.length === 1 ? "" : "s"}
                                          </span>
                                       ) : null}
                                    </button>
                                 </li>
                              );
                           })}
                        </ul>
                     </>
                  )}

                  {!queueLoading && queue.count > 0 ? (
                     <div className="drafting-pagination" aria-label="Drafting queue pagination">
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

               <section className="drafting-detail" aria-labelledby="drafting-detail-heading">
                  {!selectedWork ? (
                     <div className="drafting-state drafting-state--detail">
                        <Icons name="file-text" size={25} />
                        <h3 id="drafting-detail-heading">Select publication work</h3>
                        <p>Choose an eligible claim or draft to inspect its authoritative context and next actions.</p>
                     </div>
                  ) : (
                     <>
                        <Button
                           type="button"
                           variant="ghost"
                           density="compact"
                           className="drafting-return-to-queue"
                           leadingIcon={<Icons name="arrow-left" size={15} />}
                           onClick={handleReturnToQueue}
                        >
                           Back to queue
                        </Button>

                        {detailLoading && !detail ? (
                           <div className="drafting-state" role="status">
                              <Icons name="loader" size={22} className="drafting-spinner" />
                              <strong>Loading canonical work item…</strong>
                           </div>
                        ) : detailError && !detail ? (
                           <div className="drafting-state drafting-state--error" role="alert">
                              <Icons name={detailUnavailable ? "eye-off" : "alert-circle"} size={22} />
                              <h3 id="drafting-detail-heading" ref={detailErrorRef} tabIndex={-1}>
                                 {detailUnavailable ? "Work item unavailable" : "Unable to load work item"}
                              </h3>
                              <p>{detailError}</p>
                              <div className="drafting-state-actions">
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
                                 <Button type="button" variant="ghost" density="compact" onClick={handleReturnToQueue}>
                                    Return to queue
                                 </Button>
                              </div>
                           </div>
                        ) : detail ? (
                           <div className="drafting-detail-content">
                              <header className="drafting-detail-header">
                                 <div>
                                    <span className="drafting-status-label">
                                       {detail.resource_type === "ELIGIBLE_CLAIM"
                                          ? "Ready to draft"
                                          : formatLabel(detail.publication_status)}
                                    </span>
                                    <h3 id="drafting-detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                                       {detail.headline || detail.decision?.canonical_claim || "Publication work item"}
                                    </h3>
                                    <p>
                                       {organizationName || detail.organization?.name || "Selected organization"} ·
                                       Initial publication workflow
                                    </p>
                                 </div>
                                 {detail.resource_type === "FACT_CHECK" ? (
                                    <span className="drafting-version-label">Article v{detail.version ?? "–"}</span>
                                 ) : null}
                              </header>

                              {!isInitialWork ? (
                                 <div className="drafting-message drafting-message--warning" role="alert">
                                    <Icons name="alert-triangle" size={18} />
                                    <p>
                                       This workspace supports initial publication work only. This item is read-only
                                       here.
                                    </p>
                                 </div>
                              ) : null}

                              {isInReview ? (
                                 <div className="drafting-review-notice">
                                    <Icons name="clock" size={18} />
                                    <div>
                                       <strong>Awaiting publication review</strong>
                                       <p>Publication actions are available only in the Publishing workspace.</p>
                                    </div>
                                 </div>
                              ) : null}

                              {conflict ? (
                                 <ServerConflict
                                    conflict={conflict}
                                    editor={editor}
                                    focusRef={conflictRef}
                                    onUseLatest={useLatestServerVersion}
                                    onContinue={continueWithLocalEdits}
                                 />
                              ) : null}

                              {detail.resource_type === "FACT_CHECK" ? (
                                 <section
                                    className="drafting-article-context"
                                    aria-labelledby="drafting-article-context-heading"
                                 >
                                    <div className="drafting-section-heading">
                                       <div>
                                          <h4 id="drafting-article-context-heading">Article context</h4>
                                          <p>Current lifecycle and concurrency metadata for this article.</p>
                                       </div>
                                    </div>
                                    <dl className="drafting-compact-metadata drafting-compact-metadata--article">
                                       <div>
                                          <dt>Status</dt>
                                          <dd>{formatLabel(detail.publication_status)}</dd>
                                       </div>
                                       <div>
                                          <dt>Drafter</dt>
                                          <dd>{actorName(detail.drafted_by)}</dd>
                                       </div>
                                       <div>
                                          <dt>Submitted</dt>
                                          <dd>
                                             <FormattedDateTime
                                                value={detail.submitted_for_review_at}
                                                fallback="Not submitted"
                                             />
                                          </dd>
                                       </div>
                                       <div>
                                          <dt>Edit generation</dt>
                                          <dd>
                                             {detail.concurrency?.edit_generation ??
                                                detail.edit_generation ??
                                                "Not recorded"}
                                          </dd>
                                       </div>
                                    </dl>
                                 </section>
                              ) : null}

                              <HumanAdjudication detail={detail} />

                              {detail.resource_type === "ELIGIBLE_CLAIM" &&
                              allowedActions.includes("CREATE_DRAFT") &&
                              isInitialWork ? (
                                 <form className="drafting-editor" onSubmit={handleCreateDraft}>
                                    <div className="drafting-section-heading">
                                       <div>
                                          <h4>Create article draft</h4>
                                          <p>Start editorial content without changing the adjudication record.</p>
                                       </div>
                                       {isDirty ? <span className="drafting-unsaved-label">Unsaved</span> : null}
                                    </div>
                                    <div className="drafting-field">
                                       <label htmlFor="drafting-create-headline">Headline</label>
                                       <Input
                                          id="drafting-create-headline"
                                          value={editor.headline}
                                          maxLength={300}
                                          required
                                          disabled={Boolean(mutation) || authorityBlocked}
                                          onChange={(event) =>
                                             setEditor((current) => ({ ...current, headline: event.target.value }))
                                          }
                                       />
                                       <span>{editor.headline.length}/300</span>
                                    </div>
                                    <div className="drafting-field">
                                       <label htmlFor="drafting-create-summary">Summary</label>
                                       <Textarea
                                          id="drafting-create-summary"
                                          rows={4}
                                          value={editor.summary}
                                          required
                                          disabled={Boolean(mutation) || authorityBlocked}
                                          onChange={(event) =>
                                             setEditor((current) => ({ ...current, summary: event.target.value }))
                                          }
                                       />
                                    </div>
                                    <div className="drafting-field">
                                       <label htmlFor="drafting-create-body">Article analysis/body</label>
                                       <Textarea
                                          id="drafting-create-body"
                                          rows={10}
                                          value={editor.articleBody}
                                          disabled={Boolean(mutation) || authorityBlocked}
                                          onChange={(event) =>
                                             setEditor((current) => ({ ...current, articleBody: event.target.value }))
                                          }
                                       />
                                       <span>Optional while creating the draft.</span>
                                    </div>
                                    <div className="drafting-field">
                                       <EditorialSourceEditor
                                          idPrefix="drafting-create-source"
                                          value={editor.sourceUrls}
                                          disabled={Boolean(mutation) || authorityBlocked}
                                          onChange={(sourceUrls) =>
                                             setEditor((current) => ({
                                                ...current,
                                                sourceUrls,
                                             }))
                                          }
                                       />
                                    </div>
                                    <div className="drafting-editor-actions">
                                       <Button
                                          type="submit"
                                          variant="primary"
                                          density="standard"
                                          loading={mutation === "create"}
                                          loadingLabel="Creating draft…"
                                          disabled={Boolean(mutation) || authorityBlocked || Boolean(conflict)}
                                          leadingIcon={<Icons name="file-text" size={16} />}
                                       >
                                          Create draft
                                       </Button>
                                    </div>
                                 </form>
                              ) : null}

                              {isDraft && isInitialWork ? (
                                 <form className="drafting-editor" onSubmit={handleSaveDraft}>
                                    <div className="drafting-section-heading">
                                       <div>
                                          <h4>Article draft</h4>
                                          <p>Manual save only. Sealed evidence remains read-only.</p>
                                       </div>
                                       {isDirty ? (
                                          <span className="drafting-unsaved-label">Unsaved</span>
                                       ) : (
                                          <span className="drafting-saved-label">Saved</span>
                                       )}
                                    </div>
                                    <div className="drafting-field">
                                       <label htmlFor="drafting-edit-headline">Headline</label>
                                       <Input
                                          id="drafting-edit-headline"
                                          value={editor.headline}
                                          maxLength={300}
                                          required
                                          disabled={
                                             Boolean(mutation) ||
                                             authorityBlocked ||
                                             Boolean(conflict) ||
                                             !allowedActions.includes("UPDATE_DRAFT")
                                          }
                                          onChange={(event) =>
                                             setEditor((current) => ({ ...current, headline: event.target.value }))
                                          }
                                       />
                                       <span>{editor.headline.length}/300</span>
                                    </div>
                                    <div className="drafting-field">
                                       <label htmlFor="drafting-edit-summary">Summary</label>
                                       <Textarea
                                          id="drafting-edit-summary"
                                          rows={4}
                                          value={editor.summary}
                                          required
                                          disabled={
                                             Boolean(mutation) ||
                                             authorityBlocked ||
                                             Boolean(conflict) ||
                                             !allowedActions.includes("UPDATE_DRAFT")
                                          }
                                          onChange={(event) =>
                                             setEditor((current) => ({ ...current, summary: event.target.value }))
                                          }
                                       />
                                    </div>
                                    <div className="drafting-field">
                                       <label htmlFor="drafting-edit-body">Article analysis/body</label>
                                       <Textarea
                                          id="drafting-edit-body"
                                          rows={14}
                                          value={editor.articleBody}
                                          disabled={
                                             Boolean(mutation) ||
                                             authorityBlocked ||
                                             Boolean(conflict) ||
                                             !allowedActions.includes("UPDATE_DRAFT")
                                          }
                                          onChange={(event) =>
                                             setEditor((current) => ({ ...current, articleBody: event.target.value }))
                                          }
                                       />
                                    </div>
                                    <div className="drafting-field">
                                       <EditorialSourceEditor
                                          idPrefix="drafting-edit-source"
                                          value={editor.sourceUrls}
                                          disabled={
                                             Boolean(mutation) ||
                                             authorityBlocked ||
                                             Boolean(conflict) ||
                                             !allowedActions.includes("UPDATE_DRAFT")
                                          }
                                          onChange={(sourceUrls) =>
                                             setEditor((current) => ({
                                                ...current,
                                                sourceUrls,
                                             }))
                                          }
                                       />
                                    </div>
                                    <div className="drafting-editor-actions">
                                       {allowedActions.includes("UPDATE_DRAFT") ? (
                                          <Button
                                             type="submit"
                                             variant="primary"
                                             density="standard"
                                             loading={mutation === "save"}
                                             loadingLabel="Saving draft…"
                                             disabled={
                                                !isDirty || Boolean(mutation) || authorityBlocked || Boolean(conflict)
                                             }
                                             leadingIcon={<Icons name="check" size={16} />}
                                          >
                                             Save draft
                                          </Button>
                                       ) : null}
                                       {allowedActions.includes("SUBMIT") ? (
                                          <Button
                                             type="button"
                                             variant="secondary"
                                             density="standard"
                                             loading={mutation === "submit"}
                                             loadingLabel="Submitting…"
                                             disabled={
                                                isDirty || Boolean(mutation) || authorityBlocked || Boolean(conflict)
                                             }
                                             onClick={handleSubmit}
                                             leadingIcon={<Icons name="send" size={16} />}
                                          >
                                             Submit for review
                                          </Button>
                                       ) : null}
                                    </div>
                                    {allowedActions.includes("SUBMIT") && isDirty ? (
                                       <p className="drafting-submit-help">
                                          Save your changes before submitting for review.
                                       </p>
                                    ) : null}
                                 </form>
                              ) : null}

                              {isInReview ? (
                                 <section
                                    className="drafting-readonly-article"
                                    aria-labelledby="drafting-submitted-article-heading"
                                 >
                                    <div className="drafting-section-heading">
                                       <div>
                                          <h4 id="drafting-submitted-article-heading">Submitted article</h4>
                                          <p>Read-only content currently awaiting institutional publication review.</p>
                                       </div>
                                    </div>
                                    <h5>{detail.headline || "Untitled fact check"}</h5>
                                    <p className="drafting-readonly-summary">
                                       {detail.summary || "No summary recorded."}
                                    </p>
                                    <div className="drafting-article-body">
                                       {detail.article_body || "No article body recorded."}
                                    </div>
                                 </section>
                              ) : null}

                              <BlockerList blockers={detail.blockers} />
                              <PublicationSources sourceItems={detail.source_items} />
                              <SealedEvidence sealedEvidence={detail.sealed_evidence} />

                              {isDraft && isInitialWork && allowedActions.includes("ABANDON") && !conflict ? (
                                 <section className="drafting-danger-zone" aria-labelledby="drafting-abandon-heading">
                                    <div className="drafting-section-heading">
                                       <div>
                                          <h4 id="drafting-abandon-heading">Abandon draft</h4>
                                          <p>
                                             Archive this unpublished draft without completing the verification
                                             assignment.
                                          </p>
                                       </div>
                                    </div>
                                    {!abandonOpen ? (
                                       <Button
                                          type="button"
                                          variant="destructive"
                                          density="compact"
                                          disabled={Boolean(mutation) || authorityBlocked}
                                          onClick={() => {
                                             setAbandonOpen(true);
                                             setValidationError("");
                                          }}
                                       >
                                          Review abandonment
                                       </Button>
                                    ) : (
                                       <form
                                          className="drafting-abandon-confirmation"
                                          aria-labelledby="drafting-abandon-confirmation-heading"
                                          onSubmit={handleAbandon}
                                       >
                                          <h5 id="drafting-abandon-confirmation-heading">
                                             Archive this unpublished draft?
                                          </h5>
                                          <p>
                                             The verification assignment is not completed. A replacement initial draft
                                             may be created later from an eligible decision.
                                          </p>
                                          <div className="drafting-field">
                                             <label htmlFor="drafting-abandon-reason">Abandonment reason</label>
                                             <Textarea
                                                id="drafting-abandon-reason"
                                                rows={4}
                                                maxLength={2000}
                                                required
                                                value={abandonReason}
                                                disabled={Boolean(mutation)}
                                                onChange={(event) => setAbandonReason(event.target.value)}
                                             />
                                             <span>{abandonReason.length}/2000</span>
                                          </div>
                                          <div className="drafting-editor-actions">
                                             <Button
                                                type="button"
                                                variant="secondary"
                                                density="compact"
                                                disabled={Boolean(mutation)}
                                                onClick={() => {
                                                   setAbandonOpen(false);
                                                   setAbandonReason("");
                                                   setValidationError("");
                                                }}
                                             >
                                                Keep draft
                                             </Button>
                                             <Button
                                                type="submit"
                                                variant="destructive"
                                                density="compact"
                                                loading={mutation === "abandon"}
                                                loadingLabel="Abandoning…"
                                                disabled={!abandonReason.trim() || Boolean(mutation)}
                                             >
                                                Abandon draft
                                             </Button>
                                          </div>
                                       </form>
                                    )}
                                 </section>
                              ) : null}
                           </div>
                        ) : null}
                     </>
                  )}
               </section>
            </div>
         )}
      </div>
   );
}

function DraftingPanel(props) {
   const { authFetch, token, user } = useAuth();
   const authIdentity = getAuthIdentity(user, token);

   return (
      <DraftingContent
         key={`${props.organizationId}:${authIdentity}`}
         {...props}
         authFetch={authFetch}
         authIdentity={authIdentity}
      />
   );
}

export default DraftingPanel;
