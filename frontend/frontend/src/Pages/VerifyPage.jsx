import { useState, useRef } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";
import "./VerifyPage.css";

const VERDICT_CONFIG = {
   FACT:         { color: "var(--verdict-fact-text)",        bg: "var(--verdict-fact-bg)",        label: "FACT" },
   FAKE:         { color: "var(--verdict-fake-text)",        bg: "var(--verdict-fake-bg)",        label: "FAKE" },
   UNVERIFIED:   { color: "var(--verdict-unverified-text)",  bg: "var(--verdict-unverified-bg)",  label: "UNVERIFIED" },
   SATIRE:       { color: "var(--verdict-satire-text)",      bg: "var(--verdict-satire-bg)",      label: "SATIRE" },
   OUT_OF_SCOPE: { color: "var(--verdict-unverified-text)",  bg: "var(--verdict-unverified-bg)",  label: "OUT OF SCOPE" },
};

// ── Result Card component ─────────────────────────────────────────────────────
function ResultCard({ result, onEscalate }) {
   const config = VERDICT_CONFIG[result.verdict] || VERDICT_CONFIG.UNVERIFIED;

   const confidenceColor =
    result.confidence_score >= 70 ? "var(--verdict-fact-border)"
    : result.confidence_score >= 40 ? "var(--verdict-misleading-border)"
    : "var(--verdict-fake-border)";

   const showEscalate =
      result.verdict === "UNVERIFIED" || result.confidence_score < 50;

   return (
      <div className="result-card">
         <div className="result-verdict-row">
            <span className="result-label">This content is</span>
            <span
               className="result-badge"
               style={{ color: config.color, backgroundColor: config.bg }}
            >
               {config.label}
            </span>
         </div>

         <div className="result-summary-box">
            <p className="result-summary-title">AI Summary</p>
            <p className="result-summary-text">{result.summary}</p>
         </div>

         <div className="result-confidence-label">
            Confidence Score: <strong>{result.confidence_score}%</strong>
         </div>
         <div className="result-confidence-track">
            <div
               className="result-confidence-fill"
               style={{
                  width: `${result.confidence_score}%`,
                  backgroundColor: confidenceColor,
               }}
            />
         </div>

         <div className="result-footer">
            <span className="result-source-type">
               <Icons name="info" size={13} />
               {result.source_type}
            </span>
            {result.source_url && !showEscalate && (
               <a
                  href={result.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="result-source-link"
               >
                  <Icons name="external-link" size={13} /> View Source
               </a>
            )}
         </div>

         {showEscalate && result.id && (
            <button className="escalate-btn" onClick={onEscalate}>
               <Icons name="flag" size={14} />
               Ask the Community
            </button>
         )}
      </div>
   );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
function VerifyPage() {
   const { authFetch }                         = useAuth();
   const navigate                              = useNavigate();
   const fileInputRef                          = useRef(null);

   const [activeTab, setActiveTab]             = useState("url");
   const [url, setUrl]                         = useState("");
   const [image, setImage]                     = useState(null);
   const [imagePreview, setImagePreview]       = useState(null);
   const [loading, setLoading]                 = useState(false);
   const [result, setResult]                   = useState(null);
   const [error, setError]                     = useState(null);

   const pollForResult = (claimId) => {
      let pollCount = 0;
      const maxPolls = 20; 

      const interval = setInterval(async () => {
         pollCount++;

         if (pollCount > maxPolls) {
            clearInterval(interval);
            setError("Verification timed out. Please try again.");
            setLoading(false);
            return;
         }

         try {
            const data = await authFetch(
               `http://localhost:8000/api/claims/${claimId}/status`
            );

            if (data.verdict !== "PENDING") {
               clearInterval(interval);
               setResult(data);
               setLoading(false);
            }
         } catch (err) {
            clearInterval(interval);
            setError("Failed to retrieve result. Please try again.");
            setLoading(false);
         }
      }, 3000);
   };

   // ── URL verification handler ──────────────────────────────────────────────
   const handleUrlVerify = async () => {
      if (!url.trim()) return;
      setLoading(true);
      setResult(null);
      setError(null);

      try {
         const data = await authFetch("http://localhost:8000/api/verify-url/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
         });
         pollForResult(data.claim_id);
      } catch (err) {
         setError("Failed to submit URL. Please try again.");
         setLoading(false);
      }
   };

   // ── Image selection handler ───────────────────────────────────────────────
   const handleImageSelect = (e) => {
      const file = e.target.files[0];
      if (!file) return;
      setImage(file);
      setImagePreview(URL.createObjectURL(file));
      setResult(null);
      setError(null);
   };

   // ── Drag and drop handlers ────────────────────────────────────────────────
   const handleDrop = (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (!file || !file.type.startsWith("image/")) return;
      setImage(file);
      setImagePreview(URL.createObjectURL(file));
      setResult(null);
      setError(null);
   };

   // ── Image verification handler ────────────────────────────────────────────
   const handleImageVerify = async () => {
      if (!image) return;
      setLoading(true);
      setResult(null);
      setError(null);

      try {
         const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(image);
         });

         const data = await authFetch("http://localhost:8000/api/analyze/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_data: base64 }),
         });

         pollForResult(data.claim_id);
      } catch (err) {
         setError("Failed to submit image. Please try again.");
         setLoading(false);
      }
   };

   // ── Tab switch handler ────────────────────────────────────────────────────
   const handleTabSwitch = (tab) => {
      setActiveTab(tab);
      setResult(null);
      setError(null);
      setLoading(false);
      setUrl("");
      setImage(null);
      setImagePreview(null);
   };

   return (
      <div className="verify-layout">
         <NavigationBar />

         <main className="verify-container">

            <div className="verify-header">
               <div className="verify-header-icon">
                  <Icons name="scan-line" size={22} color="var( --text-body)" />
               </div>
               <div>
                  <h1 className="verify-title">Verify a Claim</h1>
                  <p className="verify-subtitle">
                     Submit a URL or image to check if it contains misinformation.
                  </p>
               </div>
            </div>

            {/* Tabs */}
            <div className="verify-tabs">
               <button
                  className={`verify-tab-btn ${activeTab === "url" ? "active" : ""}`}
                  onClick={() => handleTabSwitch("url")}
               >
                  <Icons name="link" size={15} />
                  Verify URL
               </button>
               <button
                  className={`verify-tab-btn ${activeTab === "image" ? "active" : ""}`}
                  onClick={() => handleTabSwitch("image")}
               >
                  <Icons name="image" size={15} />
                  Verify Image
               </button>
            </div>

            <div className="verify-body">

               {/* ── URL Tab ── */}
               {activeTab === "url" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons name="link" size={14} />
                        Paste a news article or social media URL
                     </label>
                     <div className="url-input-row">
                        <input
                           type="text"
                           className="url-input"
                           placeholder="https://..."
                           value={url}
                           onChange={(e) => setUrl(e.target.value)}
                           onKeyDown={(e) => e.key === "Enter" && handleUrlVerify()}
                           disabled={loading}
                        />
                        <button
                           className="verify-submit-btn"
                           onClick={handleUrlVerify}
                           disabled={loading || !url.trim()}
                        >
                           {loading ? (
                              <>
                                 <div className="btn-spinner" />
                                 Verifying...
                              </>
                           ) : (
                              <>
                                 <Icons name="search" size={15} />
                                 Verify
                              </>
                           )}
                        </button>
                     </div>
                     <p className="panel-hint">
                        Works best with news articles. Social media posts and paywalled sites may not load correctly.
                     </p>
                  </div>
               )}

               {/* ── Image Tab ── */}
               {activeTab === "image" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons name="image" size={14} />
                        Upload a screenshot or image to verify
                     </label>

                     <div
                        className={`drop-zone ${imagePreview ? "has-image" : ""}`}
                        onClick={() => !imagePreview && fileInputRef.current?.click()}
                        onDrop={handleDrop}
                        onDragOver={(e) => e.preventDefault()}
                     >
                        {imagePreview ? (
                           <div className="image-preview-wrapper">
                              <img
                                 src={imagePreview}
                                 alt="Preview"
                                 className="image-preview"
                              />
                              <button
                                 className="remove-image-btn"
                                 onClick={(e) => {
                                    e.stopPropagation();
                                    setImage(null);
                                    setImagePreview(null);
                                    setResult(null);
                                 }}
                              >
                                 <Icons name="x" size={14} /> Remove
                              </button>
                           </div>
                        ) : (
                           <div className="drop-zone-content">
                              <Icons name="upload" size={32} color="#9ca3af" />
                              <p className="drop-zone-text">
                                 Drag and drop an image here, or{" "}
                                 <span className="drop-zone-link">browse</span>
                              </p>
                              <p className="drop-zone-hint">PNG, JPG, WEBP supported</p>
                           </div>
                        )}
                     </div>

                     {/* Hidden file input */}
                     <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden-file-input"
                        onChange={handleImageSelect}
                     />

                     <button
                        className="verify-submit-btn full-width"
                        onClick={handleImageVerify}
                        disabled={loading || !image}
                     >
                        {loading ? (
                           <>
                              <div className="btn-spinner" />
                              Analyzing image...
                           </>
                        ) : (
                           <>
                              <Icons name="scan-line" size={15} />
                              Verify Image
                           </>
                        )}
                     </button>
                     <p className="panel-hint">
                        Our AI will extract text from the image using OCR and verify the claim.
                     </p>
                  </div>
               )}

               {loading && (
                  <div className="verify-loading box-panel">
                     <div className="loading-spinner" />
                     <div>
                        <p className="loading-title">Analyzing your content...</p>
                        <p className="loading-subtitle">
                           This usually takes 10–30 seconds. Please wait.
                        </p>
                     </div>
                  </div>
               )}

               {error && (
                  <div className="verify-error">
                     <Icons name="alert-triangle" size={15} />
                     {error}
                  </div>
               )}

               {/* ── Result ── */}
               {result && !loading && (
                  <ResultCard
                     result={result}
                     onEscalate={() =>
                        navigate(`/thread/create?claim_id=${result.id}`)
                     }
                  />
               )}

            </div>
         </main>
      </div>
   );
}

export default VerifyPage;