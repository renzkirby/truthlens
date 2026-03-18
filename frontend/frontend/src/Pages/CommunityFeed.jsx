import React, { useEffect, useState } from "react";
import "./CommunityFeed.css";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useNavigate } from "react-router-dom";

function timeAgo(dateString) {
   const now = new Date();
   const past = new Date(dateString);
   const seconds = Math.floor((now - past) / 1000);

   if (seconds < 60) return `${seconds}s ago`;
   if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
   if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
   return `${Math.floor(seconds / 86400)}d ago`;
}

function getActionText(verdict) {
   if (!verdict || verdict === "UNVERIFIED") return "Needs Evidence";
   if (verdict === "FACT" || verdict === "FAKE") return "Verified";
   return "Pending";
}

const CommunityFeed = () => {
   const [threads, setThreads] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const navigate = useNavigate();
   const { authFetch } = useAuth();

   useEffect(() => {
      const fetchThreads = async () => {
         try {
            const threadData = await authFetch("http://localhost:8000/api/threads/", {
               method: "GET",
            });
            setThreads(threadData);
         } catch (err) {
            setError("Failed to load threads");
         } finally {
            setLoading(false);
         }
      };
      fetchThreads();
   }, []);

   const handleThreadClick = (threadID) => {
      navigate(`/thread/detail/${threadID}`);
   };

   return (
      <div className="feed-layout">
         {/* Navbar */}
         <NavigationBar />

         {/* Main Feed Area */}
         <main className="feed-container">
            {/* Filter Bar */}
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
               <div className="search-box">
                  <Icons name="search" />
                  <input
                     type="text"
                     placeholder="Search claims..."
                  />
               </div>
            </div>

            {/* Input Bar */}
            <div className="input-bar box-panel">
               <div className="avatar-icon">
                  <Icons
                     name="user"
                     size={20}
                  />
               </div>
               <input
                  type="text"
                  placeholder="Flag a new claim for the community.."
                  className="claim-input"
               />
               <button className="snip-btn">
                  <Icons name="scissors" />
                  Snip
               </button>
            </div>

            {loading && <p>Loading threads...</p>}
            {error && <p style={{ color: "red" }}>{error}</p>}

            {/* Posts List */}
            <div className="posts-list">
               {!loading && threads.length === 0 ? (
                  <h2 className="no-threads-text">
                     No threads yet. Be the first to escalate a claim.
                  </h2>
               ) : (
                  threads.map((thread) => {
                     const verdict = thread.claim.verdict;
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
                              <strong>Flagged claim:</strong> "
                              {thread.claim.ai_summary || thread.claim.context_text}"
                           </div>

                           {/* Media Placeholder */}
                           <div
                              className="card-media"
                              onClick={() => {
                                 handleThreadClick(thread.id);
                              }}>
                              <div className="media-icon">
                                 <Icons
                                    name="globe"
                                    size={24}
                                 />
                              </div>
                              <span className="media-source">Snipped from Twitter / X</span>
                           </div>

                           {/* AI Analysis Bar */}
                           <div className={`ai-analysis-bar bar-${verdictClass}`}>
                              <div className="ai-info">
                                 <div className={`status-badge solid badge-${verdictClass}`}>
                                    {verdictClass === "misleading" && (
                                       <Icons name="alert-triangle" />
                                    )}
                                    {verdictClass === "unverified" && <Icons name="help-circle" />}
                                    {verdict}
                                 </div>
                                 <span className="ai-confidence-text">
                                    AI Confidence: <strong>{thread.claim.consensus_score}%</strong>
                                 </span>
                              </div>
                              <button className="needs-evidence-btn">
                                 {getActionText(verdict)}
                              </button>
                           </div>

                           {/* Card Footer actions */}
                           <div className="card-footer">
                              <button className="action-item">
                                 <Icons name="message-square" />
                                 Comment
                                 <span className="count-pill">{thread.comment_count}</span>
                              </button>

                              <button className="action-item primary-action">
                                 <Icons name="circle-plus" />
                                 Add Evidence
                              </button>

                              <button className="action-item">
                                 <Icons name="paperclip" />
                                 Evidence
                                 <span className="count-pill">{thread.evidence_count}</span>
                              </button>
                           </div>
                        </div>
                     );
                  })
               )}
            </div>
         </main>
      </div>
   );
};

export default CommunityFeed;
