/**
 * Thread Detail Page
 * ══════════════════════════════════════════════════════════════════
 * Displays full thread discussion including claim verdict, evidence, and comments.
 *
 * Features:
 *   - Full claim information with AI verdict and verdict badge
 *   - Evidence collection (user-submitted supporting/contradicting evidence)
 *   - Comment thread for discussion
 *   - User reputation/trust scores
 *   - Evidence and comment editing capabilities
 *
 * Sections:
 *   - Main verdict display with AI analysis
 *   - Evidence tab: Browse and submit supporting/contradicting evidence
 *   - Comments tab: Read and participate in discussion
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useNotification } from "../context/NotificationContext";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import EvidenceCard from "../components/EvidenceCard";

// ── Utilities & Constants ──
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_CONFIG, VERDICT_META, EVIDENCE_VERDICT_META } from "../utils/constants";
import timeAgo from "../utils/timeAgo";

// ── Styles ──
import "./ThreadDetailPage.css";

/**
 * Get trust score display color based on tier
 * @param {number} score - Trust score (0-100)
 * @returns {string} Hex color for the tier
 */
function tierColor(score) {
   if (score >= 75) return "#0e9f6e"; // Green: High trust
   if (score >= 45) return "#d97706"; // Orange: Medium trust
   return "#e02424"; // Red: Low trust
}

/**
 * Generate user avatar background/text colors deterministically from username
 * @param {string} username - Username to hash
 * @param {boolean} isMod - Whether user is a moderator
 * @returns {object} { bg, color } for avatar styling
 */
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

// ── Sub-components ──

/**
 * VerdictBadge: Display formatted verdict with icon and color
 */
function VerdictBadge({ verdict }) {
   const meta = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNVERIFIED;
   return (
      <span
         className="verdict-badge"
         style={{
            color: meta.color,
            background: meta.bg,
            borderColor: meta.border,
         }}>
         <Icons
            name={meta.icon || "help-circle"}
            size={12}
            color={meta.color}
            strokeWidth={2.5}
         />
         {meta.label}
      </span>
   );
}

/**
 * TrustGauge: SVG circular progress bar showing trust score
 */
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

/**
 * UserAvatar: Colored circle with user initials
 */
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

const ThreadDetailSkeleton = () => {
   return (
      <div className="thread-layout">
         <NavigationBar />
         <div className="tdp-page">
            <div className="tdp-breadcrumb" style={{ borderBottomColor: "var(--border-default)" }}>
               <div className="tdp-breadcrumb-left" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <div className="skeleton-box" style={{ width: "120px", height: "16px" }}></div>
                  <span className="tdp-breadcrumb-dot">·</span>
                  <div className="skeleton-box" style={{ width: "100px", height: "16px" }}></div>
                  <span className="tdp-breadcrumb-dot">·</span>
                  <div className="skeleton-box" style={{ width: "200px", height: "16px" }}></div>
               </div>
               <div className="tdp-breadcrumb-right">
                  <div className="skeleton-box" style={{ width: "80px", height: "24px", borderRadius: "12px" }}></div>
               </div>
            </div>

            <div className="tdp-hero" style={{ background: "var(--bg-surface)", borderBottomColor: "var(--border-default)" }}>
               <div className="tdp-hero-inner">
                  <div className="tdp-hero-left" style={{ display: "flex", flexDirection: "column", gap: "12px", width: "100%" }}>
                     <div className="skeleton-box" style={{ width: "200px", height: "14px" }}></div>
                     <div className="skeleton-box" style={{ width: "100%", height: "28px", marginTop: "8px" }}></div>
                     <div className="skeleton-box" style={{ width: "80%", height: "28px" }}></div>
                     <div className="tdp-claim-meta" style={{ marginTop: "16px", display: "flex", gap: "16px" }}>
                        <div className="skeleton-box" style={{ width: "150px", height: "14px" }}></div>
                        <div className="skeleton-box" style={{ width: "100px", height: "14px" }}></div>
                        <div className="skeleton-box" style={{ width: "160px", height: "14px" }}></div>
                     </div>
                  </div>
                  <div className="tdp-verdict-card" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                     <div className="skeleton-box" style={{ width: "100px", height: "28px", borderRadius: "20px" }}></div>
                     <div className="skeleton-box" style={{ width: "100%", height: "14px", marginTop: "8px" }}></div>
                     <div className="skeleton-box" style={{ width: "90%", height: "14px" }}></div>
                     <div style={{ display: "flex", justifyContent: "space-between", marginTop: "16px" }}>
                        <div className="skeleton-box" style={{ width: "120px", height: "14px" }}></div>
                        <div className="skeleton-box" style={{ width: "40px", height: "14px" }}></div>
                     </div>
                  </div>
               </div>
            </div>

            <div className="tdp-body">
               <div className="tdp-main">
                  <div className="tdp-post-card">
                     <div className="tdp-post-header">
                        <div className="author-avatar skeleton-box" style={{ width: "38px", height: "38px", borderRadius: "50%" }}></div>
                        <div className="tdp-post-author" style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                           <div className="skeleton-box" style={{ width: "120px", height: "16px" }}></div>
                           <div className="skeleton-box" style={{ width: "160px", height: "12px" }}></div>
                        </div>
                        <div className="tdp-post-actions">
                           <div className="skeleton-box" style={{ width: "100px", height: "24px", borderRadius: "12px" }}></div>
                        </div>
                     </div>
                     <div className="tdp-snip-placeholder skeleton-box" style={{ height: "300px", width: "100%", borderRadius: "12px", border: "none" }}></div>
                  </div>
                  <div className="tdp-tabs-section" style={{ marginTop: "24px" }}>
                     <div className="tdp-tab-bar" style={{ display: "flex", gap: "16px", borderBottom: "2px solid var(--border-default)", paddingBottom: "12px" }}>
                        <div className="skeleton-box" style={{ width: "100px", height: "24px" }}></div>
                        <div className="skeleton-box" style={{ width: "100px", height: "24px" }}></div>
                     </div>
                     <div style={{ marginTop: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
                        <div className="skeleton-box" style={{ width: "100%", height: "120px", borderRadius: "12px" }}></div>
                        <div className="skeleton-box" style={{ width: "100%", height: "120px", borderRadius: "12px" }}></div>
                     </div>
                  </div>
               </div>
            </div>
         </div>
      </div>
   );
};

function ThreadDetailPage() {
   const [searchParams, setSearchParams] = useSearchParams();
   const initialTab = searchParams.get("tab") === "evidence" ? "evidence" : "comments";
   const [thread, setThread] = useState(null);
   const [comments, setComments] = useState([]);
   const [evidenceList, setEvidenceList] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const [currentSection, setCurrentSection] = useState(initialTab);

   // Evidence form state
   const [showForm, setShowForm] = useState(false);
   const [evidenceUrl, setEvidenceUrl] = useState("");
   const [evidenceType, setEvidenceType] = useState("CONTRADICTS CLAIM");
   const [explanation, setExplanation] = useState("");
   const [evidenceVerdict, setEvidenceVerdict] = useState("UNVERIFIED");
   const [submitting, setSubmitting] = useState(false);

   // Comment input state
   const [newComment, setNewComment] = useState("");
   const [editingCommentId, setEditingCommentId] = useState(null);
   const [editingCommentText, setEditingCommentText] = useState("");
   const [editingEvidenceId, setEditingEvidenceId] = useState(null);
   const [editingEvidenceText, setEditingEvidenceText] = useState("");
   const [editingEvidenceVerdict, setEditingEvidenceVerdict] = useState("UNVERIFIED");
   const [votingEvidenceId, setVotingEvidenceId] = useState(null);
   const [reporting, setReporting] = useState(false);
   const [confirmDialog, setConfirmDialog] = useState({
      open: false,
      type: null,
      targetId: null,
   });
   const [reportDialogOpen, setReportDialogOpen] = useState(false);
   const [reportReason, setReportReason] = useState("OTHER");
   const [reportNotes, setReportNotes] = useState("");
   const tabsSectionRef = useRef(null);
   const didAutoScrollRef = useRef(false);

   const { authFetch, user } = useAuth();
   const { addToast } = useNotification();
   const isModerator = user?.role === "MOD" || user?.role === "MODERATOR";
   const { threadId } = useParams();
   const navigate = useNavigate();
   const apiUrl = (path) =>
      `${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api"}/${path}`;

   // ── Fetch thread data from API ──
   const refreshThreadData = async () => {
      const threadData = await authFetch(apiUrl(`threads/${threadId}/`), {
         method: "GET",
      });
      setThread(threadData);
      setComments(threadData.comments || []);
      setEvidenceList(threadData.evidence_submissions || []);
   };

   useEffect(() => {
      const fetchThread = async () => {
         try {
            await refreshThreadData();
         } catch (err) {
            setError("Failed to load thread.");
         } finally {
            setLoading(false);
         }
      };
      fetchThread();
   }, [threadId]);

   useEffect(() => {
      didAutoScrollRef.current = false;
   }, [threadId]);

   useEffect(() => {
      const tabFromQuery = searchParams.get("tab");
      const openEvidenceFormFromQuery = searchParams.get("openForm") === "evidence";
      const normalizedTab =
         tabFromQuery === "evidence" || openEvidenceFormFromQuery ? "evidence" : "comments";
      setCurrentSection(normalizedTab);

      if (openEvidenceFormFromQuery) {
         setShowForm(true);
      }

      if (!loading && tabFromQuery && tabsSectionRef.current && !didAutoScrollRef.current) {
         const prefersReducedMotion =
            typeof window !== "undefined" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches;
         tabsSectionRef.current.scrollIntoView({
            behavior: prefersReducedMotion ? "auto" : "smooth",
            block: "start",
         });
         didAutoScrollRef.current = true;
      }
   }, [searchParams, loading]);

   const handleSectionChange = (section) => {
      setCurrentSection(section);
      setSearchParams({ tab: section });
   };

   const verdict = (getEffectiveVerdict(thread?.claim) || "UNVERIFIED").toLowerCase();
   const vm = VERDICT_META[verdict] || VERDICT_META.unverified;
   const sortedComments = [...comments].sort((a, b) => {
      const aTime = new Date(a?.commented_at || a?.created_at || a?.timestamp || 0).getTime();
      const bTime = new Date(b?.commented_at || b?.created_at || b?.timestamp || 0).getTime();
      return bTime - aTime;
   });
   const evidenceTypeTone = (() => {
      if (evidenceType.includes("SUPPORT")) return "is-supports";
      if (evidenceType.includes("CONTRADICT")) return "is-contradicts";
      if (evidenceType.includes("CONTEXT")) return "is-context";
      if (evidenceType.includes("VERIFICATION")) return "is-verification";
      return "is-neutral";
   })();
   const confirmActionMeta = useMemo(() => {
      if (confirmDialog.type === "comment") {
         return {
            code: "REMOVE COMMENT",
            title: "Policy Action: Remove Comment",
            description: "This comment will be permanently removed from the discussion thread.",
            cta: "Confirm Remove",
         };
      }

      return {
         code: "REMOVE EVIDENCE",
         title: "Policy Action: Remove Evidence",
         description: "This evidence item will be permanently removed from the thread.",
         cta: "Confirm Remove",
      };
   }, [confirmDialog.type]);

   const reportActionMeta = {
      code: "REPORT THREAD",
      title: "Policy Action: Report Thread",
      description: "Submit a report so moderators can investigate this thread for policy concerns.",
      cta: "Submit Report",
   };

   //Evidence submit handler
   async function handleEvidenceSubmit(e) {
      e.preventDefault();
      if (!evidenceUrl.trim() || !explanation.trim()) return;
      setSubmitting(true);
      try {
         const payload = {
            thread_id: threadId,
            evidence_url: evidenceUrl,
            evidence_type: evidenceType,
            evidence_verdict: evidenceVerdict,
            evidence_caption: explanation,
         };

         await authFetch(apiUrl("evidence/"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
         });

         addToast({
            type: "success",
            message: "Evidence submitted successfully!",
            duration: 3000,
         });

         await refreshThreadData();
         setShowForm(false);
         setEvidenceUrl("");
         setExplanation("");
         setEvidenceVerdict("UNVERIFIED");
         handleSectionChange("evidence");
      } catch (error) {
         console.error("Error submitting evidence:", error);
         addToast({
            type: "error",
            message: `Error submitting evidence: ${error.message || "Unknown error"}`,
         });
         setError(`Error: ${error.message}`);
      } finally {
         setSubmitting(false);
      }
   }

   //Comment submit handler
   async function handleCommentSubmit(e) {
      e.preventDefault();
      const trimmedComment = newComment.trim();
      if (!trimmedComment) return;

      const optimisticId = `optimistic-${Date.now()}`;
      const optimisticComment = {
         id: optimisticId,
         comment_text: trimmedComment,
         commenter: {
            id: user?.id,
            username: user?.username || "You",
            role: user?.role || null,
         },
         commented_at: new Date().toISOString(),
         likes: 0,
      };

      const previousComments = comments;
      const previousCommentCount = Number(thread?.comment_count ?? comments.length);

      setComments((prev) => [optimisticComment, ...prev]);
      setThread((prev) => {
         if (!prev) return prev;
         return {
            ...prev,
            comment_count: previousCommentCount + 1,
         };
      });
      setNewComment("");

      try {
         const createdComment = await authFetch(apiUrl("comments/"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thread_id: threadId, comment_text: trimmedComment }),
         });

         setComments((prev) =>
            prev.map((comment) => (comment.id === optimisticId ? createdComment : comment)),
         );

         addToast({
            type: "success",
            message: "Comment posted successfully!",
            duration: 2000,
         });
      } catch (error) {
         setComments(previousComments);
         setThread((prev) => {
            if (!prev) return prev;
            return {
               ...prev,
               comment_count: previousCommentCount,
            };
         });
         setNewComment(trimmedComment);
         console.error("Error posting comment:", error);
         addToast({
            type: "error",
            message: "Failed to post comment",
         });
      }
   }

   async function handleDeleteComment(commentId, shouldProceed = false) {
      if (!shouldProceed) {
         setConfirmDialog({ open: true, type: "comment", targetId: commentId });
         return;
      }

      const previousComments = comments;
      const previousCommentCount = Number(thread?.comment_count ?? comments.length);
      const hasComment = comments.some((comment) => comment.id === commentId);

      if (hasComment) {
         setComments((prev) => prev.filter((comment) => comment.id !== commentId));
         setThread((prev) => {
            if (!prev) return prev;
            return {
               ...prev,
               comment_count: Math.max(0, previousCommentCount - 1),
            };
         });
      }

      try {
         await authFetch(apiUrl(`comments/${commentId}/`), {
            method: "DELETE",
         });
         addToast({
            type: "success",
            message: "Comment deleted successfully",
            duration: 2000,
         });
      } catch (error) {
         if (hasComment) {
            setComments(previousComments);
            setThread((prev) => {
               if (!prev) return prev;
               return {
                  ...prev,
                  comment_count: previousCommentCount,
               };
            });
         }
         console.error("Error deleting comment:", error);
         addToast({
            type: "error",
            message: "Failed to delete comment",
         });
      }
   }

   async function handleSaveCommentEdit(commentId) {
      const trimmedComment = editingCommentText.trim();
      if (!trimmedComment) return;

      const previousComments = comments;
      setComments((prev) =>
         prev.map((comment) =>
            comment.id === commentId ? { ...comment, comment_text: trimmedComment } : comment,
         ),
      );
      setEditingCommentId(null);
      setEditingCommentText("");

      try {
         const updatedComment = await authFetch(apiUrl(`comments/${commentId}/`), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ comment_text: trimmedComment }),
         });

         setComments((prev) =>
            prev.map((comment) =>
               comment.id === commentId ? { ...comment, ...updatedComment } : comment,
            ),
         );

         addToast({
            type: "success",
            message: "Comment updated successfully",
            duration: 2000,
         });
      } catch (error) {
         setComments(previousComments);
         setEditingCommentId(commentId);
         setEditingCommentText(trimmedComment);
         console.error("Error editing comment:", error);
         addToast({
            type: "error",
            message: "Failed to update comment",
         });
      }
   }

   async function handleDeleteEvidence(evidenceId, shouldProceed = false) {
      if (!shouldProceed) {
         setConfirmDialog({ open: true, type: "evidence", targetId: evidenceId });
         return;
      }
      try {
         await authFetch(apiUrl(`evidence/${evidenceId}/`), {
            method: "DELETE",
         });
         addToast({
            type: "success",
            message: "Evidence deleted successfully",
            duration: 2000,
         });
         await refreshThreadData();
      } catch (error) {
         console.error("Error deleting evidence:", error);
         addToast({
            type: "error",
            message: "Failed to delete evidence",
         });
      }
   }

   async function handleSaveEvidenceEdit(evidenceId) {
      if (!editingEvidenceText.trim()) return;
      try {
         await authFetch(apiUrl(`evidence/${evidenceId}/`), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               evidence_caption: editingEvidenceText,
               evidence_verdict: editingEvidenceVerdict,
            }),
         });
         addToast({
            type: "success",
            message: "Evidence updated successfully",
            duration: 2000,
         });
         await refreshThreadData();
         setEditingEvidenceId(null);
         setEditingEvidenceText("");
         setEditingEvidenceVerdict("UNVERIFIED");
      } catch (error) {
         console.error("Error editing evidence:", error);
         addToast({
            type: "error",
            message: "Failed to update evidence",
         });
      }
   }

   function handleReportThread() {
      if (!thread?.id || reporting) return;
      setReportDialogOpen(true);
   }

   async function submitReportThread() {
      const reasonInput = reportReason?.trim().toUpperCase();
      if (!reasonInput) return;

      const allowedReasons = new Set(["INAPPROPRIATE", "SPAM", "HARASSMENT", "OTHER"]);
      if (!allowedReasons.has(reasonInput)) {
         addToast({
            type: "error",
            message: "Invalid reason. Use INAPPROPRIATE, SPAM, HARASSMENT, or OTHER.",
         });
         return;
      }

      setReporting(true);
      try {
         await authFetch(apiUrl("thread-flags/"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               thread_id: thread.id,
               reason: reasonInput,
               notes: reportNotes.trim(),
            }),
         });

         addToast({
            type: "success",
            message: "Thread reported. Moderators have been notified.",
            duration: 2500,
         });

         setReportDialogOpen(false);
         setReportReason("OTHER");
         setReportNotes("");
         await refreshThreadData();
      } catch (reportError) {
         addToast({
            type: "error",
            message: reportError?.message || "Failed to report thread.",
         });
      } finally {
         setReporting(false);
      }
   }

   async function handleVote(evidence, nextVoteValue) {
      if (!evidence?.id) return;

      if (evidence?.contributor?.id === user?.id) {
         addToast({
            type: "error",
            message: "You cannot vote on your own evidence.",
         });
         return;
      }

      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
      setVotingEvidenceId(evidence.id);

      const previousEvidenceList = evidenceList;
      const previousThreadEvidence = thread?.evidence_submissions || [];

      const applyOptimisticVote = (item) => {
         if (!item || item.id !== evidence.id) return item;

         const upvotes = Number(item.upvotes || 0);
         const downvotes = Number(item.downvotes || 0);
         const currentVote = item.my_vote?.vote_value;

         let nextUpvotes = upvotes;
         let nextDownvotes = downvotes;
         let nextMyVote = item.my_vote || null;

         if (!item.my_vote) {
            if (nextVoteValue) nextUpvotes += 1;
            else nextDownvotes += 1;
            nextMyVote = { id: "optimistic", vote_value: nextVoteValue };
         } else if (currentVote === nextVoteValue) {
            if (currentVote) nextUpvotes = Math.max(0, upvotes - 1);
            else nextDownvotes = Math.max(0, downvotes - 1);
            nextMyVote = null;
         } else {
            if (currentVote) {
               nextUpvotes = Math.max(0, upvotes - 1);
               nextDownvotes += 1;
            } else {
               nextDownvotes = Math.max(0, downvotes - 1);
               nextUpvotes += 1;
            }
            nextMyVote = { ...(item.my_vote || {}), vote_value: nextVoteValue };
         }

         const contributorTrust = Number(item.contributor?.trust_score || 0);
         const nextWeighted = Number(
            (nextUpvotes * (contributorTrust / 100) - nextDownvotes * 0.5).toFixed(2),
         );

         return {
            ...item,
            upvotes: nextUpvotes,
            downvotes: nextDownvotes,
            my_vote: nextMyVote,
            weighted_score: nextWeighted,
         };
      };

      setEvidenceList((prev) => prev.map(applyOptimisticVote));
      setThread((prev) => {
         if (!prev) return prev;
         return {
            ...prev,
            evidence_submissions: (prev.evidence_submissions || []).map(applyOptimisticVote),
         };
      });

      try {
         const myVote = evidence.my_vote;

         if (!myVote) {
            await authFetch(`${API_BASE_URL}/votes/`, {
               method: "POST",
               headers: { "Content-Type": "application/json" },
               body: JSON.stringify({
                  evidence: evidence.id,
                  vote_value: nextVoteValue,
               }),
            });
         } else if (myVote.vote_value === nextVoteValue) {
            await authFetch(`${API_BASE_URL}/votes/${myVote.id}/`, {
               method: "DELETE",
            });
         } else {
            await authFetch(`${API_BASE_URL}/votes/${myVote.id}/`, {
               method: "PATCH",
               headers: { "Content-Type": "application/json" },
               body: JSON.stringify({ vote_value: nextVoteValue }),
            });
         }

         await refreshThreadData();
      } catch (voteError) {
         setEvidenceList(previousEvidenceList);
         setThread((prev) => {
            if (!prev) return prev;
            return {
               ...prev,
               evidence_submissions: previousThreadEvidence,
            };
         });
         addToast({
            type: "error",
            message: voteError?.message || "Failed to cast vote.",
         });
      } finally {
         setVotingEvidenceId(null);
      }
   }

   async function handleConfirmAction() {
      const { type, targetId } = confirmDialog;
      if (!type || !targetId) return;

      setConfirmDialog({ open: false, type: null, targetId: null });
      if (type === "comment") {
         await handleDeleteComment(targetId, true);
      } else if (type === "evidence") {
         await handleDeleteEvidence(targetId, true);
      }
   }

   //Weight display
   const trustScore = Number(user?.trust_breakdown?.trust_score ?? user?.trust_score ?? 0);
   const weight = (1 + trustScore / 100).toFixed(1);
   const authorTrustBreakdown = thread?.author?.trust_breakdown || {};

   if (loading) {
      return <ThreadDetailSkeleton />;
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
                     onClick={() => navigate(-1)}>
                     <Icons
                        name="arrow-left"
                        size={14}
                     />
                     Community Feed
                  </button>

                  <span className="tdp-breadcrumb-dot">·</span>

                  <span className="tdp-breadcrumb-thread">
                     Thread #{thread.display_id ? thread.display_id : thread.id.substring(0, 6)}
                  </span>

                  <span className="tdp-breadcrumb-dot">·</span>

                  <span className="tdp-breadcrumb-time">
                     Started{" "}
                     {new Date(thread.created_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                     })}{" "}
                     by <strong>@{thread.author?.username || "unknown"}</strong>
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
                     {thread.claim?.moderator_verdict_info ? (
                        // MODERATOR VERDICT VERSION
                        <>
                           <div style={{ marginBottom: "12px" }}>
                              <span
                                 style={{
                                    fontSize: "11px",
                                    fontWeight: "600",
                                    color: "#6b7280",
                                    textTransform: "uppercase",
                                    letterSpacing: "0.05em",
                                 }}>
                                 Final Verdict (Moderator-Verified)
                              </span>
                           </div>
                           <VerdictBadge
                              verdict={thread.claim.moderator_verdict_info.verdict.toUpperCase()}
                           />
                           <p className="tdp-verdict-desc">
                              {VERDICT_META[
                                 thread.claim.moderator_verdict_info.verdict.toLowerCase()
                              ]?.desc || "Moderators have reviewed the evidence."}
                           </p>
                           <div className="tdp-evidence-count-row">
                              <span className="tdp-confidence-label">Verified Evidence</span>
                              <span
                                 className="tdp-evidence-count-val"
                                 style={{ color: "#10b981" }}>
                                 {thread.claim.moderator_verdict_info.verified_evidence_count} item
                                 {thread.claim.moderator_verdict_info.verified_evidence_count !== 1
                                    ? "s"
                                    : ""}
                              </span>
                           </div>

                           {/* REFINEMENT #9: Evidence Breakdown for MISLEADING verdicts */}
                           {thread.claim.moderator_verdict_info.verdict === "MISLEADING" && (
                              <div
                                 style={{
                                    marginTop: "12px",
                                    padding: "10px",
                                    backgroundColor: "#fef3c7",
                                    borderRadius: "6px",
                                    fontSize: "12px",
                                 }}>
                                 <span style={{ color: "#92400e", fontWeight: "500" }}>
                                    Mixed Evidence:
                                 </span>
                                 <div style={{ marginTop: "6px", color: "#78350f" }}>
                                    <div>Some evidence supports</div>
                                    <div>Some evidence contradicts</div>
                                    <div style={{ marginTop: "4px", fontSize: "11px" }}>
                                       This claim is partially accurate
                                    </div>
                                 </div>
                              </div>
                           )}
                        </>
                     ) : thread.claim?.verified_evidence_count > 0 &&
                       !thread.claim?.moderator_verdict_info ? (
                        // REFINEMENT #7: Pending Consensus - Evidence Under Review
                        <>
                           <div style={{ marginBottom: "12px" }}>
                              <span
                                 style={{
                                    fontSize: "11px",
                                    fontWeight: "600",
                                    color: "#d97706",
                                    textTransform: "uppercase",
                                    letterSpacing: "0.05em",
                                 }}>
                                 Verdict Pending
                              </span>
                           </div>
                           <VerdictBadge verdict="unverified" />
                           <p className="tdp-verdict-desc">Evidence under review by moderators</p>
                           <div className="tdp-evidence-count-row">
                              <span className="tdp-confidence-label">Evidence Under Review</span>
                              <span
                                 className="tdp-evidence-count-val"
                                 style={{ color: "#d97706" }}>
                                 {thread.claim.verified_evidence_count} item
                                 {thread.claim.verified_evidence_count !== 1 ? "s" : ""}
                              </span>
                           </div>
                           <p
                              style={{
                                 marginTop: "10px",
                                 fontSize: "12px",
                                 color: "#9ca3af",
                                 fontStyle: "italic",
                              }}>
                              Final verdict will be determined once moderators reach consensus
                           </p>
                        </>
                     ) : (
                        // AI VERDICT VERSION (fallback)
                        <>
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
                        </>
                     )}
                  </div>
               </div>
            </div>

            <div className="tdp-body">
               {/* Left column*/}
               <div className="tdp-main">
                  {/* Post card */}
                  <div className="tdp-post-card">
                     <div className="tdp-post-header">
                        <div
                           className="tdp-author-profile-pic"
                           style={{ overflow: "hidden" }}
                           onClick={(e) => {
                              e.stopPropagation(); // Prevents triggering the thread card click
                              navigate(`/user/${thread.author.username}`);
                           }}>
                           {thread.author.avatar_url ? (
                              <img
                                 src={thread.author.avatar_url}
                                 alt={`${thread.author.username}'s avatar`}
                                 style={{
                                    width: "100%",
                                    height: "100%",
                                    objectFit: "cover",
                                 }}
                              />
                           ) : (
                              <UserAvatar
                                 username={
                                    thread.author?.username || thread.flagged_by?.username || ""
                                 }
                                 size={38}
                              />
                           )}
                        </div>
                        <div className="tdp-post-author">
                           <span
                              className="tdp-author-name"
                              onClick={(e) => {
                                 e.stopPropagation(); // Prevents triggering the thread card click
                                 navigate(`/user/${thread.author.username}`);
                              }}>
                              {thread.author?.username || thread.flagged_by?.username}
                           </span>
                           <div className="tdp-author-meta">
                              <span>
                                 {new Date(thread.created_at).toLocaleDateString("en-US", {
                                    month: "short",
                                    day: "numeric",
                                    year: "numeric",
                                    hour: "numeric",
                                    minute: "2-digit",
                                 })}{" "}
                              </span>
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
                        {thread.claim.media_url ? (
                           <img
                              src={thread.claim.media_url}
                              alt="Snipped claim"
                              className="card-media-image"
                           />
                        ) : (
                           <>
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
                           </>
                        )}
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
                                 <div
                                    className={`tdp-select-wrap tdp-evidence-type-wrap ${evidenceTypeTone}`}>
                                    <select
                                       className="tdp-select tdp-evidence-type-select"
                                       value={evidenceType}
                                       onChange={(e) => setEvidenceType(e.target.value)}>
                                       <option value={"CONTRADICTS CLAIM"}>
                                          Contradicts Claim
                                       </option>
                                       <option value={"SUPPORTS CLAIM"}>Supports Claim</option>
                                       <option value={"PROVIDES CONTEXT"}>Provides Context</option>
                                       <option value={"SOURCE VERIFICATION"}>
                                          Source Verification
                                       </option>
                                    </select>
                                    <Icons
                                       name="chevron-down"
                                       size={13}
                                       color="#6b7280"
                                       className="tdp-select-chevron"
                                    />
                                 </div>
                              </div>
                           </div>
                           <div className="tdp-form-group">
                              <label className="tdp-form-label">Supporting Verdict</label>
                              <div className="tdp-evidence-verdicts">
                                 {Object.entries(EVIDENCE_VERDICT_META).map(([key, meta]) => {
                                    return (
                                       <button
                                          type="button"
                                          key={key}
                                          className={`tdp-evidence-verdict tdp-evidence-verdict--${key.toLowerCase()} ${evidenceVerdict === key ? "selected" : ""}`}
                                          onClick={(e) => {
                                             setEvidenceVerdict(key);
                                          }}>
                                          <Icons name={meta.icon} />
                                          {meta.label}
                                       </button>
                                    );
                                 })}
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
                  <div
                     className="tdp-tabs-section"
                     ref={tabsSectionRef}>
                     <div className="tdp-tab-bar">
                        <button
                           className={`tdp-tab ${currentSection === "comments" ? "active" : ""}`}
                           onClick={() => handleSectionChange("comments")}>
                           <Icons
                              name="message-circle"
                              size={13}
                              color={currentSection === "comments" ? "#4f46e5" : "#6b7280"}
                              strokeWidth={2.5}
                           />
                           Comments ({sortedComments.length})
                        </button>
                        <button
                           className={`tdp-tab ${currentSection === "evidence" ? "active" : ""}`}
                           onClick={() => handleSectionChange("evidence")}>
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
                              {sortedComments.length === 0 && (
                                 <p className="tdp-empty">No comments yet. Be the first!</p>
                              )}
                              {sortedComments.map((comment, i) => {
                                 const isMod =
                                    comment.commenter?.role === "MOD" ||
                                    comment.commenter?.role === "MODERATOR";
                                 const username = comment.commenter?.username || "Unknown";
                                 const isOwner = comment.commenter?.id === user?.id;
                                 const commentDateTime = comment.commented_at
                                    ? new Date(comment.commented_at).toLocaleString()
                                    : comment.created_at
                                      ? new Date(comment.created_at).toLocaleString()
                                      : comment.timestamp || "";
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
                                                   {commentDateTime}
                                                </span>
                                             </div>
                                             {editingCommentId === comment.id ? (
                                                <div className="tdp-inline-edit-wrap">
                                                   <textarea
                                                      className="tdp-inline-edit-textarea"
                                                      value={editingCommentText}
                                                      onChange={(e) =>
                                                         setEditingCommentText(e.target.value)
                                                      }
                                                      rows={3}
                                                   />
                                                   <div className="tdp-inline-edit-actions">
                                                      <button
                                                         className="tdp-owner-action save"
                                                         type="button"
                                                         onClick={() =>
                                                            handleSaveCommentEdit(comment.id)
                                                         }>
                                                         Save
                                                      </button>
                                                      <button
                                                         className="tdp-owner-action"
                                                         type="button"
                                                         onClick={() => {
                                                            setEditingCommentId(null);
                                                            setEditingCommentText("");
                                                         }}>
                                                         Cancel
                                                      </button>
                                                   </div>
                                                </div>
                                             ) : (
                                                <p className="tdp-comment-text">
                                                   {comment.comment_text}
                                                </p>
                                             )}
                                          </div>
                                          {editingCommentId !== comment.id && (
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
                                                {isOwner && (
                                                   <>
                                                      <button
                                                         className="tdp-owner-action"
                                                         type="button"
                                                         onClick={() => {
                                                            setEditingCommentId(comment.id);
                                                            setEditingCommentText(
                                                               comment.comment_text || "",
                                                            );
                                                         }}>
                                                         Edit
                                                      </button>
                                                      <button
                                                         className="tdp-owner-action danger"
                                                         type="button"
                                                         onClick={() =>
                                                            handleDeleteComment(comment.id)
                                                         }>
                                                         Delete
                                                      </button>
                                                   </>
                                                )}
                                             </div>
                                          )}
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

                           {evidenceList.map((ev, i) => (
                              <EvidenceCard
                                 key={ev.id || i}
                                 evidence={ev}
                                 isModerator={isModerator}
                                 isOwner={ev.contributor?.id === user?.id}
                                 currentUserId={user?.id}
                                 isTop={i === 0 && evidenceList.length > 1}
                                 onEdit={handleSaveEvidenceEdit}
                                 onDelete={handleDeleteEvidence}
                                 onVote={handleVote}
                                 votingEvidenceId={votingEvidenceId}
                                 onVerify={async (evidenceId, status, notes) => {
                                    const API_BASE_URL =
                                       import.meta.env.VITE_API_BASE_URL ||
                                       "http://localhost:8000/api";
                                    try {
                                       await authFetch(
                                          `${API_BASE_URL}/evidence/${evidenceId}/verify/`,
                                          {
                                             method: "PATCH",
                                             headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify({
                                                evidence_status: status,
                                                moderator_notes: notes,
                                             }),
                                          },
                                       );
                                       await refreshThreadData();
                                    } catch (error) {
                                       setError("Error verifying evidence");
                                    }
                                 }}
                                 editingId={editingEvidenceId}
                                 editingText={editingEvidenceText}
                                 editingVerdict={editingEvidenceVerdict}
                                 setEditingId={setEditingEvidenceId}
                                 setEditingText={setEditingEvidenceText}
                                 setEditingVerdict={setEditingEvidenceVerdict}
                              />
                           ))}

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
                        <div
                           className="tdp-author-profile-pic"
                           style={{ overflow: "hidden" }}
                           onClick={(e) => {
                              e.stopPropagation(); // Prevents triggering the thread card click
                              navigate(`/user/${thread.author.username}`);
                           }}>
                           {thread.author.avatar_url ? (
                              <img
                                 src={thread.author.avatar_url}
                                 alt={`${thread.author.username}'s avatar`}
                                 style={{
                                    width: "100%",
                                    height: "100%",
                                    objectFit: "cover",
                                 }}
                              />
                           ) : (
                              <UserAvatar
                                 username={
                                    thread.author?.username || thread.flagged_by?.username || ""
                                 }
                                 size={38}
                              />
                           )}
                        </div>
                        <div className="tdp-posted-by-info">
                           <div
                              className="tdp-posted-by-name"
                              onClick={(e) => {
                                 e.stopPropagation(); // Prevents triggering the thread card click
                                 navigate(`/user/${thread.author.username}`);
                              }}>
                              @{thread.author?.username || "Unknown"}
                           </div>
                           {thread.author?.trust_score >= 80 && (
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
                        <TrustGauge score={thread.author?.trust_score ?? 0} />
                     </div>
                     <div className="tdp-poster-stats">
                        <div className="tdp-poster-stat">
                           <span className="tdp-stat-val">
                              {thread.author?.trust_score?.toFixed(1) || "0.0"}
                           </span>
                           <span className="tdp-stat-lbl">Trust</span>
                        </div>
                        <div className="tdp-poster-stat">
                           <span className="tdp-stat-val">{thread.evidence_count ?? 0}</span>
                           <span className="tdp-stat-lbl">Evidence</span>
                        </div>
                        <div className="tdp-poster-stat">
                           <span className="tdp-stat-val">{thread.comment_count ?? 0}</span>
                           <span className="tdp-stat-lbl">Comments</span>
                        </div>
                     </div>
                  </div>

                  {/* Author Trust Score */}
                  <div className="tdp-sidebar-card">
                     <div className="tdp-sidebar-card-label">AUTHOR TRUST SCORE BREAKDOWN</div>
                     {[
                        {
                           label: "Base Score",
                           score: authorTrustBreakdown.base_score ?? 50,
                           share: authorTrustBreakdown.base_share_pct ?? 0,
                           max: 50,
                           color: "#4f46e5",
                        },
                        {
                           label: "Contribution Accuracy",
                           score: authorTrustBreakdown.contribution_points ?? 0,
                           share: authorTrustBreakdown.contribution_share_pct ?? 0,
                           max: 30,
                           color: "#0e9f6e",
                        },
                        {
                           label: "Vote Balance",
                           score: authorTrustBreakdown.vote_points ?? 0,
                           share: authorTrustBreakdown.vote_share_pct ?? 0,
                           max: 15,
                           color: "#d97706",
                        },
                        {
                           label: "Tenure Bonus",
                           score: authorTrustBreakdown.tenure_points ?? 0,
                           share: authorTrustBreakdown.tenure_share_pct ?? 0,
                           max: 5,
                           color: "#4f46e5",
                        },
                        {
                           label: "Conduct Penalties",
                           score: authorTrustBreakdown.penalties ?? 0,
                           share: authorTrustBreakdown.penalties_share_pct ?? 0,
                           max: 30,
                           color: "#dc2626",
                        },
                     ].map(({ label, score, share, max, color }) => (
                        <div
                           key={label}
                           className="tdp-trust-row">
                           <div className="tdp-trust-row-header">
                              <span className="tdp-trust-row-label">{label}</span>
                              <span
                                 className="tdp-trust-row-val"
                                 style={{ color }}>
                                 {Number(share || 0).toFixed(1)}%
                              </span>
                           </div>
                           <div className="tdp-trust-track">
                              <div
                                 className="tdp-trust-fill"
                                 style={{
                                    width: `${Math.max(0, Math.min(100, Number(share || 0)))}%`,
                                    background: color,
                                 }}
                              />
                           </div>
                           <div className="tdp-trust-impact">
                              Impact: {label === "Conduct Penalties" ? "-" : "+"}
                              {Math.abs(Number(score || 0)).toFixed(1)} pts
                           </div>
                        </div>
                     ))}
                     <div className="tdp-trust-breakdown-meta">
                        Accuracy:{" "}
                        {Math.round((authorTrustBreakdown.contribution_accuracy_rate || 0) * 100)}%
                        | Net votes: {authorTrustBreakdown.net_votes ?? 0} | Months:{" "}
                        {authorTrustBreakdown.months_active ?? 0}
                     </div>
                  </div>

                  {/* Related claims */}
                  {thread.related_claims?.length > 0 && (
                     <div className="tdp-sidebar-card">
                        <div className="tdp-sidebar-card-label">RELATED CLAIMS</div>
                        {thread.related_claims.map((rc, i) => (
                           <div
                              key={rc.id || i}
                              className={`tdp-related-claim ${i < thread.related_claims.length - 1 ? "bordered" : ""}`}>
                              <VerdictBadge
                                 verdict={(getEffectiveVerdict(rc) || "UNVERIFIED").toLowerCase()}
                              />
                              <p className="tdp-related-text">{rc.caption}</p>
                           </div>
                        ))}
                     </div>
                  )}

                  {/* Report / Share */}
                  <div className="tdp-sidebar-actions">
                     <button
                        className="tdp-report-btn"
                        onClick={handleReportThread}
                        disabled={reporting}>
                        <Icons
                           name="flag"
                           size={13}
                           color="#e02424"
                           strokeWidth={2.5}
                        />
                        {reporting ? "Reporting..." : "Report"}
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

         {confirmDialog.open && (
            <div className="tdp-dialog-overlay">
               <div className="tdp-dialog">
                  <div className="tdp-dialog-policy-chip danger">{confirmActionMeta.code}</div>
                  <h3 className="tdp-dialog-title">{confirmActionMeta.title}</h3>
                  <p className="tdp-dialog-text">{confirmActionMeta.description}</p>
                  <div className="tdp-dialog-actions">
                     <button
                        type="button"
                        className="tdp-dialog-btn secondary"
                        onClick={() =>
                           setConfirmDialog({ open: false, type: null, targetId: null })
                        }>
                        Cancel
                     </button>
                     <button
                        type="button"
                        className="tdp-dialog-btn danger"
                        onClick={handleConfirmAction}>
                        {confirmActionMeta.cta}
                     </button>
                  </div>
               </div>
            </div>
         )}

         {reportDialogOpen && (
            <div className="tdp-dialog-overlay">
               <div className="tdp-dialog">
                  <div className="tdp-dialog-policy-chip warning">{reportActionMeta.code}</div>
                  <h3 className="tdp-dialog-title">{reportActionMeta.title}</h3>
                  <p className="tdp-dialog-text">{reportActionMeta.description}</p>
                  <div className="tdp-dialog-form-row">
                     <label className="tdp-dialog-label">Reason</label>
                     <select
                        className="tdp-dialog-select"
                        value={reportReason}
                        onChange={(e) => setReportReason(e.target.value)}>
                        <option value="INAPPROPRIATE">Inappropriate</option>
                        <option value="SPAM">Spam</option>
                        <option value="HARASSMENT">Harassment</option>
                        <option value="OTHER">Other</option>
                     </select>
                  </div>
                  <div className="tdp-dialog-form-row">
                     <label className="tdp-dialog-label">Notes (optional)</label>
                     <textarea
                        className="tdp-dialog-textarea"
                        rows={3}
                        value={reportNotes}
                        onChange={(e) => setReportNotes(e.target.value)}
                     />
                  </div>
                  <div className="tdp-dialog-actions">
                     <button
                        type="button"
                        className="tdp-dialog-btn secondary"
                        disabled={reporting}
                        onClick={() => {
                           setReportDialogOpen(false);
                           setReportReason("OTHER");
                           setReportNotes("");
                        }}>
                        Cancel
                     </button>
                     <button
                        type="button"
                        className="tdp-dialog-btn warning"
                        disabled={reporting}
                        onClick={submitReportThread}>
                        {reporting ? "Submitting..." : reportActionMeta.cta}
                     </button>
                  </div>
               </div>
            </div>
         )}
      </div>
   );
}

export default ThreadDetailPage;
