import "./SnippingTool.css";
import { Image, Scissors } from "lucide-react";

export default function SnippingTool({ handleSnipClick, isSnipping }) {
   return (
      <div className="snipping-page">
         <div className="page-intro">
            <span className="page-eyebrow">Verify Image</span>
            <h1>Check what you're seeing.</h1>
            <p>Select a suspicious image or claim on the page to start an investigation.</p>
         </div>
         <div className="snip-action-box">
            <div className="snip-icon-wrapper"><Image size={24} aria-hidden="true" /></div>
            <div>
               <div className="snip-title">Verify Image</div>
               <div className="snip-subtitle">Draw a box around the claim</div>
            </div>
         </div>
         <button type="button" className="primary-button" onClick={handleSnipClick} disabled={isSnipping}>
            <Scissors size={17} aria-hidden="true" />
            {isSnipping ? "Snipping..." : "Start Snipping"}
         </button>
      </div>
   );
}
