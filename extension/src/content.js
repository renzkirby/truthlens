import "./content.css";
import { state } from "./modules/state.js";
import { createOverlay, cleanup, onMouseDown, onMouseMove, onMouseUp } from "./modules/overlay.js";

console.log("TruthLens content script loaded");

const BRIDGE_EVENT_SOURCE = "TRUTHLENS_WEB_AUTH_BRIDGE";
const EXTENSION_EVENT_SOURCE = "TRUTHLENS_EXTENSION";
const BRIDGE_SCRIPT_ID = "truthlens-auth-bridge-script";

function isBridgeTargetPage() {
   return state.WEB_APP_ORIGINS.includes(window.location.origin);
}

function injectAuthBridgeScript() {
   if (document.getElementById(BRIDGE_SCRIPT_ID)) {
      return;
   }

   const bridgeScript = document.createElement("script");
   bridgeScript.id = BRIDGE_SCRIPT_ID;
   bridgeScript.src = chrome.runtime.getURL("auth-bridge.js");
   bridgeScript.async = false;

   const parent = document.head || document.documentElement;
   if (!parent) {
      return;
   }

   parent.appendChild(bridgeScript);
}

function requestTokenSyncFromPageBridge() {
   window.postMessage(
      {
         source: EXTENSION_EVENT_SOURCE,
         type: "REQUEST_TOKENS",
      },
      window.location.origin,
   );
}

function handleBridgeMessage(event) {
   if (event.source !== window) {
      return;
   }

   const data = event.data;
   if (!data || data.source !== BRIDGE_EVENT_SOURCE || data.type !== "TOKENS_UPDATED") {
      return;
   }

   chrome.runtime.sendMessage(
      {
         type: "SYNC_AUTH_TOKEN",
         payload: data.payload,
      },
      (response) => {
         if (chrome.runtime.lastError) {
            console.warn("Auth bridge sync failed:", chrome.runtime.lastError.message);
            return;
         }

         if (!response?.accepted) {
            console.warn(
               "Auth bridge sync rejected by worker:",
               response?.error || "Unknown error",
            );
         }
      },
   );
}

function initializeAuthBridge() {
   if (!isBridgeTargetPage()) {
      return;
   }

   window.addEventListener("message", handleBridgeMessage);
   injectAuthBridgeScript();

   window.setTimeout(() => {
      requestTokenSyncFromPageBridge();
   }, 250);

   document.addEventListener("visibilitychange", () => {
      if (!document.hidden) {
         requestTokenSyncFromPageBridge();
      }
   });
}

initializeAuthBridge();

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

   if (request.type === "DISPLAY_SNIPPET_RESULT") {
      import("./modules/ui.jsx").then(({ displayResultCard, removeLoadingCard, successCard }) => {
         setTimeout(() => {
            removeLoadingCard();
         }, 2000);
         successCard("Analysis complete!");
         displayResultCard(request.data);
      });
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_SNIPPET_CACHED_RESULT") {
      import("./modules/ui.jsx").then(
         ({ displayCachedResultCard, removeLoadingCard, successCard }) => {
            setTimeout(() => {
               removeLoadingCard();
            }, 1000);
            successCard("Previously verified claim found!");
            displayCachedResultCard(request.data);
         },
      );
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_SNIPPET_ERROR") {
      import("./modules/ui.jsx").then(({ removeLoadingCard, displayErrorCard }) => {
         removeLoadingCard();
         displayErrorCard(request.message || "Failed to analyze image. Please try again.");
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
