import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "./Icons.jsx";
import "./NavigationBar.css";
import NotificationPopup from "./NotificationPopup.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { buildApiUrl, useEndpoint } from "../utils/api";

/**
 *
 * @param {Object} user - User object from auth context
 * @returns {string} Dashboard path (/moderation or /dashboard)
 */

const getDashboardPath = (user) => {
   if (user?.role === "MOD" || user?.role === "MODERATOR") {
      return "/moderation";
   }
   return "/dashboard";
};

const isModeratorRole = (role) => role === "MOD" || role === "MODERATOR";

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
   const searchContainerRef = useRef(null);
   const searchRequestIdRef = useRef(0);
   const location = useLocation();
   const navigate = useNavigate();
   const threadsEndpoint = useEndpoint("THREADS");
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
            setIsOpen(false);
            setSearchOpen(false);
            setMobileSearchOpen(false);
         }
      }
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
   }, []);

   useEffect(() => {
      setIsOpen(false);
      setSearchOpen(false);
      setMobileSearchOpen(false);
   }, [location.pathname]);

   useEffect(() => {
      const timeoutId = window.setTimeout(() => {
         setDebouncedSearch(searchInput.trim());
      }, 250);

      return () => window.clearTimeout(timeoutId);
   }, [searchInput]);

   useEffect(() => {
      const query = debouncedSearch;
      if (!query) {
         setSearchLoading(false);
         setSearchUsers([]);
         setSearchThreads([]);
         return;
      }

      const requestId = searchRequestIdRef.current + 1;
      searchRequestIdRef.current = requestId;
      setSearchLoading(true);
      setSearchOpen(true);

      const encodedQuery = encodeURIComponent(query);
      const threadSearchUrl = `${threadsEndpoint}?search=${encodedQuery}`;
      const userSearchUrl = `${usersSearchEndpoint}?search=${encodedQuery}&limit=6`;

      Promise.all([
         authFetch(threadSearchUrl, { method: "GET" }),
         authFetch(userSearchUrl, { method: "GET" }),
      ])
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

   function trustColor(score) {
      if (score >= 75) return "#0e9f6e";
      if (score >= 45) return "#d97706";
      return "#e02424";
   }

   const handleSearchSubmit = (e) => {
      e.preventDefault();
      const query = searchInput.trim();
      if (!query) return;
      setSearchOpen(false);
      navigate(`/community?q=${encodeURIComponent(query)}`);
   };

   const handleClearSearch = () => {
      setSearchInput("");
      setDebouncedSearch("");
      setSearchOpen(false);
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
      const authorName = thread?.author?.username
         ? `@${thread.author.username}`
         : "Community thread";
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
   const displayTrustScore = Number(user?.trust_breakdown?.trust_score ?? user?.trust_score ?? 0);
   const color = trustColor(displayTrustScore);
   const profileScorePillStyle = isModeratorUser
      ? undefined
      : { color, borderColor: `${color}99`, background: `${color}75` };

   return (
      <>
         <nav className="top-navbar">
            <div className="nav-left">
               <div className="logo-section">
                  <img
                     src={LogoImage}
                     alt="TruthLens Logo"
                     style={{ height: "40px", width: "auto" }}
                  />
                  <Link
                     to="/community"
                     className="link">
                     <span className="logo-text">TruthLens</span>
                  </Link>
               </div>

               <div className="nav-tabs">
                  <Link
                     to="/community"
                     className="link">
                     <div
                        className={`nav-tab ${location.pathname === "/community" ? "active" : ""}`}>
                        <Icons name="globe" />
                        Community Feed
                     </div>
                  </Link>
                  {/* <Link
                  to={getDashboardPath(user)}
                  className="link">
                  <div
                     className={`nav-tab ${location.pathname === getDashboardPath(user) ? "active" : ""}`}>
                     <Icons name={isModeratorUser ? "shield" : "dashboard"} />
                     Dashboard
                  </div>
               </Link> */}
                  <Link
                     to="/verify"
                     className="link">
                     <div className={`nav-tab ${location.pathname === "/verify" ? "active" : ""}`}>
                        <Icons name="scan-line" />
                        Verify
                     </div>
                  </Link>
               </div>
            </div>

            <div className="nav-right">
               <div
                  className="navbar-search"
                  ref={searchContainerRef}>
                  <form
                     className="search-box"
                     onSubmit={handleSearchSubmit}>
                     <Icons
                        name="search"
                        color="gray"
                     />
                     <input
                        type="text"
                        placeholder="Search people and claims..."
                        value={searchInput}
                        onFocus={() => {
                           if (searchInput.trim()) {
                              setSearchOpen(true);
                           }
                        }}
                        onChange={(e) => setSearchInput(e.target.value)}
                        aria-label="Global search"
                     />
                     {searchInput && (
                        <button
                           type="button"
                           className="search-clear-btn"
                           onClick={handleClearSearch}
                           aria-label="Clear search">
                           <Icons
                              name="x"
                              size={14}
                           />
                        </button>
                     )}
                  </form>

                  {shouldShowSearchDropdown && (
                     <div
                        className="search-results-dropdown"
                        role="listbox"
                        aria-label="Global search results">
                        {searchLoading ? (
                           <div className="search-results-state">
                              <Icons
                                 name="loader"
                                 size={14}
                                 className="search-spinner"
                              />
                              Searching TruthLens...
                           </div>
                        ) : (
                           <>
                              {totalSearchResults === 0 && (
                                 <div className="search-results-state">
                                    No results found for "{debouncedSearch}".
                                 </div>
                              )}

                              {searchUsers.length > 0 && (
                                 <div className="search-section">
                                    <div className="search-section-title">People</div>
                                    {searchUsers.map((searchUser) => (
                                       <button
                                          key={searchUser.id}
                                          type="button"
                                          className="search-result-item user-result"
                                          onClick={() =>
                                             handleUserResultClick(searchUser.username)
                                          }>
                                          <div className="search-user-avatar">
                                             {searchUser.avatar_url ? (
                                                <img
                                                   src={searchUser.avatar_url}
                                                   alt={`${searchUser.username}'s avatar`}
                                                />
                                             ) : (
                                                <Icons
                                                   name="user"
                                                   size={14}
                                                />
                                             )}
                                          </div>
                                          <div className="search-result-copy">
                                             <span className="search-result-title">
                                                @{searchUser.username}
                                             </span>
                                             <span className="search-result-subtitle">
                                                {searchUser.bio || "TruthLens member"}
                                             </span>
                                          </div>
                                          <span
                                             className={`search-trust-pill ${isModeratorRole(searchUser.role) ? "mod" : ""}`}>
                                             {isModeratorRole(searchUser.role)
                                                ? "MOD"
                                                : Number(searchUser.trust_score || 0).toFixed(1)}
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
                                          onClick={() => handleThreadResultClick(thread.id)}>
                                          <div className="search-thread-icon">
                                             <Icons
                                                name="file-text"
                                                size={14}
                                             />
                                          </div>
                                          <div className="search-result-copy">
                                             <span className="search-result-title">
                                                {getThreadTitle(thread)}
                                             </span>
                                             <span className="search-result-subtitle">
                                                {getThreadSubtitle(thread)}
                                             </span>
                                          </div>
                                       </button>
                                    ))}
                                 </div>
                              )}

                              {totalSearchResults > 0 && (
                                 <button
                                    type="button"
                                    className="search-view-all-btn"
                                    onClick={handleViewAllResults}>
                                    View all results for "{debouncedSearch}"
                                 </button>
                              )}
                           </>
                        )}
                     </div>
                  )}
               </div>
               <NotificationPopup />

               <div
                  className="user-menu-container"
                  ref={dropdownRef}>
                  <button
                     className={`user-profile-pill ${isOpen ? "open" : ""}`}
                     onClick={() => setIsOpen((v) => !v)}
                     aria-haspopup="menu"
                     aria-expanded={isOpen}>
                     <div className="user-icon-sm">
                        {isModeratorUser ? <Icons name="shield-user" /> : <Icons name="user" />}
                     </div>
                     <span className="username">@{user?.username}</span>
                     <span
                        className={`trust-score ${isModeratorUser ? "trust-score-mod" : ""}`}
                        style={profileScorePillStyle}>
                        {isModeratorUser ? "MOD" : displayTrustScore.toFixed(1)}
                     </span>
                     <span className={`chevron ${isOpen ? "rotated" : ""}`}>
                        <Icons
                           name="chevron-down"
                           color="#fff"
                        />
                     </span>
                  </button>

                  {isOpen && (
                     <div
                        className="dropdown-menu"
                        role="menu">
                        <div className="dropdown-header">
                           <span className="dropdown-username">@{user?.username}</span>
                           <span className="dropdown-email">{user?.email}</span>
                        </div>

                        <div
                           className="dropdown-section"
                           role="group">
                           <Link
                              to="/profile"
                              className="link"
                              role="menuitem">
                              <button
                                 className={`dropdown-item ${location.pathname === "/profile" ? "active" : ""}`}
                                 onClick={() => setIsOpen(false)}>
                                 <Icons name="user" />
                                 My Public Profile
                              </button>
                           </Link>
                           <Link
                              to={getDashboardPath(user)}
                              className="link"
                              role="menuitem">
                              <button
                                 className="dropdown-item"
                                 onClick={() => setIsOpen(false)}>
                                 <Icons name={isModeratorUser ? "shield" : "dashboard"} />
                                 Dashboard
                              </button>
                           </Link>
                           <Link
                              to="/settings"
                              className="link"
                              role="menuitem">
                              <button
                                 className="dropdown-item"
                                 onClick={() => setIsOpen(false)}>
                                 <Icons name="settings" />
                                 Settings
                              </button>
                           </Link>
                        </div>

                        <div className="dropdown-divider" />

                        <div
                           className="dropdown-section"
                           role="group">
                           <button
                              className="dropdown-item danger"
                              role="menuitem"
                              onClick={() => {
                                 setIsOpen(false);
                                 logout();
                                 navigate("/login");
                              }}>
                              <Icons name="logout" />
                              Log Out
                           </button>
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
                        }}>
                        <Icons
                           name="search"
                           size={18}
                           color="#6b7280"
                        />
                        <input
                           type="text"
                           className="mobile-search-input"
                           placeholder="Search people and claims..."
                           value={searchInput}
                           onChange={(e) => setSearchInput(e.target.value)}
                           autoFocus
                           aria-label="Mobile search"
                        />
                        {searchInput && (
                           <button
                              type="button"
                              className="search-clear-btn"
                              onClick={handleClearSearch}>
                              <Icons
                                 name="x"
                                 size={16}
                              />
                           </button>
                        )}
                     </form>
                     <button
                        className="mobile-search-cancel"
                        onClick={() => {
                           setMobileSearchOpen(false);
                           handleClearSearch();
                        }}>
                        Cancel
                     </button>
                  </div>

                  <div className="mobile-search-results">
                     {searchLoading ? (
                        <div className="search-results-state">
                           <Icons
                              name="loader"
                              size={14}
                              className="search-spinner"
                           />
                           Searching TruthLens...
                        </div>
                     ) : (
                        <>
                           {debouncedSearch &&
                              searchUsers.length === 0 &&
                              searchThreads.length === 0 && (
                                 <div className="search-results-state">
                                    No results found for "{debouncedSearch}".
                                 </div>
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
                                       }}>
                                       <div className="search-user-avatar">
                                          {su.avatar_url ? (
                                             <img
                                                src={su.avatar_url}
                                                alt={`${su.username}'s avatar`}
                                             />
                                          ) : (
                                             <Icons
                                                name="user"
                                                size={14}
                                             />
                                          )}
                                       </div>
                                       <div className="search-result-copy">
                                          <span className="search-result-title">
                                             @{su.username}
                                          </span>
                                          <span className="search-result-subtitle">
                                             {su.bio || "TruthLens member"}
                                          </span>
                                       </div>
                                       <span
                                          className={`search-trust-pill ${isModeratorRole(su.role) ? "mod" : ""}`}>
                                          {isModeratorRole(su.role)
                                             ? "MOD"
                                             : Number(su.trust_score || 0).toFixed(1)}
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
                                       }}>
                                       <div className="search-thread-icon">
                                          <Icons
                                             name="file-text"
                                             size={14}
                                          />
                                       </div>
                                       <div className="search-result-copy">
                                          <span className="search-result-title">
                                             {getThreadTitle(thread)}
                                          </span>
                                          <span className="search-result-subtitle">
                                             {getThreadSubtitle(thread)}
                                          </span>
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
         </nav>

         {/* ── Mobile Bottom Tab Bar ── */}
         <nav
            className="mobile-bottom-bar"
            aria-label="Mobile navigation">
            <Link
               to="/community"
               className={`bottom-tab ${location.pathname === "/community" ? "active" : ""}`}>
               <Icons
                  name="home"
                  size={22}
               />
               <span>Feed</span>
            </Link>
            <button
               className={`bottom-tab ${mobileSearchOpen ? "active" : ""}`}
               onClick={() => setMobileSearchOpen(true)}>
               <Icons
                  name="search"
                  size={22}
               />
               <span>Search</span>
            </button>
            <Link
               to="/verify"
               className={`bottom-tab bottom-tab-center ${location.pathname === "/verify" ? "active" : ""}`}>
               <div className="bottom-tab-center-icon">
                  <Icons
                     name="scan-line"
                     size={24}
                     color="#fff"
                  />
               </div>
               <span>Verify</span>
            </Link>
            <Link
               to="/notifications"
               className={`bottom-tab ${location.pathname === "/notifications" ? "active" : ""}`}>
               <Icons
                  name="bell"
                  size={22}
               />
               <span>Notifications</span>
            </Link>
            <Link
               to="/profile"
               className={`bottom-tab ${location.pathname === "/profile" ? "active" : ""}`}>
               <Icons
                  name="user"
                  size={22}
               />
               <span>Me</span>
            </Link>
         </nav>
      </>
   );
}

export default NavigationBar;
