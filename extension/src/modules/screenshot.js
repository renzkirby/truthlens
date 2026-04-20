import { state } from "./state.js";
import { cleanup } from "./overlay.js";
import { sendImageToServer } from "./api.js";
import { displayLoadingCard, removeLoadingCard, displayErrorCard } from "./ui.jsx";

export function captureScreenshot(coords) {
   console.log("Requesting screenshot with coords:", coords);

   if (state.selectionBox) state.selectionBox.style.display = "none";
   if (state.overlay) state.overlay.style.display = "none";

   setTimeout(() => {
      chrome.runtime.sendMessage(
         {
            type: "CAPTURE_SCREENSHOT",
            coords: coords,
         },
         function (response) {
            if (response && response.screenshot) {
               console.log("Screenshot received, cropping...");
               cropAndSave(response.screenshot, coords);
            } else {
               console.error("Screenshot capture failed");
               cleanup();
            }
         },
      );
   }, 100);
}

function cropAndSave(fullScreenshot, coords) {
   const img = new Image();
   img.onload = function () {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");

      const dpr = window.devicePixelRatio || 1;

      canvas.width = coords.width * dpr;
      canvas.height = coords.height * dpr;

      ctx.drawImage(
         img,
         coords.left * dpr,
         coords.top * dpr,
         coords.width * dpr,
         coords.height * dpr,
         0,
         0,
         canvas.width,
         canvas.height,
      );

      const croppedScreenshot = canvas.toDataURL("image/png");
      console.log("Screenshot cropped successfully");

      // helper function to finalize payload and send to server, called after fetching deepfake toggle state
      const finalizePayload = (isDeepfakeCheckEnabled) => {
         const payload = { image_data: croppedScreenshot };

            if (state.snipIntent === "deepfake") {
               state.isAnalyzing = true;
               // Pass a custom message to the loading card
               displayLoadingCard("Running forensic AI analysis..."); 
               
               // Import this new function dynamically to avoid circular dependencies
               import("./api.js").then(({ sendDeepfakeToServer }) => {
                  sendDeepfakeToServer(payload).catch((error) => {
                     removeLoadingCard();
                     displayErrorCard("Failed to analyze image forensics.");
                  });
               });
            } else {
               state.isAnalyzing = true;
               displayLoadingCard();
               payload.check_deepfake = false; // We default to false now
               sendImageToServer(payload).catch((error) => {
                  removeLoadingCard();
                  displayErrorCard("Failed to send image to server.");
               });
            }
            cleanup();
      };

      // Fetch the Deepfake toggle state
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
         chrome.storage.local.get(["checkDeepfake"], function (result) {
            finalizePayload(result.checkDeepfake || false);
         });
      } else {
         console.warn("Chrome storage API not accessible. Defaulting to false.");
         finalizePayload(false);
      }
   };

   img.src = fullScreenshot;
}
