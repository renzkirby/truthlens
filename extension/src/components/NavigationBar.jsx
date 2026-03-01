import "./NavigationBar.css";
import { useState } from "react";

function NavigationBar({ activeLink, setActiveLink }) {
   const handleLinkClick = (link) => {
      setActiveLink(link);
   };
   return (
      <nav className="extension-navigation-bar">
         <div className="extension-nav-links">
            <a
               href="#"
               className={`extension-nav-link ${activeLink === "snipping" ? "active" : ""}`}
               onClick={() => handleLinkClick("snipping")}>
               Snipping Tool
            </a>
            <a
               href="#"
               className={`extension-nav-link ${activeLink === "file-upload" ? "active" : ""}`}
               onClick={() => handleLinkClick("file-upload")}>
               File Upload
            </a>
            <a
               href="#"
               className={`extension-nav-link ${activeLink === "url-upload" ? "active" : ""}`}
               onClick={() => handleLinkClick("url-upload")}>
               Url Upload
            </a>
         </div>
      </nav>
   );
}

export default NavigationBar;
