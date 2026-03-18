import { fetchClaimResult } from "./modules/api.js";
import { removeLoadingCard } from "./modules/ui.js";

console.log("TruthLens background service worker loaded");

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "CAPTURE_SCREENSHOT") {
      console.log("Capturing full tab screenshot");

      chrome.tabs.captureVisibleTab(null, { format: "png" }, function (dataUrl) {
         if (chrome.runtime.lastError) {
            console.error("Screenshot error:", chrome.runtime.lastError);
            sendResponse({ error: chrome.runtime.lastError.message });
            return;
         }

         console.log("Screenshot captured, sending back to popup");
         sendResponse({ screenshot: dataUrl });
      });

      return true;
   }

   // Needs fix
   if (request.type === "VERIFY_URL") {
      const { url, tabId } = request;

      fetch("http://localhost:8000/api/verify-url/", {
         method: "POST",
         headers: { "content-type": "application/json" },
         body: JSON.stringify({ url: url }),
      })
         .then((res) => res.json())
         .then((data) => {
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
               const claim = await fetchClaimResult(data.claim_id);
               if (claim && claim.verdict !== "PENDING") {
                  clearInterval(pollInterval);
                  chrome.tabs.sendMessage(tabId, {
                     type: "DISPLAY_URL_RESULT",
                     data: claim,
                  });
               }
               // if (!claim) {
               //    clearInterval(pollInterval);
               //    chrome.tabs.sendMessage(tabId, {
               //       type: "DISPLAY_URL_RESULT",
               //       data: {
               //          verdict: "OUT_OF_SCOPE",
               //          summary:
               //             "The content of the image is not a claim that can be fact-checked.",
               //          confidence_score: 100,
               //          source_type: "N/A",
               //          source_url: url,
               //       },
               //    });
               // }
            }, 3000);
         })
         .catch((err) => {
            console.error("URL verification failed:", err);
            chrome.tabs.sendMessage(tabId, {
               type: "DISPLAY_URL_RESULT",
               data: {
                  verdict: "UNVERIFIED",
                  summary: "Verification failed. Please try again.",
                  confidence_score: 0,
                  source_type: "Error",
                  source_url: "#",
               },
            });
         });

      return true;
   }
});
