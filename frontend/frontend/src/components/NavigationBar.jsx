import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "./Icons.jsx";
import "./NavigationBar.css";
import Button from "./ui/Button.jsx";
import IconButton from "./ui/IconButton.jsx";
import { useAuth } from "../hooks/useAuth";
import { buildApiUrl, resolveApiEndpoint } from "../utils/api";
import { canAccessWorkspace } from "../utils/workspace";

const isModeratorRole = (role) => role === "MOD" || role === "MODERATOR";
const ACCOUNT_PANEL_ID = "tl-app-nav-account-panel";

function NavigationBar() {
   const { user, logout, authFetch } = useAuth();
   const [isOpen, setIsOpen] = useState(false);
   const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
   const [searchInput, setSearchInput] = useState("");
   const [debouncedSearch, setDebouncedSearch] = useState("");
   const [searchOpen, setSearchOpen] = useState(false);
   const [searchLoading, setSearchLoading] = useState(false);
   const [searchUsers, setSearchUsers] = useState([]);
   const [searchThreads, setSearchThreads] = useState([]);
   const dropdownRef = useRef(null);
   const accountTriggerRef = useRef(null);
   const searchContainerRef = useRef(null);
   const searchRequestIdRef = useRef(0);
   const location = useLocation();
   const navigate = useNavigate();
   const threadsEndpoint = resolveApiEndpoint("THREADS");
   const usersSearchEndpoint = buildApiUrl("users/search/");

   useEffect(() => {
      function handleClickOutside(e) {
         if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
            setIsOpen(false);
         }
         if (searchContainerRef.current && !searchContainerRef.current.contains(e.target)) {
            setSearchOpen(false);
         }
      }
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
   }, []);

   useEffect(() => {
      function handleEscape(e) {
         if (e.key === "Escape") {
            setSearchOpen(false);
            setMobileSearchOpen(false);
         }
      }
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
   }, []);

   useEffect(() => {
      if (!isOpen) return undefined;

      function handleAccountEscape(e) {
         if (e.key === "Escape") {
            setIsOpen(false);
            accountTriggerRef.current?.focus();
         }
      }

      document.addEventListener("keydown", handleAccountEscape);
      return () => document.removeEventListener("keydown", handleAccountEscape);
   }, [isOpen]);

   const closeNavigationOverlays = () => {
      setIsOpen(false);
      setSearchOpen(false);
      setMobileSearchOpen(false);
   };

   useEffect(() => {
      const timeoutId = window.setTimeout(() => {
         setDebouncedSearch(searchInput.trim());
      }, 250);

      return () => window.clearTimeout(timeoutId);
   }, [searchInput]);

   useEffect(() => {
      const query = debouncedSearch;

      if (!query) return;

      const requestId = searchRequestIdRef.current + 1;
      searchRequestIdRef.current = requestId;

      const encodedQuery = encodeURIComponent(query);

      const threadSearchUrl = `${threadsEndpoint}?search=${encodedQuery}`;

      const userSearchUrl = `${usersSearchEndpoint}?search=${encodedQuery}&limit=6`;

      Promise.all([authFetch(threadSearchUrl, { method: "GET" }), authFetch(userSearchUrl, { method: "GET" })])
         .then(([threadData, userData]) => {
            if (requestId !== searchRequestIdRef.current) return;

            const nextThreads = Array.isArray(threadData?.results)
               ? threadData.results
               : Array.isArray(threadData)
                 ? threadData
                 : [];

            const nextUsers = Array.isArray(userData?.results)
               ? userData.results
               : Array.isArray(userData)
                 ? userData
                 : [];

            setSearchThreads(nextThreads.slice(0, 6));
            setSearchUsers(nextUsers.slice(0, 6));
         })
         .catch(() => {
            if (requestId !== searchRequestIdRef.current) return;

            setSearchThreads([]);
            setSearchUsers([]);
         })
         .finally(() => {
            if (requestId === searchRequestIdRef.current) {
               setSearchLoading(false);
            }
         });
   }, [authFetch, debouncedSearch, threadsEndpoint, usersSearchEndpoint]);

   const handleSearchSubmit = (e) => {
      e.preventDefault();
      const query = searchInput.trim();
      if (!query) return;
      setSearchOpen(false);
      navigate(`/community?q=${encodeURIComponent(query)}`);
   };

   const handleSearchInputChange = (e) => {
      const value = e.target.value;
      const hasQuery = value.trim().length > 0;

      setSearchInput(value);

      if (hasQuery) {
         setSearchOpen(true);
         setSearchLoading(true);
      } else {
         // Invalidate any request that may still be running
         searchRequestIdRef.current += 1;

         setSearchOpen(false);
         setSearchLoading(false);
         setSearchUsers([]);
         setSearchThreads([]);
      }
   };

   const handleClearSearch = () => {
      searchRequestIdRef.current += 1;

      setSearchInput("");
      setDebouncedSearch("");
      setSearchOpen(false);
      setSearchLoading(false);
      setSearchUsers([]);
      setSearchThreads([]);
   };

   const handleUserResultClick = (username) => {
      setSearchOpen(false);
      navigate(`/user/${username}`);
   };

   const handleThreadResultClick = (threadId) => {
      setSearchOpen(false);
      navigate(`/thread/detail/${threadId}`);
   };

   const handleViewAllResults = () => {
      const query = (debouncedSearch || searchInput).trim();
      if (!query) return;
      setSearchOpen(false);
      navigate(`/community?q=${encodeURIComponent(query)}`);
   };

   const getThreadTitle = (thread) => {
      const caption = thread?.caption?.trim();
      if (caption) return caption;
      const claimText = thread?.claim?.context_text?.trim();
      if (claimText) return claimText;
      return "Untitled thread";
   };

   const getThreadSubtitle = (thread) => {
      const authorName = thread?.author?.username ? `@${thread.author.username}` : "Community thread";
      const verdict =
         thread?.claim?.effective_verdict ||
         thread?.claim?.final_verdict ||
         thread?.claim?.verdict ||
         thread?.claim?.ai_verdict ||
         "UNVERIFIED";
      return `${authorName} · ${verdict}`;
   };

   const shouldShowSearchDropdown = searchOpen && searchInput.trim().length > 0;
   const totalSearchResults = searchUsers.length + searchThreads.length;
   const isModeratorUser = isModeratorRole(user?.role);
   const canUseWorkspace = canAccessWorkspace(user);
   const displayTrustScore = Number(user?.trust_breakdown?.trust_score ?? user?.trust_score ?? 0);
   const isCommunityRoute =
      location.pathname === "/community" ||
      location.pathname === "/thread/create" ||
      location.pathname.startsWith("/thread/detail/");
   const isVerifyRoute = location.pathname === "/verify" || location.pathname.startsWith("/analysis/");
   const isDashboardRoute = location.pathname === "/dashboard";
   const isWorkspaceRoute = location.pathname === "/workspace" || location.pathname === "/moderation";
   const isProfileRoute = location.pathname === "/profile";

   return (
      <>
         <header className="top-navbar">
            <div className="tl-app-nav__start">
               <Link to="/community" className="tl-app-nav__brand">
                  <img src={LogoImage} alt="" className="tl-app-nav__brand-mark" />
                  <span className="tl-app-nav__brand-name">TruthLens</span>
               </Link>

               <nav className="tl-app-nav__primary" aria-label="Primary navigation">
                  <Link
                     to="/community"
                     className={`tl-app-nav__primary-link ${isCommunityRoute ? "active" : ""}`}
                     aria-current={isCommunityRoute ? "page" : undefined}
                  >
                     <Icons name="globe" />
                     Community
                  </Link>
                  <Link
                     to="/verify"
                     className={`tl-app-nav__primary-link ${isVerifyRoute ? "active" : ""}`}
                     aria-current={isVerifyRoute ? "page" : undefined}
                  >
                     <Icons name="scan-line" />
                     Verify
                  </Link>
                  <Link
                     to="/dashboard"
                     className={`tl-app-nav__primary-link ${isDashboardRoute ? "active" : ""}`}
                     aria-current={isDashboardRoute ? "page" : undefined}
                  >
                     <Icons name="dashboard" />
                     Dashboard
                  </Link>
                  {canUseWorkspace && (
                     <Link
                        to="/workspace"
                        className={`tl-app-nav__primary-link ${isWorkspaceRoute ? "active" : ""}`}
                        aria-current={isWorkspaceRoute ? "page" : undefined}
                     >
                        <Icons name="shield-check" />
                        Workspace
                     </Link>
                  )}
               </nav>
            </div>

            <div className="tl-app-nav__actions">
               <IconButton
                  variant="ghost"
                  density="comfortable"
                  className="tl-app-nav__mobile-search-trigger"
                  icon={<Icons name="search" size={20} />}
                  aria-label="Search"
                  onClick={() => setMobileSearchOpen(true)}
               />
               <div className="navbar-search" ref={searchContainerRef}>
                  <form className="search-box" onSubmit={handleSearchSubmit}>
                     <Icons name="search" color="gray" />
                     <input
                        type="text"
                        placeholder="Search people and claims..."
                        value={searchInput}
                        onFocus={() => {
                           if (searchInput.trim()) {
                              setSearchOpen(true);
                           }
                        }}
                        onChange={handleSearchInputChange}
                        aria-label="Global search"
                     />
                     {searchInput && (
                        <button
                           type="button"
                           className="search-clear-btn"
                           onClick={handleClearSearch}
                           aria-label="Clear search"
                        >
                           <Icons name="x" size={14} />
                        </button>
                     )}
                  </form>

                  {shouldShowSearchDropdown && (
                     <div className="search-results-dropdown" role="listbox" aria-label="Global search results">
                        {searchLoading ? (
                           <div className="search-results-state">
                              <Icons name="loader" size={14} className="search-spinner" />
                              Searching TruthLens...
                           </div>
                        ) : (
                           <>
                              {totalSearchResults === 0 && (
                                 <div className="search-results-state">No results found for "{debouncedSearch}".</div>
                              )}

                              {searchUsers.length > 0 && (
                                 <div className="search-section">
                                    <div className="search-section-title">People</div>
                                    {searchUsers.map((searchUser) => (
                                       <button
                                          key={searchUser.id}
                                          type="button"
                                          className="search-result-item user-result"
                                          onClick={() => handleUserResultClick(searchUser.username)}
                                       >
                                          <div className="search-user-avatar">
                                             {searchUser.avatar_url ? (
                                                <img
                                                   src={searchUser.avatar_url}
                                                   alt={`${searchUser.username}'s avatar`}
                                                />
                                             ) : (
                                                <Icons name="user" size={14} />
                                             )}
                                          </div>
                                          <div className="search-result-copy">
                                             <span className="search-result-title">@{searchUser.username}</span>
                                             <span className="search-result-subtitle">
                                                {searchUser.bio || "TruthLens member"}
                                             </span>
                                          </div>
                                          <span className="search-user-signals">
                                             <span className="search-trust-pill">
                                                Trust {Number(searchUser.trust_score || 0).toFixed(1)}
                                             </span>
                                             {isModeratorRole(searchUser.role) && (
                                                <span className="search-platform-role" aria-label="Platform moderator">
                                                   MOD
                                                </span>
                                             )}
                                          </span>
                                       </button>
                                    ))}
                                 </div>
                              )}

                              {searchThreads.length > 0 && (
                                 <div className="search-section">
                                    <div className="search-section-title">Threads</div>
                                    {searchThreads.map((thread) => (
                                       <button
                                          key={thread.id}
                                          type="button"
                                          className="search-result-item thread-result"
                                          onClick={() => handleThreadResultClick(thread.id)}
                                       >
                                          <div className="search-thread-icon">
                                             <Icons name="file-text" size={14} />
                                          </div>
                                          <div className="search-result-copy">
                                             <span className="search-result-title">{getThreadTitle(thread)}</span>
                                             <span className="search-result-subtitle">{getThreadSubtitle(thread)}</span>
                                          </div>
                                       </button>
                                    ))}
                                 </div>
                              )}

                              {totalSearchResults > 0 && (
                                 <button type="button" className="search-view-all-btn" onClick={handleViewAllResults}>
                                    View all results for "{debouncedSearch}"
                                 </button>
                              )}
                           </>
                        )}
                     </div>
                  )}
               </div>
               <div className="tl-app-nav__account" ref={dropdownRef}>
                  <button
                     ref={accountTriggerRef}
                     type="button"
                     className={`tl-app-nav__account-trigger ${isOpen ? "open" : ""}`}
                     onClick={() => setIsOpen((v) => !v)}
                     aria-expanded={isOpen}
                     aria-controls={ACCOUNT_PANEL_ID}
                  >
                     <span className="tl-app-nav__account-avatar" aria-hidden="true">
                        {isModeratorUser ? <Icons name="shield-user" /> : <Icons name="user" />}
                     </span>
                     <span className="tl-app-nav__account-copy">
                        <span className="tl-app-nav__account-name">@{user?.username}</span>
                        <span className="tl-app-nav__account-trust">Trust {displayTrustScore.toFixed(1)}</span>
                     </span>
                     {isModeratorUser && (
                        <span className="tl-app-nav__platform-role" aria-label="Platform moderator">
                           MOD
                        </span>
                     )}
                     <span className={`tl-app-nav__chevron ${isOpen ? "rotated" : ""}`} aria-hidden="true">
                        <Icons name="chevron-down" color="#fff" />
                     </span>
                  </button>

                  {isOpen && (
                     <div className="tl-app-nav__account-panel" id={ACCOUNT_PANEL_ID}>
                        <div className="tl-app-nav__account-header">
                           <span className="tl-app-nav__panel-username">@{user?.username}</span>
                           <span className="tl-app-nav__panel-email">{user?.email}</span>
                           <div className="tl-app-nav__account-metadata">
                              <span className="tl-app-nav__panel-trust">
                                 Trust {displayTrustScore.toFixed(1)}
                              </span>
                              {isModeratorUser && (
                                 <span className="tl-app-nav__panel-role">Platform moderator</span>
                              )}
                           </div>
                        </div>

                        <div className="tl-app-nav__account-links">
                           <Link
                              to="/profile"
                              className={`tl-app-nav__account-link ${location.pathname === "/profile" ? "active" : ""}`}
                              onClick={() => setIsOpen(false)}
                           >
                              <Icons name="user" />
                              My Public Profile
                           </Link>
                           <Link
                              to="/settings"
                              className={`tl-app-nav__account-link ${location.pathname === "/settings" ? "active" : ""}`}
                              onClick={() => setIsOpen(false)}
                           >
                              <Icons name="settings" />
                              Settings
                           </Link>
                        </div>

                        <div className="tl-app-nav__account-action">
                           <Button
                              variant="destructive"
                              density="compact"
                              fullWidth
                              leadingIcon={<Icons name="logout" />}
                              className="tl-app-nav__logout"
                              onClick={() => {
                                 setIsOpen(false);
                                 logout();
                                 navigate("/login");
                              }}
                           >
                              Log Out
                           </Button>
                        </div>
                     </div>
                  )}
               </div>
            </div>

            {/* ── Mobile Search Overlay ── */}
            {mobileSearchOpen && (
               <div className="mobile-search-overlay">
                  <div className="mobile-search-header">
                     <form
                        className="mobile-search-form"
                        onSubmit={(e) => {
                           e.preventDefault();
                           const q = searchInput.trim();
                           if (!q) return;
                           setMobileSearchOpen(false);
                           navigate(`/community?q=${encodeURIComponent(q)}`);
                        }}
                     >
                        <Icons name="search" size={18} color="#6b7280" />
                        <input
                           type="text"
                           className="mobile-search-input"
                           placeholder="Search people and claims..."
                           value={searchInput}
                           onChange={handleSearchInputChange}
                           autoFocus
                           aria-label="Mobile search"
                        />
                        {searchInput && (
                           <button type="button" className="search-clear-btn" onClick={handleClearSearch}>
                              <Icons name="x" size={16} />
                           </button>
                        )}
                     </form>
                     <button
                        className="mobile-search-cancel"
                        onClick={() => {
                           setMobileSearchOpen(false);
                           handleClearSearch();
                        }}
                     >
                        Cancel
                     </button>
                  </div>

                  <div className="mobile-search-results">
                     {searchLoading ? (
                        <div className="search-results-state">
                           <Icons name="loader" size={14} className="search-spinner" />
                           Searching TruthLens...
                        </div>
                     ) : (
                        <>
                           {debouncedSearch && searchUsers.length === 0 && searchThreads.length === 0 && (
                              <div className="search-results-state">No results found for "{debouncedSearch}".</div>
                           )}

                           {searchUsers.length > 0 && (
                              <div className="search-section">
                                 <div className="search-section-title">People</div>
                                 {searchUsers.map((su) => (
                                    <button
                                       key={su.id}
                                       type="button"
                                       className="search-result-item"
                                       onClick={() => {
                                          setMobileSearchOpen(false);
                                          handleUserResultClick(su.username);
                                       }}
                                    >
                                       <div className="search-user-avatar">
                                          {su.avatar_url ? (
                                             <img src={su.avatar_url} alt={`${su.username}'s avatar`} />
                                          ) : (
                                             <Icons name="user" size={14} />
                                          )}
                                       </div>
                                       <div className="search-result-copy">
                                          <span className="search-result-title">@{su.username}</span>
                                          <span className="search-result-subtitle">{su.bio || "TruthLens member"}</span>
                                       </div>
                                       <span className="search-user-signals">
                                          <span className="search-trust-pill">
                                             Trust {Number(su.trust_score || 0).toFixed(1)}
                                          </span>
                                          {isModeratorRole(su.role) && (
                                             <span className="search-platform-role" aria-label="Platform moderator">
                                                MOD
                                             </span>
                                          )}
                                       </span>
                                    </button>
                                 ))}
                              </div>
                           )}

                           {searchThreads.length > 0 && (
                              <div className="search-section">
                                 <div className="search-section-title">Threads</div>
                                 {searchThreads.map((thread) => (
                                    <button
                                       key={thread.id}
                                       type="button"
                                       className="search-result-item"
                                       onClick={() => {
                                          setMobileSearchOpen(false);
                                          handleThreadResultClick(thread.id);
                                       }}
                                    >
                                       <div className="search-thread-icon">
                                          <Icons name="file-text" size={14} />
                                       </div>
                                       <div className="search-result-copy">
                                          <span className="search-result-title">{getThreadTitle(thread)}</span>
                                          <span className="search-result-subtitle">{getThreadSubtitle(thread)}</span>
                                       </div>
                                    </button>
                                 ))}
                              </div>
                           )}
                        </>
                     )}
                  </div>
               </div>
            )}
         </header>

         {/* ── Mobile Bottom Tab Bar ── */}
         <nav className="mobile-bottom-bar" aria-label="Mobile primary navigation">
            <Link
               to="/community"
               className={`bottom-tab ${isCommunityRoute ? "active" : ""}`}
               onClick={closeNavigationOverlays}
               aria-current={isCommunityRoute ? "page" : undefined}
            >
               <Icons name="globe" size={20} />
               <span>Community</span>
            </Link>
            <Link
               to="/verify"
               className={`bottom-tab ${isVerifyRoute ? "active" : ""}`}
               onClick={closeNavigationOverlays}
               aria-current={isVerifyRoute ? "page" : undefined}
            >
               <Icons name="scan-line" size={20} />
               <span>Verify</span>
            </Link>
            <Link
               to="/dashboard"
               className={`bottom-tab ${isDashboardRoute ? "active" : ""}`}
               onClick={closeNavigationOverlays}
               aria-current={isDashboardRoute ? "page" : undefined}
            >
               <Icons name="dashboard" size={20} />
               <span>Dashboard</span>
            </Link>
            {canUseWorkspace && (
               <Link
                  to="/workspace"
                  className={`bottom-tab ${isWorkspaceRoute ? "active" : ""}`}
                  onClick={closeNavigationOverlays}
                  aria-current={isWorkspaceRoute ? "page" : undefined}
               >
                  <Icons name="shield-check" size={20} />
                  <span>Workspace</span>
               </Link>
            )}
            <Link
               to="/profile"
               className={`bottom-tab ${isProfileRoute ? "active" : ""}`}
               onClick={closeNavigationOverlays}
               aria-current={isProfileRoute ? "page" : undefined}
            >
               <Icons name="user" size={20} />
               <span>Profile</span>
            </Link>
         </nav>
      </>
   );
}

export default NavigationBar;
