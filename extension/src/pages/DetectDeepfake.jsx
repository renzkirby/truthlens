// src/pages/DetectDeepfake.jsx
import { Crosshair, Sparkles } from "lucide-react";

function DetectDeepfake({ handleDeepfakeSnipClick, isSnipping }) {
   return (
      <div className="snipping-page">
         <div className="snip-action-box">
            <div className="snip-icon-wrapper" style={{ background: "#7c3aed" }}>
               <Sparkles size={22} color="#fff" strokeWidth={2} />
            </div>
            <div className="snip-title" style={{ color: "#5b21b6" }}>AI Forensics Scanner</div>
            <div className="snip-subtitle">Draw a box around an image to detect AI generation</div>
         </div>

         <button
            className="snip-btn"
            style={{ background: "#7c3aed" }}
            onClick={handleDeepfakeSnipClick}
            disabled={isSnipping}>
            {isSnipping ? "Snipping..." : "Scan for Deepfake"}
         </button>
      </div>
   );
}

export default DetectDeepfake;