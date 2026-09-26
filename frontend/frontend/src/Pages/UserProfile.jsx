import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import ImageLightbox from "../components/ImageLightbox.jsx";
import Icons from "../components/Icons.jsx";
import { useAuth } from "../hooks/useAuth";
import { useNotification } from "../hooks/useNotification";
import { resolveApiEndpoint } from "../utils/api";
import "./UserProfile.css";

const TAB_PAGE_SIZE = 6;
const TAB_SKELETON_COUNT = 3;
const ACTIVITY_TABS = ["threads", "contributions"];

function getTrustLevel(score) {
   if (score <= 25) return { label: "Untrusted", tone: "untrusted" };
   if (score < 40) return { label: "At risk", tone: "at-risk" };
   if (score < 60) return { label: "Newcomer", tone: "newcomer" };
   if (score < 75) return { label: "Contributor", tone: "contributor" };
   if (score < 90) return { label: "Trusted analyst", tone: "trusted" };
   return { label: "Expert analyst", tone: "expert" };
}

function isPlatformModeratorRole(role) {
   return role === "MOD" || role === "MODERATOR";
}

function formatDate(dateStr) {
   if (!dateStr) return "Date unavailable";
   const date = new Date(dateStr);
   if (Number.isNaN(date.getTime())) return "Date unavailable";
   return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
   });
}

function formatActivityDate(dateStr) {
   if (!dateStr) return "Date unavailable";
   const date = new Date(dateStr);
   if (Number.isNaN(date.getTime())) return "Date unavailable";
   return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
   });
}

function humanizeValue(value, fallback = "Unspecified") {
   if (!value) return fallback;
   return String(value)
      .toLowerCase()
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getClaimContext(claim) {
   if (claim?.context_text?.trim()) return claim.context_text.trim();
   return `${humanizeValue(claim?.claim_type, "Claim")} claim`;
}

function getTabDescription(activeTab, isOwnProfile) {
   if (activeTab === "threads") {
      return isOwnProfile
         ? "Threads you started for community verification."
         : "Threads this member started for community verification.";
   }
   return isOwnProfile
      ? "Evidence and comments you contributed across community threads."
      : "Evidence and comments this member contributed across community threads.";
}

function getEmptyTabMessage(activeTab, isOwnProfile) {
   if (activeTab === "threads") {
      return isOwnProfile
         ? "You have not started a community thread yet."
         : "This member has not started a community thread yet.";
   }
   return isOwnProfile
      ? "You have not submitted evidence or comments yet."
      : "This member has not submitted evidence or comments yet.";
}

function ProfileAvatar({ user, className = "", onImageError }) {
   const username = user?.username || "Community member";

   if (user?.avatar_url) {
      return (
         <span className={`user-profile__avatar ${className}`.trim()}>
            <img src={user.avatar_url} alt={`${username}'s avatar`} onError={onImageError} />
         </span>
      );
   }

   return (
      <span
         className={`user-profile__avatar user-profile__avatar--fallback ${className}`.trim()}
         role="img"
         aria-label={`${username}'s avatar placeholder`}
      >
         <span aria-hidden="true">{username.charAt(0).toUpperCase()}</span>
      </span>
   );
}

function ProfileDialog({
   children,
   className = "",
   describedBy,
   initialFocusRef,
   isBusy = false,
   labelledBy,
   onClose,
   returnFocusRef,
}) {
   const dialogRef = useRef(null);
   const onCloseRef = useRef(onClose);
   const isBusyRef = useRef(isBusy);

   useEffect(() => {
      onCloseRef.current = onClose;
      isBusyRef.current = isBusy;
   }, [isBusy, onClose]);

   useEffect(() => {
      const returnTarget = returnFocusRef?.current || document.activeElement;
      const previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";

      const focusDialog = window.requestAnimationFrame(() => {
         (initialFocusRef?.current || dialogRef.current)?.focus();
      });

      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !isBusyRef.current) {
            event.preventDefault();
            onCloseRef.current();
            return;
         }

         if (event.key !== "Tab") return;

         const focusable = Array.from(
            dialogRef.current?.querySelectorAll(
               'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
            ) || [],
         ).filter((element) => !element.hasAttribute("hidden"));

         if (focusable.length === 0) {
            event.preventDefault();
            dialogRef.current?.focus();
            return;
         }

         const first = focusable[0];
         const last = focusable[focusable.length - 1];
         if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
         } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
         }
      };

      document.addEventListener("keydown", handleKeyDown);

      return () => {
         window.cancelAnimationFrame(focusDialog);
         document.body.style.overflow = previousBodyOverflow;
         document.removeEventListener("keydown", handleKeyDown);
         window.requestAnimationFrame(() => returnTarget?.focus?.());
      };
   }, [initialFocusRef, returnFocusRef]);

   return (
      <div
         className="user-profile__dialog-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !isBusy) onClose();
         }}
      >
         <div
            ref={dialogRef}
            className={`user-profile__dialog ${className}`.trim()}
            role="dialog"
            aria-modal="true"
            aria-labelledby={labelledBy}
            aria-describedby={describedBy}
            tabIndex={-1}
         >
            {children}
         </div>
      </div>
   );
}

function UserProfile() {
   const { username } = useParams();
   const navigate = useNavigate();
   const { user: authUser, authFetch, refreshUser } = useAuth();
   const { addToast } = useNotification();

   const [publicUser, setPublicUser] = useState(null);
   const [profileStatus, setProfileStatus] = useState("idle");
   const [profileError, setProfileError] = useState("");
   const [profileAttempt, setProfileAttempt] = useState(0);
   const [failedProfileAvatarUrl, setFailedProfileAvatarUrl] = useState(null);
   const [isProfileImageOpen, setIsProfileImageOpen] = useState(false);
   const profileImageTriggerRef = useRef(null);

   const isOwnProfile = !username || username === authUser?.username;
   const displayUser = isOwnProfile ? authUser : publicUser;
   const displayUsername = displayUser?.username;

   useEffect(() => {
      if (isOwnProfile) return undefined;

      let isCancelled = false;
      setPublicUser(null);
      setProfileStatus("loading");
      setProfileError("");

      authFetch(resolveApiEndpoint("USER_PROFILE", username), { method: "GET" })
         .then((data) => {
            if (isCancelled) return;
            setPublicUser(data);
            setProfileStatus("success");
         })
         .catch((error) => {
            if (isCancelled) return;
            if (error?.status === 404) {
               setProfileStatus("not-found");
               return;
            }
            setProfileStatus("error");
            setProfileError("We couldn't load this profile. Check your connection and try again.");
         });

      return () => {
         isCancelled = true;
      };
   }, [authFetch, isOwnProfile, profileAttempt, username]);

   useEffect(() => {
      if (!isOwnProfile) return;
      setProfileStatus(authUser ? "success" : "loading");
      setProfileError("");
   }, [authUser, isOwnProfile]);

   useEffect(() => {
      if (isOwnProfile) refreshUser?.();
   }, [isOwnProfile, refreshUser, username]);

   const [isFollowing, setIsFollowing] = useState(false);
   const [followersCount, setFollowersCount] = useState(0);
   const [followingCount, setFollowingCount] = useState(0);
   const [isFollowPending, setIsFollowPending] = useState(false);

   useEffect(() => {
      if (!displayUser) return;
      setIsFollowing(Boolean(displayUser.is_following));
      setFollowersCount(Number(displayUser.followers_count) || 0);
      setFollowingCount(Number(displayUser.following_count) || 0);
   }, [displayUser]);

   const handleFollowToggle = async () => {
      if (!displayUsername || isFollowPending) return;
      setIsFollowPending(true);
      try {
         const response = await authFetch(resolveApiEndpoint("USER_FOLLOW", displayUsername), {
            method: "POST",
         });
         setIsFollowing(Boolean(response.is_following));
         setFollowersCount(Number(response.followers_count) || 0);
      } catch {
         addToast({
            type: "error",
            message: `We couldn't ${isFollowing ? "unfollow" : "follow"} this member. Please try again.`,
         });
      } finally {
         setIsFollowPending(false);
      }
   };

   const [activeTab, setActiveTab] = useState("threads");
   const [activityState, setActivityState] = useState({
      threads: { status: "idle", items: [], error: "" },
      contributions: { status: "idle", items: [], error: "" },
   });
   const [visibleCounts, setVisibleCounts] = useState({
      threads: TAB_PAGE_SIZE,
      contributions: TAB_PAGE_SIZE,
   });
   const activityRequestGenerationRef = useRef({
      threads: 0,
      contributions: 0,
   });
   const activityUsernameRef = useRef(displayUsername);

   useEffect(() => {
      activityUsernameRef.current = displayUsername;
      activityRequestGenerationRef.current = {
         threads: activityRequestGenerationRef.current.threads + 1,
         contributions: activityRequestGenerationRef.current.contributions + 1,
      };
      setActiveTab("threads");
      setActivityState({
         threads: { status: "idle", items: [], error: "" },
         contributions: { status: "idle", items: [], error: "" },
      });
      setVisibleCounts({
         threads: TAB_PAGE_SIZE,
         contributions: TAB_PAGE_SIZE,
      });
      setIsProfileImageOpen(false);
   }, [displayUsername]);

   const activeActivity = activityState[activeTab];

   useEffect(() => {
      if (!displayUsername || activeActivity.status !== "idle") return undefined;

      const requestedTab = activeTab;
      const requestedUsername = displayUsername;
      const requestGeneration = activityRequestGenerationRef.current[requestedTab] + 1;
      activityRequestGenerationRef.current[requestedTab] = requestGeneration;
      const endpoint = requestedTab === "threads" ? "USER_THREADS" : "USER_CONTRIBUTIONS";

      const isCurrentRequest = () =>
         activityUsernameRef.current === requestedUsername &&
         activityRequestGenerationRef.current[requestedTab] === requestGeneration;

      setActivityState((current) => ({
         ...current,
         [requestedTab]: { ...current[requestedTab], status: "loading", error: "" },
      }));

      authFetch(resolveApiEndpoint(endpoint, requestedUsername), { method: "GET" })
         .then((data) => {
            if (!isCurrentRequest()) return;
            const items = Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
            setActivityState((current) => ({
               ...current,
               [requestedTab]: { status: "success", items, error: "" },
            }));
         })
         .catch(() => {
            if (!isCurrentRequest()) return;
            setActivityState((current) => ({
               ...current,
               [requestedTab]: {
                  ...current[requestedTab],
                  status: "error",
                  error: "We couldn't load this activity. Please try again.",
               },
            }));
         });
   }, [activeActivity.status, activeTab, authFetch, displayUsername]);

   const visibleTabItems = useMemo(() => {
      const visibleCount = visibleCounts[activeTab] ?? TAB_PAGE_SIZE;
      return activeActivity.items.slice(0, visibleCount);
   }, [activeActivity.items, activeTab, visibleCounts]);

   const currentVisibleCount = visibleCounts[activeTab] ?? TAB_PAGE_SIZE;
   const hasMoreTabItems = activeActivity.items.length > currentVisibleCount;
   const canShowLessTabItems = currentVisibleCount > TAB_PAGE_SIZE && activeActivity.items.length > TAB_PAGE_SIZE;

   const selectTab = (tab) => setActiveTab(tab);

   const handleTabKeyDown = (event) => {
      const currentIndex = ACTIVITY_TABS.indexOf(activeTab);
      let nextIndex = null;
      if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % ACTIVITY_TABS.length;
      if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + ACTIVITY_TABS.length) % ACTIVITY_TABS.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = ACTIVITY_TABS.length - 1;
      if (nextIndex === null) return;
      event.preventDefault();
      const nextTab = ACTIVITY_TABS[nextIndex];
      selectTab(nextTab);
      document.getElementById(`profile-tab-${nextTab}`)?.focus();
   };

   const retryActivity = () => {
      setActivityState((current) => ({
         ...current,
         [activeTab]: { ...current[activeTab], status: "idle", error: "" },
      }));
   };

   const [connectionDialog, setConnectionDialog] = useState(null);
   const [connectionState, setConnectionState] = useState({ status: "idle", items: [], error: "" });
   const connectionDialogTriggerRef = useRef(null);
   const connectionCloseRef = useRef(null);
   const connectionRequestGenerationRef = useRef(0);

   const loadConnections = async (type) => {
      if (!displayUsername) return;
      const requestGeneration = connectionRequestGenerationRef.current + 1;
      connectionRequestGenerationRef.current = requestGeneration;
      const endpoint = type === "followers" ? "USER_FOLLOWERS" : "USER_FOLLOWING";
      setConnectionState({ status: "loading", items: [], error: "" });
      try {
         const data = await authFetch(resolveApiEndpoint(endpoint, displayUsername), { method: "GET" });
         if (connectionRequestGenerationRef.current !== requestGeneration) return;
         const items = Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : [];
         setConnectionState({ status: "success", items, error: "" });
      } catch {
         if (connectionRequestGenerationRef.current !== requestGeneration) return;
         setConnectionState({
            status: "error",
            items: [],
            error: `We couldn't load ${type}. Please try again.`,
         });
      }
   };

   const openConnectionDialog = (type, trigger) => {
      connectionDialogTriggerRef.current = trigger;
      setConnectionDialog(type);
      loadConnections(type);
   };

   const closeConnectionDialog = () => {
      connectionRequestGenerationRef.current += 1;
      setConnectionDialog(null);
   };

   const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
   const [editUsername, setEditUsername] = useState("");
   const [editBio, setEditBio] = useState("");
   const [editAvatarBase64, setEditAvatarBase64] = useState(null);
   const [editAvatarFileName, setEditAvatarFileName] = useState("");
   const [isSavingProfile, setIsSavingProfile] = useState(false);
   const [editError, setEditError] = useState("");
   const editDialogTriggerRef = useRef(null);
   const editUsernameRef = useRef(null);

   const openEditDialog = (trigger) => {
      editDialogTriggerRef.current = trigger;
      setEditUsername(displayUser?.username || "");
      setEditBio(displayUser?.bio || "");
      setEditAvatarBase64(null);
      setEditAvatarFileName("");
      setEditError("");
      setIsEditDialogOpen(true);
   };

   const closeEditDialog = () => {
      if (!isSavingProfile) setIsEditDialogOpen(false);
   };

   const handleImageUpload = (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      setEditAvatarFileName(file.name);
      const reader = new FileReader();
      reader.onloadend = () => setEditAvatarBase64(reader.result);
      reader.readAsDataURL(file);
   };

   const handleSaveProfile = async (event) => {
      event.preventDefault();
      const normalizedUsername = editUsername.trim();
      if (!normalizedUsername) {
         setEditError("Username is required.");
         editUsernameRef.current?.focus();
         return;
      }

      setIsSavingProfile(true);
      setEditError("");
      try {
         const payload = { username: normalizedUsername, bio: editBio };
         if (editAvatarBase64) payload.avatar_base64 = editAvatarBase64;
         await authFetch(resolveApiEndpoint("PROFILE_UPDATE"), {
            method: "PATCH",
            body: payload,
         });
         const refreshedUser = await refreshUser?.();
         const savedUsername = refreshedUser?.username || normalizedUsername;
         setIsEditDialogOpen(false);
         if (username && savedUsername !== username) {
            navigate(`/user/${encodeURIComponent(savedUsername)}`, { replace: true });
         }
         addToast({ type: "success", message: "Profile updated." });
      } catch (error) {
         const usernameMessage = Array.isArray(error?.username) ? error.username[0] : error?.username;
         setEditError(usernameMessage || "We couldn't save your profile. Review your changes and try again.");
      } finally {
         setIsSavingProfile(false);
      }
   };

   if (profileStatus === "loading" || profileStatus === "idle") {
      return (
         <main className="user-profile user-profile--state" aria-busy="true">
            <div className="user-profile__page-state" role="status" aria-live="polite">
               <span className="user-profile__state-icon user-profile__state-icon--loading" aria-hidden="true">
                  <Icons name="loader" size={24} />
               </span>
               <h1>Loading profile</h1>
               <p>Gathering this member's community activity.</p>
            </div>
         </main>
      );
   }

   if (profileStatus === "not-found") {
      return (
         <main className="user-profile user-profile--state">
            <div className="user-profile__page-state">
               <span className="user-profile__state-icon" aria-hidden="true">
                  <Icons name="user" size={24} />
               </span>
               <h1>Profile unavailable</h1>
               <p>This community member could not be found.</p>
               <Link className="user-profile__primary-button" to="/community">
                  Back to community
               </Link>
            </div>
         </main>
      );
   }

   if (profileStatus === "error" || !displayUser) {
      return (
         <main className="user-profile user-profile--state">
            <div className="user-profile__page-state" role="alert">
               <span className="user-profile__state-icon user-profile__state-icon--error" aria-hidden="true">
                  <Icons name="alert-circle" size={24} />
               </span>
               <h1>Profile could not load</h1>
               <p>{profileError || "We couldn't load this profile. Please try again."}</p>
               <button
                  type="button"
                  className="user-profile__primary-button"
                  onClick={() => setProfileAttempt((attempt) => attempt + 1)}
               >
                  Try again
               </button>
            </div>
         </main>
      );
   }

   const numericTrustScore = Number(displayUser.trust_score);
   const hasTrustScore =
      displayUser.trust_score !== null && displayUser.trust_score !== undefined && Number.isFinite(numericTrustScore);
   const trustLevel = hasTrustScore
      ? getTrustLevel(numericTrustScore)
      : { label: "Not available", tone: "unavailable" };
   const isPlatformModerator = isPlatformModeratorRole(displayUser.role);
   const roleLabel = isPlatformModerator ? "Platform moderator" : "Community member";
   const currentTabDescription = getTabDescription(activeTab, isOwnProfile);
   const currentTabEmptyMessage = getEmptyTabMessage(activeTab, isOwnProfile);
   const hasViewableProfileAvatar =
      Boolean(displayUser.avatar_url) && failedProfileAvatarUrl !== displayUser.avatar_url;

   return (
      <main className="user-profile">
         <section className="user-profile__profile-card" aria-labelledby="profile-heading">
            <div className="user-profile__identity">
               <div className="user-profile__identity-top">
                  {hasViewableProfileAvatar ? (
                     <button
                        ref={profileImageTriggerRef}
                        type="button"
                        className="image-view-trigger user-profile__avatar-trigger"
                        aria-label={`View @${displayUser.username} profile picture`}
                        onClick={() => setIsProfileImageOpen(true)}
                     >
                        <ProfileAvatar
                           user={displayUser}
                           className="user-profile__avatar--large"
                           onImageError={() => setFailedProfileAvatarUrl(displayUser.avatar_url)}
                        />
                     </button>
                  ) : (
                     <ProfileAvatar
                        user={{ ...displayUser, avatar_url: null }}
                        className="user-profile__avatar--large"
                     />
                  )}

                  <div className="user-profile__name-group">
                     <h1 id="profile-heading">{displayUser.username}</h1>
                     <p className="user-profile__handle">@{displayUser.username.toLowerCase()}</p>
                  </div>

                  <div className={`user-profile__trust-compact is-${trustLevel.tone}`} aria-labelledby="trust-heading">
                     <span id="trust-heading" className="user-profile__trust-compact-label">
                        Trust Score
                     </span>
                     <div className="user-profile__trust-compact-value">
                        <strong>{hasTrustScore ? numericTrustScore.toFixed(1) : "—"}</strong>
                        <span>{trustLevel.label}</span>
                     </div>
                     <p className="user-profile__sr-only">
                        Participation reputation on TruthLens, not verification or publication authority.
                     </p>
                  </div>
               </div>

               <div className="user-profile__identity-details">
                  <p className={`user-profile__role ${isPlatformModerator ? "is-moderator" : ""}`}>
                     {isPlatformModerator && <Icons name="shield-user" size={16} aria-hidden="true" />}
                     {roleLabel}
                  </p>

                  <p className={`user-profile__bio ${displayUser.bio ? "" : "is-empty"}`.trim()}>
                     {displayUser.bio ||
                        (isOwnProfile ? "Add a bio to introduce yourself to the community." : "No bio shared.")}
                  </p>

                  <p className="user-profile__joined">
                     <Icons name="calendar" size={15} aria-hidden="true" />
                     Joined {formatDate(displayUser.date_joined)}
                  </p>

                  <div className="user-profile__profile-footer">
                     <div className="user-profile__connections">
                        <button
                           type="button"
                           onClick={(event) => openConnectionDialog("following", event.currentTarget)}
                           aria-label={`View ${followingCount.toLocaleString()} following`}
                        >
                           <strong>{followingCount.toLocaleString()}</strong> Following
                        </button>
                        <button
                           type="button"
                           onClick={(event) => openConnectionDialog("followers", event.currentTarget)}
                           aria-label={`View ${followersCount.toLocaleString()} followers`}
                        >
                           <strong>{followersCount.toLocaleString()}</strong> Followers
                        </button>
                     </div>

                     {isOwnProfile ? (
                        <button
                           type="button"
                           className="user-profile__secondary-button user-profile__profile-action"
                           onClick={(event) => openEditDialog(event.currentTarget)}
                        >
                           <Icons name="pencil" size={16} aria-hidden="true" />
                           Edit profile
                        </button>
                     ) : (
                        <button
                           type="button"
                           className={`user-profile__primary-button user-profile__profile-action ${isFollowing ? "is-following" : ""}`}
                           onClick={handleFollowToggle}
                           disabled={isFollowPending}
                           aria-pressed={isFollowing}
                        >
                           <Icons name={isFollowing ? "user-check" : "user-plus"} size={16} aria-hidden="true" />
                           {isFollowPending ? "Updating…" : isFollowing ? "Following" : "Follow"}
                        </button>
                     )}
                  </div>
               </div>
            </div>

            <section
               className="user-profile__activity"
               aria-labelledby="activity-heading"
               aria-describedby="activity-description"
            >
               <h2 id="activity-heading" className="user-profile__sr-only">
                  Community activity
               </h2>
               <p id="activity-description" className="user-profile__sr-only">
                  {currentTabDescription}
               </p>

               <div className="user-profile__activity-nav">
                  <div
                     className="user-profile__tabs"
                     role="tablist"
                     aria-label="Community activity"
                     onKeyDown={handleTabKeyDown}
                  >
                     {ACTIVITY_TABS.map((tab) => (
                        <button
                           key={tab}
                           id={`profile-tab-${tab}`}
                           type="button"
                           role="tab"
                           aria-selected={activeTab === tab}
                           aria-controls={`profile-panel-${tab}`}
                           tabIndex={activeTab === tab ? 0 : -1}
                           onClick={() => selectTab(tab)}
                        >
                           {tab === "threads" ? "Threads" : "Contributions"}
                        </button>
                     ))}
                  </div>

                  {activeActivity.status === "success" && activeActivity.items.length > 0 && (
                     <span className="user-profile__activity-count">
                        {activeActivity.items.length.toLocaleString()}{" "}
                        {activeTab === "threads" ? "threads" : "contributions"}
                     </span>
                  )}
               </div>

               {ACTIVITY_TABS.map((tab) => {
                  const isActivePanel = activeTab === tab;
                  return (
                     <div
                        key={tab}
                        id={`profile-panel-${tab}`}
                        className="user-profile__tab-panel"
                        role="tabpanel"
                        aria-labelledby={`profile-tab-${tab}`}
                        hidden={!isActivePanel}
                        tabIndex={isActivePanel ? 0 : -1}
                     >
                        {isActivePanel &&
                           (activeActivity.status === "loading" ? (
                              <div className="user-profile__loading-block" role="status" aria-live="polite">
                                 <span className="user-profile__sr-only">Loading {activeTab}.</span>
                                 <div className="user-profile__skeleton-list" aria-hidden="true">
                                    {Array.from({ length: TAB_SKELETON_COUNT }).map((_, index) => (
                                       <div className="user-profile__skeleton-item" key={`activity-skeleton-${index}`}>
                                          <span className="user-profile__skeleton-line is-short" />
                                          <span className="user-profile__skeleton-line" />
                                          <span className="user-profile__skeleton-line is-medium" />
                                       </div>
                                    ))}
                                 </div>
                              </div>
                           ) : activeActivity.status === "error" ? (
                              <div className="user-profile__inline-state is-error" role="alert">
                                 <Icons name="alert-circle" size={20} aria-hidden="true" />
                                 <div>
                                    <h3>Activity could not load</h3>
                                    <p>{activeActivity.error}</p>
                                 </div>
                                 <button type="button" onClick={retryActivity}>
                                    Try again
                                 </button>
                              </div>
                           ) : activeActivity.items.length === 0 ? (
                              <div className="user-profile__empty-state">
                                 <Icons
                                    name={activeTab === "threads" ? "message-square" : "file-text"}
                                    size={22}
                                    aria-hidden="true"
                                 />
                                 <h3>No {activeTab} yet</h3>
                                 <p>{currentTabEmptyMessage}</p>
                              </div>
                           ) : (
                              <>
                                 <div className="user-profile__activity-list">
                                    {activeTab === "threads"
                                       ? visibleTabItems.map((thread) => (
                                            <article className="user-profile__activity-item" key={thread.id}>
                                               <div className="user-profile__activity-item-topline">
                                                  <span
                                                     className={`user-profile__status is-${String(thread.status || "open").toLowerCase()}`}
                                                  >
                                                     <Icons name="circle" size={10} aria-hidden="true" />
                                                     {humanizeValue(thread.status, "Open")}
                                                  </span>
                                                  <time dateTime={thread.created_at}>
                                                     {formatActivityDate(thread.created_at)}
                                                  </time>
                                               </div>
                                               <div className="user-profile__activity-copy">
                                                  <h3>{getClaimContext(thread.claim)}</h3>
                                                  <p>
                                                     {thread.caption ||
                                                        "Community discussion started without additional context."}
                                                  </p>
                                               </div>
                                               <div className="user-profile__activity-footer">
                                                  <div
                                                     className="user-profile__activity-metrics"
                                                     aria-label="Thread activity"
                                                  >
                                                     <span>
                                                        <Icons name="paperclip" size={15} aria-hidden="true" />
                                                        {Number(thread.evidence_count || 0).toLocaleString()} evidence
                                                     </span>
                                                     <span>
                                                        <Icons name="message-circle" size={15} aria-hidden="true" />
                                                        {Number(thread.comment_count || 0).toLocaleString()} comments
                                                     </span>
                                                  </div>
                                                  <Link to={`/thread/detail/${encodeURIComponent(thread.id)}`}>
                                                     Open thread{" "}
                                                     <Icons name="arrow-right" size={15} aria-hidden="true" />
                                                  </Link>
                                               </div>
                                            </article>
                                         ))
                                       : visibleTabItems.map((item) => {
                                            const isComment = item.activity_type === "COMMENT";
                                            const contributionText = isComment
                                               ? item.comment_text || "Comment submitted."
                                               : item.evidence_caption || "Evidence submitted.";
                                            return (
                                               <article
                                                  className="user-profile__activity-item"
                                                  key={`${item.activity_type}-${item.id}`}
                                               >
                                                  <div className="user-profile__activity-item-topline">
                                                     <span
                                                        className={`user-profile__contribution-type ${isComment ? "is-comment" : "is-evidence"}`}
                                                     >
                                                        <Icons
                                                           name={isComment ? "message-square" : "file-text"}
                                                           size={15}
                                                           aria-hidden="true"
                                                        />
                                                        {isComment ? "Comment" : "Evidence"}
                                                     </span>
                                                     <time dateTime={item.activity_at}>
                                                        {formatActivityDate(item.activity_at)}
                                                     </time>
                                                  </div>
                                                  <div className="user-profile__activity-copy">
                                                     <h3>{contributionText}</h3>
                                                     <p>
                                                        <span>On: </span>
                                                        {getClaimContext(item.thread?.claim)}
                                                     </p>
                                                     {item.thread?.caption && (
                                                        <p className="user-profile__thread-caption">
                                                           {item.thread.caption}
                                                        </p>
                                                     )}
                                                  </div>
                                                  <div className="user-profile__activity-footer">
                                                     <div className="user-profile__activity-metrics">
                                                        {!isComment && (
                                                           <>
                                                              <span>{humanizeValue(item.evidence_type)}</span>
                                                              <span>
                                                                 {humanizeValue(item.evidence_status, "Unverified")}
                                                              </span>
                                                           </>
                                                        )}
                                                        {item.evidence_url && (
                                                           <a
                                                              href={item.evidence_url}
                                                              target="_blank"
                                                              rel="noopener noreferrer"
                                                           >
                                                              Cited source{" "}
                                                              <Icons
                                                                 name="external-link"
                                                                 size={14}
                                                                 aria-hidden="true"
                                                              />
                                                           </a>
                                                        )}
                                                     </div>
                                                     <Link to={`/thread/detail/${encodeURIComponent(item.thread?.id)}`}>
                                                        Open thread{" "}
                                                        <Icons name="arrow-right" size={15} aria-hidden="true" />
                                                     </Link>
                                                  </div>
                                               </article>
                                            );
                                         })}
                                 </div>

                                 {(hasMoreTabItems || canShowLessTabItems) && (
                                    <div className="user-profile__pagination">
                                       <span>
                                          Showing {visibleTabItems.length.toLocaleString()} of{" "}
                                          {activeActivity.items.length.toLocaleString()}
                                       </span>
                                       <div>
                                          {canShowLessTabItems && (
                                             <button
                                                type="button"
                                                onClick={() =>
                                                   setVisibleCounts((current) => ({
                                                      ...current,
                                                      [activeTab]: TAB_PAGE_SIZE,
                                                   }))
                                                }
                                             >
                                                Show less
                                             </button>
                                          )}
                                          {hasMoreTabItems && (
                                             <button
                                                type="button"
                                                onClick={() =>
                                                   setVisibleCounts((current) => ({
                                                      ...current,
                                                      [activeTab]:
                                                         (current[activeTab] ?? TAB_PAGE_SIZE) + TAB_PAGE_SIZE,
                                                   }))
                                                }
                                             >
                                                Load more
                                             </button>
                                          )}
                                       </div>
                                    </div>
                                 )}
                              </>
                           ))}
                     </div>
                  );
               })}
            </section>
         </section>

         <ImageLightbox
            open={isProfileImageOpen}
            src={displayUser.avatar_url}
            alt={`${displayUser.username}'s profile picture`}
            ariaLabel={`Profile picture for @${displayUser.username}`}
            onClose={() => setIsProfileImageOpen(false)}
            returnFocusRef={profileImageTriggerRef}
            variant="profile"
         />

         {connectionDialog && (
            <ProfileDialog
               labelledBy="connection-dialog-title"
               describedBy="connection-dialog-description"
               initialFocusRef={connectionCloseRef}
               onClose={closeConnectionDialog}
               returnFocusRef={connectionDialogTriggerRef}
            >
               <div className="user-profile__dialog-header">
                  <div>
                     <h2 id="connection-dialog-title">
                        {connectionDialog === "followers" ? "Followers" : "Following"}
                     </h2>
                     <p id="connection-dialog-description">
                        {connectionDialog === "followers"
                           ? `People who follow @${displayUser.username}.`
                           : `People @${displayUser.username} follows.`}
                     </p>
                  </div>
                  <button
                     ref={connectionCloseRef}
                     type="button"
                     className="user-profile__icon-button"
                     onClick={closeConnectionDialog}
                     aria-label="Close connections dialog"
                  >
                     <Icons name="x" size={20} aria-hidden="true" />
                  </button>
               </div>

               <div className="user-profile__connection-list">
                  {connectionState.status === "loading" ? (
                     <div className="user-profile__dialog-state" role="status" aria-live="polite">
                        <Icons name="loader" size={20} aria-hidden="true" />
                        Loading {connectionDialog}…
                     </div>
                  ) : connectionState.status === "error" ? (
                     <div className="user-profile__dialog-state is-error" role="alert">
                        <Icons name="alert-circle" size={20} aria-hidden="true" />
                        <p>{connectionState.error}</p>
                        <button type="button" onClick={() => loadConnections(connectionDialog)}>
                           Try again
                        </button>
                     </div>
                  ) : connectionState.items.length === 0 ? (
                     <div className="user-profile__dialog-state">
                        <Icons name="users" size={20} aria-hidden="true" />
                        No {connectionDialog} yet.
                     </div>
                  ) : (
                     connectionState.items.map((member) => (
                        <button
                           type="button"
                           className="user-profile__connection"
                           key={member.id}
                           onClick={() => {
                              closeConnectionDialog();
                              navigate(`/user/${encodeURIComponent(member.username)}`);
                           }}
                        >
                           <ProfileAvatar user={member} />
                           <span>
                              <strong>{member.username}</strong>
                              <small>
                                 {isPlatformModeratorRole(member.role)
                                    ? "Platform moderator"
                                    : `Trust score ${Number(member.trust_score || 0).toFixed(1)}`}
                              </small>
                           </span>
                           <Icons name="chevron-right" size={18} aria-hidden="true" />
                        </button>
                     ))
                  )}
               </div>
            </ProfileDialog>
         )}

         {isEditDialogOpen && (
            <ProfileDialog
               className="user-profile__dialog--edit"
               labelledBy="edit-profile-dialog-title"
               describedBy="edit-profile-dialog-description"
               initialFocusRef={editUsernameRef}
               isBusy={isSavingProfile}
               onClose={closeEditDialog}
               returnFocusRef={editDialogTriggerRef}
            >
               <form onSubmit={handleSaveProfile}>
                  <div className="user-profile__dialog-header">
                     <div>
                        <h2 id="edit-profile-dialog-title">Edit profile</h2>
                        <p id="edit-profile-dialog-description">Update how you appear to the TruthLens community.</p>
                     </div>
                     <button
                        type="button"
                        className="user-profile__icon-button"
                        onClick={closeEditDialog}
                        disabled={isSavingProfile}
                        aria-label="Close edit profile dialog"
                     >
                        <Icons name="x" size={20} aria-hidden="true" />
                     </button>
                  </div>

                  <div className="user-profile__edit-fields">
                     <div className="user-profile__avatar-field">
                        {editAvatarBase64 ? (
                           <span className="user-profile__avatar user-profile__avatar--edit">
                              <img src={editAvatarBase64} alt="New profile avatar preview" />
                           </span>
                        ) : (
                           <ProfileAvatar user={displayUser} className="user-profile__avatar--edit" />
                        )}
                        <div className="user-profile__avatar-upload">
                           <span>Profile picture</span>
                           <label className="user-profile__file-button">
                              <Icons name="upload" size={15} aria-hidden="true" />
                              Choose photo
                              <input
                                 className="user-profile__file-input"
                                 type="file"
                                 accept="image/*"
                                 onChange={handleImageUpload}
                                 disabled={isSavingProfile}
                              />
                           </label>
                           {editAvatarFileName && <small>{editAvatarFileName}</small>}
                        </div>
                     </div>

                     <label className="user-profile__edit-field">
                        <span>Username</span>
                        <input
                           ref={editUsernameRef}
                           type="text"
                           value={editUsername}
                           onChange={(event) => setEditUsername(event.target.value)}
                           autoComplete="username"
                           maxLength={150}
                           required
                           disabled={isSavingProfile}
                        />
                        <small>Your @handle and profile URL update with your username.</small>
                     </label>

                     <label className="user-profile__edit-field">
                        <span>Bio</span>
                        <textarea
                           value={editBio}
                           onChange={(event) => setEditBio(event.target.value)}
                           placeholder="Tell the community about yourself."
                           disabled={isSavingProfile}
                        />
                     </label>

                     {editError && (
                        <p className="user-profile__form-error" role="alert">
                           <Icons name="alert-circle" size={17} aria-hidden="true" />
                           {editError}
                        </p>
                     )}
                  </div>

                  <div className="user-profile__dialog-actions">
                     <button
                        type="button"
                        className="user-profile__tertiary-button"
                        onClick={closeEditDialog}
                        disabled={isSavingProfile}
                     >
                        Cancel
                     </button>
                     <button type="submit" className="user-profile__primary-button" disabled={isSavingProfile}>
                        {isSavingProfile ? "Saving…" : "Save changes"}
                     </button>
                  </div>
               </form>
            </ProfileDialog>
         )}
      </main>
   );
}

export default UserProfile;
