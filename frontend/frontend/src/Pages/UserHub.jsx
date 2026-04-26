import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "../context/AuthContext";
import "./UserHub.css";
import Icons from "../components/Icons.jsx";
import NavigationBar from "../components/NavigationBar.jsx";

const VerdictBadge = ({ verdict }) => {
   const map = {
      FACT: {
         bg: "#d1fae5",
         text: "#065f46",
         border: "#0e9f6e",
         label: "Fact",
         Icon: "check-circle",
      },
      FAKE: { bg: "#fee2e2", text: "#7f1d1d", border: "#e02424", label: "Fake", Icon: "x-circle" },
      MISLEADING: {
         bg: "#fef3c7",
         text: "#78350f",
         border: "#d97706",
         label: "Misleading",
         Icon: "alert-triangle",
      },
      SATIRE: { bg: "#ede9fe", text: "#4c1d95", border: "#7c3aed", label: "Satire", Icon: "wand" },
      UNVERIFIED: {
         bg: "#f3f4f6",
         text: "#374151",
         border: "#6b7280",
         label: "Unverified",
         Icon: "help-circle",
      },
   };

   const normalized = verdict ? verdict.toUpperCase() : "UNVERIFIED";
   const s = map[normalized] || map.UNVERIFIED;

   return (
      <span
         className="hub-verdict-badge"
         style={{ background: s.bg, color: s.text, borderColor: s.border }}>
         <Icons
            name={s.Icon}
            size={12}
            strokeWidth={2.5}
         />
         {s.label}
      </span>
   );
};

const TrustGauge = ({ score }) => {
   const color = score >= 80 ? "#10b981" : score >= 50 ? "#f59e0b" : "#ef4444";
   const dashArray = `${(score / 100) * 163.4} 163.4`;

   return (
      <div className="hub-gauge-wrapper">
         <svg
            width={80}
            height={80}
            viewBox="0 0 64 64">
            <circle
               cx={32}
               cy={32}
               r={26}
               fill="none"
               stroke="#e2e8f0"
               strokeWidth={6}
            />
            <circle
               cx={32}
               cy={32}
               r={26}
               fill="none"
               stroke={color}
               strokeWidth={6}
               strokeDasharray={dashArray}
               strokeLinecap="round"
               transform="rotate(-90 32 32)"
            />
            <text
               x={32}
               y={38}
               textAnchor="middle"
               fontSize={16}
               fontWeight={800}
               fill={color}>
               {Math.round(score)}
            </text>
         </svg>
         <span className="hub-gauge-label">TRUST SCORE</span>
      </div>
   );
};

export default function UserHub() {
   const { authFetch } = useAuth();
   const [hubData, setHubData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const [searchQuery, setSearchQuery] = useState("");

   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
   const apiUrl = (path) => `${API_BASE_URL.replace(/\/$/, "")}/${path}`;

   useEffect(() => {
      const loadDashboard = async () => {
         try {
            setLoading(true);
            const data = await authFetch(apiUrl("users/me/dashboard/"), { method: "GET" });
            setHubData(data);
         } catch (err) {
            setError("Failed to load your personal hub data.");
         } finally {
            setLoading(false);
         }
      };
      loadDashboard();
   }, [authFetch]);

   const filteredLibrary = useMemo(() => {
      if (!hubData?.library?.saved_receipts) return [];
      let receipts = hubData.library.saved_receipts;
      if (searchQuery) {
         const lower = searchQuery.toLowerCase();
         receipts = receipts.filter(
            (r) =>
               (r.ai_summary && r.ai_summary.toLowerCase().includes(lower)) ||
               (r.final_verdict && r.final_verdict.toLowerCase().includes(lower)) ||
               (r.ai_verdict && r.ai_verdict.toLowerCase().includes(lower)),
         );
      }
      return receipts;
   }, [hubData?.library?.saved_receipts, searchQuery]);

   if (loading)
      return (
         <div className="hub-wrapper loading">
            <p>Loading personal dashboard...</p>
         </div>
      );
   if (error)
      return (
         <div className="hub-wrapper error">
            <p>{error}</p>
         </div>
      );

   const { user_info, reputation, impact } = hubData;

   // Handle Publish Stub
   const handlePublish = (e) => {
      e.preventDefault();
      alert("Publish to Community feature is coming soon!");
   };

   return (
      <div className="hub-page-layout">
         <NavigationBar />
         <div className="hub-wrapper">
            <main className="hub-container">
               <header className="hub-header">
                  <div className="hub-header-left">
                     <h1 className="hub-title">My Hub</h1>
                     <p className="hub-subtitle">Manage your progression and fact-check library.</p>
                  </div>
               </header>

               {/* Reputation & Progression Row */}
               <div className="hub-rep-row box-panel">
                  <div className="hub-rep-gauge">
                     <TrustGauge score={reputation?.trust_score || 0} />
                  </div>
                  <div className="hub-rep-info">
                     <h2 className="hub-rank-title">{reputation.current_rank}</h2>
                     <p className="hub-rank-sub">
                        Next Milestone: <strong>{reputation.points_to_next_rank}</strong> pt needed
                     </p>
                     <div className="hub-progress-bar">
                        <div
                           className="hub-progress-fill"
                           style={{
                              width: `${Math.min(((reputation.trust_score % 50) / 50) * 100, 100)}%`,
                           }}></div>
                     </div>
                  </div>
               </div>

               {/* Impact Metrics Row */}
               <div className="hub-impact-grid">
                  <div className="hub-stat-card box-panel">
                     <Icons
                        name="scan-line"
                        size={24}
                        color="#6366f1"
                     />
                     <div className="stat-meta">
                        <div className="stat-val">{impact.total_scans || 0}</div>
                        <div className="stat-lbl">Total Scans</div>
                     </div>
                  </div>
                  <div className="hub-stat-card box-panel">
                     <Icons
                        name="message-square"
                        size={24}
                        color="#3b82f6"
                     />
                     <div className="stat-meta">
                        <div className="stat-val">{impact.community_contributions || 0}</div>
                        <div className="stat-lbl">Contributions & Votes</div>
                     </div>
                  </div>
                  <div className="hub-stat-card box-panel">
                     <Icons
                        name="activity"
                        size={24}
                        color="#10b981"
                     />
                     <div className="stat-meta">
                        <div className="stat-val">{impact.impact_ripple || 0}</div>
                        <div className="stat-lbl">Impact Ripple</div>
                     </div>
                  </div>
               </div>

               {/* Private Fact-Check Library */}
               <div className="hub-library box-panel">
                  <div className="library-header">
                     <h3 className="section-title">Private Fact-Check Library</h3>
                     <div className="library-search">
                        <Icons
                           name="search"
                           size={16}
                           color="#64748b"
                        />
                        <input
                           type="text"
                           placeholder="Search receipts..."
                           value={searchQuery}
                           onChange={(e) => setSearchQuery(e.target.value)}
                        />
                     </div>
                  </div>

                  <div className="library-list">
                     {filteredLibrary.length > 0 ? (
                        filteredLibrary.map((claim, idx) => (
                           <div
                              key={idx}
                              className="library-item">
                              <div className="li-main">
                                 <div className="li-icon">
                                    <Icons
                                       name={claim.claim_type === "IMAGE" ? "image" : "globe"}
                                       size={20}
                                       color="#64748b"
                                    />
                                 </div>
                                 <div className="li-content">
                                    <p className="li-excerpt">
                                       {claim.ai_summary || "No summary available."}
                                    </p>
                                    <div className="li-meta">
                                       <span>
                                          {new Date(claim.last_updated).toLocaleDateString()}
                                       </span>
                                       {claim.source_link && (
                                          <a
                                             href={claim.source_link}
                                             target="_blank"
                                             rel="noreferrer">
                                             Source Link
                                          </a>
                                       )}
                                    </div>
                                 </div>
                              </div>
                              <div className="li-actions">
                                 <VerdictBadge verdict={claim.final_verdict || claim.ai_verdict} />
                                 
                                 <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", justifyContent: "flex-end" }}>
                                    <a
                                       href={`/analysis/${claim.id}`}
                                       target="_blank"
                                       rel="noopener noreferrer"
                                       className="hub-btn-report"
                                    >
                                       <Icons name="file-text" size={14} /> View Full Report
                                    </a>
                                    
                                    <button
                                       className="hub-btn-publish"
                                       onClick={handlePublish}>
                                       <Icons
                                          name="arrow-up-right"
                                          size={14}
                                       />{" "}
                                       Escalate
                                    </button>
                                 </div>
                              </div>
                           </div>
                        ))
                     ) : (
                        <div className="library-empty">
                           <Icons
                              name="inbox"
                              size={32}
                              color="#cbd5e1"
                           />
                           <p>
                              No saved receipts found. Scans you save privately will appear here.
                           </p>
                        </div>
                     )}
                  </div>
               </div>
            </main>
         </div>
      </div>
   );
}
