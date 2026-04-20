import React from 'react';
import { renderToString } from 'react-dom/server';
import { Sparkles, ShieldCheck } from 'lucide-react';
import { state } from "./state.js";

const sparklesIconSVG = renderToString(React.createElement(Sparkles, { size: 14 }));
const shieldCheckSVG = renderToString(React.createElement(ShieldCheck, { size: 14 }));

export function displayResultCard(claim) {
   const { id, verdict, summary, confidence_score, source_type, source_url, sources, is_ai_generated, has_community_verdict, thread_id, final_verdict, ai_verdict, score_context } = claim;

   // Use community verdict if available, otherwise AI verdict
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
         badgeColor = "#6b7280";
         break;
   }

   let confidence_bar_color = "#6b7280";
   if (confidence_score < 40) confidence_bar_color = "#e02424";
   else if (confidence_score >= 40 && confidence_score < 70) confidence_bar_color = "#ebdc09";
   else if (confidence_score >= 70) confidence_bar_color = "#0e9f6e";

   const aiWarningHTML = is_ai_generated
      ? `<div class="truthlens-banner truthlens-ai-warning">
            <span class="truthlens-banner-icon">${sparklesIconSVG}</span>
            AI-GENERATED MEDIA DETECTED
         </div>`
      : "";

   // Community verdict banner
   const communityBannerHTML = has_community_verdict
      ? `<div class="truthlens-banner truthlens-community-verified">
            <span class="truthlens-banner-icon">${shieldCheckSVG}</span>
            COMMUNITY VERIFIED
         </div>`
      : "";

   const card = document.createElement("div");
   card.id = "truthlens-result-card";
   card.className = "truthlens-card";
   let sourcesHTML = "";
   const evidenceList = sources && sources.length > 0 ? sources : (source_url ? [source_url] : []);
   
   if (displayVerdict !== "OUT_OF_SCOPE" && evidenceList.length > 0) {
      sourcesHTML = `
         <div style="margin-top: 12px; font-size: 11px;">
            <strong style="color: #374151; display: block; margin-bottom: 4px;">Sources:</strong>
            <div style="display: flex; flex-direction: column; gap: 4px;">
               ${evidenceList.map(src => `
                  <a href="${src}" target="_blank" style="color: #4f46e5; text-decoration: none; background: #f9fafb; padding: 4px 8px; border-radius: 4px; border: 1px solid #e5e7eb; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                     "${src}"
                  </a>
               `).join('')}
            </div>
         </div>
      `;
   }

   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
         <button id="truthlens-close-btn" class="truthlens-close-btn">&times;</button>
      </div>
      <div class="truthlens-verdict-text">
         This post is <span class="truthlens-verdict" style="background-color: ${badgeColor};">${displayVerdict}</span>
      </div>

      ${communityBannerHTML}
      ${aiWarningHTML}
      <div class="truthlens-summary-box">
         <div class="truthlens-summary-title">${has_community_verdict ? 'Community Verdict Summary' : 'AI Summary'}</div>
         <div style="font-size: 14px; line-height: 1.4;">${summary}</div>
      </div>

      <div class="truthlens-confidence-score">Confidence Score: <strong>${confidence_score}%</strong></div>
      <div class="truthlens-confidence-bar">
         <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
      </div>
      ${score_context ? `
      <div class="truthlens-score-context" style="font-size: 12px; color: #6b7280; margin-top: 8px; line-height: 1.3;">
         <strong>Context:</strong> ${score_context}
      </div>
      <br>
      ` : ''}

      ${sourcesHTML}

      ${thread_id
         ? `<a href='http://localhost:5174/thread/detail/${thread_id}' target='_blank' class='truthlens-source-link' style='display: block; text-align: center; background: #f3f4f6; padding: 8px; border-radius: 6px; text-decoration: none; color: #4f46e5; font-weight: 600; margin-top: 12px; border: 1px solid #e5e7eb;'>View Community Discussion</a>`
         : (displayVerdict === "UNVERIFIED" || confidence_score < 50)
            ? `<a href='http://localhost:5174/thread/create?claim_id=${id}' target='_blank' class='truthlens-source-link' style='display: block; text-align: center; background: #eff6ff; padding: 8px; border-radius: 6px; text-decoration: none; color: var(--brand-primary, #4f46e5); font-weight: 600; margin-top: 12px; border: 1px dashed #bfdbfe;'>[+] Ask the community</a>` 
            : ""
      }


      <div class="truthlens-footer">Source Type: ${has_community_verdict ? 'Community Moderation' : source_type}</div>
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
   const msg = typeof customMsg === 'string' 
      ? customMsg 
      : (state.isAnalyzing ? "Analyzing the image, please wait..." : "Analyzing Done");

   const card = document.createElement("div");
   card.id = "truthlens-loading-card";
   card.className = "truthlens-card";
   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
      </div>
      <div class="truthlens-loading">
         <div class="truthlens-spinner"></div>
         <div class='truthlens-loading-text'>${msg}</div>
      </div>
   `;
   document.body.appendChild(card);
   setTimeout(() => card.classList.add("show"), 100);
}

export function displayDeepfakeResultCard(data) {
   const { ai_probability, is_fake } = data;
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
      
      <div class="truthlens-verdict-text">
         Analysis: <span class="truthlens-verdict" style="background-color: ${badgeColor};">${verdictText}</span>
      </div>
      
      <div class="truthlens-summary-box">
         <div style="font-size: 14px; line-height: 1.4;">
            Our neural network indicates a <strong>${percentage}%</strong> probability that this image was generated or heavily manipulated by AI models like Midjourney or Stable Diffusion.
         </div>
      </div>
      
      <div class="truthlens-confidence-bar">
         <div class="truthlens-confidence-fill" style="width: ${percentage}%; background-color: ${badgeColor};"></div>
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
   const { verdict, final_verdict, summary, confidence_score, thread_id, moderator_notes, claim_id, source_type, is_ai_generated, score_context, sources, source_url } = match;
   const displayVerdict = final_verdict || verdict;

   let badgeColor = "#6b7280";
   switch (displayVerdict) {
      case "FACT": badgeColor = "#0e9f6e"; break;
      case "FAKE": badgeColor = "#e02424"; break;
      case "MISLEADING": badgeColor = "#f97316"; break;
      case "SATIRE": badgeColor = "#8b5cf6"; break;
      case "UNVERIFIED": badgeColor = "#ebdc09"; break;
   }

   let confidence_bar_color = "#6b7280";
   if (confidence_score < 40) confidence_bar_color = "#e02424";
   else if (confidence_score >= 40 && confidence_score < 70) confidence_bar_color = "#ebdc09";
   else if (confidence_score >= 70) confidence_bar_color = "#0e9f6e";

   const displaySummary = moderator_notes || summary || "This claim has been reviewed by the community.";

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
   const evidenceList = sources && sources.length > 0 ? sources : (source_url ? [source_url] : []);

   if (displayVerdict !== "OUT_OF_SCOPE" && evidenceList.length > 0) {
      sourcesHTML = `
         <div style="margin-top: 12px; font-size: 11px;">
            <strong style="color: #374151; display: block; margin-bottom: 4px;">Sources:</strong>
            <div style="display: flex; flex-direction: column; gap: 4px;">
               ${evidenceList.map(src => `
                  <a href="${src}" target="_blank" style="color: #4f46e5; text-decoration: none; background: #f9fafb; padding: 4px 8px; border-radius: 4px; border: 1px solid #e5e7eb; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                     "${src}"
                  </a>
               `).join('')}
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

      <div class="truthlens-verdict-text">
         This post is <span class="truthlens-verdict" style="background-color: ${badgeColor};">${displayVerdict}</span>
      </div>

      ${communityBannerHTML}
      ${aiWarningHTML}

      <div class="truthlens-summary-box">
         <div class="truthlens-summary-title">Community Verdict Summary</div>
         <div style="font-size: 14px; line-height: 1.4;">${displaySummary}</div>
      </div>

      ${confidence_score !== null ? `
         <div class="truthlens-confidence-score">Confidence Score: ${confidence_score}</div>
         <div class="truthlens-confidence-bar">
            <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
         </div>
         ${score_context ? `
         <div class="truthlens-score-context" style="font-size: 12px; color: #6b7280; margin-top: 8px; line-height: 1.3;">
            <strong>Context:</strong> ${score_context}
         </div>
         ` : ''}
      ` : ''}

      ${sourcesHTML}

      ${thread_id
         ? `<a href='http://localhost:5174/thread/detail/${thread_id}' target='_blank' class='truthlens-source-link'>View Community Discussion</a>`
         : ''
      }
      <div class="truthlens-footer">Source Type: Community Moderation</div>
   `;

   document.body.appendChild(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);

   document.getElementById("truthlens-close-btn").addEventListener("click", () => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}
