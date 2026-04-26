import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import { getEffectiveVerdict } from "../utils/verdict";
import { VERDICT_META } from "../utils/constants";
import "./ThreadDetailPage.css";

const DeepAnalysisSkeleton = () => {
   return (
      <div className="thread-layout">
         <NavigationBar />
         <div className="tdp-page">
            <div className="tdp-breadcrumb" style={{ borderBottomColor: "var(--border-default)" }}>
               <div className="tdp-breadcrumb-left" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <div className="skeleton-box" style={{ width: "100px", height: "16px" }}></div>
                  <div className="skeleton-box" style={{ width: "120px", height: "16px" }}></div>
                  <span className="tdp-breadcrumb-dot">·</span>
                  <div className="skeleton-box" style={{ width: "150px", height: "16px" }}></div>
               </div>
            </div>

            <div className="tdp-hero" style={{ background: "var(--bg-surface)", borderBottomColor: "var(--border-default)" }}>
               <div className="tdp-hero-inner">
                  <div className="tdp-hero-left" style={{ display: "flex", flexDirection: "column", gap: "12px", width: "100%" }}>
                     <div className="skeleton-box" style={{ width: "200px", height: "14px" }}></div>
                     <div className="skeleton-box" style={{ width: "100%", height: "28px", marginTop: "8px" }}></div>
                     <div className="skeleton-box" style={{ width: "80%", height: "28px" }}></div>
                  </div>
                  <div className="tdp-verdict-card" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                     <div className="skeleton-box" style={{ width: "100px", height: "28px", borderRadius: "20px" }}></div>
                     <div className="skeleton-box" style={{ width: "100%", height: "14px", marginTop: "8px" }}></div>
                     <div className="skeleton-box" style={{ width: "90%", height: "14px" }}></div>
                     <div style={{ display: "flex", justifyContent: "space-between", marginTop: "16px" }}>
                        <div className="skeleton-box" style={{ width: "120px", height: "14px" }}></div>
                        <div className="skeleton-box" style={{ width: "40px", height: "14px" }}></div>
                     </div>
                  </div>
               </div>
            </div>

            <div className="tdp-body">
               <div className="tdp-main">
                  <div className="tdp-post-card">
                     <div className="tdp-post-header" style={{ padding: "16px 20px" }}>
                        <div className="skeleton-box" style={{ width: "200px", height: "20px" }}></div>
                     </div>
                     <div style={{ padding: "20px" }}>
                        <div className="skeleton-box" style={{ width: "100%", height: "120px", borderRadius: "8px" }}></div>
                     </div>
                  </div>
               </div>
               <aside className="tdp-sidebar">
                  <div className="tdp-sidebar-card">
                     <div className="skeleton-box" style={{ width: "150px", height: "14px", marginBottom: "16px" }}></div>
                     <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                        {[1, 2].map(i => (
                           <div key={i} className="skeleton-box" style={{ width: "100%", height: "100px", borderRadius: "10px" }}></div>
                        ))}
                     </div>
                  </div>
               </aside>
            </div>
         </div>
      </div>
   );
};

function DeepAnalysisPage() {
   const { claimId } = useParams();
   const navigate = useNavigate();
   const { authFetch } = useAuth();
   const [claimData, setClaimData] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);

   const apiUrl = (path) =>
      `${import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api"}/${path}`;

   useEffect(() => {
      const fetchAnalysis = async () => {
         try {
            const data = await authFetch(apiUrl(`claims/${claimId}/analysis/`), {
               method: "GET",
            });
            setClaimData(data);
         } catch (err) {
            console.error("Failed to fetch analysis:", err);
            setError("Could not load the analysis report.");
         } finally {
            setLoading(false);
         }
      };
      fetchAnalysis();
   }, [claimId]);

   if (loading) {
      return <DeepAnalysisSkeleton />;
   }

   if (error || !claimData) {
      return (
         <div className="thread-layout">
            <NavigationBar />
            <div className="tdp-error">
               <Icons name="alert-triangle" size={32} color="#d97706" />
               <p>{error || "Analysis not found."}</p>
               <button onClick={() => navigate("/community")}>Back to Dashboard</button>
            </div>
         </div>
      );
   }

   const verdict = (getEffectiveVerdict(claimData) || "UNVERIFIED").toLowerCase();
   const vm = VERDICT_META[verdict] || VERDICT_META.unverified;

   return (
      <div className="thread-layout">
         <NavigationBar />
         <div className="tdp-page">
            
            {/* Breadcrumb */}
            <div className="tdp-breadcrumb" style={{ borderBottomColor: vm.color }}>
               <div className="tdp-breadcrumb-left">
                  <button className="tdp-back-btn" onClick={() => window.close()}>
                     <Icons name="arrow-left" size={13} color="#4f46e5" />
                     <span>Close Analysis</span>
                  </button>
                  <Icons name="arrow-right" size={13} color="#d1d5db" />
                  <span className="tdp-breadcrumb-thread">AI Forensics Report</span>
                  <span className="tdp-breadcrumb-dot">·</span>
                  <span className="tdp-breadcrumb-time">Claim ID: {claimId.split('-')[0]}...</span>
               </div>
            </div>

            {/* Hero Section */}
            <div className="tdp-hero" style={{ background: vm.bg, borderBottomColor: `${vm.color}30` }}>
               <div className="tdp-hero-inner">
                  <div className="tdp-hero-left">
                     <div className="tdp-claim-label" style={{ color: vm.color }}>
                        <Icons name="cpu" size={11} color={vm.color} strokeWidth={2.5} />
                        EXTRACTED CLAIM UNDER ANALYSIS
                     </div>
                     <h1 className="tdp-claim-text">{claimData.context_text || "No specific text was extracted for this claim."}</h1>
                  </div>

                  {/* Verdict Card */}
                  <div className="tdp-verdict-card">
                     <span
                        className="verdict-badge"
                        style={{ color: vm.color, background: vm.bg, borderColor: vm.border }}>
                        <Icons name={vm.icon || "help-circle"} size={12} color={vm.color} strokeWidth={2.5} />
                        {vm.label}
                     </span>
                     <p className="tdp-verdict-desc">{claimData.ai_summary}</p>
                     
                     <div className="tdp-confidence-row" style={{ marginTop: "10px" }}>
                        <span className="tdp-confidence-label">AI Confidence</span>
                        <span className="tdp-confidence-value" style={{ color: vm.color }}>
                           {claimData.consensus_score ?? "—"}%
                        </span>
                     </div>
                     <div className="tdp-confidence-track">
                        <div
                           className="tdp-confidence-fill"
                           style={{ width: `${claimData.consensus_score ?? 0}%`, background: vm.color }}
                        />
                     </div>
                     {claimData.score_context && (
                        <div style={{ fontSize: "12px", color: "#6b7280", marginTop: "12px", lineHeight: "1.4" }}>
                           <strong>Context:</strong> {claimData.score_context}
                        </div>
                     )}
                  </div>
               </div>
            </div>

            {/* Two-Column Body */}
            <div className="tdp-body">
               
               {/* Left Column: AI Reasoning */}
               <div className="tdp-main">
                  <div className="tdp-post-card">
                     <div className="tdp-post-header" style={{ padding: "16px 20px" }}>
                        <h3 style={{ margin: 0, fontSize: "15px", color: "#111827", display: "flex", alignItems: "center", gap: "8px" }}>
                           <Icons name="brain-circuit" size={18} color="#4f46e5" /> 
                           Engine Reasoning Breakdown
                        </h3>
                     </div>
                     <div style={{ padding: "20px" }}>
                        {claimData.ai_reasoning ? (
                           <div style={{ background: "#f9fafb", padding: "16px", borderRadius: "8px", border: "1px solid #e5e7eb", fontSize: "13px", lineHeight: "1.7", color: "#374151", whiteSpace: "pre-wrap" }}>
                              {claimData.ai_reasoning}
                           </div>
                        ) : (
                           <div style={{ background: "#fef2f2", padding: "16px", borderRadius: "8px", border: "1px solid #fca5a5", fontSize: "13px", color: "#991b1b" }}>
                              <strong>No reasoning data found.</strong> This might be an older claim processed before the reasoning engine was fully active, or the backend Celery tasks have not yet updated this claim.
                           </div>
                        )}
                     </div>
                  </div>
                  
                  {/* Original Media Display (If available) */}
                  {claimData.media_url && (
                     <div className="tdp-post-card" style={{ marginTop: "16px" }}>
                        <div className="tdp-post-header" style={{ padding: "16px 20px" }}>
                           <h3 style={{ margin: 0, fontSize: "15px", color: "#111827", display: "flex", alignItems: "center", gap: "8px" }}>
                              <Icons name="image" size={18} color="#4f46e5" /> 
                              Original Media Analyzed
                           </h3>
                        </div>
                        <div style={{ padding: "20px", display: "flex", justifyContent: "center", background: "#f9fafb" }}>
                           <img src={claimData.media_url} alt="Analyzed media" style={{ maxWidth: "100%", maxHeight: "400px", borderRadius: "8px", border: "1px solid #e5e7eb" }} />
                        </div>
                     </div>
                  )}
               </div>

               {/* Right Column: Source Material */}
               <aside className="tdp-sidebar">
                  <div className="tdp-sidebar-card">
                     <div className="tdp-sidebar-card-label" style={{ marginBottom: "16px" }}>
                        EVIDENCE SOURCES ({claimData.ai_sources?.length || 0})
                     </div>
                     
                     {claimData.ai_sources && claimData.ai_sources.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                           {claimData.ai_sources.map((source, idx) => {
                              // Handle both the old format (strings) and the new format (objects)
                              const isLegacyStr = typeof source === 'string';
                              const url = isLegacyStr ? source : source.url;
                              const title = isLegacyStr ? "External Source" : source.title;
                              const snippet = isLegacyStr ? "No summary available for this legacy source." : source.snippet;
                              
                              let domain = url;
                              try {
                                 domain = new URL(url).hostname.replace('www.', '');
                              } catch (e) { /* ignore invalid urls */ }
                              
                              return (
                                 <div key={idx} style={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: "10px", overflow: "hidden", boxShadow: "0 2px 4px rgba(0,0,0,0.02)" }}>
                                    <div style={{ padding: "12px", borderBottom: "1px solid #f3f4f6", background: "#f9fafb", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                       <span style={{ fontSize: "10px", fontWeight: "800", color: "#4f46e5", textTransform: "uppercase", letterSpacing: "0.05em" }}>Source {idx + 1}</span>
                                       <span style={{ fontSize: "11px", fontWeight: "600", color: "#6b7280" }}>{domain}</span>
                                    </div>
                                    <div style={{ padding: "14px 12px" }}>
                                       <h4 style={{ margin: "0 0 8px 0", fontSize: "13px", color: "#111827", lineHeight: "1.4" }}>{title}</h4>
                                       <p style={{ margin: "0 0 12px 0", fontSize: "12px", color: "#4b5563", lineHeight: "1.6" }}>{snippet}</p>
                                       <a href={url} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: "4px", fontSize: "12px", fontWeight: "700", color: "#2563eb", textDecoration: "none" }}>
                                          Read Full Article <Icons name="external-link" size={12} color="#2563eb" />
                                       </a>
                                    </div>
                                 </div>
                              );
                           })}
                        </div>
                     ) : (
                        <div style={{ background: "#f9fafb", padding: "16px", borderRadius: "8px", border: "1px dashed #d1d5db" }}>
                           <p style={{ fontSize: "12px", color: "#6b7280", margin: 0, lineHeight: "1.5", textAlign: "center" }}>
                              No specific external web sources were logged for this verdict. This usually happens if the claim was verified exclusively via image forensics.
                           </p>
                        </div>
                     )}
                  </div>
               </aside>

            </div>
         </div>
      </div>
   );
}

export default DeepAnalysisPage;