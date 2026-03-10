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
    setLoading(true);
    setResult(null);

    try {
      const res = await axios.post("http://localhost:8000/api/verify-url/", {
        url: url,
      });
      setResult(res.data);
    } catch (error) {
      setResult({ error: "Something went wrong. Please try again." });
    }

    setLoading(false);
  };

  const statusInfo =
    result && result.status ? STATUS_CONFIG[result.status] : null;

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
            <>
              <div className="status-row">
                <span className="this-post-is">This post is</span>
                {statusInfo && (
                  <span
                    className="status-badge"
                    style={{ backgroundColor: statusInfo.bg }}
                  >
                    {statusInfo.label}
                  </span>
                )}
              </div>

              <div className="summary-box">
                <p className="summary-title">Summary</p>
                <p className="summary-text">{result.explanation}</p>
              </div>

              <a
                className="source-btn"
                href={result.original_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                View source link
              </a>
            </>
          )}
        </>
      )}
    </div>
  );
}

export default UrlUpload;
