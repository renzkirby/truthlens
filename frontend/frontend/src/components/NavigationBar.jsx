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
               <span className="logo-text">TruthLens</span>
            </div>

            <div className="nav-tabs">
               <div className="nav-tab active">
                  <Icons name="globe" />
                  Community Feed
               </div>
               <div className="nav-tab">
                  <svg
                     width="18"
                     height="18"
                     viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     strokeWidth="2">
                     <rect
                        x="3"
                        y="3"
                        width="7"
                        height="7"
                     />
                     <rect
                        x="14"
                        y="3"
                        width="7"
                        height="7"
                     />
                     <rect
                        x="14"
                        y="14"
                        width="7"
                        height="7"
                     />
                     <rect
                        x="3"
                        y="14"
                        width="7"
                        height="7"
                     />
                  </svg>
                  Dashboard
               </div>
               <div className="nav-tab">
                  <svg
                     width="18"
                     height="18"
                     viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     strokeWidth="2">
                     <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                     <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                  </svg>
                  Notifications
               </div>
               <div className="nav-tab">
                  <svg
                     width="18"
                     height="18"
                     viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     strokeWidth="2">
                     <circle
                        cx="12"
                        cy="12"
                        r="3"
                     />
                     <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                  Settings
               </div>
            </div>
         </div>

         <div className="nav-right">
            <div className="user-profile-pill">
               <div className="user-icon-sm">
                  <svg
                     width="14"
                     height="14"
                     viewBox="0 0 24 24"
                     fill="none"
                     stroke="currentColor"
                     strokeWidth="2">
                     <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                     <circle
                        cx="12"
                        cy="7"
                        r="4"
                     />
                  </svg>
               </div>
               <span className="username">@RenzPogi</span>
               <span className="trust-score">82</span>
            </div>
         </div>
      </nav>
   );
}

export default NavigationBar;
