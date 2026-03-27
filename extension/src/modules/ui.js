import { state } from "./state.js";

export function displayResultCard(claim) {
   const { id, verdict, summary, confidence_score, source_type, source_url, is_ai_generated } = claim;
   let badgeColor = "#6b7280";

   switch (verdict) {
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

   const sparklesIconSVG = `
      <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
         <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.937A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .962 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.582a.5.5 0 0 1 0 .962L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.962 0z"/>
         <path d="M20 3h4"/><path d="M22 1v4"/><path d="M1 20h4"/><path d="M3 18v4"/>
      </svg>
   `;

   const aiWarningHTML = is_ai_generated 
      ? `<div style="background-color: #f5f3ff; color: #5b21b6; border: 1.5px solid #8b5cf6; padding: 10px 14px; border-radius: 8px; font-size: 11px; font-weight: 700; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; text-transform: uppercase; letter-spacing: 0.5px;">
            <span style="display: flex; align-items: center; color: #8b5cf6;">${sparklesIconSVG}</span>
            AI-GENERATED MEDIA DETECTED
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
         This post is <span class="truthlens-verdict" style="background-color: ${badgeColor};">${verdict}</span>
      </div>

      ${aiWarningHTML} <div class="truthlens-summary-box">
         <div class="truthlens-summary-title">AI Summary</div>
         <div style="font-size: 14px; line-height: 1.4;">${summary}</div>
      </div>

      <div class="truthlens-confidence-score">Confidence Score: ${confidence_score}</div>
      <div class="truthlens-confidence-bar">
         <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
      </div>
      ${
         verdict === "UNVERIFIED" || confidence_score < 50
            ? `<a href='http://localhost:5174/thread/create?claim_id=${id}' target='_blank' class='truthlens-source-link'>Want to ask the community?</a>`
            : verdict === "OUT_OF_SCOPE"
              ? ""
              : `<a href="${source_url}" target="_blank" class="truthlens-source-link">View Source</a>`
      }
      <div class="truthlens-footer">Source Type: ${source_type}</div>
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
