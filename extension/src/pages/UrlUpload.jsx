// UrlUpload.jsx
import { useState } from "react";
import "./UrlUpload.css";
import { Link as LinkIcon, ScanLine, Lightbulb } from "lucide-react";

function UrlUpload() {
   const [url, setUrl] = useState("");
   const [error, setError] = useState("");

   const handleVerify = async () => {
      if (!url) return;

      setError("");

      try {
         const [tab] = await chrome.tabs.query({
            active: true,
            currentWindow: true,
         });

         if (
            !tab ||
            !Number.isInteger(tab.id) ||
            tab.url?.startsWith("chrome://") ||
            tab.url?.startsWith("edge://") ||
            tab.url?.startsWith("about:")
         ) {
            setError("Open a normal webpage first so TruthLens has somewhere to display the result.");
            return;
         }

         chrome.runtime.sendMessage(
            {
               type: "VERIFY_URL",
               url: url.trim(),
               tabId: tab.id,
            },
            (response) => {
               if (chrome.runtime.lastError || !response?.accepted) {
                  setError(
                     response?.error ||
                        "TruthLens could not start the URL verification. Reload the extension and try again.",
                  );
                  return;
               }

               chrome.tabs.sendMessage(tab.id, {
                  type: "DISPLAY_URL_LOADING",
               });
               window.close();
            },
         );
      } catch (submissionError) {
         console.error("URL verification startup failed:", submissionError);
         setError("TruthLens could not start the URL verification. Reload the extension and try again.");
      }
   };

   return (
      <div className="url-page">
         <div className="page-intro">
            <span className="page-eyebrow">Analyze URL</span>
            <h1>Check an article or webpage.</h1>
         </div>
         <label htmlFor="claim-url" className="url-page-label">Article or claim URL</label>

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
                  id="claim-url"
                  className="url-input"
                  type="text"
                  placeholder="https://example.com/article…"
                  value={url}
                  onChange={(e) => {
                     setUrl(e.target.value);
                     if (error) setError("");
                  }}
                  onKeyDown={(e) => e.key === "Enter" && handleVerify()}
               />
            </div>
            <button
               type="button"
               className="primary-button"
               disabled={!url}
               onClick={handleVerify}>
               <ScanLine
                  size={13}
                  strokeWidth={2.5}
               />
               Analyze URL
            </button>
         </div>

         {error && (
            <p className="url-page-error" role="alert">
               {error}
            </p>
         )}

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
