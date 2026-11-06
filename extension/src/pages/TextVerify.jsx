import { useState } from "react";
import { FileText, ScanLine } from "lucide-react";
import { shouldSubmitTextVerifyOnKeyDown } from "./textVerifyKeyboard.js";
import "./TextVerify.css";

function TextVerify() {
   const [text, setText] = useState("");
   const [error, setError] = useState("");
   const [isAnalyzing, setIsAnalyzing] = useState(false);

   const handleVerify = async () => {
      const claimText = text.trim();
      if (!claimText || isAnalyzing) return;

      setIsAnalyzing(true);
      setError("");

      try {
         const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

         if (
            !tab ||
            !Number.isInteger(tab.id) ||
            tab.url?.startsWith("chrome://") ||
            tab.url?.startsWith("edge://") ||
            tab.url?.startsWith("about:")
         ) {
            setError("Open a normal webpage first so TruthLens has somewhere to display the result.");
            setIsAnalyzing(false);
            return;
         }

         chrome.tabs.sendMessage(tab.id, {
            type: "DISPLAY_URL_LOADING",
            customMsg: "Analyzing the submitted text claim...",
         });

         chrome.runtime.sendMessage(
            {
               type: "VERIFY_TEXT",
               tabId: tab.id,
               text: claimText,
            },
            (response) => {
               if (chrome.runtime.lastError || !response?.accepted) {
                  chrome.tabs.sendMessage(tab.id, {
                     type: "DISPLAY_TEXT_ERROR",
                     message:
                        response?.error ||
                        "TruthLens could not start the text verification. Reload the extension and try again.",
                     kind: response?.error ? "input" : "service",
                  });
               }
               window.close();
            },
         );
      } catch (submissionError) {
         console.error("Text verification failed:", submissionError);
         setError("TruthLens could not start this verification. Reload the extension and try again.");
         setIsAnalyzing(false);
      }
   };

   return (
      <div className="text-verify-page">
         <div className="page-intro">
            <span className="page-eyebrow">Verify Text</span>
            <h1>Check a written claim.</h1>
            <p>Paste a factual statement or short passage for evidence-based verification.</p>
         </div>

         <label htmlFor="truthlens-text-claim" className="text-verify-label">
            Claim or passage
         </label>
         <div className="text-verify-input-wrap">
            <FileText size={15} className="text-verify-input-icon" aria-hidden="true" />
            <textarea
               id="truthlens-text-claim"
               value={text}
               onChange={(event) => {
                  setText(event.target.value);
                  if (error) setError("");
               }}
               onKeyDown={(event) => {
                  if (!shouldSubmitTextVerifyOnKeyDown(event)) return;

                  event.preventDefault();
                  handleVerify();
               }}
               placeholder="Paste the claim you want TruthLens to investigate…"
               rows={6}
               aria-describedby="truthlens-text-help"
            />
         </div>

         <p id="truthlens-text-help" className="text-verify-help">
            Be specific enough that the claim can be checked against public evidence. Press Enter to verify, or Shift + Enter for a new line.
         </p>

         {error && (
            <p className="text-verify-error" role="alert">
               {error}
            </p>
         )}

         <button
            type="button"
            className="primary-button"
            disabled={!text.trim() || isAnalyzing}
            onClick={handleVerify}
         >
            <ScanLine size={15} aria-hidden="true" />
            {isAnalyzing ? "Analyzing..." : "Verify Text"}
         </button>
      </div>
   );
}

export default TextVerify;
