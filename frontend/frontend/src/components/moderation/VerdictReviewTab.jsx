import { useMemo, useState } from "react";
import Icons from "../Icons";
import VerdictBadge from "./VerdictBadge";
import StatusBadge from "./StatusBadge";
import { timeAgo } from "./moderationUtils";
import { getAiVerdict } from "../../utils/verdict";
import ModeratorDecisionPanel from "./ModeratorDecisionPanel";

const STATUS_OPTIONS = ["OPEN", "CLOSED", "REJECTED"];

function VerdictReviewTab({
   threads,
   loading,
   error,
   reviewedFilter,
   onReviewedFilterChange,
   searchQuery,
   onSearchChange,
   decisions,
   onDecisionChange,
   onResolveThread,
   resolvingThreadId,
   onOpenThread,
}) {
   const [expandedThreadId, setExpandedThreadId] = useState(null);
   const filteredThreads = useMemo(() => {
      return threads.filter((thread) => {
         const isReviewed = Boolean(thread.moderator_verdict);
         const matchesReviewed =
            reviewedFilter === "all" ||
            (reviewedFilter === "pending" && !isReviewed) ||
            (reviewedFilter === "resolved" && isReviewed);

         const query = searchQuery.trim().toLowerCase();
         const matchesSearch =
            query.length === 0 ||
            thread.claim?.ai_summary?.toLowerCase().includes(query) ||
            thread.caption?.toLowerCase().includes(query) ||
            thread.author?.username?.toLowerCase().includes(query);

         return matchesReviewed && matchesSearch;
      });
   }, [threads, reviewedFilter, searchQuery]);

   const getDecisionState = (thread) => {
      const existing = decisions[thread.id];
      if (existing) return existing;
      const status = STATUS_OPTIONS.includes(thread.status) ? thread.status : "CLOSED";
      return {
         verdict:
            thread.moderator_verdict ||
            thread.claim?.final_verdict ||
            thread.claim?.ai_verdict ||
            "UNVERIFIED",
         status,
         notes: thread.moderator_notes || "",
      };
   };

   return (
      <>
         <div className="mod-filters box-panel">
            <div className="mod-filter-left">
               <span className="mod-filter-label">Review State:</span>
               {["all", "pending", "resolved"].map((item) => (
                  <button
                     key={item}
                     className={`mod-filter-btn ${reviewedFilter === item ? "active" : ""}`}
                     onClick={() => onReviewedFilterChange(item)}>
                     {item.toUpperCase()}
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
                  placeholder="Search adjudication queue..."
                  value={searchQuery}
                  onChange={(e) => onSearchChange(e.target.value)}
               />
            </div>
         </div>

         <div className="mod-table-wrapper box-panel">
            <div className="mod-table-header">
               <h2 className="mod-section-title">
                  <Icons
                     name="list-checks"
                     size={15}
                  />
                  Verdict Review Queue
                  <span className="mod-count-pill">{filteredThreads.length}</span>
               </h2>
            </div>

            {loading && <p className="mod-empty">Loading verdict queue...</p>}
            {error && <p className="mod-error">{error}</p>}
            {!loading && !error && filteredThreads.length === 0 && (
               <p className="mod-empty">No threads in this adjudication filter.</p>
            )}

            {!loading && !error && filteredThreads.length > 0 && (
               <div className="mod-table">
                  <div className="mod-table-row mod-table-head mod-table-row-verdict">
                     <span>Claim</span>
                     <span>AI</span>
                     <span>Moderator</span>
                     <span>Status</span>
                     <span></span>
                  </div>

                  {filteredThreads.map((thread) => {
                     const decision = getDecisionState(thread);
                     const isResolving = resolvingThreadId === thread.id;
                     const isExpanded = expandedThreadId === thread.id;

                     return (
                        <div
                           key={thread.id}
                           className="mod-expandable-row-wrapper">
                           <div className="mod-table-row mod-table-data mod-table-row-verdict">
                              <div className="mod-claim-cell">
                                 <p className="mod-claim-text">
                                    {thread.claim?.ai_summary || thread.caption || "No summary"}
                                 </p>
                                 <span className="mod-claim-time">
                                    {timeAgo(thread.created_at)}
                                 </span>
                              </div>

                              <div>
                                 {getAiVerdict(thread.claim) ? (
                                    <VerdictBadge verdict={getAiVerdict(thread.claim)} />
                                 ) : (
                                    <span className="mod-na">-</span>
                                 )}
                              </div>

                              <div>
                                 {thread.moderator_verdict || thread.claim?.final_verdict ? (
                                    <VerdictBadge
                                       verdict={
                                          thread.moderator_verdict || thread.claim?.final_verdict
                                       }
                                    />
                                 ) : (
                                    <span className="mod-na">Pending</span>
                                 )}
                              </div>
                              <div>
                                 <StatusBadge status={thread.status} />
                              </div>
                              <div className="mod-row-actions">
                                 <button
                                    className="mod-expand-btn"
                                    onClick={() =>
                                       setExpandedThreadId(isExpanded ? null : thread.id)
                                    }
                                    title={isExpanded ? "Collapse" : "Expand to review"}>
                                    <Icons
                                       name={isExpanded ? "chevron-up" : "chevron-down"}
                                       size={16}
                                    />
                                 </button>
                                 <button
                                    className="mod-action-btn view"
                                    onClick={() => onOpenThread(thread.id)}
                                    title="Open thread detail">
                                    <Icons
                                       name="eye"
                                       size={13}
                                    />
                                 </button>
                              </div>
                           </div>

                           {isExpanded && (
                              <div className="mod-expanded-panel-wrapper">
                                 <ModeratorDecisionPanel
                                    thread={thread}
                                    decision={decision}
                                    onDecisionChange={onDecisionChange}
                                    onResolveThread={onResolveThread}
                                    isResolving={isResolving}
                                    onClose={() => setExpandedThreadId(null)}
                                 />
                              </div>
                           )}
                        </div>
                     );
                  })}
               </div>
            )}
         </div>
      </>
   );
}

export default VerdictReviewTab;
