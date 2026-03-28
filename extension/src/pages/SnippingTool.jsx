// SnippingTool.jsx
import "./SnippingTool.css";
import { Crosshair, Sparkles } from "lucide-react";

function SnippingTool({ handleSnipClick, isSnipping, onToggleDeepfake, checkDeepfake }) {
   return (
      <div className="snipping-page">
         <div className="snip-action-box">
            <div className="snip-icon-wrapper">
               <Crosshair
                  size={22}
                  color="var(--brand-primary)"
                  strokeWidth={2}
               />
            </div>
            <div className="snip-title">Activate Screen Snip</div>
            <div className="snip-subtitle">Draw a box around the claim</div>
         </div>

         {/* DEEPFAKE DETECT SWITCH */}
         <div className="deepfake-toggle-container">
            <div className="toggle-label-group">
               <Sparkles size={14} color="var(--brand-primary)" />
               <div className="toggle-text">
                  <span className="toggle-title">Detect AI Generated Image</span>
                  <span className="toggle-desc">Slightly increases verification time</span>
               </div>
            </div>
            <label className="switch">
               <input
                  type="checkbox"
                  checked={checkDeepfake}
                  onChange={(e) => onToggleDeepfake(e.target.checked)}
                  disabled={isSnipping}
               />
               <span className="slider round"></span>
            </label>
         </div>


         <button
            className="snip-btn"
            onClick={handleSnipClick}
            disabled={isSnipping}>
            {isSnipping ? "Snipping..." : "Start Snipping"}
         </button>
      </div>
   );
}

export default SnippingTool;
