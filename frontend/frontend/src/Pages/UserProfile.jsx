/**
 * User Profile Page
 * ══════════════════════════════════════════════════════════════════
 * Displays user profile information, reputation metrics, and claim history.
 *
 * Features:
 *   - User identity and trust level
 *   - Reputation dashboard (trust score, accuracy rate)
 *   - Claim history (scans, contributions, drafts)
 *   - Activity timeline
 *
 * State Management:
 *   - Custom hook (useFetchClaims) handles claim fetching
 *   - Verdict utilities for consistent verdict display
 *   - Centralized constants
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar.jsx";

// ── Utilities & Hooks ──
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_CONFIG, API_BASE_URL } from "../utils/constants";
import { useFetchClaims } from "../hooks";

// ── Styles ──
import "./UserProfile.css";

/**
 * Get trust level label and color based on score
 * @param {number} score - User's trust score (0-100)
 * @returns {object} { label, color }
 */
function getTrustLevel(score) {
   if (score >= 80) return { label: "Expert", color: "#22c55e" };
   if (score >= 60) return { label: "Trusted", color: "#3b82f6" };
   if (score >= 40) return { label: "Contributor", color: "#f97316" };
   return { label: "Newcomer", color: "var(--text-muted)" };
}

/**
 * Format date string to readable format
 * @param {string} dateStr - ISO date string
 * @returns {string} Formatted date (e.g., "January 15, 2024")
 */
function formatDate(dateStr) {
   if (!dateStr) return "—";
   return new Date(dateStr).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
   });
}

/**
 * Convert date to relative time format
 * @param {string} dateStr - ISO date string
 * @returns {string} Relative time (e.g., "2d ago", "Today")
 */
function timeAgo(dateStr) {
   if (!dateStr) return "—";
   const diff = Date.now() - new Date(dateStr).getTime();
   const days = Math.floor(diff / (1000 * 60 * 60 * 24));
   if (days === 0) return "Today";
   if (days === 1) return "Yesterday";
   if (days < 7) return `${days}d ago`;
   if (days < 30) return `${Math.floor(days / 7)}w ago`;
   return `${Math.floor(days / 30)}mo ago`;
}

/**
 * UserProfile Component
 * Shows user identity, reputation, and contribution history
 */
function UserProfile() {
   const { username } = useParams(); // Get username from URL if it exists
   const { user: authUser, authFetch, refreshUser } = useAuth();

   const [activeTab, setActiveTab] = useState("scans");
   const [publicUser, setPublicUser] = useState(null);
   const [isLoadingProfile, setIsLoadingProfile] = useState(false);

   // Determine if we are viewing our own profile or someone else's
   const isOwnProfile = !username || username === authUser?.username;
   const displayUser = isOwnProfile ? authUser : publicUser;

   // Dynamic Claims URL depending on whose profile we are viewing
   const claimsEndpoint = isOwnProfile ? "auth/my-claims/" : `users/${username}/claims/`;

   const { claims, loading: claimsLoading } = useFetchClaims(authFetch, claimsEndpoint);

   // Fetch public profile if we are viewing someone else
   useEffect(() => {
      if (isOwnProfile) {
         refreshUser?.();
      } else {
         setIsLoadingProfile(true);
         authFetch(`${API_BASE_URL}/users/${username}/`, { method: "GET" })
            .then((data) => {
               setPublicUser(data);
            })
            .catch((err) => console.error("Failed to load user", err))
            .finally(() => setIsLoadingProfile(false));
      }
   }, [username, isOwnProfile]);

   if (isLoadingProfile) {
      return (
         <div className="profile-layout">
            <NavigationBar />
            <main className="profile-container">
               <p style={{ textAlign: "center", marginTop: "50px" }}>Loading profile...</p>
            </main>
         </div>
      );
   }

   if (!displayUser && !isOwnProfile) {
      return (
         <div className="profile-layout">
            <NavigationBar />
            <main className="profile-container">
               <h2 style={{ textAlign: "center", marginTop: "50px" }}>User not found.</h2>
            </main>
         </div>
      );
   }

   // ── Compute Profile Stats ──
   const totalScans = claims.length;
   const fakesStopped = claims.filter((c) => getEffectiveVerdict(c) === "FAKE").length;
   const verifiedClaims = claims.filter((c) => getEffectiveVerdict(c) === "FACT").length;
   const accuracyRate =
      totalScans > 0 ? Math.round(((fakesStopped + verifiedClaims) / totalScans) * 100) : 0;

   const trustBreakdown = displayUser?.trust_breakdown || {};
   const displayTrustScore = Number(trustBreakdown.trust_score ?? displayUser?.trust_score ?? 0);
   const trustLevel = getTrustLevel(displayTrustScore);

   const breakdownRows = [
      {
         label: "Base Score",
         value: trustBreakdown.base_score ?? 50,
         share: trustBreakdown.base_share_pct ?? 0,
         max: 50,
         color: "#4f46e5",
      },
      {
         label: "Contribution Accuracy",
         value: trustBreakdown.contribution_points ?? 0,
         share: trustBreakdown.contribution_share_pct ?? 0,
         max: 30,
         color: "#0e9f6e",
      },
      {
         label: "Vote Balance",
         value: trustBreakdown.vote_points ?? 0,
         share: trustBreakdown.vote_share_pct ?? 0,
         max: 15,
         color: "#d97706",
      },
      {
         label: "Tenure Bonus",
         value: trustBreakdown.tenure_points ?? 0,
         share: trustBreakdown.tenure_share_pct ?? 0,
         max: 5,
         color: "#2563eb",
      },
      {
         label: "Conduct Penalties",
         value: trustBreakdown.penalties ?? 0,
         share: trustBreakdown.penalties_share_pct ?? 0,
         max: 30,
         color: "#dc2626",
      },
   ];

   return (
      <div className="profile-layout">
         <NavigationBar />

         <main className="profile-container">
            {/* ── User Identity Header ── */}
            <div className="profile-header">
               <div className="profile-avatar">
                  {displayUser?.username?.[0]?.toUpperCase() || "?"}
               </div>
               <div className="profile-identity">
                  <h1 className="profile-username">{displayUser?.username || "—"}</h1>
                  {/* Hide email if viewing a public profile to protect privacy */}
                  {isOwnProfile && <p className="profile-email">{displayUser?.email || "—"}</p>}
                  <div className="profile-meta">
                     <span
                        className="trust-level-badge"
                        style={{ backgroundColor: trustLevel.color }}>
                        {trustLevel.label}
                     </span>
                     <span className="join-date">
                        Joined {formatDate(displayUser?.date_joined)}
                     </span>
                  </div>
               </div>
            </div>

            {/* ── Reputation Dashboard ── */}
            <div className="box-panel">
               <h2 className="section-title">Reputation Dashboard</h2>
               <div className="stats-grid">
                  <div className="stat-card">
                     <p className="stat-label">Trust Score</p>
                     <p className="stat-value">{displayTrustScore.toFixed(1)}</p>
                     <div className="trust-bar-track">
                        <div
                           className="trust-bar-fill"
                           style={{
                              width: `${Math.min(displayTrustScore, 100)}%`,
                              backgroundColor: trustLevel.color,
                           }}
                        />
                     </div>
                     <p className="stat-sublabel">{trustLevel.label} Level</p>
                  </div>

                  <div className="stat-card">
                     <p className="stat-label">Accuracy Rate</p>
                     <p className="stat-value">{accuracyRate}%</p>
                     <p className="stat-sublabel">of verdicts confirmed</p>
                  </div>

                  <div className="stat-card">
                     <p className="stat-label">Fake News Stopped</p>
                     <p className="stat-value">{fakesStopped}</p>
                     <p className="stat-sublabel">FAKE verdicts found</p>
                  </div>

                  <div className="stat-card">
                     <p className="stat-label">Total Scans</p>
                     <p className="stat-value">{totalScans}</p>
                     <p className="stat-sublabel">claims analyzed</p>
                  </div>
               </div>

               <div className="trust-breakdown-card">
                  <div className="trust-breakdown-header">
                     <h3 className="trust-breakdown-title">Trust Score Breakdown</h3>
                     <span className="trust-breakdown-formula">T = B + C + V + t - P</span>
                  </div>
                  <div className="trust-breakdown-list">
                     {breakdownRows.map((row) => {
                        const width = Math.max(0, Math.min(100, Number(row.share || 0)));
                        return (
                           <div
                              className="trust-breakdown-row"
                              key={row.label}>
                              <div className="trust-breakdown-row-top">
                                 <span className="trust-breakdown-row-label">{row.label}</span>
                                 <span
                                    className="trust-breakdown-row-value"
                                    style={{ color: row.color }}>
                                    {width.toFixed(1)}%
                                 </span>
                              </div>
                              <div className="trust-breakdown-track">
                                 <div
                                    className="trust-breakdown-fill"
                                    style={{ width: `${width}%`, backgroundColor: row.color }}
                                 />
                              </div>
                              <p className="trust-breakdown-impact">
                                 Impact: {row.label === "Conduct Penalties" ? "-" : "+"}
                                 {Math.abs(Number(row.value || 0)).toFixed(1)} pts
                              </p>
                           </div>
                        );
                     })}
                  </div>
               </div>
            </div>

            {/* ── Activity History & Claims ── */}
            <div className="box-panel">
               <div className="tabs-row">
                  <button
                     className={`tab-btn ${activeTab === "scans" ? "active" : ""}`}
                     onClick={() => setActiveTab("scans")}>
                     {isOwnProfile ? "My Personal Scans" : `${displayUser?.username}'s Scans`}
                  </button>
               </div>

               {activeTab === "scans" && (
                  <div className="tab-content">
                     {claimsLoading ? (
                        <p className="empty-msg">Loading scans...</p>
                     ) : claims.length === 0 ? (
                        <p className="empty-msg">No scans yet.</p>
                     ) : (
                        <div className="claims-list">
                           {claims.map((claim) => {
                              const verdict =
                                 VERDICT_CONFIG[getEffectiveVerdict(claim)] ||
                                 VERDICT_CONFIG.PENDING;
                              return (
                                 <div
                                    className="claim-card"
                                    key={claim.id}>
                                    <div className="claim-top">
                                       <span
                                          className="claim-verdict-badge"
                                          style={{ backgroundColor: verdict.color }}>
                                          {verdict.label}
                                       </span>
                                       <span className="claim-type-pill">{claim.claim_type}</span>
                                       <span className="claim-time">
                                          {timeAgo(claim.last_updated)}
                                       </span>
                                    </div>
                                    <p className="claim-summary">
                                       {claim.ai_summary || "No summary available."}
                                    </p>
                                    {claim.source_link && (
                                       <a
                                          href={claim.source_link}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="claim-source-link">
                                          View Source →
                                       </a>
                                    )}
                                 </div>
                              );
                           })}
                        </div>
                     )}
                  </div>
               )}
            </div>

            {/* Account Settings - ONLY SHOW IF VIEWING OWN PROFILE */}
            {isOwnProfile && (
               <div className="box-panel">
                  <h2 className="section-title">Account Settings</h2>
                  <div className="settings-grid">
                     <button className="settings-btn">Change Password</button>
                     <button className="settings-btn">Change Email</button>
                     <button className="settings-btn danger">Delete Account</button>
                  </div>
               </div>
            )}
         </main>
      </div>
   );
}

export default UserProfile;
