import { useState } from "react";
import axios from "axios";
import "./UrlUpload.css";

const STATUS_CONFIG = {
  FACT: { bg: "#22c55e", label: "FACT" },
  FAKE: { bg: "#ef4444", label: "FAKE" },
  UNVERIFIED: { bg: "#f97316", label: "UNVERIFIED" },
  SATIRE: { bg: "#a855f7", label: "SATIRE" },
  OPINION: { bg: "#6b7280", label: "OPINION" },
};

function UrlUpload() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

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

  const statusInfo =
    result && result.verdict ? STATUS_CONFIG[result.verdict] : null;

  // console.log(result.status);
  console.log(statusInfo);

  console.log("Result:", result);

  return (
    <div className="url-page">
      <h1>URL Upload</h1>

      {/* Input */}
      <div className="input-row">
        <input
          className="url-input"
          type="text"
          placeholder="Paste a URL to verify..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleVerify()}
        />
        <button
          className="verify-btn"
          onClick={handleVerify}
          disabled={loading}
        >
          {loading ? "Checking..." : "Verify"}
        </button>
      </div>

      {/* Result */}
      {result && (
        <>
          {result.error ? (
            <p className="error-msg">{result.error}</p>
          ) : (
            <p className="success-msg">
              Verification complete! Check the result card on the page.
            </p>
          )}
        </>
      )}
    </div>
  );
}

export default UrlUpload;
