import { state } from "./state.js";
import { cleanup } from "./overlay.js";
import { sendImageToServer } from "./api.js";
import { displayLoadingCard } from "./ui.js";

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

      const payload = { image_data: croppedScreenshot };
      sendImageToServer(payload);
      state.isAnalyzing = true;
      displayLoadingCard();

      cleanup();
   };

   img.src = fullScreenshot;
}
