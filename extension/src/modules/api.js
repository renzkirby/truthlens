import { state } from "./state.js";
import { displayResultCard, removeLoadingCard, displayErrorCard, successCard, displayCachedResultCard } from "./ui.js";

// Sending snipped image to backend
export async function sendImageToServer(image) {
   const response = await fetch(`${state.API_BASE_URL}/analyze/`, {
      method: "POST",
      headers: {
         "content-type": "application/json",
      },
      body: JSON.stringify(image),
   });

   if (!response.ok) {
      console.error("Failed to send image to server:", response.statusText);
      removeLoadingCard();
      displayErrorCard("Failed to send image to server. Please try again later.");
      return;
   }

   const data = await response.json();
   const claim_id = data.claim_id;
   console.log("Claim ID received from server:", claim_id);

   // ── Cached verdict shortcut ──
   // If the backend found a resolved match, display it immediately (no polling needed)
   if (data.cached && data.match) {
      console.log("Cache hit! Displaying resolved verdict from community.");
      setTimeout(() => {
         removeLoadingCard();
      }, 1000);
      successCard("Previously verified claim found!");
      displayCachedResultCard(data.match);
      return;
   }

   // Added polling for continuous claim calling until result is given
   let pollCount = 0;
   const maxPolls = 20;

   const pollInterval = setInterval(async () => {
      pollCount++;
      if (pollCount > maxPolls) {
         clearInterval(pollInterval);
         console.error("Polling timed out");
         removeLoadingCard();
         displayErrorCard("Failed to get claim result. Please try again later.");
         return;
      }
      const claim = await fetchClaimResult(claim_id);
      if (claim && claim.verdict !== "PENDING") {
         clearInterval(pollInterval);
         setTimeout(() => {
            removeLoadingCard();
         }, 2000);
         successCard("Analysis complete!");
         displayResultCard(claim);
      }
   }, 3000);
}

// Getting claim result
export async function fetchClaimResult(claim_id) {
   try {
      const response = await fetch(`${state.API_BASE_URL}/claims/${claim_id}/status`);
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
      const response = await fetch(`${state.API_BASE_URL}/claims/match/?${params}`);
      const data = await response.json();
      console.log("Claim match check:", data);
      return data.match || null;
   } catch (error) {
      console.error("Error checking claim match:", error);
      return null;
   }
}
