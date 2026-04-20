import { state } from "./state.js";
import { buildAuthHeaders, clearAuthSession } from "./auth.js";

async function fetchWithAuthFallback(url, options = {}) {
   const baseHeaders = options.headers || {};
   const headersWithAuth = await buildAuthHeaders(baseHeaders);

   let response = await fetch(url, {
      ...options,
      headers: headersWithAuth,
   });

   if (response.status === 401 && headersWithAuth.Authorization) {
      await clearAuthSession();
      response = await fetch(url, {
         ...options,
         headers: baseHeaders,
      });
   }

   return response;
}

// Send snipped image payload to the background service worker.
// The background script owns cross-origin network calls to avoid page-origin CORS issues.
export async function sendImageToServer(image) {
   return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
         {
            type: "VERIFY_SNIPPET",
            payload: image,
         },
         (response) => {
            if (chrome.runtime.lastError) {
               reject(
                  new Error(
                     chrome.runtime.lastError.message || "Failed to contact extension worker.",
                  ),
               );
               return;
            }

            if (!response?.accepted) {
               reject(new Error(response?.error || "Snippet verification request was rejected."));
               return;
            }

            resolve(response);
         },
      );
   });
}

// Getting claim result
export async function fetchClaimResult(claim_id) {
   try {
      const response = await fetchWithAuthFallback(
         `${state.API_BASE_URL}/claims/${claim_id}/status`,
      );
      if (!response.ok) {
         throw new Error(`Status ${response.status}`);
      }
      const data = await response.json();
      console.log("Polled claim status:", data);
      return data;
   } catch (error) {
      console.error("Error polling claim status:", error);
      return {
         verdict: "OUT_OF_SCOPE",
         summary: "The content of the image is not a claim that can be fact-checked.",
         confidence_score: 100,
         source_type: "N/A",
         source_url: "",
      };
   }
}

/**
 * Check if a claim has already been resolved by the community.
 * Used by the extension for pre-check before sending to AI pipeline.
 *
 * @param {string} fingerprint - The computed claim fingerprint
 * @param {string} claimType - IMAGE, URL, or TEXT
 * @returns {object|null} Match result or null if no match
 */
export async function checkClaimMatch(fingerprint, claimType) {
   try {
      const params = new URLSearchParams({ fingerprint, claim_type: claimType });
      const response = await fetchWithAuthFallback(`${state.API_BASE_URL}/claims/match/?${params}`);
      if (!response.ok) {
         throw new Error(`Status ${response.status}`);
      }
      const data = await response.json();
      console.log("Claim match check:", data);
      return data.match || null;
   } catch (error) {
      console.error("Error checking claim match:", error);
      return null;
   }
}

export async function sendDeepfakeToServer(payload) {
   return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: "VERIFY_DEEPFAKE", payload }, (response) => {
         if (chrome.runtime.lastError) return reject(new Error("Worker error"));
         if (!response?.accepted) return reject(new Error(response?.error));
         resolve(response);
      });
   });
}