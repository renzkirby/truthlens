import { Scissors, Sparkles } from "lucide-react";
import "./SnippingTool.css";
import "./DetectDeepfake.css";

export default function DetectDeepfake({ handleDeepfakeSnipClick, isSnipping }) {
   return (
      <div className="snipping-page deepfake-page">
         <div className="page-intro">
            <span className="page-eyebrow">Deepfake Detection</span>
            <h1>Take a closer look.</h1>
            <p>Check an image for signs of AI generation.</p>
         </div>
         <div className="snip-action-box">
            <div className="snip-icon-wrapper"><Sparkles size={24} aria-hidden="true" /></div>
            <div>
               <div className="snip-title">AI Forensics Scanner</div>
               <div className="snip-subtitle">Draw a box around an image to analyze it</div>
            </div>
         </div>
         <button type="button" className="primary-button" onClick={handleDeepfakeSnipClick} disabled={isSnipping}>
            <Scissors size={17} aria-hidden="true" />
            {isSnipping ? "Snipping..." : "Scan for Deepfake"}
         </button>
      </div>
   );
}
