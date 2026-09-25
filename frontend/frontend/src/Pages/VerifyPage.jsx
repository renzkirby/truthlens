import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import Icons from "../components/Icons.jsx";
import { VERDICT_CONFIG } from "../utils/constants";
import "./VerifyPage.css";

const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 60;
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];
const DOCUMENT_EXTENSIONS = ["pdf", "docx", "txt"];

const VERIFY_MODES = [
   { id: "url", label: "URL", icon: "link", group: "claim" },
   { id: "text", label: "Text", icon: "file-text", group: "claim" },
   { id: "image", label: "Image", icon: "image", group: "claim" },
   { id: "file", label: "Document", icon: "file", group: "claim" },
   { id: "deepfake", label: "AI Image Check", icon: "sparkles", group: "media" },
];

const normalizeResult = (payload, claimId) => ({
   ...payload,
   id: payload?.id || payload?.claim_id || claimId,
});

const isResolvedMatch = (match) => Boolean(match?.verdict && match.verdict !== "PENDING");
const hasNumericValue = (value) =>
   value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value));

const getErrorMessage = (error, fallback) => {
   if (error?.status === 429) {
      return "Too many verification requests. Please wait a moment and try again.";
   }

   if (error?.status === 400 || error?.status === 415) {
      return "We could not process that input. Check the format and try again.";
   }

   return fallback;
};

const getSafeSourceUrl = (value) => {
   if (typeof value !== "string") return null;

   try {
      const parsedUrl = new URL(value);
      return parsedUrl.protocol === "http:" || parsedUrl.protocol === "https:" ? value : null;
   } catch {
      return null;
   }
};

const getSourceDetails = (source) => {
   if (typeof source === "string") return { url: getSafeSourceUrl(source), title: null };
   if (!source || typeof source !== "object") return { url: null, title: null };
   return { url: getSafeSourceUrl(source.url), title: source.title || null };
};

const getSourceLabel = ({ url, title }) => {
   if (title) return title;
   if (!url) return "Source";

   try {
      return new URL(url).hostname.replace(/^www\./, "");
   } catch {
      return url;
   }
};

const VerifyLoadingState = ({ mode }) => {
   const isMediaCheck = mode === "deepfake";

   return (
      <div className="verify-loading-container" role="status" aria-live="polite">
         <span className="verify-loading-spinner" aria-hidden="true" />
         <div>
            <p className="verify-loading-text">{isMediaCheck ? "Analyzing media signals" : "Analysis in progress"}</p>
            <p className="verify-loading-subtext">
               {isMediaCheck
                  ? "The model is checking for signals associated with AI-generated imagery."
                  : "TruthLens is gathering source context and evaluating the submitted claim."}
            </p>
         </div>
      </div>
   );
};

const VerdictBadge = ({ verdict }) => {
   const normalizedVerdict = verdict || "UNVERIFIED";
   const config = VERDICT_CONFIG[normalizedVerdict] || VERDICT_CONFIG.UNVERIFIED;

   return (
      <span className={`result-badge result-badge--${normalizedVerdict.toLowerCase()}`}>
         <Icons name={config.icon} size={15} />
         {config.label}
      </span>
   );
};

const AiConfidence = ({ value }) => {
   if (!hasNumericValue(value)) return null;
   const numericValue = Number(value);

   const boundedValue = Math.min(100, Math.max(0, numericValue));

   return (
      <div className="ai-confidence">
         <div className="ai-confidence-heading">
            <span>AI confidence</span>
            <strong>{Math.round(boundedValue)}%</strong>
         </div>
         <div
            className="ai-confidence-track"
            role="meter"
            aria-label="AI confidence"
            aria-valuemin="0"
            aria-valuemax="100"
            aria-valuenow={Math.round(boundedValue)}
         >
            <span className="ai-confidence-fill" style={{ width: `${boundedValue}%` }} />
         </div>
         <p>Model confidence in its own assessment, not human or institutional certainty.</p>
      </div>
   );
};

const SourceList = ({ sources, title }) => {
   const sourceItems = (sources || []).map(getSourceDetails).filter((source) => source.url);
   if (!sourceItems.length) return null;

   return (
      <section className="result-sources-section" aria-labelledby="verify-sources-title">
         <h3 id="verify-sources-title" className="result-section-title">
            {title}
         </h3>
         <ul className="result-sources-list">
            {sourceItems.map((source, index) => (
               <li key={`${source.url}-${index}`}>
                  <a href={source.url} target="_blank" rel="noopener noreferrer" className="result-source-item">
                     <span>{getSourceLabel(source)}</span>
                     {source.title && <small>{source.url}</small>}
                     <Icons name="external-link" size={14} aria-hidden="true" />
                  </a>
               </li>
            ))}
         </ul>
      </section>
   );
};

const OrganizationIdentity = ({ organization }) => {
   const [failedLogoUrl, setFailedLogoUrl] = useState(null);
   const logoUrl = organization?.logo_url || null;
   const canShowLogo = Boolean(logoUrl && failedLogoUrl !== logoUrl);

   if (!organization?.name) return null;

   return (
      <div className="organization-identity">
         {canShowLogo ? (
            <img
               src={logoUrl}
               alt={`${organization.name} logo`}
               className="organization-logo"
               onError={() => setFailedLogoUrl(logoUrl)}
            />
         ) : (
            <span className="organization-monogram" aria-hidden="true">
               {organization.name.charAt(0).toUpperCase()}
            </span>
         )}
         <div>
            <span>Published by</span>
            <strong>{organization.name}</strong>
         </div>
      </div>
   );
};

const ResultCard = ({ result }) => {
   const resolutionSource = result.resolution_source || (result.final_verdict ? "ADJUDICATION" : "AI");
   const isOfficial = resolutionSource === "OFFICIAL_FACT_CHECK";
   const isAdjudication = resolutionSource === "ADJUDICATION";
   const hasCommunityDiscussion = resolutionSource === "COMMUNITY_THREAD";
   const officialFactCheck = isOfficial ? result.official_fact_check : null;
   const organization = officialFactCheck?.organization;
   const officialRoute =
      organization?.public_profile_available && organization?.slug && officialFactCheck?.fact_check_id
         ? `/partners/${encodeURIComponent(organization.slug)}/fact-checks/${encodeURIComponent(officialFactCheck.fact_check_id)}`
         : null;
   const displayedVerdict = isAdjudication
      ? result.final_verdict || result.verdict
      : isOfficial
        ? officialFactCheck?.verdict || result.verdict
        : result.ai_verdict || result.verdict;
   const aiVerdict = result.ai_verdict && result.ai_verdict !== displayedVerdict ? result.ai_verdict : null;
   const summary = isOfficial ? officialFactCheck?.summary || result.summary : result.summary;
   const sources = isOfficial
      ? officialFactCheck?.sources || []
      : result.sources?.length
        ? result.sources
        : result.source_url
          ? [result.source_url]
          : [];
   const canDiscuss = result.verdict !== "OUT_OF_SCOPE" && Boolean(result.id);
   const isAiOwnedResult = resolutionSource === "AI" || resolutionSource === "COMMUNITY_THREAD";
   const isEscalation =
      isAiOwnedResult &&
      (displayedVerdict === "UNVERIFIED" ||
         (hasNumericValue(result.confidence_score) && Number(result.confidence_score) < 50));
   const sourceSectionTitle = isOfficial
      ? "Published sources"
      : resolutionSource === "AI"
        ? "Sources considered by AI"
        : "Available sources";

   const provenance = isOfficial
      ? {
           icon: "shield-check",
           title: "Published fact-check",
           description: "An institutional publication is the authoritative conclusion shown here.",
           className: "official",
        }
      : isAdjudication
        ? {
             icon: "users",
             title: "Human adjudication",
             description: "A human adjudicator determined the verdict. AI material is separated below.",
             className: "adjudication",
          }
        : {
             icon: "sparkles",
             title: "AI-assisted assessment",
             description:
                "This conclusion was produced by automated analysis and should be checked against its sources.",
             className: "ai",
          };

   return (
      <article className="result-card" aria-labelledby="result-provenance-title">
         <header className={`result-provenance result-provenance--${provenance.className}`}>
            <span className="result-provenance-icon" aria-hidden="true">
               <Icons name={provenance.icon} size={18} />
            </span>
            <div>
               <h2 id="result-provenance-title">{provenance.title}</h2>
               <p>{provenance.description}</p>
            </div>
         </header>

         {hasCommunityDiscussion && (
            <div className="community-availability">
               <Icons name="message-circle" size={16} aria-hidden="true" />
               <div>
                  <strong>Community discussion available</strong>
                  <span>The discussion is separate from the AI-assisted assessment above.</span>
               </div>
            </div>
         )}

         {isOfficial && <OrganizationIdentity organization={organization} />}

         <section className="result-conclusion" aria-labelledby="result-conclusion-title">
            <p id="result-conclusion-title" className="result-section-title">
               {isOfficial ? "Published conclusion" : isAdjudication ? "Adjudicated conclusion" : "AI conclusion"}
            </p>
            <div className="result-verdict-row">
               <VerdictBadge verdict={displayedVerdict} />
            </div>
            {isOfficial && officialFactCheck?.headline && (
               <h3 className="official-headline">{officialFactCheck.headline}</h3>
            )}
         </section>

         {result.is_ai_generated && (
            <div className="result-signal-note">
               <Icons name="sparkles" size={15} aria-hidden="true" />
               AI-generated media signals were detected in the submitted content.
            </div>
         )}

         {isOfficial ? (
            summary && (
               <section className="result-summary-box" aria-labelledby="published-summary-title">
                  <h3 id="published-summary-title" className="result-section-title">
                     Published summary
                  </h3>
                  <p className="result-summary-text">{summary}</p>
               </section>
            )
         ) : isAdjudication ? (
            (summary || hasNumericValue(result.confidence_score) || result.score_context) && (
               <section className="ai-context" aria-labelledby="ai-context-title">
                  <div className="ai-context-heading">
                     <Icons name="sparkles" size={16} aria-hidden="true" />
                     <h3 id="ai-context-title">AI analysis context</h3>
                  </div>
                  {summary && <p className="result-summary-text">{summary}</p>}
                  {aiVerdict && (
                     <p className="ai-context-verdict">
                        AI assessment: <VerdictBadge verdict={aiVerdict} />
                     </p>
                  )}
                  <AiConfidence value={result.confidence_score} />
                  {result.score_context && (
                     <p className="result-score-context">
                        <strong>AI assessment context:</strong> {result.score_context}
                     </p>
                  )}
               </section>
            )
         ) : (
            <>
               {summary && (
                  <section className="result-summary-box" aria-labelledby="ai-summary-title">
                     <h3 id="ai-summary-title" className="result-section-title">
                        AI analysis summary
                     </h3>
                     <p className="result-summary-text">{summary}</p>
                  </section>
               )}
               <AiConfidence value={result.confidence_score} />
            </>
         )}

         {result.score_context && !isOfficial && !isAdjudication && (
            <p className="result-score-context">
               <strong>AI assessment context:</strong> {result.score_context}
            </p>
         )}

         <SourceList sources={sources} title={sourceSectionTitle} />

         {result.source_type && (
            <p className="result-source-type">
               <Icons name="info" size={14} aria-hidden="true" />
               Input or source type: {result.source_type}
            </p>
         )}

         <div className="result-action-buttons">
            {officialRoute && (
               <Link to={officialRoute} className="result-action result-action--primary">
                  Read published fact-check
                  <Icons name="arrow-right" size={16} aria-hidden="true" />
               </Link>
            )}

            {result.id && (
               <Link
                  to={`/analysis/${encodeURIComponent(result.id)}`}
                  className={`result-action ${officialRoute ? "result-action--secondary" : "result-action--primary"}`}
               >
                  View AI analysis
                  <Icons name="arrow-right" size={16} aria-hidden="true" />
               </Link>
            )}

            {result.thread_id ? (
               <Link
                  to={`/thread/detail/${encodeURIComponent(result.thread_id)}`}
                  className="result-action result-action--secondary"
               >
                  View community discussion
               </Link>
            ) : canDiscuss ? (
               <Link
                  to={`/thread/create?claim_id=${encodeURIComponent(result.id)}`}
                  className="result-action result-action--tertiary"
               >
                  <Icons name={isEscalation ? "flag" : "users"} size={15} aria-hidden="true" />
                  {isEscalation ? "Ask the community" : "Start a community discussion"}
               </Link>
            ) : null}
         </div>
      </article>
   );
};

const DeepfakeResult = ({ result }) => {
   const detected = result.detected;

   return (
      <article className="result-card media-result" aria-labelledby="media-result-title">
         <header className="result-provenance result-provenance--ai">
            <span className="result-provenance-icon" aria-hidden="true">
               <Icons name="scan-line" size={18} />
            </span>
            <div>
               <h2 id="media-result-title">Automated image analysis</h2>
               <p>This is a model estimate, not proof that the image is authentic or fabricated.</p>
            </div>
         </header>

         <div className={`media-signal media-signal--${detected ? "detected" : "clear"}`}>
            <Icons name={detected ? "alert-triangle" : "info"} size={18} aria-hidden="true" />
            <strong>{detected ? "AI-generation signals detected" : "No strong AI-generation signals detected"}</strong>
         </div>

         <section className="media-probability" aria-labelledby="media-probability-title">
            <p id="media-probability-title">Model-estimated AI-generation likelihood</p>
            <strong>{result.score === null ? "Unavailable" : `${result.score}%`}</strong>
         </section>

         {result.summary && (
            <section className="result-summary-box" aria-labelledby="media-explanation-title">
               <h3 id="media-explanation-title" className="result-section-title">
                  Model explanation
               </h3>
               <p className="result-summary-text">{result.summary}</p>
            </section>
         )}

         <p className="media-caveat">
            Automated detection can miss sophisticated edits or flag genuine images. Use provenance, original files, and
            corroborating evidence before drawing a conclusion.
         </p>
      </article>
   );
};

function VerifyPage() {
   const { authFetch } = useAuth();
   const [activeTab, setActiveTab] = useState("url");
   const [url, setUrl] = useState("");
   const [text, setText] = useState("");
   const [claimImage, setClaimImage] = useState(null);
   const [claimImagePreview, setClaimImagePreview] = useState(null);
   const [mediaImage, setMediaImage] = useState(null);
   const [mediaImagePreview, setMediaImagePreview] = useState(null);
   const [docFile, setDocFile] = useState(null);
   const [loading, setLoading] = useState(false);
   const [result, setResult] = useState(null);
   const [error, setError] = useState(null);

   const tabRefs = useRef([]);
   const claimImageInputRef = useRef(null);
   const mediaImageInputRef = useRef(null);
   const docFileInputRef = useRef(null);
   const pollTimerRef = useRef(null);
   const operationRef = useRef(0);
   const resultRef = useRef(null);

   useEffect(() => {
      return () => {
         if (claimImagePreview) URL.revokeObjectURL(claimImagePreview);
      };
   }, [claimImagePreview]);

   useEffect(() => {
      return () => {
         if (mediaImagePreview) URL.revokeObjectURL(mediaImagePreview);
      };
   }, [mediaImagePreview]);

   useEffect(() => {
      return () => {
         operationRef.current += 1;
         if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
      };
   }, []);

   useEffect(() => {
      if (result && !loading) resultRef.current?.focus();
   }, [result, loading]);

   const cancelActiveWork = () => {
      operationRef.current += 1;
      if (pollTimerRef.current) {
         clearTimeout(pollTimerRef.current);
         pollTimerRef.current = null;
      }
   };

   const beginOperation = () => {
      cancelActiveWork();
      const operationId = operationRef.current;
      setLoading(true);
      setResult(null);
      setError(null);
      return operationId;
   };

   const failOperation = (operationId, message) => {
      if (operationRef.current !== operationId) return;
      setError(message);
      setLoading(false);
   };

   const pollForResult = (claimId, operationId) => {
      let pollCount = 0;

      const poll = async () => {
         if (operationRef.current !== operationId) return;
         pollCount += 1;

         if (pollCount > MAX_POLLS) {
            failOperation(operationId, "This analysis is taking longer than expected. You can try again in a moment.");
            return;
         }

         try {
            const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/claims/${claimId}/status`);
            if (operationRef.current !== operationId) return;

            if (data.verdict !== "PENDING") {
               setResult(normalizeResult(data, claimId));
               setLoading(false);
               return;
            }

            pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
         } catch (pollError) {
            failOperation(
               operationId,
               getErrorMessage(pollError, "We could not retrieve the verification result. Please try again."),
            );
         }
      };

      pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
   };

   const handleSubmissionResponse = (data, operationId) => {
      if (operationRef.current !== operationId) return;

      if (isResolvedMatch(data?.match)) {
         setResult(normalizeResult(data.match, data.claim_id));
         setLoading(false);
         return;
      }

      if (!data?.claim_id) {
         failOperation(operationId, "The verification request did not start correctly. Please try again.");
         return;
      }

      pollForResult(data.claim_id, operationId);
   };

   const handleUrlVerify = async (event) => {
      event?.preventDefault();
      if (!url.trim()) return;
      const operationId = beginOperation();

      try {
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/verify-url/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: { url: url.trim() },
         });
         handleSubmissionResponse(data, operationId);
      } catch (submissionError) {
         failOperation(
            operationId,
            getErrorMessage(submissionError, "We could not submit that URL. Check it and try again."),
         );
      }
   };

   const handleTextVerify = async () => {
      if (!text.trim()) return;
      const operationId = beginOperation();

      try {
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/verify-text/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: { text: text.trim() },
         });
         handleSubmissionResponse(data, operationId);
      } catch (submissionError) {
         failOperation(
            operationId,
            getErrorMessage(submissionError, "We could not submit that text. Please try again."),
         );
      }
   };

   const handleImageVerify = async () => {
      if (!claimImage) return;
      const operationId = beginOperation();

      try {
         const base64 = await readFileAsDataUrl(claimImage);
         if (operationRef.current !== operationId) return;
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/analyze/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: { image_data: base64 },
         });
         handleSubmissionResponse(data, operationId);
      } catch (submissionError) {
         failOperation(
            operationId,
            getErrorMessage(submissionError, "We could not analyze that image. Please try another file."),
         );
      }
   };

   const handleFileVerify = async () => {
      if (!docFile) return;
      const operationId = beginOperation();

      try {
         const base64 = await readFileAsDataUrl(docFile);
         if (operationRef.current !== operationId) return;
         const data = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/verify-file/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: {
               file_data: base64,
               file_name: docFile.name,
               file_type: docFile.type,
            },
         });
         handleSubmissionResponse(data, operationId);
      } catch (submissionError) {
         failOperation(
            operationId,
            getErrorMessage(submissionError, "We could not analyze that document. Please try again."),
         );
      }
   };

   const handleDeepfakeTest = async () => {
      if (!mediaImage) return;
      const operationId = beginOperation();

      try {
         const base64 = await readFileAsDataUrl(mediaImage);
         if (operationRef.current !== operationId) return;
         const response = await authFetch(`${import.meta.env.VITE_API_BASE_URL}/test-deepfake/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: { image_data: base64 },
         });
         if (operationRef.current !== operationId) return;
         const probability = Number(response.ai_probability);
         setResult({
            isDeepfakeTest: true,
            score: Number.isFinite(probability) ? (probability * 100).toFixed(1) : null,
            detected: Boolean(response.is_fake),
            summary: response.summary,
         });
         setLoading(false);
      } catch (submissionError) {
         failOperation(
            operationId,
            getErrorMessage(submissionError, "The media analysis could not be completed. Please try again."),
         );
      }
   };

   const selectImage = (file, setFile, setPreview, inputRef) => {
      if (!file) return;

      const extension = file.name.split(".").pop()?.toLowerCase();
      if (!IMAGE_TYPES.includes(file.type) && !["jpg", "jpeg", "png", "webp"].includes(extension)) {
         cancelActiveWork();
         setFile(null);
         setPreview(null);
         setResult(null);
         setError("Choose a PNG, JPG, or WEBP image.");
         setLoading(false);
         if (inputRef.current) inputRef.current.value = "";
         return;
      }

      cancelActiveWork();
      setFile(file);
      setPreview(URL.createObjectURL(file));
      setResult(null);
      setError(null);
      setLoading(false);
   };

   const selectDocument = (file) => {
      if (!file) return;
      const extension = file.name.split(".").pop()?.toLowerCase();

      if (!DOCUMENT_EXTENSIONS.includes(extension)) {
         cancelActiveWork();
         setDocFile(null);
         setResult(null);
         setError("Choose a PDF, DOCX, or TXT document.");
         setLoading(false);
         if (docFileInputRef.current) docFileInputRef.current.value = "";
         return;
      }

      cancelActiveWork();
      setDocFile(file);
      setResult(null);
      setError(null);
      setLoading(false);
   };

   const clearFile = (setFile, inputRef, setPreview = null) => {
      cancelActiveWork();
      setFile(null);
      if (setPreview) setPreview(null);
      setResult(null);
      setError(null);
      setLoading(false);
      if (inputRef.current) inputRef.current.value = "";
   };

   const handleTabSwitch = (tab) => {
      if (tab === activeTab) return;
      cancelActiveWork();
      setActiveTab(tab);
      setResult(null);
      setError(null);
      setLoading(false);
   };

   const handleTabKeyDown = (event, index) => {
      let nextIndex = null;
      if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % VERIFY_MODES.length;
      if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
         nextIndex = (index - 1 + VERIFY_MODES.length) % VERIFY_MODES.length;
      }
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = VERIFY_MODES.length - 1;
      if (nextIndex === null) return;

      event.preventDefault();
      handleTabSwitch(VERIFY_MODES[nextIndex].id);
      tabRefs.current[nextIndex]?.focus();
   };

   return (
      <div className="verify-layout">
         <main className={`verify-container ${result && !loading ? "has-result" : ""}`}>
            <header className="verify-header">
               <div className="verify-header-icon" aria-hidden="true">
                  <Icons name="scan-line" size={22} />
               </div>
               <div>
                  <h1 className="verify-title">Verify a claim or check image</h1>
                  <p className="verify-subtitle">
                     Compare claims with available evidence, or check an image for AI-generation signals.
                  </p>
               </div>
            </header>

            <section className="verify-mode-selector" aria-label="Verification method">
               <div className="verify-mode-context">
                  <span>Claim verification</span>
                  <span>AI image detection</span>
               </div>
               <div className="verify-tabs" role="tablist" aria-label="Choose what to analyze">
                  {VERIFY_MODES.map((mode, index) => (
                     <button
                        key={mode.id}
                        ref={(element) => {
                           tabRefs.current[index] = element;
                        }}
                        id={`verify-tab-${mode.id}`}
                        type="button"
                        role="tab"
                        aria-selected={activeTab === mode.id}
                        aria-controls="verify-mode-panel"
                        tabIndex={activeTab === mode.id ? 0 : -1}
                        className={`verify-tab-btn ${mode.group === "media" ? "verify-tab-btn--media" : ""} ${activeTab === mode.id ? "active" : ""}`}
                        onClick={() => handleTabSwitch(mode.id)}
                        onKeyDown={(event) => handleTabKeyDown(event, index)}
                     >
                        <Icons name={mode.icon} size={16} aria-hidden="true" />
                        {mode.label}
                     </button>
                  ))}
               </div>
            </section>

            <div className="verify-body">
               <div className="verify-body-left">
                  {loading && <VerifyLoadingState mode={activeTab} />}

                  {error && (
                     <div className="verify-error" role="alert">
                        <Icons name="alert-triangle" size={17} aria-hidden="true" />
                        <span>{error}</span>
                     </div>
                  )}

                  <section
                     id="verify-mode-panel"
                     role="tabpanel"
                     aria-labelledby={`verify-tab-${activeTab}`}
                     className="verify-panel box-panel"
                  >
                     {activeTab === "url" && (
                        <form onSubmit={handleUrlVerify}>
                           <PanelHeading
                              icon="link"
                              title="Check a URL-based claim"
                              description="Submit a public article or post. TruthLens will analyze its claim and available source context."
                           />
                           <label className="field-label" htmlFor="verify-url-input">
                              Article or post URL
                           </label>
                           <div className="url-input-row">
                              <input
                                 id="verify-url-input"
                                 type="url"
                                 inputMode="url"
                                 className="verify-input"
                                 placeholder="https://example.com/article"
                                 value={url}
                                 onChange={(event) => {
                                    setUrl(event.target.value);
                                    setResult(null);
                                    setError(null);
                                 }}
                                 disabled={loading}
                                 required
                                 aria-describedby="verify-url-hint"
                              />
                              <SubmitButton loading={loading} disabled={!url.trim()} label="Verify URL" />
                           </div>
                           <p id="verify-url-hint" className="panel-hint">
                              Public pages work best. Paywalls and sign-in walls may limit the available evidence.
                           </p>
                        </form>
                     )}

                     {activeTab === "text" && (
                        <>
                           <PanelHeading
                              icon="file-text"
                              title="Check a written claim"
                              description="Paste one clear factual claim, quotation, or short post for focused analysis."
                           />
                           <label className="field-label" htmlFor="verify-text-input">
                              Claim text
                           </label>
                           <textarea
                              id="verify-text-input"
                              className="verify-input verify-textarea"
                              placeholder="Paste the claim you want to check…"
                              value={text}
                              onChange={(event) => {
                                 setText(event.target.value);
                                 setResult(null);
                                 setError(null);
                              }}
                              disabled={loading}
                              rows={6}
                              aria-describedby="verify-text-hint"
                           />
                           <button
                              type="button"
                              className="verify-submit-btn full-width"
                              onClick={handleTextVerify}
                              disabled={loading || !text.trim()}
                           >
                              <Icons name="search" size={16} aria-hidden="true" />
                              Verify text
                           </button>
                           <p id="verify-text-hint" className="panel-hint">
                              Keep the wording specific. Context such as dates, places, and named people can improve the
                              analysis.
                           </p>
                        </>
                     )}

                     {activeTab === "image" && (
                        <>
                           <PanelHeading
                              icon="image"
                              title="Verify a claim shown in an image"
                              description="Upload a screenshot or image containing text. TruthLens will extract and analyze the claim."
                           />
                           <UploadZone
                              previewUrl={claimImagePreview}
                              file={claimImage}
                              inputRef={claimImageInputRef}
                              accept="image/jpeg,image/png,image/webp"
                              hint="PNG, JPG, or WEBP"
                              onSelect={(file) =>
                                 selectImage(file, setClaimImage, setClaimImagePreview, claimImageInputRef)
                              }
                              onRemove={() => clearFile(setClaimImage, claimImageInputRef, setClaimImagePreview)}
                              previewAlt="Selected claim image preview"
                           />
                           <button
                              type="button"
                              className="verify-submit-btn full-width"
                              onClick={handleImageVerify}
                              disabled={loading || !claimImage}
                           >
                              <Icons name="scan-line" size={16} aria-hidden="true" />
                              Verify image claim
                           </button>
                        </>
                     )}

                     {activeTab === "file" && (
                        <>
                           <PanelHeading
                              icon="file"
                              title="Verify claims in a document"
                              description="Upload a supported document so TruthLens can extract and analyze its claims."
                           />
                           <UploadZone
                              file={docFile}
                              inputRef={docFileInputRef}
                              accept=".pdf,.docx,.txt"
                              hint="PDF, DOCX, or TXT"
                              onSelect={selectDocument}
                              onRemove={() => clearFile(setDocFile, docFileInputRef)}
                           />
                           <button
                              type="button"
                              className="verify-submit-btn full-width"
                              onClick={handleFileVerify}
                              disabled={loading || !docFile}
                           >
                              <Icons name="scan-line" size={16} aria-hidden="true" />
                              Verify document
                           </button>
                        </>
                     )}

                     {activeTab === "deepfake" && (
                        <>
                           <PanelHeading
                              icon="sparkles"
                              title="Check for AI-generated image signals"
                              description="Estimate whether an image contains patterns associated with AI generation. This does not verify the image's claim."
                              tone="media"
                           />
                           <UploadZone
                              previewUrl={mediaImagePreview}
                              file={mediaImage}
                              inputRef={mediaImageInputRef}
                              accept="image/jpeg,image/png,image/webp"
                              hint="PNG, JPG, or WEBP"
                              onSelect={(file) =>
                                 selectImage(file, setMediaImage, setMediaImagePreview, mediaImageInputRef)
                              }
                              onRemove={() => clearFile(setMediaImage, mediaImageInputRef, setMediaImagePreview)}
                              previewAlt="Selected media preview"
                           />
                           <button
                              type="button"
                              className="verify-submit-btn full-width"
                              onClick={handleDeepfakeTest}
                              disabled={loading || !mediaImage}
                           >
                              <Icons name="scan-line" size={16} aria-hidden="true" />
                              Check for AI-generated image signals
                           </button>
                           <p className="panel-hint">
                              Automated image detection is one signal, not proof of authenticity or manipulation.
                           </p>
                        </>
                     )}
                  </section>
               </div>

               {result && !loading && (
                  <div ref={resultRef} className="verify-body-right verify-result-animator" tabIndex="-1">
                     {result.isDeepfakeTest ? <DeepfakeResult result={result} /> : <ResultCard result={result} />}
                  </div>
               )}
            </div>
         </main>
      </div>
   );
}

const readFileAsDataUrl = (file) =>
   new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(new Error("The selected file could not be read."));
      reader.readAsDataURL(file);
   });

const PanelHeading = ({ icon, title, description, tone = "claim" }) => (
   <header className={`panel-heading panel-heading--${tone}`}>
      <span className="panel-heading-icon" aria-hidden="true">
         <Icons name={icon} size={18} />
      </span>
      <div>
         <h2>{title}</h2>
         <p>{description}</p>
      </div>
   </header>
);

const SubmitButton = ({ loading, disabled, label }) => (
   <button type="submit" className="verify-submit-btn" disabled={loading || disabled}>
      <Icons name="search" size={16} aria-hidden="true" />
      {label}
   </button>
);

const UploadZone = ({ previewUrl, file, inputRef, accept, hint, onSelect, onRemove, previewAlt }) => {
   const handleDrop = (event) => {
      event.preventDefault();
      onSelect(event.dataTransfer.files?.[0]);
   };

   return (
      <div
         className={`upload-zone ${file ? "has-file" : ""}`}
         onDrop={handleDrop}
         onDragOver={(event) => event.preventDefault()}
      >
         {file ? (
            <div className="upload-preview">
               {previewUrl ? (
                  <img src={previewUrl} alt={previewAlt} className="image-preview" />
               ) : (
                  <div className="file-preview-box">
                     <Icons name="file-text" size={32} aria-hidden="true" />
                     <p className="file-name">{file.name}</p>
                     <p className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                  </div>
               )}
               <button type="button" className="remove-file-btn" onClick={onRemove}>
                  <Icons name="x" size={15} aria-hidden="true" />
                  Remove file
               </button>
            </div>
         ) : (
            <button type="button" className="upload-zone-trigger" onClick={() => inputRef.current?.click()}>
               <span className="upload-zone-icon" aria-hidden="true">
                  <Icons name="upload" size={24} />
               </span>
               <span className="upload-zone-title">Drop a file here or choose from your device</span>
               <span className="upload-zone-hint">{hint}</span>
            </button>
         )}
         <input
            ref={inputRef}
            type="file"
            accept={accept}
            className="hidden-file-input"
            tabIndex={-1}
            onChange={(event) => onSelect(event.target.files?.[0])}
         />
      </div>
   );
};

export default VerifyPage;
