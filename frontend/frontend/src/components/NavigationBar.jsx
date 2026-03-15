import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "./Icons.jsx";
import "./NavigationBar.css";
import { useAuth } from "../context/AuthContext.jsx";

function NavigationBar() {
   const { user, logout } = useAuth();
   const [isOpen, setIsOpen] = useState(false);
   const dropdownRef = useRef(null);
   const location = useLocation();

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
      function handleEscape(e) {
         if (e.key === "Escape") setIsOpen(false);
      }
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
   }, []);

   useEffect(() => {
      setIsOpen(false);
   }, [location.pathname]);

   function trustColor(score) {
      if (score >= 75) return "#0e9f6e";
      if (score >= 45) return "#d97706";
      return "#e02424";
   }
   const color = trustColor(user?.trust_score ?? 0);

   return (
      <nav className="top-navbar">
         <div className="nav-left">
            <div className="logo-section">
               <img
                  src={LogoImage}
                  alt="TruthLens Logo"
                  style={{ height: "40px", width: "auto" }}
               />
               <Link
                  to="/landing-page"
                  className="link">
                  <span className="logo-text">TruthLens</span>
               </Link>
            </div>

            <div className="nav-tabs">
               <Link
                  to="/community"
                  className="link">
                  <div className={`nav-tab ${location.pathname === "/community" ? "active" : ""}`}>
                     <Icons name="globe" />
                     Community Feed
                  </div>
               </Link>
               <Link
                  to="/dashboard"
                  className="link">
                  <div className={`nav-tab ${location.pathname === "/dashboard" ? "active" : ""}`}>
                     <Icons name="dashboard" />
                     Dashboard
                  </div>
               </Link>
               <Link
                  to="/notifications"
                  className="link">
                  <div
                     className={`nav-tab ${location.pathname === "/notifications" ? "active" : ""}`}>
                     <Icons name="bell" />
                     Notifications
                  </div>
               </Link>
            </div>
         </div>

         <div className="nav-right">
            <div
               className="user-menu-container"
               ref={dropdownRef}>
               <button
                  className={`user-profile-pill ${isOpen ? "open" : ""}`}
                  onClick={() => setIsOpen((v) => !v)}
                  aria-haspopup="menu"
                  aria-expanded={isOpen}>
                  <div className="user-icon-sm">
                     <Icons name="user" />
                  </div>
                  <span className="username">@{user?.username}</span>
                  <span
                     className="trust-score"
                     style={{ color, borderColor: `${color}55`, background: `${color}20` }}>
                     {user?.trust_score}
                  </span>
                  <span className={`chevron ${isOpen ? "rotated" : ""}`}>
                     <Icons name="chevron-down" />
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
                           to={`/u/${user?.username}`}
                           className="link"
                           role="menuitem">
                           <button
                              className="dropdown-item"
                              onClick={() => setIsOpen(false)}>
                              <Icons name="user" />
                              My Public Profile
                           </button>
                        </Link>
                        <Link
                           to="/dashboard"
                           className="link"
                           role="menuitem">
                           <button
                              className="dropdown-item"
                              onClick={() => setIsOpen(false)}>
                              <Icons name="dashboard" />
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
                           }}>
                           <Icons name="logout" />
                           Log Out
                        </button>
                     </div>
                  </div>
               )}
            </div>
         </div>
      </nav>
   );
}

export default NavigationBar;
