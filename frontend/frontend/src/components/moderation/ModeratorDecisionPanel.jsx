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
                  disabled={isResolving}>
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
