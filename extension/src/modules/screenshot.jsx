import React from "react";
import { createRoot } from "react-dom/client";
import { state } from "./state.js";
import { sendImageToServer } from "./api.js";
import { displayLoadingCard, removeLoadingCard, displayErrorCard } from "./ui.jsx";
import { extensionErrorPresentation } from "./userFacingError.js";
import CropStudio from "../components/CropStudio.jsx";

let cropRoot = null;
let cropRootNode = null;

export function startCropStudio() {
   setTimeout(() => {
      chrome.runtime.sendMessage(
         {
            type: "CAPTURE_SCREENSHOT",
         },
         function (response) {
            if (response && response.screenshot) {
               renderCropStudioUI(response.screenshot);
            } else {
               console.error("Screenshot capture failed");
               displayErrorCard(
                  response?.error ||
                     "TruthLens could not capture this page. Open a normal webpage and try again.",
                  { kind: "input" },
               );
            }
         },
      );
   }, 100);
}

export function cleanupCropStudio() {
   state.isSnipping = false;
   if (cropRoot) {
      cropRoot.unmount();
      cropRoot = null;
   }
   if (cropRootNode) {
      cropRootNode.remove();
      cropRootNode = null;
   }
   document.body.style.cursor = "";
}

function renderCropStudioUI(fullScreenshot) {
   cropRootNode = document.createElement("div");
   cropRootNode.id = "truthlens-crop-studio-root";
   cropRootNode.style.position = "fixed";
   cropRootNode.style.top = "0";
   cropRootNode.style.left = "0";
   cropRootNode.style.width = "100%";
   cropRootNode.style.height = "100%";
   cropRootNode.style.zIndex = "9999999";
   cropRootNode.style.backgroundColor = "rgba(0, 0, 0, 0.8)";
   document.body.appendChild(cropRootNode);

   cropRoot = createRoot(cropRootNode);
   document.body.style.cursor = "default";

   cropRoot.render(
      <CropStudio
         imageSrc={fullScreenshot}
         onConfirm={(croppedDataUrl) => {
            processCroppedImage(croppedDataUrl);
         }}
         onCancel={() => {
            cleanupCropStudio();
         }}
      />,
   );
}

function processCroppedImage(croppedScreenshot) {
   const finalizePayload = () => {
      const payload = { image_data: croppedScreenshot };

      if (state.snipIntent === "deepfake") {
         state.isAnalyzing = true;
         // Pass a custom message to the loading card
         displayLoadingCard("Running forensic AI analysis...");

         // Import this new function dynamically to avoid circular dependencies
         import("./api.js").then(({ sendDeepfakeToServer }) => {
            sendDeepfakeToServer(payload).catch((error) => {
               removeLoadingCard();
               const presentation = extensionErrorPresentation({ error });
               displayErrorCard(presentation.message, { kind: presentation.kind });
            });
         });
      } else {
         state.isAnalyzing = true;
         displayLoadingCard();
         payload.check_deepfake = false; // We default to false now
         sendImageToServer(payload).catch((error) => {
            removeLoadingCard();
            const presentation = extensionErrorPresentation({ error });
            displayErrorCard(presentation.message, { kind: presentation.kind });
         });
      }
      cleanupCropStudio();
   };

   finalizePayload();
}
