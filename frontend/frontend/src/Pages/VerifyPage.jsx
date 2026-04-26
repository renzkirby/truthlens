/**
 * Verify Page (Fact Checking Interface)
 * ══════════════════════════════════════════════════════════════════
 * Main fact-checking interface where users submit claims for AI analysis.
 *
 * Features:
 *   - Multiple input methods (text snippet, URL, image/screenshot)
 *   - AI analysis results with confidence score
 *   - Verdict display with explanation
 *   - Escalation to community if unverified or low confidence
 *   - Result card with source links and context
 *
 * Workflow:
 *   1. User inputs claim (snippet, URL, or image)
 *   2. Backend processes via AI pipeline
 *   3. Results display with verdict, confidence, and summary
 *   4. User can escalate to community if desired
 */

import { useState, useRef } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";

// ── Utilities & Constants ──
import { VERDICT_CONFIG } from "../utils/constants";

// ── Styles ──
import "./VerifyPage.css";

const ResultSkeleton = () => {
   return (
      <div className="result-card" style={{ background: "var(--bg-surface)" }}>
         <div className="result-verdict-row" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <div className="skeleton-box" style={{ width: "120px", height: "16px" }}></div>
            <div className="skeleton-box" style={{ width: "100px", height: "24px", borderRadius: "12px" }}></div>
         </div>
         
         <div className="result-summary-box" style={{ marginTop: "16px" }}>
            <div className="skeleton-box" style={{ width: "150px", height: "16px", marginBottom: "12px" }}></div>
            <div className="skeleton-box" style={{ width: "100%", height: "14px", marginBottom: "8px" }}></div>
            <div className="skeleton-box" style={{ width: "100%", height: "14px", marginBottom: "8px" }}></div>
            <div className="skeleton-box" style={{ width: "80%", height: "14px" }}></div>
         </div>

         <div style={{ marginTop: "24px" }}>
            <div className="skeleton-box" style={{ width: "150px", height: "16px", marginBottom: "8px" }}></div>
            <div className="skeleton-box" style={{ width: "100%", height: "8px", borderRadius: "4px" }}></div>
         </div>

         <div style={{ marginTop: "24px", display: "flex", flexDirection: "column", gap: "12px" }}>
            <div className="skeleton-box" style={{ width: "100px", height: "16px" }}></div>
            <div className="skeleton-box" style={{ width: "100%", height: "14px" }}></div>
            <div className="skeleton-box" style={{ width: "80%", height: "14px" }}></div>
         </div>

         <div className="result-action-buttons" style={{ marginTop: "24px", display: "flex", gap: "12px" }}>
            <div className="skeleton-box" style={{ width: "150px", height: "36px", borderRadius: "8px" }}></div>
            <div className="skeleton-box" style={{ width: "180px", height: "36px", borderRadius: "8px" }}></div>
         </div>
      </div>
   );
};

// ── Result Card Component ──
// Displays AI analysis result with verdict badge, confidence, and CTA buttons
const ResultCard = ({ result, onEscalate }) => {
   const config = VERDICT_CONFIG[result.verdict] || VERDICT_CONFIG.UNVERIFIED;

   const confidenceColor =
      result.confidence_score >= 70
         ? "var(--verdict-fact-border)"
         : result.confidence_score >= 40
           ? "var(--verdict-misleading-border)"
           : "var(--verdict-fake-border)";

   const showEscalate = result.verdict === "UNVERIFIED" || result.confidence_score < 50;

   const evidenceList = result.sources && result.sources.length > 0 
      ? result.sources 
      : (result.source_url ? [result.source_url] : []);

   return (
      <div className="result-card">
         <div className="result-verdict-row">
            <span className="result-label">This content is</span>
            <span
               className="result-badge"
               style={{ color: config.color, backgroundColor: config.bg }}>
               {config.label}
            </span>
         </div>

         {/* ── Banners ── */}
         {result.has_community_verdict && (
            <div className="result-banner community-verified">
               <Icons name="shield-check" size={14} /> COMMUNITY VERIFIED
            </div>
         )}
         {result.is_ai_generated && (
            <div className="result-banner ai-warning">
               <Icons name="sparkles" size={14} /> AI-GENERATED MEDIA DETECTED
            </div>
         )}

         <div className="result-summary-box">
            <p className="result-summary-title">
               {result.has_community_verdict ? 'Community Verdict Summary' : 'AI Summary'}
            </p>
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

         {/* ── Score Context ── */}
         {result.score_context && (
            <div className="result-score-context">
               <strong>Context:</strong> {result.score_context}
            </div>
         )}

         {/* ── Multiple Sources List ── */}
         {result.verdict !== "OUT_OF_SCOPE" && evidenceList.length > 0 && (
            <div className="result-sources-section">
               <strong className="result-sources-title">Sources:</strong>
               <div className="result-sources-list">
                  {evidenceList.map((src, index) => {
                     const urlStr = typeof src === 'string' ? src : src.url;
                     return (
                        <a key={index} href={urlStr} target="_blank" rel="noopener noreferrer" className="result-source-item">
                           "{urlStr}"
                        </a>
                     );
                  })}
               </div>
            </div>
         )}


         <div className="result-footer" style={{ marginTop: '8px' }}>
            <span className="result-source-type">
               <Icons name="info" size={13} />
               Source Type: {result.has_community_verdict ? 'Community Moderation' : result.source_type}
            </span>
         </div>

         {/* ── Call to Action Buttons ── */}
         <div className="result-action-buttons">
            <a 
               href={`/analysis/${result.id}`} 
               target="_blank" 
               rel="noopener noreferrer" 
               className="view-report-btn"
            >
               View Full Report →
            </a>

            {result.thread_id ? (
               <a 
                  href={`/thread/detail/${result.thread_id}`} 
                  target="_blank" 
                  rel="noopener noreferrer" 
                  className="view-thread-btn"
               >
                  View Community Discussion
               </a>
            ) : showEscalate && result.id ? (
               <button
                  className="escalate-btn"
                  onClick={onEscalate}>
                  <Icons name="flag" size={14} />
                  Ask the Community
               </button>
            ) : null}
         </div>
      </div>
   );
};

// ── Main Page ─────────────────────────────────────────────────────────────────
function VerifyPage() {
   const { authFetch } = useAuth();
   const navigate = useNavigate();
   const fileInputRef = useRef(null);

   const [activeTab, setActiveTab] = useState("url");
   const [url, setUrl] = useState("");
   const [image, setImage] = useState(null);
   const [imagePreview, setImagePreview] = useState(null);
   const [text, setText] = useState("");
   const [loading, setLoading] = useState(false);
   const [result, setResult] = useState(null);
   const [error, setError] = useState(null);
   const [docFile, setDocFile] = useState(null);
   const docFileInputRef = useRef(null);

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
               `${import.meta.env.VITE_API_BASE_URL}/claims/${claimId}/status`,
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
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/verify-url/`, {
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

         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/analyze/`, {
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

   // ── File upload handlers ───────────────────────────────────────────────
   const handleDocFileSelect = (e) => {
      const file = e.target.files[0];
      if (!file) return;
      setDocFile(file);
      setResult(null);
      setError(null);
   };

   const handleDocDrop = (e) => {
      e.preventDefault();
      const file = e.dataTransfer.files[0];
      if (!file) return;
      setDocFile(file);
      setResult(null);
      setError(null);
   };

   const handleFileVerify = async () => {
      if (!docFile) return;
      setLoading(true);
      setResult(null);
      setError(null);

      try {
         // Convert document to base64
         const base64 = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(docFile);
         });

         // NOTE: We will need to build this endpoint in Django later to parse the PDF/DOCX!
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/verify-file/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
               file_data: base64,
               file_name: docFile.name,
               file_type: docFile.type 
            }),
         });
         
         pollForResult(data.claim_id);
      } catch (err) {
         setError("Failed to submit document. Please try again.");
         setLoading(false);
      }
   };

   // ── AI-GENERATED IMAGE DETECTION handler ────────────────────────────────────────────────────
   const handleDeepfakeTest = async () => {
      if (!image) return;
      setLoading(true);
      setResult(null);
      setError(null);

      const base64 = await new Promise((resolve, reject) => {
         const reader = new FileReader();
         reader.onload = () => resolve(reader.result);
         reader.onerror = reject;
         reader.readAsDataURL(image);
      });

      try {
         const response = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/test-deepfake/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_data: base64 }),
         });

         // Custom simple result for the sandbox
         setResult({
            isDeepfakeTest: true,
            score: (response.ai_probability * 100).toFixed(1),
            verdict: response.is_fake ? "AI GENERATED" : "REAL IMAGE",
            summary: response.summary
         });
      } catch (err) {
         setError("Deepfake test failed.");
      } finally {
         setLoading(false);
      }
   };

   // ── Text verification handler ────────────────────────────────────────────
   const handleTextVerify = async () => {
      if (!text.trim()) return;
      setLoading(true);
      setResult(null);
      setError(null);

      try {
         // We will build this endpoint in Django next!
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/verify-text/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text }),
         });
         pollForResult(data.claim_id);
      } catch (err) {
         setError("Failed to submit text. Please try again.");
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
      setText("");
      setDocFile(null);
   };

   return (
      <div className="verify-layout">
         <NavigationBar />

         <main className="verify-container">
            <div className="verify-header">
               <div className="verify-header-icon">
                  <Icons
                     name="scan-line"
                     size={22}
                     color="#fff"
                  />
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
                  onClick={() => handleTabSwitch("url")}>
                  <Icons
                     name="link"
                     size={15}
                  />
                  Analyze URL
               </button>
               <button
                  className={`verify-tab-btn ${activeTab === "image" ? "active" : ""}`}
                  onClick={() => handleTabSwitch("image")}>
                  <Icons
                     name="image"
                     size={15}
                  />
                  Verify Image
               </button>
               <button
                  className={`verify-tab-btn ${activeTab === "text" ? "active" : ""}`}
                  onClick={() => handleTabSwitch("text")}>
                  <Icons
                     name="file-text"
                     size={15}
                  />
                  Verify Text
               </button>
               <button
                  className={`verify-tab-btn ${activeTab === "file" ? "active" : ""}`}
                  onClick={() => handleTabSwitch("file")}>
                  <Icons name="file" size={15} />
                  Verify File
               </button>
               <button
                  className={`verify-tab-btn ${activeTab === "deepfake" ? "active" : ""}`}
                  onClick={() => {
                     setActiveTab("deepfake");
                     setResult(null);
                     setError(null);
                  }}>
                  <Icons
                     name="sparkles"
                     size={16}
                  />
                  Detect Deepfake
               </button>
            </div>

            <div className="verify-body">
               {/* Loading State */}
               {loading && <ResultSkeleton />}
               {/* Error State */}
               {error && (
                  <div className="verify-error">
                     <Icons
                        name="alert-triangle"
                        size={15}
                     />
                     {error}
                  </div>
               )}
               {/* ── Standard Fact-Check Result ── */}
               {result && !result.isDeepfakeTest && !loading && (
                  <ResultCard
                     result={result}
                     onEscalate={() => navigate(`/thread/create?claim_id=${result.id}`)}
                  />
               )}

               {/* ── Deepfake Test Custom Result ── */}
               {result && result.isDeepfakeTest && !loading && (
                  <div className="result-card box-panel">
                     <div className="result-verdict-row">
                        <span className="result-label">Deepfake Analysis:</span>
                        <span
                           className="result-badge"
                           style={{
                              backgroundColor:
                                 result.verdict === "AI GENERATED"
                                    ? "var(--fake-bg, #fee2e2)"
                                    : "var(--fact-bg, #dcfce7)",
                              color:
                                 result.verdict === "AI GENERATED"
                                    ? "var(--fake-text, #991b1b)"
                                    : "var(--fact-text, #166534)",
                              border: `1px solid ${result.verdict === "AI GENERATED" ? "var(--fake-border, #f87171)" : "var(--fact-border, #86efac)"}`,
                           }}>
                           {result.verdict}
                        </span>
                     </div>

                     <div className="result-summary-box">
                        <p className="result-summary-title">AI Forensic Analysis</p>
                        <p className="result-summary-text" style={{ marginBottom: "8px" }}>
                           The forensic model is <strong>{result.score}%</strong> confident that
                           this image was generated or manipulated by AI.
                        </p>
                        <div style={{ borderTop: "1px solid #e5e7eb", paddingTop: "8px", fontSize: "13px", color: "#4b5563" }}>
                           <strong>Explanation:</strong> {result.summary}
                        </div>
                     </div>
                  </div>
               )}

               {/* ── URL Tab ── */}
               {activeTab === "url" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons
                           name="link"
                           size={14}
                        />
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
                           disabled={loading || !url.trim()}>
                           {loading ? (
                              <>
                                 <div className="btn-spinner" />
                                 Verifying...
                              </>
                           ) : (
                              <>
                                 <Icons
                                    name="search"
                                    size={15}
                                 />
                                 Verify
                              </>
                           )}
                        </button>
                     </div>
                     <p className="panel-hint">
                        Works best with news articles. Social media posts and paywalled sites may
                        not load correctly.
                     </p>
                  </div>
               )}

               {/* ── Image Tab ── */}
               {activeTab === "image" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons
                           name="image"
                           size={14}
                        />
                        Upload a screenshot or image to verify
                     </label>

                     <div
                        className={`drop-zone ${imagePreview ? "has-image" : ""}`}
                        onClick={() => !imagePreview && fileInputRef.current?.click()}
                        onDrop={handleDrop}
                        onDragOver={(e) => e.preventDefault()}>
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
                                 }}>
                                 <Icons
                                    name="x"
                                    size={14}
                                 />{" "}
                                 Remove
                              </button>
                           </div>
                        ) : (
                           <div className="drop-zone-content">
                              <Icons
                                 name="upload"
                                 size={32}
                                 color="#9ca3af"
                              />
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
                        disabled={loading || !image}>
                        {loading ? (
                           <>
                              <div className="btn-spinner" />
                              Analyzing image...
                           </>
                        ) : (
                           <>
                              <Icons
                                 name="scan-line"
                                 size={15}
                              />
                              Verify Image
                           </>
                        )}
                     </button>
                     <p className="panel-hint">
                        Our AI will extract text from the image using OCR and verify the claim.
                     </p>
                  </div>
               )}
               {/* Text Tab */}
               {activeTab === "text" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons
                           name="file-text"
                           size={14}
                        />
                        Paste a claim, quote, or social media post
                     </label>

                     <textarea
                        className="url-input"
                        placeholder="e.g., 'The government just announced a nationwide lockdown starting tomorrow...'"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        disabled={loading}
                        rows={5}
                        style={{
                           resize: "vertical",
                           height: "auto",
                           minHeight: "100px",
                           padding: "12px",
                           marginBottom: "15px",
                           width: "100%",
                        }}
                     />

                     <button
                        className="verify-submit-btn full-width"
                        onClick={handleTextVerify}
                        disabled={loading || !text.trim()}>
                        {loading ? (
                           <>
                              <div className="btn-spinner" />
                              Analyzing text...
                           </>
                        ) : (
                           <>
                              <Icons
                                 name="search"
                                 size={15}
                              />
                              Verify Text
                           </>
                        )}
                     </button>
                     <p className="panel-hint">
                        Our AI will extract the core claim, cross-reference it with live news, and
                        evaluate its factual accuracy.
                     </p>
                  </div>
               )}

               {/* ── File Tab ── */}
               {activeTab === "file" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons name="file" size={14} />
                        Upload a document to verify
                     </label>

                     <div
                        className={`drop-zone ${docFile ? "has-image" : ""}`}
                        onClick={() => !docFile && docFileInputRef.current?.click()}
                        onDrop={handleDocDrop}
                        onDragOver={(e) => e.preventDefault()}>
                        {docFile ? (
                           <div className="image-preview-wrapper">
                              <div className="file-preview-box">
                                 <Icons name="file-text" size={32} color="#4f46e5" />
                                 <p className="file-name">{docFile.name}</p>
                                 <p className="file-size">{(docFile.size / 1024 / 1024).toFixed(2)} MB</p>
                              </div>
                              <button
                                 className="remove-image-btn"
                                 onClick={(e) => {
                                    e.stopPropagation();
                                    setDocFile(null);
                                    setResult(null);
                                 }}>
                                 <Icons name="x" size={14} /> Remove
                              </button>
                           </div>
                        ) : (
                           <div className="drop-zone-content">
                              <Icons name="upload" size={32} color="#9ca3af" />
                              <p className="drop-zone-text">
                                 Drag and drop a document here, or <span className="drop-zone-link">browse</span>
                              </p>
                              <p className="drop-zone-hint">PDF & TXT format supported</p>
                           </div>
                        )}
                     </div>

                     {/* Hidden file input */}
                     <input
                        ref={docFileInputRef}
                        type="file"
                        accept=".pdf,.docx,.txt"
                        className="hidden-file-input"
                        onChange={handleDocFileSelect}
                     />

                     <button
                        className="verify-submit-btn full-width"
                        onClick={handleFileVerify}
                        disabled={loading || !docFile}>
                        {loading ? (
                           <>
                              <div className="btn-spinner" />
                              Analyzing document...
                           </>
                        ) : (
                           <>
                              <Icons name="scan-line" size={15} />
                              Verify Document
                           </>
                        )}
                     </button>
                     <p className="panel-hint">
                        Our AI will extract text from the document and cross-reference its claims.
                     </p>
                  </div>
               )}

               {/* Deepfake Tab */}
               {activeTab === "deepfake" && (
                  <div className="verify-panel box-panel">
                     <label className="panel-label">
                        <Icons
                           name="sparkles"
                           size={14}
                        />
                        Upload a photo for Deepfake detection
                     </label>

                     <div
                        className={`drop-zone ${imagePreview ? "has-image" : ""}`}
                        onClick={() => !imagePreview && fileInputRef.current?.click()}
                        onDrop={handleDrop}
                        onDragOver={(e) => e.preventDefault()}>
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
                                 }}>
                                 <Icons
                                    name="x"
                                    size={14}
                                 />{" "}
                                 Remove
                              </button>
                           </div>
                        ) : (
                           <div className="drop-zone-content">
                              <Icons
                                 name="upload"
                                 size={32}
                                 color="#9ca3af"
                              />
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
                        onClick={handleDeepfakeTest}
                        disabled={loading || !image}>
                        {loading ? (
                           <>
                              <div className="btn-spinner" />
                              Analyzing pixels...
                           </>
                        ) : (
                           <>
                              <Icons
                                 name="scan-line"
                                 size={15}
                              />
                              Run Deepfake Test
                           </>
                        )}
                     </button>
                     <p className="panel-hint">
                        Our AI model will analyze the image for digital fabrication or AI
                        generation.
                     </p>
                  </div>
               )}
            </div>
         </main>
      </div>
   );
}

export default VerifyPage;
