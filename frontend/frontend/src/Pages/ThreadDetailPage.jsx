import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useNotification } from "../hooks/useNotification";
import Icons from "../components/Icons";
import EvidenceCard from "../components/EvidenceCard";
import { VERDICT_CONFIG, EVIDENCE_VERDICT_META } from "../utils/constants";
import "./ThreadDetailPage.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}/${path}`;

function normalizeText(value) {
   return (value || "").trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

function isHttpUrl(value) {
   if (!value) return false;
   try {
      const url = new URL(value);
      return url.protocol === "http:" || url.protocol === "https:";
   } catch {
      return false;
   }
}

function safeActionMessage(error, fallback) {
   const status = Number(error?.status);
   if (!Number.isInteger(status) || status < 400 || status >= 500) return fallback;
   const candidate = [error?.detail, error?.message]
      .find((value) => typeof value === "string" && value.trim())
      ?.trim();
   if (!candidate || candidate.length > 200) return fallback;
   if (/<[a-z][\s\S]*>|traceback|stack trace|internal server|exception|sql|django|request failed|network error|unexpected token|parse error/i.test(candidate)) return fallback;
   return candidate;
}

function formatDate(value, options = {}) {
   if (!value) return "Date unavailable";
   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Date unavailable";
   return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      ...options,
   });
}

function VerdictBadge({ verdict }) {
   const key = (verdict || "UNVERIFIED").toUpperCase();
   const meta = VERDICT_CONFIG[key] || VERDICT_CONFIG.UNVERIFIED;
   return (
      <span className={`thread-detail-verdict thread-detail-verdict--${key.toLowerCase()}`}>
         <Icons name={meta.icon || "help-circle"} size={14} />
         {meta.label || key}
      </span>
   );
}

function getUserInitials(username) {
   const parts = String(username || "")
      .split(/[\s._-]+/)
      .map((part) => part.trim())
      .filter(Boolean);
   if (!parts.length) return "?";
   if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
   return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function getRoleLabel(role) {
   const normalized = String(role || "").toUpperCase();
   if (["MOD", "MODERATOR"].includes(normalized)) return "Platform moderator";
   return "Community member";
}

function makeLocalCommentId() {
   if (globalThis.crypto?.randomUUID) return `local-${globalThis.crypto.randomUUID()}`;
   return `local-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function Avatar({ user, size = "medium" }) {
   const [imageFailed, setImageFailed] = useState(false);
   const username = user?.username || "Unknown";
   const tone = [...username].reduce((sum, character) => sum + character.charCodeAt(0), 0) % 5;
   return (
      <span className={`thread-detail-avatar thread-detail-avatar--${size} thread-detail-avatar--tone-${tone}`}>
         {user?.avatar_url && !imageFailed ? (
            <img src={user.avatar_url} alt="" onError={() => setImageFailed(true)} />
         ) : (
            <span className="thread-detail-avatar-fallback" aria-hidden="true">{getUserInitials(username)}</span>
         )}
      </span>
   );
}

function ClaimMedia({ claim }) {
   const [failed, setFailed] = useState(false);
   if (!isHttpUrl(claim?.media_url)) return null;
   if (failed) return <p className="thread-detail-media-error">Claim media is unavailable.</p>;
   if (claim.claim_type === "VIDEO") {
      return (
         <video className="thread-detail-media" controls preload="metadata" onError={() => setFailed(true)}>
            <source src={claim.media_url} />
            Your browser cannot play this video.
         </video>
      );
   }
   return (
      <img
         className="thread-detail-media"
         src={claim.media_url}
         alt="Media attached to the claim"
         onError={() => setFailed(true)}
      />
   );
}

function AccessibleDialog({ open, busy = false, labelledBy, describedBy, onClose, fallbackFocusRef, children }) {
   const dialogRef = useRef(null);
   const restoreFocusRef = useRef(null);
   const onCloseRef = useRef(onClose);
   const busyRef = useRef(busy);

   useEffect(() => {
      onCloseRef.current = onClose;
      busyRef.current = busy;
   }, [busy, onClose]);

   useEffect(() => {
      if (!open) return undefined;
      restoreFocusRef.current = document.activeElement;
      const fallbackFocusTarget = fallbackFocusRef?.current;
      const dialog = dialogRef.current;
      const initial = dialog?.querySelector("[data-dialog-initial]");
      (initial || dialog)?.focus();
      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !busyRef.current) {
            event.preventDefault();
            onCloseRef.current();
            return;
         }
         if (event.key !== "Tab" || !dialog) return;
         const controls = [...dialog.querySelectorAll(
            'button:not([disabled]), select:not([disabled]), textarea:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
         )];
         if (!controls.length) {
            event.preventDefault();
            dialog.focus();
            return;
         }
         const first = controls[0];
         const last = controls[controls.length - 1];
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
         const previousFocus = restoreFocusRef.current;
         if (previousFocus?.isConnected) {
            previousFocus.focus();
         } else if (fallbackFocusTarget?.isConnected) {
            fallbackFocusTarget.focus();
         }
      };
   }, [open, fallbackFocusRef]);

   if (!open) return null;
   return (
      <div
         className="thread-detail-dialog-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busy) onClose();
         }}
      >
         <div
            ref={dialogRef}
            className="thread-detail-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={labelledBy}
            aria-describedby={describedBy}
            tabIndex={-1}
         >
            {children}
         </div>
      </div>
   );
}

function buildCommentTree(comments) {
   const nodes = new Map(comments.map((comment) => [String(comment.id), { ...comment, children: [] }]));
   const roots = [];
   nodes.forEach((comment) => {
      const parent = comment.parent_id ? nodes.get(String(comment.parent_id)) : null;
      if (parent) parent.children.push(comment);
      else roots.push(comment);
   });
   const time = (comment) => new Date(comment.commented_at || 0).getTime();
   roots.sort((left, right) => time(right) - time(left));
   const sortReplies = (comment) => {
      comment.children.sort((left, right) => time(left) - time(right));
      comment.children.forEach(sortReplies);
   };
   roots.forEach(sortReplies);
   return roots;
}

const DEFAULT_VISIBLE_REPLIES = 3;
const REPLY_PAGE_SIZE = 5;

function flattenReplies(comment, depth = 1, result = []) {
   comment.children.forEach((child) => {
      result.push({ comment: child, depth });
      flattenReplies(child, depth + 1, result);
   });
   return result;
}

function findCommentThread(roots, targetId) {
   const normalizedTarget = String(targetId);
   for (const root of roots) {
      if (String(root.id) === normalizedTarget) return { root, replyIndex: -1 };
      const replies = flattenReplies(root);
      const replyIndex = replies.findIndex(({ comment }) => String(comment.id) === normalizedTarget);
      if (replyIndex >= 0) return { root, replyIndex };
   }
   return null;
}

function InlineReplyComposer({ target, currentUser, value, onChange, onSubmit, onCancel, inputRef }) {
   const targetUsername = target?.commenter?.username || "Unknown";
   return (
      <form className="thread-detail-inline-reply" onSubmit={(event) => onSubmit(event, target)}>
         <Avatar user={currentUser} />
         <div className="thread-detail-inline-reply-body">
            <div className="thread-detail-inline-reply-heading">
               <span>Replying to</span>
               <Link to={`/user/${encodeURIComponent(targetUsername)}`}>@{targetUsername}</Link>
            </div>
            <label className="sr-only" htmlFor={`reply-comment-${target.id}`}>Reply to @{targetUsername}</label>
            <textarea
               ref={inputRef}
               id={`reply-comment-${target.id}`}
               value={value}
               onChange={(event) => onChange(event.target.value)}
               placeholder={`Write a reply to @${targetUsername}`}
               rows={3}
            />
            <div className="thread-detail-inline-reply-actions">
               <button type="button" className="thread-detail-text-button" onClick={onCancel}>Cancel</button>
               <button type="submit" className="thread-detail-primary-button" disabled={!value.trim()}>Reply</button>
            </div>
         </div>
      </form>
   );
}

function CommentItem({
   comment,
   visualDepth = 0,
   isReply = false,
   currentUserId,
   editingId,
   editingText,
   highlightedId,
   likingIds,
   onEditingTextChange,
   onStartEdit,
   onCancelEdit,
   onSaveEdit,
   onDelete,
   onReply,
   onLike,
   onShare,
   onRetry,
   onDiscard,
}) {
   const isOwner = String(comment.commenter?.id || "") === String(currentUserId || "");
   const username = comment.commenter?.username || "Unknown";
   const isModerator = ["MOD", "MODERATOR"].includes(String(comment.commenter?.role || "").toUpperCase());
   const isEditing = editingId === comment.id;
   const isLiking = likingIds.has(comment.id);
   const sendState = comment._sendState;
   const isSending = sendState === "sending";
   const isFailed = sendState === "failed";
   const isPersisted = !sendState;

   return (
      <article
         id={`comment-${comment.id}`}
         className={`thread-detail-comment ${isReply ? "thread-detail-comment--reply" : ""} ${highlightedId === comment.id ? "is-highlighted" : ""} ${isSending ? "is-sending" : ""} ${isFailed ? "is-send-failed" : ""}`}
         style={{ "--reply-depth": Math.min(visualDepth, 2) }}
         tabIndex={-1}
      >
         <Link className="thread-detail-comment-avatar-link" to={`/user/${encodeURIComponent(username)}`}>
            <Avatar user={comment.commenter} />
            <span className="sr-only">View @{username}&apos;s profile</span>
         </Link>
         <div className="thread-detail-comment-content">
            <div className="thread-detail-comment-bubble">
               <header className="thread-detail-comment-header">
                  <Link to={`/user/${encodeURIComponent(username)}`}>@{username}</Link>
                  {isModerator && <span className="thread-detail-role-label">Platform moderator</span>}
                  {isSending ? (
                     <span className="thread-detail-send-state" role="status">Sending…</span>
                  ) : isFailed ? (
                     <span className="thread-detail-send-state thread-detail-send-state--failed" role="status">Not sent</span>
                  ) : (
                     <time dateTime={comment.commented_at}>{formatDate(comment.commented_at, { hour: "numeric", minute: "2-digit" })}</time>
                  )}
               </header>

               {comment.reply_to_username && (
                  <p className="thread-detail-reply-context">
                     Reply to <Link to={`/user/${encodeURIComponent(comment.reply_to_username)}`}>@{comment.reply_to_username}</Link>
                  </p>
               )}

               {isEditing ? (
                  <div className="thread-detail-inline-edit">
                     <label className="sr-only" htmlFor={`edit-comment-${comment.id}`}>Edit comment</label>
                     <textarea id={`edit-comment-${comment.id}`} value={editingText} onChange={(event) => onEditingTextChange(event.target.value)} rows={3} />
                     <div className="thread-detail-inline-actions">
                        <button type="button" className="thread-detail-primary-button" onClick={() => onSaveEdit(comment.id)}>Save</button>
                        <button type="button" className="thread-detail-text-button" onClick={onCancelEdit}>Cancel</button>
                     </div>
                  </div>
               ) : (
                  <p className="thread-detail-comment-text">{comment.comment_text}</p>
               )}
            </div>

            {!isEditing && isFailed && (
               <div className="thread-detail-comment-actions" role="group" aria-label={`Recovery actions for ${username}'s comment`}>
                  <button type="button" className="is-primary-text" onClick={() => onRetry(comment)}>Retry</button>
                  <button type="button" onClick={() => onDiscard(comment)}>Discard</button>
               </div>
            )}

            {!isEditing && isPersisted && (
               <div className="thread-detail-comment-actions" role="group" aria-label={`Actions for ${username}'s comment`}>
                  <button
                     type="button"
                     className={`thread-detail-comment-like ${comment.is_liked ? "is-selected" : ""}`}
                     aria-pressed={Boolean(comment.is_liked)}
                     aria-label={`${comment.is_liked ? "Unlike" : "Like"} ${username}'s comment. ${comment.like_count || 0} likes`}
                     disabled={isLiking}
                     onClick={() => onLike(comment)}
                  >
                     <Icons name="thumbs-up" size={13} />
                     <span aria-hidden="true">{comment.like_count || 0}</span>
                  </button>
                  <button type="button" onClick={() => onReply(comment)}>Reply</button>
                  <button type="button" onClick={() => onShare(comment)}>Share</button>
                  {isOwner && (
                     <>
                        <button type="button" className="is-owner-action" onClick={() => onStartEdit(comment)}>Edit</button>
                        <button type="button" className="is-danger is-owner-action" onClick={() => onDelete(comment.id)}>Delete</button>
                     </>
                  )}
               </div>
            )}
         </div>
      </article>
   );
}

function CommentThread({
   root,
   visibleReplyCount,
   currentUser,
   editingId,
   editingText,
   highlightedId,
   likingIds,
   replyComposer,
   replyInputRef,
   onEditingTextChange,
   onStartEdit,
   onCancelEdit,
   onSaveEdit,
   onDelete,
   onStartReply,
   onReplyTextChange,
   onSubmitReply,
   onCancelReply,
   onLike,
   onShare,
   onRetry,
   onDiscard,
   onShowReplies,
   onShowMoreReplies,
   onHideReplies,
}) {
   const replies = flattenReplies(root);
   const safeVisibleCount = Math.max(0, Math.min(visibleReplyCount, replies.length));
   const visibleReplies = replies.slice(0, safeVisibleCount);
   const remainingReplies = replies.length - safeVisibleCount;
   const rootHasReplyComposer = replyComposer?.targetId === root.id;

   return (
      <section className="thread-detail-thread-block" aria-label={`Comment thread by ${root.commenter?.username || "community member"}`}>
         <CommentItem
            comment={root}
            currentUserId={currentUser?.id}
            editingId={editingId}
            editingText={editingText}
            highlightedId={highlightedId}
            likingIds={likingIds}
            onEditingTextChange={onEditingTextChange}
            onStartEdit={onStartEdit}
            onCancelEdit={onCancelEdit}
            onSaveEdit={onSaveEdit}
            onDelete={onDelete}
            onReply={(comment) => onStartReply(comment, root.id)}
            onLike={onLike}
            onShare={onShare}
            onRetry={onRetry}
            onDiscard={onDiscard}
         />

         {rootHasReplyComposer && (
            <InlineReplyComposer
               target={root}
               currentUser={currentUser}
               value={replyComposer.text}
               onChange={onReplyTextChange}
               onSubmit={onSubmitReply}
               onCancel={onCancelReply}
               inputRef={replyInputRef}
            />
         )}

         {visibleReplies.length > 0 && (
            <div className="thread-detail-replies" aria-label={`Replies to @${root.commenter?.username || "user"}`}>
               {visibleReplies.map(({ comment, depth }) => (
                  <div key={comment.id} className="thread-detail-reply-row">
                     <CommentItem
                        comment={comment}
                        visualDepth={Math.min(depth, 2)}
                        isReply
                        currentUserId={currentUser?.id}
                        editingId={editingId}
                        editingText={editingText}
                        highlightedId={highlightedId}
                        likingIds={likingIds}
                        onEditingTextChange={onEditingTextChange}
                        onStartEdit={onStartEdit}
                        onCancelEdit={onCancelEdit}
                        onSaveEdit={onSaveEdit}
                        onDelete={onDelete}
                        onReply={(item) => onStartReply(item, root.id)}
                        onLike={onLike}
                        onShare={onShare}
                        onRetry={onRetry}
                        onDiscard={onDiscard}
                     />
                     {replyComposer?.targetId === comment.id && (
                        <InlineReplyComposer
                           target={comment}
                           currentUser={currentUser}
                           value={replyComposer.text}
                           onChange={onReplyTextChange}
                           onSubmit={onSubmitReply}
                           onCancel={onCancelReply}
                           inputRef={replyInputRef}
                        />
                     )}
                  </div>
               ))}
            </div>
         )}

         {replies.length > 0 && (
            <div className="thread-detail-reply-controls" role="group" aria-label={`Reply visibility for @${root.commenter?.username || "user"}'s comment`}>
               {safeVisibleCount === 0 ? (
                  <button type="button" onClick={() => onShowReplies(root.id, replies.length)} aria-expanded="false">
                     View {replies.length} {replies.length === 1 ? "reply" : "replies"}
                  </button>
               ) : (
                  <>
                     {remainingReplies > 0 && (
                        <button type="button" onClick={() => onShowMoreReplies(root.id, replies.length)}>
                           View {remainingReplies} more {remainingReplies === 1 ? "reply" : "replies"}
                        </button>
                     )}
                     <button type="button" onClick={() => onHideReplies(root.id)} aria-expanded="true">Hide replies</button>
                  </>
               )}
            </div>
         )}
      </section>
   );
}

function ThreadDetailSkeleton() {
   return (
      <main className="thread-detail-page thread-detail-skeleton-page" aria-busy="true">
         <span className="sr-only" role="status">Loading thread…</span>
         <div className="thread-detail-skeleton-shell" aria-hidden="true">
            <div className="thread-detail-skeleton-topbar">
               <div className="thread-detail-skeleton-topbar-inner">
                  <div className="thread-detail-skeleton-row thread-detail-skeleton-row--breadcrumb">
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--back" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--meta" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--date" />
                  </div>
                  <div className="thread-detail-skeleton-row">
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--badge" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--status" />
                  </div>
               </div>
            </div>

            <section className="thread-detail-skeleton-hero">
               <div className="thread-detail-skeleton-hero-inner">
                  <div className="thread-detail-skeleton-claim">
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--eyebrow" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--claim-long" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--claim-medium" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--claim-short" />
                     <div className="thread-detail-skeleton-row thread-detail-skeleton-row--activity">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--activity" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--activity" />
                     </div>
                  </div>
                  <div className="thread-detail-skeleton-assessment">
                     <div className="thread-detail-skeleton-row thread-detail-skeleton-row--spread">
                        <div className="thread-detail-skeleton-row">
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--logo" />
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--reviewer" />
                        </div>
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--badge" />
                     </div>
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--assessment-copy" />
                     <div className="thread-detail-skeleton-metric">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--metric-label" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--metric-value" />
                     </div>
                  </div>
               </div>
            </section>

            <div className="thread-detail-skeleton-body">
               <div className="thread-detail-skeleton-main">
                  <div className="thread-detail-skeleton-card thread-detail-skeleton-post">
                     <div className="thread-detail-skeleton-post-header">
                        <div className="thread-detail-skeleton-row">
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--avatar" />
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--author" />
                        </div>
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--post-kind" />
                     </div>
                     <div className="thread-detail-skeleton-context">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--context-label" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--context-copy" />
                     </div>
                     <div className="thread-detail-skeleton-media">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--media-icon" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--media-copy" />
                     </div>
                  </div>

                  <div className="thread-detail-skeleton-cta">
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--cta" />
                  </div>

                  <div className="thread-detail-skeleton-card thread-detail-skeleton-discussion">
                     <div className="thread-detail-skeleton-tabs">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--tab" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--tab" />
                     </div>
                     <div className="thread-detail-skeleton-composer">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--avatar" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--composer" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--send" />
                     </div>
                     <div className="thread-detail-skeleton-comment">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--avatar" />
                        <div>
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--comment-name" />
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--comment-line" />
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--comment-line-short" />
                        </div>
                     </div>
                  </div>
               </div>

               <aside className="thread-detail-skeleton-sidebar">
                  <div className="thread-detail-skeleton-card thread-detail-skeleton-sidebar-card">
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--sidebar-label" />
                     <div className="thread-detail-skeleton-row thread-detail-skeleton-row--spread">
                        <div className="thread-detail-skeleton-row">
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--avatar-large" />
                           <span className="thread-detail-skeleton-block thread-detail-skeleton-block--sidebar-author" />
                        </div>
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--trust-ring" />
                     </div>
                     <div className="thread-detail-skeleton-stats">
                        <span /><span /><span />
                     </div>
                  </div>
                  <div className="thread-detail-skeleton-card thread-detail-skeleton-sidebar-card">
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--sidebar-label" />
                     <div className="thread-detail-skeleton-row thread-detail-skeleton-row--spread">
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--reputation" />
                        <span className="thread-detail-skeleton-block thread-detail-skeleton-block--metric-value" />
                     </div>
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--trust-track" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--trust-copy" />
                     <span className="thread-detail-skeleton-block thread-detail-skeleton-block--profile-link" />
                  </div>
                  <div className="thread-detail-skeleton-actions">
                     <span className="thread-detail-skeleton-block" />
                     <span className="thread-detail-skeleton-block" />
                  </div>
               </aside>
            </div>
         </div>
      </main>
   );
}

export default function ThreadDetailPage() {
   const { authFetch, user } = useAuth();
   const { addToast } = useNotification();
   const { threadId } = useParams();
   const navigate = useNavigate();
   const location = useLocation();
   const [searchParams] = useSearchParams();
   const commentHash = location.hash.startsWith("#comment-") ? location.hash.slice(1) : null;
   const initialTab = commentHash ? "comments" : searchParams.get("tab") === "evidence" ? "evidence" : "comments";

   const [thread, setThread] = useState(null);
   const [comments, setComments] = useState([]);
   const [evidenceList, setEvidenceList] = useState([]);
   const [loading, setLoading] = useState(true);
   const [loadError, setLoadError] = useState("");
   const [currentTab, setCurrentTab] = useState(initialTab);
   const [showEvidenceForm, setShowEvidenceForm] = useState(false);
   const [evidenceUrl, setEvidenceUrl] = useState("");
   const [evidenceType, setEvidenceType] = useState("CONTRADICTS CLAIM");
   const [evidenceAssessment, setEvidenceAssessment] = useState("UNVERIFIED");
   const [evidenceExplanation, setEvidenceExplanation] = useState("");
   const [submittingEvidence, setSubmittingEvidence] = useState(false);
   const [newComment, setNewComment] = useState("");
   const [replyComposer, setReplyComposer] = useState(null);
   const [replyVisibility, setReplyVisibility] = useState({});
   const [submittingComment, setSubmittingComment] = useState(false);
   const [editingCommentId, setEditingCommentId] = useState(null);
   const [editingCommentText, setEditingCommentText] = useState("");
   const [likingIds, setLikingIds] = useState(new Set());
   const [highlightedCommentId, setHighlightedCommentId] = useState(null);
   const [editingEvidenceId, setEditingEvidenceId] = useState(null);
   const [editingEvidenceText, setEditingEvidenceText] = useState("");
   const [editingEvidenceVerdict, setEditingEvidenceVerdict] = useState("UNVERIFIED");
   const [votingEvidenceId, setVotingEvidenceId] = useState(null);
   const [confirmDialog, setConfirmDialog] = useState({ open: false, type: null, targetId: null });
   const [dialogBusy, setDialogBusy] = useState(false);
   const [reportDialogOpen, setReportDialogOpen] = useState(false);
   const [reportReason, setReportReason] = useState("OTHER");
   const [reportNotes, setReportNotes] = useState("");
   const [reporting, setReporting] = useState(false);
   const pageRef = useRef(null);
   const replyInputRef = useRef(null);
   const evidenceFormRef = useRef(null);
   const tabRefs = useRef({});
   const deepLinkHandledRef = useRef(false);

   const refreshThreadData = useCallback(async () => {
      const data = await authFetch(apiUrl(`threads/${threadId}/`), { method: "GET" });
      setThread(data);
      setComments((current) => {
         const transient = current.filter((comment) => comment._sendState && comment._threadId === threadId);
         return [...transient, ...(data.comments || [])];
      });
      setEvidenceList(data.evidence_submissions || []);
      return data;
   }, [authFetch, threadId]);

   const commentTree = useMemo(() => buildCommentTree(comments), [comments]);
   const activeCommentCount = useMemo(
      () => comments.filter((comment) => comment._sendState !== "failed").length,
      [comments],
   );

   useEffect(() => {
      let active = true;
      setLoading(true);
      setLoadError("");
      refreshThreadData()
         .catch((error) => {
            console.error("Failed to load thread", error);
            if (active) setLoadError(safeActionMessage(error, "We couldn't load this thread. Please try again."));
         })
         .finally(() => { if (active) setLoading(false); });
      return () => { active = false; };
   }, [refreshThreadData]);

   useEffect(() => { deepLinkHandledRef.current = false; }, [threadId, commentHash]);

   useEffect(() => {
      const openForm = searchParams.get("openForm") === "evidence";
      if (commentHash) setCurrentTab("comments");
      else setCurrentTab(searchParams.get("tab") === "evidence" || openForm ? "evidence" : "comments");
      if (openForm) setShowEvidenceForm(true);
   }, [commentHash, searchParams]);

   useEffect(() => {
      if (loading || !commentHash || deepLinkHandledRef.current || currentTab !== "comments") return undefined;
      const targetId = commentHash.replace(/^comment-/, "");
      const threadMatch = findCommentThread(commentTree, targetId);
      if (threadMatch && threadMatch.replyIndex >= 0 && replyVisibility[threadMatch.root.id] !== Number.MAX_SAFE_INTEGER) {
         setReplyVisibility((current) => ({ ...current, [threadMatch.root.id]: Number.MAX_SAFE_INTEGER }));
         return undefined;
      }

      const frame = window.requestAnimationFrame(() => {
         const target = document.getElementById(commentHash);
         if (!target) return;
         const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
         target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
         target.focus({ preventScroll: true });
         setHighlightedCommentId(targetId);
         deepLinkHandledRef.current = true;
      });
      const timeout = window.setTimeout(() => setHighlightedCommentId(null), 3000);
      return () => {
         window.cancelAnimationFrame(frame);
         window.clearTimeout(timeout);
      };
   }, [commentHash, commentTree, currentTab, loading, replyVisibility]);

   useEffect(() => {
      if (!loading && showEvidenceForm && searchParams.get("openForm") === "evidence") {
         const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
         evidenceFormRef.current?.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
      }
   }, [loading, searchParams, showEvidenceForm]);

   const sortedEvidence = useMemo(() => [...evidenceList].sort((left, right) => {
      const scoreDifference = Number(right.weighted_score || 0) - Number(left.weighted_score || 0);
      if (scoreDifference) return scoreDifference;
      const timeDifference = new Date(right.submitted_at || 0).getTime() - new Date(left.submitted_at || 0).getTime();
      if (timeDifference) return timeDifference;
      return String(left.id).localeCompare(String(right.id));
   }), [evidenceList]);

   const changeTab = useCallback((nextTab) => {
      setCurrentTab(nextTab);
      const params = new URLSearchParams(searchParams);
      params.set("tab", nextTab);
      params.delete("openForm");
      navigate({ pathname: location.pathname, search: `?${params.toString()}`, hash: "" }, { replace: true });
   }, [location.pathname, navigate, searchParams]);

   const handleTabKeyDown = (event, activeTab) => {
      const tabs = ["comments", "evidence"];
      const index = tabs.indexOf(activeTab);
      let next = null;
      if (event.key === "ArrowRight") next = tabs[(index + 1) % tabs.length];
      if (event.key === "ArrowLeft") next = tabs[(index - 1 + tabs.length) % tabs.length];
      if (event.key === "Home") next = tabs[0];
      if (event.key === "End") next = tabs[tabs.length - 1];
      if (!next) return;
      event.preventDefault();
      changeTab(next);
      tabRefs.current[next]?.focus();
   };

   const shareUrl = useCallback(async (url, title, successMessage) => {
      try {
         if (navigator.share) {
            await navigator.share({ title, url });
            return;
         }
         if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(url);
            addToast({ type: "success", message: successMessage, duration: 2200 });
            return;
         }
         throw new Error("Share unavailable");
      } catch (error) {
         if (error?.name === "AbortError") return;
         addToast({ type: "warning", message: "Sharing isn't available in this browser. Copy the page address instead." });
      }
   }, [addToast]);

   const shareThread = () => shareUrl(`${window.location.origin}/thread/detail/${thread.id}`, "TruthLens thread", "Thread link copied.");
   const shareComment = (comment) => shareUrl(
      `${window.location.origin}/thread/detail/${thread.id}?tab=comments#comment-${comment.id}`,
      `Comment by @${comment.commenter?.username || "TruthLens user"}`,
      "Comment link copied.",
   );

   function optimisticCommentFrom({ text, parent = null }) {
      const commenterRole = user?.role || user?.profile?.role || "USER";
      return {
         id: makeLocalCommentId(),
         commenter: {
            id: user?.id,
            username: user?.username || "You",
            avatar_url: user?.avatar_url || null,
            role: commenterRole,
         },
         parent_id: parent?.id || null,
         reply_to_username: parent?.commenter?.username || null,
         comment_text: text,
         commented_at: new Date().toISOString(),
         like_count: 0,
         is_liked: false,
         _sendState: "sending",
         _threadId: threadId,
      };
   }

   async function persistOptimisticComment(optimistic, successMessage) {
      try {
         const created = await authFetch(apiUrl("comments/"), {
            method: "POST",
            body: {
               thread_id: threadId,
               parent_id: optimistic.parent_id,
               comment_text: optimistic.comment_text,
            },
         });
         setComments((current) => current.map((comment) => comment.id === optimistic.id ? created : comment));
         addToast({ type: "success", message: successMessage, duration: 1800 });
         return true;
      } catch (error) {
         console.error("Failed to post comment", error);
         const message = safeActionMessage(error, "We couldn't post this comment. You can retry it below.");
         setComments((current) => current.map((comment) => comment.id === optimistic.id
            ? { ...comment, _sendState: "failed", _sendError: message }
            : comment));
         addToast({ type: "error", message });
         return false;
      }
   }

   async function handleCommentSubmit(event) {
      event.preventDefault();
      const text = newComment.trim();
      if (!text || submittingComment) return;

      const optimistic = optimisticCommentFrom({ text });
      setComments((current) => [optimistic, ...current]);
      setNewComment("");
      setSubmittingComment(true);
      try {
         await persistOptimisticComment(optimistic, "Comment posted.");
      } finally {
         setSubmittingComment(false);
      }
   }

   function startReply(comment, rootId) {
      if (comment._sendState) return;
      setReplyComposer({
         targetId: comment.id,
         rootId,
         username: comment.commenter?.username || "Unknown",
         text: "",
      });
      window.requestAnimationFrame(() => replyInputRef.current?.focus());
   }

   async function handleReplySubmit(event, targetComment) {
      event.preventDefault();
      const text = replyComposer?.text?.trim();
      if (!text || !targetComment || replyComposer?.targetId !== targetComment.id) return;

      const optimistic = optimisticCommentFrom({ text, parent: targetComment });
      const rootId = replyComposer.rootId;
      setComments((current) => [optimistic, ...current]);
      setReplyVisibility((current) => ({ ...current, [rootId]: Number.MAX_SAFE_INTEGER }));
      setReplyComposer(null);
      await persistOptimisticComment(optimistic, "Reply posted.");
   }

   async function retryOptimisticComment(comment) {
      if (comment._sendState !== "failed") return;
      const optimistic = { ...comment, _sendState: "sending", _sendError: null };
      setComments((current) => current.map((item) => item.id === comment.id ? optimistic : item));
      await persistOptimisticComment(optimistic, comment.parent_id ? "Reply posted." : "Comment posted.");
   }

   function discardOptimisticComment(comment) {
      if (!comment._sendState) return;
      setComments((current) => current.filter((item) => item.id !== comment.id));
   }

   async function handleLike(comment) {
      if (likingIds.has(comment.id) || comment._sendState) return;

      const previousLiked = Boolean(comment.is_liked);
      const previousCount = Number(comment.like_count || 0);
      const optimisticLiked = !previousLiked;
      const optimisticCount = Math.max(0, previousCount + (optimisticLiked ? 1 : -1));

      setLikingIds((current) => new Set(current).add(comment.id));
      setComments((current) => current.map((item) => item.id === comment.id
         ? { ...item, is_liked: optimisticLiked, like_count: optimisticCount }
         : item));

      try {
         const result = await authFetch(apiUrl(`comments/${comment.id}/like/`), {
            method: previousLiked ? "DELETE" : "POST",
         });
         setComments((current) => current.map((item) => item.id === comment.id
            ? { ...item, like_count: result.like_count, is_liked: result.is_liked }
            : item));
      } catch (error) {
         console.error("Failed to update comment like", error);
         setComments((current) => current.map((item) => item.id === comment.id
            ? { ...item, is_liked: previousLiked, like_count: previousCount }
            : item));
         addToast({ type: "error", message: safeActionMessage(error, "We couldn't update this like. Please try again.") });
      } finally {
         setLikingIds((current) => {
            const next = new Set(current);
            next.delete(comment.id);
            return next;
         });
      }
   }

   function visibleRepliesFor(root) {
      const total = flattenReplies(root).length;
      const configured = replyVisibility[root.id];
      if (configured === 0) return 0;
      if (Number.isInteger(configured)) return Math.min(configured, total);
      return 0;
   }

   function showReplies(rootId, total) {
      setReplyVisibility((current) => ({ ...current, [rootId]: Math.min(DEFAULT_VISIBLE_REPLIES, total) }));
   }

   function showMoreReplies(rootId, total) {
      setReplyVisibility((current) => {
         const configured = current[rootId];
         const currentVisible = Number.isInteger(configured) && configured > 0
            ? Math.min(configured, total)
            : Math.min(DEFAULT_VISIBLE_REPLIES, total);
         return { ...current, [rootId]: Math.min(total, currentVisible + REPLY_PAGE_SIZE) };
      });
   }

   function hideReplies(rootId) {
      setReplyVisibility((current) => ({ ...current, [rootId]: 0 }));
      setReplyComposer((current) => current?.rootId === rootId ? null : current);
   }

   async function handleSaveCommentEdit(commentId) {
      const text = editingCommentText.trim();
      if (!text) return;
      try {
         const updated = await authFetch(apiUrl(`comments/${commentId}/`), { method: "PATCH", body: { comment_text: text } });
         setComments((current) => current.map((comment) => comment.id === commentId ? { ...comment, ...updated } : comment));
         setEditingCommentId(null);
         setEditingCommentText("");
         addToast({ type: "success", message: "Comment updated.", duration: 1800 });
      } catch (error) {
         console.error("Failed to edit comment", error);
         addToast({ type: "error", message: safeActionMessage(error, "We couldn't update this comment. Please try again.") });
      }
   }

   async function performDelete() {
      const { type, targetId } = confirmDialog;
      if (!type || !targetId || dialogBusy) return;
      setDialogBusy(true);
      try {
         await authFetch(apiUrl(`${type === "comment" ? "comments" : "evidence"}/${targetId}/`), { method: "DELETE" });
         if (type === "comment") {
            setComments((current) => current
               .filter((comment) => comment.id !== targetId)
               .map((comment) => comment.parent_id === targetId ? { ...comment, parent_id: null, reply_to_username: null } : comment));
            setReplyComposer((current) => current?.targetId === targetId ? null : current);
            setThread((current) => current ? { ...current, comment_count: Math.max(0, Number(current.comment_count || 0) - 1) } : current);
         } else await refreshThreadData();
         setConfirmDialog({ open: false, type: null, targetId: null });
         addToast({ type: "success", message: type === "comment" ? "Comment deleted." : "Evidence deleted.", duration: 1800 });
      } catch (error) {
         console.error("Failed to delete item", error);
         addToast({ type: "error", message: safeActionMessage(error, `We couldn't delete this ${type}. Please try again.`) });
      } finally {
         setDialogBusy(false);
      }
   }

   async function handleEvidenceSubmit(event) {
      event.preventDefault();
      if (!evidenceUrl.trim() || !evidenceExplanation.trim() || submittingEvidence) return;
      setSubmittingEvidence(true);
      try {
         await authFetch(apiUrl("evidence/"), {
            method: "POST",
            body: {
               thread_id: threadId,
               evidence_url: evidenceUrl.trim(),
               evidence_type: evidenceType,
               evidence_verdict: evidenceAssessment,
               evidence_caption: evidenceExplanation.trim(),
            },
         });
         await refreshThreadData();
         setEvidenceUrl("");
         setEvidenceExplanation("");
         setEvidenceAssessment("UNVERIFIED");
         setShowEvidenceForm(false);
         changeTab("evidence");
         addToast({ type: "success", message: "Evidence submitted for community review.", duration: 2200 });
      } catch (error) {
         console.error("Failed to submit evidence", error);
         addToast({ type: "error", message: safeActionMessage(error, "We couldn't submit this evidence. Please review it and try again.") });
      } finally {
         setSubmittingEvidence(false);
      }
   }

   async function handleSaveEvidenceEdit(evidenceId, caption, verdict) {
      if (!caption.trim()) return;
      try {
         await authFetch(apiUrl(`evidence/${evidenceId}/`), { method: "PATCH", body: { evidence_caption: caption.trim(), evidence_verdict: verdict } });
         await refreshThreadData();
         setEditingEvidenceId(null);
         setEditingEvidenceText("");
         setEditingEvidenceVerdict("UNVERIFIED");
         addToast({ type: "success", message: "Evidence updated.", duration: 1800 });
      } catch (error) {
         console.error("Failed to edit evidence", error);
         addToast({ type: "error", message: safeActionMessage(error, "We couldn't update this evidence. Please try again.") });
      }
   }

   async function handleVote(evidence, nextValue) {
      if (!evidence?.id || votingEvidenceId || evidence.contributor?.id === user?.id) return;

      const previousEvidence = { ...evidence };
      const previousVoteValue = evidence.my_vote?.vote_value;
      let nextUpvotes = Number(evidence.upvotes || 0);
      let nextDownvotes = Number(evidence.downvotes || 0);
      let nextMyVote = evidence.my_vote;

      if (!evidence.my_vote) {
         if (nextValue) nextUpvotes += 1;
         else nextDownvotes += 1;
         nextMyVote = { id: `pending-${evidence.id}`, vote_value: nextValue };
      } else if (previousVoteValue === nextValue) {
         if (nextValue) nextUpvotes = Math.max(0, nextUpvotes - 1);
         else nextDownvotes = Math.max(0, nextDownvotes - 1);
         nextMyVote = null;
      } else {
         if (nextValue) {
            nextUpvotes += 1;
            nextDownvotes = Math.max(0, nextDownvotes - 1);
         } else {
            nextDownvotes += 1;
            nextUpvotes = Math.max(0, nextUpvotes - 1);
         }
         nextMyVote = { ...evidence.my_vote, vote_value: nextValue };
      }

      setVotingEvidenceId(evidence.id);
      setEvidenceList((current) => current.map((item) => item.id === evidence.id
         ? { ...item, upvotes: nextUpvotes, downvotes: nextDownvotes, my_vote: nextMyVote }
         : item));

      try {
         if (!evidence.my_vote) await authFetch(apiUrl("votes/"), { method: "POST", body: { evidence: evidence.id, vote_value: nextValue } });
         else if (previousVoteValue === nextValue) await authFetch(apiUrl(`votes/${evidence.my_vote.id}/`), { method: "DELETE" });
         else await authFetch(apiUrl(`votes/${evidence.my_vote.id}/`), { method: "PATCH", body: { vote_value: nextValue } });
         await refreshThreadData();
      } catch (error) {
         console.error("Failed to vote", error);
         setEvidenceList((current) => current.map((item) => item.id === evidence.id ? previousEvidence : item));
         addToast({ type: "error", message: safeActionMessage(error, "We couldn't record this vote. Please try again.") });
      } finally {
         setVotingEvidenceId(null);
      }
   }

   async function submitReport() {
      if (reporting) return;
      setReporting(true);
      try {
         await authFetch(apiUrl("thread-flags/"), { method: "POST", body: { thread_id: thread.id, reason: reportReason, notes: reportNotes.trim() } });
         setReportDialogOpen(false);
         setReportReason("OTHER");
         setReportNotes("");
         addToast({ type: "success", message: "Report submitted for platform safety review.", duration: 2200 });
      } catch (error) {
         console.error("Failed to report thread", error);
         addToast({ type: "error", message: safeActionMessage(error, "We couldn't submit this report. Please try again.") });
      } finally {
         setReporting(false);
      }
   }

   if (loading) return <ThreadDetailSkeleton />;
   if (loadError || !thread) {
      return (
         <main className="thread-detail-page thread-detail-state">
            <Icons name="alert-triangle" size={30} />
            <h1>Thread unavailable</h1>
            <p>{loadError || "We couldn't find this thread."}</p>
            <button type="button" className="thread-detail-primary-button" onClick={() => navigate("/community")}>Back to Community</button>
         </main>
      );
   }

   const claimText = thread.claim?.context_text?.trim() || thread.caption?.trim() || "Discussion";
   const hasClaim = Boolean(thread.claim?.context_text?.trim());
   const communityContext = hasClaim && thread.caption?.trim() && normalizeText(thread.caption) !== normalizeText(claimText) ? thread.caption.trim() : "";
   const humanVerdict = thread.claim?.human_verdict;
   const publishedFactCheck = thread.claim?.published_fact_check;
   const assessmentVerdict = humanVerdict?.verdict || thread.claim?.ai_verdict || "UNVERIFIED";
   const verifiedCount = Number(thread.claim?.verified_evidence_count || 0);
   const confidenceValue = thread.claim?.consensus_score;
   const confidence = Number(confidenceValue);
   const hasConfidence = confidenceValue !== null && confidenceValue !== "" && Number.isFinite(confidence);
   const authorUsername = thread.author?.username || "Unknown";
   const authorRoleLabel = getRoleLabel(thread.author?.role);
   const assessmentKey = String(assessmentVerdict || "UNVERIFIED").toUpperCase();
   const assessmentMeta = VERDICT_CONFIG[assessmentKey] || VERDICT_CONFIG.UNVERIFIED;
   const currentUserTrustScore = Number(user?.trust_breakdown?.trust_score ?? user?.trust_score ?? 0);
   const currentUserWeight = (1 + currentUserTrustScore / 100).toFixed(1);
   const evidenceTypeTone = evidenceType.includes("SUPPORT")
      ? "supports"
      : evidenceType.includes("CONTRADICT")
        ? "contradicts"
        : evidenceType.includes("CONTEXT")
          ? "context"
          : evidenceType.includes("VERIFICATION")
            ? "verification"
            : "neutral";

   return (
      <main
         ref={pageRef}
         className={`thread-detail-page thread-detail-page--classic thread-detail-page--${assessmentKey.toLowerCase()}`}
         style={{
            "--thread-verdict-color": assessmentMeta.color,
            "--thread-verdict-bg": assessmentMeta.bg,
            "--thread-verdict-border": assessmentMeta.border,
         }}
         tabIndex={-1}
      >
         <header className="thread-detail-topbar thread-detail-topbar--classic">
            <div className="thread-detail-topbar-inner">
               <div className="thread-detail-breadcrumb-left">
                  <button type="button" className="thread-detail-back" onClick={() => navigate("/community")}>
                     <Icons name="arrow-left" size={15} /> Community Feed
                  </button>
                  <span className="thread-detail-breadcrumb-dot" aria-hidden="true">•</span>
                  <strong>Thread #{thread.display_id || String(thread.id).slice(0, 6)}</strong>
                  <span className="thread-detail-breadcrumb-dot" aria-hidden="true">•</span>
                  <span>Started {formatDate(thread.created_at, { hour: "numeric", minute: "2-digit" })} by <strong>@{authorUsername}</strong></span>
               </div>
               <div className="thread-detail-metadata">
                  <VerdictBadge verdict={assessmentVerdict} />
                  {thread.status && <span className="thread-detail-status">{thread.status}</span>}
               </div>
            </div>
         </header>

         <section className={`thread-detail-hero thread-detail-hero--${String(assessmentVerdict || "UNVERIFIED").toLowerCase()}`} aria-labelledby="thread-detail-heading">
            <div className="thread-detail-hero-inner">
               <div className="thread-detail-hero-copy">
                  <p className="thread-detail-eyebrow"><Icons name="flag" size={13} /> Claim</p>
                  <h1 id="thread-detail-heading">{claimText}</h1>
                  <div className="thread-detail-counts" aria-label="Thread activity">
                     <span><Icons name="message-circle" size={14} /> <strong>{activeCommentCount}</strong> comments</span>
                     <span><Icons name="paperclip" size={14} /> <strong>{evidenceList.length}</strong> evidence submissions</span>
                     {thread.claim?.claim_type === "URL" && isHttpUrl(thread.claim?.url_link) && (
                        <a href={thread.claim.url_link} target="_blank" rel="noopener noreferrer">Claim URL <Icons name="external-link" size={13} /></a>
                     )}
                  </div>
               </div>

               <aside className="thread-detail-assessment thread-detail-assessment--classic" aria-label="Current assessment">
                  <div className="thread-detail-assessment-heading">
                     <div className="thread-detail-assessment-source">
                        {humanVerdict?.organization?.logo_url && <img src={humanVerdict.organization.logo_url} alt="" className="thread-detail-reviewer-logo" />}
                        <div>
                           <span className="thread-detail-assessment-kicker">
                              {humanVerdict ? (humanVerdict.organization ? `Reviewed by ${humanVerdict.organization.name}` : "Human review") : "AI analysis"}
                           </span>
                           {humanVerdict?.reviewed_at && <time dateTime={humanVerdict.reviewed_at}>{formatDate(humanVerdict.reviewed_at)}</time>}
                        </div>
                     </div>
                     <VerdictBadge verdict={assessmentVerdict} />
                  </div>

                  {humanVerdict ? (
                     <>
                        <p className="thread-detail-assessment-copy">This verdict reflects attributable human review.</p>
                        <div className="thread-detail-assessment-metric">
                           <span>Verified evidence</span>
                           <strong>{verifiedCount}</strong>
                        </div>
                     </>
                  ) : (
                     <>
                        {thread.claim?.ai_summary && <p className="thread-detail-assessment-copy">{thread.claim.ai_summary}</p>}
                        {hasConfidence && (
                           <div className="thread-detail-confidence">
                              <div><span>AI confidence</span><strong>{Math.max(0, Math.min(100, Math.round(confidence)))}%</strong></div>
                              <div className="thread-detail-confidence-track"><span style={{ width: `${Math.max(0, Math.min(100, confidence))}%` }} /></div>
                           </div>
                        )}
                        <div className="thread-detail-assessment-metric">
                           <span>Evidence submissions</span>
                           <strong>{evidenceList.length}</strong>
                        </div>
                     </>
                  )}
                  {!humanVerdict && verifiedCount > 0 && (
                     <p className="thread-detail-neutral-note">{verifiedCount} verified evidence {verifiedCount === 1 ? "item is" : "items are"} available for human review.</p>
                  )}
                  {humanVerdict && publishedFactCheck?.organization?.slug && publishedFactCheck?.publication_id && (
                     <div className="thread-detail-publication">
                        <span className="thread-detail-publication-label">Published fact-check</span>
                        <Link
                           className="thread-detail-publication-link"
                           to={`/partners/${encodeURIComponent(publishedFactCheck.organization.slug)}/fact-checks/${encodeURIComponent(publishedFactCheck.publication_id)}`}
                           aria-label={`Read ${publishedFactCheck.organization.name} published fact-check: ${publishedFactCheck.headline}`}
                        >
                           <strong>{publishedFactCheck.headline}</strong>
                           <span>Read full fact-check <Icons name="arrow-right" size={13} /></span>
                        </Link>
                     </div>
                  )}
               </aside>
            </div>
         </section>

         <div className="thread-detail-body thread-detail-body--classic">
            <div className="thread-detail-main-column">
               <article className="thread-detail-post-card thread-detail-post-card--classic">
                  <header className="thread-detail-post-header">
                     <Link className="thread-detail-post-author" to={`/user/${encodeURIComponent(authorUsername)}`} aria-label={`View @${authorUsername}'s profile`}>
                        <Avatar user={thread.author} size="large" />
                        <span>
                           <strong>{authorUsername}</strong>
                           <small>{formatDate(thread.created_at, { hour: "numeric", minute: "2-digit" })}</small>
                        </span>
                     </Link>
                     <span className="thread-detail-post-kind">Community post</span>
                  </header>

                  {communityContext && (
                     <div className="thread-detail-community-context-strip">
                        <span>Community context</span>
                        <p>{communityContext}</p>
                     </div>
                  )}

                  <div className="thread-detail-post-media">
                     {thread.claim?.media_url ? (
                        <ClaimMedia claim={thread.claim} />
                     ) : (
                        <div className="thread-detail-post-placeholder">
                           <Icons name="message-square" size={30} />
                           <span>No media attached to this claim.</span>
                        </div>
                     )}
                  </div>
               </article>

               <button
                  type="button"
                  className="thread-detail-evidence-cta"
                  onClick={() => {
                     changeTab("evidence");
                     setShowEvidenceForm(true);
                     window.requestAnimationFrame(() => evidenceFormRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" }));
                  }}
               >
                  <Icons name="paperclip" size={16} /> Submit Evidence for This Claim
               </button>

               <section className="thread-detail-discussion thread-detail-discussion--classic" aria-label="Thread discussion">
                  <div className="thread-detail-tabs" role="tablist" aria-label="Thread content">
                     <button ref={(node) => { tabRefs.current.comments = node; }} id="thread-detail-comments-tab" type="button" role="tab" aria-selected={currentTab === "comments"} aria-controls="thread-detail-comments-panel" tabIndex={currentTab === "comments" ? 0 : -1} onClick={() => changeTab("comments")} onKeyDown={(event) => handleTabKeyDown(event, "comments")}>
                        <Icons name="message-circle" size={15} /> Comments <span>{activeCommentCount}</span>
                     </button>
                     <button ref={(node) => { tabRefs.current.evidence = node; }} id="thread-detail-evidence-tab" type="button" role="tab" aria-selected={currentTab === "evidence"} aria-controls="thread-detail-evidence-panel" tabIndex={currentTab === "evidence" ? 0 : -1} onClick={() => changeTab("evidence")} onKeyDown={(event) => handleTabKeyDown(event, "evidence")}>
                        <Icons name="paperclip" size={15} /> Evidence Board <span>{evidenceList.length}</span>
                     </button>
                  </div>

                  {currentTab === "comments" && (
                     <div id="thread-detail-comments-panel" role="tabpanel" aria-labelledby="thread-detail-comments-tab" className="thread-detail-panel thread-detail-panel--comments">
                        <form className="thread-detail-composer thread-detail-composer--classic" onSubmit={handleCommentSubmit}>
                           <Avatar user={user} />
                           <div className="thread-detail-composer-body">
                              <label className="sr-only" htmlFor="thread-comment-composer">Write a comment</label>
                              <textarea id="thread-comment-composer" value={newComment} onChange={(event) => setNewComment(event.target.value)} placeholder="Write a comment…" rows={2} />
                           </div>
                           <button type="submit" className="thread-detail-comment-submit" disabled={!newComment.trim() || submittingComment} aria-label="Post comment">
                              {submittingComment ? <span className="thread-detail-mini-spinner" aria-hidden="true" /> : <Icons name="send" size={16} />}
                           </button>
                        </form>

                        <div className="thread-detail-comment-list">
                           {!commentTree.length && <p className="thread-detail-empty">No comments yet. Start the discussion.</p>}
                           {commentTree.map((comment) => (
                              <CommentThread
                                 key={comment.id}
                                 root={comment}
                                 visibleReplyCount={visibleRepliesFor(comment)}
                                 currentUser={user}
                                 editingId={editingCommentId}
                                 editingText={editingCommentText}
                                 highlightedId={highlightedCommentId}
                                 likingIds={likingIds}
                                 replyComposer={replyComposer}
                                 replyInputRef={replyInputRef}
                                 onEditingTextChange={setEditingCommentText}
                                 onStartEdit={(item) => { setEditingCommentId(item.id); setEditingCommentText(item.comment_text || ""); }}
                                 onCancelEdit={() => { setEditingCommentId(null); setEditingCommentText(""); }}
                                 onSaveEdit={handleSaveCommentEdit}
                                 onDelete={(id) => setConfirmDialog({ open: true, type: "comment", targetId: id })}
                                 onStartReply={startReply}
                                 onReplyTextChange={(text) => setReplyComposer((current) => current ? { ...current, text } : current)}
                                 onSubmitReply={handleReplySubmit}
                                 onCancelReply={() => setReplyComposer(null)}
                                 onLike={handleLike}
                                 onShare={shareComment}
                                 onRetry={retryOptimisticComment}
                                 onDiscard={discardOptimisticComment}
                                 onShowReplies={showReplies}
                                 onShowMoreReplies={showMoreReplies}
                                 onHideReplies={hideReplies}
                              />
                           ))}
                        </div>
                     </div>
                  )}

                  {currentTab === "evidence" && (
                     <div id="thread-detail-evidence-panel" role="tabpanel" aria-labelledby="thread-detail-evidence-tab" className="thread-detail-panel thread-detail-panel--evidence">
                        <div className="thread-detail-evidence-toolbar thread-detail-evidence-toolbar--legacy">
                           <div>
                              <h2>Evidence Board</h2>
                              <p>Community-submitted sources, ranked by weighted trust score.</p>
                           </div>
                           <button type="button" className="thread-detail-text-button" onClick={() => setShowEvidenceForm((open) => !open)}>
                              {showEvidenceForm ? "Close form" : "Contribute evidence"}
                           </button>
                        </div>
                        {showEvidenceForm && (
                           <form className="thread-detail-evidence-form thread-detail-evidence-form--legacy" ref={evidenceFormRef} onSubmit={handleEvidenceSubmit}>
                              <div className="thread-detail-evidence-form-title">
                                 <Icons name="paperclip" size={14} />
                                 New Evidence Submission
                              </div>
                              <div className="thread-detail-evidence-form-row">
                                 <div className="thread-detail-evidence-form-group">
                                    <label htmlFor="evidence-source-url">Source URL <span aria-hidden="true">*</span></label>
                                    <div className="thread-detail-evidence-input-shell">
                                       <Icons name="link" size={13} />
                                       <input id="evidence-source-url" type="url" value={evidenceUrl} onChange={(event) => setEvidenceUrl(event.target.value)} placeholder="https://reliable-source.com/..." required />
                                    </div>
                                 </div>
                                 <div className="thread-detail-evidence-form-group">
                                    <label htmlFor="evidence-type">Relationship to claim</label>
                                    <div className={`thread-detail-evidence-select-shell thread-detail-evidence-select-shell--${evidenceTypeTone}`}>
                                       <select id="evidence-type" value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)}>
                                          <option value="CONTRADICTS CLAIM">Contradicts Claim</option>
                                          <option value="SUPPORTS CLAIM">Supports Claim</option>
                                          <option value="PROVIDES CONTEXT">Provides Context</option>
                                          <option value="SOURCE VERIFICATION">Source Verification</option>
                                       </select>
                                       <Icons name="chevron-down" size={13} />
                                    </div>
                                 </div>
                              </div>
                              <div className="thread-detail-evidence-form-row">
                                 <div className="thread-detail-evidence-form-group thread-detail-evidence-form-group--assessment">
                                    <label htmlFor="evidence-assessment">Your assessment</label>
                                    <div className="thread-detail-evidence-select-shell">
                                       <select id="evidence-assessment" value={evidenceAssessment} onChange={(event) => setEvidenceAssessment(event.target.value)}>
                                          {Object.entries(EVIDENCE_VERDICT_META).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
                                       </select>
                                       <Icons name="chevron-down" size={13} />
                                    </div>
                                    <small>Your assessment is your interpretation, not a TruthLens or professional verdict.</small>
                                 </div>
                              </div>
                              <div className="thread-detail-evidence-form-group">
                                 <label htmlFor="evidence-explanation">Explanation <span aria-hidden="true">*</span></label>
                                 <textarea id="evidence-explanation" value={evidenceExplanation} onChange={(event) => setEvidenceExplanation(event.target.value)} rows={5} placeholder="Explain why this source supports, contradicts, or adds context to the claim..." required />
                              </div>
                              <div className="thread-detail-evidence-form-footer">
                                 <span className="thread-detail-evidence-weight">
                                    <Icons name="bar-chart" size={12} />
                                    Your weight: <strong>×{currentUserWeight}</strong> <span>(Trust Score {currentUserTrustScore.toFixed(0)})</span>
                                 </span>
                                 <div className="thread-detail-evidence-form-buttons">
                                    <button type="button" className="thread-detail-text-button" onClick={() => setShowEvidenceForm(false)} disabled={submittingEvidence}>Cancel</button>
                                    <button type="submit" className="thread-detail-primary-button" disabled={submittingEvidence}>
                                       {submittingEvidence ? "Submitting…" : "Submit"}
                                       {!submittingEvidence && <Icons name="arrow-right" size={14} />}
                                    </button>
                                 </div>
                              </div>
                           </form>
                        )}
                        <div className="thread-detail-evidence-sort-row">
                           <span><Icons name="bar-chart" size={13} /> Sorted by weighted trust score</span>
                           <span className="thread-detail-evidence-formula">weighted = (up × trust/100) − (down × 0.5)</span>
                        </div>
                        <div className="thread-detail-evidence-list">
                           {!sortedEvidence.length && <p className="thread-detail-empty">No community evidence has been submitted yet.</p>}
                           {sortedEvidence.map((evidence, index) => (
                              <EvidenceCard
                                 key={evidence.id}
                                 evidence={evidence}
                                 isOwner={evidence.contributor?.id === user?.id}
                                 currentUserId={user?.id}
                                 isTop={index === 0 && sortedEvidence.length > 1}
                                 onEdit={handleSaveEvidenceEdit}
                                 onDelete={(id) => setConfirmDialog({ open: true, type: "evidence", targetId: id })}
                                 onVote={handleVote}
                                 votingEvidenceId={votingEvidenceId}
                                 editingId={editingEvidenceId}
                                 editingText={editingEvidenceText}
                                 editingVerdict={editingEvidenceVerdict}
                                 setEditingId={setEditingEvidenceId}
                                 setEditingText={setEditingEvidenceText}
                                 setEditingVerdict={setEditingEvidenceVerdict}
                              />
                           ))}
                        </div>
                     </div>
                  )}
               </section>
            </div>

            <aside className="thread-detail-sidebar thread-detail-sidebar--classic" aria-label="Discussion details">
               <section className="thread-detail-sidebar-card thread-detail-sidebar-card--author">
                  <p className="thread-detail-sidebar-label">Posted by</p>
                  <div className="thread-detail-sidebar-author-row">
                     <Link className="thread-detail-sidebar-author" to={`/user/${encodeURIComponent(authorUsername)}`} aria-label={`View @${authorUsername}'s profile`}>
                        <Avatar user={thread.author} size="large" />
                        <span>
                           <strong>@{authorUsername}</strong>
                           <small>{authorRoleLabel}</small>
                        </span>
                     </Link>
                     <div
                        className="thread-detail-trust-ring"
                        style={{ "--trust-value": `${Math.max(0, Math.min(100, Number(thread.author?.trust_score || 0)))}%` }}
                        aria-label={`Community trust score ${Number(thread.author?.trust_score || 0).toFixed(1)}`}
                     >
                        <span>{Math.round(Number(thread.author?.trust_score || 0))}</span>
                     </div>
                  </div>
                  <div className="thread-detail-poster-stats">
                     <div><strong>{Number(thread.author?.trust_score || 0).toFixed(1)}</strong><span>Trust</span></div>
                     <div><strong>{evidenceList.length}</strong><span>Evidence</span></div>
                     <div><strong>{activeCommentCount}</strong><span>Comments</span></div>
                  </div>
               </section>

               <section className="thread-detail-sidebar-card thread-detail-sidebar-card--trust">
                  <p className="thread-detail-sidebar-label">Community trust score</p>
                  <div className="thread-detail-trust-meter-row"><span>Reputation</span><strong>{Number(thread.author?.trust_score || 0).toFixed(1)}%</strong></div>
                  <div className="thread-detail-trust-meter"><span style={{ width: `${Math.max(0, Math.min(100, Number(thread.author?.trust_score || 0)))}%` }} /></div>
                  <p className="thread-detail-trust-note">Trust reflects community reputation and participation. It does not determine whether this claim is true.</p>
                  <Link className="thread-detail-profile-link" to={`/user/${encodeURIComponent(authorUsername)}`}>View full profile <Icons name="arrow-right" size={13} /></Link>
               </section>

               <div className="thread-detail-sidebar-actions thread-detail-sidebar-actions--classic" role="group" aria-label="Thread actions">
                  <button type="button" className="is-danger" onClick={() => setReportDialogOpen(true)}><Icons name="flag" size={15} /> Report</button>
                  <button type="button" onClick={shareThread}><Icons name="share-2" size={15} /> Share</button>
               </div>
            </aside>
         </div>

         <AccessibleDialog open={confirmDialog.open} busy={dialogBusy} labelledBy="thread-detail-delete-title" describedBy="thread-detail-delete-description" onClose={() => setConfirmDialog({ open: false, type: null, targetId: null })} fallbackFocusRef={pageRef}>
            <p className="thread-detail-dialog-kicker">Delete {confirmDialog.type}</p>
            <h2 id="thread-detail-delete-title">Remove this {confirmDialog.type}?</h2>
            <p id="thread-detail-delete-description">{confirmDialog.type === "comment" ? "This action cannot be undone. Replies remain in the discussion without a parent link." : "This action cannot be undone."}</p>
            <div className="thread-detail-dialog-actions"><button type="button" className="thread-detail-text-button" data-dialog-initial onClick={() => setConfirmDialog({ open: false, type: null, targetId: null })} disabled={dialogBusy}>Cancel</button><button type="button" className="thread-detail-danger-button" onClick={performDelete} disabled={dialogBusy}>{dialogBusy ? "Deleting…" : "Delete"}</button></div>
         </AccessibleDialog>

         <AccessibleDialog open={reportDialogOpen} busy={reporting} labelledBy="thread-detail-report-title" describedBy="thread-detail-report-description" onClose={() => setReportDialogOpen(false)} fallbackFocusRef={pageRef}>
            <p className="thread-detail-dialog-kicker">Platform safety</p>
            <h2 id="thread-detail-report-title">Report this thread</h2>
            <p id="thread-detail-report-description">Send this thread to platform moderators for a safety review.</p>
            <div className="thread-detail-field"><label htmlFor="thread-report-reason">Reason</label><select id="thread-report-reason" data-dialog-initial value={reportReason} onChange={(event) => setReportReason(event.target.value)} disabled={reporting}><option value="INAPPROPRIATE">Inappropriate</option><option value="SPAM">Spam</option><option value="HARASSMENT">Harassment</option><option value="OTHER">Other</option></select></div>
            <div className="thread-detail-field"><label htmlFor="thread-report-notes">Notes (optional)</label><textarea id="thread-report-notes" rows={4} value={reportNotes} onChange={(event) => setReportNotes(event.target.value)} disabled={reporting} /></div>
            <div className="thread-detail-dialog-actions"><button type="button" className="thread-detail-text-button" onClick={() => setReportDialogOpen(false)} disabled={reporting}>Cancel</button><button type="button" className="thread-detail-primary-button" onClick={submitReport} disabled={reporting}>{reporting ? "Submitting…" : "Submit report"}</button></div>
         </AccessibleDialog>
      </main>
   );
}
