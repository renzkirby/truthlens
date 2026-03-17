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

   if (request.type === "VERIFY_URL") {
      const { url, tabId } = request;

      fetch("http://localhost:8000/api/verify-url/", {
         method: "POST",
         headers: { "content-type": "application/json" },
         body: JSON.stringify({ url: url }),
      })
         .then((res) => res.json())
         .then((data) => {
            chrome.tabs.sendMessage(tabId, {
               type: "DISPLAY_URL_RESULT",
               data: data,
            });
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
