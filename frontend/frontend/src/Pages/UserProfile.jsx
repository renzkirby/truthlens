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

import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar.jsx";

// ── Utilities & Hooks ──
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_CONFIG, API_BASE_URL } from "../utils/constants";
import Icons from "../components/Icons.jsx";

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

function isModeratorRole(role) {
   return role === "MOD" || role === "MODERATOR";
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

const TAB_PAGE_SIZE = 6;
const TAB_SKELETON_COUNT = 3;

function getTabDescription(activeTab, isOwnProfile) {
   if (activeTab === "threads") {
      return isOwnProfile
         ? "Threads you started for community verification."
         : "Threads initiated by this user.";
   }
   if (activeTab === "evidence") {
      return isOwnProfile
         ? "Evidence and comments you contributed across threads."
         : "Evidence and comments contributed by this user.";
   }
   return isOwnProfile
      ? "Official moderation verdicts you have issued."
      : "Official moderation verdicts issued by this moderator.";
}

function getEmptyTabMessage(activeTab, isOwnProfile) {
   if (activeTab === "threads") {
      return isOwnProfile
         ? "You have not opened any community threads yet."
         : "This user has not opened any community threads yet.";
   }
   if (activeTab === "evidence") {
      return isOwnProfile
         ? "You have not submitted evidence or comments yet."
         : "This user has not submitted evidence or comments yet.";
   }
   return isOwnProfile
      ? "You have not issued any moderator verdicts yet."
      : "No moderator verdicts have been published yet.";
}

/**
 * UserProfile Component
 * Shows user identity, reputation, and contribution history
 */
function UserProfile() {
   const { username } = useParams(); // Get username from URL if it exists
   const navigate = useNavigate();
   const { user: authUser, authFetch, refreshUser, logout } = useAuth();

   const [activeTab, setActiveTab] = useState("threads");
   const [publicUser, setPublicUser] = useState(null);
   const [isLoadingProfile, setIsLoadingProfile] = useState(false);
   const [activityLoading, setActivityLoading] = useState(false);
   const [activityError, setActivityError] = useState(null);
   const [threadActivity, setThreadActivity] = useState([]);
   const [evidenceActivity, setEvidenceActivity] = useState([]);
   const [verdictActivity, setVerdictActivity] = useState([]);
   const [loadedActivityTabs, setLoadedActivityTabs] = useState({
      threads: false,
      evidence: false,
      verdicts: false,
   });
   const [visibleCounts, setVisibleCounts] = useState({
      threads: TAB_PAGE_SIZE,
      evidence: TAB_PAGE_SIZE,
      verdicts: TAB_PAGE_SIZE,
   });

   // Determine if we are viewing our own profile or someone else's
   const isOwnProfile = !username || username === authUser?.username;
   const displayUser = isOwnProfile ? authUser : publicUser;
   const displayUsername = displayUser?.username;
   const isModeratorProfile = isModeratorRole(displayUser?.role);
   const organizationName = displayUser?.organization_name?.trim() || "Institution not listed";

   const activeTabItems = useMemo(() => {
      if (activeTab === "threads") return threadActivity;
      if (activeTab === "evidence") return evidenceActivity;
      return verdictActivity;
   }, [activeTab, evidenceActivity, threadActivity, verdictActivity]);

   const currentTabLoading = activityLoading;
   const currentTabError = activityError;
   const currentTabDescription = getTabDescription(activeTab, isOwnProfile);
   const currentTabEmptyMessage = getEmptyTabMessage(activeTab, isOwnProfile);

   const visibleTabItems = useMemo(() => {
      const visibleCount = visibleCounts[activeTab] ?? TAB_PAGE_SIZE;
      return activeTabItems.slice(0, visibleCount);
   }, [activeTab, activeTabItems, visibleCounts]);

   const currentVisibleCount = visibleCounts[activeTab] ?? TAB_PAGE_SIZE;
   const hasMoreTabItems = activeTabItems.length > currentVisibleCount;
   const canShowLessTabItems =
      currentVisibleCount > TAB_PAGE_SIZE && activeTabItems.length > TAB_PAGE_SIZE;
   const [moderatorStats, setModeratorStats] = useState(null);
   const [isLoadingModeratorStats, setIsLoadingModeratorStats] = useState(false);
   const [moderatorStatsError, setModeratorStatsError] = useState(false);

   // ── Follow System State ──
   const [isFollowing, setIsFollowing] = useState(false);
   const [followersCount, setFollowersCount] = useState(0);
   const [followingCount, setFollowingCount] = useState(0);

   // Sync state when the user data loads
   useEffect(() => {
      if (displayUser) {
         setIsFollowing(displayUser.is_following || false);
         setFollowersCount(displayUser.followers_count || 0);
         setFollowingCount(displayUser.following_count || 0);
      }
   }, [displayUser]);

   useEffect(() => {
      if (!displayUsername || !isModeratorProfile) {
         setModeratorStats(null);
         setIsLoadingModeratorStats(false);
         setModeratorStatsError(false);
         return;
      }

      let isCancelled = false;
      setIsLoadingModeratorStats(true);
      setModeratorStatsError(false);

      authFetch(`${API_BASE_URL}/users/${displayUsername}/moderation-stats/`, { method: "GET" })
         .then((data) => {
            if (isCancelled) return;
            setModeratorStats(data || null);
            setModeratorStatsError(false);
         })
         .catch(() => {
            if (isCancelled) return;
            setModeratorStats(null);
            setModeratorStatsError(true);
         })
         .finally(() => {
            if (!isCancelled) {
               setIsLoadingModeratorStats(false);
            }
         });

      return () => {
         isCancelled = true;
      };
   }, [authFetch, displayUsername, isModeratorProfile]);

   // Handle follow button click
   const handleFollowToggle = async () => {
      try {
         // Updated to use the dynamic API_BASE_URL!
         const response = await authFetch(`${API_BASE_URL}/users/${displayUser.username}/follow/`, {
            method: "POST",
         });
         // Instantly update the UI with the backend's response
         setIsFollowing(response.is_following);
         setFollowersCount(response.followers_count);
      } catch (err) {
         console.error("Failed to toggle follow status:", err);
      }
   };
   // ── Modal State ──
   const [modalType, setModalType] = useState(null); // 'followers' or 'following'
   const [modalData, setModalData] = useState([]);
   const [isModalLoading, setIsModalLoading] = useState(false);

   // ── Edit Profile State ──
   const [isEditModalOpen, setIsEditModalOpen] = useState(false);
   const [editBio, setEditBio] = useState("");
   const [editAvatarBase64, setEditAvatarBase64] = useState(null);
   const [isSavingProfile, setIsSavingProfile] = useState(false);

   const openFollowModal = async (type) => {
      setModalType(type);
      setIsModalLoading(true);
      try {
         const response = await authFetch(
            `${import.meta.env.VITE_API_BASE_URL}/users/${displayUser.username}/${type}/`,
            {
               method: "GET",
            },
         );

         const data = response?.data || response?.results || response || [];
         setModalData(Array.isArray(data) ? data : []);
      } catch (err) {
         console.error(`Failed to fetch ${type}:`, err);
         setModalData([]);
      } finally {
         setIsModalLoading(false);
      }
   };

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

   useEffect(() => {
      setActiveTab("threads");
      setActivityError(null);
      setActivityLoading(false);
      setThreadActivity([]);
      setEvidenceActivity([]);
      setVerdictActivity([]);
      setLoadedActivityTabs({
         threads: false,
         evidence: false,
         verdicts: false,
      });
      setVisibleCounts({
         threads: TAB_PAGE_SIZE,
         evidence: TAB_PAGE_SIZE,
         verdicts: TAB_PAGE_SIZE,
      });
   }, [displayUsername, isOwnProfile]);

   useEffect(() => {
      if (!displayUsername) {
         return;
      }

      if (activeTab === "verdicts" && !isModeratorProfile) {
         setActiveTab("threads");
         return;
      }

      if (loadedActivityTabs[activeTab]) {
         return;
      }

      const endpointMap = {
         threads: `${API_BASE_URL}/users/${displayUsername}/threads/`,
         evidence: `${API_BASE_URL}/users/${displayUsername}/evidence/`,
         verdicts: `${API_BASE_URL}/users/${displayUsername}/verdicts/`,
      };

      let isCancelled = false;
      setActivityLoading(true);
      setActivityError(null);

      authFetch(endpointMap[activeTab], { method: "GET" })
         .then((data) => {
            if (isCancelled) {
               return;
            }

            const normalized = Array.isArray(data)
               ? data
               : Array.isArray(data?.results)
                 ? data.results
                 : [];

            if (activeTab === "threads") {
               setThreadActivity(normalized);
            } else if (activeTab === "evidence") {
               setEvidenceActivity(normalized);
            } else {
               setVerdictActivity(normalized);
            }

            setLoadedActivityTabs((prev) => ({
               ...prev,
               [activeTab]: true,
            }));
         })
         .catch((err) => {
            if (isCancelled) {
               return;
            }
            setActivityError(err?.message || "Failed to load profile activity.");
         })
         .finally(() => {
            if (!isCancelled) {
               setActivityLoading(false);
            }
         });

      return () => {
         isCancelled = true;
      };
   }, [
      activeTab,
      authFetch,
      displayUsername,
      isModeratorProfile,
      loadedActivityTabs,
      isOwnProfile,
   ]);

   const handleLoadMore = () => {
      setVisibleCounts((prev) => ({
         ...prev,
         [activeTab]: (prev[activeTab] ?? TAB_PAGE_SIZE) + TAB_PAGE_SIZE,
      }));
   };

   const handleShowLess = () => {
      setVisibleCounts((prev) => ({
         ...prev,
         [activeTab]: TAB_PAGE_SIZE,
      }));
   };

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
   const moderatorStatsSnapshot = moderatorStats || {
      total_claims_resolved: 0,
      fact_verdicts_issued: 0,
      fake_verdicts_issued: 0,
      pending_moderator_review: 0,
   };

   const trustBreakdown = displayUser?.trust_breakdown || {};
   const displayTrustScore = Number(trustBreakdown.trust_score ?? displayUser?.trust_score ?? 0);
   const trustLevel = getTrustLevel(displayTrustScore);

   const transparencyStats = [
      {
         label: "Total Claims Resolved",
         value: Number(moderatorStatsSnapshot.total_claims_resolved ?? 0),
      },
      {
         label: "FACT Verdicts Issued",
         value: Number(moderatorStatsSnapshot.fact_verdicts_issued ?? 0),
      },
      {
         label: "FAKE Verdicts Issued",
         value: Number(moderatorStatsSnapshot.fake_verdicts_issued ?? 0),
      },
      {
         label: "Pending Moderator Review",
         value: Number(moderatorStatsSnapshot.pending_moderator_review ?? 0),
      },
   ];

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

   const openEditModal = () => {
      setEditBio(displayUser?.bio || "");
      setEditAvatarBase64(null); // Reset pending image
      setIsEditModalOpen(true);
   };

   // Convert chosen file to Base64
   const handleImageUpload = (e) => {
      const file = e.target.files[0];
      if (file) {
         const reader = new FileReader();
         reader.onloadend = () => {
            setEditAvatarBase64(reader.result);
         };
         reader.readAsDataURL(file);
      }
   };

   // Save changes to the backend
   const handleSaveProfile = async () => {
      setIsSavingProfile(true);
      try {
         const payload = { bio: editBio };
         if (editAvatarBase64) {
            payload.avatar_base64 = editAvatarBase64;
         }

         const response = await authFetch(`${API_BASE_URL}/auth/profile/update/`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
         });

         setIsEditModalOpen(false);
         refreshUser?.(); // Force context to update with new data
      } catch (err) {
         console.error("Failed to update profile:", err);
      } finally {
         setIsSavingProfile(false);
      }
   };

   return (
      <div className="profile-layout">
         <NavigationBar />

         <main className="profile-container">
            {/* ── User Identity Header (X-Style Layout) ── */}
            <div className="profile-header-container">
               {/* 1. Cover Banner */}
               <div className="profile-cover-banner">
                  {displayUser?.cover_photo_url && (
                     <img
                        src={displayUser.cover_photo_url}
                        alt="Cover"
                     />
                  )}
               </div>

               <div className="profile-header-body">
                  {/* 2. Overlapping Avatar */}
                  <div className="profile-avatar-wrapper">
                     <div className="profile-avatar">
                        {displayUser?.avatar_url ? (
                           <img
                              src={displayUser.avatar_url}
                              alt={`${displayUser.username}'s avatar`}
                           />
                        ) : (
                           displayUser?.username?.[0]?.toUpperCase() || "?"
                        )}
                     </div>
                  </div>

                  {/* 3. Action Buttons (Right Aligned) */}
                  <div className="profile-action-row">
                     {isOwnProfile ? (
                        <button
                           type="button"
                           className="action-btn action-btn-edit"
                           onClick={openEditModal}>
                           Edit Profile
                        </button>
                     ) : displayUser ? (
                        <button
                           type="button"
                           className={`action-btn action-btn-follow ${isFollowing ? "following" : ""}`}
                           onClick={handleFollowToggle}>
                           {isFollowing ? "Following" : "Follow"}
                        </button>
                     ) : null}
                  </div>

                  {/* 4. Identity & Bio */}
                  <div className="profile-identity">
                     <div className="profile-title-row">
                        <h1 className="profile-username">{displayUser?.username || "—"}</h1>
                        {isModeratorProfile ? (
                           <span className="official-moderator-badge">
                              <Icons
                                 name="shield-user"
                                 size={14}
                              />
                              Official Moderator
                           </span>
                        ) : (
                           <span
                              className="trust-level-badge"
                              style={{ backgroundColor: trustLevel.color }}>
                              {trustLevel.label}
                           </span>
                        )}
                     </div>

                     <p className="profile-handle">
                        @{displayUser?.username?.toLowerCase() || "—"}
                     </p>

                     {isModeratorProfile && (
                        <div className="profile-organization-row">
                           <p className="organization-name">{organizationName}</p>
                           <span className="institutional-trust-chip">
                              <Icons
                                 name="shield-user"
                                 size={12}
                              />
                              Institutional Trust
                           </span>
                        </div>
                     )}
                  </div>

                  {displayUser?.bio && <p className="user-bio">{displayUser.bio}</p>}

                  {/* 5. Meta Info (Join Date, Trust Badge) */}
                  <div className="profile-meta-row">
                     <div className="meta-item">
                        <Icons
                           name="calendar"
                           size={16}
                        />
                        Joined {formatDate(displayUser?.date_joined)}
                     </div>
                  </div>

                  {/* 6. Follower Stats */}
                  <div className="follow-stats">
                     <span onClick={() => openFollowModal("following")}>
                        <strong>{followingCount}</strong> Following
                     </span>
                     <span onClick={() => openFollowModal("followers")}>
                        <strong>{followersCount}</strong> Followers
                     </span>
                  </div>

               </div>
            </div>
            {/* ── End Header ── */}

            {/* ── Reputation Dashboard ── */}
            {!isModeratorProfile && (
               <div className="box-panel">
                  <h2 className="section-title">Reputation Dashboard</h2>
                  <div className="stats-grid">
                     <div
                        className="stat-card"
                        style={{ gridColumn: "1 / -1" }}>
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
            )}

            {isModeratorProfile && (
               <div className="box-panel">
                  <h2 className="section-title">Institutional Trust Profile</h2>

                  <div className="moderator-profile-summary">
                     <p className="moderator-summary-title">Official Moderator</p>
                     <p className="moderator-summary-desc">
                        Affiliated with {organizationName}. This profile uses institutional trust
                        verification instead of gamified scoring.
                     </p>
                  </div>

                  <div className="moderator-transparency-grid">
                     {transparencyStats.map((stat) => (
                        <div
                           key={stat.label}
                           className="moderator-transparency-card">
                           <p className="moderator-transparency-label">{stat.label}</p>
                           <p className="moderator-transparency-value">
                              {isLoadingModeratorStats ? (
                                 <span
                                    className="moderator-transparency-skeleton"
                                    aria-hidden="true"
                                 />
                              ) : moderatorStatsError ? (
                                 "--"
                              ) : (
                                 stat.value
                              )}
                           </p>
                        </div>
                     ))}
                  </div>

                  <p className="moderator-transparency-note">
                     {isLoadingModeratorStats
                        ? "Syncing moderator activity records..."
                        : moderatorStatsError
                          ? "Transparency stats are temporarily unavailable. Please try again shortly."
                          : "Transparency stats are shown for public accountability and may update as moderation records are finalized."}
                  </p>
               </div>
            )}

            {/* ── Activity History & Claims ── */}
            <div className="box-panel">
               <div className="tabs-row">
                  <button
                     className={`tab-btn ${activeTab === "threads" ? "active" : ""}`}
                     onClick={() => setActiveTab("threads")}>
                     {isOwnProfile ? "My Threads" : "Threads"}
                  </button>
                  <button
                     className={`tab-btn ${activeTab === "evidence" ? "active" : ""}`}
                     onClick={() => setActiveTab("evidence")}>
                     {isOwnProfile ? "My Evidence" : "Evidence"}
                  </button>
                  {isModeratorProfile && (
                     <button
                        className={`tab-btn ${activeTab === "verdicts" ? "active" : ""}`}
                        onClick={() => setActiveTab("verdicts")}>
                        {isOwnProfile ? "My Verdicts" : "Verdicts"}
                     </button>
                  )}
               </div>

               <div className="tab-summary-row">
                  <p className="tab-summary-copy">{currentTabDescription}</p>
                  {!currentTabLoading && !currentTabError && activeTabItems.length > 0 && (
                     <span className="tab-summary-count">
                        Showing {visibleTabItems.length} of {activeTabItems.length}
                     </span>
                  )}
               </div>

               <div className="tab-content">
                  {currentTabLoading ? (
                     <div
                        className="profile-skeleton-list"
                        aria-hidden="true">
                        {Array.from({ length: TAB_SKELETON_COUNT }).map((_, index) => (
                           <div
                              className="profile-skeleton-card"
                              key={`activity-skeleton-${index}`}>
                              <span className="profile-skeleton-line short" />
                              <span className="profile-skeleton-line" />
                              <span className="profile-skeleton-line long" />
                           </div>
                        ))}
                     </div>
                  ) : currentTabError ? (
                     <p className="empty-msg">{currentTabError}</p>
                  ) : activeTabItems.length === 0 ? (
                     <p className="empty-msg">{currentTabEmptyMessage}</p>
                  ) : (
                     <>
                        <div className="claims-list">
                           {activeTab === "threads" &&
                              visibleTabItems.map((thread) => (
                                 <div
                                    className="claim-card"
                                    key={thread.id}>
                                    <div className="claim-top">
                                       <span className="claim-type-pill">
                                          {thread.status || "OPEN"}
                                       </span>
                                       <span className="claim-time">
                                          {timeAgo(thread.created_at)}
                                       </span>
                                    </div>
                                    <p className="claim-summary">
                                       {thread.caption || "Thread started without a caption."}
                                    </p>
                                    <p className="claim-summary claim-meta-summary">
                                       Claim ID: {thread.claim_id} | {thread.evidence_count}{" "}
                                       evidence | {thread.comment_count} comments
                                    </p>
                                    <button
                                       type="button"
                                       className="claim-source-link claim-source-button"
                                       onClick={() => navigate(`/thread/detail/${thread.id}`)}>
                                       Open Thread →
                                    </button>
                                 </div>
                              ))}

                           {activeTab === "evidence" &&
                              visibleTabItems.map((item) => (
                                 <div
                                    className="claim-card"
                                    key={`${item.activity_type}-${item.id}`}>
                                    <div className="claim-top">
                                       <span className="claim-type-pill">{item.activity_type}</span>
                                       <span className="claim-time">
                                          {timeAgo(item.activity_at)}
                                       </span>
                                    </div>

                                    {item.activity_type === "COMMENT" ? (
                                       <>
                                          <p className="claim-summary">
                                             {item.comment_text || "Comment submitted."}
                                          </p>
                                          <p className="claim-summary claim-meta-summary">
                                             On thread:{" "}
                                             {item.thread?.caption || item.thread?.id || "Unknown"}
                                          </p>
                                       </>
                                    ) : (
                                       <>
                                          <p className="claim-summary">
                                             {item.evidence_caption || "Evidence submitted."}
                                          </p>
                                          <p className="claim-summary claim-meta-summary">
                                             Type: {item.evidence_type || "Unspecified"} | Status:{" "}
                                             {item.evidence_status || "UNVERIFIED"}
                                          </p>
                                          {item.evidence_url && (
                                             <a
                                                href={item.evidence_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="claim-source-link">
                                                View cited source →
                                             </a>
                                          )}
                                       </>
                                    )}
                                 </div>
                              ))}

                           {activeTab === "verdicts" &&
                              visibleTabItems.map((entry) => {
                                 const verdict =
                                    VERDICT_CONFIG[entry.moderator_verdict] ||
                                    VERDICT_CONFIG.UNVERIFIED;

                                 return (
                                    <div
                                       className="claim-card"
                                       key={entry.thread_id}>
                                       <div className="claim-top">
                                          <span
                                             className="claim-verdict-badge"
                                             style={{
                                                backgroundColor: verdict.bg,
                                                color: verdict.color,
                                                border: `1px solid ${verdict.border}`,
                                             }}>
                                             {entry.moderator_verdict || "UNVERIFIED"}
                                          </span>
                                          <span className="claim-time">
                                             {timeAgo(entry.moderated_at)}
                                          </span>
                                       </div>
                                       <p className="claim-summary">
                                          {entry.caption || "Moderator-reviewed thread."}
                                       </p>
                                       <p className="claim-summary claim-meta-summary">
                                          Claim ID: {entry.claim_id}
                                       </p>
                                       {entry.moderator_notes && (
                                          <p className="claim-summary claim-meta-summary">
                                             Notes: {entry.moderator_notes}
                                          </p>
                                       )}
                                    </div>
                                 );
                              })}
                        </div>

                        <div className="activity-pagination-row">
                           <span className="activity-pagination-meta">
                              Showing {visibleTabItems.length} of {activeTabItems.length}
                           </span>
                           <div className="activity-pagination-actions">
                              {canShowLessTabItems && (
                                 <button
                                    type="button"
                                    className="activity-show-less-btn"
                                    onClick={handleShowLess}>
                                    Show Less
                                 </button>
                              )}
                              {hasMoreTabItems && (
                                 <button
                                    type="button"
                                    className="activity-load-more-btn"
                                    onClick={handleLoadMore}>
                                    Load More
                                 </button>
                              )}
                           </div>
                        </div>
                     </>
                  )}
               </div>
            </div>

            {/* Account Settings removed, migrated to Settings */}

            {/* ── FOLLOW MODAL ── */}
            {modalType && (
               <div
                  className="modal-overlay"
                  onClick={() => setModalType(null)}>
                  <div
                     className="modal-content"
                     onClick={(e) => e.stopPropagation()}>
                     <div className="modal-header">
                        <h3 style={{ margin: 0, fontSize: "18px" }}>
                           {modalType === "followers" ? "Followers" : "Following"}
                        </h3>
                        <button
                           className="close-modal-btn"
                           onClick={() => setModalType(null)}>
                           <Icons
                              name="x"
                              size={20}
                           />
                        </button>
                     </div>

                     <div className="modal-user-list">
                        {isModalLoading ? (
                           <p
                              className="empty-msg"
                              style={{ padding: "20px" }}>
                              Loading...
                           </p>
                        ) : modalData.length === 0 ? (
                           <p
                              className="empty-msg"
                              style={{ padding: "20px" }}>
                              No {modalType} found.
                           </p>
                        ) : (
                           modalData.map((u) => (
                              <div
                                 key={u.id}
                                 className="modal-user-item"
                                 onClick={() => {
                                    setModalType(null); // Close modal
                                    navigate(`/user/${u.username}`); // <--- FAST REACT NAVIGATION!
                                 }}>
                                 {/* Added safe chaining to prevent crashes */}
                                 <div className="modal-user-avatar">
                                    {u?.username?.[0]?.toUpperCase() || "?"}
                                 </div>
                                 <div className="modal-user-info">
                                    <strong>{u?.username || "Unknown"}</strong>
                                    <span>
                                       {isModeratorRole(u?.role)
                                          ? "Official Moderator"
                                          : getTrustLevel(u?.trust_score || 0).label}
                                    </span>
                                 </div>
                              </div>
                           ))
                        )}
                     </div>
                  </div>
               </div>
            )}
            {/* ── EDIT PROFILE MODAL ── */}
            {isEditModalOpen && (
               <div
                  className="modal-overlay"
                  onClick={() => setIsEditModalOpen(false)}>
                  <div
                     className="modal-content"
                     onClick={(e) => e.stopPropagation()}
                     style={{ padding: "24px" }}>
                     <div
                        className="modal-header"
                        style={{ padding: "0 0 16px 0", marginBottom: "16px" }}>
                        <h3 style={{ margin: 0, fontSize: "18px" }}>Edit Profile</h3>
                        <button
                           className="close-modal-btn"
                           onClick={() => setIsEditModalOpen(false)}>
                           <Icons
                              name="x"
                              size={20}
                           />
                        </button>
                     </div>

                     <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                        {/* Avatar Upload */}
                        <div>
                           <label
                              style={{
                                 display: "block",
                                 marginBottom: "8px",
                                 fontWeight: "600",
                                 fontSize: "14px",
                              }}>
                              Profile Picture
                           </label>
                           <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                              <div
                                 className="profile-avatar"
                                 style={{ width: "60px", height: "60px", overflow: "hidden" }}>
                                 {editAvatarBase64 ? (
                                    <img
                                       src={editAvatarBase64}
                                       style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                    />
                                 ) : displayUser?.avatar_url ? (
                                    <img
                                       src={displayUser.avatar_url}
                                       style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                    />
                                 ) : (
                                    displayUser?.username?.[0]?.toUpperCase()
                                 )}
                              </div>
                              <input
                                 type="file"
                                 accept="image/*"
                                 onChange={handleImageUpload}
                                 style={{ fontSize: "14px" }}
                              />
                           </div>
                        </div>

                        {/* Bio Textarea */}
                        <div>
                           <label
                              style={{
                                 display: "block",
                                 marginBottom: "8px",
                                 fontWeight: "600",
                                 fontSize: "14px",
                              }}>
                              Bio
                           </label>
                           <textarea
                              value={editBio}
                              onChange={(e) => setEditBio(e.target.value)}
                              placeholder="Tell the community about yourself..."
                              style={{
                                 width: "100%",
                                 padding: "8px",
                                 borderRadius: "8px",
                                 border: "1px solid #d1d5db",
                                 minHeight: "80px",
                                 resize: "vertical",
                              }}
                           />
                        </div>

                        {/* Save Button */}
                        <button
                           onClick={handleSaveProfile}
                           disabled={isSavingProfile}
                           className="follow-btn following"
                           style={{ width: "100%", marginTop: "8px" }}>
                           {isSavingProfile ? "Saving..." : "Save Changes"}
                        </button>
                     </div>
                  </div>
               </div>
            )}

            {/* 7. Mobile-Only Profile Actions (Since top-nav is hidden on mobile) */}
            {isOwnProfile && (
               <div className="mobile-profile-nav">
                  <button 
                     className="mobile-nav-pill"
                     onClick={() => navigate(isModeratorRole(authUser?.role) ? "/moderation" : "/dashboard")}>
                     <Icons name={isModeratorRole(authUser?.role) ? "shield" : "dashboard"} size={16} /> Dashboard
                  </button>
                  <button 
                     className="mobile-nav-pill"
                     onClick={() => navigate("/settings")}>
                     <Icons name="settings" size={16} /> Settings
                  </button>
                  <button 
                     className="mobile-nav-pill danger"
                     onClick={() => {
                        logout();
                        navigate("/login");
                     }}>
                     <Icons name="logout" size={16} /> Log Out
                  </button>
               </div>
            )}
         </main>
      </div>
   );
}

export default UserProfile;
