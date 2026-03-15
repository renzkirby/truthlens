import { Link } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "./Icons.jsx";
import "./NavigationBar.css";

function NavigationBar() {
   return (
      <nav className="top-navbar">
         <div className="nav-left">
            <div className="logo-section">
               <div className="logo-section">
                  <img
                     src={LogoImage}
                     alt="TruthLens Logo"
                     style={{ height: "40px", width: "auto" }}
                  />
               </div>
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
                  <div className="nav-tab active">
                     <Icons name="globe" />
                     Community Feed
                  </div>
               </Link>
               <Link
                  to="/dashboard"
                  className="link">
                  <div className="nav-tab">
                     <Icons name="dashboard" />
                     Dashboard
                  </div>
               </Link>
               <Link
                  to="/notifications"
                  className="link">
                  <div className="nav-tab">
                     <Icons name="bell" />
                     Notifications
                  </div>
               </Link>
               <Link
                  to="/settings"
                  className="link">
                  <div className="nav-tab">
                     <Icons name="settings" />
                     Settings
                  </div>
               </Link>
            </div>
         </div>

         <div className="nav-right">
            <div className="user-profile-pill">
               <div className="user-icon-sm">
                  <Icons name="user" />
               </div>
               <span className="username">@RenzPogi</span>
               <span className="trust-score">82</span>
            </div>
         </div>
      </nav>
   );
}

export default NavigationBar;
