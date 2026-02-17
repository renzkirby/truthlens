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
});
