// UrlUpload.jsx
import { useState } from "react";
import "./UrlUpload.css";
import { Link as LinkIcon, ScanLine, Lightbulb } from "lucide-react";

function UrlUpload() {
   const [url, setUrl] = useState("");

   const handleVerify = async () => {
      if (!url) return;

      try {
         const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true,
         });

         // Tell background.js to handle the verification
         chrome.runtime.sendMessage({
            type: "VERIFY_URL",
            url: url,
            tabId: tab.id,
         });

         // Show loading card and close popup
         chrome.tabs.sendMessage(tab.id, {
            type: "DISPLAY_URL_LOADING",
         });

         window.close();
      } catch (error) {
         console.error("Error:", error);
      }
   };

   return (
      <div className="url-page">
         {/* Label */}
         <p className="url-page-label">Paste article or claim URL</p>

         {/* Input row */}
         <div className="url-input-row">
            <div className="url-input-wrap">
               <LinkIcon
                  size={13}
                  color="#9ca3af"
                  strokeWidth={2}
                  className="url-input-icon"
               />
               <input
                  className="url-input"
                  type="text"
                  placeholder="https://example.com/article…"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleVerify()}
               />
            </div>
            <button
               className="url-scan-btn"
               onClick={handleVerify}>
               <ScanLine
                  size={13}
                  strokeWidth={2.5}
               />
               Scan
            </button>
         </div>

         {/* Tip box */}
         <div className="url-tip-box">
            <Lightbulb
               size={12}
               color="#d97706"
               className="url-tip-icon"
            />
            <span>
               TruthLens will extract and analyze the main claims from this URL automatically.
            </span>
         </div>

      </div>
   );
}

export default UrlUpload;
