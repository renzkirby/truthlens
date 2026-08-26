import React, { useState, useEffect } from "react";
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
   const [selectedClaimId, setSelectedClaimId] = useState(null);

   const [libraryView, setLibraryView] = useState("history");
   const [libraryData, setLibraryData] = useState({
      count: 0,
      page: 1,
      page_size: 10,
      total_pages: 1,
      has_next: false,
      has_previous: false,
      results: [],
   });

   const [libraryLoading, setLibraryLoading] = useState(true);
   const [libraryError, setLibraryError] = useState(null);

   const [searchInput, setSearchInput] = useState("");
   const [searchQuery, setSearchQuery] = useState("");

   const [verdictFilter, setVerdictFilter] = useState("");
   const [typeFilter, setTypeFilter] = useState("");
   const [sortOrder, setSortOrder] = useState("newest");
   const [libraryPage, setLibraryPage] = useState(1);

   const [libraryCounts, setLibraryCounts] = useState({
      history: null,
      saved: null,
   });

   const [savingClaimIds, setSavingClaimIds] = useState(new Set());

   const [saveError, setSaveError] = useState(null);

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

   useEffect(() => {
      const timeoutId = window.setTimeout(() => {
         setSearchQuery(searchInput.trim());
         setLibraryPage(1);
      }, 350);

      return () => window.clearTimeout(timeoutId);
   }, [searchInput]);

   useEffect(() => {
      let ignore = false;

      const loadLibrary = async () => {
         try {
            setLibraryLoading(true);
            setLibraryError(null);

            const params = new URLSearchParams({
               view: libraryView,
               page: String(libraryPage),
               page_size: "10",
               sort: sortOrder,
            });

            if (searchQuery) {
               params.set("search", searchQuery);
            }

            if (verdictFilter) {
               params.set("verdict", verdictFilter);
            }

            if (typeFilter) {
               params.set("type", typeFilter);
            }

            const data = await authFetch(buildApiUrl(`users/me/fact-checks/?${params.toString()}`), {
               method: "GET",
            });

            if (ignore) return;

            setLibraryData(data);

            if (data.counts) {
               setLibraryCounts({
                  history: data.counts.history,
                  saved: data.counts.saved,
               });
            }

            // Protect against a stale page after filtering.
            if (data.page !== libraryPage && data.page >= 1) {
               setLibraryPage(data.page);
            }
         } catch (err) {
            if (ignore) return;

            console.error("Failed to load fact-check library:", err);

            setLibraryError("Could not load your fact-check activity.");
         } finally {
            if (!ignore) {
               setLibraryLoading(false);
            }
         }
      };

      loadLibrary();

      return () => {
         ignore = true;
      };
   }, [authFetch, libraryView, libraryPage, searchQuery, verdictFilter, typeFilter, sortOrder]);

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

   const handleEscalate = (claimId) => {
      navigate(`/thread/create?claim_id=${encodeURIComponent(claimId)}`);
   };

   const getSourceLabel = (url) => {
      if (!url) return "Source";

      try {
         return new URL(url).hostname.replace(/^www\./, "");
      } catch {
         return "Source";
      }
   };

   const handleLibraryViewChange = (nextView) => {
      if (nextView === libraryView) return;

      setLibraryView(nextView);
      setLibraryPage(1);
   };

   const handleVerdictChange = (event) => {
      setVerdictFilter(event.target.value);
      setLibraryPage(1);
   };

   const handleTypeChange = (event) => {
      setTypeFilter(event.target.value);
      setLibraryPage(1);
   };

   const handleSortChange = (event) => {
      setSortOrder(event.target.value);
      setLibraryPage(1);
   };

   const clearLibraryFilters = () => {
      setSearchInput("");
      setSearchQuery("");
      setVerdictFilter("");
      setTypeFilter("");
      setSortOrder("newest");
      setLibraryPage(1);
   };

   const hasLibraryFilters =
      Boolean(searchQuery) || Boolean(verdictFilter) || Boolean(typeFilter) || sortOrder !== "newest";

   const handleToggleSave = async (claim) => {
      if (savingClaimIds.has(claim.id)) return;

      const previousIsSaved = Boolean(claim.is_saved);
      const optimisticIsSaved = !previousIsSaved;

      const previousLibraryData = libraryData;
      const previousLibraryCounts = libraryCounts;

      setSaveError(null);

      setSavingClaimIds((current) => {
         const next = new Set(current);
         next.add(claim.id);
         return next;
      });

      /*
       * Optimistic UI:
       * update immediately before the server responds.
       */
      if (libraryView === "saved" && previousIsSaved) {
         /*
          * In Saved view, unsaving should immediately
          * remove the card rather than reload the list.
          */
         setLibraryData((current) => {
            const nextResults = current.results.filter((item) => item.id !== claim.id);

            const nextCount = Math.max(0, current.count - 1);

            const nextTotalPages = Math.max(1, Math.ceil(nextCount / current.page_size));

            return {
               ...current,
               count: nextCount,
               total_pages: nextTotalPages,
               has_next: current.page < nextTotalPages,
               results: nextResults,
            };
         });
      } else {
         /*
          * History view:
          * simply flip Save <-> Saved in place.
          */
         setLibraryData((current) => ({
            ...current,
            results: current.results.map((item) =>
               item.id === claim.id
                  ? {
                       ...item,
                       is_saved: optimisticIsSaved,
                    }
                  : item,
            ),
         }));
      }

      setLibraryCounts((current) => ({
         ...current,
         saved: current.saved === null ? current.saved : Math.max(0, current.saved + (optimisticIsSaved ? 1 : -1)),
      }));

      try {
         const result = await authFetch(buildApiUrl(`claims/${claim.id}/toggle-save/`), {
            method: "POST",
         });

         /*
          * Server response is authoritative.
          * Reconcile count in case another tab/session
          * changed saved claims simultaneously.
          */
         if (typeof result.saved_count === "number") {
            setLibraryCounts((current) => ({
               ...current,
               saved: result.saved_count,
            }));
         }

         /*
          * In History, reconcile button state too.
          */
         if (libraryView !== "saved") {
            setLibraryData((current) => ({
               ...current,
               results: current.results.map((item) =>
                  item.id === claim.id
                     ? {
                          ...item,
                          is_saved: result.is_saved,
                       }
                     : item,
               ),
            }));
         }

         /*
          * Rare pagination edge case:
          * if we removed the final card on a Saved page,
          * move backward one page.
          *
          * Example:
          * page 3 contains only one item.
          * After removing it, page 3 no longer exists.
          */
         if (
            libraryView === "saved" &&
            previousIsSaved &&
            previousLibraryData.results.length === 1 &&
            previousLibraryData.page > 1
         ) {
            setLibraryPage(previousLibraryData.page - 1);
         }
      } catch (err) {
         console.error("Failed to update saved claim:", err);

         /*
          * Roll back everything exactly as it was
          * before the optimistic update.
          */
         setLibraryData(previousLibraryData);
         setLibraryCounts(previousLibraryCounts);

         setSaveError("Could not update this saved claim. Please try again.");
      } finally {
         setSavingClaimIds((current) => {
            const next = new Set(current);
            next.delete(claim.id);
            return next;
         });
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

               {/* Fact-Check Library */}
               <section className="hub-library box-panel">
                  <div className="library-header">
                     <div className="library-heading">
                        <span className="hub-section-eyebrow">YOUR LIBRARY</span>

                        <div className="library-title-row">
                           <h2 className="section-title">Fact-check library</h2>

                           <span className="library-count">{libraryData.count}</span>
                        </div>

                        <p className="library-description">
                           Browse your fact-check history and claims you&apos;ve saved for later.
                        </p>
                     </div>
                  </div>

                  <div className="library-tabs">
                     <button
                        type="button"
                        className={`library-tab ${libraryView === "history" ? "library-tab--active" : ""}`}
                        onClick={() => handleLibraryViewChange("history")}
                     >
                        <Icons name="clock" size={15} />
                        History
                        {libraryCounts.history !== null && (
                           <span className="library-tab-count">{libraryCounts.history}</span>
                        )}
                     </button>

                     <button
                        type="button"
                        className={`library-tab ${libraryView === "saved" ? "library-tab--active" : ""}`}
                        onClick={() => handleLibraryViewChange("saved")}
                     >
                        <Icons name="bookmark" size={15} />
                        Saved
                        {libraryCounts.saved !== null && (
                           <span className="library-tab-count">{libraryCounts.saved}</span>
                        )}
                     </button>
                  </div>

                  <div className="library-toolbar">
                     <div className="library-search">
                        <Icons name="search" size={16} />

                        <input
                           type="search"
                           placeholder={libraryView === "history" ? "Search history..." : "Search saved claims..."}
                           aria-label="Search fact checks"
                           value={searchInput}
                           onChange={(event) => setSearchInput(event.target.value)}
                        />
                     </div>

                     <div className="library-filters">
                        <label className="library-filter">
                           <span className="sr-only">Filter by verdict</span>

                           <select value={verdictFilter} onChange={handleVerdictChange}>
                              <option value="">All verdicts</option>
                              <option value="FACT">Fact</option>
                              <option value="FAKE">Fake</option>
                              <option value="MISLEADING">Misleading</option>
                              <option value="SATIRE">Satire</option>
                              <option value="UNVERIFIED">Unverified</option>
                              <option value="OUT_OF_SCOPE">Out of scope</option>
                           </select>
                        </label>

                        <label className="library-filter">
                           <span className="sr-only">Filter by claim type</span>

                           <select value={typeFilter} onChange={handleTypeChange}>
                              <option value="">All types</option>
                              <option value="TEXT">Text</option>
                              <option value="IMAGE">Image</option>
                              <option value="URL">URL</option>
                              <option value="VIDEO">Video</option>
                              <option value="FILE">File</option>
                           </select>
                        </label>

                        <label className="library-filter">
                           <span className="sr-only">Sort fact checks</span>

                           <select value={sortOrder} onChange={handleSortChange}>
                              <option value="newest">Newest first</option>
                              <option value="oldest">Oldest first</option>
                           </select>
                        </label>

                        {hasLibraryFilters && (
                           <button type="button" className="library-clear-filters" onClick={clearLibraryFilters}>
                              Clear
                           </button>
                        )}
                     </div>
                  </div>
                  {saveError && (
                     <div className="library-save-error" role="alert">
                        <Icons name="alert-circle" size={14} />

                        <span>{saveError}</span>

                        <button type="button" onClick={() => setSaveError(null)} aria-label="Dismiss save error">
                           <Icons name="x" size={13} />
                        </button>
                     </div>
                  )}

                  <div className="library-content">
                     {libraryLoading ? (
                        <div className="library-loading">
                           <Icons name="loader" size={22} className="spin" />
                           <span>Loading fact checks...</span>
                        </div>
                     ) : libraryError ? (
                        <div className="library-empty">
                           <div className="library-empty-icon">
                              <Icons name="alert-triangle" size={24} />
                           </div>

                           <h3>Unable to load fact checks</h3>
                           <p>{libraryError}</p>
                        </div>
                     ) : libraryData.results.length > 0 ? (
                        <div className="library-list">
                           {libraryData.results.map((claim) => (
                              <div key={claim.id} className="library-item">
                                 <div className="li-main">
                                    <div className="li-icon">
                                       <Icons
                                          name={
                                             claim.claim_type === "IMAGE"
                                                ? "image"
                                                : claim.claim_type === "TEXT"
                                                  ? "file-text"
                                                  : claim.claim_type === "FILE"
                                                    ? "file"
                                                    : "globe"
                                          }
                                          size={20}
                                          color="#64748b"
                                          className="li-icon-svg"
                                       />
                                    </div>

                                    <div className="li-content">
                                       <div className="li-type-row">
                                          <span className="li-type">{claim.claim_type || "CLAIM"}</span>

                                          <span className="li-date">
                                             {new Date(claim.activity_at || claim.last_updated).toLocaleDateString()}
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
                                       <VerdictBadge
                                          verdict={claim.effective_verdict || claim.final_verdict || claim.ai_verdict}
                                       />
                                    </div>

                                    <div className="hub-btns-row">
                                       <button
                                          type="button"
                                          className={`hub-btn-save ${claim.is_saved ? "hub-btn-save--saved" : ""}`}
                                          onClick={() => handleToggleSave(claim)}
                                          disabled={savingClaimIds.has(claim.id)}
                                          aria-busy={savingClaimIds.has(claim.id)}
                                          aria-label={claim.is_saved ? "Remove from saved claims" : "Save claim"}
                                       >
                                          {savingClaimIds.has(claim.id) ? (
                                             <Icons name="loader" size={14} className="hub-btn-icon spin" />
                                          ) : (
                                             <Icons name="bookmark" size={14} className="hub-btn-icon" />
                                          )}

                                          {claim.is_saved ? "Saved" : "Save"}
                                       </button>
                                       <button
                                          type="button"
                                          onClick={() => setSelectedClaimId(claim.id)}
                                          className="hub-btn-report"
                                       >
                                          <Icons name="file-text" size={14} className="hub-btn-icon" />
                                          View Analysis Report
                                       </button>

                                       <button
                                          type="button"
                                          className="hub-btn-publish"
                                          onClick={() => handleEscalate(claim.id)}
                                       >
                                          <Icons name="arrow-up-right" size={14} className="hub-btn-icon" />
                                          Escalate
                                       </button>
                                    </div>
                                 </div>
                              </div>
                           ))}
                        </div>
                     ) : (
                        <div className="library-empty">
                           <div className="library-empty-icon">
                              <Icons name={libraryView === "saved" ? "bookmark" : "inbox"} size={24} />
                           </div>

                           <h3>
                              {hasLibraryFilters
                                 ? "No matching fact checks"
                                 : libraryView === "saved"
                                   ? "No saved claims yet"
                                   : "No fact checks yet"}
                           </h3>

                           <p>
                              {hasLibraryFilters
                                 ? "Try adjusting your search or filters."
                                 : libraryView === "saved"
                                   ? "Claims you save will appear here for quick access later."
                                   : "Claims you investigate will appear here."}
                           </p>
                        </div>
                     )}
                  </div>

                  {!libraryLoading && !libraryError && libraryData.count > 0 && (
                     <div className="library-pagination">
                        <button
                           type="button"
                           className="library-page-button"
                           disabled={!libraryData.has_previous}
                           onClick={() => setLibraryPage((page) => Math.max(1, page - 1))}
                        >
                           <Icons name="chevron-left" size={15} />
                           Previous
                        </button>

                        <span className="library-page-status">
                           Page <strong>{libraryData.page}</strong> of <strong>{libraryData.total_pages}</strong>
                        </span>

                        <button
                           type="button"
                           className="library-page-button"
                           disabled={!libraryData.has_next}
                           onClick={() => setLibraryPage((page) => page + 1)}
                        >
                           Next
                           <Icons name="chevron-right" size={15} />
                        </button>
                     </div>
                  )}
               </section>
            </main>
         </div>

         {selectedClaimId && <AnalysisModal claimId={selectedClaimId} onClose={() => setSelectedClaimId(null)} />}
      </div>
   );
}
