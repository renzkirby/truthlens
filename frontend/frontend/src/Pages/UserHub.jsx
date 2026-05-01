import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "../context/AuthContext";
import "./UserHub.css";
import Icons from "../components/Icons.jsx";
import NavigationBar from "../components/NavigationBar.jsx";
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_META } from "../utils/constants";

const AnalysisModal = ({ claimId, onClose }) => {
   const { authFetch } = useAuth();
   const [claimData, setClaimData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);

   const apiUrl = (path) =>
      `${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api"}/${path}`;

   useEffect(() => {
      const fetchAnalysis = async () => {
         try {
            const data = await authFetch(apiUrl(`claims/${claimId}/analysis/`), {
               method: "GET",
            });
            setClaimData(data);
         } catch (err) {
            console.error("Failed to fetch analysis:", err);
            setError("Could not load the analysis report.");
         } finally {
            setLoading(false);
         }
      };
      fetchAnalysis();
   }, [claimId, authFetch]);

   if (loading) {
      return (
         <div
            className="hub-modal-overlay"
            onClick={onClose}>
            <div
               className="hub-modal-content"
               onClick={(e) => e.stopPropagation()}>
               <div className="hub-modal-loading">
                  <Icons
                     name="loader"
                     size={32}
                     className="spin"
                     color="#4f46e5"
                  />
                  <p>Loading Analysis Report...</p>
               </div>
            </div>
         </div>
      );
   }

   if (error || !claimData) {
      return (
         <div
            className="hub-modal-overlay"
            onClick={onClose}>
            <div
               className="hub-modal-content error"
               onClick={(e) => e.stopPropagation()}>
               <Icons
                  name="alert-triangle"
                  size={32}
                  color="#d97706"
               />
               <h2>Error</h2>
               <p>{error || "Analysis not found."}</p>
               <button
                  className="hub-modal-close-btn"
                  onClick={onClose}>
                  Close
               </button>
            </div>
         </div>
      );
   }

   const verdict = (getEffectiveVerdict(claimData) || "UNVERIFIED").toLowerCase();
   const vm = VERDICT_META[verdict] || VERDICT_META.unverified;

   return (
      <div
         className="hub-modal-overlay"
         onClick={onClose}>
         <div
            className="hub-modal-content community-brief-modal"
            onClick={(e) => e.stopPropagation()}>
            <div className="br-modal-header">
               <div className="br-verdict-row">
                  <span
                     className="hub-verdict-badge"
                     style={{ color: vm.color, background: vm.bg, borderColor: vm.border }}>
                     <Icons
                        name={vm.icon || "help-circle"}
                        size={14}
                        color={vm.color}
                        strokeWidth={2.5}
                     />
                     {vm.label}
                  </span>
                  <div className="br-confidence">
                     <Icons
                        name="activity"
                        size={14}
                        color="#64748b"
                     />
                     <span>{claimData.consensus_score ?? "—"}% Confidence</span>
                  </div>
               </div>
               <button
                  className="br-close-btn"
                  onClick={onClose}>
                  <Icons
                     name="x"
                     size={20}
                     color="#64748b"
                  />
               </button>
            </div>

            <div className="br-modal-body">
               <div className="br-section">
                  <h4 className="br-section-title">Claim</h4>
                  <p className="br-primary-text">{claimData.context_text || "No text extracted"}</p>
               </div>

               <div className="br-section">
                  <h4 className="br-section-title">Summary</h4>
                  <p className="br-secondary-text">
                     {claimData.ai_summary || "No summary available."}
                  </p>
               </div>

               {(claimData.score_context || claimData.verified_via) && (
                  <div className="br-section">
                     <h4 className="br-section-title">Context</h4>
                     <p className="br-secondary-text">
                        {claimData.score_context || `Verified via: ${claimData.verified_via}`}
                     </p>
                  </div>
               )}

               <div className="br-section">
                  <h4 className="br-section-title">Sources</h4>
                  {claimData.ai_sources && claimData.ai_sources.length > 0 ? (
                     <div className="br-sources-pills">
                        {claimData.ai_sources.map((source, idx) => {
                           const isLegacyStr = typeof source === "string";
                           const url = isLegacyStr ? source : source.url;
                           let domain = "External Source";
                           if (url) {
                              try {
                                 domain = new URL(url).hostname.replace("www.", "");
                              } catch (e) {}
                           }

                           return (
                              <a
                                 key={idx}
                                 href={url}
                                 target="_blank"
                                 rel="noreferrer"
                                 className="br-source-pill">
                                 <Icons
                                    name="external-link"
                                    size={12}
                                    color="#64748b"
                                 />
                                 {domain}
                              </a>
                           );
                        })}
                     </div>
                  ) : (
                     <span className="br-empty-text">No external sources logged.</span>
                  )}
               </div>
            </div>

            <div className="br-modal-footer">
               <a
                  href={`/analysis/${claimId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="br-full-analysis-btn">
                  View Full Analysis
                  <Icons
                     name="arrow-right"
                     size={16}
                  />
               </a>
            </div>
         </div>
      </div>
   );
};

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

const UserHubSkeleton = () => {
   return (
      <div className="hub-page-layout">
         <NavigationBar />
         <div className="hub-wrapper">
            <main className="hub-container">
               <header className="hub-header">
                  <div
                     className="hub-header-left"
                     style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                     <div
                        className="skeleton-box"
                        style={{ width: "150px", height: "32px", borderRadius: "8px" }}></div>
                     <div
                        className="skeleton-box"
                        style={{ width: "300px", height: "16px" }}></div>
                  </div>
               </header>

               <div
                  className="hub-rep-row box-panel"
                  style={{ display: "flex", gap: "24px", alignItems: "center" }}>
                  <div
                     className="skeleton-box"
                     style={{ width: "80px", height: "80px", borderRadius: "50%" }}></div>
                  <div
                     className="hub-rep-info"
                     style={{ flex: 1, display: "flex", flexDirection: "column", gap: "12px" }}>
                     <div
                        className="skeleton-box"
                        style={{ width: "200px", height: "24px" }}></div>
                     <div
                        className="skeleton-box"
                        style={{ width: "150px", height: "14px" }}></div>
                     <div
                        className="skeleton-box"
                        style={{ width: "100%", height: "12px", borderRadius: "6px" }}></div>
                  </div>
               </div>

               <div className="hub-impact-grid">
                  {[1, 2, 3].map((i) => (
                     <div
                        key={i}
                        className="hub-stat-card box-panel"
                        style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                        <div
                           className="skeleton-box"
                           style={{ width: "40px", height: "40px", borderRadius: "12px" }}></div>
                        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                           <div
                              className="skeleton-box"
                              style={{ width: "60px", height: "24px" }}></div>
                           <div
                              className="skeleton-box"
                              style={{ width: "100px", height: "14px" }}></div>
                        </div>
                     </div>
                  ))}
               </div>

               <div className="hub-library box-panel">
                  <div
                     className="library-header"
                     style={{
                        display: "flex",
                        justifyContent: "space-between",
                        marginBottom: "20px",
                     }}>
                     <div
                        className="skeleton-box"
                        style={{ width: "200px", height: "24px" }}></div>
                     <div
                        className="skeleton-box"
                        style={{ width: "150px", height: "36px", borderRadius: "20px" }}></div>
                  </div>
                  <div className="library-list">
                     {[1, 2, 3].map((i) => (
                        <div
                           key={i}
                           className="library-item"
                           style={{
                              display: "flex",
                              justifyContent: "space-between",
                              padding: "16px",
                              borderBottom: "1px solid var(--border-subtle)",
                           }}>
                           <div style={{ display: "flex", gap: "16px", flex: 1 }}>
                              <div
                                 className="skeleton-box"
                                 style={{
                                    width: "40px",
                                    height: "40px",
                                    borderRadius: "8px",
                                 }}></div>
                              <div
                                 style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "8px",
                                    flex: 1,
                                 }}>
                                 <div
                                    className="skeleton-box"
                                    style={{ width: "80%", height: "16px" }}></div>
                                 <div
                                    className="skeleton-box"
                                    style={{ width: "120px", height: "14px" }}></div>
                              </div>
                           </div>
                           <div
                              style={{
                                 display: "flex",
                                 flexDirection: "column",
                                 gap: "12px",
                                 alignItems: "flex-end",
                              }}>
                              <div
                                 className="skeleton-box"
                                 style={{
                                    width: "80px",
                                    height: "24px",
                                    borderRadius: "12px",
                                 }}></div>
                              <div style={{ display: "flex", gap: "8px" }}>
                                 <div
                                    className="skeleton-box"
                                    style={{
                                       width: "100px",
                                       height: "30px",
                                       borderRadius: "6px",
                                    }}></div>
                                 <div
                                    className="skeleton-box"
                                    style={{
                                       width: "100px",
                                       height: "30px",
                                       borderRadius: "6px",
                                    }}></div>
                              </div>
                           </div>
                        </div>
                     ))}
                  </div>
               </div>
            </main>
         </div>
      </div>
   );
};

export default function UserHub() {
   const { authFetch } = useAuth();
   const [hubData, setHubData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const [searchQuery, setSearchQuery] = useState("");
   const [selectedClaimId, setSelectedClaimId] = useState(null);

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

   if (loading) return <UserHubSkeleton />;
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
                                       className="li-icon-svg"
                                    />
                                 </div>
                                 <div className="li-content">
                                    <p className="li-excerpt">
                                       {claim.context_text
                                          ? `"${claim.context_text}"`
                                          : claim.ai_summary || "No summary available."}
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
                                 <div className="li-verdict-top-right">
                                    <VerdictBadge
                                       verdict={claim.final_verdict || claim.ai_verdict}
                                    />
                                 </div>
                                 <div className="hub-btns-row">
                                    <button
                                       onClick={() => setSelectedClaimId(claim.id)}
                                       className="hub-btn-report">
                                       <Icons
                                          name="file-text"
                                          size={14}
                                          className="hub-btn-icon"
                                       />{" "}
                                       View Analysis Report
                                    </button>

                                    <button
                                       className="hub-btn-publish"
                                       onClick={handlePublish}>
                                       <Icons
                                          name="arrow-up-right"
                                          size={14}
                                          className="hub-btn-icon"
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

         {selectedClaimId && (
            <AnalysisModal
               claimId={selectedClaimId}
               onClose={() => setSelectedClaimId(null)}
            />
         )}
      </div>
   );
}
