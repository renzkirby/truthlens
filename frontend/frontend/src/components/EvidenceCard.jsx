import { useState } from "react";
import { Link } from "react-router-dom";
import Icons from "./Icons";
import { EVIDENCE_VERDICT_META } from "../utils/constants";
import "./EvidenceCard.css";

function EvidenceAvatar({ contributor }) {
   const [failed, setFailed] = useState(false);
   const username = contributor?.username || "Unknown";
   return (
      <span className="evidence-card-avatar">
         {contributor?.avatar_url && !failed ? (
            <img src={contributor.avatar_url} alt="" onError={() => setFailed(true)} />
         ) : (
            <span aria-hidden="true">{username.slice(0, 1).toUpperCase()}</span>
         )}
      </span>
   );
}

function formatEvidenceType(value) {
   return (value || "Evidence")
      .replace(/_/g, " ")
      .toLowerCase()
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function evidenceTypeTone(value) {
   const normalized = String(value || "").toUpperCase();
   if (normalized.includes("SUPPORT")) return "supports";
   if (normalized.includes("CONTRADICT")) return "contradicts";
   if (normalized.includes("CONTEXT")) return "context";
   if (normalized.includes("VERIFICATION")) return "verification";
   return "neutral";
}

function parseSource(value) {
   if (!value) return { host: "", path: "" };
   try {
      const parsed = new URL(value);
      return {
         host: parsed.hostname.replace(/^www\./, ""),
         path: parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "",
      };
   } catch {
      return { host: value.replace(/^https?:\/\//, ""), path: "" };
   }
}

function formatSubmittedAt(value) {
   if (!value) return "Date unavailable";
   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Date unavailable";
   return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
   });
}

export default function EvidenceCard({
   evidence,
   isOwner,
   currentUserId,
   isTop,
   onEdit,
   onDelete,
   onVote,
   votingEvidenceId,
   editingId,
   editingText,
   editingVerdict,
   setEditingId,
   setEditingText,
   setEditingVerdict,
}) {
   const verdict = (evidence.evidence_verdict || "UNVERIFIED").toUpperCase();
   const verdictMeta = EVIDENCE_VERDICT_META[verdict] || EVIDENCE_VERDICT_META.UNVERIFIED;
   const username = evidence.contributor?.username || "Unknown";
   const contributorTrust = Number(evidence.contributor?.trust_score || 0);
   const isEditing = editingId === evidence.id;
   const isOwnEvidence = String(evidence.contributor?.id || "") === String(currentUserId || "");
   const isVoting = votingEvidenceId === evidence.id;
   const reviewStatus = String(evidence.evidence_status || "UNVERIFIED").toUpperCase();
   const typeTone = evidenceTypeTone(evidence.evidence_type);
   const source = parseSource(evidence.evidence_url);
   const sourcePath = source.path.length > 38 ? `${source.path.slice(0, 38)}…` : source.path;
   const upvotes = Number(evidence.upvotes || 0);
   const downvotes = Number(evidence.downvotes || 0);
   const fallbackWeighted = upvotes * (contributorTrust / 100) - downvotes * 0.5;
   const weighted = Number(evidence.weighted_score ?? fallbackWeighted);
   const weightedLabel = Number.isFinite(weighted) ? weighted.toFixed(1) : "0.0";

   return (
      <article className={`evidence-card evidence-card--${typeTone}`}>
         <header className="evidence-card-header">
            <Link className="evidence-card-contributor" to={`/user/${encodeURIComponent(username)}`}>
               <EvidenceAvatar contributor={evidence.contributor} />
               <span>
                  <strong>@{username}</strong>
                  <small>Trust: <b>{contributorTrust.toFixed(1)}</b></small>
               </span>
            </Link>
            <div className="evidence-card-header-actions">
               {isTop && <span className="evidence-card-rank"><Icons name="star" size={12} /> Top ranked</span>}
               {isOwner && !isEditing && (
                  <>
                     <button
                        type="button"
                        onClick={() => {
                           setEditingId(evidence.id);
                           setEditingText(evidence.evidence_caption || "");
                           setEditingVerdict(verdict);
                        }}
                     >
                        Edit
                     </button>
                     <button type="button" className="is-danger" onClick={() => onDelete(evidence.id)}>Delete</button>
                  </>
               )}
            </div>
         </header>

         {isEditing ? (
            <div className="evidence-card-edit">
               <label htmlFor={`evidence-caption-${evidence.id}`}>Evidence explanation</label>
               <textarea id={`evidence-caption-${evidence.id}`} rows={4} value={editingText} onChange={(event) => setEditingText(event.target.value)} />
               <label htmlFor={`evidence-assessment-${evidence.id}`}>Your assessment</label>
               <select id={`evidence-assessment-${evidence.id}`} value={editingVerdict} onChange={(event) => setEditingVerdict(event.target.value)}>
                  {Object.entries(EVIDENCE_VERDICT_META).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
               </select>
               <p>Your assessment is your interpretation, not a TruthLens or professional verdict.</p>
               <div>
                  <button type="button" className="is-primary" onClick={() => onEdit(evidence.id, editingText, editingVerdict)}>Save</button>
                  <button type="button" onClick={() => { setEditingId(null); setEditingText(""); setEditingVerdict("UNVERIFIED"); }}>Cancel</button>
               </div>
            </div>
         ) : (
            <p className="evidence-card-explanation">{evidence.evidence_caption?.trim() || "No explanation provided."}</p>
         )}

         {evidence.evidence_url && (
            <a className="evidence-card-source" href={evidence.evidence_url} target="_blank" rel="noopener noreferrer">
               <span className="evidence-card-source-copy">
                  <small><span className="evidence-card-source-mark" aria-hidden="true">{(source.host?.[0] || "?").toUpperCase()}</span> Evidence source</small>
                  <strong>{source.host || evidence.evidence_url}</strong>
                  {sourcePath && <span className="evidence-card-source-path">{sourcePath}</span>}
               </span>
               <span className="evidence-card-source-cta">Open source <Icons name="external-link" size={14} /></span>
            </a>
         )}

         <div className="evidence-card-semantics">
            <div className="evidence-card-semantic-item">
               <span>Contributor assessment</span>
               <strong className={`evidence-card-assessment evidence-card-assessment--${verdict.toLowerCase()}`}>
                  <Icons name={verdictMeta.icon || "help-circle"} size={13} /> {verdictMeta.label || verdict}
               </strong>
            </div>
            <div className="evidence-card-semantic-item">
               <span>Review status</span>
               <strong className={`evidence-card-review evidence-card-review--${reviewStatus.toLowerCase()}`}>
                  {reviewStatus.charAt(0) + reviewStatus.slice(1).toLowerCase()}
               </strong>
            </div>
            <div className="evidence-card-semantic-item">
               <span>Evidence type</span>
               <strong className={`evidence-card-type evidence-card-type--${typeTone}`}>{formatEvidenceType(evidence.evidence_type)}</strong>
            </div>
            <time dateTime={evidence.submitted_at}>{formatSubmittedAt(evidence.submitted_at)}</time>
         </div>

         <footer className="evidence-card-votes">
            <div className="evidence-card-vote-cluster" role="group" aria-label="Community evidence voting">
               <button
                  type="button"
                  className={`evidence-card-vote evidence-card-vote--up ${evidence.my_vote?.vote_value === true ? "is-selected" : ""}`}
                  aria-pressed={evidence.my_vote?.vote_value === true}
                  onClick={() => onVote?.(evidence, true)}
                  disabled={isVoting || isOwnEvidence}
                  title={isOwnEvidence ? "You cannot vote on your own evidence." : "Upvote evidence"}
               >
                  <Icons name="chevron-up" size={15} /> <span className="sr-only">Upvote</span>{upvotes}
               </button>
               <button
                  type="button"
                  className={`evidence-card-vote evidence-card-vote--down ${evidence.my_vote?.vote_value === false ? "is-selected" : ""}`}
                  aria-pressed={evidence.my_vote?.vote_value === false}
                  onClick={() => onVote?.(evidence, false)}
                  disabled={isVoting || isOwnEvidence}
                  title={isOwnEvidence ? "You cannot vote on your own evidence." : "Downvote evidence"}
               >
                  <Icons name="chevron-down" size={15} /> <span className="sr-only">Downvote</span>{downvotes}
               </button>
               <span className="evidence-card-weighted"><Icons name="hash" size={12} /> Weighted: {weightedLabel}</span>
            </div>
            <span className="evidence-card-vote-hint">
               {isOwnEvidence
                  ? "Your own evidence is not votable."
                  : isVoting
                    ? "Syncing vote…"
                    : "Votes are recorded now; trust impact applies after thread resolution."}
            </span>
         </footer>
      </article>
   );
}
