import { state } from "./state.js";
import { authenticatedFetch } from "./auth.js";

export class ApiRequestError extends Error {
   constructor(message, status = null) {
      super(message);
      this.name = "ApiRequestError";
      this.status = status;
   }
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
               reject(new Error(chrome.runtime.lastError.message || "Failed to contact extension worker."));
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
      const response = await authenticatedFetch(
         `${state.API_BASE_URL}/claims/${claim_id}/status`,
         {},
         { allowGuestAfterAuthFailure: true },
      );
      if (!response.ok) {
         const errorPayload = await response.json().catch(() => null);
         throw new ApiRequestError(
            errorPayload?.detail || errorPayload?.error || `Claim polling failed with status ${response.status}.`,
            response.status,
         );
      }

      const data = await response.json().catch(() => null);
      if (!data || typeof data !== "object" || typeof data.verdict !== "string") {
         throw new ApiRequestError("Claim polling returned an invalid response.", response.status);
      }

      console.log("Polled claim status:", data);
      return data;
   } catch (error) {
      console.error("Error polling claim status:", error);
      if (error instanceof ApiRequestError) {
         throw error;
      }

      throw new ApiRequestError(
         error?.message ? `Claim polling request failed: ${error.message}` : "Claim polling request failed.",
      );
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
      const response = await authenticatedFetch(
         `${state.API_BASE_URL}/claims/match/?${params}`,
         {},
         { allowGuestAfterAuthFailure: true },
      );
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
