import "./content.css";
import { state } from "./modules/state.js";
import { startCropStudio } from "./modules/screenshot.jsx";

const BRIDGE_EVENT_SOURCE = "TRUTHLENS_WEB_AUTH_BRIDGE";
const EXTENSION_EVENT_SOURCE = "TRUTHLENS_EXTENSION";
const BRIDGE_SCRIPT_ID = "truthlens-auth-bridge-script";
const TOKEN_SYNC_POLL_MS = 3000;
const WEB_AUTH_SESSION_ID_KEY = "truthlens_auth_session_id";
const WEB_AUTH_SESSION_STARTED_AT_KEY = "truthlens_auth_session_started_at";
const WEB_AUTH_UPDATED_AT_KEY = "truthlens_auth_updated_at";

let lastSyncedTokenFingerprint = null;

function normalizeTokenPayload(payload = {}) {
   const access = typeof payload.access === "string" && payload.access.trim() ? payload.access.trim() : null;
   const refresh = typeof payload.refresh === "string" && payload.refresh.trim() ? payload.refresh.trim() : null;
   const persistence = payload.persistence === "local" ? "local" : access || refresh ? "session" : null;
   const sessionId =
      typeof payload.sessionId === "string" && payload.sessionId.trim()
         ? payload.sessionId.trim()
         : null;
   const sessionStartedAt = Number(payload.sessionStartedAt) || null;
   const updatedAt = Number(payload.updatedAt) || null;

   return {
      access,
      refresh,
      persistence,
      sessionId,
      sessionStartedAt,
      updatedAt,
   };
}

function getTokenFingerprint(tokens) {
   return [
      tokens?.access || "",
      tokens?.refresh || "",
      tokens?.persistence || "",
      tokens?.sessionId || "",
      tokens?.sessionStartedAt || "",
      tokens?.updatedAt || "",
   ].join("::");
}

function syncTokensToWorker(tokens, reason = "unknown") {
   const normalizedTokens = normalizeTokenPayload(tokens);
   const fingerprint = getTokenFingerprint(normalizedTokens);
   if (fingerprint === lastSyncedTokenFingerprint) {
      return;
   }

   lastSyncedTokenFingerprint = fingerprint;

   chrome.runtime.sendMessage(
      {
         type: "SYNC_AUTH_TOKEN",
         payload: {
            ...normalizedTokens,
            reason,
         },
      },
      (response) => {
         if (chrome.runtime.lastError) {
            console.warn("Auth bridge sync failed:", chrome.runtime.lastError.message);
            return;
         }

         if (!response?.accepted) {
            console.warn("Auth bridge sync rejected by worker:", response?.error || "Unknown error");
         }
      },
   );
}

function readTokensFromPageStorage() {
   try {
      const readStorage = (storage, persistence) => {
         const access = storage.getItem("access");
         const refresh = storage.getItem("refresh");

         if (!access && !refresh) {
            return null;
         }

         return normalizeTokenPayload({
            access,
            refresh,
            persistence,
            sessionId: storage.getItem(WEB_AUTH_SESSION_ID_KEY),
            sessionStartedAt: storage.getItem(WEB_AUTH_SESSION_STARTED_AT_KEY),
            updatedAt: storage.getItem(WEB_AUTH_UPDATED_AT_KEY),
         });
      };

      return (
         readStorage(window.localStorage, "local") ||
         readStorage(window.sessionStorage, "session") ||
         normalizeTokenPayload()
      );
   } catch {
      return normalizeTokenPayload();
   }
}

function syncTokensDirectlyFromStorage(reason) {
   syncTokensToWorker(readTokensFromPageStorage(), reason);
}

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

   syncTokensToWorker(data.payload, "page_bridge");
}

function initializeAuthBridge() {
   if (!isBridgeTargetPage()) {
      return;
   }

   restoreTokensFromWorker(() => {
      window.addEventListener("message", handleBridgeMessage);
      injectAuthBridgeScript();

      window.setTimeout(() => {
         requestTokenSyncFromPageBridge();
         syncTokensDirectlyFromStorage("storage_initial");
      }, 250);

      document.addEventListener("visibilitychange", () => {
         if (!document.hidden) {
            requestTokenSyncFromPageBridge();
            syncTokensDirectlyFromStorage("storage_visibility");
         }
      });

      window.setInterval(() => {
         syncTokensDirectlyFromStorage("storage_poll");
      }, TOKEN_SYNC_POLL_MS);
   });
}

initializeAuthBridge();

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "ACTIVATE_SNIPPING") {
      state.snipIntent = request.intent || "factcheck";
      activateSnippingMode();
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_DEEPFAKE_RESULT") {
      import("./modules/ui.jsx").then(({ displayDeepfakeResultCard, removeLoadingCard }) => {
         removeLoadingCard();
         setTimeout(() => displayDeepfakeResultCard(request.data), 100);
      });
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_URL_LOADING") {
      import("./modules/ui.jsx").then(({ displayLoadingCard }) => {
         state.isAnalyzing = true;
         displayLoadingCard(request.customMsg);
      });
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_URL_RESULT" || request.type === "DISPLAY_TEXT_RESULT") {
      import("./modules/ui.jsx").then(({ displayResultCard, removeLoadingCard }) => {
         removeLoadingCard();
         setTimeout(() => displayResultCard(request.data), 2000);
      });
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_URL_ERROR" || request.type === "DISPLAY_TEXT_ERROR") {
      import("./modules/ui.jsx").then(({ displayErrorCard, removeLoadingCard }) => {
         removeLoadingCard();
         displayErrorCard(
            request.message ||
               (request.type === "DISPLAY_TEXT_ERROR"
                  ? "Unable to verify this text. Please try again."
                  : "Unable to verify this URL. Please try again."),
         );
      });
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_SNIPPET_RESULT" || request.type === "DISPLAY_IMAGE_RESULT") {
      import("./modules/ui.jsx").then(({ displayResultCard, removeLoadingCard, successCard }) => {
         setTimeout(() => {
            removeLoadingCard();
         }, 2000);
         successCard("Analysis complete!");
         displayResultCard(request.data);
      });
      sendResponse({ success: true });
   }

   if (
      request.type === "DISPLAY_SNIPPET_CACHED_RESULT" ||
      request.type === "DISPLAY_IMAGE_CACHED_RESULT" ||
      request.type === "DISPLAY_URL_CACHED_RESULT" ||
      request.type === "DISPLAY_TEXT_CACHED_RESULT"
   ) {
      import("./modules/ui.jsx").then(({ displayResultCard, removeLoadingCard, successCard }) => {
         setTimeout(() => {
            removeLoadingCard();
         }, 1000);
         successCard("Previous TruthLens result found!");
         displayResultCard(request.data);
      });
      sendResponse({ success: true });
   }

   if (request.type === "DISPLAY_SNIPPET_ERROR" || request.type === "DISPLAY_IMAGE_ERROR") {
      import("./modules/ui.jsx").then(({ removeLoadingCard, displayErrorCard }) => {
         removeLoadingCard();
         displayErrorCard(request.message || "Failed to analyze image. Please try again.");
      });
      sendResponse({ success: true });
   }
});

function activateSnippingMode() {
   state.isSnipping = true;

   startCropStudio();
}

function restoreTokensFromWorker(onComplete) {
   chrome.runtime.sendMessage(
      {
         type: "REQUEST_WEB_AUTH_SESSION",
      },
      (response) => {
         if (chrome.runtime.lastError) {
            console.warn("Auth session restore failed:", chrome.runtime.lastError.message);

            onComplete?.();
            return;
         }

         if (!response?.accepted) {
            onComplete?.();
            return;
         }

         const restored = normalizeTokenPayload(response);

         try {
            const pageAccess = window.localStorage.getItem("access") || window.sessionStorage.getItem("access");
            const pageRefresh = window.localStorage.getItem("refresh") || window.sessionStorage.getItem("refresh");
            const pageHasAuthMaterial = Boolean(pageAccess || pageRefresh);

            if (!pageHasAuthMaterial && (restored.access || restored.refresh)) {
               const targetStorage =
                  restored.persistence === "local"
                     ? window.localStorage
                     : window.sessionStorage;
               const otherStorage =
                  restored.persistence === "local"
                     ? window.sessionStorage
                     : window.localStorage;

               ["access", "refresh", WEB_AUTH_SESSION_ID_KEY, WEB_AUTH_SESSION_STARTED_AT_KEY, WEB_AUTH_UPDATED_AT_KEY]
                  .forEach((key) => otherStorage.removeItem(key));

               if (restored.access) {
                  targetStorage.setItem("access", restored.access);
               }

               if (restored.refresh) {
                  targetStorage.setItem("refresh", restored.refresh);
               }

               if (restored.sessionId) {
                  targetStorage.setItem(WEB_AUTH_SESSION_ID_KEY, restored.sessionId);
               }

               if (restored.sessionStartedAt) {
                  targetStorage.setItem(
                     WEB_AUTH_SESSION_STARTED_AT_KEY,
                     String(restored.sessionStartedAt),
                  );
               }

               if (restored.updatedAt) {
                  targetStorage.setItem(
                     WEB_AUTH_UPDATED_AT_KEY,
                     String(restored.updatedAt),
                  );
               }
            }
         } catch (error) {
            console.warn("Failed to restore TruthLens web session:", error);
         }

         onComplete?.();
      },
   );
}
