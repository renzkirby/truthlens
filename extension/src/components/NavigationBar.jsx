// NavigationBar.jsx
import "./NavigationBar.css";
import { Scissors, Upload, Link, Sparkles } from "lucide-react";

function NavigationBar({ activeLink, setActiveLink }) {
   return (
      <nav className="extension-navigation-bar">
         <div className="extension-nav-links">
            <button 
               className={`nav-tab ${activeLink === "snipping" ? "active" : ""}`}
               onClick={() => setActiveLink("snipping")}
               title="Verify Image (Snip)" // Tooltip added
            >
               <Scissors size={18} strokeWidth={2} />
               <span className="nav-label">Snip</span>
            </button>
            <button 
               className={`nav-tab ${activeLink === "url-upload" ? "active" : ""}`}
               onClick={() => setActiveLink("url-upload")}
               title="Analyze URL"
            >
               <Link size={18} strokeWidth={2} />
               <span className="nav-label">URL</span>
            </button>
            <button 
               className={`nav-tab ${activeLink === "detect-deepfake" ? "active" : ""}`}
               onClick={() => setActiveLink("detect-deepfake")}
               title="Detect Deepfake"
            >
               <Sparkles size={18} strokeWidth={2} />
               <span className="nav-label">AI Scan</span>
            </button>
            <button 
               className={`nav-tab ${activeLink === "file-upload" ? "active" : ""}`}
               onClick={() => setActiveLink("file-upload")}
               title="Upload File"
            >
               <Upload size={18} strokeWidth={2} />
               <span className="nav-label">File</span>
            </button>
         </div>
      </nav>
   );
}

export default NavigationBar;