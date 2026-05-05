import React from "react";
import { renderToString } from "react-dom/server";
import { Sparkles, ShieldCheck, Flag, CheckCircle, XCircle, AlertTriangle, HelpCircle, Activity, Search, Users, ExternalLink } from "lucide-react";
import { state } from "./state.js";

// Pre-render icons
const iconSparkles = renderToString(React.createElement(Sparkles, { size: 14 }));
const iconShield = renderToString(React.createElement(ShieldCheck, { size: 16 }));
const iconFlag = renderToString(React.createElement(Flag, { size: 16 }));
const iconCheck = renderToString(React.createElement(CheckCircle, { size: 16 }));
const iconX = renderToString(React.createElement(XCircle, { size: 16 }));
const iconAlert = renderToString(React.createElement(AlertTriangle, { size: 16 }));
const iconHelp = renderToString(React.createElement(HelpCircle, { size: 16 }));
const iconActivity = renderToString(React.createElement(Activity, { size: 12 }));
const iconSearch = renderToString(React.createElement(Search, { size: 16 }));
const iconUsers = renderToString(React.createElement(Users, { size: 16 }));
const iconExternal = renderToString(React.createElement(ExternalLink, { size: 12 }));

// Helper function to get UI properties based on verdict
function getVerdictUI(verdict) {
   switch (verdict) {
      case "FACT": return { color: "#10b981", class: "fact", icon: iconCheck, text: "Fact" };
      case "FAKE": return { color: "#ef4444", class: "fake", icon: iconX, text: "Fake" };
      case "MISLEADING": return { color: "#f59e0b", class: "misleading", icon: iconAlert, text: "Misleading" };
      case "SATIRE": return { color: "#8b5cf6", class: "satire", icon: iconSparkles, text: "Satire" };
      case "OUT_OF_SCOPE": return { color: "#9ca3af", class: "out-of-scope", icon: iconHelp, text: "Out of Scope" };
      case "UNVERIFIED": return { color: "#ebdc09", class: "unverified", icon: iconHelp, text: "Unverified" };
      default: return { color: "#ebdc09", class: "unverified", icon: iconHelp, text: "Unverified" };
   }
}

export function displayResultCard(claim) {
   const {
      id, verdict, summary, confidence_score, thread_id, final_verdict, sources, source_url
   } = claim;
   const deepAnalysisUrl = `http://localhost:5174/analysis/${id}`;

   const displayVerdict = final_verdict || verdict;
   const ui = getVerdictUI(displayVerdict);

   // 1. Generate Sources HTML
   let sourcesHTML = "";
   const evidenceList = sources && sources.length > 0 ? sources : source_url ? [source_url] : [];

   if (displayVerdict !== "OUT_OF_SCOPE" && evidenceList.length > 0) {
      sourcesHTML = `
         <div style="margin-top: 12px; margin-bottom: 16px; font-size: 11px;">
            <strong style="color: #374151; display: block; margin-bottom: 4px;">Sources:</strong>
            
            <div style="display: flex; flex-direction: column; gap: 4px; max-height: 110px; overflow-y: auto; padding-right: 4px;">
               ${evidenceList
                  .map((src) => {
                     const urlStr = typeof src === "string" ? src : src.url;
                     
                     // NEW: Try to use the article title. If it doesn't exist, extract the clean domain name (e.g., "gmanetwork.com")
                     let displayTitle = urlStr;
                     try {
                         displayTitle = (typeof src === "object" && src.title) 
                             ? src.title 
                             : new URL(urlStr).hostname.replace('www.', '');
                     } catch (e) {
                         displayTitle = urlStr;
                     }

                     return `
                  <a href="${urlStr}" target="_blank" title="${urlStr}" style="color: #4f46e5; text-decoration: none; background: #f9fafb; padding: 6px 10px; border-radius: 6px; border: 1px solid #e5e7eb; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; font-weight: 600;">
                     ${displayTitle}
                  </a>
                  `;
                  })
                  .join("")}
            </div>
         </div>
      `;
   }

   // 2. Dynamic Button Logic
   let primaryButtonHTML = "";
   let secondaryLinkHTML = "";

   const communityLink = thread_id
       ? `http://localhost:5174/thread/detail/${thread_id}`
       : `http://localhost:5174/thread/create?claim_id=${id}`;
   const communityText = thread_id ? "View Community Discussion" : "Ask the Community";

   if (displayVerdict === "UNVERIFIED") {
       // UNVERIFIED: Primary CTA is asking the community. Secondary is full report.
       primaryButtonHTML = `<a href='${communityLink}' target='_blank' class='truthlens-primary-btn'>${iconUsers} ${communityText}</a>`;
       secondaryLinkHTML = `<a href='${deepAnalysisUrl}' target='_blank' class='truthlens-dashboard-link'>View full report ${iconExternal}</a>`;
   } else {
       // VERIFIED (Fact/Fake/etc): Primary CTA is the full report. Secondary is community discussion.
       primaryButtonHTML = `<a href='${deepAnalysisUrl}' target='_blank' class='truthlens-primary-btn'>${iconSearch} View Full Report</a>`;
       secondaryLinkHTML = `<a href='${communityLink}' target='_blank' class='truthlens-dashboard-link'>${communityText} ${iconExternal}</a>`;
   }

   const card = document.createElement("div");
   card.id = "truthlens-result-card";
   // Apply the color-coded border class to the entire card
   card.className = `truthlens-card verdict-${ui.class}`;

   card.innerHTML = `
      <div class="truthlens-header">
         <div class="truthlens-title" style="color: ${ui.color};">
            ${iconFlag} CLAIM FLAGGED
         </div>
         <button id="truthlens-close-btn" class="truthlens-close-btn">&times;</button>
      </div>

      <div class="truthlens-badge badge-${ui.class}">
         ${ui.icon} ${ui.text}
      </div>

      <div style="overflow-y: auto; padding-right: 4px; overflow-x: hidden;">
         <div class="truthlens-summary-box">
            <div class="truthlens-summary-title">
               ${iconSparkles} AI SUMMARY
            </div>
            <div class="truthlens-summary-text">${summary || "No summary available."}</div>
         </div>

         <div class="truthlens-confidence-container">
            <div class="truthlens-confidence-header">
               <div class="truthlens-confidence-title">
                  ${iconActivity} AI CONFIDENCE
               </div>
               <div class="truthlens-confidence-value" style="color: ${ui.color};">${confidence_score || 0}%</div>
            </div>
            <div class="truthlens-confidence-bar">
               <div class="truthlens-confidence-fill" style="width: ${confidence_score || 0}%; background: linear-gradient(90deg, #10b981 0%, ${ui.color} 100%);"></div>
            </div>
            <div class="truthlens-score-context">
               ${confidence_score < 50 ? "Low confidence — human review recommended" : "High confidence based on available data"}
            </div>
         </div>

         ${sourcesHTML}

         ${primaryButtonHTML}
         ${secondaryLinkHTML}
      </div>
   `;

   document.body.appendChild(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);

   document.getElementById("truthlens-close-btn").addEventListener("click", () => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}

export function displayLoadingCard(customMsg) {
   const msg = typeof customMsg === "string" ? customMsg : "Analyzing claim...";

   const card = document.createElement("div");
   card.id = "truthlens-loading-card";
   card.className = "truthlens-card";
   card.innerHTML = `
      <button id="truthlens-load-close-btn" class="truthlens-close-btn" style="position: absolute; top: 12px; right: 12px;">&times;</button>
      <div class="truthlens-spinner"></div>
      <div class="truthlens-loading-title">${msg}</div>
      <div class="truthlens-loading-progress-bar">
         <div class="truthlens-loading-progress-fill"></div>
      </div>
      <div class="truthlens-loading-subtitle">
         ${iconSearch} Querying fact-check databases
      </div>
   `;
   document.body.appendChild(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);
   
   document.getElementById("truthlens-load-close-btn").addEventListener("click", removeLoadingCard);
}


export function displayDeepfakeResultCard(data) {
   const { ai_probability, is_fake, summary } = data;
   const percentage = Math.round(ai_probability * 100);
   const badgeColor = is_fake ? "#e02424" : "#0e9f6e";
   const verdictText = is_fake ? "AI-GENERATED" : "AUTHENTIC / HUMAN";

   const card = document.createElement("div");
   card.id = "truthlens-result-card";
   card.className = "truthlens-card";

   card.innerHTML = `
      <div class="truthlens-header">
      
         <strong class="truthlens-title" style="color: #7c3aed;">TruthLens</strong>
         <button id="truthlens-close-btn" class="truthlens-close-btn">&times;</button>
      </div>
      
      <div style="max-height: 380px; overflow-y: auto; padding-right: 4px; overflow-x: hidden;">
         <div class="truthlens-verdict-text">
            Analysis: <span class="truthlens-verdict" style="background-color: ${badgeColor};">${verdictText}</span>
         </div>
         
         <div class="truthlens-summary-box">
            <div style="font-size: 14px; line-height: 1.4; margin-bottom: 8px;">
               Our neural network indicates a <strong>${percentage}%</strong> probability that this image is AI-generated.
            </div>
            <div style="font-size: 13px; line-height: 1.4; color: #4b5563; border-top: 1px solid #e5e7eb; padding-top: 8px;">
               <strong>AI Explanation:</strong> ${summary || "No detailed explanation available."}
            </div>
         </div>
         
         <div class="truthlens-confidence-bar">
            <div class="truthlens-confidence-fill" style="width: ${percentage}%; background-color: ${badgeColor};"></div>
         </div>
      </div>
   `;

   document.body.appendChild(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);

   document.getElementById("truthlens-close-btn").addEventListener("click", () => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}

export function removeLoadingCard() {
   state.isAnalyzing = false;
   const loadingCard = document.getElementById("truthlens-loading-card");
   if (loadingCard) {
      loadingCard.classList.remove("show");
      setTimeout(() => loadingCard.remove(), 300);
   }
}

export function displayErrorCard(message) {
   const card = document.createElement("div");
   card.id = "truthlens-error-card";
   card.className = "truthlens-card";
   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
      </div>
      <div class="truthlens-error">
         <div class="truthlens-error-icon">!</div>
         <div class="truthlens-error-text">${message}</div>
      </div>
   `;
   document.body.appendChild(card);
   setTimeout(() => card.classList.add("show"), 100);
   setTimeout(() => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}

export function successCard(message) {
   const card = document.createElement("div");
   card.id = "truthlens-success-card";
   card.className = "truthlens-card";
   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
      </div>
      <div class="truthlens-success">
         <div class="truthlens-success-icon">✓</div>
         <div class="truthlens-success-text">${message}</div>
      </div>
   `;
   document.body.appendChild(card);
   setTimeout(() => card.classList.add("show"), 100);
   setTimeout(() => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}

/**
 * Display a result card for claims that were resolved by the community (cached verdict).
 * Shows a distinctive "Community Verified" treatment vs the standard AI result.
 */
export function displayCachedResultCard(match) {
   const {
      verdict,
      final_verdict,
      summary,
      confidence_score,
      thread_id,
      moderator_notes,
      claim_id,
      source_type,
      is_ai_generated,
      score_context,
      sources,
      source_url,
   } = match;
   const displayVerdict = final_verdict || verdict;

   let badgeColor = "#6b7280";
   switch (displayVerdict) {
      case "FACT":
         badgeColor = "#0e9f6e";
         break;
      case "FAKE":
         badgeColor = "#e02424";
         break;
      case "MISLEADING":
         badgeColor = "#f97316";
         break;
      case "SATIRE":
         badgeColor = "#8b5cf6";
         break;
      case "UNVERIFIED":
         badgeColor = "#ebdc09";
         break;
      case "OUT_OF_SCOPE":
         badgeColor = "#9ca3af";
         break;
   }

   let confidence_bar_color = "#6b7280";
   if (confidence_score < 40) confidence_bar_color = "#e02424";
   else if (confidence_score >= 40 && confidence_score < 70) confidence_bar_color = "#ebdc09";
   else if (confidence_score >= 70) confidence_bar_color = "#0e9f6e";

   const displaySummary =
      moderator_notes || summary || "This claim has been reviewed by the community.";

   const aiWarningHTML = is_ai_generated
      ? `<div class="truthlens-banner truthlens-ai-warning">
            <span class="truthlens-banner-icon">${sparklesIconSVG}</span>
            AI-GENERATED MEDIA DETECTED
         </div>`
      : "";

   const communityBannerHTML = `
      <div class="truthlens-banner truthlens-community-verified">
         <span class="truthlens-banner-icon">${shieldCheckSVG}</span>
         COMMUNITY VERIFIED
      </div>`;

   let sourcesHTML = "";
   const evidenceList = sources && sources.length > 0 ? sources : source_url ? [source_url] : [];

   if (displayVerdict !== "OUT_OF_SCOPE" && evidenceList.length > 0) {
      sourcesHTML = `
         <div style="margin-top: 12px; font-size: 11px;">
            <strong style="color: #374151; display: block; margin-bottom: 4px;">Sources:</strong>
            <div style="display: flex; flex-direction: column; gap: 4px;">
               ${evidenceList
                  .map((src) => {
                     // Handle both the old string format and the new rich object format
                     const urlStr = typeof src === "string" ? src : src.url;
                     return `
                  <a href="${urlStr}" target="_blank" style="color: #4f46e5; text-decoration: none; background: #f9fafb; padding: 4px 8px; border-radius: 4px; border: 1px solid #e5e7eb; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                     ${urlStr}
                  </a>
                  `;
                  })
                  .join("")}
            </div>
         </div>
      `;
   }

   const card = document.createElement("div");
   card.id = "truthlens-result-card";
   card.className = "truthlens-card";

   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
         <button id="truthlens-close-btn" class="truthlens-close-btn">&times;</button>
      </div>

      <div style="overflow-y: auto; padding-right: 4px; overflow-x: hidden;">
         <div class="truthlens-verdict-text">
            This post is <span class="truthlens-verdict" style="background-color: ${badgeColor};">${displayVerdict}</span>
         </div>

         ${communityBannerHTML}
         ${aiWarningHTML}

         <div class="truthlens-summary-box">
            <div class="truthlens-summary-title">Community Verdict Summary</div>
            <div style="font-size: 14px; line-height: 1.4;">${displaySummary}</div>
         </div>

         ${
            confidence_score !== null
               ? `
            <div class="truthlens-confidence-score">Confidence Score: ${confidence_score}</div>
            <div class="truthlens-confidence-bar">
               <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
            </div>
            ${
               score_context
                  ? `
            <div class="truthlens-score-context" style="font-size: 12px; color: #6b7280; margin-top: 8px; line-height: 1.3;">
               <strong>Context:</strong> ${score_context}
            </div>
            `
                  : ""
            }
         `
               : ""
         }

         ${sourcesHTML}

         ${
            thread_id
               ? `<a href='http://localhost:5174/thread/detail/${thread_id}' target='_blank' class='truthlens-source-link'>View Community Discussion</a>`
               : ""
         }
         <div class="truthlens-footer">Source Type: Community Moderation</div>
      </div>
   `;

   document.body.appendChild(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);

   document.getElementById("truthlens-close-btn").addEventListener("click", () => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}
