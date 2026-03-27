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
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";

// ── Utilities & Hooks ──
import timeAgo from "../utils/timeAgo";
import { getEffectiveVerdict } from "../utils/verdict";
import { useEndpoint } from "../utils/api";

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

/**
 * CommunityFeed Component
 * Shows browsable feed of community-escalated claims with infinite scroll
 */
function CommunityFeed() {
   const navigate = useNavigate();
   const { authFetch } = useAuth();

   // ── Infinite Scroll State ──
   const [threads, setThreads] = useState([]);
   const [loading, setLoading] = useState(false);
   const [hasMore, setHasMore] = useState(true);
   const [error, setError] = useState(null);
   const [currentCursor, setCurrentCursor] = useState(null);
   const observerTarget = useRef(null);
   const pageSize = 20;

   // ── Fetch threads with pagination ──
   const fetchThreadsPage = useCallback(
      async (cursor = null) => {
         try {
            setLoading(true);
            setError(null);

            // Build URL with cursor parameter
            const baseUrl = useEndpoint("THREADS");
            const url = cursor ? `${baseUrl}?cursor=${cursor}` : baseUrl;

            const response = await authFetch(url, { method: "GET" });

            // Handle paginated response
            const newThreads = response.results || response || [];
            setThreads((prev) => [...prev, ...newThreads]);

            // Update cursor for next page
            setCurrentCursor(response.next || null);

            // Check if there are more pages
            setHasMore(!!response.next);
         } catch (err) {
            console.error("Failed to fetch threads:", err);
            setError("Failed to load threads");
         } finally {
            setLoading(false);
         }
      },
      [authFetch],
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
            if (entries[0].isIntersecting && hasMore && !loading) {
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
            {/* Note: Filter buttons are currently placeholders (functionality can be added) */}
            <div className="filter-bar box-panel">
               <div className="filter-left">
                  <span className="filter-label">Filter:</span>
                  <button className="filter-btn active">
                     <Icons name="trending-up" />
                     Trending
                  </button>
                  <button className="filter-btn">
                     <Icons name="check" />
                     Recently Verified
                  </button>
                  <button className="filter-btn">
                     <Icons name="search" />
                     Needs Evidence
                  </button>
               </div>
            </div>

            {/* ── Loading & Error States ── */}
            {threads.length === 0 && loading && (
               <p style={{ padding: "20px", textAlign: "center" }}>Loading threads...</p>
            )}
            {error && <p style={{ color: "red", padding: "20px" }}>{error}</p>}

            {/* ── Threads List ── */}
            {/* Empty state or thread cards */}
            <div className="posts-list">
               {threads.length === 0 && !loading ? (
                  <h2 className="no-threads-text">
                     No threads yet. Be the first to escalate a claim.
                  </h2>
               ) : (
                  threads.map((thread) => {
                     const verdict = getEffectiveVerdict(thread.claim);
                     const verdictClass = verdict?.toLowerCase();

                     return (
                        <div
                           key={thread.id}
                           className="post-card">
                           {/* Card Header */}
                           <div className="card-header">
                              <div className="post-author-info">
                                 <div className="author-avatar">
                                    <Icons
                                       name="user"
                                       size={20}
                                    />
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
                                 <button className="more-btn">
                                    <Icons
                                       name="more-horizontal"
                                       size={20}
                                    />
                                 </button>
                              </div>
                           </div>

                           {/* Card Claim Text */}
                           <div className="card-claim">
                              {/* <strong>Flagged claim:</strong> "
                              {thread.claim.ai_summary || thread.claim.context_text}" */}
                              {thread.caption}
                           </div>

                           {/* Media Placeholder */}
                           <div
                              className="card-media"
                              onClick={() => {
                                 handleThreadClick(thread.id);
                              }}
                              style={
                                 thread.claim.media_url ? { height: "auto" } : { height: "350px" }
                              }>
                              {thread.claim.media_url ? (
                                 <img
                                    src={thread.claim.media_url}
                                    alt="Snipped claim"
                                    className="card-media-image"
                                 />
                              ) : (
                                 <>
                                    <div className="media-icon">
                                       <Icons
                                          name="globe"
                                          size={24}
                                       />
                                    </div>
                                    <span className="media-source">Snipped from Twitter / X</span>
                                 </>
                              )}
                           </div>

                           {/* AI Analysis Bar or Moderator Verdict */}
                           <div className={`ai-analysis-bar bar-${verdictClass}`}>
                              {thread.claim?.has_moderator_verdict &&
                              thread.claim?.moderator_verdict_info ? (
                                 // Show Moderator Verdict
                                 <div className="ai-info">
                                    <div
                                       className={`status-badge solid badge-${thread.claim.moderator_verdict_info.verdict.toLowerCase()}`}>
                                       <Icons name="check-circle" />
                                       Verified
                                    </div>
                                    <span className="ai-confidence-text">
                                       Final Verdict:{" "}
                                       <strong>
                                          {thread.claim.moderator_verdict_info.verdict}
                                       </strong>{" "}
                                       (
                                       {thread.claim.moderator_verdict_info.verified_evidence_count}{" "}
                                       evidence)
                                    </span>
                                 </div>
                              ) : (
                                 // Show AI Verdict (fallback)
                                 <div className="ai-info">
                                    <div className={`status-badge solid badge-${verdictClass}`}>
                                       {verdictClass === "misleading" && (
                                          <Icons name="alert-triangle" />
                                       )}
                                       {verdictClass === "unverified" && (
                                          <Icons name="help-circle" />
                                       )}
                                       {verdict}
                                    </div>
                                    <span className="ai-confidence-text">
                                       AI Confidence:{" "}
                                       <strong>{thread.claim.consensus_score}%</strong>
                                    </span>
                                 </div>
                              )}
                              <button className="needs-evidence-btn">
                                 {getActionText(verdict)}
                              </button>
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
                     {loading && <p>Loading more threads...</p>}
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
         </main>
      </div>
   );
}

export default CommunityFeed;
