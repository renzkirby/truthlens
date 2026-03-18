import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import "./ThreadDetailPage.css";

// Verdict config
const VERDICT_META = {
   verified: {
      color: "#0e9f6e",
      bg: "#ecfdf5",
      border: "#6ee7b7",
      icon: "check-circle",
      label: "Verified",
      desc: "This claim has been confirmed by multiple trusted sources.",
   },
   fake: {
      color: "#e02424",
      bg: "#fef2f2",
      border: "#fca5a5",
      icon: "x-circle",
      label: "Fake / False",
      desc: "This claim has been debunked by reliable fact-checkers.",
   },
   misleading: {
      color: "#d97706",
      bg: "#fffbeb",
      border: "#fde68a",
      icon: "alert-triangle",
      label: "Misleading",
      desc: "This claim contains partial truths but omits key context.",
   },
   unverified: {
      color: "#6b7280",
      bg: "#f9fafb",
      border: "#e5e7eb",
      icon: "help-circle",
      label: "Unverified",
      desc: "Insufficient evidence to confirm or deny this claim.",
   },
   satire: {
      color: "#7c3aed",
      bg: "#f5f3ff",
      border: "#c4b5fd",
      icon: "wand",
      label: "Satire",
      desc: "This content is intentional satire or parody.",
   },
};

//Helpers
function tierColor(score) {
   if (score >= 75) return "#0e9f6e";
   if (score >= 45) return "#d97706";
   return "#e02424";
}

function avatarStyle(username = "", isMod = false) {
   if (isMod) return { bg: "#d1fae5", color: "#059669" };
   const palettes = [
      { bg: "#ede9fe", color: "#7c3aed" },
      { bg: "#fce7f3", color: "#db2777" },
      { bg: "#e0f2fe", color: "#0284c7" },
      { bg: "#fef3c7", color: "#d97706" },
      { bg: "#f0fdf4", color: "#16a34a" },
   ];
   let hash = 0;
   for (let i = 0; i < username.length; i++) hash += username.charCodeAt(i);
   return palettes[hash % palettes.length];
}

//Sub-components

function VerdictBadge({ verdict }) {
   const meta = VERDICT_META[verdict] || VERDICT_META.unverified;
   return (
      <span
         className="verdict-badge"
         style={{ color: meta.color, background: meta.bg, borderColor: meta.border }}>
         <Icons
            name={meta.icon}
            size={12}
            color={meta.color}
            strokeWidth={2.5}
         />
         {meta.label}
      </span>
   );
}

function TrustGauge({ score = 0 }) {
   const r = 30;
   const circ = 2 * Math.PI * r;
   const filled = (Math.min(score, 100) / 100) * circ;
   const color = tierColor(score);
   return (
      <div className="trust-gauge-wrap">
         <svg
            width="76"
            height="76"
            viewBox="0 0 76 76">
            <circle
               cx="38"
               cy="38"
               r={r}
               fill="none"
               stroke="#f3f4f6"
               strokeWidth="7"
            />
            <circle
               cx="38"
               cy="38"
               r={r}
               fill="none"
               stroke={color}
               strokeWidth="7"
               strokeDasharray={`${filled} ${circ}`}
               strokeLinecap="round"
               transform="rotate(-90 38 38)"
            />
            <text
               x="38"
               y="43"
               textAnchor="middle"
               fontSize="15"
               fontWeight="900"
               fill="#111827">
               {score}
            </text>
         </svg>
         <span className="trust-gauge-label">TRUST SCORE</span>
      </div>
   );
}

function UserAvatar({ username = "", isMod = false, size = 36 }) {
   const style = avatarStyle(username, isMod);
   const initials = username.replace("@", "").slice(0, 1).toUpperCase();
   return (
      <div
         className="user-avatar"
         style={{
            width: size,
            height: size,
            background: style.bg,
            color: style.color,
            fontSize: size * 0.38,
         }}>
         {initials || (
            <Icons
               name="user-circle"
               size={size * 0.6}
               color={style.color}
            />
         )}
      </div>
   );
}

// Main component
function ThreadDetailPage() {
   const [thread, setThread] = useState(null);
   const [comments, setComments] = useState([]);
   const [evidenceList, setEvidenceList] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const [currentSection, setCurrentSection] = useState("comments");

   // Evidence form state
   const [showForm, setShowForm] = useState(false);
   const [evidenceUrl, setEvidenceUrl] = useState("");
   const [evidenceType, setEvidenceType] = useState("Contradicts Claim");
   const [explanation, setExplanation] = useState("");
   const [submitting, setSubmitting] = useState(false);

   // Comment input state
   const [newComment, setNewComment] = useState("");

   const { authFetch, user } = useAuth();
   const { threadId } = useParams();
   const navigate = useNavigate();
   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

   useEffect(() => {
      const fetchThread = async () => {
         try {
            const threadData = await authFetch(`${API_BASE_URL}/threads/${threadId}/`, {
               method: "GET",
            });
            setThread(threadData);
            setComments(threadData.comments || []);
            setEvidenceList(threadData.evidence_submissions || []);
         } catch (err) {
            setError("Failed to load thread.");
         } finally {
            setLoading(false);
         }
      };
      fetchThread();
   }, [threadId]);

   const verdict = thread?.verdict || "unverified";
   const vm = VERDICT_META[verdict] || VERDICT_META.unverified;

   //Evidence submit handler
   async function handleEvidenceSubmit(e) {
      e.preventDefault();
      if (!evidenceUrl.trim() || !explanation.trim()) return;
      setSubmitting(true);
      try {
         await authFetch(`${API_BASE_URL}/evidence/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               thread_id: threadId,
               evidence_url: evidenceUrl,
               evidence_type: evidenceType,
               evidence_caption: explanation,
            }),
         });

         const updated = await authFetch(`${API_BASE_URL}/threads/${threadId}/`, { method: "GET" });
         setEvidenceList(updated.evidence_submissions || []);
         setShowForm(false);
         setEvidenceUrl("");
         setExplanation("");
         setCurrentSection("evidence");
      } catch {
         setError("Error in submitting evidence");
      } finally {
         setSubmitting(false);
      }
   }

   //Comment submit handler
   async function handleCommentSubmit(e) {
      e.preventDefault();
      if (!newComment.trim()) return;
      try {
         await authFetch(`${API_BASE_URL}/comments/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: threadId, comment_text: newComment }),
         });
         const updated = await authFetch(`${API_BASE_URL}/threads/${threadId}/`, { method: "GET" });
         setComments(updated.comments || []);
         setNewComment("");
      } catch {
         setError("Error in sending comment");
      }
   }

   //Weight display
   const trustScore = user?.trust_score ?? 0;
   const weight = (1 + trustScore / 100).toFixed(1);

   if (loading) {
      return (
         <>
            <NavigationBar />
            <div className="tdp-loading">
               <div className="tdp-spinner" />
               <p>Loading thread…</p>
            </div>
         </>
      );
   }

   if (error || !thread) {
      return (
         <>
            <NavigationBar />
            <div className="tdp-error">
               <Icons
                  name="alert-triangle"
                  size={32}
                  color="#d97706"
               />
               <p>{error || "Thread not found."}</p>
               <button onClick={() => navigate("/community")}>Back to Community Feed</button>
            </div>
         </>
      );
   }

   return (
      
      <div className="thread-layout">
         <NavigationBar />

         <div className="tdp-page">
            {/*Breadcrumb bar */}
            <div
               className="tdp-breadcrumb"
               style={{ borderBottomColor: vm.color }}>
               <div className="tdp-breadcrumb-left">
                  <button
                     className="tdp-back-btn"
                     onClick={() => navigate("/community")}>
                     <Icons
                        name="globe"
                        size={13}
                        color="#4f46e5"
                     />
                     <span>Community Feed</span>
                  </button>
                  <Icons
                     name="arrow-right"
                     size={13}
                     color="#d1d5db"
                  />
                  <span className="tdp-breadcrumb-thread">Thread #{threadId}</span>
                  <span className="tdp-breadcrumb-dot">·</span>
                  <span className="tdp-breadcrumb-time">
                     Flagged {thread.created_at || thread.posted_at || "recently"} by{" "}
                     <strong>
                        {thread.flagged_by?.username ||
                           thread.original_poster?.username ||
                           "a user"}
                     </strong>
                  </span>
               </div>
               <div className="tdp-breadcrumb-right">
                  <VerdictBadge verdict={verdict} />
                  {thread.status && <span className="tdp-status-pill">{thread.status}</span>}
               </div>
            </div>

            {/*Claim Hero*/}
            <div
               className="tdp-hero"
               style={{ background: vm.bg, borderBottomColor: `${vm.color}30` }}>
               <div className="tdp-hero-inner">
                  {/* Left: claim text */}
                  <div className="tdp-hero-left">
                     <div
                        className="tdp-claim-label"
                        style={{ color: vm.color }}>
                        <Icons
                           name="flag"
                           size={11}
                           color={vm.color}
                           strokeWidth={2.5}
                        />
                        CLAIM UNDER INVESTIGATION
                     </div>
                     <h1 className="tdp-claim-text">{thread.caption}</h1>
                     <div className="tdp-claim-meta">
                        {thread.source && (
                           <span>
                              <Icons
                                 name="globe"
                                 size={12}
                                 color="#6b7280"
                              />
                              Sourced from <strong>{thread.source}</strong>
                           </span>
                        )}
                        <span>
                           <Icons
                              name="message-circle"
                              size={12}
                              color="#6b7280"
                           />
                           <strong>{comments.length}</strong> comments
                        </span>
                        <span>
                           <Icons
                              name="paperclip"
                              size={12}
                              color="#6b7280"
                           />
                           <strong>{evidenceList.length}</strong> evidence submissions
                        </span>
                     </div>
                  </div>

                  {/* Right: verdict card */}
                  <div className="tdp-verdict-card">
                     <VerdictBadge verdict={verdict} />
                     <p className="tdp-verdict-desc">{vm.desc}</p>
                     <div className="tdp-confidence">
                        <div className="tdp-confidence-row">
                           <span className="tdp-confidence-label">AI Confidence</span>
                           <span
                              className="tdp-confidence-value"
                              style={{ color: vm.color }}>
                              {thread.claim.consensus_score ?? "—"}%
                           </span>
                        </div>
                        <div className="tdp-confidence-track">
                           <div
                              className="tdp-confidence-fill"
                              style={{
                                 width: `${thread.claim.consensus_score ?? 0}%`,
                                 background: vm.color,
                              }}
                           />
                        </div>
                     </div>
                     <div className="tdp-evidence-count-row">
                        <span className="tdp-confidence-label">Evidence submissions</span>
                        <span
                           className="tdp-evidence-count-val"
                           style={{ color: vm.color }}>
                           {evidenceList.length}
                        </span>
                     </div>
                  </div>
               </div>
            </div>

            <div className="tdp-body">
               {/* Left column*/}
               <div className="tdp-main">
                  {/* Post card */}
                  <div className="tdp-post-card">
                     <div className="tdp-post-header">
                        <UserAvatar
                           username={
                              thread.original_poster?.username || thread.flagged_by?.username || ""
                           }
                           size={38}
                        />
                        <div className="tdp-post-author">
                           <span className="tdp-author-name">
                              {thread.original_poster?.username || thread.flagged_by?.username}
                           </span>
                           <div className="tdp-author-meta">
                              <span>{thread.created_at || thread.posted_at || ""}</span>
                              <span className="tdp-via-badge">
                                 <Icons
                                    name="search"
                                    size={9}
                                    color="#4f46e5"
                                 />
                                 via TruthLens
                              </span>
                           </div>
                        </div>
                        <div className="tdp-post-actions">
                           <span className="tdp-original-pill">Original post</span>
                           <a
                              href={thread.source_url || "#"}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="tdp-icon-btn">
                              <Icons
                                 name="external-link"
                                 size={14}
                                 color="#6b7280"
                              />
                           </a>
                        </div>
                     </div>
                     {/* Snipped image placeholder */}
                     <div className="tdp-snip-placeholder">
                        <div className="tdp-snip-icon-wrap">
                           <Icons
                              name="globe"
                              size={28}
                              color="#9ca3af"
                           />
                        </div>
                        <span className="tdp-snip-label">
                           Snipped from {thread.source || "external source"}
                        </span>
                     </div>
                  </div>

                  {/* Evidence submit toggle */}
                  <div className="tdp-evidence-toggle-wrap">
                     <button
                        className={`tdp-evidence-toggle-btn ${showForm ? "open" : ""}`}
                        onClick={() => setShowForm((v) => !v)}>
                        <Icons
                           name={showForm ? "x" : "paperclip"}
                           size={15}
                           color="#fff"
                           strokeWidth={2.5}
                        />
                        {showForm ? "Cancel Evidence Submission" : "Submit Evidence for This Claim"}
                     </button>

                     {/* Collapsible form */}
                     {showForm && (
                        <form
                           className="tdp-evidence-form"
                           onSubmit={handleEvidenceSubmit}>
                           <div className="tdp-evidence-form-title">
                              <Icons
                                 name="paperclip"
                                 size={13}
                                 color="#4f46e5"
                                 strokeWidth={2.5}
                              />
                              New Evidence Submission
                           </div>
                           <div className="tdp-form-row">
                              <div className="tdp-form-group">
                                 <label className="tdp-form-label">
                                    Source URL <span className="tdp-required">*</span>
                                 </label>
                                 <div className="tdp-input-wrap">
                                    <Icons
                                       name="link"
                                       size={12}
                                       color="#9ca3af"
                                    />
                                    <input
                                       type="url"
                                       className="tdp-input"
                                       placeholder="https://reliable-source.com/…"
                                       value={evidenceUrl}
                                       onChange={(e) => setEvidenceUrl(e.target.value)}
                                       required
                                    />
                                 </div>
                              </div>
                              <div className="tdp-form-group">
                                 <label className="tdp-form-label">Evidence</label>
                                 <div className="tdp-select-wrap">
                                    <select
                                       className="tdp-select"
                                       value={evidenceType}
                                       onChange={(e) => setEvidenceType(e.target.value)}>
                                       <option>Contradicts Claim</option>
                                       <option>Supports Claim</option>
                                       <option>Provides Context</option>
                                       <option>Source Verification</option>
                                    </select>
                                    <Icons
                                       name="chevron-down"
                                       size={13}
                                       color="#6b7280"
                                    />
                                 </div>
                              </div>
                           </div>
                           <div className="tdp-form-group">
                              <label className="tdp-form-label">
                                 Explanation <span className="tdp-required">*</span>
                              </label>
                              <textarea
                                 className="tdp-textarea"
                                 placeholder="Explain why this source supports or refutes the claim…"
                                 value={explanation}
                                 onChange={(e) => setExplanation(e.target.value)}
                                 rows={4}
                                 required
                              />
                           </div>
                           <div className="tdp-form-footer">
                              <span className="tdp-weight-info">
                                 <Icons
                                    name="bar-chart"
                                    size={11}
                                    color="#6b7280"
                                 />
                                 Your weight: <strong className="tdp-weight-val">×{weight}</strong>{" "}
                                 (Trust Score {trustScore})
                              </span>
                              <div className="tdp-form-btns">
                                 <button
                                    type="button"
                                    className="tdp-btn-cancel"
                                    onClick={() => setShowForm(false)}>
                                    Cancel
                                 </button>
                                 <button
                                    type="submit"
                                    className="tdp-btn-submit"
                                    disabled={submitting}>
                                    {submitting ? "Submitting…" : "Submit"}
                                    {!submitting && (
                                       <Icons
                                          name="arrow-right"
                                          size={13}
                                          strokeWidth={2.5}
                                          color="#fff"
                                       />
                                    )}
                                 </button>
                              </div>
                           </div>
                        </form>
                     )}
                  </div>

                  {/* Tabs */}
                  <div className="tdp-tabs-section">
                     <div className="tdp-tab-bar">
                        <button
                           className={`tdp-tab ${currentSection === "comments" ? "active" : ""}`}
                           onClick={() => setCurrentSection("comments")}>
                           <Icons
                              name="message-circle"
                              size={13}
                              color={currentSection === "comments" ? "#4f46e5" : "#6b7280"}
                              strokeWidth={2.5}
                           />
                           Comments ({comments.length})
                        </button>
                        <button
                           className={`tdp-tab ${currentSection === "evidence" ? "active" : ""}`}
                           onClick={() => setCurrentSection("evidence")}>
                           <Icons
                              name="paperclip"
                              size={13}
                              color={currentSection === "evidence" ? "#4f46e5" : "#6b7280"}
                              strokeWidth={2.5}
                           />
                           Evidence Board ({evidenceList.length})
                        </button>
                     </div>

                     {/*Comments tab*/}
                     {currentSection === "comments" && (
                        <div className="tdp-tab-content">
                           {/* Comment input */}
                           <form
                              className="tdp-comment-input-row"
                              onSubmit={handleCommentSubmit}>
                              <UserAvatar
                                 username={user?.username || ""}
                                 size={34}
                              />
                              <input
                                 type="text"
                                 className="tdp-comment-input"
                                 placeholder="Write a comment…"
                                 value={newComment}
                                 onChange={(e) => setNewComment(e.target.value)}
                              />
                              {newComment.trim() && (
                                 <button
                                    type="submit"
                                    className="tdp-comment-submit">
                                    <Icons
                                       name="send"
                                       size={14}
                                       color="#fff"
                                    />
                                 </button>
                              )}
                           </form>

                           {/* Comment list */}
                           <div className="tdp-comment-list">
                              {comments.length === 0 && (
                                 <p className="tdp-empty">No comments yet. Be the first!</p>
                              )}
                              {comments.map((comment, i) => {
                                 const isMod = comment.commenter?.is_moderator;
                                 const username = comment.commenter?.username || "Unknown";
                                 return (
                                    <div
                                       key={comment.id || i}
                                       className="tdp-comment-item">
                                       <UserAvatar
                                          username={username}
                                          isMod={isMod}
                                          size={34}
                                       />
                                       <div className="tdp-comment-body">
                                          <div className="tdp-comment-bubble">
                                             <div className="tdp-comment-header">
                                                <span className="tdp-comment-user">{username}</span>
                                                {isMod && (
                                                   <span className="tdp-mod-badge">
                                                      <Icons
                                                         name="shield"
                                                         size={8}
                                                         color="#059669"
                                                         strokeWidth={2.5}
                                                      />
                                                      MOD
                                                   </span>
                                                )}
                                                <span className="tdp-comment-time">
                                                   {comment.created_at || comment.timestamp || ""}
                                                </span>
                                             </div>
                                             <p className="tdp-comment-text">
                                                {comment.comment_text}
                                             </p>
                                          </div>
                                          <div className="tdp-comment-actions">
                                             <button className="tdp-comment-like">
                                                <Icons
                                                   name="thumbs-up"
                                                   size={11}
                                                   color="#6b7280"
                                                   strokeWidth={2}
                                                />
                                                {comment.likes ?? 0}
                                             </button>
                                             <button className="tdp-comment-reply">Reply</button>
                                          </div>
                                       </div>
                                    </div>
                                 );
                              })}
                           </div>

                           {comments.length > 5 && (
                              <button className="tdp-see-more">See More…</button>
                           )}
                        </div>
                     )}

                     {/*Evidence Board tab*/}
                     {currentSection === "evidence" && (
                        <div className="tdp-tab-content">
                           <div className="tdp-evidence-sort-row">
                              <span>
                                 <Icons
                                    name="bar-chart"
                                    size={12}
                                    color="#6b7280"
                                 />
                                 Sorted by weighted trust score
                              </span>
                              <span className="tdp-formula">
                                 weighted = (up × trust/100) − (down × 0.5)
                              </span>
                           </div>

                           {evidenceList.length === 0 && (
                              <p className="tdp-empty">
                                 No evidence yet.{" "}
                                 <button
                                    className="tdp-empty-link"
                                    onClick={() => setShowForm(true)}>
                                    Be the first to submit evidence.
                                 </button>
                              </p>
                           )}

                           {evidenceList.map((ev, i) => {
                              const score = ev.contributor?.trust_score ?? 0;
                              const tc = tierColor(score);
                              const isTop = i === 0 && evidenceList.length > 1;
                              const weighted =
                                 ev.weighted_score ??
                                 (ev.upvotes * (score / 100) - ev.downvotes * 0.5).toFixed(1);
                              return (
                                 <div
                                    key={ev.id || i}
                                    className="tdp-evidence-card"
                                    style={{ borderLeftColor: tc }}>
                                    <div className="tdp-evidence-card-header">
                                       <div className="tdp-evidence-contributor">
                                          <UserAvatar
                                             username={ev.contributor?.username || ""}
                                             size={30}
                                          />
                                          <div>
                                             <div className="tdp-ev-username">
                                                {ev.contributor?.username}
                                             </div>
                                             <div
                                                className="tdp-ev-trust"
                                                style={{ color: tc }}>
                                                <Icons
                                                   name="badge-check"
                                                   size={9}
                                                   color={tc}
                                                />
                                                Trust: <strong>{score}</strong>
                                             </div>
                                          </div>
                                       </div>
                                       <div className="tdp-evidence-card-right">
                                          {isTop && (
                                             <span className="tdp-top-badge">
                                                <Icons
                                                   name="star"
                                                   size={8}
                                                   strokeWidth={2.5}
                                                   color="#065f46"
                                                />
                                                Top
                                             </span>
                                          )}
                                          {ev.evidence_url && (
                                             <a
                                                href={ev.evidence_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="tdp-source-link">
                                                <Icons
                                                   name="external-link"
                                                   size={10}
                                                   color="#4f46e5"
                                                />
                                                {ev.evidence_url
                                                   .replace(/^https?:\/\//, "")
                                                   .slice(0, 28)}
                                                {ev.evidence_url.length > 40 ? "…" : ""}
                                             </a>
                                          )}
                                       </div>
                                    </div>
                                    <p className="tdp-evidence-text">{ev.evidence_caption}</p>
                                    <div className="tdp-evidence-votes">
                                       <button className="tdp-vote-btn up">
                                          <Icons
                                             name="chevron-up"
                                             size={13}
                                             strokeWidth={2.5}
                                             color="#166534"
                                          />
                                          {ev.upvotes ?? 0}
                                       </button>
                                       <button className="tdp-vote-btn down">
                                          <Icons
                                             name="chevron-down"
                                             size={13}
                                             strokeWidth={2.5}
                                             color="#991b1b"
                                          />
                                          {ev.downvotes ?? 0}
                                       </button>
                                       <span className="tdp-weighted-score">
                                          <Icons
                                             name="hash"
                                             size={9}
                                             color="#6b7280"
                                          />
                                          Weighted: {weighted}
                                       </span>
                                    </div>
                                 </div>
                              );
                           })}

                           {evidenceList.length > 5 && (
                              <button className="tdp-see-more">See More…</button>
                           )}
                        </div>
                     )}
                  </div>
               </div>

               {/*Right sidebar*/}
               <aside className="tdp-sidebar">
                  {/* Posted by */}
                  <div className="tdp-sidebar-card">
                     <div className="tdp-sidebar-card-label">POSTED BY</div>
                     <div className="tdp-posted-by-row">
                        <UserAvatar
                           username={thread.flagged_by?.username || ""}
                           size={44}
                        />
                        <div className="tdp-posted-by-info">
                           <div className="tdp-posted-by-name">
                              {thread.flagged_by?.username || "Unknown"}
                           </div>
                           {thread.flagged_by?.is_trusted_contributor && (
                              <div className="tdp-trusted-label">
                                 <Icons
                                    name="badge-check"
                                    size={11}
                                    color="#0e9f6e"
                                 />
                                 Trusted Contributor
                              </div>
                           )}
                        </div>
                        <TrustGauge score={thread.flagged_by?.trust_score ?? 0} />
                     </div>
                     <div className="tdp-poster-stats">
                        <div className="tdp-poster-stat">
                           <span className="tdp-stat-val">
                              {thread.flagged_by?.total_scans ?? "—"}
                           </span>
                           <span className="tdp-stat-lbl">Scans</span>
                        </div>
                        <div className="tdp-poster-stat">
                           <span className="tdp-stat-val">
                              {thread.flagged_by?.total_evidence ?? "—"}
                           </span>
                           <span className="tdp-stat-lbl">Evidence</span>
                        </div>
                        <div className="tdp-poster-stat">
                           <span className="tdp-stat-val">
                              {thread.flagged_by?.accuracy_percentage != null
                                 ? `${thread.flagged_by.accuracy_percentage}%`
                                 : "—"}
                           </span>
                           <span className="tdp-stat-lbl">Accuracy</span>
                        </div>
                     </div>
                  </div>

                  {/* Community Trust Score */}
                  <div className="tdp-sidebar-card">
                     <div className="tdp-sidebar-card-label">COMMUNITY TRUST SCORE</div>
                     {[
                        {
                           label: "Accuracy Rate",
                           score: thread.flagged_by?.accuracy_rate ?? 0,
                           color: "#0e9f6e",
                        },
                        {
                           label: "Evidence Quality",
                           score: thread.flagged_by?.evidence_quality ?? 0,
                           color: "#d97706",
                        },
                        {
                           label: "Vote Balance",
                           score: thread.flagged_by?.vote_balance ?? 0,
                           color: "#d97706",
                        },
                        {
                           label: "Tenure Bonus",
                           score: thread.flagged_by?.tenure_bonus ?? 0,
                           color: "#4f46e5",
                        },
                     ].map(({ label, score, color }) => (
                        <div
                           key={label}
                           className="tdp-trust-row">
                           <div className="tdp-trust-row-header">
                              <span className="tdp-trust-row-label">{label}</span>
                              <span
                                 className="tdp-trust-row-val"
                                 style={{ color }}>
                                 {score}
                              </span>
                           </div>
                           <div className="tdp-trust-track">
                              <div
                                 className="tdp-trust-fill"
                                 style={{ width: `${score}%`, background: color }}
                              />
                           </div>
                        </div>
                     ))}
                     <button className="tdp-full-breakdown">Full breakdown</button>
                  </div>

                  {/* Related claims */}
                  {thread.related_claims?.length > 0 && (
                     <div className="tdp-sidebar-card">
                        <div className="tdp-sidebar-card-label">RELATED CLAIMS</div>
                        {thread.related_claims.map((rc, i) => (
                           <div
                              key={rc.id || i}
                              className={`tdp-related-claim ${i < thread.related_claims.length - 1 ? "bordered" : ""}`}>
                              <VerdictBadge verdict={rc.verdict} />
                              <p className="tdp-related-text">{rc.caption}</p>
                           </div>
                        ))}
                     </div>
                  )}

                  {/* Report / Share */}
                  <div className="tdp-sidebar-actions">
                     <button className="tdp-report-btn">
                        <Icons
                           name="flag"
                           size={13}
                           color="#e02424"
                           strokeWidth={2.5}
                        />
                        Report
                     </button>
                     <button className="tdp-share-btn">
                        <Icons
                           name="external-link"
                           size={13}
                           color="#6b7280"
                           strokeWidth={2}
                        />
                        Share
                     </button>
                  </div>
               </aside>
            </div>
         </div>
      </div>
   );
}

export default ThreadDetailPage;
