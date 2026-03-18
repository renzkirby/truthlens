import { state } from "./state.js";
import { displayResultCard, removeLoadingCard } from "./ui.js";

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
      return;
   }

   const data = await response.json();
   const claim_id = data.claim_id;
   console.log("Claim ID received from server:", claim_id);

   // Added polling for continuous claim calling until result is given
   let pollCount = 0;
   const maxPolls = 20;

   const pollInterval = setInterval(async () => {
      pollCount++;
      if (pollCount > maxPolls) {
         clearInterval(pollInterval);
         console.error("Polling timed out");
         removeLoadingCard();
         return;
      }
      const claim = await fetchClaimResult(claim_id);
      if (claim && claim.verdict !== "PENDING") {
         clearInterval(pollInterval);
         displayResultCard(claim);
         setTimeout(() => {
            removeLoadingCard();
         }, 2000);
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
         source_url: url,
      };
   }
}
