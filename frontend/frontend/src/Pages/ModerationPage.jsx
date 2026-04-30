import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";
import SafetyReviewTab from "../components/moderation/SafetyReviewTab";
import VerdictReviewTab from "../components/moderation/VerdictReviewTab";
import ModerationSidebar from "../components/moderation/ModerationSidebar";
import ModeratorPanel from "../components/moderation/ModeratorPanel";
import { getEffectiveVerdict } from "../utils/verdict";
import "./ModerationPage.css";

function ModerationPage() {
   const { authFetch } = useAuth();
   const navigate = useNavigate();

   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
   const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}/${path}`;

   const [activeTab, setActiveTab] = useState("safety");

   const [safetyThreads, setSafetyThreads] = useState([]);
   const [verdictThreads, setVerdictThreads] = useState([]);
   const [claims, setClaims] = useState([]);

   const [safetyLoading, setSafetyLoading] = useState(true);
   const [verdictLoading, setVerdictLoading] = useState(true);
   const [claimsLoading, setClaimsLoading] = useState(true);

   const [safetyError, setSafetyError] = useState(null);
   const [verdictError, setVerdictError] = useState(null);
   const [claimsError, setClaimsError] = useState(null);

   const [modStats, setModStats] = useState(null);

   const [safetyStatusFilter, setSafetyStatusFilter] = useState("ALL");
   const [safetySearch, setSafetySearch] = useState("");
   const [verdictReviewedFilter, setVerdictReviewedFilter] = useState("all");
   const [verdictSearch, setVerdictSearch] = useState("");

   const [decisionDrafts, setDecisionDrafts] = useState({});
   const [resolvingThreadId, setResolvingThreadId] = useState(null);
   const [safetyActingThreadId, setSafetyActingThreadId] = useState(null);
   const [safetyActionDialog, setSafetyActionDialog] = useState({
      open: false,
      threadId: null,
      action: null,
      notes: "",
   });

   const loadSafetyQueue = async () => {
      try {
         setSafetyLoading(true);
         setSafetyError(null);
         const data = await authFetch(apiUrl("moderation/queue/?status=ALL"), {
            method: "GET",
         });
         setSafetyThreads(data || []);
      } catch (error) {
         setSafetyError("Failed to load safety review queue.");
      } finally {
         setSafetyLoading(false);
      }
   };

   const loadVerdictQueue = async () => {
      try {
         setVerdictLoading(true);
         setVerdictError(null);
         const data = await authFetch(apiUrl("moderation/verdict-queue/?reviewed=all"), {
            method: "GET",
         });
         setVerdictThreads(data || []);
      } catch (error) {
         setVerdictError("Failed to load verdict adjudication queue.");
      } finally {
         setVerdictLoading(false);
      }
   };

   const loadClaims = async () => {
      try {
         setClaimsLoading(true);
         setClaimsError(null);
         const data = await authFetch(apiUrl("claims/"), { method: "GET" });
         setClaims(data || []);
      } catch (error) {
         setClaimsError("Failed to load recent AI verdicts.");
      } finally {
         setClaimsLoading(false);
      }
   };

   const loadStats = async () => {
      try {
         const data = await authFetch(apiUrl("moderation/stats/"), { method: "GET" });
         setModStats(data);
      } catch (error) {
         console.error("Failed to load moderation stats", error);
      }
   };

   useEffect(() => {
      loadSafetyQueue();
      loadVerdictQueue();
      loadClaims();
      loadStats();
   }, []);

   const handleOpenThread = (threadId) => {
      navigate(`/thread/detail/${threadId}`);
   };

   const handleDecisionChange = (threadId, patch) => {
      setDecisionDrafts((prev) => {
         const prevDraft = prev[threadId] || {};
         return {
            ...prev,
            [threadId]: {
               ...prevDraft,
               ...patch,
            },
         };
      });
   };

   const handleResolveThread = async (threadId) => {
      const thread = verdictThreads.find((item) => item.id === threadId);
      if (!thread) return;

      const draft = decisionDrafts[threadId] || {};
      const threadStatus = ["OPEN", "CLOSED", "REJECTED"].includes(thread.status)
         ? thread.status
         : "CLOSED";
      const payload = {
         moderator_verdict:
            draft.verdict ||
            thread.moderator_verdict ||
            thread.claim?.final_verdict ||
            thread.claim?.ai_verdict ||
            "UNVERIFIED",
         status: draft.status || threadStatus,
         moderator_notes: draft.notes ?? thread.moderator_notes ?? "",
         canonical_claim: draft.canonical_claim || "",
      };

      try {
         setResolvingThreadId(threadId);
         const updated = await authFetch(apiUrl(`moderation/threads/${threadId}/resolve/`), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
         });

         setVerdictThreads((prev) => prev.map((item) => (item.id === threadId ? updated : item)));
         setSafetyThreads((prev) => prev.map((item) => (item.id === threadId ? updated : item)));
         setDecisionDrafts((prev) => {
            const next = { ...prev };
            delete next[threadId];
            return next;
         });
      } catch (error) {
         setVerdictError(error?.message || "Unable to resolve thread.");
      } finally {
         setResolvingThreadId(null);
      }
   };

   const handleSafetyAction = async (threadId, action) => {
      const defaultNotes =
         action === "REMOVE"
            ? "Removed after safety review."
            : action === "DISMISS"
              ? "Reports reviewed and dismissed."
              : "Escalated from safety queue for further review.";

      setSafetyActionDialog({
         open: true,
         threadId,
         action,
         notes: defaultNotes,
      });
   };

   const submitSafetyAction = async () => {
      const threadId = safetyActionDialog.threadId;
      const action = safetyActionDialog.action;
      const notes = safetyActionDialog.notes || "";
      if (!threadId || !action) return;

      try {
         setSafetyActingThreadId(threadId);
         const updated = await authFetch(apiUrl(`moderation/threads/${threadId}/safety-action/`), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action, moderator_notes: notes }),
         });

         // Safety queue only contains flagged threads; action clears flags so it drops from this list.
         setSafetyThreads((prev) => prev.filter((item) => item.id !== threadId));
         // Keep verdict queue in sync with updated status/notes.
         setVerdictThreads((prev) =>
            prev.map((item) => (item.id === threadId ? { ...item, ...updated } : item)),
         );
         setSafetyActionDialog({ open: false, threadId: null, action: null, notes: "" });
      } catch (error) {
         setSafetyError(error?.message || "Unable to apply safety action.");
      } finally {
         setSafetyActingThreadId(null);
      }
   };

   const safetyActionMeta = useMemo(() => {
      const action = safetyActionDialog.action;
      if (action === "REMOVE") {
         return {
            code: "REMOVE",
            title: "Policy Action: REMOVE",
            description:
               "Permanently remove this thread from active circulation after confirming harmful or policy-violating content.",
            cta: "Confirm Remove",
            tone: "danger",
         };
      }

      if (action === "ESCALATE") {
         return {
            code: "ESCALATE",
            title: "Policy Action: ESCALATE",
            description:
               "Escalate this thread for deeper review when evidence is contested or needs senior moderation attention.",
            cta: "Confirm Escalation",
            tone: "warning",
         };
      }

      return {
         code: "DISMISS",
         title: "Policy Action: DISMISS",
         description:
            "Dismiss the report after review when no policy violation is found and keep the thread visible.",
         cta: "Confirm Dismissal",
         tone: "neutral",
      };
   }, [safetyActionDialog.action]);

   const recentClaims = useMemo(() => {
      return [...claims]
         .sort((a, b) => new Date(b.last_updated) - new Date(a.last_updated))
         .slice(0, 8);
   }, [claims]);

   const openThreads = modStats?.open_threads || 0;
   const closedThreads = modStats?.closed_threads || 0;
   const flaggedThreads = modStats?.flagged_threads || 0;
   const pendingVerdicts = modStats?.pending_verdicts || 0;

   // ── Render ───────────────────────────────────────────────────────────────
   return (
      <div className="mod-layout">
         <NavigationBar />

         <main className="mod-container">
            {/* ── Page Header ── */}
            <div className="mod-header">
               <div className="mod-header-left">
                  <div className="mod-header-icon">
                     <Icons
                        name="shield"
                        size={22}
                        color="#fff"
                     />
                  </div>
                  <div>
                     <h1 className="mod-title">Moderation Panel</h1>
                     <p className="mod-subtitle">
                        Safety moderation and final verdict adjudication in separate queues.
                     </p>
                  </div>
               </div>
               <div className="mod-header-right">
                  <span className="mod-access-badge">
                     <Icons
                        name="lock"
                        size={12}
                     />
                     Moderator Access
                  </span>
               </div>
            </div>

            {/* ── Overview Stats Row ── */}
            {/* TODO: Replace with real-time stats from a dedicated /api/moderation/stats/ endpoint */}
            <div className="mod-stats-row">
               <div className="mod-stat-card">
                  <Icons
                     name="alert-triangle"
                     size={18}
                     color="var(--verdict-misleading-border)"
                  />
                  <div>
                     <p className="mod-stat-value">{flaggedThreads}</p>
                     <p className="mod-stat-label">Flagged Threads</p>
                  </div>
               </div>
               <div className="mod-stat-card">
                  <Icons
                     name="check-circle"
                     size={18}
                     color="var(--verdict-fact-border)"
                  />
                  <div>
                     <p className="mod-stat-value">{closedThreads}</p>
                     <p className="mod-stat-label">Closed Threads</p>
                  </div>
               </div>
               <div className="mod-stat-card">
                  <Icons
                     name="x-circle"
                     size={18}
                     color="var(--verdict-fake-border)"
                  />
                  <div>
                     <p className="mod-stat-value">{openThreads}</p>
                     <p className="mod-stat-label">Open Threads</p>
                  </div>
               </div>
               <div className="mod-stat-card">
                  <Icons
                     name="help-circle"
                     size={18}
                     color="var(--verdict-unverified-border)"
                  />
                  <div>
                     <p className="mod-stat-value">{pendingVerdicts}</p>
                     <p className="mod-stat-label">Pending Verdicts</p>
                  </div>
               </div>
            </div>

            <div className="mod-body">
               <div className="mod-queue">
                  <div className="mod-tab-bar box-panel">
                     <button
                        className={`mod-tab-btn ${activeTab === "safety" ? "active" : ""}`}
                        onClick={() => setActiveTab("safety")}>
                        <Icons
                           name="shield"
                           size={14}
                        />
                        Safety Review
                     </button>
                     <button
                        className={`mod-tab-btn ${activeTab === "verdict" ? "active" : ""}`}
                        onClick={() => setActiveTab("verdict")}>
                        <Icons
                           name="list-checks"
                           size={14}
                        />
                        Verdict Review
                     </button>
                     <button
                        className={`mod-tab-btn ${activeTab === "evidence" ? "active" : ""}`}
                        onClick={() => setActiveTab("evidence")}>
                        <Icons
                           name="paperclip"
                           size={14}
                        />
                        Evidence Review
                     </button>
                  </div>

                  {activeTab === "safety" ? (
                     <SafetyReviewTab
                        threads={safetyThreads}
                        loading={safetyLoading}
                        error={safetyError}
                        statusFilter={safetyStatusFilter}
                        onStatusFilterChange={setSafetyStatusFilter}
                        searchQuery={safetySearch}
                        onSearchChange={setSafetySearch}
                        onOpenThread={handleOpenThread}
                        onSafetyAction={handleSafetyAction}
                        actingThreadId={safetyActingThreadId}
                     />
                  ) : activeTab === "evidence" ? (
                     <div className="mod-evidence-tab-content">
                        <ModeratorPanel onVerificationComplete={() => {}} />
                     </div>
                  ) : (
                     <VerdictReviewTab
                        threads={verdictThreads}
                        loading={verdictLoading}
                        error={verdictError}
                        reviewedFilter={verdictReviewedFilter}
                        onReviewedFilterChange={setVerdictReviewedFilter}
                        searchQuery={verdictSearch}
                        onSearchChange={setVerdictSearch}
                        decisions={decisionDrafts}
                        onDecisionChange={handleDecisionChange}
                        onResolveThread={handleResolveThread}
                        resolvingThreadId={resolvingThreadId}
                        onOpenThread={handleOpenThread}
                     />
                  )}
               </div>

               <ModerationSidebar loading={claimsLoading} recentClaims={claimsLoading || claimsError ? [] : recentClaims} />
            </div>

            {safetyActionDialog.open && (
               <div className="mod-dialog-overlay">
                  <div className="mod-dialog">
                     <div className={`mod-dialog-policy-chip ${safetyActionMeta.tone}`}>
                        {safetyActionMeta.code}
                     </div>
                     <h3 className="mod-dialog-title">{safetyActionMeta.title}</h3>
                     <p className="mod-dialog-text">{safetyActionMeta.description}</p>
                     <label className="mod-dialog-label">Moderator notes</label>
                     <textarea
                        className="mod-dialog-textarea"
                        rows={4}
                        value={safetyActionDialog.notes}
                        onChange={(e) =>
                           setSafetyActionDialog((prev) => ({ ...prev, notes: e.target.value }))
                        }
                     />
                     <div className="mod-dialog-actions">
                        <button
                           type="button"
                           className="mod-dialog-btn secondary"
                           disabled={Boolean(safetyActingThreadId)}
                           onClick={() =>
                              setSafetyActionDialog({
                                 open: false,
                                 threadId: null,
                                 action: null,
                                 notes: "",
                              })
                           }>
                           Cancel
                        </button>
                        <button
                           type="button"
                           className={`mod-dialog-btn ${safetyActionMeta.tone}`}
                           disabled={Boolean(safetyActingThreadId)}
                           onClick={submitSafetyAction}>
                           {safetyActingThreadId ? "Applying..." : safetyActionMeta.cta}
                        </button>
                     </div>
                  </div>
               </div>
            )}
         </main>
      </div>
   );
}

export default ModerationPage;
