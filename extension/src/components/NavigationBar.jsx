// NavigationBar.jsx
import "./NavigationBar.css";
import { Scissors, Upload, Link } from "lucide-react";

function NavigationBar({ activeLink, setActiveLink }) {
   return (
      <nav className="extension-navigation-bar">
         <div className="extension-nav-links">
            <button 
               className={`nav-tab ${activeLink === "snipping" ? "active" : ""}`}
               onClick={() => setActiveLink("snipping")}>
               <Scissors size={14} strokeWidth={2.5} /> Snip
            </button>
            <button 
               className={`nav-tab ${activeLink === "file-upload" ? "active" : ""}`}
               onClick={() => setActiveLink("file-upload")}>
               <Upload size={14} strokeWidth={2.5} /> Upload
            </button>
            <button 
               className={`nav-tab ${activeLink === "url-upload" ? "active" : ""}`}
               onClick={() => setActiveLink("url-upload")}>
               <Link size={14} strokeWidth={2.5} /> Scan URL
            </button>
         </div>
      </nav>
   );
}

export default NavigationBar;