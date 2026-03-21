import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons.jsx";
import "./CreateThreadPage.css";

const FLAG_OPTIONS = [
   {
      value: "FACT",
      label: "Fact",
      icon: "check-circle",
      color: "var(--verdict-fact-text)",
      bg: "var(--verdict-fact-bg)",
      border: "var(--verdict-fact-border)",
   },
   {
      value: "FAKE",
      label: "Fake",
      icon: "x-circle",
      color: "var(--verdict-fake-text)",
      bg: "var(--verdict-fake-bg)",
      border: "var(--verdict-fake-border)",
   },
   {
      value: "MISLEADING",
      label: "Misleading",
      icon: "alert-triangle",
      color: "var(--verdict-misleading-text)",
      bg: "var(--verdict-misleading-bg)",
      border: "var(--verdict-misleading-border)",
   },
   {
      value: "SATIRE",
      label: "Satire",
      icon: "wand",
      color: "var(--verdict-satire-text)",
      bg: "var(--verdict-satire-bg)",
      border: "var(--verdict-satire-border)",
   },
   {
      value: "UNVERIFIED",
      label: "Unverified",
      icon: "help-circle",
      color: "var(--verdict-unverified-text)",
      bg: "var(--verdict-unverified-bg)",
      border: "var(--verdict-unverified-border)",
   },
];

const VERDICT_COLORS = {
   FACT: "var(--verdict-fact-text)",
   FAKE: "var(--verdict-fake-text)",
   MISLEADING: "var(--verdict-misleading-text)",
   SATIRE: "var(--verdict-satire-text)",
   UNVERIFIED: "var(--verdict-unverified-text)",
};

function CreateThreadPage() {
   const [loading, setLoading] = useState(true);
   const [submitting, setSubmitting] = useState(false);
   const [claim, setClaim] = useState(null);
   const [error, setError] = useState(null);
   const [searchParams] = useSearchParams();
   const claimId = searchParams.get("claim_id");
   const { authFetch } = useAuth();
   const navigate = useNavigate();
   const [formValues, setformValues] = useState({
      caption: "",
      source_url: "",
      flag_reason: "",
   });

   const handleInputChange = (e) => {
      const { name, value } = e.target;
      setformValues({
         ...formValues,
         [name]: value,
      });
   };

   const handleFlagSelect = (value) => {
      setformValues({ ...formValues, flag_reason: value });
      console.log(formValues.flag_reason);
   };

   const handleSubmit = async () => {
      if (!formValues.flag_reason) {
         setError("Please select a flag reason before submitting.");
         return;
      }

      setSubmitting(true);
      setError(null);
      try {
         const responseData = await authFetch("http://localhost:8000/api/threads/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               claim_id: claimId,
               caption: formValues.caption,
               flag_reason: formValues.flag_reason,
            }),
         });
         navigate(`/thread/detail/${responseData.id}`);
      } catch (err) {
         setError("Something went wrong in creating a thread.");
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
            const claimData = await authFetch(`http://localhost:8000/api/claims/${claimId}/`, {
               method: "GET",
            });
            setClaim(claimData);
            setformValues((prev) => ({
               ...prev,
               caption: claimData.ai_summary || "",
               source_url: claimData.source_link || "",
            }));
            console.log(claimData);
         } catch (err) {
            setError("Failed loading form");
         } finally {
            setLoading(false);
         }
      };
      fetchClaimData();
   }, [claimId]);

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
                           {FLAG_OPTIONS.map((opt) => (
                              <button
                                 key={opt.value}
                                 type="button"
                                 className={`flag-option-btn ${formValues.flag_reason === opt.value ? "selected" : ""}`}
                                 style={
                                    formValues.flag_reason === opt.value
                                       ? {
                                            color: opt.color,
                                            backgroundColor: opt.bg,
                                            borderColor: opt.border,
                                         }
                                       : {}
                                 }
                                 onClick={() => {
                                    handleFlagSelect(opt.value);
                                    console.log(opt.color, opt.value, opt.bg, opt.border);
                                 }}>
                                 <Icons
                                    name={opt.icon}
                                    size={15}
                                 />
                                 {opt.label}
                              </button>
                           ))}
                        </div>
                     </div>

                     <button
                        className="submit-thread-btn"
                        onClick={() => {
                           handleSubmit();
                        }}
                        disabled={submitting || !formValues.flag_reason}>
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
                                 color: VERDICT_COLORS[claim.verdict] || "var(--text-muted)",
                              }}>
                              {claim.verdict || "—"}
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
