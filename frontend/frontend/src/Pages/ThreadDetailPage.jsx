import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";
import { Link } from "react-router-dom";
import Icons from "../components/Icons.jsx";
import "./ThreadDetail.css";


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

const VERDICT_CONFIG = {
   FACT:         { color: "var(--fact-text)",         bg: "var(--fact-bg)",         border: "var(--fact-border)",         label: "Fact" },
   FAKE:         { color: "var(--fake-text)",         bg: "var(--fake-bg)",         border: "var(--fake-border)",         label: "Fake / False" },
   MISLEADING:   { color: "var(--misleading-text)",   bg: "var(--misleading-bg)",   border: "var(--misleading-border)",   label: "Misleading" },
   SATIRE:       { color: "var(--satire-text)",       bg: "var(--satire-bg)",       border: "var(--satire-border)",       label: "Satire" },
   UNVERIFIED:   { color: "var(--unverified-text)",   bg: "var(--unverified-bg)",   border: "var(--unverified-border)",   label: "Unverified" },
   OUT_OF_SCOPE: { color: "var(--out-of-scope-text)", bg: "var(--out-of-scope-bg)", border: "var(--out-of-scope-border)", label: "Out of Scope" },
};

function VerdictBadge({ verdict }) {
   const config = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNVERIFIED;
   return (
      <span
         className="verdict-badge"
         style={{
            color: config.color,
            backgroundColor: config.bg,
            borderColor: config.border,
         }}
      >
         <Icons name="alert-triangle" size={13} />
         {config.label}
      </span>
   );
}


function ThreadDetailPage() {
   const [thread, setThread] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const [activeTab, setActiveTab] = useState("comments");
   const [comment, setComment]     = useState("");
   const { authFetch } = useAuth();
   const [searchParams] = useSearchParams();
   const threadId = searchParams.get("thread_id");
   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

   useEffect(() => {
      const fetchThread = async () => {
         try {
            const threadData = await authFetch(`${API_BASE_URL}/threads/${threadId}/`, {
               method: "GET",
            });
            setThread(threadData);
         } catch (err) {
            setError("Failed to load thread");
         } finally {
            setLoading(false);
         }
      };
      fetchThread();
   }, [threadId]);

   if (loading) return (
      <div className="thread-layout">
         <NavigationBar />
         <p className="thread-loading">Loading thread...</p>
      </div>
   );

   if (error) return (
      <div className="thread-layout">
         <NavigationBar />
         <p className="thread-error">{error}</p>
      </div>
   );

   const claim   = thread?.claim;
   const verdict = claim?.verdict;
   const config  = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNVERIFIED;

   const confidenceColor =
      claim?.consensus_score >= 70 ? "#0e9f6e"
      : claim?.consensus_score >= 40 ? "#d97706"
      : "#e02424";

   return (
      
      <div className="thread-layout">
         <NavigationBar />

         {/* Breadcrumb + action bar */}
         <div className="thread-topbar">
            <div className="breadcrumb">
               <Link to="/community" className="breadcrumb-link">
                  <Icons name="globe" size={14} />
                  Community Feed
               </Link>
               <Icons name="chevron-right" size={14} />
               <span className="breadcrumb-current">Thread #{threadId?.slice(0, 4)}</span>
            </div>
            <div className="topbar-actions">
               {verdict && <VerdictBadge verdict={verdict} />}
               <button className="needs-evidence-topbar-btn">Needs Evidence</button>
            </div>
         </div>

         {/* Hero banner */}
         <div className="thread-hero" style={{ backgroundColor: config.bg }}>
            <div className="thread-hero-content">
               <p className="claim-investigation-label">
                  <Icons name="flag" size={13} />
                  CLAIM UNDER INVESTIGATION
               </p>
               <h1 className="claim-title">"{claim?.ai_summary || thread?.caption}"</h1>
               <div className="claim-meta">
                  <span className="meta-item">
                     <Icons name="globe" size={13} />
                     Sourced from <strong>Twitter / X</strong>
                  </span>
                  <span className="meta-item">
                     <Icons name="message-square" size={13} />
                     {thread?.comment_count || 0} comments
                  </span>
                  <span className="meta-item">
                     <Icons name="paperclip" size={13} />
                     {thread?.evidence_count || 0} evidence submissions
                  </span>
               </div>
            </div>

            {/* AI verdict card */}
            <div className="ai-verdict-card">
               <VerdictBadge verdict={verdict} />
               <p className="ai-verdict-desc">{claim?.ai_summary || "No AI summary available."}</p>
               <div className="ai-stat-row">
                  <span className="ai-stat-label">AI Confidence</span>
                  <span className="ai-stat-value" style={{ color: confidenceColor }}>
                     {claim?.consensus_score ?? "—"} %
                  </span>
               </div>
               <div className="confidence-track">
                  <div
                     className="confidence-fill"
                     style={{
                        width: `${claim?.consensus_score || 0}%`,
                        backgroundColor: confidenceColor,
                     }}
                  />
               </div>
               <div className="ai-stat-row" style={{ marginTop: 12 }}>
                  <span className="ai-stat-label">Evidence submissions</span>
                  <span className="ai-stat-value" style={{ color: confidenceColor }}>
                     {thread?.evidence_count || 0}
                  </span>
               </div>
            </div>
         </div>

         {/* Main content area */}
         <div className="thread-body">

            {/* Left column */}
            <div className="thread-left">
               <div className="post-card box-panel">
                  <div className="post-card-header">
                     <div className="post-author">
                        <div className="author-avatar-sm">
                           <Icons name="user" size={16} />
                        </div>
                        <div>
                           <span className="author-name">@{thread?.author?.username}</span>
                           <span className="post-time">{timeAgo(thread?.created_at)}</span>
                        </div>
                     </div>
                     <div className="post-header-right">
                        <button className="original-post-btn">Original post</button>
                        <Icons name="external-link" size={16} color="#9ca3af" />
                     </div>
                  </div>

                  <div className="media-placeholder">
                     <div className="media-icon-box">
                        <Icons name="globe" size={28} color="#9ca3af" />
                     </div>
                     <span className="media-label">Snipped from Twitter / X</span>
                  </div>

                  <button className="submit-evidence-btn">
                     <Icons name="paperclip" size={16} />
                     Submit Evidence for This Claim
                  </button>

                  <div className="tabs-row">
                     <button
                        className={`tab-btn ${activeTab === "comments" ? "active" : ""}`}
                        onClick={() => setActiveTab("comments")}
                     >
                        <Icons name="message-circle" size={14} />
                        Comments ({thread?.comment_count || 0})
                     </button>
                     <button
                        className={`tab-btn ${activeTab === "evidence" ? "active" : ""}`}
                        onClick={() => setActiveTab("evidence")}
                     >
                        <Icons name="paperclip" size={14} />
                        Evidence Board ({thread?.evidence_count || 0})
                     </button>
                  </div>

                  {activeTab === "comments" && (
                     <div className="comments-section">
                        <div className="comment-input-row">
                           <div className="author-avatar-sm">
                              <Icons name="user" size={16} />
                           </div>
                           <input
                              type="text"
                              className="comment-input"
                              placeholder="Write a comment..."
                              value={comment}
                              onChange={(e) => setComment(e.target.value)}
                           />
                        </div>
                        <div className="comments-list">
                           {thread?.comments?.length === 0 ? (
                              <p className="empty-msg">No comments yet.</p>
                           ) : (
                              thread?.comments?.map((c) => (
                                 <div key={c.id} className="comment-item">
                                    <div className="author-avatar-sm">
                                       <Icons name="user" size={16} />
                                    </div>
                                    <div className="comment-body">
                                       <div className="comment-header">
                                          <span className="comment-author">@{c.commenter?.username}</span>
                                          <span className="comment-time">{timeAgo(c.commented_at)}</span>
                                       </div>
                                       <p className="comment-text">{c.comment_text}</p>
                                       <div className="comment-actions">
                                          <button className="comment-action-btn">
                                             <Icons name="thumbs-up" size={13} /> {c.likes || 0}
                                          </button>
                                          <button className="comment-action-btn">Reply</button>
                                       </div>
                                    </div>
                                 </div>
                              ))
                           )}
                        </div>
                     </div>
                  )}

                  {activeTab === "evidence" && (
                     <div className="evidence-section">
                        {thread?.evidence_submissions?.length === 0 ? (
                           <p className="empty-msg">No evidence submitted yet.</p>
                        ) : (
                           thread?.evidence_submissions?.map((ev) => (
                              <div key={ev.id} className="evidence-item">
                                 <div className="evidence-header">
                                    <span className="evidence-author">@{ev.contributor?.username}</span>
                                    <span className="evidence-time">{timeAgo(ev.submitted_at)}</span>
                                 </div>
                                 <p className="evidence-caption">{ev.evidence_caption}</p>
                                 {ev.evidence_url && (
                                    <a
                                       href={ev.evidence_url}
                                       target="_blank"
                                       rel="noopener noreferrer"
                                       className="evidence-link"
                                    >
                                       <Icons name="external-link" size={13} /> View Evidence
                                    </a>
                                 )}
                              </div>
                           ))
                        )}
                     </div>
                  )}
               </div>
            </div>

            {/* Right column */}
            <div className="thread-right">
               <div className="box-panel sidebar-card">
                  <p className="sidebar-label">POSTED BY</p>
                  <div className="posted-by-row">
                     <div className="posted-by-left">
                        <div className="author-avatar-lg">
                           <Icons name="user" size={22} />
                        </div>
                        <div>
                           <span className="posted-username">@{thread?.author?.username}</span>
                           <span className="posted-role">
                              <Icons name="badge-check" size={13} color="#0e9f6e" />
                              Trusted Contributor
                           </span>
                        </div>
                     </div>
                     <div className="trust-circle">
                        <span className="trust-number">{thread?.author?.trust_score?.toFixed(0) || 0}</span>
                     </div>
                  </div>
                  <p className="trust-score-label">TRUST SCORE</p>
                  <div className="author-stats-row">
                     <div className="author-stat">
                        <span className="author-stat-value">—</span>
                        <span className="author-stat-label">Scans</span>
                     </div>
                     <div className="author-stat">
                        <span className="author-stat-value">{thread?.evidence_count || 0}</span>
                        <span className="author-stat-label">Evidence</span>
                     </div>
                     <div className="author-stat">
                        <span className="author-stat-value">—</span>
                        <span className="author-stat-label">Accuracy</span>
                     </div>
                  </div>
               </div>

               <div className="box-panel sidebar-card">
                  <p className="sidebar-label">COMMUNITY TRUST SCORE</p>
                  <div className="trust-bar-row">
                     <span className="trust-bar-label">Accuracy Rate</span>
                     <div className="trust-bar-track">
                        <div className="trust-bar-fill green" style={{ width: "91%" }} />
                     </div>
                     <span className="trust-bar-num green">91</span>
                  </div>
                  <div className="trust-bar-row">
                     <span className="trust-bar-label">Evidence Quality</span>
                     <div className="trust-bar-track">
                        <div className="trust-bar-fill orange" style={{ width: "74%" }} />
                     </div>
                     <span className="trust-bar-num orange">74</span>
                  </div>
                  <div className="trust-bar-row">
                     <span className="trust-bar-label">Vote Balance</span>
                     <div className="trust-bar-track">
                        <div className="trust-bar-fill orange" style={{ width: "67%" }} />
                     </div>
                     <span className="trust-bar-num orange">67</span>
                  </div>
                  <div className="trust-bar-row">
                     <span className="trust-bar-label">Tenure Bonus</span>
                     <div className="trust-bar-track">
                        <div className="trust-bar-fill blue" style={{ width: "82%" }} />
                     </div>
                     <span className="trust-bar-num blue">82</span>
                  </div>
                  <button className="full-breakdown-btn">Full breakdown</button>
               </div>

               <div className="box-panel sidebar-card report-row">
                  <button className="report-btn">
                     <Icons name="flag" size={14} /> Report
                  </button>
                  <button className="share-btn">
                     <Icons name="external-link" size={14} /> Share
                  </button>
               </div>
            </div>
         </div>
      </div>
      
   );
}

export default ThreadDetailPage;
