import Icons from "../Icons";
import VerdictBadge from "./VerdictBadge";
import { timeAgo } from "./moderationUtils";
import { getAiVerdict } from "../../utils/verdict";

function ModerationSidebar({ recentClaims }) {
   return (
      <div className="mod-sidebar">
         <div className="box-panel">
            <h2 className="mod-section-title">
               <Icons
                  name="activity"
                  size={15}
               />
               Recent AI Verdicts
            </h2>
            <div className="mod-recent-list">
               {recentClaims.length === 0 ? (
                  <p className="mod-empty">No claims yet.</p>
               ) : (
                  recentClaims.map((claim) => (
                     <div
                        key={claim.id}
                        className="mod-recent-item">
                        <div className="mod-recent-top">
                           {getAiVerdict(claim) ? (
                              <VerdictBadge verdict={getAiVerdict(claim)} />
                           ) : (
                              <span className="mod-status-badge open">PENDING</span>
                           )}
                           <span className="mod-recent-time">{timeAgo(claim.last_updated)}</span>
                        </div>
                        <p className="mod-recent-summary">{claim.ai_summary || "Processing..."}</p>
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
                              <span className="mod-conf-label">{claim.consensus_score}%</span>
                           </div>
                        )}
                     </div>
                  ))
               )}
            </div>
         </div>

         <div className="box-panel mod-notes-card">
            <h2 className="mod-section-title">
               <Icons
                  name="file-text"
                  size={15}
               />
               Moderator Notes
            </h2>
            <textarea
               className="mod-notes-input"
               placeholder="Add internal notes here... (local only for now)"
               rows={5}
            />
            <p className="mod-notes-hint">Notes are not saved yet. Backend endpoint needed.</p>
         </div>
      </div>
   );
}

export default ModerationSidebar;
