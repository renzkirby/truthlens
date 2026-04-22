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
               <Scissors size={12} strokeWidth={2.5} /> Verify Image
            </button>
            <button 
               className={`nav-tab ${activeLink === "url-upload" ? "active" : ""}`}
               onClick={() => setActiveLink("url-upload")}>
               <Link size={12} strokeWidth={2.5} /> Analyze URL
            </button>
            <button 
               className={`nav-tab ${activeLink === "detect-deepfake" ? "active" : ""}`}
               onClick={() => setActiveLink("detect-deepfake")}>
               <Link size={12} strokeWidth={2.5} /> Detect Deepfake
            </button>
            <button 
               className={`nav-tab ${activeLink === "file-upload" ? "active" : ""}`}
               onClick={() => setActiveLink("file-upload")}>
               <Upload size={12} strokeWidth={2.5} /> Upload File
            </button>
         </div>
      </nav>
   );
}

export default NavigationBar;