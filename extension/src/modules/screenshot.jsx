import React from "react";
import { createRoot } from "react-dom/client";
import { state } from "./state.js";
import { sendImageToServer } from "./api.js";
import { displayLoadingCard, removeLoadingCard, displayErrorCard } from "./ui.jsx";
import CropStudio from "../components/CropStudio.jsx";

let cropRoot = null;
let cropRootNode = null;

export function startCropStudio() {
   console.log("Requesting full screenshot for Crop Studio...");

   setTimeout(() => {
      chrome.runtime.sendMessage(
         {
            type: "CAPTURE_SCREENSHOT",
         },
         function (response) {
            if (response && response.screenshot) {
               console.log("Full screenshot received, rendering CropStudio...");
               renderCropStudioUI(response.screenshot);
            } else {
               console.error("Screenshot capture failed");
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
            console.log("Crop confirmed via UI");
            processCroppedImage(croppedDataUrl);
         }}
         onCancel={() => {
            console.log("Crop canceled via UI");
            cleanupCropStudio();
         }}
      />,
   );
}

function processCroppedImage(croppedScreenshot) {
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
      cleanupCropStudio();
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
}
