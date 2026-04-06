/**
 * Create Thread Page
 * ══════════════════════════════════════════════════════════════════
 * User submits a claim to community for escalated discussion/evidence collection.
 *
 * Features:
 *   - Display AI analysis result for a claim
 *   - Flag reason selection (allows users to challenge/discuss AI verdict)
 *   - Caption and source URL input
 *   - Escalate to community discussion
 *
 * State:
 *   - Claim data (from URL parameter)
 *   - Form inputs: caption, source_url, escalation_reason
 *   - Submission state (loading, errors)
 */

import { useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons.jsx";

// ── Utilities & Constants ──
import { getAiVerdict } from "../utils/verdict";
import { VERDICT_CONFIG, VERDICT_OPTIONS, ESCALATION_OPTIONS, VERDICT_COLORS } from "../utils/constants";
import { useEndpoint } from "../utils/api";

// ── Styles ──
import "./CreateThreadPage.css";

function CreateThreadPage() {
   const [loading, setLoading] = useState(true);
   const [submitting, setSubmitting] = useState(false);
   const [claim, setClaim] = useState(null);
   const [error, setError] = useState(null);
   const [existingThread, setExistingThread] = useState(null);
   const [searchParams] = useSearchParams();
   const claimId = searchParams.get("claim_id");
   const { authFetch } = useAuth();
   const navigate = useNavigate();
   const [formValues, setFormValues] = useState({
      caption: "",
      source_url: "",
      escalation_reason: "",
   });

   /**
    * Handle form input changes (caption, source_url)
    * @param {Event} e - Input change event
    */
   const handleInputChange = (e) => {
      const { name, value } = e.target;
      setFormValues({
         ...formValues,
         [name]: value,
      });
   };

   /**
    * Handle flag reason selection
    * @param {string} value - Selected flag reason value
    */
   const handleFlagSelect = (value) => {
      setFormValues({ ...formValues, escalation_reason: value });
   };

   /**
    * Submit thread escalation to backend
    * Validates escalation_reason, creates thread with claim and form data
    */
   const handleSubmit = async () => {
      if (!formValues.escalation_reason) {
         setError("Please select a reason for escalating this thread before submitting.");
         return;
      }

      setSubmitting(true);
      setError(null);
      try {
         const url = useEndpoint("THREADS");
         const responseData = await authFetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               claim_id: claimId,
               caption: formValues.caption,
               escalation_reason: formValues.escalation_reason,
            }),
         });
         navigate(`/thread/detail/${responseData.id}`);
      } catch (err) {
         // Handle thread deduplication redirect
         if (err?.existing_thread_id && err?.redirect) {
            setExistingThread(err.existing_thread_id);
            setError(null);
            // Auto-redirect after a brief moment
            setTimeout(() => {
               navigate(`/thread/detail/${err.existing_thread_id}`);
            }, 3000);
            return;
         }
         setError(err?.detail || "Something went wrong in creating a thread.");
      } finally {
         setSubmitting(false);
      }
   };

   useEffect(() => {
      if (!claimId) {
         setError("No claim ID provided");
         setLoading(false);
         return;
      }
      const fetchClaimData = async () => {
         try {
            const claimUrl = useEndpoint("CLAIMS") + claimId + "/";
            const claimData = await authFetch(claimUrl, {
               method: "GET",
            });
            setClaim(claimData);
            setFormValues((prev) => ({
               ...prev,
               caption: claimData.ai_summary || "",
               source_url: claimData.source_link || "",
            }));

            // Check if this claim already has existing threads (pre-check dedup)
            try {
               const threadsUrl = useEndpoint("THREADS");
               const threadsData = await authFetch(threadsUrl + `?claim_id=${claimId}`, {
                  method: "GET",
               });
               // threadsData may be paginated (cursor-based), check results array
               const threads = threadsData?.results || threadsData || [];
               if (Array.isArray(threads) && threads.length > 0) {
                  // Found existing thread — set redirect
                  const existingId = threads[0].id;
                  setExistingThread(existingId);
               }
            } catch (threadErr) {
               // Non-critical — if thread check fails, we still allow the form
               console.warn("Thread pre-check failed:", threadErr);
            }

            console.log(claimData);
         } catch (err) {
            setError("Failed loading form");
         } finally {
            setLoading(false);
         }
      };
      fetchClaimData();
   }, [claimId]);

   const aiVerdict = getAiVerdict(claim);

   return (
      <div className="create-thread-layout">
         <NavigationBar />

         <div className="create-thread-topbar">
            <div className="breadcrumb">
               <Link
                  to="/community"
                  className="breadcrumb-link">
                  <Icons
                     name="globe"
                     size={14}
                  />
                  Community Feed
               </Link>
               <Icons
                  name="chevron-right"
                  size={14}
               />
               <span className="breadcrumb-current">Escalate a Claim</span>
            </div>
         </div>

         <main className="create-thread-container">
            <div className="create-thread-header">
               <div className="create-thread-icon">
                  <Icons
                     name="flag"
                     size={22}
                     color="#fff"
                  />
               </div>
               <div>
                  <h1 className="create-thread-title">Escalate to Community</h1>
                  <p className="create-thread-subtitle">
                     The AI couldn't verify this claim with confidence. Submit it to the community
                     for review.
                  </p>
               </div>
            </div>

            {loading && <p className="create-thread-loading">Loading claim data...</p>}
            {error && (
               <div className="create-thread-error">
                  <Icons
                     name="alert-triangle"
                     size={15}
                  />
                  {error}
               </div>
            )}

            {/* Thread Deduplication: Redirect Notice */}
            {existingThread && (
               <div style={{
                  backgroundColor: "#ecfdf5",
                  border: "1.5px solid #0e9f6e",
                  borderRadius: "12px",
                  padding: "20px 24px",
                  marginBottom: "20px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px",
               }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", color: "#065f46", fontWeight: 700, fontSize: "14px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                     <Icons name="info" size={16} />
                     A Community Discussion Already Exists
                  </div>
                  <p style={{ color: "#065f46", fontSize: "14px", lineHeight: "1.5", margin: 0 }}>
                     This claim has already been escalated by another user. You can view the existing discussion and contribute evidence there instead of creating a duplicate.
                  </p>
                  <Link
                     to={`/thread/detail/${existingThread}`}
                     style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "8px",
                        backgroundColor: "#0e9f6e",
                        color: "#fff",
                        padding: "10px 20px",
                        borderRadius: "8px",
                        fontWeight: 600,
                        fontSize: "14px",
                        textDecoration: "none",
                        width: "fit-content",
                     }}>
                     <Icons name="arrow-right" size={16} />
                     Go to Existing Thread
                  </Link>
               </div>
            )}

            {!loading && claim && (
               <div className="create-thread-body">
                  <div className="create-thread-form-col">
                     <div className="form-section box-panel">
                        <label className="form-label">
                           <Icons
                              name="file-text"
                              size={15}
                           />
                           Claim Caption
                        </label>
                        <p className="form-hint">
                           Describe the claim you're escalating. You can edit the AI-generated text
                           below.
                        </p>
                        <textarea
                           name="caption"
                           className="form-textarea"
                           onChange={handleInputChange}
                           value={formValues.caption}
                           rows={4}
                           placeholder="Describe the claim..."
                        />
                     </div>

                     {/*!loading && claim && (
                        <div className="form-section box-panel">
                           <label className="form-label">
                              <Icons
                                 name="link"
                                 size={15}
                              />
                              Source URL
                           </label>
                           <p className="form-hint">
                              This was automatically filled from the URL you verified.
                           </p>
                           <input
                              name="source_url"
                              type="url"
                              className="form-input"
                              onChange={handleInputChange}
                              value={formValues.source_url}
                              placeholder="https://..."
                           />
                        </div>
                     )*/}

                     <div className="form-section box-panel">
                        <label className="form-label">
                           <Icons
                              name="alert-triangle"
                              size={15}
                           />
                           Why are you flagging this?
                        </label>
                        <p className="form-hint">
                           Select the category that best describes this claim.
                        </p>
                        <div className="flag-options">
                           {ESCALATION_OPTIONS.map((opt) => (
                              <button
                                 key={opt.value}
                                 type="button"
                                 className={`escalation-option-btn ${formValues.escalation_reason === opt.value ? "selected" : ""}`}
                                 onClick={() => handleFlagSelect(opt.value)}>
                                 <div className="escalation-header">
                                    <Icons
                                       name={opt.icon}
                                       size={15}
                                    />
                                    <strong>{opt.label}</strong>
                                 </div>
                                 <span className="escalation-desc">{opt.desc}</span>
                              </button>
                           ))}
                        </div>
                     </div>

                     <button
                        className="submit-thread-btn"
                        onClick={() => {
                           handleSubmit();
                        }}
                        disabled={submitting || !formValues.escalation_reason}>
                        {submitting ? (
                           <>Submitting...</>
                        ) : (
                           <>
                              <Icons
                                 name="send"
                                 size={16}
                              />
                              Submit to Community
                           </>
                        )}
                     </button>
                  </div>

                  <div className="create-thread-sidebar">
                     <div className="box-panel ai-analysis-card">
                        <p className="sidebar-label">AI PRE-ANALYSIS</p>

                        <div className="ai-verdict-row">
                           <span className="ai-analysis-label">Verdict</span>
                           <span
                              className="ai-verdict-value"
                              style={{
                                 color: VERDICT_COLORS[aiVerdict] || "var(--text-muted)",
                              }}>
                              {aiVerdict || "—"}
                           </span>
                        </div>

                        <div className="ai-verdict-row">
                           <span className="ai-analysis-label">Confidence Score</span>
                           <span className="ai-confidence-value">
                              {claim.consensus_score ?? "—"}%
                           </span>
                        </div>

                        {claim.consensus_score !== null && (
                           <div className="ai-confidence-bar-track">
                              <div
                                 className="ai-confidence-bar-fill"
                                 style={{
                                    width: `${claim.consensus_score || 0}%`,
                                    backgroundColor:
                                       claim.consensus_score >= 70
                                          ? "var(--verdict-fact-text)"
                                          : claim.consensus_score >= 40
                                            ? "var(--verdict-misleading-text)"
                                            : "var(--verdict-fake-text)",
                                 }}
                              />
                           </div>
                        )}

                        <div className="ai-summary-box">
                           <span className="ai-analysis-label">AI Summary</span>
                           <p className="ai-summary-text">
                              {claim.ai_summary || "No summary available."}
                           </p>
                        </div>

                        <div className="ai-source-row">
                           <span className="ai-analysis-label">Source Type</span>
                           <span className="ai-source-value">{claim.source_type || "—"}</span>
                        </div>
                     </div>

                     <div className="box-panel info-card">
                        <p className="sidebar-label">
                           <Icons
                              name="info"
                              size={13}
                           />
                           WHY ESCALATE?
                        </p>
                        <p className="info-text">
                           When AI confidence is low or a claim is unverified, the community can
                           weigh in with evidence and votes to reach a final verdict.
                        </p>
                        <p className="info-text">
                           Your Trust Score increases when your escalations are resolved accurately.
                        </p>
                     </div>
                  </div>
               </div>
            )}
         </main>
      </div>
   );
}

export default CreateThreadPage;
