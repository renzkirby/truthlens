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
            <div className="snip-title">Verify Image</div>
            <div className="snip-subtitle">Draw a box around the claim</div>
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
