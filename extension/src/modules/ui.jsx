import React from 'react';
import { renderToString } from 'react-dom/server';
import { Sparkles, ShieldCheck } from 'lucide-react';
import { state } from "./state.js";

const sparklesIconSVG = renderToString(React.createElement(Sparkles, { size: 14 }));
const shieldCheckSVG = renderToString(React.createElement(ShieldCheck, { size: 14 }));

export function displayResultCard(claim) {
   const { id, verdict, summary, confidence_score, source_type, source_url, is_ai_generated, has_community_verdict, thread_id, final_verdict, ai_verdict, score_context } = claim;

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

      <div class="truthlens-confidence-score">Confidence Score: ${confidence_score}</div>
      <div class="truthlens-confidence-bar">
         <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
      </div>
      ${score_context ? `
      <div class="truthlens-score-context" style="font-size: 12px; color: #6b7280; margin-top: 8px; line-height: 1.3;">
         <strong>Context:</strong> ${score_context}
      </div>
      <br>
      ` : ''}
      ${thread_id
         ? `<a href='http://localhost:5174/thread/detail/${thread_id}' target='_blank' class='truthlens-source-link'>View Community Discussion</a>`
         : (displayVerdict === "UNVERIFIED" || confidence_score < 50)
            ? `<a href='http://localhost:5174/thread/create?claim_id=${id}' target='_blank' class='truthlens-source-link'>Want to ask the community?</a>`
            : displayVerdict === "OUT_OF_SCOPE"
               ? ""
               : `<a href="${source_url}" target="_blank" class="truthlens-source-link">View Source</a>`
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

export function displayLoadingCard() {
   const card = document.createElement("div");
   card.id = "truthlens-loading-card";
   card.className = "truthlens-card";
   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
      </div>
      <div class="truthlens-loading">
         <div class="truthlens-spinner"></div>
         <div class='truthlens-loading-text'>${state.isAnalyzing ? "Analyzing the image, please wait..." : "Analyzing Done"}</div>
      </div>
   `;
   document.body.appendChild(card);
   setTimeout(() => card.classList.add("show"), 100);
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
   const { verdict, final_verdict, summary, confidence_score, thread_id, moderator_notes, claim_id, source_type, is_ai_generated, score_context } = match;
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
         COMMUNITY VERIFIED — CACHED RESULT
      </div>`;

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
