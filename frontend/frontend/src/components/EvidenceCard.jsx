import { useState } from "react";
import Icons from "./Icons";
import "./EvidenceCard.css";
import { EVIDENCE_VERDICT_META } from "../utils/constants";

// Import UserAvatar function (defined in ThreadDetailPage, need to extract or pass as prop)
// For now, we'll define it here
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

/**
 * EvidenceCard - Unified component for both user & moderator contexts
 *
 * Props:
 *   evidence: Evidence object from API
 *   isModerator: Boolean - switches to verification mode
 *   isOwner: Boolean - shows edit/delete buttons (users only)
 *   isTop: Boolean - shows "Top" badge (only first evidence)
 *   onEdit: Function(evidenceId, caption, verdict) - edit evidence
 *   onDelete: Function(evidenceId) - delete evidence
 *   onVerify: Function(evidenceId, status, notes) - verify evidence (mod only)
 *   editingId: Current editing ID state
 *   editingText: Current editing text state
 *   editingVerdict: Current editing verdict state
 *   setEditingId, setEditingText, setEditingVerdict: State setters
 */
function EvidenceCard({
   evidence,
   isModerator,
   isOwner,
   currentUserId,
   isTop,
   onEdit,
   onDelete,
   onVote,
   votingEvidenceId,
   onVerify,
   editingId,
   editingText,
   editingVerdict,
   setEditingId,
   setEditingText,
   setEditingVerdict,
}) {
   const [notes, setNotes] = useState("");
   const [isVerifying, setIsVerifying] = useState(false);

   const ev = evidence;
   const upvotes = ev.upvotes ?? 0;
   const downvotes = ev.downvotes ?? 0;
   const score = ev.contributor?.trust_score ?? 0;

   // Trust color tier
   const tc = score >= 75 ? "#0e9f6e" : score >= 45 ? "#d97706" : "#e02424";

   // Source parsing
   const sourceInfo = ev.evidence_url
      ? (() => {
           try {
              const parsed = new URL(ev.evidence_url);
              return {
                 host: parsed.hostname.replace(/^www\./, ""),
                 path: parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "",
              };
           } catch {
              return {
                 host: ev.evidence_url.replace(/^https?:\/\//, ""),
                 path: "",
              };
           }
        })()
      : { host: "", path: "" };

   const sourcePathPreview =
      sourceInfo.path.length > 34 ? `${sourceInfo.path.slice(0, 34)}...` : sourceInfo.path;

   const evidenceTypeRaw = ev.evidence_type || "SOURCE";
   const evidenceTypeLabel = evidenceTypeRaw
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (letter) => letter.toUpperCase());

   const evidenceTypeClass = (() => {
      if (evidenceTypeRaw.includes("CONTRADICT")) return "contradicts";
      if (evidenceTypeRaw.includes("SUPPORT")) return "supports";
      if (evidenceTypeRaw.includes("CONTEXT")) return "context";
      if (evidenceTypeRaw.includes("VERIFICATION")) return "verification";
      return "neutral";
   })();

   const evidenceVerdictRaw = (ev.evidence_verdict || "UNVERIFIED").toUpperCase();
   const evidenceVerdictMeta =
      EVIDENCE_VERDICT_META[evidenceVerdictRaw] || EVIDENCE_VERDICT_META.UNVERIFIED;

   const headline = ev.evidence_caption?.trim() || "Source shared";
   const submittedLabel = ev.submitted_at
      ? new Date(ev.submitted_at).toLocaleTimeString(undefined, {
           month: "short",
           day: "numeric",
           year: "numeric",
           hour: "2-digit",
           minute: "2-digit",
        })
      : "Date unknown";

   const weighted = ev.weighted_score ?? (upvotes * (score / 100) - downvotes * 0.5).toFixed(1);
   const myVoteValue = ev.my_vote?.vote_value;
   const isOwnEvidence = ev.contributor?.id === currentUserId;
   const isVoting = votingEvidenceId === ev.id;

   const handleVerify = async (status) => {
      setIsVerifying(true);
      await onVerify(ev.id, status, notes);
      setNotes("");
      setIsVerifying(false);
   };

   return (
      <div className={`tdp-evidence-card evidence-card-${isModerator ? "mod" : "user"}`}>
         {/* Header with contributor and actions */}
         <div className="tdp-evidence-card-header">
            <div className="tdp-evidence-contributor">
               <UserAvatar
                  username={ev.contributor?.username || ""}
                  size={30}
               />
               <div>
                  <div className="tdp-ev-username">{ev.contributor?.username}</div>
                  <div
                     className="tdp-ev-trust"
                     style={{ color: tc }}>
                     <Icons
                        name="badge-check"
                        size={9}
                        color={tc}
                     />
                     Trust: <strong>{score.toFixed(1)}</strong>
                  </div>
               </div>
            </div>

            <div className="tdp-evidence-header-actions">
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

               {isOwner && editingId !== ev.id && (
                  <>
                     <button
                        className="tdp-owner-action"
                        type="button"
                        onClick={() => {
                           setEditingId(ev.id);
                           setEditingText(ev.evidence_caption || "");
                           setEditingVerdict(evidenceVerdictRaw);
                        }}>
                        Edit
                     </button>
                     <button
                        className="tdp-owner-action danger"
                        type="button"
                        onClick={() => onDelete(ev.id)}>
                        Delete
                     </button>
                  </>
               )}
            </div>
         </div>

         {/* Caption - editable for owner */}
         {editingId === ev.id ? (
            <div className="tdp-inline-edit-wrap evidence">
               <textarea
                  className="tdp-inline-edit-textarea"
                  value={editingText}
                  onChange={(e) => setEditingText(e.target.value)}
                  rows={3}
               />
               <div className="tdp-inline-edit-row">
                  <select
                     className="tdp-inline-edit-select"
                     value={editingVerdict}
                     onChange={(e) => setEditingVerdict(e.target.value)}>
                     {Object.keys(EVIDENCE_VERDICT_META).map((key) => (
                        <option
                           key={key}
                           value={key}>
                           {EVIDENCE_VERDICT_META[key].label}
                        </option>
                     ))}
                  </select>
                  <div className="tdp-inline-edit-actions">
                     <button
                        className="tdp-owner-action save"
                        type="button"
                        onClick={() => onEdit(ev.id, editingText, editingVerdict)}>
                        Save
                     </button>
                     <button
                        className="tdp-owner-action"
                        type="button"
                        onClick={() => {
                           setEditingId(null);
                           setEditingText("");
                           setEditingVerdict("UNVERIFIED");
                        }}>
                        Cancel
                     </button>
                  </div>
               </div>
            </div>
         ) : (
            <p className="tdp-evidence-headline">{headline}</p>
         )}

         {/* Source link */}
         {ev.evidence_url && (
            <a
               href={ev.evidence_url}
               target="_blank"
               rel="noopener noreferrer"
               className={`tdp-source-link prominent ${evidenceTypeClass}`}>
               <span className="tdp-source-link-kicker">
                  <span
                     className="tdp-source-brand-badge"
                     aria-hidden="true">
                     {(sourceInfo.host?.[0] || "?").toUpperCase()}
                  </span>
                  Primary source
               </span>
               <span className="tdp-source-link-url">{sourceInfo.host}</span>
               {sourcePathPreview && (
                  <span className="tdp-source-link-path">{sourcePathPreview}</span>
               )}
               <span className="tdp-source-link-cta">
                  Read article
                  <Icons
                     name="external-link"
                     size={11}
                     color="#1d4ed8"
                  />
               </span>
            </a>
         )}

         {/* Meta: verdict, type, submitted time */}
         <div className="tdp-evidence-news-meta">
            <span className={`tdp-meta-chip verdict ${evidenceVerdictRaw.toLowerCase()}`}>
               <Icons
                  name={evidenceVerdictMeta.icon}
                  size={10}
               />
               {evidenceVerdictMeta.label}
            </span>
            <span className="tdp-meta-dot">•</span>
            <span className={`tdp-meta-chip type ${evidenceTypeClass}`}>{evidenceTypeLabel}</span>
            <span className="tdp-meta-dot">•</span>
            <span className="tdp-meta-chip">{submittedLabel}</span>
         </div>

         {/* Actions - voting (users) vs verification (mods) */}
         {isModerator ? (
            // MODERATOR MODE
            ev.evidence_status && ev.evidence_status !== "UNVERIFIED" ? (
               // Verified/Rejected - Show read-only status
               <div
                  className={`tdp-evidence-verified-info ${
                     ev.evidence_status === "REJECTED" ? "rejected" : ""
                  }`}>
                  <div className="tdp-verification-badge">
                     <Icons
                        name={ev.evidence_status === "VERIFIED" ? "check-circle" : "x-circle"}
                        size={16}
                        color={ev.evidence_status === "VERIFIED" ? "#10b981" : "#dc2626"}
                     />
                     <span className="tdp-verification-status">
                        {ev.evidence_status === "VERIFIED" ? "Verified" : "Rejected"}
                     </span>
                  </div>

                  <div className="tdp-verification-details">
                     <div className="tdp-verified-by">
                        <span className="tdp-label">Reviewed by:</span>
                        <span className="tdp-value">
                           {ev.verified_by?.username || "Moderator"}
                        </span>{" "}
                        <span className="tdp-mod-badge">
                           <Icons
                              name="shield"
                              size={8}
                              color="#059669"
                              strokeWidth={2.5}
                           />
                           MOD
                        </span>
                     </div>
                     {ev.verified_at && (
                        <div className="tdp-verified-at">
                           <span className="tdp-label">On:</span>
                           <span className="tdp-value">
                              {new Date(ev.verified_at).toLocaleString(undefined, {
                                 month: "short",
                                 day: "numeric",
                                 year: "numeric",
                                 hour: "2-digit",
                                 minute: "2-digit",
                              })}
                           </span>
                        </div>
                     )}
                  </div>

                  {ev.moderator_notes && (
                     <div className="tdp-moderator-notes-display">
                        <div className="tdp-notes-label">Moderator Notes:</div>
                        <div className="tdp-notes-text">{ev.moderator_notes}</div>
                     </div>
                  )}
               </div>
            ) : (
               // Unverified - Show verification form
               <div className="tdp-evidence-moderation">
                  <textarea
                     className="tdp-mod-notes"
                     placeholder="Moderator notes (optional)..."
                     value={notes}
                     onChange={(e) => setNotes(e.target.value)}
                     disabled={isVerifying}
                  />
                  <div className="tdp-mod-actions">
                     <button
                        className="tdp-mod-btn verify"
                        onClick={() => handleVerify("VERIFIED")}
                        disabled={isVerifying}>
                        <Icons
                           name="check"
                           size={14}
                        />
                        Verify
                     </button>
                     <button
                        className="tdp-mod-btn reject"
                        onClick={() => handleVerify("REJECTED")}
                        disabled={isVerifying}>
                        <Icons
                           name="x"
                           size={14}
                        />
                        Reject
                     </button>
                  </div>
               </div>
            )
         ) : (
            // USER MODE
            <div className="tdp-evidence-votes">
               <button
                  className={`tdp-vote-btn up ${myVoteValue === true ? "active" : ""}`}
                  onClick={() => onVote?.(ev, true)}
                  disabled={isVoting || isOwnEvidence}
                  title={isOwnEvidence ? "You cannot vote on your own evidence." : "Upvote"}>
                  <Icons
                     name="chevron-up"
                     size={13}
                     strokeWidth={2.5}
                     color="#166534"
                  />
                  {upvotes}
               </button>
               <button
                  className={`tdp-vote-btn down ${myVoteValue === false ? "active" : ""}`}
                  onClick={() => onVote?.(ev, false)}
                  disabled={isVoting || isOwnEvidence}
                  title={isOwnEvidence ? "You cannot vote on your own evidence." : "Downvote"}>
                  <Icons
                     name="chevron-down"
                     size={13}
                     strokeWidth={2.5}
                     color="#991b1b"
                  />
                  {downvotes}
               </button>
               <span className="tdp-weighted-score">
                  <Icons
                     name="hash"
                     size={9}
                     color="#6b7280"
                  />
                  Weighted: {weighted}
               </span>
               <span
                  className={`tdp-evidence-status evidence-status-${ev.evidence_status?.toLowerCase()}`}>
                  Status: {ev.evidence_status}
               </span>
               <span className="tdp-vote-policy-hint">
                  {isVoting
                     ? "Syncing vote..."
                     : "Votes are recorded now; trust impact applies after thread resolution."}
               </span>
            </div>
         )}
      </div>
   );
}

export default EvidenceCard;
