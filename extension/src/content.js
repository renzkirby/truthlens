import "./content.css";
import { state } from "./modules/state.js";
import { createOverlay, cleanup, onMouseDown, onMouseMove, onMouseUp } from "./modules/overlay.js";

console.log("TruthLens content script loaded");

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "ACTIVATE_SNIPPING") {
      console.log("Snipping mode activated!");
      activateSnippingMode();
      sendResponse({ success: true });
   }
   
   if (request.type === "DISPLAY_URL_LOADING") {
      import("./modules/ui.jsx").then(({ displayLoadingCard }) => {
         state.isAnalyzing = true;
         displayLoadingCard();
      });
      sendResponse({ success: true });
      }

   if (request.type === "DISPLAY_URL_RESULT") {
      import("./modules/ui.jsx").then(({ displayResultCard, removeLoadingCard }) => {
         removeLoadingCard();
         setTimeout(() => displayResultCard(request.data), 2000);
      });
      sendResponse({ success: true });
   }
});

function activateSnippingMode() {
   state.isSnipping = true;

   createOverlay();

   document.addEventListener("mousedown", onMouseDown);
   document.addEventListener("mousemove", onMouseMove);
   document.addEventListener("mouseup", onMouseUp);
   document.addEventListener("keydown", onKeyDown);

   document.body.style.cursor = "crosshair";
}

function onKeyDown(e) {
   if (e.key === "Escape") {
      console.log("Snipping canceled by user");
      cleanup();
   }
}
