import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import "./UserHub.css";
import Icons from "../components/Icons.jsx";
import NavigationBar from "../components/NavigationBar.jsx";
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_META } from "../utils/constants";
import { buildApiUrl } from "../utils/api";

const AnalysisModal = ({ claimId, onClose }) => {
   const { authFetch } = useAuth();
   const [claimData, setClaimData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);

   const apiUrl = (path) => `${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api"}/${path}`;

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
         <div className="hub-modal-overlay" onClick={onClose}>
            <div className="hub-modal-content" onClick={(e) => e.stopPropagation()}>
               <div className="hub-modal-loading">
                  <Icons name="loader" size={32} className="spin" color="#4f46e5" />
                  <p>Loading Analysis Report...</p>
               </div>
            </div>
         </div>
      );
   }

   if (error || !claimData) {
      return (
         <div className="hub-modal-overlay" onClick={onClose}>
            <div className="hub-modal-content error" onClick={(e) => e.stopPropagation()}>
               <Icons name="alert-triangle" size={32} color="#d97706" />
               <h2>Error</h2>
               <p>{error || "Analysis not found."}</p>
               <button className="hub-modal-close-btn" onClick={onClose}>
                  Close
               </button>
            </div>
         </div>
      );
   }

   const verdict = (getEffectiveVerdict(claimData) || "UNVERIFIED").toLowerCase();
   const vm = VERDICT_META[verdict] || VERDICT_META.unverified;

   return (
      <div className="hub-modal-overlay" onClick={onClose}>
         <div className="hub-modal-content community-brief-modal" onClick={(e) => e.stopPropagation()}>
            <div className="br-modal-header">
               <div className="br-verdict-row">
                  <span
                     className="hub-verdict-badge"
                     style={{
                        color: vm.color,
                        background: vm.bg,
                        borderColor: vm.border,
                     }}
                  >
                     <Icons name={vm.icon || "help-circle"} size={14} color={vm.color} strokeWidth={2.5} />
                     {vm.label}
                  </span>
                  <div className="br-confidence">
                     <Icons name="activity" size={14} color="#64748b" />
                     <span>{claimData.consensus_score ?? "—"}% Confidence</span>
                  </div>
               </div>
               <button className="br-close-btn" onClick={onClose}>
                  <Icons name="x" size={20} color="#64748b" />
               </button>
            </div>

            <div className="br-modal-body">
               <div className="br-section">
                  <h4 className="br-section-title">Claim</h4>
                  <p className="br-primary-text">{claimData.context_text || "No text extracted"}</p>
               </div>

               <div className="br-section">
                  <h4 className="br-section-title">Summary</h4>
                  <p className="br-secondary-text">{claimData.ai_summary || "No summary available."}</p>
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
                              } catch (error) {
                                 console.warn("Invalid source URL:", url, error);
                              }
                           }

                           return (
                              <a key={idx} href={url} target="_blank" rel="noreferrer" className="br-source-pill">
                                 <Icons name="external-link" size={12} color="#64748b" />
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
                  className="br-full-analysis-btn"
               >
                  View Full Analysis
                  <Icons name="arrow-right" size={16} />
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
      FAKE: {
         bg: "#fee2e2",
         text: "#7f1d1d",
         border: "#e02424",
         label: "Fake",
         Icon: "x-circle",
      },
      MISLEADING: {
         bg: "#fef3c7",
         text: "#78350f",
         border: "#d97706",
         label: "Misleading",
         Icon: "alert-triangle",
      },
      SATIRE: {
         bg: "#ede9fe",
         text: "#4c1d95",
         border: "#7c3aed",
         label: "Satire",
         Icon: "wand",
      },
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
      <span className="hub-verdict-badge" style={{ background: s.bg, color: s.text, borderColor: s.border }}>
         <Icons name={s.Icon} size={12} strokeWidth={2.5} />
         {s.label}
      </span>
   );
};

const TrustGauge = ({ score }) => {
   const color = score >= 80 ? "#10b981" : score >= 50 ? "#f59e0b" : "#ef4444";
   const dashArray = `${(score / 100) * 163.4} 163.4`;

   return (
      <div className="hub-gauge-wrapper">
         <svg width={80} height={80} viewBox="0 0 64 64">
            <circle cx={32} cy={32} r={26} fill="none" stroke="#e2e8f0" strokeWidth={6} />
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
            <text x={32} y={38} textAnchor="middle" fontSize={16} fontWeight={800} fill={color}>
               {Math.round(score)}
            </text>
         </svg>
         <span className="hub-gauge-label">TRUST SCORE</span>
      </div>
   );
};

const formatTrustEffect = (value, type = "contribution") => {
   const numericValue = Number(value) || 0;

   if (type === "penalty") {
      const penalty = Math.abs(numericValue);

      if (penalty === 0) {
         return "0";
      }

      return `-${penalty}`;
   }

   if (numericValue > 0) {
      return `+${numericValue}`;
   }

   return `${numericValue}`;
};

const TrustBreakdownItem = ({ icon, label, description, value, type }) => {
   const numericValue = Number(value) || 0;
   const isPenalty = type === "penalty";

   let tone = "neutral";

   if (isPenalty && numericValue !== 0) {
      tone = "negative";
   } else if (!isPenalty && numericValue > 0) {
      tone = "positive";
   } else if (!isPenalty && numericValue < 0) {
      tone = "negative";
   }

   return (
      <div className="hub-trust-factor">
         <div className="hub-trust-factor-main">
            <div className="hub-trust-factor-icon">
               <Icons name={icon} size={16} />
            </div>

            <div>
               <div className="hub-trust-factor-label">{label}</div>

               <div className="hub-trust-factor-description">{description}</div>
            </div>
         </div>

         <span className={`hub-trust-factor-value hub-trust-factor-value--${tone}`}>
            {formatTrustEffect(value, type)}
         </span>
      </div>
   );
};

const ImpactCard = ({ icon, value, label, description, tone }) => {
   return (
      <article className={`hub-impact-card hub-impact-card--${tone}`}>
         <div className="hub-impact-icon">
            <Icons name={icon} size={19} />
         </div>

         <div className="hub-impact-content">
            <div className="hub-impact-value">{value ?? 0}</div>

            <div className="hub-impact-label">{label}</div>

            <p className="hub-impact-description">{description}</p>
         </div>
      </article>
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
                     style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "8px",
                     }}
                  >
                     <div
                        className="skeleton-box"
                        style={{
                           width: "150px",
                           height: "32px",
                           borderRadius: "8px",
                        }}
                     ></div>
                     <div className="skeleton-box" style={{ width: "300px", height: "16px" }}></div>
                  </div>
               </header>

               <div className="hub-rep-row box-panel" style={{ display: "flex", gap: "24px", alignItems: "center" }}>
                  <div
                     className="skeleton-box"
                     style={{
                        width: "80px",
                        height: "80px",
                        borderRadius: "50%",
                     }}
                  ></div>
                  <div
                     className="hub-rep-info"
                     style={{
                        flex: 1,
                        display: "flex",
                        flexDirection: "column",
                        gap: "12px",
                     }}
                  >
                     <div className="skeleton-box" style={{ width: "200px", height: "24px" }}></div>
                     <div className="skeleton-box" style={{ width: "150px", height: "14px" }}></div>
                     <div
                        className="skeleton-box"
                        style={{
                           width: "100%",
                           height: "12px",
                           borderRadius: "6px",
                        }}
                     ></div>
                  </div>
               </div>

               <div className="hub-impact-grid">
                  {[1, 2, 3].map((i) => (
                     <div
                        key={i}
                        className="hub-stat-card box-panel"
                        style={{
                           display: "flex",
                           alignItems: "center",
                           gap: "16px",
                        }}
                     >
                        <div
                           className="skeleton-box"
                           style={{
                              width: "40px",
                              height: "40px",
                              borderRadius: "12px",
                           }}
                        ></div>
                        <div
                           style={{
                              display: "flex",
                              flexDirection: "column",
                              gap: "8px",
                           }}
                        >
                           <div className="skeleton-box" style={{ width: "60px", height: "24px" }}></div>
                           <div className="skeleton-box" style={{ width: "100px", height: "14px" }}></div>
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
                     }}
                  >
                     <div className="skeleton-box" style={{ width: "200px", height: "24px" }}></div>
                     <div
                        className="skeleton-box"
                        style={{
                           width: "150px",
                           height: "36px",
                           borderRadius: "20px",
                        }}
                     ></div>
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
                           }}
                        >
                           <div style={{ display: "flex", gap: "16px", flex: 1 }}>
                              <div
                                 className="skeleton-box"
                                 style={{
                                    width: "40px",
                                    height: "40px",
                                    borderRadius: "8px",
                                 }}
                              ></div>
                              <div
                                 style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "8px",
                                    flex: 1,
                                 }}
                              >
                                 <div className="skeleton-box" style={{ width: "80%", height: "16px" }}></div>
                                 <div className="skeleton-box" style={{ width: "120px", height: "14px" }}></div>
                              </div>
                           </div>
                           <div
                              style={{
                                 display: "flex",
                                 flexDirection: "column",
                                 gap: "12px",
                                 alignItems: "flex-end",
                              }}
                           >
                              <div
                                 className="skeleton-box"
                                 style={{
                                    width: "80px",
                                    height: "24px",
                                    borderRadius: "12px",
                                 }}
                              ></div>
                              <div style={{ display: "flex", gap: "8px" }}>
                                 <div
                                    className="skeleton-box"
                                    style={{
                                       width: "100px",
                                       height: "30px",
                                       borderRadius: "6px",
                                    }}
                                 ></div>
                                 <div
                                    className="skeleton-box"
                                    style={{
                                       width: "100px",
                                       height: "30px",
                                       borderRadius: "6px",
                                    }}
                                 ></div>
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
   const navigate = useNavigate();
   const [hubData, setHubData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const [searchQuery, setSearchQuery] = useState("");
   const [selectedClaimId, setSelectedClaimId] = useState(null);

   useEffect(() => {
      const loadDashboard = async () => {
         try {
            setLoading(true);
            const data = await authFetch(buildApiUrl("users/me/dashboard/"), {
               method: "GET",
            });
            setHubData(data);
         } catch (err) {
            console.error("Failed to load user hub data:", err);
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

   const { reputation, impact, user_info: userInfo } = hubData;

   const username = userInfo?.username || "User";
   const avatarUrl = userInfo?.avatar_url;
   const avatarInitial = username.charAt(0).toUpperCase();

   // Handle Publish Stub
   const handlePublish = (e) => {
      e.preventDefault();
      alert("Publish to Community feature is coming soon!");
   };

   const getSourceLabel = (url) => {
      if (!url) return "Source";

      try {
         return new URL(url).hostname.replace(/^www\./, "");
      } catch {
         return "Source";
      }
   };

   return (
      <div className="hub-page-layout">
         <NavigationBar />
         <div className="hub-wrapper">
            <main className="hub-container">
               <header className="hub-overview">
                  <div className="hub-overview-identity">
                     <div className="hub-avatar">
                        {avatarUrl ? (
                           <img src={avatarUrl} alt={`${username}'s profile`} />
                        ) : (
                           <span>{avatarInitial}</span>
                        )}
                     </div>

                     <div className="hub-overview-copy">
                        <span className="hub-eyebrow">YOUR DASHBOARD</span>

                        <h1 className="hub-title">Welcome back, @{username}</h1>

                        <p className="hub-subtitle">
                           Track your investigations, reputation, and contribution to TruthLens.
                        </p>

                        <div className="hub-status-row">
                           <span className="hub-status-badge">{reputation?.status || "Provisional"}</span>

                           {reputation?.confidence?.label && (
                              <span className="hub-confidence-label">{reputation.confidence.label} confidence</span>
                           )}
                        </div>
                     </div>
                  </div>

                  <div className="hub-overview-actions">
                     <button
                        type="button"
                        className="hub-action hub-action-primary"
                        onClick={() => navigate("/verify")}
                     >
                        <Icons name="scan-line" size={17} />
                        Verify something
                     </button>

                     <button
                        type="button"
                        className="hub-action hub-action-secondary"
                        onClick={() => navigate("/community")}
                     >
                        <Icons name="users" size={17} />
                        Explore Community
                     </button>

                     <button
                        type="button"
                        className="hub-action hub-action-tertiary"
                        onClick={() => navigate("/profile")}
                     >
                        <Icons name="user" size={17} />
                        View profile
                     </button>
                  </div>
               </header>

               {/* Trust & Reputation */}
               <section className="hub-reputation-card box-panel">
                  <div className="hub-reputation-main">
                     <div className="hub-reputation-heading">
                        <div>
                           <span className="hub-section-eyebrow">TRUST & REPUTATION</span>

                           <h2 className="hub-section-heading">Your reputation</h2>
                        </div>

                        <div className="hub-confidence-chip">
                           <Icons name="activity" size={14} />
                           <span>{reputation?.confidence?.label || "Provisional"} confidence</span>
                        </div>
                     </div>

                     <div className="hub-reputation-summary">
                        <div className="hub-reputation-score">
                           <TrustGauge score={reputation?.trust_score ?? 50} />
                        </div>

                        <div className="hub-reputation-rank">
                           <span className="hub-reputation-rank-label">Current rank</span>

                           <h3>{reputation?.current_rank || "Provisional"}</h3>

                           {reputation?.current_rank === "Provisional" ? (
                              <p className="hub-reputation-description">
                                 We&apos;re still building enough history to establish your reputation.
                              </p>
                           ) : (
                              <p className="hub-reputation-description">
                                 Your Trust Score reflects the quality and reception of your verified contributions.
                              </p>
                           )}
                        </div>
                     </div>

                     <div className="hub-rank-progress">
                        <div className="hub-rank-progress-header">
                           <div>
                              <span className="hub-rank-progress-label">
                                 {reputation?.next_rank ? `Progress to ${reputation.next_rank}` : "Reputation progress"}
                              </span>

                              <span className="hub-rank-progress-detail">
                                 {reputation?.next_rank ? (
                                    <>
                                       {reputation.actions_to_next_rank > 0 && (
                                          <>
                                             {reputation.actions_to_next_rank} resolved{" "}
                                             {reputation.actions_to_next_rank === 1 ? "action" : "actions"} needed
                                          </>
                                       )}

                                       {reputation.actions_to_next_rank > 0 &&
                                          reputation.score_to_next_rank > 0 &&
                                          " · "}

                                       {reputation.score_to_next_rank > 0 && (
                                          <>
                                             {reputation.score_to_next_rank} Trust Score{" "}
                                             {reputation.score_to_next_rank === 1 ? "point" : "points"} needed
                                          </>
                                       )}

                                       {reputation.actions_to_next_rank === 0 &&
                                          reputation.score_to_next_rank === 0 &&
                                          "Requirements met"}
                                    </>
                                 ) : (
                                    "Highest reputation rank reached"
                                 )}
                              </span>
                           </div>

                           <span className="hub-rank-progress-percent">
                              {Math.round(Math.max(0, Math.min(reputation?.progress_percent ?? 0, 100)))}%
                           </span>
                        </div>

                        <div className="hub-progress-bar">
                           <div
                              className="hub-progress-fill"
                              style={{
                                 width: `${Math.max(0, Math.min(reputation?.progress_percent ?? 0, 100))}%`,
                              }}
                           />
                        </div>

                        <div className="hub-rank-progress-meta">
                           <span>{reputation?.resolved_actions ?? 0} resolved actions</span>

                           <span>Baseline Trust Score: {reputation?.breakdown?.base_score ?? 50}</span>
                        </div>
                     </div>
                  </div>

                  <aside className="hub-trust-breakdown">
                     <div className="hub-trust-breakdown-header">
                        <div>
                           <span className="hub-section-eyebrow">SCORE BREAKDOWN</span>

                           <h3>What affects your score</h3>
                        </div>

                        <div className="hub-score-total">
                           <span>Current</span>
                           <strong>{Math.round(reputation?.trust_score ?? 50)}</strong>
                        </div>
                     </div>

                     <div className="hub-trust-factor-list">
                        <TrustBreakdownItem
                           icon="check-circle"
                           label="Contribution Quality"
                           description="Quality of resolved evidence and reports"
                           value={reputation?.breakdown?.contribution_points}
                        />

                        <TrustBreakdownItem
                           icon="users"
                           label="Community Reception"
                           description="Weighted reception from other contributors"
                           value={reputation?.breakdown?.community_points}
                        />

                        <TrustBreakdownItem
                           icon="clock"
                           label="Account History"
                           description="Sustained successful participation"
                           value={reputation?.breakdown?.history_points}
                        />

                        <TrustBreakdownItem
                           icon="shield"
                           label="Moderation Penalties"
                           description="Penalties from confirmed moderation actions"
                           value={reputation?.breakdown?.moderation_penalty}
                           type="penalty"
                        />
                     </div>

                     <div className="hub-trust-note">
                        <Icons name="info" size={14} />

                        <p>Routine scans and passive activity do not directly increase your Trust Score.</p>
                     </div>
                  </aside>
               </section>

               {/* Impact Overview */}
               <section className="hub-impact-section">
                  <div className="hub-section-header">
                     <div>
                        <span className="hub-section-eyebrow">YOUR IMPACT</span>

                        <h2 className="hub-section-heading">Activity overview</h2>

                        <p className="hub-section-description">
                           A snapshot of how you use TruthLens and contribute to community verification.
                        </p>
                     </div>
                  </div>

                  <div className="hub-impact-grid">
                     <ImpactCard
                        icon="scan-line"
                        value={impact?.total_scans ?? 0}
                        label="Fact checks"
                        description="Claims you have investigated with TruthLens."
                        tone="indigo"
                     />

                     <ImpactCard
                        icon="message-square"
                        value={impact?.community_contributions ?? 0}
                        label="Community activity"
                        description="Evidence submissions and votes you have contributed."
                        tone="blue"
                     />

                     <ImpactCard
                        icon="activity"
                        value={impact?.impact_ripple ?? 0}
                        label="Community impact"
                        description="Votes received on evidence you submitted."
                        tone="green"
                     />
                  </div>
               </section>

               {/* Fact-Check Activity */}
               <section className="hub-library box-panel">
                  <div className="library-header">
                     <div className="library-heading">
                        <span className="hub-section-eyebrow">YOUR ACTIVITY</span>

                        <div className="library-title-row">
                           <h2 className="section-title">Recent fact checks</h2>

                           <span className="library-count">{hubData?.library?.saved_receipts?.length ?? 0}</span>
                        </div>

                        <p className="library-description">
                           Review claims you have previously checked and reopen their analysis.
                        </p>
                     </div>
                     <div className="library-search">
                        <Icons name="search" size={16} />

                        <input
                           type="search"
                           placeholder="Search fact checks..."
                           aria-label="Search fact checks"
                           value={searchQuery}
                           onChange={(e) => setSearchQuery(e.target.value)}
                        />
                     </div>
                  </div>

                  <div className="library-list">
                     {filteredLibrary.length > 0 ? (
                        filteredLibrary.map((claim) => (
                           <div key={claim.id} className="library-item">
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
                                    <div className="li-type-row">
                                       <span className="li-type">{claim.claim_type || "CLAIM"}</span>

                                       <span className="li-date">
                                          {new Date(claim.last_updated).toLocaleDateString()}
                                       </span>
                                    </div>
                                    <p className="li-excerpt">
                                       {claim.context_text
                                          ? `"${claim.context_text}"`
                                          : claim.ai_summary || "No summary available."}
                                    </p>
                                    <div className="li-meta">
                                       {claim.canonical_source_url && (
                                          <span className="li-source-meta">
                                             <span className="li-source-label">Top Source</span>

                                             <span aria-hidden="true">·</span>

                                             <a
                                                href={claim.canonical_source_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="li-source-link"
                                             >
                                                {getSourceLabel(claim.canonical_source_url)}
                                                <Icons name="external-link" size={11} />
                                             </a>
                                          </span>
                                       )}
                                    </div>
                                 </div>
                              </div>
                              <div className="li-actions">
                                 <div className="li-verdict-top-right">
                                    <VerdictBadge verdict={claim.final_verdict || claim.ai_verdict} />
                                 </div>
                                 <div className="hub-btns-row">
                                    <button onClick={() => setSelectedClaimId(claim.id)} className="hub-btn-report">
                                       <Icons name="file-text" size={14} className="hub-btn-icon" /> View Analysis
                                       Report
                                    </button>

                                    <button className="hub-btn-publish" onClick={handlePublish}>
                                       <Icons name="arrow-up-right" size={14} className="hub-btn-icon" /> Escalate
                                    </button>
                                 </div>
                              </div>
                           </div>
                        ))
                     ) : (
                        <div className="library-empty">
                           <div className="library-empty-icon">
                              <Icons name="inbox" size={24} />
                           </div>

                           <h3>{searchQuery ? "No matching fact checks" : "No fact checks yet"}</h3>

                           <p>
                              {searchQuery
                                 ? "Try a different search term."
                                 : "Claims you investigate will appear here."}
                           </p>
                        </div>
                     )}
                  </div>
               </section>
            </main>
         </div>

         {selectedClaimId && <AnalysisModal claimId={selectedClaimId} onClose={() => setSelectedClaimId(null)} />}
      </div>
   );
}
