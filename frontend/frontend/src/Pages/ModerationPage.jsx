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

   const [safetyStatusFilter, setSafetyStatusFilter] = useState("ALL");
   const [safetySearch, setSafetySearch] = useState("");
   const [verdictReviewedFilter, setVerdictReviewedFilter] = useState("all");
   const [verdictSearch, setVerdictSearch] = useState("");

   const [decisionDrafts, setDecisionDrafts] = useState({});
   const [resolvingThreadId, setResolvingThreadId] = useState(null);

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

   useEffect(() => {
      loadSafetyQueue();
      loadVerdictQueue();
      loadClaims();
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

   const recentClaims = useMemo(() => {
      return [...claims]
         .sort((a, b) => new Date(b.last_updated) - new Date(a.last_updated))
         .slice(0, 8);
   }, [claims]);

   const openThreads = verdictThreads.filter(
      (item) => item.status === "OPEN" || !item.status,
   ).length;
   const closedThreads = verdictThreads.filter((item) => item.status === "CLOSED").length;
   const flaggedThreads = safetyThreads.length;
   const pendingVerdicts = verdictThreads.filter((item) => !item.moderator_verdict).length;

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

               <ModerationSidebar recentClaims={claimsLoading || claimsError ? [] : recentClaims} />
            </div>
         </main>
      </div>
   );
}

export default ModerationPage;
