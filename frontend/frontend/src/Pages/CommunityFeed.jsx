import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";

import Icons from "../components/Icons.jsx";
import { useAuth } from "../hooks/useAuth";
import { useNotification } from "../hooks/useNotification";
import { buildApiUrl, resolveApiEndpoint } from "../utils/api";
import timeAgo from "../utils/timeAgo";
import { getEffectiveVerdict } from "../utils/verdict";

import "./CommunityFeed.css";

const MAX_SAFE_ERROR_LENGTH = 200;
const UNSAFE_ERROR_PATTERN =
   /<[^>]+>|traceback|stack trace|django|internal server error|exception at|request failed with status code|\b(?:valueerror|typeerror|runtimeerror|databaseerror|integrityerror|operationalerror)\b|\bat\s+\S+\s*\([^)]*:\d+:\d+\)/i;

const ASSESSMENT_SOURCES = { ALL: "ALL", HUMAN: "human", AI: "ai" };
const CATEGORIES = { ALL: "ALL", TEXT: "TEXT", IMAGE: "IMAGE", VIDEO: "VIDEO", FILE: "FILE", URL: "URL" };

const CATEGORY_FILTERS = [
   { value: CATEGORIES.ALL, label: "All", icon: null },
   { value: CATEGORIES.TEXT, label: "Text", icon: "file-text" },
   { value: CATEGORIES.IMAGE, label: "Images", icon: "image" },
   { value: CATEGORIES.VIDEO, label: "Video", icon: "play" },
   { value: CATEGORIES.FILE, label: "Files", icon: "paperclip" },
   { value: CATEGORIES.URL, label: "Links", icon: "link" },
];

const ASSESSMENT_FILTERS = [
   { value: ASSESSMENT_SOURCES.ALL, label: "All" },
   { value: ASSESSMENT_SOURCES.HUMAN, label: "Human review" },
   { value: ASSESSMENT_SOURCES.AI, label: "AI analysis" },
];

function getSafeActionMessage(error, fallback) {
   const status = Number(error?.status);
   if (!Number.isInteger(status) || status < 400 || status >= 500) return fallback;

   const candidate = [error?.detail, error?.message]
      .filter((value) => typeof value === "string")
      .map((value) => value.trim())
      .find((value) => value && value.length <= MAX_SAFE_ERROR_LENGTH && !UNSAFE_ERROR_PATTERN.test(value));

   return candidate ? candidate.replace(/\s+/g, " ") : fallback;
}

function normalizeComparableText(value) {
   return typeof value === "string" ? value.trim().replace(/\s+/g, " ").toLocaleLowerCase() : "";
}

function getClaimMediaAlt(claimText) {
   if (!claimText) return "Media attached to this discussion";
   const compactText = claimText.trim().replace(/\s+/g, " ");
   const boundedText = compactText.length > 140 ? `${compactText.slice(0, 137)}...` : compactText;
   return `Media attached to the claim: ${boundedText}`;
}

function moveMenuFocus(event, onClose) {
   const menuItems = Array.from(
      event.currentTarget.querySelectorAll('[role="menuitem"], [role="menuitemradio"]'),
   ).filter((item) => !item.disabled);
   if (!menuItems.length) return;

   const currentIndex = menuItems.indexOf(document.activeElement);
   let nextIndex = currentIndex;

   if (event.key === "ArrowDown") {
      event.preventDefault();
      nextIndex = currentIndex < menuItems.length - 1 ? currentIndex + 1 : 0;
   } else if (event.key === "ArrowUp") {
      event.preventDefault();
      nextIndex = currentIndex > 0 ? currentIndex - 1 : menuItems.length - 1;
   } else if (event.key === "Home") {
      event.preventDefault();
      nextIndex = 0;
   } else if (event.key === "End") {
      event.preventDefault();
      nextIndex = menuItems.length - 1;
   } else if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
   } else {
      return;
   }

   menuItems[nextIndex]?.focus();
}

function FeedSkeleton() {
   return (
      <div className="feed-skeleton-list" aria-hidden="true">
         {[1, 2, 3].map((item) => (
            <div key={item} className="feed-skeleton-card">
               <div className="feed-skeleton-header">
                  <div className="feed-skeleton-avatar" />
                  <div className="feed-skeleton-author">
                     <div className="feed-skeleton-line feed-skeleton-line--name" />
                     <div className="feed-skeleton-line feed-skeleton-line--time" />
                  </div>
               </div>
               <div className="feed-skeleton-content">
                  <div className="feed-skeleton-line" />
                  <div className="feed-skeleton-line feed-skeleton-line--wide" />
                  <div className="feed-skeleton-line feed-skeleton-line--short" />
               </div>
               <div className="feed-skeleton-assessment">
                  <div className="feed-skeleton-line feed-skeleton-line--name" />
                  <div className="feed-skeleton-badge" />
               </div>
            </div>
         ))}
      </div>
   );
}

function VerdictBadge({ verdict }) {
   const verdictClass = String(verdict || "UNVERIFIED").toLocaleLowerCase();
   return <span className={`feed-verdict feed-verdict--${verdictClass}`}>{verdict || "UNVERIFIED"}</span>;
}

function AssessmentSummary({ claim }) {
   const humanVerdict = claim?.human_verdict;
   const verdict = humanVerdict?.verdict || getEffectiveVerdict(claim) || "UNVERIFIED";
   const organization = humanVerdict?.organization;
   const verifiedEvidenceCount = claim?.verified_evidence_count ?? 0;

   if (humanVerdict) {
      const provenanceContent = organization ? (
         <>
            {organization.logo_url && (
               <img
                  className="feed-assessment-logo"
                  src={organization.logo_url}
                  alt={`${organization.name} logo`}
                  loading="lazy"
                  onError={(event) => {
                     event.currentTarget.hidden = true;
                  }}
               />
            )}
            <span>Reviewed by {organization.name}</span>
         </>
      ) : (
         <span>Human review</span>
      );

      return (
         <section className="feed-assessment" aria-label="Human review assessment">
            <div className="feed-assessment-heading">
               {organization?.slug ? (
                  <Link className="feed-provenance-link" to={`/partners/${organization.slug}`}>
                     {provenanceContent}
                  </Link>
               ) : (
                  <div className="feed-provenance">{provenanceContent}</div>
               )}
               <VerdictBadge verdict={verdict} />
            </div>
            <p className="feed-assessment-support">
               {verifiedEvidenceCount} verified evidence {verifiedEvidenceCount === 1 ? "item" : "items"}
            </p>
         </section>
      );
   }

   const confidence = claim?.consensus_score;
   return (
      <section className="feed-assessment" aria-label="AI analysis assessment">
         <div className="feed-assessment-heading">
            <div className="feed-provenance">
               <Icons name="cpu" size={18} aria-hidden="true" />
               <span>AI analysis</span>
            </div>
            <VerdictBadge verdict={verdict} />
         </div>
         <p className="feed-assessment-support feed-assessment-support--confidence">
            {confidence == null ? "Confidence unavailable" : `${confidence}% confidence`}
         </p>
         <p className="feed-assessment-summary">{claim?.ai_summary || "AI summary unavailable."}</p>
      </section>
   );
}

function MediaPreview({ thread, claimText, failed, onError }) {
   const mediaUrl = thread?.claim?.media_url;
   if (!mediaUrl) return null;

   if (failed) {
      return (
         <div className="feed-media-fallback" role="status">
            <Icons name="alert-circle" size={20} aria-hidden="true" />
            <span>Claim media could not be displayed.</span>
         </div>
      );
   }

   if (thread.claim.claim_type === CATEGORIES.VIDEO) {
      return (
         <div className="feed-media">
            <video
               className="feed-media-content"
               src={mediaUrl}
               controls
               preload="metadata"
               aria-label={getClaimMediaAlt(claimText)}
               onError={onError}
            />
         </div>
      );
   }

   return (
      <Link className="feed-media" to={`/thread/detail/${thread.id}`} aria-label="Open discussion media">
         <img
            className="feed-media-content"
            src={mediaUrl}
            alt={getClaimMediaAlt(claimText)}
            loading="lazy"
            onError={onError}
         />
      </Link>
   );
}

function CommunityFeed() {
   const navigate = useNavigate();
   const [searchParams] = useSearchParams();
   const { authFetch, user } = useAuth();
   const { addToast } = useNotification();
   const threadsEndpoint = resolveApiEndpoint("THREADS");

   const [threads, setThreads] = useState([]);
   const [loading, setLoading] = useState(false);
   const [hasMore, setHasMore] = useState(true);
   const [loadError, setLoadError] = useState(null);
   const [currentCursor, setCurrentCursor] = useState(null);
   const [activeAssessmentSource, setActiveAssessmentSource] = useState(ASSESSMENT_SOURCES.ALL);
   const [activeCategoryFilter, setActiveCategoryFilter] = useState(CATEGORIES.ALL);
   const [sortOrder, setSortOrder] = useState("newest");

   const [isAssessmentMenuOpen, setIsAssessmentMenuOpen] = useState(false);
   const [isSortMenuOpen, setIsSortMenuOpen] = useState(false);
   const [openMenuThreadId, setOpenMenuThreadId] = useState(null);
   const [editingThreadId, setEditingThreadId] = useState(null);
   const [editingCaption, setEditingCaption] = useState("");
   const [savingThreadId, setSavingThreadId] = useState(null);
   const [deletingThreadId, setDeletingThreadId] = useState(null);
   const [reportingThreadId, setReportingThreadId] = useState(null);
   const [sharingThreadId, setSharingThreadId] = useState(null);
   const [failedMediaIds, setFailedMediaIds] = useState(() => new Set());
   const [reportDialog, setReportDialog] = useState({ open: false, threadId: null, reason: "OTHER", notes: "" });
   const [deleteDialog, setDeleteDialog] = useState({ open: false, threadId: null, caption: "" });

   const observerTarget = useRef(null);
   const requestedPagesRef = useRef(new Set());
   const requestGenerationRef = useRef(0);
   const assessmentTriggerRef = useRef(null);
   const assessmentMenuRef = useRef(null);
   const sortTriggerRef = useRef(null);
   const sortMenuRef = useRef(null);
   const threadMenuRefs = useRef(new Map());
   const dialogRef = useRef(null);
   const dialogReturnFocusRef = useRef(null);
   const deleteCancelRef = useRef(null);
   const reportReasonRef = useRef(null);
   const mainRef = useRef(null);

   const activeSearchTerm = (searchParams.get("q") || "").trim();
   const threadDetailUrl = (threadId) => `${threadsEndpoint}${threadId}/`;
   const threadFlagsEndpoint = buildApiUrl("thread-flags/");
   const isThreadOwner = (thread) => thread?.author?.id === user?.id;
   const reportActionMeta = {
      code: "REPORT THREAD",
      title: "Report this discussion",
      description: "Submit a report so moderators can investigate this discussion for policy concerns.",
      cta: "Submit report",
   };

   const restoreDialogFocus = useCallback((preferHeading = false) => {
      window.setTimeout(() => {
         const returnTarget = dialogReturnFocusRef.current;
         if (!preferHeading && returnTarget?.isConnected) returnTarget.focus();
         else mainRef.current?.focus();
      }, 0);
   }, []);

   const closeDeleteDialog = useCallback(() => {
      if (deletingThreadId) return;
      setDeleteDialog({ open: false, threadId: null, caption: "" });
      restoreDialogFocus();
   }, [deletingThreadId, restoreDialogFocus]);

   const closeReportDialog = useCallback(() => {
      if (reportingThreadId) return;
      setReportDialog({ open: false, threadId: null, reason: "OTHER", notes: "" });
      restoreDialogFocus();
   }, [reportingThreadId, restoreDialogFocus]);

   const closeSortMenu = useCallback(() => {
      setIsSortMenuOpen(false);
      window.setTimeout(() => sortTriggerRef.current?.focus(), 0);
   }, []);

   const closeAssessmentMenu = useCallback(() => {
      setIsAssessmentMenuOpen(false);
      window.setTimeout(() => assessmentTriggerRef.current?.focus(), 0);
   }, []);

   const closeThreadMenu = useCallback(() => {
      const trigger = threadMenuRefs.current.get(openMenuThreadId);
      setOpenMenuThreadId(null);
      window.setTimeout(() => trigger?.focus(), 0);
   }, [openMenuThreadId]);

   useEffect(() => {
      const handleClickOutside = (event) => {
         if (!event.target.closest(".feed-thread-menu-wrap")) setOpenMenuThreadId(null);
         if (!event.target.closest(".feed-mobile-assessment")) setIsAssessmentMenuOpen(false);
         if (!event.target.closest(".feed-sort")) setIsSortMenuOpen(false);
      };
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
   }, []);

   useEffect(() => {
      if (!isAssessmentMenuOpen) return;
      window.requestAnimationFrame(() =>
         assessmentMenuRef.current?.querySelector('[role="menuitemradio"]')?.focus(),
      );
   }, [isAssessmentMenuOpen]);

   useEffect(() => {
      if (!isSortMenuOpen) return;
      window.requestAnimationFrame(() => sortMenuRef.current?.querySelector('[role="menuitemradio"]')?.focus());
   }, [isSortMenuOpen]);

   useEffect(() => {
      if (!openMenuThreadId) return;
      window.requestAnimationFrame(() => {
         document.querySelector(`#thread-actions-${openMenuThreadId} [role="menuitem"]`)?.focus();
      });
   }, [openMenuThreadId]);

   useEffect(() => {
      if (deleteDialog.open) window.requestAnimationFrame(() => deleteCancelRef.current?.focus());
      else if (reportDialog.open) window.requestAnimationFrame(() => reportReasonRef.current?.focus());
   }, [deleteDialog.open, reportDialog.open]);

   useEffect(() => {
      if (!deleteDialog.open && !reportDialog.open) return;

      const handleDialogKeyDown = (event) => {
         const deleteBusy = deleteDialog.open && Boolean(deletingThreadId);
         const reportBusy = reportDialog.open && Boolean(reportingThreadId);

         if (event.key === "Escape") {
            if (deleteBusy || reportBusy) return;
            event.preventDefault();
            if (deleteDialog.open) closeDeleteDialog();
            if (reportDialog.open) closeReportDialog();
            return;
         }
         if (event.key !== "Tab") return;

         const focusable = Array.from(
            dialogRef.current?.querySelectorAll(
               'button:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
            ) || [],
         );
         if (!focusable.length) {
            event.preventDefault();
            dialogRef.current?.focus();
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

      document.addEventListener("keydown", handleDialogKeyDown);
      return () => document.removeEventListener("keydown", handleDialogKeyDown);
   }, [closeDeleteDialog, closeReportDialog, deleteDialog.open, deletingThreadId, reportDialog.open, reportingThreadId]);

   const startEditThread = (event, thread) => {
      event.stopPropagation();
      setEditingThreadId(thread.id);
      setEditingCaption(thread.caption || "");
      setOpenMenuThreadId(null);
   };

   const cancelEditThread = () => {
      setEditingThreadId(null);
      setEditingCaption("");
   };

   const saveEditThread = async (event, threadId) => {
      event.stopPropagation();
      if (!editingCaption.trim()) {
         addToast({ type: "warning", message: "Community context cannot be empty." });
         return;
      }

      try {
         setSavingThreadId(threadId);
         const updated = await authFetch(threadDetailUrl(threadId), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ caption: editingCaption.trim() }),
         });
         setThreads((currentThreads) =>
            currentThreads.map((thread) =>
               thread.id === threadId
                  ? { ...thread, caption: updated?.caption ?? editingCaption.trim(), status: updated?.status ?? thread.status }
                  : thread,
            ),
         );
         cancelEditThread();
         addToast({ type: "success", message: "Community context updated." });
      } catch (error) {
         addToast({ type: "error", message: getSafeActionMessage(error, "Unable to update this discussion. Please try again.") });
      } finally {
         setSavingThreadId(null);
      }
   };

   const openDeleteDialog = (event, thread) => {
      event.stopPropagation();
      dialogReturnFocusRef.current = threadMenuRefs.current.get(thread.id);
      setDeleteDialog({ open: true, threadId: thread.id, caption: thread.caption || "this discussion" });
      setOpenMenuThreadId(null);
   };

   const confirmDeleteThread = async () => {
      const threadId = deleteDialog.threadId;
      if (!threadId) return;
      try {
         setDeletingThreadId(threadId);
         await authFetch(threadDetailUrl(threadId), { method: "DELETE" });
         setThreads((currentThreads) => currentThreads.filter((thread) => thread.id !== threadId));
         setDeleteDialog({ open: false, threadId: null, caption: "" });
         restoreDialogFocus(true);
         addToast({ type: "success", message: "Discussion deleted." });
      } catch (error) {
         addToast({ type: "error", message: getSafeActionMessage(error, "Unable to delete this discussion. Please try again.") });
      } finally {
         setDeletingThreadId(null);
      }
   };

   const openReportDialog = (event, thread) => {
      event.stopPropagation();
      if (!thread?.id || isThreadOwner(thread)) return;
      dialogReturnFocusRef.current = threadMenuRefs.current.get(thread.id);
      setReportDialog({ open: true, threadId: thread.id, reason: "OTHER", notes: "" });
      setOpenMenuThreadId(null);
   };

   const submitReportThread = async () => {
      const reasonInput = reportDialog.reason?.trim().toUpperCase();
      if (!reportDialog.threadId || !reasonInput) return;
      const allowedReasons = new Set(["INAPPROPRIATE", "SPAM", "HARASSMENT", "OTHER"]);
      if (!allowedReasons.has(reasonInput)) {
         addToast({ type: "error", message: "Choose a valid reason before submitting the report." });
         return;
      }

      try {
         setReportingThreadId(reportDialog.threadId);
         await authFetch(threadFlagsEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: reportDialog.threadId, reason: reasonInput, notes: reportDialog.notes.trim() }),
         });
         addToast({ type: "success", message: "Report submitted for review." });
         setReportDialog({ open: false, threadId: null, reason: "OTHER", notes: "" });
         restoreDialogFocus();
      } catch (error) {
         addToast({ type: "error", message: getSafeActionMessage(error, "Unable to submit this report. Please try again.") });
      } finally {
         setReportingThreadId(null);
      }
   };

   const shareThread = async (event, thread) => {
      event.stopPropagation();
      if (!thread?.id) return;
      const shareUrl = `${window.location.origin}/thread/detail/${thread.id}`;
      const shareText = thread?.caption?.trim() || "View this TruthLens discussion.";

      try {
         setSharingThreadId(thread.id);
         if (navigator.share) {
            await navigator.share({ title: "TruthLens discussion", text: shareText, url: shareUrl });
            addToast({ type: "success", message: "Discussion link shared." });
         } else if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(shareUrl);
            addToast({ type: "success", message: "Discussion link copied to clipboard." });
         } else addToast({ type: "warning", message: "Sharing is not supported in this browser." });
      } catch (error) {
         if (error?.name !== "AbortError") {
            addToast({ type: "error", message: getSafeActionMessage(error, "Unable to share this discussion.") });
         }
      } finally {
         setSharingThreadId(null);
         setOpenMenuThreadId(null);
         window.setTimeout(() => threadMenuRefs.current.get(thread.id)?.focus(), 0);
      }
   };

   const fetchThreadsPage = useCallback(
      async (pageUrl = null, generation = requestGenerationRef.current) => {
         const pageKey = `${generation}:${pageUrl || "FIRST"}`;
         if (requestedPagesRef.current.has(pageKey)) return;

         try {
            requestedPagesRef.current.add(pageKey);
            setLoading(true);
            setLoadError(null);
            let url = pageUrl || threadsEndpoint;
            if (!pageUrl) {
               const query = new URLSearchParams();
               if (activeSearchTerm) query.set("search", activeSearchTerm);
               query.set("sort", sortOrder);
               if (activeAssessmentSource !== ASSESSMENT_SOURCES.ALL) query.set("assessment_source", activeAssessmentSource);
               if (activeCategoryFilter !== CATEGORIES.ALL) query.set("claim_type", activeCategoryFilter);
               url = `${threadsEndpoint}?${query.toString()}`;
            }

            const response = await authFetch(url, { method: "GET" });
            if (generation !== requestGenerationRef.current) return;
            const newThreads = response.results || response || [];
            setThreads((currentThreads) => {
               const existingIds = new Set(currentThreads.map((thread) => thread.id));
               const uniqueIncoming = newThreads.filter((thread) => thread?.id && !existingIds.has(thread.id));
               return [...currentThreads, ...uniqueIncoming];
            });
            setCurrentCursor(response?.next || null);
            setHasMore(Boolean(response?.next));
         } catch (error) {
            if (generation !== requestGenerationRef.current) return;
            requestedPagesRef.current.delete(pageKey);
            console.error("Failed to fetch threads:", error);
            const message = "Unable to load the community feed. Please try again.";
            setLoadError(message);
            addToast({ type: "error", message });
         } finally {
            if (generation === requestGenerationRef.current) setLoading(false);
         }
      },
      [authFetch, addToast, threadsEndpoint, activeSearchTerm, sortOrder, activeAssessmentSource, activeCategoryFilter],
   );

   useEffect(() => {
      const generation = requestGenerationRef.current + 1;
      requestGenerationRef.current = generation;
      requestedPagesRef.current.clear();
      setThreads([]);
      setCurrentCursor(null);
      setHasMore(true);
      fetchThreadsPage(null, generation);
   }, [fetchThreadsPage]);

   useEffect(() => {
      if (
         !("IntersectionObserver" in window) ||
         !observerTarget.current ||
         loading ||
         !hasMore ||
         !currentCursor
      ) {
         return;
      }
      const observer = new IntersectionObserver(
         (entries) => {
            if (entries[0].isIntersecting && !loading && currentCursor) fetchThreadsPage(currentCursor, requestGenerationRef.current);
         },
         { rootMargin: "240px 0px", threshold: 0.01 },
      );
      observer.observe(observerTarget.current);
      return () => observer.disconnect();
   }, [loading, hasMore, currentCursor, fetchThreadsPage]);

   const handleThreadClick = (threadId, tab = null, options = { openEvidenceForm: false }) => {
      const params = new URLSearchParams();
      if (tab) params.set("tab", tab);
      if (options.openEvidenceForm) params.set("openForm", "evidence");
      const query = params.toString();
      const detailPath = `/thread/detail/${threadId}`;
      navigate(query ? `${detailPath}?${query}` : detailPath);
   };

   const selectSortOrder = (value) => {
      setSortOrder(value);
      closeSortMenu();
   };

   const selectAssessmentSource = (value) => {
      setActiveAssessmentSource(value);
      closeAssessmentMenu();
   };

   const markMediaFailed = (threadId) => {
      setFailedMediaIds((currentIds) => new Set(currentIds).add(threadId));
   };

   const retryUrl = threads.length > 0 ? currentCursor : null;

   return (
      <div className="feed-layout">
         <main ref={mainRef} className="feed-container" aria-busy={loading} tabIndex="-1">
            <h1 className="feed-visually-hidden">Community</h1>

            <section className="feed-controls" aria-label="Community feed controls">
               <div className="feed-category-scroll" role="group" aria-label="Filter by claim type">
                  {CATEGORY_FILTERS.map((category) => (
                     <button
                        key={category.value}
                        type="button"
                        className={`feed-category-btn ${activeCategoryFilter === category.value ? "is-selected" : ""}`}
                        onClick={() => setActiveCategoryFilter(category.value)}
                        aria-pressed={activeCategoryFilter === category.value}
                     >
                        {category.icon && <Icons name={category.icon} size={15} aria-hidden="true" />}
                        {category.label}
                     </button>
                  ))}
               </div>

               <div className="feed-filter-row">
                  <div className="feed-assessment-filters" role="group" aria-label="Filter by assessment source">
                     <span className="feed-filter-label" aria-hidden="true">Assessment</span>
                     {ASSESSMENT_FILTERS.map((source) => (
                        <button
                           key={source.value}
                           type="button"
                           className={`feed-filter-btn ${activeAssessmentSource === source.value ? "is-selected" : ""}`}
                           onClick={() => {
                              setIsAssessmentMenuOpen(false);
                              setActiveAssessmentSource(source.value);
                           }}
                           aria-pressed={activeAssessmentSource === source.value}
                        >
                           {source.label}
                        </button>
                     ))}
                  </div>

                  <div className="feed-mobile-assessment">
                     <button
                        ref={assessmentTriggerRef}
                        type="button"
                        className="feed-sort-trigger feed-assessment-trigger"
                        onClick={() => {
                           setIsSortMenuOpen(false);
                           setIsAssessmentMenuOpen((isOpen) => !isOpen);
                        }}
                        aria-haspopup="menu"
                        aria-expanded={isAssessmentMenuOpen}
                        aria-controls="community-assessment-menu"
                     >
                        <span className="feed-control-trigger-label">
                           {activeAssessmentSource === ASSESSMENT_SOURCES.ALL
                              ? "All assessments"
                              : ASSESSMENT_FILTERS.find(
                                   (source) => source.value === activeAssessmentSource,
                                )?.label}
                        </span>
                        <Icons name="chevron-down" size={15} aria-hidden="true" />
                     </button>
                     {isAssessmentMenuOpen && (
                        <div
                           ref={assessmentMenuRef}
                           id="community-assessment-menu"
                           className="feed-popup-menu feed-assessment-menu"
                           role="menu"
                           aria-label="Filter by assessment source"
                           onKeyDown={(event) => moveMenuFocus(event, closeAssessmentMenu)}
                        >
                           {ASSESSMENT_FILTERS.map((source) => (
                              <button
                                 key={source.value}
                                 type="button"
                                 role="menuitemradio"
                                 aria-checked={activeAssessmentSource === source.value}
                                 className="feed-popup-item"
                                 onClick={() => selectAssessmentSource(source.value)}
                              >
                                 {source.value === ASSESSMENT_SOURCES.ALL
                                    ? "All assessments"
                                    : source.label}
                                 {activeAssessmentSource === source.value && (
                                    <Icons name="check" size={15} aria-hidden="true" />
                                 )}
                              </button>
                           ))}
                        </div>
                     )}
                  </div>

                  <div className="feed-sort">
                     <span className="feed-filter-label">Sort</span>
                     <button
                        ref={sortTriggerRef}
                        type="button"
                        className="feed-sort-trigger"
                        onClick={() => {
                           setIsAssessmentMenuOpen(false);
                           setIsSortMenuOpen((isOpen) => !isOpen);
                        }}
                        aria-haspopup="menu"
                        aria-expanded={isSortMenuOpen}
                        aria-controls="community-sort-menu"
                     >
                        <span className="feed-control-trigger-label">
                           {sortOrder === "newest" ? "Newest first" : "Oldest first"}
                        </span>
                        <Icons name="chevron-down" size={15} aria-hidden="true" />
                     </button>
                     {isSortMenuOpen && (
                        <div
                           ref={sortMenuRef}
                           id="community-sort-menu"
                           className="feed-popup-menu feed-sort-menu"
                           role="menu"
                           aria-label="Sort discussions"
                           onKeyDown={(event) => moveMenuFocus(event, closeSortMenu)}
                        >
                           {[
                              ["newest", "Newest first"],
                              ["oldest", "Oldest first"],
                           ].map(([value, label]) => (
                              <button
                                 key={value}
                                 type="button"
                                 role="menuitemradio"
                                 aria-checked={sortOrder === value}
                                 className="feed-popup-item"
                                 onClick={() => selectSortOrder(value)}
                              >
                                 {label}
                                 {sortOrder === value && <Icons name="check" size={15} aria-hidden="true" />}
                              </button>
                           ))}
                        </div>
                     )}
                  </div>
               </div>
            </section>

            {activeSearchTerm && <p className="feed-search-summary">Results for “{activeSearchTerm}”</p>}
            <div className="feed-results-status" role="status" aria-live="polite" aria-atomic="true">
               {loading && threads.length === 0 ? "Loading community discussions." : ""}
            </div>
            {threads.length === 0 && loading && <FeedSkeleton />}
            {loadError && (
               <div className="feed-load-error" role="alert">
                  <span>{loadError}</span>
                  <button
                     type="button"
                     className="feed-retry-btn"
                     onClick={() => fetchThreadsPage(retryUrl, requestGenerationRef.current)}
                     disabled={loading}
                  >
                     Try again
                  </button>
               </div>
            )}

            {threads.length === 0 && !loading && !loadError && (
               <section className="feed-empty" aria-labelledby="feed-empty-title">
                  <Icons name="message-square" size={24} aria-hidden="true" />
                  <h2 id="feed-empty-title">
                     {activeSearchTerm
                        ? `No discussions found for “${activeSearchTerm}”.`
                        : activeAssessmentSource !== ASSESSMENT_SOURCES.ALL || activeCategoryFilter !== CATEGORIES.ALL
                          ? "No discussions match these filters."
                          : "No community discussions yet."}
                  </h2>
                  <p>Try another filter or return later as new claim discussions are added.</p>
               </section>
            )}

            {threads.length > 0 && (
               <div className="feed-posts" aria-label="Community discussions">
                  {threads.map((thread) => {
                     const claimText = thread.claim?.context_text?.trim() || "";
                     const captionText = thread.caption?.trim() || "";
                     const isEditing = editingThreadId === thread.id;
                     const contextsMatch = Boolean(claimText) && normalizeComparableText(claimText) === normalizeComparableText(captionText);
                     const showCommunityContext =
                        isEditing || (Boolean(captionText) && (!claimText || !contextsMatch));
                     const contextLabel = claimText ? "Community context" : "Discussion";
                     const detailPath = `/thread/detail/${thread.id}`;
                     const menuIsOpen = openMenuThreadId === thread.id;

                     return (
                        <article key={thread.id} className="feed-card" aria-label={`Discussion by ${thread.author.username}`}>
                           <header className="feed-card-header">
                              <Link className="feed-author-link" to={`/user/${thread.author.username}`}>
                                 <span className="feed-author-avatar" aria-hidden={!thread.author.avatar_url}>
                                    {thread.author.avatar_url ? (
                                       <img src={thread.author.avatar_url} alt={`${thread.author.username}'s avatar`} loading="lazy" />
                                    ) : (
                                       <Icons name="user" size={19} aria-hidden="true" />
                                    )}
                                 </span>
                                 <span className="feed-author-meta">
                                    <span className="feed-author-name">@{thread.author.username}</span>
                                    <time className="feed-author-time" dateTime={thread.created_at}>{timeAgo(thread.created_at)}</time>
                                 </span>
                              </Link>

                              <div className="feed-thread-menu-wrap">
                                 <button
                                    ref={(node) => {
                                       if (node) threadMenuRefs.current.set(thread.id, node);
                                       else threadMenuRefs.current.delete(thread.id);
                                    }}
                                    type="button"
                                    className="feed-more-btn"
                                    onClick={(event) => {
                                       event.stopPropagation();
                                       setOpenMenuThreadId((currentId) => (currentId === thread.id ? null : thread.id));
                                    }}
                                    aria-label={`More actions for discussion by ${thread.author.username}`}
                                    aria-haspopup="menu"
                                    aria-expanded={menuIsOpen}
                                    aria-controls={`thread-actions-${thread.id}`}
                                 >
                                    <Icons name="more-horizontal" size={20} aria-hidden="true" />
                                 </button>

                                 {menuIsOpen && (
                                    <div
                                       id={`thread-actions-${thread.id}`}
                                       className="feed-popup-menu feed-thread-menu"
                                       role="menu"
                                       aria-label={`Discussion actions for ${thread.author.username}`}
                                       onKeyDown={(event) => moveMenuFocus(event, closeThreadMenu)}
                                    >
                                       {isThreadOwner(thread) ? (
                                          <>
                                             <button type="button" role="menuitem" className="feed-popup-item" onClick={(event) => startEditThread(event, thread)}>
                                                <Icons name="pencil" size={16} aria-hidden="true" /> Edit
                                             </button>
                                             <button type="button" role="menuitem" className="feed-popup-item" onClick={(event) => shareThread(event, thread)} disabled={sharingThreadId === thread.id}>
                                                <Icons name="share-2" size={16} aria-hidden="true" /> {sharingThreadId === thread.id ? "Sharing..." : "Share"}
                                             </button>
                                             <button type="button" role="menuitem" className="feed-popup-item feed-popup-item--danger" onClick={(event) => openDeleteDialog(event, thread)} disabled={deletingThreadId === thread.id}>
                                                <Icons name="trash" size={16} aria-hidden="true" /> Delete
                                             </button>
                                          </>
                                       ) : (
                                          <>
                                             <button type="button" role="menuitem" className="feed-popup-item" onClick={(event) => openReportDialog(event, thread)} disabled={reportingThreadId === thread.id}>
                                                <Icons name="flag" size={16} aria-hidden="true" /> Report
                                             </button>
                                             <button type="button" role="menuitem" className="feed-popup-item" onClick={(event) => shareThread(event, thread)} disabled={sharingThreadId === thread.id}>
                                                <Icons name="share-2" size={16} aria-hidden="true" /> {sharingThreadId === thread.id ? "Sharing..." : "Share"}
                                             </button>
                                          </>
                                       )}
                                    </div>
                                 )}
                              </div>
                           </header>

                           <div className="feed-card-body">
                              {claimText && (
                                 <section className="feed-text-block">
                                    <h2 className="feed-content-label">Claim</h2>
                                    <Link className="feed-claim-link" to={detailPath}>{claimText}</Link>
                                 </section>
                              )}

                              {showCommunityContext && (
                                 <section className="feed-text-block feed-text-block--context">
                                    <h2 className="feed-content-label">{contextLabel}</h2>
                                    {isEditing ? (
                                       <div className="feed-edit-wrap">
                                          <label className="feed-visually-hidden" htmlFor={`edit-caption-${thread.id}`}>Edit community context</label>
                                          <textarea
                                             id={`edit-caption-${thread.id}`}
                                             className="feed-edit-input"
                                             value={editingCaption}
                                             onChange={(event) => setEditingCaption(event.target.value)}
                                             rows={3}
                                             autoFocus
                                          />
                                          <div className="feed-edit-actions">
                                             <button type="button" className="feed-action-btn feed-action-btn--primary" onClick={(event) => saveEditThread(event, thread.id)} disabled={savingThreadId === thread.id}>
                                                {savingThreadId === thread.id ? "Saving..." : "Save"}
                                             </button>
                                             <button type="button" className="feed-action-btn" onClick={cancelEditThread} disabled={savingThreadId === thread.id}>Cancel</button>
                                          </div>
                                       </div>
                                    ) : (
                                       <Link className="feed-context-link" to={detailPath}>{captionText}</Link>
                                    )}
                                 </section>
                              )}

                              <MediaPreview thread={thread} claimText={claimText} failed={failedMediaIds.has(thread.id)} onError={() => markMediaFailed(thread.id)} />

                              <AssessmentSummary claim={thread.claim} />
                           </div>

                           <footer className="feed-card-actions" aria-label="Community activity">
                              <button type="button" className="feed-card-action" onClick={() => handleThreadClick(thread.id, "comments")}>
                                 <Icons name="message-square" size={18} aria-hidden="true" />
                                 <span>Comment</span>
                                 <span className="feed-count" aria-label={`${thread.comment_count} comments`}>{thread.comment_count}</span>
                              </button>
                              <button type="button" className="feed-card-action feed-card-action--primary" onClick={() => handleThreadClick(thread.id, "evidence", { openEvidenceForm: true })}>
                                 <Icons name="circle-plus" size={18} aria-hidden="true" /> <span>Add Evidence</span>
                              </button>
                              <button type="button" className="feed-card-action" onClick={() => handleThreadClick(thread.id, "evidence")}>
                                 <Icons name="paperclip" size={18} aria-hidden="true" />
                                 <span className="feed-evidence-label-desktop">Evidence submissions</span>
                                 <span className="feed-evidence-label-mobile">Evidence</span>
                                 <span className="feed-count" aria-label={`${thread.evidence_count} evidence submissions`}>{thread.evidence_count}</span>
                              </button>
                           </footer>
                        </article>
                     );
                  })}

                  {hasMore && currentCursor && (
                     <div className="feed-pagination">
                        <button type="button" className="feed-load-more" onClick={() => fetchThreadsPage(currentCursor, requestGenerationRef.current)} disabled={loading}>
                           {loading ? "Loading more..." : "Load more"}
                        </button>
                        <div className="feed-pagination-status" role="status" aria-live="polite">
                           {loading ? "Loading more discussions." : "More discussions are available."}
                        </div>
                        <div ref={observerTarget} className="feed-load-sentinel" aria-hidden="true" />
                     </div>
                  )}
                  {!hasMore && <p className="feed-end-message" role="status">You’ve reached the end of the community feed.</p>}
               </div>
            )}

            {deleteDialog.open && (
               <div className="feed-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeDeleteDialog()}>
                  <div ref={dialogRef} className="feed-modal" role="dialog" aria-modal="true" aria-labelledby="delete-dialog-title" aria-describedby="delete-dialog-description" tabIndex="-1">
                     <h2 id="delete-dialog-title" className="feed-modal-title">Delete discussion?</h2>
                     <p id="delete-dialog-description" className="feed-modal-text">This removes the community discussion. The action cannot be undone.</p>
                     <div className="feed-modal-actions">
                        <button ref={deleteCancelRef} type="button" className="feed-modal-btn" onClick={closeDeleteDialog} disabled={Boolean(deletingThreadId)}>Cancel</button>
                        <button type="button" className="feed-modal-btn feed-modal-btn--danger" onClick={confirmDeleteThread} disabled={Boolean(deletingThreadId)}>
                           {deletingThreadId ? "Deleting..." : "Delete discussion"}
                        </button>
                     </div>
                  </div>
               </div>
            )}

            {reportDialog.open && (
               <div className="feed-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && closeReportDialog()}>
                  <div ref={dialogRef} className="feed-modal" role="dialog" aria-modal="true" aria-labelledby="report-dialog-title" aria-describedby="report-dialog-description" tabIndex="-1">
                     <span className="feed-modal-label-text">{reportActionMeta.code}</span>
                     <h2 id="report-dialog-title" className="feed-modal-title">{reportActionMeta.title}</h2>
                     <p id="report-dialog-description" className="feed-modal-text">{reportActionMeta.description}</p>
                     <div className="feed-modal-field">
                        <label htmlFor="report-reason">Reason</label>
                        <select
                           ref={reportReasonRef}
                           id="report-reason"
                           className="feed-modal-select"
                           value={reportDialog.reason}
                           onChange={(event) => setReportDialog((currentDialog) => ({ ...currentDialog, reason: event.target.value }))}
                           disabled={Boolean(reportingThreadId)}
                        >
                           <option value="INAPPROPRIATE">Inappropriate</option>
                           <option value="SPAM">Spam</option>
                           <option value="HARASSMENT">Harassment</option>
                           <option value="OTHER">Other</option>
                        </select>
                     </div>
                     <div className="feed-modal-field">
                        <label htmlFor="report-notes">Notes (optional)</label>
                        <textarea
                           id="report-notes"
                           className="feed-modal-textarea"
                           rows={4}
                           value={reportDialog.notes}
                           onChange={(event) => setReportDialog((currentDialog) => ({ ...currentDialog, notes: event.target.value }))}
                           disabled={Boolean(reportingThreadId)}
                        />
                     </div>
                     <div className="feed-modal-actions">
                        <button type="button" className="feed-modal-btn" onClick={closeReportDialog} disabled={Boolean(reportingThreadId)}>Cancel</button>
                        <button type="button" className="feed-modal-btn feed-modal-btn--warning" onClick={submitReportThread} disabled={Boolean(reportingThreadId)}>
                           {reportingThreadId ? "Submitting..." : reportActionMeta.cta}
                        </button>
                     </div>
                  </div>
               </div>
            )}
         </main>
      </div>
   );
}

export default CommunityFeed;
