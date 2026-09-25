import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import Icons from "../components/Icons";
import { API_BASE_URL, VERDICT_META } from "../utils/constants";
import "./DeepAnalysisPage.css";

const SUPPORTED_VERDICTS = new Set(["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED", "OUT_OF_SCOPE", "PENDING"]);

const VERDICT_ICONS = {
   FACT: "check-circle",
   FAKE: "x-circle",
   MISLEADING: "alert-triangle",
   SATIRE: "wand",
   UNVERIFIED: "help-circle",
   OUT_OF_SCOPE: "alert-octagon",
   PENDING: "clock",
};

const buildClaimUrl = (claimId, suffix) => {
   const baseUrl = API_BASE_URL.replace(/\/$/, "");
   return `${baseUrl}/claims/${encodeURIComponent(claimId)}/${suffix}`;
};

const normalizeVerdict = (value, fallback = "UNVERIFIED") => {
   const normalized = typeof value === "string" ? value.trim().toUpperCase() : "";
   return SUPPORTED_VERDICTS.has(normalized) ? normalized : fallback;
};

const getVerdictMeta = (verdict) => {
   if (!verdict) return null;
   return VERDICT_META[verdict.toLowerCase()] || VERDICT_META.unverified;
};

const getSafeHttpUrl = (value) => {
   if (typeof value !== "string" || !value.trim()) return null;

   try {
      const parsed = new URL(value.trim());
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null;
      return parsed.toString();
   } catch {
      return null;
   }
};

const getDomain = (url) => {
   try {
      return new URL(url).hostname.replace(/^www\./i, "");
   } catch {
      return "External source";
   }
};

const normalizeSources = (sources) => {
   if (!Array.isArray(sources)) return [];

   const seen = new Set();

   return sources.reduce((normalizedSources, source) => {
      const isLegacySource = typeof source === "string";
      const rawUrl = isLegacySource ? source : source?.url;
      const url = getSafeHttpUrl(rawUrl);
      const title = !isLegacySource && typeof source?.title === "string" ? source.title.trim() : "";
      const snippet = !isLegacySource && typeof source?.snippet === "string" ? source.snippet.trim() : "";
      const domain = url ? getDomain(url) : "Link unavailable";
      const displayTitle = title || (url ? domain : "Source details unavailable");
      const dedupeKey = url
         ? url.replace(/#.*$/, "").replace(/\/$/, "").toLowerCase()
         : `${displayTitle}|${snippet}|${String(rawUrl || "")}`.toLowerCase();

      if (seen.has(dedupeKey)) return normalizedSources;
      seen.add(dedupeKey);

      normalizedSources.push({ url, title: displayTitle, snippet, domain });
      return normalizedSources;
   }, []);
};

const formatDate = (value) => {
   if (!value) return null;
   const parsed = new Date(value);
   if (Number.isNaN(parsed.getTime())) return null;

   return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
   }).format(parsed);
};

const formatClaimType = (value) => {
   if (typeof value !== "string" || !value.trim()) return null;
   return value
      .trim()
      .toLowerCase()
      .replace(/_/g, " ")
      .replace(/^./, (character) => character.toUpperCase());
};

const getConfidence = (value) => {
   if (value === null || value === undefined || value === "") return null;
   const numericValue = Number(value);
   if (!Number.isFinite(numericValue)) return null;
   return Math.min(100, Math.max(0, numericValue));
};

function VerdictBadge({ verdict, labelPrefix }) {
   const meta = getVerdictMeta(verdict);
   if (!meta) return null;

   return (
      <span className="deep-analysis-verdict-badge" data-verdict={verdict.toLowerCase()}>
         <Icons name={VERDICT_ICONS[verdict] || "help-circle"} size={15} aria-hidden="true" />
         {labelPrefix && <span className="deep-analysis-verdict-prefix">{labelPrefix}</span>}
         <span>{meta.label}</span>
      </span>
   );
}

function ResilientImage({ src, alt, className, fallback }) {
   const [failedSrc, setFailedSrc] = useState(null);
   const hasFailed = Boolean(src && failedSrc === src);

   if (!src || hasFailed) return fallback || null;

   return (
      <img
         src={src}
         alt={alt}
         className={className}
         loading="lazy"
         decoding="async"
         onError={() => setFailedSrc(src)}
      />
   );
}

function OrganizationIdentity({ organization, compact = false }) {
   if (!organization?.name) return null;

   const logoUrl = getSafeHttpUrl(organization.logo_url);
   const fallback = (
      <span className="deep-analysis-organization-logo-fallback" aria-hidden="true">
         <Icons name="landmark" size={compact ? 16 : 20} />
      </span>
   );

   return (
      <div className={`deep-analysis-organization ${compact ? "deep-analysis-organization--compact" : ""}`}>
         <ResilientImage
            src={logoUrl}
            alt={`${organization.name} logo`}
            className="deep-analysis-organization-logo"
            fallback={fallback}
         />
         <div>
            <span className="deep-analysis-organization-label">Published by</span>
            <strong>{organization.name}</strong>
         </div>
      </div>
   );
}

function PublicationSources({ sources }) {
   const normalizedSources = useMemo(() => normalizeSources(sources), [sources]);
   if (normalizedSources.length === 0) return null;

   return (
      <div className="deep-analysis-publication-sources">
         <h3>Published sources</h3>
         <ul>
            {normalizedSources.map((source, index) => (
               <li key={`${source.url || source.title}-${index}`}>
                  {source.url ? (
                     <a href={source.url} target="_blank" rel="noopener noreferrer">
                        <span>{source.title}</span>
                        <Icons name="external-link" size={14} aria-hidden="true" />
                     </a>
                  ) : (
                     <span>{source.title}</span>
                  )}
               </li>
            ))}
         </ul>
      </div>
   );
}

function ResolutionContext({ statusData }) {
   const resolutionSource = statusData?.resolution_source;

   if (!resolutionSource || resolutionSource === "AI") return null;

   if (resolutionSource === "COMMUNITY_THREAD") {
      const threadId = statusData.thread_id;

      return (
         <section
            className="deep-analysis-resolution deep-analysis-resolution--community"
            aria-labelledby="resolution-heading"
         >
            <div className="deep-analysis-resolution-icon" aria-hidden="true">
               <Icons name="message-square" size={22} />
            </div>
            <div className="deep-analysis-resolution-content">
               <p className="deep-analysis-provenance-label">Current resolution context</p>
               <h2 id="resolution-heading">Community discussion available</h2>
               <p>
                  A community thread is available for this claim. The discussion is separate from the automated
                  assessment below and does not change the AI conclusion.
               </p>
               {threadId && (
                  <Link className="deep-analysis-text-action" to={`/thread/detail/${encodeURIComponent(threadId)}`}>
                     View community discussion
                     <Icons name="arrow-right" size={16} aria-hidden="true" />
                  </Link>
               )}
            </div>
         </section>
      );
   }

   if (resolutionSource === "ADJUDICATION") {
      const adjudicatedVerdict = normalizeVerdict(statusData.final_verdict || statusData.verdict, null);

      return (
         <section
            className="deep-analysis-resolution deep-analysis-resolution--human"
            aria-labelledby="resolution-heading"
         >
            <div className="deep-analysis-resolution-icon" aria-hidden="true">
               <Icons name="user-check" size={22} />
            </div>
            <div className="deep-analysis-resolution-content">
               <p className="deep-analysis-provenance-label">Current resolution context</p>
               <div className="deep-analysis-resolution-heading-row">
                  <h2 id="resolution-heading">Human adjudication</h2>
                  {adjudicatedVerdict && <VerdictBadge verdict={adjudicatedVerdict} />}
               </div>
               <p>
                  An accountable human decision is available for this claim. It is shown separately from the AI report,
                  whose summary, rationale, and confidence remain automated analysis.
               </p>
            </div>
         </section>
      );
   }

   if (resolutionSource === "OFFICIAL_FACT_CHECK" && statusData.official_fact_check) {
      const factCheck = statusData.official_fact_check;
      const organization = factCheck.organization;
      const publishedVerdict = normalizeVerdict(factCheck.verdict || statusData.verdict, null);
      const publishedDate = formatDate(factCheck.published_at);
      const canOpenPublication = Boolean(
         organization?.public_profile_available && organization?.slug && factCheck.fact_check_id,
      );

      return (
         <section
            className="deep-analysis-resolution deep-analysis-resolution--published"
            aria-labelledby="resolution-heading"
         >
            <div className="deep-analysis-resolution-icon" aria-hidden="true">
               <Icons name="newspaper" size={22} />
            </div>
            <div className="deep-analysis-resolution-content">
               <p className="deep-analysis-provenance-label">Current resolution context</p>
               <div className="deep-analysis-resolution-heading-row">
                  <h2 id="resolution-heading">Published fact-check</h2>
                  {publishedVerdict && <VerdictBadge verdict={publishedVerdict} />}
               </div>

               <OrganizationIdentity organization={organization} />
               {factCheck.headline && <h3 className="deep-analysis-publication-headline">{factCheck.headline}</h3>}
               {factCheck.summary && <p className="deep-analysis-publication-summary">{factCheck.summary}</p>}
               {publishedDate && <p className="deep-analysis-publication-date">Published {publishedDate}</p>}
               <PublicationSources sources={factCheck.sources} />

               {canOpenPublication && (
                  <Link
                     className="deep-analysis-primary-action"
                     to={`/partners/${encodeURIComponent(organization.slug)}/fact-checks/${encodeURIComponent(factCheck.fact_check_id)}`}
                  >
                     Read published fact-check
                     <Icons name="arrow-right" size={16} aria-hidden="true" />
                  </Link>
               )}
            </div>
         </section>
      );
   }

   return null;
}

function DeepAnalysisSkeleton() {
   return (
      <main className="deep-analysis-page" aria-busy="true">
         <div className="deep-analysis-shell deep-analysis-loading" role="status" aria-live="polite">
            <span className="deep-analysis-visually-hidden">Loading AI analysis report</span>
            <div className="deep-analysis-skeleton-toolbar" aria-hidden="true">
               <span className="deep-analysis-skeleton deep-analysis-skeleton--back" />
               <span className="deep-analysis-skeleton deep-analysis-skeleton--meta" />
            </div>
            <article className="deep-analysis-skeleton-report" aria-hidden="true">
               <div className="deep-analysis-skeleton-header">
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--label" />
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--title" />
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--subtitle" />
               </div>
               <div className="deep-analysis-skeleton-section">
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--section-title" />
                  <div className="deep-analysis-skeleton-assessment">
                     <span className="deep-analysis-skeleton deep-analysis-skeleton--verdict" />
                     <div>
                        <span className="deep-analysis-skeleton deep-analysis-skeleton--line" />
                        <span className="deep-analysis-skeleton deep-analysis-skeleton--line-short" />
                        <span className="deep-analysis-skeleton deep-analysis-skeleton--block" />
                     </div>
                  </div>
               </div>
               <div className="deep-analysis-skeleton-section deep-analysis-skeleton-section--compact">
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--section-title" />
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--line" />
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--line" />
                  <span className="deep-analysis-skeleton deep-analysis-skeleton--line-short" />
               </div>
            </article>
         </div>
      </main>
   );
}

function DeepAnalysisPage() {
   const { claimId } = useParams();
   const navigate = useNavigate();
   const { authFetch } = useAuth();
   const [claimData, setClaimData] = useState(null);
   const [statusData, setStatusData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(false);
   const [requestVersion, setRequestVersion] = useState(0);

   useEffect(() => {
      let active = true;

      queueMicrotask(() => {
         if (!active) return;
         setClaimData(null);
         setStatusData(null);
         setError(false);
         setLoading(true);
      });

      const analysisRequest = authFetch(buildClaimUrl(claimId, "analysis/"), { method: "GET" });
      const statusRequest = authFetch(buildClaimUrl(claimId, "status"), { method: "GET" });

      statusRequest
         .then((data) => {
            if (active && data && typeof data === "object") setStatusData(data);
         })
         .catch(() => {
            if (active) setStatusData(null);
         });

      analysisRequest
         .then((data) => {
            if (!active) return;

            if (!data || typeof data !== "object") {
               setError(true);
               return;
            }

            setClaimData(data);
         })
         .catch(() => {
            if (active) setError(true);
         })
         .finally(() => {
            if (active) setLoading(false);
         });

      return () => {
         active = false;
      };
   }, [authFetch, claimId, requestVersion]);

   const handleBack = () => {
      if (window.history.state?.idx > 0) {
         navigate(-1);
      } else {
         navigate("/verify");
      }
   };

   if (loading) return <DeepAnalysisSkeleton />;

   if (error || !claimData) {
      return (
         <main className="deep-analysis-page">
            <div className="deep-analysis-shell deep-analysis-error-shell">
               <button type="button" className="deep-analysis-back-button" onClick={handleBack}>
                  <Icons name="arrow-left" size={17} aria-hidden="true" />
                  Back
               </button>
               <section className="deep-analysis-error" role="alert" aria-live="assertive">
                  <span className="deep-analysis-error-icon" aria-hidden="true">
                     <Icons name="alert-triangle" size={24} />
                  </span>
                  <h1>We couldn&apos;t load this analysis report</h1>
                  <p>
                     The report may be temporarily unavailable. Try again, or return to Verify to check another claim.
                  </p>
                  <div className="deep-analysis-error-actions">
                     <button
                        type="button"
                        className="deep-analysis-primary-action"
                        onClick={() => setRequestVersion((version) => version + 1)}
                     >
                        <Icons name="refresh-cw" size={16} aria-hidden="true" />
                        Retry
                     </button>
                     <Link className="deep-analysis-secondary-action" to="/verify">
                        Back to Verify
                     </Link>
                  </div>
               </section>
            </div>
         </main>
      );
   }

   const aiVerdict = normalizeVerdict(claimData.ai_verdict);
   const aiSources = normalizeSources(claimData.ai_sources);
   const confidence = getConfidence(claimData.consensus_score);
   const claimType = formatClaimType(claimData.claim_type);
   const rawClaimType = typeof claimData.claim_type === "string" ? claimData.claim_type.trim().toUpperCase() : "";
   const updatedDate = formatDate(claimData.last_updated);
   const originalUrl = rawClaimType === "URL" ? getSafeHttpUrl(claimData.url_link) : null;
   const originalMediaUrl = rawClaimType === "IMAGE" ? getSafeHttpUrl(claimData.media_url) : null;
   const hasOriginalMaterial = Boolean(originalUrl || originalMediaUrl);
   const relatedFactChecks = Array.isArray(statusData?.related_fact_checks) ? statusData.related_fact_checks : [];

   return (
      <main className="deep-analysis-page" id="main-content">
         <div className="deep-analysis-shell">
            <nav className="deep-analysis-toolbar" aria-label="Analysis report navigation">
               <button type="button" className="deep-analysis-back-button" onClick={handleBack}>
                  <Icons name="arrow-left" size={17} aria-hidden="true" />
                  Back
               </button>
               <div className="deep-analysis-toolbar-meta">
                  <span>Automated report</span>
                  {updatedDate && <span>Updated {updatedDate}</span>}
               </div>
            </nav>

            <article className="deep-analysis-report" aria-labelledby="deep-analysis-title">
               <header className="deep-analysis-report-header">
                  <div className="deep-analysis-title-row">
                     <div>
                        <h1 id="deep-analysis-title">AI analysis report</h1>
                        <p>An automated assessment of the submitted claim and the evidence considered by the model.</p>
                     </div>
                     <span className="deep-analysis-ai-label">
                        <Icons name="sparkles" size={15} aria-hidden="true" />
                        AI-assisted assessment
                     </span>
                  </div>

                  <section className="deep-analysis-claim" aria-labelledby="claim-analyzed-heading">
                     <div className="deep-analysis-section-heading">
                        <div>
                           <h2 id="claim-analyzed-heading">Claim analyzed</h2>
                           <p>The text or context evaluated by the automated analysis.</p>
                        </div>
                        {claimType && <span className="deep-analysis-claim-type">{claimType}</span>}
                     </div>
                     <blockquote>
                        {claimData.context_text || "No claim text is available for this analysis."}
                     </blockquote>
                  </section>
               </header>

               <ResolutionContext statusData={statusData} />

               <section className="deep-analysis-section" aria-labelledby="ai-assessment-heading">
                  <div className="deep-analysis-section-heading">
                     <div>
                        <h2 id="ai-assessment-heading">AI assessment</h2>
                        <p>This section contains automated output, not a human or institutional decision.</p>
                     </div>
                  </div>

                  <div className="deep-analysis-assessment">
                     <div className="deep-analysis-assessment-verdict">
                        <span className="deep-analysis-field-label">AI verdict</span>
                        <VerdictBadge verdict={aiVerdict} />
                        <p>Automated classification from the AI analysis.</p>
                     </div>

                     <div className="deep-analysis-assessment-details">
                        <div className="deep-analysis-assessment-block">
                           <h3>AI analysis summary</h3>
                           <p>{claimData.ai_summary || "No AI summary is available for this analysis."}</p>
                        </div>

                        <div className="deep-analysis-confidence-context-grid">
                           <div className="deep-analysis-confidence">
                              <div className="deep-analysis-confidence-heading">
                                 <h3>AI confidence</h3>
                                 <strong>{confidence === null ? "Not available" : `${Math.round(confidence)}%`}</strong>
                              </div>
                              {confidence !== null && (
                                 <div
                                    className="deep-analysis-confidence-track"
                                    role="meter"
                                    aria-label="AI confidence"
                                    aria-valuemin="0"
                                    aria-valuemax="100"
                                    aria-valuenow={Math.round(confidence)}
                                 >
                                    <span style={{ width: `${confidence}%` }} />
                                 </div>
                              )}
                              <p>
                                 Model confidence in this automated assessment. It is not human or institutional
                                 certainty.
                              </p>
                           </div>

                           <div className="deep-analysis-assessment-context">
                              <h3>AI assessment context</h3>
                              <p>
                                 {claimData.score_context ||
                                    "No additional AI assessment context is available for this analysis."}
                              </p>
                           </div>
                        </div>
                     </div>
                  </div>
               </section>

               <section className="deep-analysis-section" aria-labelledby="ai-rationale-heading">
                  <div className="deep-analysis-section-heading">
                     <div>
                        <h2 id="ai-rationale-heading">AI analysis rationale</h2>
                        <p>The model&apos;s detailed explanation for its automated assessment.</p>
                     </div>
                     <span className="deep-analysis-section-provenance">
                        <Icons name="brain-circuit" size={16} aria-hidden="true" />
                        AI analysis
                     </span>
                  </div>
                  <div
                     className={`deep-analysis-rationale ${claimData.ai_reasoning ? "" : "deep-analysis-rationale--empty"}`}
                  >
                     {claimData.ai_reasoning || "No detailed AI rationale is available for this analysis."}
                  </div>
               </section>

               <section className="deep-analysis-section" aria-labelledby="ai-sources-heading">
                  <div className="deep-analysis-section-heading">
                     <div>
                        <h2 id="ai-sources-heading">Sources considered by AI</h2>
                        <p>
                           These sources informed the automated assessment. Their inclusion does not independently
                           guarantee the verdict.
                        </p>
                     </div>
                     <span className="deep-analysis-source-count">
                        {aiSources.length} {aiSources.length === 1 ? "source" : "sources"}
                     </span>
                  </div>

                  {aiSources.length > 0 ? (
                     <ol className="deep-analysis-source-list">
                        {aiSources.map((source, index) => (
                           <li className="deep-analysis-source" key={`${source.url || source.title}-${index}`}>
                              <div className="deep-analysis-source-number" aria-hidden="true">
                                 {String(index + 1).padStart(2, "0")}
                              </div>
                              <div className="deep-analysis-source-body">
                                 <span className="deep-analysis-source-domain">{source.domain}</span>
                                 <h3>{source.title}</h3>
                                 {source.snippet && <p>{source.snippet}</p>}
                                 {source.url ? (
                                    <a href={source.url} target="_blank" rel="noopener noreferrer">
                                       Open source
                                       <Icons name="external-link" size={14} aria-hidden="true" />
                                    </a>
                                 ) : (
                                    <span className="deep-analysis-source-unavailable">
                                       No safe web link is available.
                                    </span>
                                 )}
                              </div>
                           </li>
                        ))}
                     </ol>
                  ) : (
                     <div className="deep-analysis-empty-state">
                        <Icons name="book-open" size={20} aria-hidden="true" />
                        <p>No AI source records are available for this analysis.</p>
                     </div>
                  )}
               </section>

               {hasOriginalMaterial && (
                  <section className="deep-analysis-section" aria-labelledby="original-material-heading">
                     <div className="deep-analysis-section-heading">
                        <div>
                           <h2 id="original-material-heading">
                              {rawClaimType === "URL" ? "Original source" : "Original material"}
                           </h2>
                           <p>
                              {rawClaimType === "URL"
                                 ? "The URL submitted for this verification."
                                 : "The image submitted for this verification."}
                           </p>
                        </div>
                     </div>

                     <div className="deep-analysis-original-material">
                        {originalMediaUrl && (
                           <div className="deep-analysis-media-frame">
                              <ResilientImage
                                 src={originalMediaUrl}
                                 alt="Image submitted for AI analysis"
                                 className="deep-analysis-media"
                                 fallback={
                                    <div className="deep-analysis-media-fallback">
                                       <Icons name="image" size={22} aria-hidden="true" />
                                       <span>The submitted image could not be displayed.</span>
                                    </div>
                                 }
                              />
                           </div>
                        )}

                        {originalUrl && (
                           <a
                              className="deep-analysis-original-link"
                              href={originalUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                           >
                              <span className="deep-analysis-original-link-icon" aria-hidden="true">
                                 <Icons name="link" size={18} />
                              </span>
                              <span>
                                 <small>Original source</small>
                                 <strong>{getDomain(originalUrl)}</strong>
                                 <span>{originalUrl}</span>
                              </span>
                              <Icons name="external-link" size={16} aria-hidden="true" />
                           </a>
                        )}
                     </div>
                  </section>
               )}

               {relatedFactChecks.length > 0 && (
                  <section className="deep-analysis-section" aria-labelledby="related-fact-checks-heading">
                     <div className="deep-analysis-section-heading">
                        <div>
                           <h2 id="related-fact-checks-heading">Related published fact-checks</h2>
                           <p>
                              These publications are available as related context. They are not presented as the current
                              resolution unless identified above as the published fact-check.
                           </p>
                        </div>
                     </div>

                     <div className="deep-analysis-related-list">
                        {relatedFactChecks.map((factCheck, index) => {
                           const organization = factCheck?.organization;
                           const publishedDate = formatDate(factCheck?.published_at);
                           const relatedVerdict = normalizeVerdict(factCheck?.verdict, null);
                           const canOpenFactCheck = Boolean(
                              organization?.public_profile_available && organization?.slug && factCheck?.fact_check_id,
                           );

                           return (
                              <article
                                 className="deep-analysis-related-item"
                                 key={factCheck?.fact_check_id || `${factCheck?.headline || "fact-check"}-${index}`}
                              >
                                 <div className="deep-analysis-related-meta">
                                    <OrganizationIdentity organization={organization} compact />
                                    {publishedDate && <span>{publishedDate}</span>}
                                 </div>
                                 <div className="deep-analysis-related-heading">
                                    <h3>{factCheck?.headline || "Published fact-check"}</h3>
                                    {relatedVerdict && <VerdictBadge verdict={relatedVerdict} />}
                                 </div>
                                 {factCheck?.summary && <p>{factCheck.summary}</p>}
                                 {canOpenFactCheck && (
                                    <Link
                                       className="deep-analysis-text-action"
                                       to={`/partners/${encodeURIComponent(organization.slug)}/fact-checks/${encodeURIComponent(factCheck.fact_check_id)}`}
                                    >
                                       Read published fact-check
                                       <Icons name="arrow-right" size={16} aria-hidden="true" />
                                    </Link>
                                 )}
                              </article>
                           );
                        })}
                     </div>
                  </section>
               )}
            </article>
         </div>
      </main>
   );
}

export default DeepAnalysisPage;
