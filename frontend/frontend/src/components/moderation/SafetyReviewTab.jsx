import { useMemo } from "react";
import Icons from "../Icons";
import VerdictBadge from "./VerdictBadge";
import StatusBadge from "./StatusBadge";
import { timeAgo } from "./moderationUtils";
import { getAiVerdict } from "../../utils/verdict";

function SafetyReviewTab({
   threads,
   loading,
   error,
   statusFilter,
   onStatusFilterChange,
   searchQuery,
   onSearchChange,
   onOpenThread,
   onSafetyAction,
   actingThreadId,
}) {
   const filteredThreads = useMemo(() => {
      return threads.filter((thread) => {
         const matchesStatus =
            statusFilter === "ALL" ||
            (statusFilter === "OPEN" && (thread.status === "OPEN" || !thread.status)) ||
            (statusFilter === "CLOSED" && thread.status === "CLOSED") ||
            (statusFilter === "PENDING" && thread.status === "PENDING") ||
            (statusFilter === "REJECTED" && thread.status === "REJECTED");

         const query = searchQuery.trim().toLowerCase();
         const matchesSearch =
            query.length === 0 ||
            thread.claim?.ai_summary?.toLowerCase().includes(query) ||
            thread.caption?.toLowerCase().includes(query) ||
            thread.author?.username?.toLowerCase().includes(query) ||
            thread.flag_reason?.toLowerCase().includes(query);

         return matchesStatus && matchesSearch;
      });
   }, [threads, statusFilter, searchQuery]);

   return (
      <>
         <div className="mod-filters box-panel">
            <div className="mod-filter-left">
               <span className="mod-filter-label">Safety Status:</span>
               {["ALL", "PENDING", "OPEN", "CLOSED", "REJECTED"].map((item) => (
                  <button
                     key={item}
                     className={`mod-filter-btn ${statusFilter === item ? "active" : ""}`}
                     onClick={() => onStatusFilterChange(item)}>
                     {item}
                  </button>
               ))}
            </div>
            <div className="mod-search-box">
               <Icons
                  name="search"
                  size={14}
                  color="var(--text-muted)"
               />
               <input
                  type="text"
                  placeholder="Search flagged threads..."
                  value={searchQuery}
                  onChange={(e) => onSearchChange(e.target.value)}
               />
            </div>
         </div>

         <div className="mod-table-wrapper box-panel">
            <div className="mod-table-header">
               <h2 className="mod-section-title">
                  <Icons
                     name="shield"
                     size={15}
                  />
                  Safety Review Queue
                  <span className="mod-count-pill">{filteredThreads.length}</span>
               </h2>
            </div>

            {loading && <p className="mod-empty">Loading safety queue...</p>}
            {error && <p className="mod-error">{error}</p>}
            {!loading && !error && filteredThreads.length === 0 && (
               <p className="mod-empty">No flagged threads for this filter.</p>
            )}

            {!loading && !error && filteredThreads.length > 0 && (
               <div className="mod-table">
                  <div className="mod-table-row mod-table-head mod-table-row-safety">
                     <span>Claim</span>
                     <span>AI Verdict</span>
                     <span>Reports</span>
                     <span>Author</span>
                     <span>Status</span>
                     <span>Action</span>
                  </div>

                  {filteredThreads.map((thread) => {
                     const isActing = actingThreadId === thread.id;
                     return (
                        <div
                           key={thread.id}
                           className="mod-table-row mod-table-data mod-table-row-safety">
                           <div className="mod-claim-cell">
                              <p className="mod-claim-text">
                                 {thread.claim?.ai_summary || thread.caption || "No summary"}
                              </p>
                              <span className="mod-claim-time">{timeAgo(thread.created_at)}</span>
                           </div>

                           <div>
                              {getAiVerdict(thread.claim) ? (
                                 <VerdictBadge verdict={getAiVerdict(thread.claim)} />
                              ) : (
                                 <span className="mod-na">-</span>
                              )}
                           </div>

                           <div className="mod-report-cell">
                              <span className="mod-report-count">{thread.flag_count || 0}</span>
                              <span className="mod-report-label">reports</span>
                           </div>

                           <div className="mod-author-cell">
                              <span className="mod-author-name">@{thread.author?.username}</span>
                              <span className="mod-trust-score">
                                 Trust: {thread.author?.trust_score?.toFixed(1) || "0.0"}
                              </span>
                           </div>

                           <StatusBadge status={thread.status} />

                           <div className="mod-actions-cell">
                              <button
                                 className="mod-action-btn view"
                                 onClick={() => onOpenThread(thread.id)}
                                 title="Open thread detail">
                                 <Icons
                                    name="eye"
                                    size={13}
                                 />
                              </button>
                              <button
                                 className="mod-action-btn reopen"
                                 onClick={() => onSafetyAction(thread.id, "DISMISS")}
                                 disabled={isActing}
                                 title="Dismiss reports and keep thread open">
                                 <Icons
                                    name="check-circle"
                                    size={13}
                                 />
                              </button>
                              <button
                                 className="mod-action-btn close"
                                 onClick={() => onSafetyAction(thread.id, "REMOVE")}
                                 disabled={isActing}
                                 title="Remove thread from community feed">
                                 <Icons
                                    name="x-circle"
                                    size={13}
                                 />
                              </button>
                              <button
                                 className="mod-action-btn"
                                 onClick={() => onSafetyAction(thread.id, "ESCALATE")}
                                 disabled={isActing}
                                 title="Escalate for full moderator review">
                                 <Icons
                                    name="arrow-right"
                                    size={13}
                                 />
                              </button>
                           </div>
                        </div>
                     );
                  })}
               </div>
            )}
         </div>
      </>
   );
}

export default SafetyReviewTab;
