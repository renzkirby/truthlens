import { useState, useEffect } from "react";
import { useAuth } from "../../context/AuthContext";
import { useNotification } from "../../context/NotificationContext";
import { API_BASE_URL } from "../../utils/constants";
import Icons from "../Icons";
import EvidenceCard from "../EvidenceCard";
import "./ModeratorPanel.css";

function ModeratorPanel({ onVerificationComplete }) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();
   const [unverifiedEvidence, setUnverifiedEvidence] = useState([]);
   const [loading, setLoading] = useState(false);
   const [error, setError] = useState(null);
   const [verifyingId, setVerifyingId] = useState(null);

   useEffect(() => {
      loadGlobalQueue();
   }, []);

   const loadGlobalQueue = async () => {
      setLoading(true);
      setError(null);
      try {
         const data = await authFetch(
            `${API_BASE_URL}/moderation/evidence-queue/?status=UNVERIFIED`,
            { method: "GET" },
         );
         setUnverifiedEvidence(data);
      } catch (error) {
         console.error("Failed to load evidence queue:", error);
         setError("Failed to load evidence queue. Please try again.");
      } finally {
         setLoading(false);
      }
   };

   // Group evidence by thread/claim for context headers
   const groupedEvidence = unverifiedEvidence.reduce((acc, ev) => {
      const threadId = ev.thread?.id;
      if (!acc[threadId]) {
         acc[threadId] = {
            thread: ev.thread,
            claim: ev.thread?.claim,
            items: [],
         };
      }
      acc[threadId].items.push(ev);
      return acc;
   }, {});

   const handleVerify = async (evidenceId, status, notes) => {
      setVerifyingId(evidenceId);
      try {
         await authFetch(`${API_BASE_URL}/evidence/${evidenceId}/verify/`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               evidence_status: status,
               moderator_notes: notes,
            }),
         });

         // Show success toast
         const statusLabel = status === "VERIFIED" ? "Verified" : "Rejected";
         addToast({
            type: "success",
            title: `Evidence ${statusLabel}`,
            message: `This evidence has been marked as ${statusLabel.toLowerCase()}.`,
            duration: 3000,
         });

         await loadGlobalQueue();
         onVerificationComplete?.();
      } catch (error) {
         console.error("Failed to verify evidence:", error);
         setError("Failed to verify evidence. Please try again.");

         // Show error toast
         addToast({
            type: "error",
            title: "Verification Failed",
            message: error.message || "An error occurred. Please try again.",
            duration: 4000,
         });
      } finally {
         setVerifyingId(null);
      }
   };

   return (
      <div className="mod-panel">
         <div className="mod-panel-header">
            <Icons
               name="shield"
               size={16}
               color="#059669"
               strokeWidth={2.5}
            />
            <h3>Global Moderation Queue</h3>
            <span className="mod-queue-count">{unverifiedEvidence.length}</span>
         </div>

         {error && (
            <div className="mod-error-banner">
               <Icons
                  name="alert-circle"
                  size={16}
                  color="#dc2626"
               />
               <span>{error}</span>
               <button
                  className="mod-retry-btn"
                  onClick={loadGlobalQueue}>
                  Retry
               </button>
            </div>
         )}

         {loading && (
            <div className="mod-loading">
               <div className="mod-spinner" />
               <p>Loading unverified evidence…</p>
            </div>
         )}

         {!loading && (
            <div className="mod-evidence-list">
               {unverifiedEvidence.length === 0 && (
                  <p className="mod-empty">
                     <Icons
                        name="check-circle"
                        size={20}
                        color="#10b981"
                     />
                     All evidence verified! Great work.
                  </p>
               )}
               {Object.entries(groupedEvidence).map(([threadId, group]) => {
                  const { thread, claim, items } = group;
                  const claimText = claim?.context_text || "Unknown claim";
                  const claimVerdict = claim?.verdict || "UNVERIFIED";
                  console.log(group);

                  return (
                     <div
                        key={threadId}
                        className="mod-thread-group">
                        {/* Claim context header */}
                        <div className="mod-claim-context">
                           <div className="mod-claim-header">
                              <Icons
                                 name="alert-circle"
                                 size={14}
                                 color="#7c3aed"
                                 strokeWidth={2}
                              />
                              <div className="mod-claim-info">
                                 <div className="mod-claim-text">{claimText}</div>
                                 <div className="mod-claim-meta">
                                    <span
                                       className={`mod-claim-verdict verdict-${claimVerdict.toLowerCase()}`}>
                                       {claimVerdict}
                                    </span>
                                    <span className="mod-claim-count">
                                       {items.length} evidence{" "}
                                       {items.length === 1 ? "item" : "items"}
                                    </span>
                                 </div>
                              </div>
                              <div className="mod-claim-actions">
                                 {/* {claim?.id && (
                                    <a
                                       href={`/claim/${claim.id}`}
                                       className="mod-action-link claim"
                                       title="View claim detail"
                                       target="_blank"
                                       rel="noopener noreferrer">
                                       <Icons
                                          name="info"
                                          size={13}
                                       />
                                       Claim
                                    </a>
                                 )} */}
                                 {thread?.id && (
                                    <a
                                       href={`/thread/detail/${thread.id}?tab=evidence`}
                                       className="mod-action-link thread"
                                       title="View full thread discussion"
                                       target="_blank"
                                       rel="noopener noreferrer">
                                       <Icons
                                          name="message-circle"
                                          size={13}
                                       />
                                       Thread
                                    </a>
                                 )}
                              </div>
                           </div>
                           <div className="mod-thread-info">
                              <span className="mod-thread-caption">
                                 "{thread?.caption || "Unknown"}"
                              </span>
                           </div>
                        </div>

                        {/* Evidence items for this claim/thread */}
                        <div className="mod-evidence-items">
                           {items.map((evidence, index) => (
                              <div
                                 key={evidence.id}
                                 className="mod-evidence-wrapper">
                                 {/* Evidence position indicator */}
                                 <span className="mod-evidence-index">
                                    Evidence {index + 1} of {items.length}
                                 </span>

                                 {/* Evidence card */}
                                 <EvidenceCard
                                    key={evidence.id}
                                    evidence={evidence}
                                    isModerator={true}
                                    isOwner={false}
                                    onVerify={handleVerify}
                                    editingId={null}
                                    editingText=""
                                    editingVerdict="UNVERIFIED"
                                    setEditingId={() => {}}
                                    setEditingText={() => {}}
                                    setEditingVerdict={() => {}}
                                 />
                              </div>
                           ))}
                        </div>
                     </div>
                  );
               })}
            </div>
         )}
      </div>
   );
}

export default ModeratorPanel;
