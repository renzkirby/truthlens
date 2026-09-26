/**
 * Create Thread Page
 *
 * Opens a community discussion around an existing claim. The selected
 * escalation reason records the author's declared investigation focus; it
 * does not change the AI assessment or create an authoritative verdict.
 */

import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import Icons from "../components/Icons.jsx";
import { useAuth } from "../hooks/useAuth";
import { ESCALATION_OPTIONS } from "../utils/constants";
import { resolveApiEndpoint } from "../utils/api";
import { getAiVerdict } from "../utils/verdict";
import "./CreateThreadPage.css";

function formatEnumLabel(value, fallback = "Not available") {
   if (!value) return fallback;
   return String(value)
      .toLowerCase()
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
}

function normalizeHttpUrl(value) {
   if (typeof value !== "string") return "";
   const normalized = value.trim();
   return /^https?:\/\//i.test(normalized) ? normalized : "";
}

function ClaimMaterialPreview({ claim }) {
   const claimType = String(claim?.claim_type || "").toUpperCase();
   const mediaUrl = typeof claim?.media_url === "string" ? claim.media_url.trim() : "";

   // Input provenance is intentionally type-specific. `canonical_source_url`,
   // `source_link`, and `top_verdict_source` may point to evidence discovered
   // during AI verification, so they must not be presented as submitted material.
   const submittedImageUrl = claimType === "IMAGE" ? mediaUrl : "";
   const submittedUrl = claimType === "URL" ? normalizeHttpUrl(claim?.url_link) : "";
   const hasMaterial = Boolean(submittedImageUrl || submittedUrl);

   if (!hasMaterial) return null;

   return (
      <div className="create-thread-material" role="group" aria-labelledby="create-thread-material-title">
         <div className="create-thread-material-heading">
            <span id="create-thread-material-title">Submitted material</span>
            <small>Included with the original claim</small>
         </div>

         {submittedImageUrl && (
            <a
               className="create-thread-material-media"
               href={submittedImageUrl}
               target="_blank"
               rel="noopener noreferrer"
               aria-label="Open submitted image in a new tab"
            >
               <img src={submittedImageUrl} alt="Submitted claim" loading="lazy" decoding="async" />
            </a>
         )}

         {submittedUrl && (
            <a
               className="create-thread-material-link"
               href={submittedUrl}
               target="_blank"
               rel="noopener noreferrer"
            >
               <span className="create-thread-material-link-icon" aria-hidden="true">
                  <Icons name="link" size={16} />
               </span>
               <span className="create-thread-material-url">{submittedUrl}</span>
               <span aria-hidden="true"><Icons name="external-link" size={14} /></span>
            </a>
         )}
      </div>
   );
}

function CreateThreadSkeleton() {
   return (
      <div className="create-thread-content-grid create-thread-skeleton" aria-busy="true">
         <span className="create-thread-sr-only" role="status" aria-live="polite">
            Loading claim and AI assessment…
         </span>
         <div className="create-thread-primary-column" aria-hidden="true">
            <div className="create-thread-panel create-thread-skeleton-panel">
               <span className="create-thread-skeleton-line create-thread-skeleton-line--short" />
               <span className="create-thread-skeleton-line create-thread-skeleton-line--long" />
               <span className="create-thread-skeleton-block create-thread-skeleton-block--claim" />
            </div>
            <div className="create-thread-panel create-thread-skeleton-panel">
               <span className="create-thread-skeleton-line create-thread-skeleton-line--medium" />
               <span className="create-thread-skeleton-line create-thread-skeleton-line--long" />
               <span className="create-thread-skeleton-block create-thread-skeleton-block--textarea" />
            </div>
            <div className="create-thread-panel create-thread-skeleton-panel">
               <span className="create-thread-skeleton-line create-thread-skeleton-line--medium" />
               <span className="create-thread-skeleton-line create-thread-skeleton-line--long" />
               <div className="create-thread-skeleton-options">
                  {[1, 2, 3, 4, 5].map((item) => (
                     <span key={item} className="create-thread-skeleton-block create-thread-skeleton-block--option" />
                  ))}
               </div>
            </div>
            <span className="create-thread-skeleton-block create-thread-skeleton-block--button" />
         </div>

         <aside className="create-thread-supporting-column" aria-hidden="true">
            <div className="create-thread-panel create-thread-skeleton-panel">
               <span className="create-thread-skeleton-line create-thread-skeleton-line--short" />
               <span className="create-thread-skeleton-block create-thread-skeleton-block--metric" />
               <span className="create-thread-skeleton-block create-thread-skeleton-block--metric" />
               <span className="create-thread-skeleton-block create-thread-skeleton-block--summary" />
            </div>
            <div className="create-thread-panel create-thread-skeleton-panel">
               <span className="create-thread-skeleton-line create-thread-skeleton-line--medium" />
               <span className="create-thread-skeleton-line create-thread-skeleton-line--long" />
               <span className="create-thread-skeleton-line create-thread-skeleton-line--long" />
            </div>
         </aside>
      </div>
   );
}

function CreateThreadPage() {
   const [loading, setLoading] = useState(true);
   const [submitting, setSubmitting] = useState(false);
   const [claim, setClaim] = useState(null);
   const [error, setError] = useState("");
   const [existingThread, setExistingThread] = useState(null);
   const [searchParams] = useSearchParams();
   const claimId = searchParams.get("claim_id");
   const { authFetch } = useAuth();
   const navigate = useNavigate();
   const [formValues, setFormValues] = useState({
      caption: "",
      escalation_reason: "",
      other_concern: "",
   });

   const handleCaptionChange = (event) => {
      setFormValues((current) => ({ ...current, caption: event.target.value }));
   };

   const handleOtherConcernChange = (event) => {
      setFormValues((current) => ({ ...current, other_concern: event.target.value }));
      setError("");
   };

   const handleReasonSelect = (value) => {
      setFormValues((current) => ({ ...current, escalation_reason: value }));
      setError("");
   };

   const handleSubmit = async (event) => {
      event.preventDefault();

      if (!formValues.escalation_reason) {
         setError("Choose the main reason for community review before starting the discussion.");
         return;
      }

      const otherConcern = formValues.other_concern.trim();
      if (formValues.escalation_reason === "OTHER" && !otherConcern) {
         setError("Describe the other concern before starting the discussion.");
         return;
      }

      const discussionContext = formValues.caption.trim();
      const caption = formValues.escalation_reason === "OTHER"
         ? [discussionContext, `Other concern: ${otherConcern}`].filter(Boolean).join("\n\n")
         : discussionContext;

      setSubmitting(true);
      setError("");
      try {
         const responseData = await authFetch(resolveApiEndpoint("THREADS"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               claim_id: claimId,
               caption,
               escalation_reason: formValues.escalation_reason,
            }),
         });
         navigate(`/thread/detail/${responseData.id}`);
      } catch (requestError) {
         if (requestError?.existing_thread_id && requestError?.redirect) {
            setExistingThread(requestError.existing_thread_id);
            setError("");
            return;
         }
         setError("We couldn't start the community discussion. Please try again.");
      } finally {
         setSubmitting(false);
      }
   };

   useEffect(() => {
      setLoading(true);
      setClaim(null);
      setExistingThread(null);
      setError("");
      setFormValues({
         caption: "",
         escalation_reason: "",
         other_concern: "",
      });

      if (!claimId) {
         setError("This page needs a claim to start a community discussion.");
         setLoading(false);
         return;
      }

      let active = true;

      const fetchClaimData = async () => {
         try {
            const claimUrl = `${resolveApiEndpoint("CLAIMS")}${claimId}/`;
            const claimData = await authFetch(claimUrl, { method: "GET" });
            if (!active) return;
            setClaim(claimData);

            try {
               const threadsData = await authFetch(
                  `${resolveApiEndpoint("THREADS")}?claim_id=${claimId}`,
                  { method: "GET" },
               );
               if (!active) return;
               const threads = threadsData?.results || threadsData || [];
               if (Array.isArray(threads) && threads.length > 0) {
                  setExistingThread(threads[0].id);
               }
            } catch (threadError) {
               console.warn("Thread pre-check failed:", threadError);
            }
         } catch (requestError) {
            console.error("Failed to fetch claim data:", requestError);
            if (active) {
               setError("We couldn't load this claim. Return to Community and try again.");
            }
         } finally {
            if (active) setLoading(false);
         }
      };

      fetchClaimData();
      return () => {
         active = false;
      };
   }, [claimId, authFetch]);

   const aiVerdict = getAiVerdict(claim);
   const aiVerdictClass = String(aiVerdict || "unavailable").toLowerCase().replace(/[^a-z0-9-]/g, "-");
   const confidence = Number(claim?.consensus_score);
   const hasConfidence = claim?.consensus_score !== null
      && claim?.consensus_score !== undefined
      && Number.isFinite(confidence);
   const boundedConfidence = hasConfidence ? Math.max(0, Math.min(100, confidence)) : 0;
   const otherConcernRequired = formValues.escalation_reason === "OTHER";
   const canSubmit = Boolean(
      formValues.escalation_reason
      && (!otherConcernRequired || formValues.other_concern.trim()),
   );

   return (
      <div className="create-thread-layout">
         <nav className="create-thread-topbar" aria-label="Breadcrumb">
            <div className="create-thread-breadcrumb">
               <Link to="/community" className="create-thread-breadcrumb-link">
                  <span aria-hidden="true"><Icons name="globe" size={14} /></span>
                  Community Feed
               </Link>
               <span className="create-thread-breadcrumb-separator" aria-hidden="true">
                  <Icons name="chevron-right" size={14} />
               </span>
               <span aria-current="page">Escalate to community</span>
            </div>
         </nav>

         <main className="create-thread-container">
            <header className="create-thread-header">
               <h1>Escalate to community</h1>
               <p>
                  Open a focused discussion where contributors can add evidence and context about this claim.
               </p>
            </header>

            {loading && <CreateThreadSkeleton />}

            {!loading && error && (
               <div className="create-thread-notice create-thread-notice--error" role="alert">
                  <span className="create-thread-notice-icon" aria-hidden="true">
                     <Icons name="alert-triangle" size={18} />
                  </span>
                  <div>
                     <strong>We couldn't continue</strong>
                     <p>{error}</p>
                  </div>
               </div>
            )}

            {!loading && existingThread && (
               <section className="create-thread-existing" aria-labelledby="create-thread-existing-title">
                  <span className="create-thread-existing-icon" aria-hidden="true">
                     <Icons name="message-square" size={20} />
                  </span>
                  <div className="create-thread-existing-copy">
                     <h2 id="create-thread-existing-title">Community discussion already exists</h2>
                     <p>
                        This claim already has a community discussion. Open the existing thread to review its status
                        and contribute where available.
                     </p>
                  </div>
                  <Link className="create-thread-existing-link" to={`/thread/detail/${existingThread}`}>
                     View existing discussion
                     <span aria-hidden="true"><Icons name="arrow-right" size={16} /></span>
                  </Link>
               </section>
            )}

            {!loading && claim && !existingThread && (
               <form className="create-thread-content-grid" onSubmit={handleSubmit} noValidate>
                  <div className="create-thread-primary-column">
                     <section className="create-thread-panel create-thread-claim" aria-labelledby="create-thread-claim-title">
                        <div className="create-thread-section-heading">
                           <h2 id="create-thread-claim-title">Claim being discussed</h2>
                           {claim.claim_type && (
                              <span className="create-thread-claim-type">{formatEnumLabel(claim.claim_type)}</span>
                           )}
                        </div>
                        <p className="create-thread-claim-text">
                           {claim.context_text?.trim() || "Claim context is not available."}
                        </p>
                        <ClaimMaterialPreview claim={claim} />
                     </section>

                     <section className="create-thread-panel" aria-labelledby="create-thread-context-title">
                        <div className="create-thread-section-heading create-thread-section-heading--stacked">
                           <h2 id="create-thread-context-title">Your discussion context</h2>
                           <p id="create-thread-caption-help">
                              Add context, a concern, or a question that can help guide the discussion. Optional.
                           </p>
                        </div>
                        <label className="create-thread-field-label" htmlFor="create-thread-caption">
                           What would you like the community to examine?
                        </label>
                        <textarea
                           id="create-thread-caption"
                           name="caption"
                           className="create-thread-textarea"
                           onChange={handleCaptionChange}
                           value={formValues.caption}
                           rows={5}
                           aria-describedby="create-thread-caption-help"
                           placeholder="Add context or a question for the community..."
                        />
                     </section>

                     <section
                        className="create-thread-panel create-thread-reasons"
                        aria-labelledby="create-thread-reason-title"
                        aria-describedby="create-thread-reason-help"
                     >
                        <div className="create-thread-section-heading create-thread-reasons-heading">
                           <h2 id="create-thread-reason-title">What needs further review?</h2>
                           <span className="create-thread-required">Required</span>
                        </div>
                        <p id="create-thread-reason-help" className="create-thread-section-helper">
                           Choose the main reason you're bringing this claim to the community. This helps contributors
                           understand what to examine.
                        </p>
                        <div className="create-thread-reason-options">
                           {ESCALATION_OPTIONS.map((option) => {
                              const selected = formValues.escalation_reason === option.value;
                              return (
                                 <button
                                    key={option.value}
                                    type="button"
                                    className={`create-thread-reason-option${selected ? " is-selected" : ""}`}
                                    aria-pressed={selected}
                                    onClick={() => handleReasonSelect(option.value)}
                                 >
                                    <span className="create-thread-reason-icon" aria-hidden="true">
                                       <Icons name={option.icon} size={18} />
                                    </span>
                                    <span className="create-thread-reason-copy">
                                       <strong>{option.label}</strong>
                                       <span>{option.desc}</span>
                                    </span>
                                    <span className="create-thread-reason-state" aria-hidden="true">
                                       {selected ? <Icons name="check-circle" size={19} /> : <Icons name="circle" size={19} />}
                                    </span>
                                 </button>
                              );
                           })}
                        </div>

                        {otherConcernRequired && (
                           <div className="create-thread-other-concern">
                              <label htmlFor="create-thread-other-concern">
                                 Describe the other concern
                                 <span className="create-thread-required create-thread-required--inline">Required</span>
                              </label>
                              <textarea
                                 id="create-thread-other-concern"
                                 name="other_concern"
                                 className="create-thread-textarea create-thread-textarea--compact"
                                 value={formValues.other_concern}
                                 onChange={handleOtherConcernChange}
                                 rows={3}
                                 required
                                 maxLength={500}
                                 aria-describedby="create-thread-other-concern-help"
                                 placeholder="Briefly explain what else the community should examine..."
                              />
                              <p id="create-thread-other-concern-help">
                                 This explanation will appear in the thread as community context.
                              </p>
                           </div>
                        )}
                     </section>

                     <div className="create-thread-actions">
                        <button
                           type="button"
                           className="create-thread-cancel"
                           onClick={() => navigate("/community")}
                           disabled={submitting}
                        >
                           Cancel
                        </button>
                        <button
                           type="submit"
                           className="create-thread-submit"
                           disabled={submitting || !canSubmit}
                           aria-busy={submitting}
                           aria-live="polite"
                        >
                           {submitting ? (
                              <>
                                 <span className="create-thread-spinner" aria-hidden="true" />
                                 Starting discussion…
                              </>
                           ) : (
                              <>
                                 <span aria-hidden="true"><Icons name="send" size={17} /></span>
                                 Start community discussion
                              </>
                           )}
                        </button>
                     </div>
                  </div>

                  <aside className="create-thread-supporting-column" aria-label="Supporting claim context">
                     <section className="create-thread-panel create-thread-ai" aria-labelledby="create-thread-ai-title">
                        <div className="create-thread-ai-heading">
                           <div>
                              <h2 id="create-thread-ai-title">AI assessment</h2>
                              <p>Generated by TruthLens AI</p>
                           </div>
                           <span className="create-thread-ai-badge">AI</span>
                        </div>

                        <dl className="create-thread-ai-metrics">
                           <div>
                              <dt>AI verdict</dt>
                              <dd className={`create-thread-ai-verdict create-thread-ai-verdict--${aiVerdictClass}`}>
                                 {formatEnumLabel(aiVerdict)}
                              </dd>
                           </div>
                           <div>
                              <dt>AI confidence</dt>
                              <dd>{hasConfidence ? `${Math.round(boundedConfidence)}%` : "Not available"}</dd>
                           </div>
                        </dl>

                        {hasConfidence && (
                           <progress
                              className="create-thread-confidence"
                              value={boundedConfidence}
                              max="100"
                              aria-label={`AI confidence ${Math.round(boundedConfidence)} percent`}
                           />
                        )}

                        <div className="create-thread-ai-summary">
                           <h3>AI analysis summary</h3>
                           <p>{claim.ai_summary?.trim() || "No AI analysis summary is available."}</p>
                        </div>
                        <p className="create-thread-ai-disclaimer">
                           This is AI-generated analysis. It is separate from community discussion, human adjudication,
                           and institutional publication.
                        </p>
                     </section>

                     <section className="create-thread-panel create-thread-explainer" aria-labelledby="create-thread-explainer-title">
                        <h2 id="create-thread-explainer-title">What escalation does</h2>
                        <ul>
                           <li>Opens a community discussion about this claim.</li>
                           <li>Lets contributors add evidence and context.</li>
                           <li>Does not change the claim assessment or create an authoritative verdict.</li>
                        </ul>
                     </section>
                  </aside>
               </form>
            )}
         </main>
      </div>
   );
}

export default CreateThreadPage;
