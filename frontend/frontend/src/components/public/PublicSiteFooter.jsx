import { Link, useLocation } from "react-router-dom";
import LogoImage from "../../assets/truthlens_logo.png";
import "./PublicSiteFooter.css";

function PublicSiteFooter() {
   const { pathname } = useLocation();
   const isLandingPage = pathname === "/landing-page";
   const sectionHref = (sectionId) =>
      isLandingPage ? `#${sectionId}` : `/landing-page#${sectionId}`;

   return (
      <footer className="public-site-footer">
         <div className="public-site-footer__container">
            <div className="public-site-footer__main">
               <div className="public-site-footer__brand">
                  <Link
                     to="/landing-page"
                     className="public-site-footer__brand-link"
                     aria-label="TruthLens home"
                  >
                     <img src={LogoImage} alt="" className="public-site-footer__logo" />

                     <span className="public-site-footer__brand-name">TruthLens</span>
                  </Link>

                  <p className="public-site-footer__description">
                     AI-assisted verification built to help you investigate questionable content, examine supporting
                     evidence, and make better-informed decisions online.
                  </p>
               </div>

               <div className="public-site-footer__nav">
                  <div className="public-site-footer__nav-group">
                     <h3>Explore</h3>

                     <a href={sectionHref("features")}>Features</a>

                     <a href={sectionHref("how-it-works")}>How it works</a>

                     <a href={sectionHref("trust")}>Trust &amp; Transparency</a>

                     <Link to="/partners">Public partners</Link>

                     <a href={sectionHref("about")}>About</a>
                  </div>

                  <div className="public-site-footer__nav-group">
                     <h3>TruthLens</h3>

                     <a
                        href="https://chromewebstore.google.com/detail/truthlens/dhkeknpnigghagekhdcpknbggfpbmkgo"
                        target="_blank"
                        rel="noopener noreferrer"
                     >
                        Chrome Extension
                     </a>

                     <Link to="/community">Community</Link>

                     <Link to="/login">Login</Link>

                     <Link to="/register">Create an account</Link>
                  </div>
               </div>
            </div>

            <div className="public-site-footer__bottom">
               <span>© {new Date().getFullYear()} TruthLens. Investigate before you amplify.</span>

               <span className="public-site-footer__status">
                  AI-assisted verification • Evidence-aware results
               </span>
            </div>
         </div>
      </footer>
   );
}

export default PublicSiteFooter;
