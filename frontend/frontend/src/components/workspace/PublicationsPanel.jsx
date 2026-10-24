import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import { resolveApiEndpoint } from "../../utils/api";
import { getAuthSessionIdentity } from "../../utils/authIdentity";
import { showWorkspaceSuccess } from "../../utils/workspaceToast";
import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";
import Input from "../ui/Input.jsx";
import Textarea from "../ui/Textarea.jsx";

import "./PublicationsPanel.css";

const PAGE_SIZE = 20;
const VERDICT_CLASSES = {
   FACT: "fact",
   FAKE: "fake",
   MISLEADING: "misleading",
   SATIRE: "satire",
   UNVERIFIED: "unverified",
   OUT_OF_SCOPE: "outofscope",
};

const RECORD_STATE_LABELS = {
   SEALED: "Sealed publication record",
   LEGACY_UNSEALED: "Legacy publication record",
   INVALID_SEAL: "Publication record needs review",
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

function formatDateTime(value, fallback = "Publication time unavailable") {
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

function VerdictBadge({ verdict }) {
   const normalized = String(verdict || "").toUpperCase();
   const tone = VERDICT_CLASSES[normalized] || "neutral";

   return <span className={`publications-verdict publications-verdict--${tone}`}>{formatLabel(verdict)}</span>;
}

function RecordStateBadge({ recordState }) {
   return (
      <span className={`publications-record-state publications-record-state--${String(recordState).toLowerCase()}`}>
         {RECORD_STATE_LABELS[recordState] || "Publication record state unavailable"}
      </span>
   );
}

function Blockers({ blockers }) {
   if (!Array.isArray(blockers) || blockers.length === 0) {
      return null;
   }

   return (
      <section className="publications-section" aria-labelledby="publications-blockers-heading">
         <div className="publications-section-heading">
            <div>
               <h4 id="publications-blockers-heading">Revision availability</h4>
               <p>The server has reported conditions that prevent new editorial revision work.</p>
            </div>
         </div>
         <ul className="publications-blockers">
            {blockers.map((blocker, index) => (
               <li key={`${blocker?.code || "blocker"}-${index}`}>
                  <Icons name="alert-circle" size={16} />
                  <span>
                     <strong>{formatLabel(blocker?.code, "Publication blocker")}</strong>
                     {blocker?.detail || "This publication is not ready for an editorial revision."}
                  </span>
               </li>
            ))}
         </ul>
      </section>
   );
}

function CorrectionWorkflowBlockers({ blockers }) {
   const groups = Object.entries(blockers || {}).filter(([, items]) => Array.isArray(items) && items.length > 0);
   if (groups.length === 0) {
      return null;
   }

   return (
      <div className="publications-correction-blockers">
         {groups.map(([action, items]) => (
            <section key={action}>
               <strong>{formatLabel(action, "Factual correction availability")}</strong>
               <ul className="publications-blockers">
                  {items.map((blocker, index) => (
                     <li key={`${action}-${blocker?.code || "blocker"}-${index}`}>
                        <Icons name="alert-circle" size={16} />
                        <span>
                           <strong>{formatLabel(blocker?.code, "Correction blocker")}</strong>
                           {blocker?.detail || "This factual-correction action is not currently available."}
                        </span>
                     </li>
                  ))}
               </ul>
            </section>
         ))}
      </div>
   );
}

function HumanDecision({ detail }) {
   const decision = detail?.decision || {};

   return (
      <section className="publications-section" aria-labelledby="publications-decision-heading">
         <div className="publications-section-heading">
            <div>
               <h4 id="publications-decision-heading">Human decision · factual authority</h4>
               <p>The accountable human adjudication is authoritative and read-only in this publication library.</p>
            </div>
            <VerdictBadge verdict={decision.verdict} />
         </div>
         <dl className="publications-metadata-grid">
            <div className="publications-metadata-wide">
               <dt>Claim reviewed</dt>
               <dd>{decision.canonical_claim || detail?.claim?.canonical_claim || "Not recorded"}</dd>
            </div>
            <div className="publications-metadata-wide">
               <dt>Adjudication rationale</dt>
               <dd>{decision.rationale || "No rationale was recorded."}</dd>
            </div>
            <div>
               <dt>Verdict</dt>
               <dd>{formatLabel(decision.verdict)}</dd>
            </div>
            <div>
               <dt>Decision revision</dt>
               <dd>{decision.revision_number ?? "Not recorded"}</dd>
            </div>
            <div>
               <dt>Decided by</dt>
               <dd>{actorName(decision.decided_by)}</dd>
            </div>
            <div>
               <dt>Decided at</dt>
               <dd>
                  <FormattedDateTime value={decision.decided_at} fallback="Not recorded" />
               </dd>
            </div>
         </dl>
      </section>
   );
}

function PublicationSources({ sourceItems }) {
   const sources = Array.isArray(sourceItems) ? sourceItems : [];

   return (
      <section className="publications-section" aria-labelledby="publications-sources-heading">
         <div className="publications-section-heading">
            <div>
               <h4 id="publications-sources-heading">Publication sources</h4>
               <p>
                  Publication sources show where each source entered the publication record. Citing a source in the
                  article does not change the sealed decision evidence.
               </p>
            </div>
            <span className="publications-count-label">{sources.length} sources</span>
         </div>

         {sources.length === 0 ? (
            <p className="publications-inline-empty">No publication sources were recorded.</p>
         ) : (
            <ul className="publications-source-list">
               {sources.map((source, index) => {
                  const externalUrl = safeExternalUrl(source?.url);
                  const isDecisionEvidence = source?.source_origin === "DECISION_EVIDENCE";
                  const isOrganizationEditorial = source?.source_origin === "ORGANIZATION_EDITORIAL";

                  return (
                     <li key={source?.id || `${source?.url}-${index}`}>
                        <div className="publications-source-main">
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
                        <div className="publications-source-flags">
                           <span>{sourceOriginLabel(source?.source_origin)}</span>
                           {isDecisionEvidence ? <span>Sealed evidence</span> : null}
                           {isOrganizationEditorial ? <span>Editorial source</span> : null}
                           {isOrganizationEditorial && source?.added_by?.username ? (
                              <span>Added by @{source.added_by.username}</span>
                           ) : null}
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
      <section className="publications-section" aria-labelledby="publications-evidence-heading">
         <div className="publications-section-heading">
            <div>
               <h4 id="publications-evidence-heading">Sealed decision-time evidence</h4>
               <p>This immutable evidence basis belongs to the human decision, not to editable article citations.</p>
            </div>
            <span className="publications-count-label">{sealedEvidence?.count ?? entries.length} records</span>
         </div>

         {!sealedEvidence ? (
            <p className="publications-inline-empty">No valid sealed evidence snapshot is available.</p>
         ) : entries.length === 0 ? (
            <p className="publications-inline-empty">The sealed decision snapshot contains no evidence records.</p>
         ) : (
            <ol className="publications-evidence-list">
               {entries.map((entry, index) => {
                  const externalUrl = safeExternalUrl(entry?.evidence_url);

                  return (
                     <li key={entry?.id || index}>
                        <div className="publications-evidence-heading">
                           <strong>{entry?.evidence_caption || `Evidence record ${index + 1}`}</strong>
                           <span>{formatLabel(entry?.evidence_status)}</span>
                        </div>
                        <p>{formatLabel(entry?.evidence_type, "Evidence type not recorded")}</p>
                        <dl className="publications-evidence-metadata">
                           <div>
                              <dt>Submitted</dt>
                              <dd>
                                 <FormattedDateTime value={entry?.submitted_at} fallback="Not recorded" />
                              </dd>
                           </div>
                           <div>
                              <dt>Reviewed</dt>
                              <dd>
                                 <FormattedDateTime value={entry?.reviewed_at} fallback="Not recorded" />
                              </dd>
                           </div>
                        </dl>
                        {entry?.moderator_notes ? <p>{entry.moderator_notes}</p> : null}
                        {entry?.rejection_reason ? <p>Rejection reason: {entry.rejection_reason}</p> : null}
                        {externalUrl ? (
                           <a href={externalUrl} target="_blank" rel="noopener noreferrer">
                              Open captured source <Icons name="external-link" size={14} />
                           </a>
                        ) : null}
                     </li>
                  );
               })}
            </ol>
         )}
      </section>
   );
}

function VersionHistory({ lineage, selectedPublicationId, disabled, onSelect }) {
   const items = Array.isArray(lineage) ? lineage : [];

   return (
      <section className="publications-section" aria-labelledby="publications-history-heading">
         <div className="publications-section-heading">
            <div>
               <h4 id="publications-history-heading">Version history</h4>
               <p>Published versions remain inspectable in their server-defined historical order.</p>
            </div>
            <span className="publications-count-label">{items.length} versions</span>
         </div>

         {items.length === 0 ? (
            <p className="publications-inline-empty">Ordered version history is unavailable for this record.</p>
         ) : (
            <ol className="publications-history-list">
               {items.map((item) => {
                  const selected = String(item.publication_id) === String(selectedPublicationId);
                  return (
                     <li key={item.publication_id}>
                        <button
                           type="button"
                           className={selected ? "is-selected" : ""}
                           aria-current={selected ? "true" : undefined}
                           disabled={disabled}
                           onClick={() => onSelect(item.publication_id)}
                        >
                           <span className="publications-history-version">Article v{item.version}</span>
                           <span className="publications-history-copy">
                              <strong>{item.headline || "Untitled publication"}</strong>
                              <span>
                                 {formatLabel(item.revision_kind)} · {formatDateTime(item.published_at)} · Published by{" "}
                                 {actorName(item.published_by)}
                              </span>
                              {item.revision_reason ? <span>Reason: {item.revision_reason}</span> : null}
                           </span>
                           <span className={`publications-history-state publications-history-state--${item.history_state.toLowerCase()}`}>
                              {formatLabel(item.history_state)}
                           </span>
                        </button>
                     </li>
                  );
               })}
            </ol>
         )}
      </section>
   );
}

function PublicationReferenceMaterial({ detail }) {
   const article = detail?.article || {};

   return (
      <details className="publications-reference-material">
         <summary>
            <span>
               <strong>Reference material</strong>
               <small>Publication sources, sealed decision evidence, and technical record details</small>
            </span>
            <Icons name="chevron-down" size={16} aria-hidden="true" />
         </summary>

         <div className="publications-reference-content">
            <PublicationSources sourceItems={detail?.source_items} />
            <SealedEvidence sealedEvidence={detail?.sealed_evidence} />

            <details className="publications-technical-details">
               <summary>Technical details</summary>
               <dl className="publications-metadata-grid">
                  <div>
                     <dt>Publication status</dt>
                     <dd>{formatLabel(article.publication_status)}</dd>
                  </div>
                  <div>
                     <dt>Revision kind</dt>
                     <dd>{formatLabel(article.revision_kind)}</dd>
                  </div>
                  <div>
                     <dt>Record integrity</dt>
                     <dd>{RECORD_STATE_LABELS[detail?.record_state] || "Record state unavailable"}</dd>
                  </div>
                  <div>
                     <dt>Decision revision</dt>
                     <dd>{detail?.decision?.revision_number ?? "Not recorded"}</dd>
                  </div>
                  <div>
                     <dt>Selected version</dt>
                     <dd>Article v{article.version ?? "–"}</dd>
                  </div>
               </dl>
            </details>
         </div>
      </details>
   );
}

function PublicationActionDialog({
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
            ?.querySelector('textarea:not([disabled]), input:not([disabled]), button:not([disabled])')
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
         className="publications-dialog-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !processing) {
               onClose();
            }
         }}
      >
         <section
            ref={dialogRef}
            className="publications-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="publications-dialog-title"
            aria-describedby="publications-dialog-description"
            aria-busy={processing || undefined}
         >
            <div className="publications-dialog-copy">
               <h3 id="publications-dialog-title">{title}</h3>
               <p id="publications-dialog-description">{description}</p>
            </div>
            {children}
         </section>
      </div>
   );
}

function PublicationsContent({
   authFetch,
   authIdentity,
   organizationId,
   organizationName,
   initialPublicationId,
   onInitialPublicationConsumed,
   onRevisionCreated,
   onCorrectionOpened,
}) {
   const { addToast } = useNotification();
   const [searchInput, setSearchInput] = useState("");
   const [search, setSearch] = useState("");
   const [offset, setOffset] = useState(0);
   const [library, setLibrary] = useState({ count: 0, limit: PAGE_SIZE, offset: 0, results: [] });
   const [libraryLoading, setLibraryLoading] = useState(true);
   const [libraryRefreshing, setLibraryRefreshing] = useState(false);
   const [libraryError, setLibraryError] = useState("");
   const [libraryRequestVersion, setLibraryRequestVersion] = useState(0);

   const [selectedPublicationId, setSelectedPublicationId] = useState(
      initialPublicationId ? String(initialPublicationId) : null,
   );
   const [detail, setDetail] = useState(null);
   const [detailLoading, setDetailLoading] = useState(false);
   const [detailError, setDetailError] = useState("");
   const [detailRequestVersion, setDetailRequestVersion] = useState(0);

   const [authorityError, setAuthorityError] = useState("");
   const [actionError, setActionError] = useState("");
   const [revisionOpen, setRevisionOpen] = useState(false);
   const [revisionReason, setRevisionReason] = useState("");
   const [correctionOpen, setCorrectionOpen] = useState(false);
   const [correctionReason, setCorrectionReason] = useState("");
   const [correctionReasonError, setCorrectionReasonError] = useState("");
   const [correctionConflict, setCorrectionConflict] = useState(null);
   const [mutation, setMutation] = useState(null);

   const mountedRef = useRef(true);
   const authorityGenerationRef = useRef(0);
   const libraryRequestIdRef = useRef(0);
   const detailRequestIdRef = useRef(0);
   const mutationRequestIdRef = useRef(0);
   const selectedPublicationIdRef = useRef(selectedPublicationId);
   const hasLoadedLibraryRef = useRef(false);
   const detailHeadingRef = useRef(null);
   const libraryHeadingRef = useRef(null);
   const messageRef = useRef(null);
   const revisionReasonRef = useRef(null);
   const createRevisionButtonRef = useRef(null);
   const correctionReasonRef = useRef(null);
   const requestCorrectionButtonRef = useRef(null);
   const focusDetailAfterLoadRef = useRef(Boolean(initialPublicationId));
   const focusLibraryAfterReturnRef = useRef(false);

   const allowedActions = Array.isArray(detail?.allowed_actions) ? detail.allowed_actions : [];
   const canCreateRevision = allowedActions.includes("CREATE_EDITORIAL_REVISION");
   const correctionWorkflow = detail?.factual_correction_workflow || null;
   const correctionActions = Array.isArray(correctionWorkflow?.allowed_actions)
      ? correctionWorkflow.allowed_actions
      : [];
   const canRequestCorrection = correctionActions.includes("REQUEST_FACTUAL_CORRECTION");
   const canOpenCorrection = correctionActions.includes("OPEN_FACTUAL_CORRECTION");

   const libraryUrl = useMemo(() => {
      const query = new URLSearchParams({
         organization_id: organizationId,
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });
      if (search) {
         query.set("search", search);
      }
      return `${resolveApiEndpoint("PUBLICATION_LIBRARY")}?${query.toString()}`;
   }, [offset, organizationId, search]);

   const revokeAuthority = useCallback(() => {
      authorityGenerationRef.current += 1;
      libraryRequestIdRef.current += 1;
      detailRequestIdRef.current += 1;
      mutationRequestIdRef.current += 1;
      setLibraryLoading(false);
      setLibraryRefreshing(false);
      setDetailLoading(false);
      setMutation(null);
      setRevisionOpen(false);
      setCorrectionOpen(false);
      setCorrectionReason("");
      setCorrectionReasonError("");
      setCorrectionConflict(null);
      setActionError("");
      setAuthorityError("Your publication library access for this organization is no longer available.");
   }, []);

   useEffect(() => {
      mountedRef.current = true;
      return () => {
         mountedRef.current = false;
         authorityGenerationRef.current += 1;
         libraryRequestIdRef.current += 1;
         detailRequestIdRef.current += 1;
         mutationRequestIdRef.current += 1;
      };
   }, []);

   useEffect(() => {
      if (initialPublicationId) {
         onInitialPublicationConsumed?.();
      }
   }, [initialPublicationId, onInitialPublicationConsumed]);

   useEffect(() => {
      selectedPublicationIdRef.current = selectedPublicationId;
      if (focusLibraryAfterReturnRef.current && !selectedPublicationId) {
         focusLibraryAfterReturnRef.current = false;
         libraryHeadingRef.current?.focus();
      }
   }, [selectedPublicationId]);

   useEffect(() => {
      if (revisionOpen) {
         requestAnimationFrame(() => revisionReasonRef.current?.focus());
      }
   }, [revisionOpen]);

   useEffect(() => {
      if (correctionOpen) {
         requestAnimationFrame(() => correctionReasonRef.current?.focus());
      }
   }, [correctionOpen]);

   useEffect(() => {
      if (!correctionOpen || !correctionReason.trim()) {
         return undefined;
      }
      const warnBeforeUnload = (event) => {
         event.preventDefault();
         event.returnValue = "";
      };
      window.addEventListener("beforeunload", warnBeforeUnload);
      return () => window.removeEventListener("beforeunload", warnBeforeUnload);
   }, [correctionOpen, correctionReason]);

   useEffect(() => {
      if ((actionError || authorityError) && !revisionOpen && !correctionOpen) {
         requestAnimationFrame(() => messageRef.current?.focus());
      }
   }, [actionError, authorityError, correctionOpen, revisionOpen]);

   useEffect(() => {
      let cancelled = false;
      const requestId = libraryRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      libraryRequestIdRef.current = requestId;

      if (!hasLoadedLibraryRef.current) {
         setLibraryLoading(true);
      } else {
         setLibraryRefreshing(true);
      }

      authFetch(libraryUrl, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               libraryRequestIdRef.current !== requestId ||
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

            hasLoadedLibraryRef.current = true;
            setLibrary({
               count,
               limit: Number(data?.limit ?? PAGE_SIZE),
               offset: Number(data?.offset ?? offset),
               results,
            });
            setLibraryError("");
            setLibraryLoading(false);
            setLibraryRefreshing(false);
         })
         .catch((error) => {
            if (
               cancelled ||
               !mountedRef.current ||
               libraryRequestIdRef.current !== requestId ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }
            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }
            setLibraryError(error?.message || "Unable to load this organization's publication library.");
            setLibraryLoading(false);
            setLibraryRefreshing(false);
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, libraryRequestVersion, libraryUrl, offset, revokeAuthority]);

   useEffect(() => {
      if (!selectedPublicationId) {
         return undefined;
      }

      let cancelled = false;
      const requestId = detailRequestIdRef.current + 1;
      const authorityGeneration = authorityGenerationRef.current;
      const requestedPublicationId = selectedPublicationId;
      detailRequestIdRef.current = requestId;
      setDetailLoading(true);
      setDetailError("");

      const query = new URLSearchParams({ organization_id: organizationId });
      const url = `${resolveApiEndpoint("PUBLICATION_LIBRARY_DETAIL", requestedPublicationId)}?${query.toString()}`;

      authFetch(url, { method: "GET" })
         .then((data) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== requestId ||
               String(selectedPublicationIdRef.current) !== String(requestedPublicationId) ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }
            setDetail(data);
            setDetailError("");
            setDetailLoading(false);
            if (focusDetailAfterLoadRef.current && window.matchMedia("(max-width: 920px)").matches) {
               requestAnimationFrame(() => detailHeadingRef.current?.focus());
            }
            focusDetailAfterLoadRef.current = false;
         })
         .catch((error) => {
            if (
               cancelled ||
               !mountedRef.current ||
               detailRequestIdRef.current !== requestId ||
               String(selectedPublicationIdRef.current) !== String(requestedPublicationId) ||
               authorityGenerationRef.current !== authorityGeneration
            ) {
               return;
            }
            if (error?.status === 401 || error?.status === 403) {
               revokeAuthority();
               return;
            }
            setDetail(null);
            setDetailLoading(false);
            setDetailError(
               error?.status === 404
                  ? "This publication is no longer available in the organization library."
                  : error?.message || "Unable to load this publication.",
            );
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, detailRequestVersion, organizationId, revokeAuthority, selectedPublicationId]);

   const refreshLibrary = () => {
      setLibraryRefreshing(true);
      setLibraryRequestVersion((current) => current + 1);
   };

   const handleSearch = (event) => {
      event.preventDefault();
      const nextSearch = searchInput.trim();
      setOffset(0);
      if (nextSearch === search && offset === 0) {
         refreshLibrary();
      } else {
         setSearch(nextSearch);
      }
   };

   const clearSearch = () => {
      setSearchInput("");
      setOffset(0);
      if (!search && offset === 0) {
         refreshLibrary();
      } else {
         setSearch("");
      }
   };

   const selectPublication = (publicationId) => {
      if (
         mutation ||
         !publicationId ||
         String(publicationId) === String(selectedPublicationIdRef.current)
      ) {
         return;
      }
      if (correctionOpen && correctionReason.trim() && !window.confirm("Discard the factual-correction reason and open another publication?")) {
         return;
      }
      detailRequestIdRef.current += 1;
      selectedPublicationIdRef.current = String(publicationId);
      setSelectedPublicationId(String(publicationId));
      setDetail(null);
      setDetailError("");
      setRevisionOpen(false);
      setRevisionReason("");
      setCorrectionOpen(false);
      setCorrectionReason("");
      setCorrectionReasonError("");
      setCorrectionConflict(null);
      setActionError("");
      focusDetailAfterLoadRef.current = true;
   };

   const returnToLibrary = () => {
      if (mutation) {
         return;
      }
      if (correctionOpen && correctionReason.trim() && !window.confirm("Discard the factual-correction reason and return to the publication list?")) {
         return;
      }

      detailRequestIdRef.current += 1;
      selectedPublicationIdRef.current = null;
      setSelectedPublicationId(null);
      setDetail(null);
      setDetailError("");
      setRevisionOpen(false);
      setRevisionReason("");
      setCorrectionOpen(false);
      setCorrectionReason("");
      setCorrectionReasonError("");
      setCorrectionConflict(null);
      setActionError("");
      focusLibraryAfterReturnRef.current = true;
   };

   const closeRevisionForm = () => {
      setRevisionOpen(false);
      setRevisionReason("");
      setActionError("");
      requestAnimationFrame(() => createRevisionButtonRef.current?.focus());
   };

   const closeCorrectionForm = () => {
      if (correctionReason.trim() && !window.confirm("Discard the factual-correction reason you entered?")) {
         return;
      }
      setCorrectionOpen(false);
      setCorrectionReason("");
      setCorrectionReasonError("");
      setCorrectionConflict(null);
      setActionError("");
      requestAnimationFrame(() => requestCorrectionButtonRef.current?.focus());
   };

   const handleRequestCorrection = async (event) => {
      event.preventDefault();
      const reason = correctionReason.trim();
      if (!reason) {
         setCorrectionReasonError("A correction reason is required.");
         requestAnimationFrame(() => correctionReasonRef.current?.focus());
         return;
      }
      if (reason.length > 2000) {
         setCorrectionReasonError("Correction reason must be 2000 characters or fewer.");
         requestAnimationFrame(() => correctionReasonRef.current?.focus());
         return;
      }
      if (mutation || !canRequestCorrection || !detail || !correctionWorkflow) {
         return;
      }

      const operation = {
         authIdentity,
         organizationId,
         publicationId: selectedPublicationIdRef.current,
         authorityGeneration: authorityGenerationRef.current,
         requestId: mutationRequestIdRef.current + 1,
      };
      mutationRequestIdRef.current = operation.requestId;
      setMutation("request-correction");
      setCorrectionReasonError("");
      setCorrectionConflict(null);
      setActionError("");

      const isOperationCurrent = () =>
         mountedRef.current &&
         mutationRequestIdRef.current === operation.requestId &&
         authorityGenerationRef.current === operation.authorityGeneration &&
         operation.authIdentity === authIdentity &&
         String(operation.organizationId) === String(organizationId) &&
         String(selectedPublicationIdRef.current) === String(operation.publicationId);

      try {
         const created = await authFetch(resolveApiEndpoint("FACTUAL_CORRECTION_REQUEST", operation.publicationId), {
            method: "POST",
            body: {
               organization_id: operation.organizationId,
               expected_predecessor_version: correctionWorkflow.concurrency?.expected_predecessor_version,
               expected_decision_revision: correctionWorkflow.concurrency?.expected_decision_revision,
               correction_reason: reason,
            },
         });
         if (!isOperationCurrent()) {
            return;
         }

         const correctionRequestId = created?.request?.id;
         setCorrectionOpen(false);
         setCorrectionReason("");
         setCorrectionConflict(null);
         refreshLibrary();
         if (correctionRequestId) {
            onCorrectionOpened?.(String(correctionRequestId));
         } else {
            setActionError("The correction was created, but its request identifier was not returned.");
            setDetailRequestVersion((current) => current + 1);
         }
      } catch (error) {
         if (!isOperationCurrent()) {
            return;
         }
         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority();
            return;
         }
         if (error?.status === 400) {
            const reasonErrors = error?.errors?.correction_reason;
            const validationDetails = Object.entries(error?.errors || {})
               .map(([name, value]) => `${formatLabel(name)}: ${Array.isArray(value) ? value.join(" ") : String(value)}`)
               .join(" ");
            if (reasonErrors) {
               setCorrectionReasonError(Array.isArray(reasonErrors) ? reasonErrors.join(" ") : String(reasonErrors));
               requestAnimationFrame(() => correctionReasonRef.current?.focus());
            } else {
               setActionError(
                  `${error?.code || "INVALID_INPUT"}: ${validationDetails || error?.message || "Review the request and try again."}`,
               );
            }
            return;
         }
         if (error?.status === 409) {
            setCorrectionConflict({
               code: error?.code || "CONFLICT",
               detail: error?.message || "The publication changed before the correction request was created.",
               blockers: error?.blockers,
               current: error?.current,
            });
            setActionError(
               `${error?.code || "CONFLICT"}: ${error?.message || "The publication changed before the correction request was created."} The correction reason is preserved; review the refreshed server state before submitting again.`,
            );
            refreshLibrary();
            setDetailRequestVersion((current) => current + 1);
            return;
         }
         if (error?.status === 404) {
            setActionError("This publication is no longer available in the selected organization.");
            refreshLibrary();
            setDetailRequestVersion((current) => current + 1);
            return;
         }
         setActionError(error?.message || "Unable to request this factual correction.");
      } finally {
         if (mountedRef.current && mutationRequestIdRef.current === operation.requestId) {
            setMutation(null);
         }
      }
   };

   const handleCreateRevision = async (event) => {
      event.preventDefault();
      const reason = revisionReason.trim();
      if (!reason) {
         setActionError("A revision reason is required.");
         return;
      }
      if (reason.length > 2000) {
         setActionError("Revision reason must be 2000 characters or fewer.");
         return;
      }
      if (mutation || !canCreateRevision || !detail) {
         return;
      }

      const operation = {
         authIdentity,
         organizationId,
         publicationId: selectedPublicationIdRef.current,
         authorityGeneration: authorityGenerationRef.current,
         requestId: mutationRequestIdRef.current + 1,
      };
      mutationRequestIdRef.current = operation.requestId;
      setMutation("create-revision");
      setActionError("");

      const isOperationCurrent = () =>
         mountedRef.current &&
         mutationRequestIdRef.current === operation.requestId &&
         authorityGenerationRef.current === operation.authorityGeneration &&
         operation.authIdentity === authIdentity &&
         String(operation.organizationId) === String(organizationId) &&
         String(selectedPublicationIdRef.current) === String(operation.publicationId);

      try {
         const created = await authFetch(
            resolveApiEndpoint("EDITORIAL_REVISION_DRAFT_CREATE", operation.publicationId),
            {
               method: "POST",
               body: {
                  organization_id: operation.organizationId,
                  expected_predecessor_version: detail.concurrency?.predecessor_version,
                  expected_decision_revision: detail.concurrency?.decision_revision,
                  revision_reason: reason,
               },
            },
         );

         if (!isOperationCurrent()) {
            return;
         }

         setRevisionOpen(false);
         setRevisionReason("");
         showWorkspaceSuccess(addToast, {
            title: "Editorial revision created",
            message: "Opening the revision in Drafting.",
         });
         refreshLibrary();
         onRevisionCreated?.(created);
      } catch (error) {
         if (!isOperationCurrent()) {
            return;
         }
         if (error?.status === 401 || error?.status === 403) {
            revokeAuthority();
            return;
         }
         if (error?.status === 409) {
            setActionError(
               `${error?.code || "CONFLICT"}: ${
                  error?.message || "The publication changed before the revision could be created."
               } Your revision reason is preserved; review the refreshed server state before trying again.`,
            );
            refreshLibrary();
            setDetailRequestVersion((current) => current + 1);
            return;
         }
         if (error?.status === 404) {
            setActionError("This publication is no longer available for editorial revision.");
            refreshLibrary();
            setDetailRequestVersion((current) => current + 1);
            return;
         }
         setActionError(error?.message || "Unable to create this editorial revision.");
      } finally {
         if (mountedRef.current && mutationRequestIdRef.current === operation.requestId) {
            setMutation(null);
         }
      }
   };

   const retryAuthority = () => {
      authorityGenerationRef.current += 1;
      setAuthorityError("");
      setLibraryError("");
      setLibraryRequestVersion((current) => current + 1);
      if (selectedPublicationId) {
         setDetailRequestVersion((current) => current + 1);
      }
   };

   const pageStart = library.count === 0 ? 0 : library.offset + 1;
   const pageEnd = Math.min(library.offset + library.results.length, library.count);
   const hasPrevious = offset > 0;
   const hasNext = offset + library.limit < library.count;

   return (
      <div className="publications-panel">
         <div className="publications-boundary-note">
            <Icons name="book-open" size={18} />
            <p>
               This is {organizationName ? `${organizationName}'s` : "the selected organization's"} internal
               publication library. Human decisions, sealed evidence, and published article versions remain distinct
               and historically inspectable.
            </p>
         </div>

         <div ref={messageRef} className="publications-messages" tabIndex={-1} aria-live="polite">
            {authorityError ? (
               <div className="publications-message publications-message--critical" role="alert">
                  <Icons name="lock" size={18} />
                  <div>
                     <strong>Publication library access unavailable</strong>
                     <p>{authorityError}</p>
                     <Button type="button" variant="secondary" density="compact" onClick={retryAuthority}>
                        Retry access
                     </Button>
                  </div>
               </div>
            ) : null}
            {actionError ? (
               <div className="publications-message publications-message--critical" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{actionError}</p>
               </div>
            ) : null}
         </div>

         {authorityError ? null : (
            <div className={`publications-workbench ${selectedPublicationId ? "has-selection" : ""}`}>
               <section className="publications-library" aria-labelledby="publications-library-heading">
                  <div className="publications-library-header">
                     <div>
                        <h3 id="publications-library-heading" ref={libraryHeadingRef} tabIndex={-1}>
                           Current publications
                        </h3>
                        <p>
                           {library.count} institutional publication{library.count === 1 ? "" : "s"}
                        </p>
                     </div>
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        leadingIcon={<Icons name="refresh-cw" size={15} />}
                        loading={libraryRefreshing}
                        loadingLabel="Refreshing…"
                        onClick={refreshLibrary}
                     >
                        Refresh
                     </Button>
                  </div>

                  <form className="publications-search" role="search" onSubmit={handleSearch}>
                     <label htmlFor="publications-search-input">Search publications</label>
                     <div className="publications-search-controls">
                        <Input
                           id="publications-search-input"
                           type="search"
                           maxLength={120}
                           value={searchInput}
                           placeholder="Search headline, claim, summary, or article"
                           leadingIcon={<Icons name="search" size={16} />}
                           onChange={(event) => setSearchInput(event.target.value)}
                        />
                        <Button type="submit" variant="primary" density="compact" disabled={libraryRefreshing}>
                           Search
                        </Button>
                        {(searchInput || search) && (
                           <Button
                              type="button"
                              variant="ghost"
                              density="compact"
                              disabled={libraryRefreshing}
                              onClick={clearSearch}
                           >
                              Clear search
                           </Button>
                        )}
                     </div>
                     {search ? <p>Showing results for “{search}”.</p> : null}
                  </form>

                  {libraryLoading ? (
                     <div className="publications-state" role="status">
                        <Icons name="loader" size={22} className="publications-spinner" />
                        <strong>Loading publications…</strong>
                     </div>
                  ) : libraryError && library.results.length === 0 ? (
                     <div className="publications-state publications-state--error" role="alert">
                        <Icons name="alert-circle" size={22} />
                        <strong>Publication library unavailable</strong>
                        <p>{libraryError}</p>
                        <Button type="button" variant="secondary" density="compact" onClick={refreshLibrary}>
                           Try again
                        </Button>
                     </div>
                  ) : library.results.length === 0 ? (
                     <div className="publications-state">
                        <Icons name={search ? "search" : "book-open"} size={24} />
                        <strong>{search ? "No matching publications" : "No publications yet"}</strong>
                        <p>
                           {search
                              ? "Try a different headline, claim, summary, or article search."
                              : "Current institutional publications will appear here after publication."}
                        </p>
                        {search ? (
                           <Button type="button" variant="secondary" density="compact" onClick={clearSearch}>
                              Clear search
                           </Button>
                        ) : null}
                     </div>
                  ) : (
                     <>
                        {libraryError ? (
                           <div className="publications-list-warning" role="alert">
                              {libraryError} Existing results remain available.
                           </div>
                        ) : null}
                        <ul className="publications-list">
                           {library.results.map((item) => {
                              const selected =
                                 String(item.publication_id) === String(selectedPublicationId);
                              return (
                                 <li key={item.publication_id}>
                                    <button
                                       type="button"
                                       className={`publications-list-row ${selected ? "is-selected" : ""}`}
                                       aria-current={selected ? "true" : undefined}
                                       disabled={Boolean(mutation)}
                                       onClick={() => selectPublication(item.publication_id)}
                                    >
                                       <span className="publications-row-topline">
                                          <span>Article v{item.version}</span>
                                          <VerdictBadge verdict={item.verdict} />
                                       </span>
                                       <strong>{item.headline || "Untitled publication"}</strong>
                                       <span className="publications-row-claim">
                                          {item.claim?.canonical_claim || "Claim text unavailable"}
                                       </span>
                                       <span className="publications-row-metadata">
                                          {formatLabel(item.revision_kind)} · {formatDateTime(item.published_at)}
                                       </span>
                                       <span className="publications-row-metadata">
                                          Published by {actorName(item.published_by)}
                                       </span>
                                       <span className="publications-row-status">
                                          <RecordStateBadge recordState={item.record_state} />
                                          {item.lineage?.previous_versions_count > 0 ? (
                                             <span>
                                                {item.lineage.previous_versions_count} previous version
                                                {item.lineage.previous_versions_count === 1 ? "" : "s"}
                                             </span>
                                          ) : null}
                                       </span>
                                    </button>
                                 </li>
                              );
                           })}
                        </ul>
                     </>
                  )}

                  {!libraryLoading && library.count > 0 ? (
                     <div className="publications-pagination" aria-label="Publications pagination">
                        <Button
                           type="button"
                           variant="secondary"
                           density="compact"
                           disabled={!hasPrevious || libraryRefreshing}
                           onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                        >
                           Previous
                        </Button>
                        <span>
                           {pageStart}–{pageEnd} of {library.count}
                        </span>
                        <Button
                           type="button"
                           variant="secondary"
                           density="compact"
                           disabled={!hasNext || libraryRefreshing}
                           onClick={() => setOffset(offset + PAGE_SIZE)}
                        >
                           Next
                        </Button>
                     </div>
                  ) : null}
               </section>

               <section className="publications-detail" aria-labelledby="publications-detail-heading">
                  {!selectedPublicationId ? (
                     <div className="publications-state publications-state--detail">
                        <Icons name="book-open" size={25} />
                        <h3 id="publications-detail-heading">Select a publication</h3>
                        <p>Open a current publication to inspect its article, human decision, sources, and history.</p>
                     </div>
                  ) : (
                     <>
                        <Button
                           type="button"
                           variant="ghost"
                           density="compact"
                           className="publications-return-to-library"
                           leadingIcon={<Icons name="arrow-left" size={15} />}
                           disabled={Boolean(mutation)}
                           onClick={returnToLibrary}
                        >
                           Back to publications
                        </Button>

                        {detailLoading && !detail ? (
                           <div className="publications-state" role="status">
                              <Icons name="loader" size={22} className="publications-spinner" />
                              <strong>Loading publication record…</strong>
                           </div>
                        ) : detailError && !detail ? (
                           <div className="publications-state publications-state--error" role="alert">
                              <Icons name="alert-circle" size={22} />
                              <h3 id="publications-detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                                 Unable to load publication
                              </h3>
                              <p>{detailError}</p>
                              <div className="publications-state-actions">
                                 <Button
                                    type="button"
                                    variant="secondary"
                                    density="compact"
                                    onClick={() => setDetailRequestVersion((current) => current + 1)}
                                 >
                                    Try again
                                 </Button>
                                 <Button
                                    type="button"
                                    variant="ghost"
                                    density="compact"
                                    disabled={Boolean(mutation)}
                                    onClick={returnToLibrary}
                                 >
                                    Return to library
                                 </Button>
                              </div>
                           </div>
                        ) : detail ? (
                           <article className="publications-detail-content">
                              <header className="publications-detail-header">
                                 <div>
                                    <span className="publications-history-label">
                                       {formatLabel(detail.history_state, "Publication")}
                                    </span>
                                    <h3 id="publications-detail-heading" ref={detailHeadingRef} tabIndex={-1}>
                                       {detail.article?.headline || "Untitled publication"}
                                    </h3>
                                    <p>{detail.claim?.canonical_claim || "Claim text unavailable"}</p>
                                 </div>
                                 <div className="publications-detail-badges">
                                    <VerdictBadge verdict={detail.decision?.verdict} />
                                    <RecordStateBadge recordState={detail.record_state} />
                                 </div>
                              </header>

                              {detail.history_state === "SUPERSEDED" ? (
                                 <div className="publications-message publications-message--info" role="status">
                                    <Icons name="info" size={18} />
                                    <div>
                                       <strong>Preserved historical publication</strong>
                                       <p>This version has been superseded and remains available for inspection.</p>
                                       <Button
                                          type="button"
                                          variant="secondary"
                                          density="compact"
                                          disabled={Boolean(mutation)}
                                          onClick={() => selectPublication(detail.current_publication_id)}
                                       >
                                          Open current publication
                                       </Button>
                                    </div>
                                 </div>
                              ) : null}

                              <section
                                 className="publications-section publications-article-section"
                                 aria-labelledby="publications-article-heading"
                              >
                                 <div className="publications-section-heading">
                                    <div>
                                       <h4 id="publications-article-heading">Published article</h4>
                                       <p>The institutional article version currently selected from publication history.</p>
                                    </div>
                                 </div>
                                 <dl className="publications-publication-summary">
                                    <div>
                                       <dt>Article version</dt>
                                       <dd>v{detail.article?.version ?? "–"}</dd>
                                    </div>
                                    <div>
                                       <dt>Published by</dt>
                                       <dd>{actorName(detail.published_by)}</dd>
                                    </div>
                                    <div>
                                       <dt>Published</dt>
                                       <dd><FormattedDateTime value={detail.published_at} /></dd>
                                    </div>
                                 </dl>
                                 <div className="publications-article-copy">
                                    <h5>Summary</h5>
                                    <p>{detail.article?.summary || "No summary recorded."}</p>
                                    <h5>Article body</h5>
                                    <div>{detail.article?.article_body || "No article body recorded."}</div>
                                 </div>
                              </section>

                              <HumanDecision detail={detail} />

                              <VersionHistory
                                 lineage={detail.lineage}
                                 selectedPublicationId={detail.selected_publication_id}
                                 disabled={Boolean(mutation)}
                                 onSelect={selectPublication}
                              />

                              <PublicationReferenceMaterial detail={detail} />

                              {(correctionWorkflow || canCreateRevision) ? (
                                 <section
                                    className="publications-maintenance"
                                    aria-labelledby="publications-maintenance-heading"
                                 >
                                    <div className="publications-section-heading">
                                       <div>
                                          <h4 id="publications-maintenance-heading">Publication maintenance</h4>
                                          <p>
                                             Start dedicated follow-up work without changing the currently published
                                             record in place.
                                          </p>
                                       </div>
                                    </div>

                                    {correctionWorkflow ? (
                                       <div className="publications-maintenance-option">
                                          <div>
                                             <strong>Factual correction</strong>
                                             <p>
                                                Use this when the published factual judgment itself may need correction.
                                                Requests and proposals remain non-authoritative until final publication.
                                             </p>
                                          </div>
                                          <div className="publications-maintenance-actions">
                                             {canOpenCorrection && correctionWorkflow.active_request_id ? (
                                                <Button
                                                   type="button"
                                                   variant="primary"
                                                   density="standard"
                                                   leadingIcon={<Icons name="badge-check" size={16} />}
                                                   disabled={Boolean(mutation)}
                                                   onClick={() =>
                                                      onCorrectionOpened?.(String(correctionWorkflow.active_request_id))
                                                   }
                                                >
                                                   Open factual correction
                                                </Button>
                                             ) : null}
                                             {canRequestCorrection ? (
                                                <Button
                                                   ref={requestCorrectionButtonRef}
                                                   type="button"
                                                   variant="secondary"
                                                   density="standard"
                                                   leadingIcon={<Icons name="badge-check" size={16} />}
                                                   disabled={Boolean(mutation)}
                                                   onClick={() => {
                                                      setCorrectionOpen(true);
                                                      setCorrectionReasonError("");
                                                      setCorrectionConflict(null);
                                                      setActionError("");
                                                   }}
                                                >
                                                   Request factual correction
                                                </Button>
                                             ) : null}
                                          </div>
                                          <CorrectionWorkflowBlockers blockers={correctionWorkflow.blockers} />
                                       </div>
                                    ) : null}

                                    {canCreateRevision ? (
                                       <div className="publications-maintenance-option">
                                          <div>
                                             <strong>Editorial revision</strong>
                                             <p>
                                                Use this for non-factual changes to wording, headline, summary, or
                                                editorial citations. The current publication stays live during review.
                                             </p>
                                          </div>
                                          <div className="publications-maintenance-actions">
                                             <Button
                                                ref={createRevisionButtonRef}
                                                type="button"
                                                variant="secondary"
                                                density="standard"
                                                leadingIcon={<Icons name="file-text" size={16} />}
                                                disabled={Boolean(mutation)}
                                                onClick={() => {
                                                   setRevisionOpen(true);
                                                   setActionError("");
                                                }}
                                             >
                                                Create editorial revision
                                             </Button>
                                          </div>
                                          <Blockers blockers={detail.blockers} />
                                       </div>
                                    ) : null}
                                 </section>
                              ) : null}
                           </article>
                        ) : null}
                     </>
                  )}
               </section>
            </div>
         )}

         <PublicationActionDialog
            open={revisionOpen && Boolean(detail)}
            processing={mutation === "create-revision"}
            title="Create an editorial revision?"
            description="Start a new draft for non-factual editorial changes. The current publication remains live and authoritative while the revision is drafted and reviewed."
            onClose={closeRevisionForm}
         >
            {actionError ? (
               <div className="publications-dialog-error" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{actionError}</p>
               </div>
            ) : null}
            <form className="publications-revision-form publications-dialog-form" onSubmit={handleCreateRevision}>
               <div>
                  <label htmlFor="publications-revision-reason">Revision reason</label>
                  <Textarea
                     ref={revisionReasonRef}
                     id="publications-revision-reason"
                     rows={5}
                     maxLength={2000}
                     required
                     value={revisionReason}
                     disabled={Boolean(mutation)}
                     aria-describedby="publications-revision-help publications-revision-count"
                     onChange={(event) => setRevisionReason(event.target.value)}
                  />
                  <div className="publications-revision-field-meta">
                     <span id="publications-revision-help">
                        Describe the editorial clarification. A factual judgment change belongs in the separate
                        factual-correction workflow.
                     </span>
                     <span id="publications-revision-count">{revisionReason.length}/2000</span>
                  </div>
               </div>
               <div className="publications-revision-confirmation">
                  <strong>Create a draft from Article v{detail?.article?.version ?? "–"}?</strong>
                  <p>The current publication stays live while the inherited revision draft is edited and reviewed.</p>
               </div>
               <div className="publications-action-row">
                  <Button
                     type="button"
                     variant="secondary"
                     density="standard"
                     disabled={Boolean(mutation)}
                     onClick={closeRevisionForm}
                  >
                     Cancel
                  </Button>
                  <Button
                     type="submit"
                     variant="primary"
                     density="standard"
                     loading={mutation === "create-revision"}
                     loadingLabel="Creating revision…"
                     disabled={!revisionReason.trim() || Boolean(mutation)}
                  >
                     Create revision and open Drafting
                  </Button>
               </div>
            </form>
         </PublicationActionDialog>

         <PublicationActionDialog
            open={correctionOpen && Boolean(detail)}
            processing={mutation === "request-correction"}
            title="Request a factual correction?"
            description="Open dedicated correction work only when the published factual judgment may need to change. The current decision and publication remain authoritative during review."
            onClose={closeCorrectionForm}
         >
            {actionError ? (
               <div className="publications-dialog-error" role="alert">
                  <Icons name="alert-circle" size={18} />
                  <p>{actionError}</p>
               </div>
            ) : null}
            {correctionConflict ? (
               <div className="publications-correction-conflict" role="alert">
                  <strong>{correctionConflict.code}</strong>
                  <p>
                     {correctionConflict.detail} No mutation was repeated. The server record was refreshed for explicit
                     reconciliation.
                  </p>
                  {Array.isArray(correctionConflict.blockers) && correctionConflict.blockers.length > 0 ? (
                     <ul>
                        {correctionConflict.blockers.map((blocker, index) => (
                           <li key={`${blocker?.code || "blocker"}-${index}`}>
                              <strong>{formatLabel(blocker?.code, "Conflict blocker")}</strong>
                              {blocker?.detail || "The server rejected the stale request."}
                           </li>
                        ))}
                     </ul>
                  ) : null}
               </div>
            ) : null}
            <form className="publications-correction-form publications-dialog-form" onSubmit={handleRequestCorrection}>
               <div>
                  <label htmlFor="publications-correction-reason">Correction reason</label>
                  <Textarea
                     ref={correctionReasonRef}
                     id="publications-correction-reason"
                     rows={5}
                     maxLength={2000}
                     required
                     value={correctionReason}
                     disabled={Boolean(mutation)}
                     invalid={Boolean(correctionReasonError)}
                     aria-describedby="publications-correction-help publications-correction-count publications-correction-error"
                     onChange={(event) => {
                        setCorrectionReason(event.target.value);
                        setCorrectionReasonError("");
                     }}
                  />
                  <div className="publications-revision-field-meta">
                     <span id="publications-correction-help">
                        Explain why the published factual judgment should enter dedicated correction review.
                     </span>
                     <span id="publications-correction-count">{correctionReason.length}/2000</span>
                  </div>
                  <span
                     id="publications-correction-error"
                     className="publications-correction-field-error"
                     role={correctionReasonError ? "alert" : undefined}
                  >
                     {correctionReasonError}
                  </span>
               </div>
               <div className="publications-correction-confirmation">
                  <strong>Request dedicated factual-correction work?</strong>
                  <p>The current human decision and publication remain authoritative while the correction is reviewed.</p>
               </div>
               <div className="publications-action-row">
                  <Button
                     type="button"
                     variant="secondary"
                     density="standard"
                     disabled={Boolean(mutation)}
                     onClick={closeCorrectionForm}
                  >
                     Cancel
                  </Button>
                  <Button
                     type="submit"
                     variant="primary"
                     density="standard"
                     loading={mutation === "request-correction"}
                     loadingLabel="Requesting correction…"
                     disabled={!correctionReason.trim() || Boolean(mutation)}
                  >
                     Request and open correction
                  </Button>
               </div>
            </form>
         </PublicationActionDialog>
      </div>
   );
}

function PublicationsPanel(props) {
   const { authFetch, token, user } = useAuth();
   const authIdentity = getAuthSessionIdentity(user, token);

   return (
      <PublicationsContent
         key={`${props.organizationId}:${authIdentity}`}
         {...props}
         authFetch={authFetch}
         authIdentity={authIdentity}
      />
   );
}

export default PublicationsPanel;
