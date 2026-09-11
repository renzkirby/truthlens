import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../../hooks/useAuth";
import LogoImage from "../../assets/truthlens_logo.png";
import "./PublicSiteHeader.css";

function PublicSiteHeader() {
   const { pathname } = useLocation();
   const { user } = useAuth();
   const [isMenuOpen, setIsMenuOpen] = useState(false);
   const menuToggleRef = useRef(null);
   const isLandingPage = pathname === "/landing-page";
   const isPartnerRoute = pathname === "/partners" || pathname.startsWith("/partners/");
   const featuresHref = isLandingPage ? "#features" : "/landing-page#features";
   const aboutHref = isLandingPage ? "#about" : "/landing-page#about";

   const closeMenu = () => setIsMenuOpen(false);

   useEffect(() => {
      if (!isMenuOpen) return undefined;

      const handleEscape = (event) => {
         if (event.key !== "Escape") return;

         setIsMenuOpen(false);
         menuToggleRef.current?.focus();
      };

      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
   }, [isMenuOpen]);

   return (
      <header className="public-site-header">
         <a className="public-site-skip-link" href="#main-content">
            Skip to main content
         </a>
         <nav className="public-site-header__inner" aria-label="Public navigation">
            <Link
               to="/landing-page"
               className="public-site-header__brand"
               aria-label="TruthLens home"
               aria-current={isLandingPage ? "page" : undefined}
               onClick={closeMenu}
            >
               <img src={LogoImage} alt="" className="public-site-header__logo" />
               <span className="public-site-header__brand-name">TruthLens</span>
            </Link>

            <div className="public-site-header__links">
               <a href={featuresHref}>Features</a>
               <a href={aboutHref}>About</a>
               <Link to="/partners" aria-current={isPartnerRoute ? "page" : undefined}>
                  Partners
               </Link>
            </div>

            <div className="public-site-header__actions">
               {user ? (
                  <Link to="/community" className="public-site-header__primary-action">
                     Open TruthLens
                  </Link>
               ) : (
                  <>
                     <Link to="/login" className="public-site-header__secondary-action">
                        Login
                     </Link>
                     <Link to="/register" className="public-site-header__primary-action">
                        Get Started
                     </Link>
                  </>
               )}
            </div>

            <button
               ref={menuToggleRef}
               type="button"
               className={`public-site-header__menu-toggle${isMenuOpen ? " is-open" : ""}`}
               aria-label={isMenuOpen ? "Close navigation menu" : "Open navigation menu"}
               aria-expanded={isMenuOpen}
               aria-controls="public-site-mobile-navigation"
               onClick={() => setIsMenuOpen((isOpen) => !isOpen)}
            >
               <span />
               <span />
               <span />
            </button>

            <div
               id="public-site-mobile-navigation"
               className={`public-site-header__mobile-navigation${isMenuOpen ? " is-open" : ""}`}
            >
               <a href={featuresHref} onClick={closeMenu}>
                  Features
               </a>
               <a href={aboutHref} onClick={closeMenu}>
                  About
               </a>
               <Link
                  to="/partners"
                  aria-current={isPartnerRoute ? "page" : undefined}
                  onClick={closeMenu}
               >
                  Partners
               </Link>

               <div className="public-site-header__mobile-actions">
                  {user ? (
                     <Link to="/community" className="public-site-header__primary-action" onClick={closeMenu}>
                        Open TruthLens
                     </Link>
                  ) : (
                     <>
                        <Link to="/login" className="public-site-header__secondary-action" onClick={closeMenu}>
                           Login
                        </Link>
                        <Link to="/register" className="public-site-header__primary-action" onClick={closeMenu}>
                           Get Started
                        </Link>
                     </>
                  )}
               </div>
            </div>
         </nav>
      </header>
   );
}

export default PublicSiteHeader;
