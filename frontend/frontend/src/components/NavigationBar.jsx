import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import GlobalSearch from "./GlobalSearch.jsx";
import Icons from "./Icons.jsx";
import "./NavigationBar.css";
import Button from "./ui/Button.jsx";
import { useAuth } from "../hooks/useAuth";
import { canAccessWorkspace } from "../utils/workspace";

const isModeratorRole = (role) => role === "MOD" || role === "MODERATOR";
const ACCOUNT_PANEL_ID = "tl-app-nav-account-panel";

function NavigationBar() {
   const { user, logout } = useAuth();
   const [isOpen, setIsOpen] = useState(false);
   const dropdownRef = useRef(null);
   const accountTriggerRef = useRef(null);
   const location = useLocation();
   const navigate = useNavigate();

   useEffect(() => {
      function handleClickOutside(e) {
         if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
            setIsOpen(false);
         }
      }
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
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
   };
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
               <GlobalSearch key={`${location.pathname}${location.search}`} />
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
