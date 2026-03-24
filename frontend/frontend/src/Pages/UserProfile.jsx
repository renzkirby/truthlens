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

import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar.jsx";

// ── Utilities & Hooks ──
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_CONFIG } from "../utils/constants";
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
   if (score >= 60) return { label: "Trusted", color: "var(--primary-blue)" };
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
   const { user, authFetch } = useAuth();
   const [activeTab, setActiveTab] = useState("scans");

   // ── Data Fetching ──
   // Use custom hook to eliminate boilerplate fetch logic
   const { claims, loading } = useFetchClaims(authFetch, "my-claims");

   // ── Compute Profile Stats ──
   const totalScans = claims.length;
   const fakesStopped = claims.filter((c) => getEffectiveVerdict(c) === "FAKE").length;
   const verifiedClaims = claims.filter((c) => getEffectiveVerdict(c) === "FACT").length;
   const accuracyRate =
      totalScans > 0 ? Math.round(((fakesStopped + verifiedClaims) / totalScans) * 100) : 0;

   const trustLevel = getTrustLevel(user?.trust_score || 0);

   return (
      <div className="profile-layout">
         <NavigationBar />

         <main className="profile-container">
            {/* ── User Identity Header ── */}
            {/* Shows avatar, username, email, trust level, join date */}
            <div className="profile-header">
               <div className="profile-avatar">{user?.username?.[0]?.toUpperCase() || "?"}</div>
               <div className="profile-identity">
                  <h1 className="profile-username">{user?.username || "—"}</h1>
                  <p className="profile-email">{user?.email || "—"}</p>
                  <div className="profile-meta">
                     <span
                        className="trust-level-badge"
                        style={{ backgroundColor: trustLevel.color }}>
                        {trustLevel.label}
                     </span>
                     <span className="join-date">Joined {formatDate(user?.date_joined)}</span>
                  </div>
               </div>
            </div>

            {/* ── Reputation Dashboard ── */}
            {/* Displays: trust score, accuracy rate, fake news stopped, total scans */}
            <div className="box-panel">
               <h2 className="section-title">Reputation Dashboard</h2>
               <div className="stats-grid">
                  <div className="stat-card">
                     <p className="stat-label">Trust Score</p>
                     <p className="stat-value">{user?.trust_score?.toFixed(1) || "0.0"}</p>
                     <div className="trust-bar-track">
                        <div
                           className="trust-bar-fill"
                           style={{
                              width: `${Math.min(user?.trust_score || 0, 100)}%`,
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
            </div>

            {/* ── Activity History & Claims ── */}
            {/* Tabbed view: scans history with verdict status, time, and summary */}
            <div className="box-panel">
               <div className="tabs-row">
                  <button
                     className={`tab-btn ${activeTab === "scans" ? "active" : ""}`}
                     onClick={() => setActiveTab("scans")}>
                     My Personal Scans
                  </button>
                  <button
                     className={`tab-btn ${activeTab === "contributions" ? "active" : ""}`}
                     onClick={() => setActiveTab("contributions")}>
                     Community Contributions
                  </button>
               </div>

               {activeTab === "scans" && (
                  <div className="tab-content">
                     {loading ? (
                        <p className="empty-msg">Loading your scans...</p>
                     ) : claims.length === 0 ? (
                        <p className="empty-msg">No scans yet. Start verifying claims!</p>
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

               {activeTab === "contributions" && (
                  <div className="tab-content">
                     <p className="empty-msg">Community contribution history coming soon.</p>
                  </div>
               )}
            </div>

            {/* Account Settings */}
            <div className="box-panel">
               <h2 className="section-title">Account Settings</h2>
               <div className="settings-grid">
                  <button className="settings-btn">Change Password</button>
                  <button className="settings-btn">Change Email</button>
                  <button className="settings-btn danger">Delete Account</button>
               </div>
               <div className="privacy-row">
                  <span className="privacy-label">Make Community Contributions Public</span>
                  <label className="toggle-switch">
                     <input
                        type="checkbox"
                        defaultChecked
                     />
                     <span className="toggle-slider" />
                  </label>
               </div>
            </div>
         </main>
      </div>
   );
}

export default UserProfile;
