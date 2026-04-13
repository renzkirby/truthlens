   /**
    * Community Feed Page
    * ══════════════════════════════════════════════════════════════════
    * Displays all community threads (flagged/escalated claims).
    * Users can explore claims, read verdicts, and engage in discussion.
    *
    * Features:
    *   - Browse all community threads
    *   - Filter by status (trending, verified, needs evidence)
    *   - View verdict status and evidence
    *   - Navigate to thread details
    *
    * State Management:
    *   - Custom hook (useFetchThreads) handles data fetching
    *   - Verdict utilities for consistent display
    *   - Centralized constants for configurations
    */

   import { useNavigate } from "react-router-dom";
   import { useAuth } from "../context/AuthContext.jsx";
   import { useEffect, useState, useRef, useCallback } from "react";
   import { useNotification } from "../context/NotificationContext";
   import NavigationBar from "../components/NavigationBar.jsx";
   import Icons from "../components/Icons.jsx";

   // ── Utilities & Hooks ──
   import timeAgo from "../utils/timeAgo";
   import { getEffectiveVerdict } from "../utils/verdict";
   import { buildApiUrl, useEndpoint } from "../utils/api";

   // ── Styles ──
   import "./CommunityFeed.css";

   /**
    * Get user-friendly action text based on claim verdict status
    * @param {string} verdict - Verdict value (FACT, FAKE, etc.)
    * @returns {string} Action text describing what to do next
    */
   function getActionText(verdict) {
      if (!verdict || verdict === "UNVERIFIED") return "Needs Evidence";
      if (verdict === "FACT" || verdict === "FAKE") return "Verified";
      return "Pending";
   }

   const FEED_FILTERS = {
      TRENDING: "TRENDING",
      VERIFIED: "VERIFIED",
      NEEDS_EVIDENCE: "NEEDS_EVIDENCE",
   };

   /**
    * CommunityFeed Component
    * Shows browsable feed of community-escalated claims with infinite scroll
    */
   function CommunityFeed() {
      const navigate = useNavigate();
      const { authFetch, user } = useAuth();
      const { addToast } = useNotification();
      const threadsEndpoint = useEndpoint("THREADS");

      // ── Infinite Scroll State ──
      const [threads, setThreads] = useState([]);
      const [loading, setLoading] = useState(false);
      const [hasMore, setHasMore] = useState(true);
      const [error, setError] = useState(null);
      const [currentCursor, setCurrentCursor] = useState(null);
      const [activeFilter, setActiveFilter] = useState(FEED_FILTERS.TRENDING);
      const observerTarget = useRef(null);
      const requestedPagesRef = useRef(new Set());

      // ── UI State for thread actions (menus, editing) ──
      const [openMenuThreadId, setOpenMenuThreadId] = useState(null);
      const [editingThreadId, setEditingThreadId] = useState(null);
      const [editingCaption, setEditingCaption] = useState("");
      const [savingThreadId, setSavingThreadId] = useState(null);
      const [deletingThreadId, setDeletingThreadId] = useState(null);
      const [reportingThreadId, setReportingThreadId] = useState(null);
      const [sharingThreadId, setSharingThreadId] = useState(null);
      const [reportDialog, setReportDialog] = useState({
         open: false,
         threadId: null,
         reason: "OTHER",
         notes: "",
      });
      const [deleteDialog, setDeleteDialog] = useState({
         open: false,
         threadId: null,
         caption: "",
      });

      const isThreadOwner = (thread) => thread?.author?.id === user?.id;

      const threadDetailUrl = (threadId) => `${threadsEndpoint}${threadId}/`;
      const threadFlagsEndpoint = buildApiUrl("thread-flags/");
      const reportActionMeta = {
         code: "REPORT THREAD",
         title: "Policy Action: Report Thread",
         description: "Submit a report so moderators can investigate this thread for policy concerns.",
         cta: "Submit Report",
      };

      const toggleThreadMenu = (e, threadId) => {
         e.stopPropagation();
         setOpenMenuThreadId((prev) => (prev === threadId ? null : threadId));
      };

      // Close thread action menu when clicking outside
      useEffect(() => {
         const handleClickOutside = (event) => {
            if (!event.target.closest(".thread-actions-menu-wrap")) {
               setOpenMenuThreadId(null);
            }
         };

         document.addEventListener("mousedown", handleClickOutside);
         return () => document.removeEventListener("mousedown", handleClickOutside);
      }, []);

      // Edit thread handlers
      const startEditThread = (e, thread) => {
         e.stopPropagation();
         setEditingThreadId(thread.id);
         setEditingCaption(thread.caption || "");
         setOpenMenuThreadId(null);
      };

      const cancelEditThread = () => {
         setEditingThreadId(null);
         setEditingCaption("");
      };

      const saveEditThread = async (e, threadId) => {
         e.stopPropagation();
         if (!editingCaption.trim()) {
            addToast({ type: "warning", message: "Thread caption cannot be empty." });
            return;
         }

         try {
            setSavingThreadId(threadId);

            const updated = await authFetch(threadDetailUrl(threadId), {
               method: "PATCH",
               headers: { "Content-Type": "application/json" },
               body: JSON.stringify({ caption: editingCaption.trim() }),
            });

            setThreads((prev) =>
               prev.map((thread) => (thread.id === threadId ? { ...thread, ...updated } : thread)),
            );
            cancelEditThread();
            addToast({ type: "success", message: "Thread updated successfully." });
         } catch (err) {
            const message = err?.message || "Failed to update thread.";
            setError(message);
            addToast({ type: "error", message });
         } finally {
            setSavingThreadId(null);
         }
      };

      const openDeleteDialog = (e, thread) => {
         e.stopPropagation();
         setDeleteDialog({
            open: true,
            threadId: thread.id,
            caption: thread.caption || "this thread",
         });
         setOpenMenuThreadId(null);
      };

      const closeDeleteDialog = () => {
         setDeleteDialog({ open: false, threadId: null, caption: "" });
      };

      const openReportDialog = (e, thread) => {
         e.stopPropagation();
         if (!thread?.id || isThreadOwner(thread)) return;

         setReportDialog({
            open: true,
            threadId: thread.id,
            reason: "OTHER",
            notes: "",
         });
         setOpenMenuThreadId(null);
      };

      const closeReportDialog = () => {
         if (reportingThreadId) return;
         setReportDialog({
            open: false,
            threadId: null,
            reason: "OTHER",
            notes: "",
         });
      };

      const submitReportThread = async () => {
         const reasonInput = reportDialog.reason?.trim().toUpperCase();
         if (!reportDialog.threadId || !reasonInput) return;

         const allowedReasons = new Set(["INAPPROPRIATE", "SPAM", "HARASSMENT", "OTHER"]);
         if (!allowedReasons.has(reasonInput)) {
            addToast({
               type: "error",
               message: "Invalid reason. Use INAPPROPRIATE, SPAM, HARASSMENT, or OTHER.",
            });
            return;
         }

         try {
            setReportingThreadId(reportDialog.threadId);
            await authFetch(threadFlagsEndpoint, {
               method: "POST",
               headers: { "Content-Type": "application/json" },
               body: JSON.stringify({
                  thread_id: reportDialog.threadId,
                  reason: reasonInput,
                  notes: reportDialog.notes.trim(),
               }),
            });

            addToast({
               type: "success",
               message: "Thread reported. Moderators have been notified.",
            });
            setReportDialog({
               open: false,
               threadId: null,
               reason: "OTHER",
               notes: "",
            });
         } catch (err) {
            const message = err?.message || "Failed to report thread.";
            setError(message);
            addToast({ type: "error", message });
         } finally {
            setReportingThreadId(null);
         }
      };

      const shareThread = async (e, thread) => {
         e.stopPropagation();
         if (!thread?.id) return;

         const shareUrl = `${window.location.origin}/thread/detail/${thread.id}`;
         const shareText = thread?.caption?.trim() || "Check this TruthLens thread.";

         try {
            setSharingThreadId(thread.id);

            if (navigator.share) {
               await navigator.share({
                  title: "TruthLens Thread",
                  text: shareText,
                  url: shareUrl,
               });
               addToast({ type: "success", message: "Thread link shared." });
            } else if (navigator.clipboard?.writeText) {
               await navigator.clipboard.writeText(shareUrl);
               addToast({ type: "success", message: "Thread link copied to clipboard." });
            } else {
               addToast({ type: "warning", message: "Sharing is not supported on this browser." });
            }
         } catch (err) {
            if (err?.name !== "AbortError") {
               addToast({ type: "error", message: err?.message || "Failed to share thread." });
            }
         } finally {
            setSharingThreadId(null);
            setOpenMenuThreadId(null);
         }
      };

      // Delete thread handler
      const confirmDeleteThread = async () => {
         const threadId = deleteDialog.threadId;
         if (!threadId) return;

         try {
            setDeletingThreadId(threadId);

            await authFetch(threadDetailUrl(threadId), {
               method: "DELETE",
            });

            setThreads((prev) => prev.filter((thread) => thread.id !== threadId));
            closeDeleteDialog();
            addToast({ type: "success", message: "Thread deleted successfully." });
         } catch (err) {
            const message = err?.message || "Failed to delete thread.";
            setError(message);
            addToast({ type: "error", message });
         } finally {
            setDeletingThreadId(null);
         }
      };

      const isModeratorVerified = (thread) => Boolean(thread?.claim?.moderator_verdict_info);
      const isPendingConsensus = (thread) => {
         const verifiedEvidenceCount = thread?.claim?.verified_evidence_count ?? 0;
         return !isModeratorVerified(thread) && verifiedEvidenceCount > 0;
      };

      const filteredThreads = threads.filter((thread) => {
         if (activeFilter === FEED_FILTERS.VERIFIED) {
            return isModeratorVerified(thread);
         }
         if (activeFilter === FEED_FILTERS.NEEDS_EVIDENCE) {
            return !isModeratorVerified(thread);
         }
         return true;
      });

      // ── Fetch threads with pagination ──
      const fetchThreadsPage = useCallback(
         async (pageUrl = null) => {
            const pageKey = pageUrl || "FIRST";
            if (requestedPagesRef.current.has(pageKey)) return;

            try {
               requestedPagesRef.current.add(pageKey);
               setLoading(true);
               setError(null);

               // DRF cursor pagination already returns the full next URL.
               const url = pageUrl || threadsEndpoint;

               const response = await authFetch(url, { method: "GET" });

               // Handle paginated response
               const newThreads = response.results || response || [];
               setThreads((prev) => {
                  const existingIds = new Set(prev.map((thread) => thread.id));
                  const dedupedIncoming = newThreads.filter(
                     (thread) => thread?.id && !existingIds.has(thread.id),
                  );
                  return [...prev, ...dedupedIncoming];
               });

               // Update next-page URL
               setCurrentCursor(response?.next || null);

               // Check if there are more pages
               setHasMore(Boolean(response?.next));
            } catch (err) {
               requestedPagesRef.current.delete(pageKey);
               console.error("Failed to fetch threads:", err);
               const message = "Failed to load threads.";
               setError(message);
               addToast({ type: "error", message });
            } finally {
               setLoading(false);
            }
         },
         [authFetch, addToast, threadsEndpoint],
      );

      // ── Initial load ──
      useEffect(() => {
         fetchThreadsPage(null);
      }, [fetchThreadsPage]);

      // ── Infinite scroll: Intersection Observer ──
      useEffect(() => {
         if (!observerTarget.current || loading || !hasMore) return;

         const observer = new IntersectionObserver(
            (entries) => {
               if (entries[0].isIntersecting && hasMore && !loading && currentCursor) {
                  fetchThreadsPage(currentCursor);
               }
            },
            { threshold: 0.1 },
         );

         observer.observe(observerTarget.current);
         return () => observer.disconnect();
      }, [loading, hasMore, currentCursor, fetchThreadsPage]);

      // ── Handler: Navigate to thread detail view ──
      const handleThreadClick = (threadID, tab = null) => {
         if (tab) {
            navigate(`/thread/detail/${threadID}?tab=${tab}`);
            return;
         }
         navigate(`/thread/detail/${threadID}`);
      };

      return (
         <div className="feed-layout">
            <NavigationBar />

            <main className="feed-container">
               {/* ── Filter Bar ── */}
               <div className="filter-bar box-panel">
                  <div className="filter-left">
                     <span className="filter-label">Filter:</span>
                     <button
                        className={`filter-btn ${activeFilter === FEED_FILTERS.TRENDING ? "active" : ""}`}
                        onClick={() => setActiveFilter(FEED_FILTERS.TRENDING)}>
                        <Icons name="trending-up" />
                        Trending
                     </button>
                     <button
                        className={`filter-btn ${activeFilter === FEED_FILTERS.VERIFIED ? "active" : ""}`}
                        onClick={() => setActiveFilter(FEED_FILTERS.VERIFIED)}>
                        <Icons name="check" />
                        Recently Verified
                     </button>
                     <button
                        className={`filter-btn ${activeFilter === FEED_FILTERS.NEEDS_EVIDENCE ? "active" : ""}`}
                        onClick={() => setActiveFilter(FEED_FILTERS.NEEDS_EVIDENCE)}>
                        <Icons name="search" />
                        Needs Evidence
                     </button>
                  </div>
               </div>

               {/* ── Loading & Error States ── */}
               {threads.length === 0 && loading && (
                  <div
                     style={{
                        padding: "40px 20px",
                        textAlign: "center",
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        gap: "12px",
                        color: "#9ca3af",
                     }}>
                     <Icons
                        name="loader"
                        size={24}
                     />
                     <p style={{ margin: 0 }}>Loading threads...</p>
                  </div>
               )}
               {error && <p style={{ color: "red", padding: "20px" }}>{error}</p>}

               {/* ── Threads List ── */}
               {/* Empty state or thread cards */}
               <div className="posts-list">
                  {filteredThreads.length === 0 && !loading ? (
                     <h2 className="no-threads-text">
                        {threads.length === 0
                           ? "No threads yet. Be the first to escalate a claim."
                           : "No threads match this filter yet."}
                     </h2>
                  ) : (
                     filteredThreads.map((thread) => {
                        const verdict = getEffectiveVerdict(thread.claim);
                        const verdictClass = verdict?.toLowerCase();
                        const hasModeratorVerdict = isModeratorVerified(thread);
                        const pendingConsensus = isPendingConsensus(thread);
                        const pendingEvidenceCount = thread.claim?.verified_evidence_count ?? 0;
                        const actionText = pendingConsensus ? "Pending" : getActionText(verdict);

                        return (
                           <div
                              key={thread.id}
                              className="post-card">
                              {/* Card Header */}
                              <div className="card-header">
                                 <div
                                    className="post-author-info"
                                    style={{ cursor: "pointer" }}
                                    onClick={(e) => {
                                       e.stopPropagation(); // Prevents triggering the thread card click
                                       navigate(`/user/${thread.author.username}`);
                                    }}>
                                    <div className="author-avatar" style={{ overflow: "hidden" }}>
                                       {thread.author.avatar_url ? (
                                          <img 
                                             src={thread.author.avatar_url} 
                                             alt={`${thread.author.username}'s avatar`} 
                                             style={{ width: "100%", height: "100%", objectFit: "cover" }} 
                                          />
                                       ) : (
                                          <Icons name="user" size={20} />
                                       )}
                                    </div>
                                    <div className="author-meta">
                                       <span className="author-name">@{thread.author.username}</span>
                                       <div className="author-time">
                                          {timeAgo(thread.created_at)} ·{" "}
                                          <span className="via-link">
                                             <Icons
                                                name="search"
                                                size={10}
                                             />
                                             via TruthLens
                                          </span>
                                       </div>
                                    </div>
                                 </div>
                                 <div className="header-actions">
                                    <div className={`status-badge badge-${verdictClass}`}>
                                       {verdictClass === "fake" && <Icons name="x-circle" />}
                                       {verdictClass === "fact" && <Icons name="check-circle" />}
                                       {verdictClass === "satire" && <Icons name="wand" />}
                                       {verdictClass === "misleading" && (
                                          <Icons name="alert-triangle" />
                                       )}
                                       {verdictClass === "unverified" && <Icons name="help-circle" />}
                                       {verdict}
                                    </div>

                                    <div className="thread-actions-menu-wrap">
                                       <button
                                          className="more-btn"
                                          onClick={(e) => toggleThreadMenu(e, thread.id)}
                                          aria-haspopup="menu"
                                          aria-expanded={openMenuThreadId === thread.id}>
                                          <Icons
                                             name="more-horizontal"
                                             size={20}
                                          />
                                       </button>

                                       {openMenuThreadId === thread.id && (
                                          <div className="thread-owner-menu">
                                             {isThreadOwner(thread) ? (
                                                <>
                                                   <button
                                                      className="thread-owner-menu-item"
                                                      onClick={(e) => startEditThread(e, thread)}>
                                                      <Icons name="pencil" />
                                                      Edit Thread
                                                   </button>
                                                   <button
                                                      className="thread-owner-menu-item"
                                                      onClick={(e) => shareThread(e, thread)}
                                                      disabled={sharingThreadId === thread.id}>
                                                      <Icons name="share-2" />
                                                      {sharingThreadId === thread.id
                                                         ? "Sharing..."
                                                         : "Share"}
                                                   </button>
                                                   <button
                                                      className="thread-owner-menu-item danger"
                                                      onClick={(e) => openDeleteDialog(e, thread)}
                                                      disabled={deletingThreadId === thread.id}>
                                                      <Icons name="trash" />
                                                      {deletingThreadId === thread.id
                                                         ? "Deleting..."
                                                         : "Delete Thread"}
                                                   </button>
                                                </>
                                             ) : (
                                                <>
                                                   <button
                                                      className="thread-owner-menu-item"
                                                      onClick={(e) => openReportDialog(e, thread)}
                                                      disabled={reportingThreadId === thread.id}>
                                                      <Icons name="flag" />
                                                      {reportingThreadId === thread.id
                                                         ? "Reporting..."
                                                         : "Report Thread"}
                                                   </button>
                                                   <button
                                                      className="thread-owner-menu-item"
                                                      onClick={(e) => shareThread(e, thread)}
                                                      disabled={sharingThreadId === thread.id}>
                                                      <Icons name="share-2" />
                                                      {sharingThreadId === thread.id
                                                         ? "Sharing..."
                                                         : "Share"}
                                                   </button>
                                                </>
                                             )}
                                          </div>
                                       )}
                                    </div>
                                 </div>
                              </div>

                              {/* Card Claim Text */}
                              <div className="card-claim">
                                 {editingThreadId === thread.id ? (
                                    <div
                                       className="thread-edit-wrap"
                                       onClick={(e) => e.stopPropagation()}>
                                       <textarea
                                          className="thread-edit-input"
                                          value={editingCaption}
                                          onChange={(e) => setEditingCaption(e.target.value)}
                                          rows={3}
                                       />
                                       <div className="thread-edit-actions">
                                          <button
                                             className="action-item primary-action"
                                             onClick={(e) => saveEditThread(e, thread.id)}
                                             disabled={savingThreadId === thread.id}>
                                             {savingThreadId === thread.id ? "Saving..." : "Save"}
                                          </button>
                                          <button
                                             className="action-item"
                                             onClick={cancelEditThread}>
                                             Cancel
                                          </button>
                                       </div>
                                    </div>
                                 ) : (
                                    thread.caption
                                 )}
                              </div>

                              {/* Card Media */}
                              {thread.claim.media_url && (
                                 <div
                                    className="card-media"
                                    onClick={() => {
                                       handleThreadClick(thread.id);
                                    }}
                                    style={{ height: "auto" }}>
                                    <img
                                       src={thread.claim.media_url}
                                       alt="Snipped claim"
                                       className="card-media-image"
                                    />
                                 </div>
                              )}

                              {/* ── AI Analysis Bar or Moderator Verdict (NOW WITH CONTEXT INSIDE) ── */}
                           <div className={`ai-analysis-bar bar-${verdictClass}`}>
                              
                              {/* TOP ROW: Verdict Info & Button */}
                              <div className="ai-analysis-top-row">
                                 {hasModeratorVerdict ? (
                                    // Show Moderator Verdict
                                    <div className="ai-info">
                                       <div className={`status-badge solid badge-${thread.claim.moderator_verdict_info.verdict.toLowerCase()}`}>
                                          <Icons name="check-circle" />
                                          {thread.claim.moderator_verdict_info.verdict === "MISLEADING" ? "Mixed" : "Verified"}
                                       </div>
                                       <span className="ai-confidence-text">
                                          Final Verdict: <strong>{thread.claim.moderator_verdict_info.verdict}</strong> ({thread.claim.moderator_verdict_info.verified_evidence_count} evidence)
                                          {thread.claim.moderator_verdict_info.verdict === "MISLEADING" && (
                                             <span className="mixed-evidence-pill">
                                                Mixed evidence
                                             </span>
                                          )}
                                       </span>
                                    </div>
                                 ) : pendingConsensus ? (
                                    // Show pending state
                                    <div className="ai-info">
                                       <div className="status-badge solid badge-unverified">
                                          <Icons name="clock" />
                                          Verdict Pending
                                       </div>
                                       <span className="ai-confidence-text">
                                          <strong>{pendingEvidenceCount}</strong> verified evidence under review
                                       </span>
                                    </div>
                                 ) : (
                                    // Show AI Verdict (fallback)
                                    <div className="ai-info">
                                       <div className={`status-badge solid badge-${verdictClass}`}>
                                          {verdictClass === "misleading" && <Icons name="alert-triangle" />}
                                          {verdictClass === "unverified" && <Icons name="help-circle" />}
                                          {verdict}
                                       </div>
                                       <span className="ai-confidence-text">
                                          AI Confidence: <strong>{thread.claim.consensus_score}%</strong>
                                       </span>
                                    </div>
                                 )}

                                 <button className="needs-evidence-btn">{actionText}</button>
                              </div>

                              {/* BOTTOM ROW: Context / Reasoning Text */}
                              <div className="ai-analysis-context">
                                 <strong className="context-label">Context: </strong>
                                 {hasModeratorVerdict 
                                    ? (thread.claim.moderator_verdict_info?.notes || thread.claim.ai_summary || "No additional context provided by moderators.")
                                    : pendingConsensus
                                    ? (`${pendingEvidenceCount} verified evidence submissions are currently under review by moderators to form a final consensus.`)
                                    : (thread.claim.ai_summary || "No AI summary available.")
                                 }
                              </div>
                           </div>
                                 
                                 
                              {/* Card Footer actions */}
                              <div className="card-footer">
                                 <button
                                    className="action-item"
                                    onClick={() => handleThreadClick(thread.id, "comments")}>
                                    <Icons name="message-square" />
                                    Comment
                                    <span className="count-pill">{thread.comment_count}</span>
                                 </button>

                                 <button
                                    className="action-item primary-action"
                                    onClick={() => handleThreadClick(thread.id, "evidence")}>
                                    <Icons name="circle-plus" />
                                    Add Evidence
                                 </button>

                                 <button
                                    className="action-item"
                                    onClick={() => handleThreadClick(thread.id, "evidence")}>
                                    <Icons name="paperclip" />
                                    Evidence
                                    <span className="count-pill">{thread.evidence_count}</span>
                                 </button>
                              </div>
                           </div>
                        );
                     })
                  )}

                  {/* Infinite Scroll Observer Target */}
                  {hasMore && (
                     <div
                        ref={observerTarget}
                        style={{
                           padding: "20px",
                           textAlign: "center",
                           color: "#9ca3af",
                        }}>
                        {!loading && hasMore && <p>Scroll to load more</p>}
                     </div>
                  )}

                  {!hasMore && threads.length > 0 && (
                     <div
                        style={{
                           padding: "20px",
                           textAlign: "center",
                           color: "#9ca3af",
                           fontSize: "14px",
                        }}>
                        No more threads to load
                     </div>
                  )}
               </div>

               {deleteDialog.open && (
                  <div
                     className="feed-modal-overlay"
                     onClick={closeDeleteDialog}>
                     <div
                        className="feed-modal"
                        onClick={(e) => e.stopPropagation()}>
                        <h3 className="feed-modal-title">Delete Thread</h3>
                        <p className="feed-modal-text">
                           This action cannot be undone. Are you sure you want to delete this thread?
                        </p>
                        <div className="feed-modal-actions">
                           <button
                              type="button"
                              className="feed-modal-btn secondary"
                              onClick={closeDeleteDialog}
                              disabled={Boolean(deletingThreadId)}>
                              Cancel
                           </button>
                           <button
                              type="button"
                              className="feed-modal-btn danger"
                              onClick={confirmDeleteThread}
                              disabled={Boolean(deletingThreadId)}>
                              {deletingThreadId ? "Deleting..." : "Delete"}
                           </button>
                        </div>
                     </div>
                  </div>
               )}

               {reportDialog.open && (
                  <div
                     className="feed-modal-overlay"
                     onClick={closeReportDialog}>
                     <div
                        className="feed-modal"
                        onClick={(e) => e.stopPropagation()}>
                        <div className="feed-modal-policy-chip warning">{reportActionMeta.code}</div>
                        <h3 className="feed-modal-title">{reportActionMeta.title}</h3>
                        <p className="feed-modal-text">{reportActionMeta.description}</p>
                        <div className="feed-modal-form-row">
                           <label className="feed-modal-label">Reason</label>
                           <select
                              className="feed-modal-select"
                              value={reportDialog.reason}
                              onChange={(e) =>
                                 setReportDialog((prev) => ({ ...prev, reason: e.target.value }))
                              }>
                              <option value="INAPPROPRIATE">Inappropriate</option>
                              <option value="SPAM">Spam</option>
                              <option value="HARASSMENT">Harassment</option>
                              <option value="OTHER">Other</option>
                           </select>
                        </div>
                        <div className="feed-modal-form-row">
                           <label className="feed-modal-label">Notes (optional)</label>
                           <textarea
                              className="feed-modal-textarea"
                              rows={4}
                              value={reportDialog.notes}
                              onChange={(e) =>
                                 setReportDialog((prev) => ({ ...prev, notes: e.target.value }))
                              }
                           />
                        </div>
                        <div className="feed-modal-actions">
                           <button
                              type="button"
                              className="feed-modal-btn secondary"
                              onClick={closeReportDialog}
                              disabled={Boolean(reportingThreadId)}>
                              Cancel
                           </button>
                           <button
                              type="button"
                              className="feed-modal-btn warning"
                              onClick={submitReportThread}
                              disabled={Boolean(reportingThreadId)}>
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
