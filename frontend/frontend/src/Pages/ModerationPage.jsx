import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";
import "./ModerationPage.css";

// ─────────────────────────────────────────────────────────────────────────────
// TODO: ROLE-BASED ACCESS CONTROL
// When implementing proper moderation roles, add a check here like:
//   const { user } = useAuth();
//   if (!user?.is_moderator && !user?.is_staff) return <Navigate to="/community" />;
//
// This requires:
//   1. Adding is_moderator or is_staff field to UserProfile model
//   2. Exposing it in UserSerializer
//   3. Checking it here before rendering the page
// ─────────────────────────────────────────────────────────────────────────────

// ── Verdict config using the design system variables ─────────────────────────
const VERDICT_CONFIG = {
   FACT:         { color: "var(--verdict-fact-text)",        bg: "var(--verdict-fact-bg)",        border: "var(--verdict-fact-border)",        label: "FACT" },
   FAKE:         { color: "var(--verdict-fake-text)",        bg: "var(--verdict-fake-bg)",        border: "var(--verdict-fake-border)",        label: "FAKE" },
   MISLEADING:   { color: "var(--verdict-misleading-text)",  bg: "var(--verdict-misleading-bg)",  border: "var(--verdict-misleading-border)",  label: "MISLEADING" },
   UNVERIFIED:   { color: "var(--verdict-unverified-text)",  bg: "var(--verdict-unverified-bg)",  border: "var(--verdict-unverified-border)",  label: "UNVERIFIED" },
   SATIRE:       { color: "var(--verdict-satire-text)",      bg: "var(--verdict-satire-bg)",      border: "var(--verdict-satire-border)",      label: "SATIRE" },
   OUT_OF_SCOPE: { color: "var(--verdict-unverified-text)",  bg: "var(--verdict-unverified-bg)",  border: "var(--verdict-unverified-border)",  label: "OUT OF SCOPE" },
};

// ── Helper: relative time ─────────────────────────────────────────────────────
function timeAgo(dateStr) {
   if (!dateStr) return "—";
   const diff  = Date.now() - new Date(dateStr).getTime();
   const mins  = Math.floor(diff / 60000);
   const hours = Math.floor(diff / 3600000);
   const days  = Math.floor(diff / 86400000);
   if (mins  < 1)  return "Just now";
   if (mins  < 60) return `${mins}m ago`;
   if (hours < 24) return `${hours}h ago`;
   if (days  < 7)  return `${days}d ago`;
   return `${Math.floor(days / 7)}w ago`;
}

// ── Verdict badge component ───────────────────────────────────────────────────
function VerdictBadge({ verdict }) {
   const config = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNVERIFIED;
   return (
      <span className="mod-verdict-badge" style={{
         color: config.color,
         backgroundColor: config.bg,
         borderColor: config.border,
      }}>
         {config.label}
      </span>
   );
}

// ── Status badge for thread open/closed ──────────────────────────────────────
function StatusBadge({ status }) {
   const isOpen = status === "OPEN" || !status;
   return (
      <span className={`mod-status-badge ${isOpen ? "open" : "closed"}`}>
         {isOpen ? "OPEN" : "CLOSED"}
      </span>
   );
}

// ── Main Component ────────────────────────────────────────────────────────────
function ModerationPage() {
   const { authFetch }                           = useAuth();
   const navigate                                = useNavigate();

   // ── Data state ──────────────────────────────────────────────────────────
   const [threads, setThreads]                   = useState([]);
   const [claims, setClaims]                     = useState([]);
   const [loading, setLoading]                   = useState(true);
   const [error, setError]                       = useState(null);

   // ── Filter and search state ──────────────────────────────────────────────
   const [statusFilter, setStatusFilter]         = useState("ALL");
   const [verdictFilter, setVerdictFilter]       = useState("ALL");
   const [searchQuery, setSearchQuery]           = useState("");

   // ── Fetch threads and claims on mount ───────────────────────────────────
   useEffect(() => {
      const fetchData = async () => {
         try {
            // Fetch all threads — used for the moderation queue
            const threadData = await authFetch("http://localhost:8000/api/threads/", {
               method: "GET",
            });
            setThreads(threadData || []);

            // Fetch all claims — used for the recent AI verdicts panel
            // TODO: When backend adds pagination, update this to fetch
            // only the most recent N claims instead of all of them
            const claimData = await authFetch("http://localhost:8000/api/claims/", {
               method: "GET",
            });
            setClaims(claimData || []);
         } catch (err) {
            setError("Failed to load moderation data.");
         } finally {
            setLoading(false);
         }
      };
      fetchData();
   }, []);

   // ── Close a thread ───────────────────────────────────────────────────────
   // Uses PATCH to update thread status to CLOSED
   // TODO: Add a confirmation dialog before closing
   // TODO: When moderator roles are implemented, log who closed the thread
   const handleCloseThread = async (threadId) => {
      try {
         await authFetch(`http://localhost:8000/api/threads/${threadId}/`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: "CLOSED" }),
         });
         // Update local state so UI reflects the change immediately
         setThreads((prev) =>
            prev.map((t) => t.id === threadId ? { ...t, status: "CLOSED" } : t)
         );
      } catch (err) {
         console.error("Failed to close thread:", err);
      }
   };

   // ── Reopen a thread ──────────────────────────────────────────────────────
   // TODO: Add moderator-only restriction when roles are implemented
   const handleReopenThread = async (threadId) => {
      try {
         await authFetch(`http://localhost:8000/api/threads/${threadId}/`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: "OPEN" }),
         });
         setThreads((prev) =>
            prev.map((t) => t.id === threadId ? { ...t, status: "OPEN" } : t)
         );
      } catch (err) {
         console.error("Failed to reopen thread:", err);
      }
   };

   // ── Filtered threads ─────────────────────────────────────────────────────
   // Apply status filter, verdict filter, and search query
   const filteredThreads = threads.filter((thread) => {
      const matchesStatus =
         statusFilter === "ALL" ||
         (statusFilter === "OPEN" && (thread.status === "OPEN" || !thread.status)) ||
         (statusFilter === "CLOSED" && thread.status === "CLOSED");

      const matchesVerdict =
         verdictFilter === "ALL" ||
         thread.claim?.verdict === verdictFilter ||
         thread.flag_reason === verdictFilter;

      const matchesSearch =
         searchQuery === "" ||
         thread.claim?.ai_summary?.toLowerCase().includes(searchQuery.toLowerCase()) ||
         thread.caption?.toLowerCase().includes(searchQuery.toLowerCase()) ||
         thread.author?.username?.toLowerCase().includes(searchQuery.toLowerCase());

      return matchesStatus && matchesVerdict && matchesSearch;
   });

   // ── Derived stats for the overview row ──────────────────────────────────
   // TODO: Replace with dedicated backend stats endpoint when available
   // These are computed from the data we already have
   const openThreads    = threads.filter((t) => t.status === "OPEN" || !t.status).length;
   const closedThreads  = threads.filter((t) => t.status === "CLOSED").length;
   const fakeCount      = threads.filter((t) => t.claim?.verdict === "FAKE").length;
   const unverifiedCount = threads.filter((t) =>
      t.claim?.verdict === "UNVERIFIED" || !t.claim?.verdict
   ).length;

   // Recent claims for the side panel — last 8 sorted by date
   const recentClaims = [...claims]
      .sort((a, b) => new Date(b.last_updated) - new Date(a.last_updated))
      .slice(0, 8);

   // ── Render ───────────────────────────────────────────────────────────────
   return (
      <div className="mod-layout">
         <NavigationBar />

         <main className="mod-container">

            {/* ── Page Header ── */}
            <div className="mod-header">
               <div className="mod-header-left">
                  <div className="mod-header-icon">
                     <Icons name="shield" size={22} color="#fff" />
                  </div>
                  <div>
                     <h1 className="mod-title">Moderation Panel</h1>
                     <p className="mod-subtitle">
                        Review flagged claims, manage threads, and monitor AI verdicts.
                     </p>
                  </div>
               </div>
               {/* TODO: Add "Export Report" button here when reporting feature is built */}
               <div className="mod-header-right">
                  <span className="mod-access-badge">
                     <Icons name="lock" size={12} />
                     Moderator Access
                  </span>
               </div>
            </div>

            {/* ── Overview Stats Row ── */}
            {/* TODO: Replace with real-time stats from a dedicated /api/moderation/stats/ endpoint */}
            <div className="mod-stats-row">
               <div className="mod-stat-card">
                  <Icons name="alert-triangle" size={18} color="var(--verdict-misleading-border)" />
                  <div>
                     <p className="mod-stat-value">{openThreads}</p>
                     <p className="mod-stat-label">Open Threads</p>
                  </div>
               </div>
               <div className="mod-stat-card">
                  <Icons name="check-circle" size={18} color="var(--verdict-fact-border)" />
                  <div>
                     <p className="mod-stat-value">{closedThreads}</p>
                     <p className="mod-stat-label">Closed Threads</p>
                  </div>
               </div>
               <div className="mod-stat-card">
                  <Icons name="x-circle" size={18} color="var(--verdict-fake-border)" />
                  <div>
                     <p className="mod-stat-value">{fakeCount}</p>
                     <p className="mod-stat-label">FAKE Verdicts</p>
                  </div>
               </div>
               <div className="mod-stat-card">
                  <Icons name="help-circle" size={18} color="var(--verdict-unverified-border)" />
                  <div>
                     <p className="mod-stat-value">{unverifiedCount}</p>
                     <p className="mod-stat-label">Needs Review</p>
                  </div>
               </div>
            </div>

            {/* ── Main content: Queue + Sidebar ── */}
            <div className="mod-body">

               {/* ── Left: Thread Queue ── */}
               <div className="mod-queue">

                  {/* Filter and search bar */}
                  <div className="mod-filters box-panel">
                     <div className="mod-filter-left">
                        <span className="mod-filter-label">Status:</span>
                        {["ALL", "OPEN", "CLOSED"].map((s) => (
                           <button
                              key={s}
                              className={`mod-filter-btn ${statusFilter === s ? "active" : ""}`}
                              onClick={() => setStatusFilter(s)}
                           >
                              {s}
                           </button>
                        ))}
                        <span className="mod-filter-divider" />
                        <span className="mod-filter-label">Verdict:</span>
                        {["ALL", "FAKE", "UNVERIFIED", "MISLEADING", "SATIRE", "FACT"].map((v) => (
                           <button
                              key={v}
                              className={`mod-filter-btn ${verdictFilter === v ? "active" : ""}`}
                              onClick={() => setVerdictFilter(v)}
                           >
                              {v}
                           </button>
                        ))}
                     </div>
                     <div className="mod-search-box">
                        <Icons name="search" size={14} color="var(--text-muted)" />
                        <input
                           type="text"
                           placeholder="Search claims, users..."
                           value={searchQuery}
                           onChange={(e) => setSearchQuery(e.target.value)}
                        />
                     </div>
                  </div>

                  {/* Thread queue table */}
                  <div className="mod-table-wrapper box-panel">
                     <div className="mod-table-header">
                        <h2 className="mod-section-title">
                           <Icons name="list-checks" size={15} />
                           Thread Queue
                           <span className="mod-count-pill">{filteredThreads.length}</span>
                        </h2>
                     </div>

                     {loading && <p className="mod-empty">Loading threads...</p>}
                     {error && <p className="mod-error">{error}</p>}

                     {!loading && filteredThreads.length === 0 && (
                        <p className="mod-empty">No threads match the current filters.</p>
                     )}

                     {!loading && filteredThreads.length > 0 && (
                        <div className="mod-table">
                           {/* Table header row */}
                           <div className="mod-table-row mod-table-head">
                              <span>Claim</span>
                              <span>AI Verdict</span>
                              <span>Flag</span>
                              <span>Author</span>
                              <span>Activity</span>
                              <span>Status</span>
                              <span>Actions</span>
                           </div>

                           {/* Table data rows */}
                           {filteredThreads.map((thread) => (
                              <div key={thread.id} className="mod-table-row mod-table-data">

                                 {/* Claim summary */}
                                 <div className="mod-claim-cell">
                                    <p className="mod-claim-text">
                                       {thread.claim?.ai_summary || thread.caption || "No summary"}
                                    </p>
                                    <span className="mod-claim-time">{timeAgo(thread.created_at)}</span>
                                 </div>

                                 {/* AI verdict */}
                                 <div>
                                    {thread.claim?.verdict ? (
                                       <VerdictBadge verdict={thread.claim.verdict} />
                                    ) : (
                                       <span className="mod-na">—</span>
                                    )}
                                    {thread.claim?.consensus_score !== null && thread.claim?.consensus_score !== undefined && (
                                       <p className="mod-confidence">
                                          {thread.claim.consensus_score}% confidence
                                       </p>
                                    )}
                                 </div>

                                 {/* Flag reason — why user escalated this */}
                                 <div>
                                    {thread.flag_reason ? (
                                       <VerdictBadge verdict={thread.flag_reason} />
                                    ) : (
                                       <span className="mod-na">—</span>
                                    )}
                                 </div>

                                 {/* Author info */}
                                 <div className="mod-author-cell">
                                    <span className="mod-author-name">
                                       @{thread.author?.username}
                                    </span>
                                    <span className="mod-trust-score">
                                       Trust: {thread.author?.trust_score?.toFixed(1) || "0.0"}
                                    </span>
                                 </div>

                                 {/* Evidence and comment counts */}
                                 <div className="mod-activity-cell">
                                    <span className="mod-activity-item">
                                       <Icons name="paperclip" size={12} />
                                       {thread.evidence_count}
                                    </span>
                                    <span className="mod-activity-item">
                                       <Icons name="message-square" size={12} />
                                       {thread.comment_count}
                                    </span>
                                 </div>

                                 {/* Thread status */}
                                 <StatusBadge status={thread.status} />

                                 {/* Action buttons */}
                                 <div className="mod-actions-cell">
                                    <button
                                       className="mod-action-btn view"
                                       onClick={() => navigate(`/thread?thread_id=${thread.id}`)}
                                       title="View thread detail"
                                    >
                                       <Icons name="eye" size={13} />
                                    </button>

                                    {/* Close or reopen depending on current status */}
                                    {(thread.status === "OPEN" || !thread.status) ? (
                                       <button
                                          className="mod-action-btn close"
                                          onClick={() => handleCloseThread(thread.id)}
                                          title="Close thread"
                                          // TODO: Add confirmation modal before closing
                                       >
                                          <Icons name="x" size={13} />
                                       </button>
                                    ) : (
                                       <button
                                          className="mod-action-btn reopen"
                                          onClick={() => handleReopenThread(thread.id)}
                                          title="Reopen thread"
                                       >
                                          <Icons name="refresh" size={13} />
                                       </button>
                                    )}
                                 </div>

                              </div>
                           ))}
                        </div>
                     )}
                  </div>
               </div>

               {/* ── Right: Recent AI Verdicts Sidebar ── */}
               <div className="mod-sidebar">
                  <div className="box-panel">
                     <h2 className="mod-section-title">
                        <Icons name="activity" size={15} />
                        Recent AI Verdicts
                     </h2>
                     {/* TODO: Add pagination or "Load more" when claim count grows */}
                     <div className="mod-recent-list">
                        {recentClaims.length === 0 ? (
                           <p className="mod-empty">No claims yet.</p>
                        ) : (
                           recentClaims.map((claim) => (
                              <div key={claim.id} className="mod-recent-item">
                                 <div className="mod-recent-top">
                                    {claim.verdict ? (
                                       <VerdictBadge verdict={claim.verdict} />
                                    ) : (
                                       <span className="mod-status-badge open">PENDING</span>
                                    )}
                                    <span className="mod-recent-time">
                                       {timeAgo(claim.last_updated)}
                                    </span>
                                 </div>
                                 <p className="mod-recent-summary">
                                    {claim.ai_summary || "Processing..."}
                                 </p>
                                 {claim.consensus_score !== null && claim.consensus_score !== undefined && (
                                    <div className="mod-recent-confidence">
                                       <div className="mod-conf-track">
                                          <div
                                             className="mod-conf-fill"
                                             style={{
                                                width: `${claim.consensus_score}%`,
                                                backgroundColor:
                                                   claim.consensus_score >= 70
                                                      ? "var(--verdict-fact-border)"
                                                      : claim.consensus_score >= 40
                                                      ? "var(--verdict-misleading-border)"
                                                      : "var(--verdict-fake-border)",
                                             }}
                                          />
                                       </div>
                                       <span className="mod-conf-label">
                                          {claim.consensus_score}%
                                       </span>
                                    </div>
                                 )}
                                 {/* TODO: Add "Review" button that links to the thread
                                     associated with this claim once claim→thread
                                     relationship is navigable */}
                              </div>
                           ))
                        )}
                     </div>
                  </div>

                  {/* ── Moderator Notes ── */}
                  {/* TODO: Implement a real moderator notes/log system
                      This should store notes in the database tied to a moderator's
                      user account so the team can coordinate */}
                  <div className="box-panel mod-notes-card">
                     <h2 className="mod-section-title">
                        <Icons name="file-text" size={15} />
                        Moderator Notes
                     </h2>
                     <textarea
                        className="mod-notes-input"
                        placeholder="Add internal notes here... (local only for now)"
                        rows={5}
                     />
                     <p className="mod-notes-hint">
                        {/* TODO: Wire this to a persistent notes endpoint */}
                        Notes are not saved yet. Backend endpoint needed.
                     </p>
                  </div>

               </div>
            </div>
         </main>
      </div>
   );
}

export default ModerationPage;