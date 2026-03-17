import { state } from "./state.js";

export function displayResultCard(claim) {
   const { verdict, summary, confidence_score, source_type, source_url } = claim;
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
      <div class="truthlens-summary-box">
         <div class="truthlens-summary-title">AI Summary</div>
         <div style="font-size: 14px; line-height: 1.4;">${summary}</div>
      </div>
      <div class="truthlens-confidence-score">Confidence Score: ${confidence_score}</div>
      <div class="truthlens-confidence-bar">
         <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
      </div>
      ${
         verdict === "UNVERIFIED" || confidence_score < 50
            ? `<a href='http://localhost:5174/thread/create?claim_id=${claim.id}' target='_blank' class='truthlens-source-link'>Want to ask the community?</a>`
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
