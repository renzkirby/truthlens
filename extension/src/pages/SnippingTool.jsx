// SnippingTool.jsx
import "./SnippingTool.css";
import { Crosshair } from "lucide-react";

function SnippingTool({ handleSnipClick, isSnipping }) {
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
