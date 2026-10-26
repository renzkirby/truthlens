import { useCallback, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import LogoImage from "../../assets/truthlens_logo.png";
import { useAuth } from "../../hooks/useAuth";
import {
   canAccessManagementConsole,
   isPlatformSafetyModerator,
} from "../../utils/management";
import Icons from "../Icons";
import Button from "../ui/Button";

import "./ManagementConsole.css";

const NAVIGATION_ITEMS = [
   { to: "/management", label: "Overview", icon: "dashboard", end: true, access: "admin" },
   { to: "/management/pipeline", label: "Pipeline Health", icon: "activity", section: "Operations", access: "admin" },
   { to: "/management/safety", label: "Safety Review", icon: "shield-check", section: "Platform Safety", access: "safety", end: true },
   { to: "/management/safety/audit", label: "Safety Audit", icon: "activity", access: "safety" },
   { to: "/management/organizations", label: "Organizations", icon: "landmark", section: "Governance", access: "admin" },
   { to: "/management/memberships", label: "Memberships", icon: "users", access: "admin" },
   { to: "/management/invitations", label: "Invitations", icon: "mail", access: "admin" },
   { to: "/management/audit", label: "Governance Audit", icon: "shield-check", access: "admin" },
];

const MOBILE_NAVIGATION_ID = "management-mobile-navigation";

function ManagementNavigation({ label, onNavigate, firstLinkRef, items }) {
   return (
      <>
         <nav aria-label={label}>
            {items.map((item, index) => (
               <div key={item.to} className={item.section ? "management-shell__nav-section" : ""}>
                  {item.section ? <span className="management-shell__nav-label">{item.section}</span> : null}
                  <NavLink
                     ref={index === 0 ? firstLinkRef : undefined}
                     to={item.to}
                     end={item.end}
                     className={({ isActive }) =>
                        `management-shell__nav-link ${isActive ? "active" : ""}`
                     }
                     onClick={onNavigate}
                  >
                     <Icons name={item.icon} size={18} />
                     {item.label}
                  </NavLink>
               </div>
            ))}
         </nav>
         <Link className="management-shell__back" to="/community" onClick={onNavigate}>
            <Icons name="globe" size={17} />
            View Community
         </Link>
      </>
   );
}

function ManagementConsoleShell() {
   const { user, logout } = useAuth();
   const navigate = useNavigate();
   const isPlatformAdmin = canAccessManagementConsole(user);
   const isSafetyModerator = isPlatformSafetyModerator(user);
   const navigationItems = NAVIGATION_ITEMS.filter((item) =>
      isPlatformAdmin ? true : item.access === "safety",
   );
   const homePath = isPlatformAdmin ? "/management" : "/management/safety";
   const explicitLogoutRef = useRef(false);
   const menuTriggerRef = useRef(null);
   const mobileDrawerRef = useRef(null);
   const firstMobileLinkRef = useRef(null);
   const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

   const closeMobileNavigation = useCallback(() => {
      setMobileNavigationOpen(false);
      window.requestAnimationFrame(() => menuTriggerRef.current?.focus());
   }, []);

   useEffect(() => () => {
      if (explicitLogoutRef.current) logout();
   }, [logout]);

   useEffect(() => {
      if (!mobileNavigationOpen) return undefined;

      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      window.requestAnimationFrame(() => firstMobileLinkRef.current?.focus());

      const handleDrawerKeyDown = (event) => {
         if (event.key === "Escape") {
            event.preventDefault();
            closeMobileNavigation();
            return;
         }

         if (event.key !== "Tab") return;

         const focusableElements = mobileDrawerRef.current?.querySelectorAll(
            'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
         );
         if (!focusableElements?.length) return;

         const firstElement = focusableElements[0];
         const lastElement = focusableElements[focusableElements.length - 1];

         if (event.shiftKey && document.activeElement === firstElement) {
            event.preventDefault();
            lastElement.focus();
         } else if (!event.shiftKey && document.activeElement === lastElement) {
            event.preventDefault();
            firstElement.focus();
         }
      };

      document.addEventListener("keydown", handleDrawerKeyDown);
      return () => {
         document.body.style.overflow = previousOverflow;
         document.removeEventListener("keydown", handleDrawerKeyDown);
      };
   }, [closeMobileNavigation, mobileNavigationOpen]);

   useEffect(() => {
      const desktopQuery = window.matchMedia("(min-width: 801px)");
      const closeAtDesktopWidth = (event) => {
         if (event.matches) setMobileNavigationOpen(false);
      };

      desktopQuery.addEventListener("change", closeAtDesktopWidth);
      return () => desktopQuery.removeEventListener("change", closeAtDesktopWidth);
   }, []);

   const handleLogout = () => {
      explicitLogoutRef.current = true;
      navigate("/login", { replace: true, state: null });
   };

   return (
      <div className="management-shell">
         <header className="management-shell__header">
            <Link className="management-shell__brand" to={homePath}>
               <img src={LogoImage} alt="" />
               <span>
                  <strong>TruthLens</strong>
                  <small>{isSafetyModerator && !isPlatformAdmin ? "Platform Safety Console" : "Management Console"}</small>
               </span>
            </Link>
            <div className="management-shell__account">
               <button
                  ref={menuTriggerRef}
                  type="button"
                  className="management-shell__menu-trigger"
                  aria-label="Open Management Console navigation"
                  aria-expanded={mobileNavigationOpen}
                  aria-controls={MOBILE_NAVIGATION_ID}
                  onClick={() => setMobileNavigationOpen(true)}
               >
                  <Icons name="panel-left" size={19} />
                  <span>Menu</span>
               </button>
               <span className="management-shell__username">@{user?.username}</span>
               <Button
                  variant="ghost"
                  density="compact"
                  leadingIcon={<Icons name="logout" />}
                  className="management-shell__logout"
                  aria-label="Log out"
                  onClick={handleLogout}
               >
                  Log out
               </Button>
            </div>
         </header>

         <div className="management-shell__body">
            <aside className="management-shell__sidebar management-shell__sidebar--desktop">
               <ManagementNavigation label="Management Console" items={navigationItems} />
            </aside>

            <main className="management-shell__main" id="management-main">
               <Outlet />
            </main>
         </div>

         {mobileNavigationOpen ? (
            <div className="management-mobile-navigation">
               <button
                  type="button"
                  className="management-mobile-navigation__backdrop"
                  aria-label="Close Management Console navigation"
                  tabIndex={-1}
                  onClick={closeMobileNavigation}
               />
               <aside
                  ref={mobileDrawerRef}
                  id={MOBILE_NAVIGATION_ID}
                  className="management-mobile-navigation__drawer"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="management-mobile-navigation-title"
               >
                  <div className="management-mobile-navigation__header">
                     <strong id="management-mobile-navigation-title">Navigation</strong>
                     <button
                        type="button"
                        className="management-mobile-navigation__close"
                        aria-label="Close Management Console navigation"
                        onClick={closeMobileNavigation}
                     >
                        <Icons name="x" size={20} />
                     </button>
                  </div>
                  <ManagementNavigation
                     label="Management Console mobile navigation"
                     onNavigate={closeMobileNavigation}
                     firstLinkRef={firstMobileLinkRef}
                     items={navigationItems}
                  />
               </aside>
            </div>
         ) : null}
      </div>
   );
}

export default ManagementConsoleShell;
