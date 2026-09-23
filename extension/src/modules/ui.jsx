import React from "react";
import { renderToString } from "react-dom/server";
import {
   Sparkles,
   ShieldCheck,
   Flag,
   CheckCircle,
   XCircle,
   AlertTriangle,
   HelpCircle,
   Activity,
   Search,
   Users,
   ExternalLink,
} from "lucide-react";
import { state } from "./state.js";

const COMMUNITY_PLATFORM_URL = state.WEB_APP_BASE_URL;

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
      case "FACT":
         return {
            color: "#10b981",
            class: "fact",
            icon: iconCheck,
            text: "Fact",
         };
      case "FAKE":
         return { color: "#ef4444", class: "fake", icon: iconX, text: "Fake" };
      case "MISLEADING":
         return {
            color: "#f59e0b",
            class: "misleading",
            icon: iconAlert,
            text: "Misleading",
         };
      case "SATIRE":
         return {
            color: "#8b5cf6",
            class: "satire",
            icon: iconSparkles,
            text: "Satire",
         };
      case "OUT_OF_SCOPE":
         return {
            color: "#9ca3af",
            class: "out-of-scope",
            icon: iconHelp,
            text: "Out of Scope",
         };
      case "UNVERIFIED":
         return {
            color: "#ebdc09",
            class: "unverified",
            icon: iconHelp,
            text: "Unverified",
         };
      default:
         return {
            color: "#ebdc09",
            class: "unverified",
            icon: iconHelp,
            text: "Unverified",
         };
   }
}

function escapeHtml(value) {
   const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
   return String(value ?? "").replace(/[&<>"']/g, (character) => entities[character]);
}

function nonblankText(value) {
   return typeof value === "string" && value.trim() ? value : "";
}

function isRecord(value) {
   return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isPublishedInstitutionalResult(result) {
   const publication = result.official_fact_check;
   return (
      result.resolution_source === "OFFICIAL_FACT_CHECK" &&
      isRecord(publication) &&
      [publication.fact_check_id, publication.verdict, publication.headline, publication.summary].some(nonblankText)
   );
}

// Attribute escaping and URL validation serve different purposes.
function safeHttpUrl(value) {
   if (
      typeof value !== "string" ||
      Array.from(value).some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
   )
      return null;
   if (!/^https?:\/\//i.test(value.trim())) return null;
   try {
      const url = new URL(value.trim());
      return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : null;
   } catch {
      return null;
   }
}

function communityBaseUrl() {
   const safeUrl = safeHttpUrl(COMMUNITY_PLATFORM_URL);
   if (!safeUrl) return null;
   const url = new URL(safeUrl);
   return url.search || url.hash ? null : safeUrl.replace(/\/+$/, "");
}

function pathComponent(value) {
   const text = typeof value === "number" && Number.isFinite(value) ? String(value) : nonblankText(value).trim();
   if (!text || text === "." || text === "..") return null;
   try {
      return encodeURIComponent(text);
   } catch {
      return null;
   }
}

function publicReachAttributes(organizationSlug, publicationId, surface) {
   if (
      typeof organizationSlug !== "string" ||
      !/^[a-zA-Z0-9_-]{1,255}$/.test(organizationSlug) ||
      typeof publicationId !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(publicationId)
   )
      return "";
   return `data-reach-organization-slug="${escapeHtml(organizationSlug)}" data-reach-publication-id="${escapeHtml(publicationId)}" data-reach-surface="${escapeHtml(surface)}"`;
}

function instrumentPublicPublicationLinks(card) {
   if (!card.isConnected) return;
   for (const link of card.querySelectorAll("a[data-reach-surface]")) {
      const send = (eventType) => {
         try {
            const pending = chrome.runtime.sendMessage({
               type: "RECORD_PUBLIC_REACH",
               event_type: eventType,
               source_surface: link.dataset.reachSurface,
               organization_slug: link.dataset.reachOrganizationSlug,
               publication_id: link.dataset.reachPublicationId,
            });
            pending?.catch(() => {});
         } catch {
            // A disconnected extension must never interfere with the card/link.
         }
      };
      send("EXTENSION_PUBLICATION_IMPRESSION");
      link.addEventListener("click", (event) => {
         if (event.isTrusted) send("EXTENSION_PUBLICATION_CLICK");
      });
      link.addEventListener("auxclick", (event) => {
         if (event.isTrusted && event.button === 1) send("EXTENSION_PUBLICATION_CLICK");
      });
   }
}

function relatedPublicationsHTML(claim) {
   if (claim.resolution_source === "OFFICIAL_FACT_CHECK" || !Array.isArray(claim.related_fact_checks)) return "";
   const baseUrl = communityBaseUrl();
   if (!baseUrl) return "";
   const entries = [];
   for (const publication of claim.related_fact_checks) {
      if (!isRecord(publication) || !isRecord(publication.organization)) continue;
      const organization = publication.organization;
      const rawSlug = nonblankText(organization.slug).trim();
      const rawId = nonblankText(publication.fact_check_id).trim();
      const headline = nonblankText(publication.headline);
      const organizationName = nonblankText(organization.name);
      if (
         organization.public_profile_available !== true ||
         !headline ||
         !organizationName ||
         !/^[a-zA-Z0-9_-]+$/.test(rawSlug) ||
         !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(rawId)
      )
         continue;
      const slug = pathComponent(rawSlug);
      const publicationId = pathComponent(rawId);
      if (!slug || !publicationId) continue;
      const articleUrl = `${baseUrl}/partners/${slug}/fact-checks/${publicationId}`;
      entries.push(`
         <div class="truthlens-related-publication">
            <p class="truthlens-related-publication-headline">${escapeHtml(headline)}</p>
            <p class="truthlens-related-publication-org">Published by ${escapeHtml(organizationName)}</p>
            <a class="truthlens-related-publication-link" ${publicReachAttributes(rawSlug, rawId, "EXTENSION_RELATED_FACT_CHECK")} href="${escapeHtml(articleUrl)}" target="_blank" rel="noopener noreferrer">Read related fact-check ${iconExternal}</a>
         </div>
      `);
      if (entries.length === 3) break;
   }
   if (!entries.length) return "";
   return `
      <section class="truthlens-related-publications" aria-labelledby="truthlens-related-publications-title">
         <h2 id="truthlens-related-publications-title" class="truthlens-related-publications-title">Related TruthLens fact-check</h2>
         ${entries.join("")}
         <p class="truthlens-related-publication-note">Related context only — this publication does not determine the verdict above.</p>
      </section>
   `;
}

function displayPublishedResultCard(claim, publication) {
   const organization = isRecord(publication.organization) ? publication.organization : {};
   const organizationName = nonblankText(organization.name);
   const publicProfileAvailable = organization.public_profile_available === true;
   const baseUrl = communityBaseUrl();
   const slug = pathComponent(organization.slug);
   const publicationId = pathComponent(publication.fact_check_id);
   const profileUrl = publicProfileAvailable && baseUrl && slug ? `${baseUrl}/partners/${slug}` : null;
   const articleUrl = profileUrl && publicationId ? `${profileUrl}/fact-checks/${publicationId}` : null;
   const logoUrl = publicProfileAvailable ? safeHttpUrl(organization.logo_url) : null;

   // The publication is authoritative; top-level values are legacy transport fallbacks.
   const verdict =
      nonblankText(publication.verdict) || nonblankText(claim.verdict) || nonblankText(claim.final_verdict);
   const supportedVerdict = ["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"].includes(verdict);
   const ui = supportedVerdict
      ? getVerdictUI(verdict)
      : { class: "out-of-scope", icon: iconHelp, text: "Verdict unavailable" };
   const summary =
      nonblankText(publication.summary) || nonblankText(claim.summary) || "No published summary available.";
   const headline = nonblankText(publication.headline) || "Published fact-check";
   const identityText = escapeHtml(organizationName || "Organization attribution unavailable");
   const identityHTML = profileUrl
      ? `<a href="${escapeHtml(profileUrl)}" target="_blank" rel="noopener noreferrer">${identityText} ${iconExternal}</a>`
      : `<span>${identityText}</span>`;
   const initial = organizationName ? escapeHtml(Array.from(organizationName.trim())[0].toUpperCase()) : iconShield;

   const metadata = [];
   if (nonblankText(publication.published_at)) {
      const publishedAt = new Date(publication.published_at);
      if (!Number.isNaN(publishedAt.getTime())) {
         const dateText = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" }).format(
            publishedAt,
         );
         metadata.push(
            `<time datetime="${escapeHtml(publishedAt.toISOString())}">Published ${escapeHtml(dateText)} (UTC)</time>`,
         );
      }
   }
   if (Number.isInteger(publication.version) && publication.version > 0) {
      metadata.push(`<span>Article v${escapeHtml(publication.version)}</span>`);
   }
   const revisionLabels = {
      INITIAL: "Initial publication",
      EDITORIAL_REVISION: "Editorial revision",
      FACTUAL_CORRECTION: "Factual correction",
   };
   if (typeof publication.revision_kind === "string" && Object.hasOwn(revisionLabels, publication.revision_kind)) {
      metadata.push(`<span>${escapeHtml(revisionLabels[publication.revision_kind])}</span>`);
   }

   const sources = Array.isArray(publication.sources)
      ? publication.sources
      : Array.isArray(claim.sources)
        ? claim.sources
        : claim.source_url
          ? [claim.source_url]
          : [];
   const sourceLinks = sources
      .map((source) => {
         const url = safeHttpUrl(typeof source === "string" ? source : isRecord(source) ? source.url : null);
         if (!url) return "";
         const title = (isRecord(source) && nonblankText(source.title)) || new URL(url).hostname;
         return `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)} ${iconExternal}</a></li>`;
      })
      .filter(Boolean)
      .join("");

   const card = document.createElement("div");
   card.id = "truthlens-result-card";
   card.className = `truthlens-card truthlens-institutional-card verdict-${ui.class}`;
   card.setAttribute("role", "region");
   card.setAttribute("aria-label", "Published institutional fact-check");
   card.innerHTML = `
      <div class="truthlens-header">
         <div class="truthlens-title" style="color: ${ui.color || "#9ca3af"};">${iconShield} PUBLISHED FACT-CHECK</div>
         <button class="truthlens-close-btn" aria-label="Close fact-check">&times;</button>
      </div>
      <div class="truthlens-publication-body">
         <div class="truthlens-badge badge-${ui.class}" role="group" aria-label="Human factual verdict: ${escapeHtml(ui.text)}">${ui.icon} ${ui.text}</div>
         <h2 class="truthlens-publication-headline" title="${escapeHtml(headline)}" aria-label="${escapeHtml(headline)}">${escapeHtml(headline)}</h2>
         <section class="truthlens-summary-box truthlens-publication-summary">
            <h3 class="truthlens-summary-title">${iconShield} PUBLISHED SUMMARY</h3>
            <div class="truthlens-summary-text truthlens-publication-summary-scroll" role="region" aria-label="Published summary" tabindex="0"><p>${escapeHtml(summary)}</p></div>
         </section>
         <div class="truthlens-publication-partner">
            <div class="truthlens-partner-mark"><span>${initial}</span>${logoUrl ? `<img hidden src="${escapeHtml(logoUrl)}" alt="" referrerpolicy="no-referrer">` : ""}</div>
            <div class="truthlens-partner-identity"><span class="truthlens-publication-label">Published by</span>${identityHTML}</div>
         </div>
         ${metadata.length ? `<div class="truthlens-publication-metadata">${metadata.join("")}</div>` : ""}
         ${sourceLinks ? `<section class="truthlens-publication-sources"><h3 class="truthlens-publication-label">Sources</h3><ul>${sourceLinks}</ul></section>` : ""}
         ${articleUrl ? `<a ${publicReachAttributes(organization.slug, publication.fact_check_id, "EXTENSION_OFFICIAL_FACT_CHECK")} href="${escapeHtml(articleUrl)}" target="_blank" rel="noopener noreferrer" class="truthlens-primary-btn">Read Full Fact-Check ${iconExternal}</a>` : ""}
      </div>
   `;

   // Keep the initial visible until an image has loaded successfully.
   const logo = card.querySelector(".truthlens-partner-mark img");
   if (logo) {
      const showLogo = () => {
         if (!logo.naturalWidth) return;
         logo.hidden = false;
         logo.previousElementSibling.hidden = true;
      };
      logo.addEventListener("load", showLogo);
      logo.addEventListener("error", () => {
         logo.previousElementSibling.hidden = false;
         logo.remove();
      });
      if (logo.complete) showLogo();
   }
   document.body.appendChild(card);
   instrumentPublicPublicationLinks(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);
   card.querySelector(".truthlens-close-btn").addEventListener("click", () => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}

export function displayResultCard(claim) {
   if (isPublishedInstitutionalResult(claim)) {
      displayPublishedResultCard(claim, claim.official_fact_check);
      return;
   }

   const { verdict, summary, confidence_score, thread_id, final_verdict, sources, source_url } = claim;
   const id = pathComponent(claim.claim_id || claim.id);
   const baseUrl = communityBaseUrl();
   const deepAnalysisUrl = baseUrl && id ? `${baseUrl}/analysis/${id}` : null;

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

                  // 1. Skip rendering if the URL is empty or a placeholder
                  if (!urlStr || urlStr === "#") return "";

                  // 2. Safely determine the display title
                  let displayTitle = urlStr;
                  if (typeof src === "object" && src.title) {
                     displayTitle = src.title;
                  } else if (urlStr.startsWith("http")) {
                     try {
                        displayTitle = new URL(urlStr).hostname.replace("www.", "");
                     } catch {
                        displayTitle = urlStr;
                     }
                  }

                  // 3. Return the anchor tag
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

   const threadId = pathComponent(thread_id);
   const communityLink =
      baseUrl && threadId
         ? `${baseUrl}/thread/detail/${threadId}`
         : baseUrl && id
           ? `${baseUrl}/thread/create?claim_id=${id}`
           : null;
   const communityText = thread_id ? "View Community Discussion" : "Ask the Community";

   if (displayVerdict === "UNVERIFIED") {
      // UNVERIFIED: Primary CTA is asking the community. Secondary is full report.
      primaryButtonHTML = communityLink
         ? `<a href='${escapeHtml(communityLink)}' target='_blank' rel='noopener noreferrer' class='truthlens-primary-btn'>${iconUsers} ${communityText}</a>`
         : "";
      secondaryLinkHTML = deepAnalysisUrl
         ? `<a href='${escapeHtml(deepAnalysisUrl)}' target='_blank' rel='noopener noreferrer' class='truthlens-dashboard-link'>View full report ${iconExternal}</a>`
         : "";
   } else {
      // VERIFIED (Fact/Fake/etc): Primary CTA is the full report. Secondary is community discussion.
      primaryButtonHTML = deepAnalysisUrl
         ? `<a href='${escapeHtml(deepAnalysisUrl)}' target='_blank' rel='noopener noreferrer' class='truthlens-primary-btn'>${iconSearch} View Full Report</a>`
         : "";
      secondaryLinkHTML = communityLink
         ? `<a href='${escapeHtml(communityLink)}' target='_blank' rel='noopener noreferrer' class='truthlens-dashboard-link'>${communityText} ${iconExternal}</a>`
         : "";
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

      <div style="overflow-y: hidden; padding-right: 4px; overflow-x: hidden;">
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
         ${relatedPublicationsHTML(claim)}

         ${primaryButtonHTML}
         ${secondaryLinkHTML}
      </div>
   `;

   document.body.appendChild(card);
   instrumentPublicPublicationLinks(card);
   void card.offsetWidth;
   setTimeout(() => card.classList.add("show"), 100);

   document.getElementById("truthlens-close-btn").addEventListener("click", () => {
      card.classList.remove("show");
      setTimeout(() => card.remove(), 300);
   });
}

export function displayLoadingCard(customMsg) {
   document.querySelectorAll("#truthlens-error-card").forEach((errorCard) => {
      errorCard.remove();
   });
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
   document.querySelectorAll("#truthlens-error-card").forEach((errorCard) => {
      errorCard.remove();
   });

   const card = document.createElement("div");
   card.id = "truthlens-error-card";
   card.className = "truthlens-card";
   card.innerHTML = `
      <div class="truthlens-header" style="align-items: center; gap: 12px;">
         <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
            <strong class="truthlens-title" style="color: #111827;">TRUTHLENS</strong>
            <span
               style="
                  display: inline-flex;
                  align-items: center;
                  padding: 3px 7px;
                  border-radius: 999px;
                  background: #fef2f2;
                  color: #b91c1c;
                  font-size: 9px;
                  font-weight: 700;
                  letter-spacing: 0.06em;
                  line-height: 1.2;
                  white-space: nowrap;
               "
            >
               SERVICE ISSUE
            </span>
         </div>

         <button
            type="button"
            id="truthlens-error-close-btn"
            class="truthlens-close-btn"
            aria-label="Dismiss error"
            title="Dismiss"
            style="
               flex-shrink: 0;
               width: 28px;
               height: 28px;
               display: inline-flex;
               align-items: center;
               justify-content: center;
               border-radius: 8px;
            "
         >
            &times;
         </button>
      </div>

      <div
         class="truthlens-error"
         role="alert"
         style="
            display: flex;
            align-items: flex-start;
            gap: 12px;
            margin-top: 14px;
         "
      >
         <div
            aria-hidden="true"
            style="
               width: 36px;
               height: 36px;
               flex: 0 0 36px;
               display: inline-flex;
               align-items: center;
               justify-content: center;
               border-radius: 10px;
               background: #fef2f2;
               color: #dc2626;
            "
         >
            ${iconAlert}
         </div>

         <div style="min-width: 0; flex: 1;">
            <div
               style="
                  margin-bottom: 4px;
                  color: #111827;
                  font-size: 14px;
                  font-weight: 700;
                  line-height: 1.35;
               "
            >
               Analysis unavailable
            </div>

            <div
               class="truthlens-error-text"
               style="
                  color: #4b5563;
                  font-size: 13px;
                  line-height: 1.45;
                  overflow-wrap: anywhere;
               "
            >
               ${message}
            </div>

            <div
               style="
                  display: flex;
                  align-items: flex-start;
                  gap: 6px;
                  margin-top: 10px;
                  padding-top: 9px;
                  border-top: 1px solid #f3f4f6;
                  color: #6b7280;
                  font-size: 11px;
                  line-height: 1.4;
               "
            >
               <span
                  aria-hidden="true"
                  style="
                     display: inline-flex;
                     align-items: center;
                     flex-shrink: 0;
                     margin-top: 1px;
                     color: #6b7280;
                  "
               >
                  ${iconShield}
               </span>
               <span>No verdict was generated. Start a new scan to try again.</span>
            </div>
         </div>
      </div>
   `;

   document.body.appendChild(card);

   const showTimer = setTimeout(() => card.classList.add("show"), 100);

   card.querySelector("#truthlens-error-close-btn").addEventListener("click", () => {
      clearTimeout(showTimer);
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
   if (isPublishedInstitutionalResult(match)) {
      displayPublishedResultCard(match, match.official_fact_check);
      return;
   }

   const {
      verdict,
      final_verdict,
      summary,
      confidence_score,
      thread_id,
      moderator_notes,
      claim_id,
      is_ai_generated,
      score_context,
      sources,
      source_url,
   } = match;

   const displayVerdict = final_verdict || verdict;
   const ui = getVerdictUI(displayVerdict);

   let confidence_bar_color = "#6b7280";
   if (confidence_score < 40) confidence_bar_color = "#e02424";
   else if (confidence_score >= 40 && confidence_score < 70) confidence_bar_color = "#ebdc09";
   else if (confidence_score >= 70) confidence_bar_color = "#0e9f6e";

   const displaySummary = moderator_notes || summary || "This claim has been reviewed by the community.";

   const aiWarningHTML = is_ai_generated
      ? `<div class="truthlens-banner truthlens-ai-warning">
            <span class="truthlens-banner-icon">${iconSparkles}</span>
            AI-GENERATED MEDIA DETECTED
         </div>`
      : "";

   // 1. Determine the Dynamic Banner based on match_type
   let customBannerHTML = "";
   if (match.match_type === "resolved") {
      customBannerHTML = `
         <div class="truthlens-banner truthlens-community-verified">
            <span class="truthlens-banner-icon">${iconShield}</span>
            COMMUNITY VERIFIED
         </div>`;
   } else if (match.match_type === "has_thread") {
      customBannerHTML = `
         <div class="truthlens-banner" style="background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;">
            <span class="truthlens-banner-icon">${iconSearch}</span>
            COMMUNITY INVESTIGATION ONGOING
         </div>`;
   }

   // 2. Determine Dynamic Buttons based on match_type
   let actionButtonsHTML = "";
   if (match.match_type === "no_verdict") {
      const createThreadUrl = `${COMMUNITY_PLATFORM_URL}/thread/create?claim_id=${claim_id}`;
      actionButtonsHTML = `
            <div style="margin-top: 16px;">
                  <p style="font-size: 12px; color: #4b5563; margin-bottom: 8px;">No one has verified this yet.</p>
                  <a href='${createThreadUrl}' target='_blank' class='truthlens-primary-btn' style="text-align: center; display: block; text-decoration: none;">
                     Post to Community for Verification
                  </a>
            </div>
         `;
   } else if (thread_id) {
      const threadUrl = `${COMMUNITY_PLATFORM_URL}/thread/detail/${thread_id}`;
      actionButtonsHTML = `
            <div style="margin-top: 16px;">
                  <a href='${threadUrl}' target='_blank' class='truthlens-primary-btn' style="text-align: center; display: block; text-decoration: none;">
                     View Community Discussion
                  </a>
            </div>
         `;
   }

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
                           displayTitle =
                              typeof src === "object" && src.title
                                 ? src.title
                                 : new URL(urlStr).hostname.replace("www.", "");
                        } catch {
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
            This post is <span class="truthlens-badge badge-${ui.class}">${ui.icon} ${ui.text}</span>
         </div>

         ${customBannerHTML}
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

         ${actionButtonsHTML}
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
