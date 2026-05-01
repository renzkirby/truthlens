import Icons from "../Icons";

const VERDICT_OPTIONS = ["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"];
const STATUS_OPTIONS = ["OPEN", "CLOSED", "REJECTED"];

function ModeratorDecisionPanel({
   thread,
   decision,
   onDecisionChange,
   onResolveThread,
   isResolving,
   onClose,
}) {

   const isMissingRequiredClaim = 
      decision.status === "CLOSED" && 
      ["FACT", "FAKE", "MISLEADING", "SATIRE"].includes(decision.verdict) && 
      (!decision.canonical_claim || decision.canonical_claim.trim() === "");

   return (
      <div className="mod-decision-panel">
         <div className="mod-decision-header">
            <h3 className="mod-decision-title">Moderator Decision</h3>
            <button
               className="mod-decision-close-btn"
               onClick={onClose}
               title="Close">
               <Icons
                  name="x"
                  size={16}
               />
            </button>
         </div>

         <div className="mod-decision-content">
            <div className="mod-decision-section">
               <label className="mod-decision-label">Final Verdict</label>
               <select
                  className="mod-decision-select"
                  value={decision.verdict}
                  onChange={(e) => onDecisionChange(thread.id, { verdict: e.target.value })}>
                  {VERDICT_OPTIONS.map((option) => (
                     <option
                        key={option}
                        value={option}>
                        {option}
                     </option>
                  ))}
               </select>
               <p className="mod-decision-hint">
                  This will override the AI verdict and become the final verdict.
               </p>
            </div>

            {/* --- NEW SECTION: CANONICAL CLAIM --- */}
            <div className="mod-decision-section">
               <label className="mod-decision-label">Official Claim Statement (Vault)</label>
               <textarea
                  className="mod-decision-textarea"
                  rows={2}
                  value={decision.canonical_claim || ""}
                  onChange={(e) => onDecisionChange(thread.id, { canonical_claim: e.target.value })}
                  placeholder="e.g., 'Vice President Sara Duterte stated...'"
               />
               <p className="mod-decision-hint" style={{ color: "var(--verdict-misleading-text, #b45309)", fontWeight: "500" }}>
                  Required if closing thread. Write a clean, third-person version of the rumor. This powers the AI Semantic Search.
               </p>
            </div>

            <div className="mod-decision-section">
               <label className="mod-decision-label">Thread Status</label>
               <select
                  className="mod-decision-select"
                  value={decision.status}
                  onChange={(e) => onDecisionChange(thread.id, { status: e.target.value })}>
                  {STATUS_OPTIONS.map((option) => (
                     <option
                        key={option}
                        value={option}>
                        {option}
                     </option>
                  ))}
               </select>
               <p className="mod-decision-hint">
                  Status tracks the moderation lifecycle (OPEN/CLOSED/REJECTED).
               </p>
            </div>

            <div className="mod-decision-section">
               <label className="mod-decision-label">Moderator Notes</label>
               <textarea
                  className="mod-decision-textarea"
                  rows={4}
                  value={decision.notes}
                  onChange={(e) => onDecisionChange(thread.id, { notes: e.target.value })}
                  placeholder="Explain your moderation decision, reasoning, or any actions taken..."
               />
               <p className="mod-decision-hint">
                  These notes are internal and visible only to moderators.
               </p>
            </div>

            <div className="mod-decision-actions">
               <button
                  className="mod-decision-resolve-btn"
                  onClick={() => onResolveThread(thread.id)}
                  disabled={isResolving || isMissingRequiredClaim}>
                  <Icons
                     name="check"
                     size={14}
                  />
                  {isResolving ? "Saving..." : "Resolve Thread"}
               </button>
               <button
                  className="mod-decision-cancel-btn"
                  onClick={onClose}>
                  Cancel
               </button>
            </div>
         </div>
      </div>
   );
}

export default ModeratorDecisionPanel;
