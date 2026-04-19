import { fetchClaimResult } from "./modules/api.js";
import {
   buildAuthHeaders,
   clearAuthSession,
   isTrustedWebOrigin,
   saveAuthSession,
} from "./modules/auth.js";
import { state } from "./modules/state.js";

console.log("TruthLens background service worker loaded");

function sendTabMessage(tabId, message) {
   if (!Number.isInteger(tabId)) return;
   chrome.tabs.sendMessage(tabId, message);
}

function resolveSenderOrigin(sender) {
   if (sender?.origin) {
      return sender.origin;
   }

   if (!sender?.url) {
      return null;
   }

   try {
      return new URL(sender.url).origin;
   } catch (_error) {
      return null;
   }
}

async function postJsonWithAuthFallback(path, payload) {
   const url = `${state.API_BASE_URL}/${path}`;
   const baseHeaders = { "content-type": "application/json" };
   const headersWithAuth = await buildAuthHeaders(baseHeaders);

   let response = await fetch(url, {
      method: "POST",
      headers: headersWithAuth,
      body: JSON.stringify(payload),
   });

   if (response.status === 401 && headersWithAuth.Authorization) {
      await clearAuthSession();
      response = await fetch(url, {
         method: "POST",
         headers: baseHeaders,
         body: JSON.stringify(payload),
      });
   }

   return response;
}

function startPollingClaim({
   claimId,
   tabId,
   successType,
   timeoutMessage,
   timeoutPayload,
   maxPolls = 20,
   pollEveryMs = 3000,
}) {
   let pollCount = 0;

   const pollInterval = setInterval(async () => {
      pollCount++;
      if (pollCount > maxPolls) {
         clearInterval(pollInterval);
         console.error("Polling timed out");
         if (timeoutPayload) {
            sendTabMessage(tabId, {
               type: timeoutMessage,
               data: timeoutPayload,
            });
         } else {
            sendTabMessage(tabId, {
               type: timeoutMessage,
               message: "Failed to get claim result. Please try again later.",
            });
         }
         return;
      }

      const claim = await fetchClaimResult(claimId);
      if (claim && claim.verdict !== "PENDING") {
         clearInterval(pollInterval);
         sendTabMessage(tabId, {
            type: successType,
            data: claim,
         });
      }
   }, pollEveryMs);
}

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "SYNC_AUTH_TOKEN") {
      const payload = request.payload || {};
      const senderOrigin = resolveSenderOrigin(sender);

      if (!isTrustedWebOrigin(senderOrigin)) {
         sendResponse({ accepted: false, error: "Untrusted origin for token sync." });
         return false;
      }

      const accessToken =
         typeof payload.access === "string" && payload.access.trim() ? payload.access : null;
      const refreshToken =
         typeof payload.refresh === "string" && payload.refresh.trim() ? payload.refresh : null;

      (async () => {
         if (!accessToken && !refreshToken) {
            await clearAuthSession();
            sendResponse({ accepted: true, mode: "cleared" });
            return;
         }

         await saveAuthSession({
            accessToken,
            refreshToken,
            origin: senderOrigin,
         });
         sendResponse({ accepted: true, mode: "stored" });
      })().catch((error) => {
         sendResponse({ accepted: false, error: error?.message || "Token sync failed." });
      });

      return true;
   }

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

   if (request.type === "VERIFY_SNIPPET") {
      const tabId = request.tabId ?? sender?.tab?.id;
      const payload = request.payload;

      if (!Number.isInteger(tabId)) {
         sendResponse({ accepted: false, error: "No active tab found for snippet verification." });
         return false;
      }

      if (!payload?.image_data) {
         sendResponse({ accepted: false, error: "Missing screenshot payload." });
         return false;
      }

      sendResponse({ accepted: true });

      postJsonWithAuthFallback("analyze/", payload)
         .then(async (res) => {
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
               throw new Error(data?.detail || data?.error || "Snippet verification failed.");
            }
            return data;
         })
         .then((data) => {
            if (data.cached && data.match) {
               sendTabMessage(tabId, {
                  type: "DISPLAY_SNIPPET_CACHED_RESULT",
                  data: data.match,
               });
               return;
            }

            startPollingClaim({
               claimId: data.claim_id,
               tabId,
               successType: "DISPLAY_SNIPPET_RESULT",
               timeoutMessage: "DISPLAY_SNIPPET_ERROR",
               maxPolls: 50,
               pollEveryMs: 3000,
            });
         })
         .catch((err) => {
            console.error("Snippet verification failed:", err);
            sendTabMessage(tabId, {
               type: "DISPLAY_SNIPPET_ERROR",
               message: "Failed to analyze image. Please try again later.",
            });
         });

      return true;
   }

   if (request.type === "VERIFY_URL") {
      const { url, tabId } = request;

      postJsonWithAuthFallback("verify-url/", { url: url })
         .then(async (res) => {
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
               throw new Error(data?.detail || "URL verification failed.");
            }
            return data;
         })
         .then((data) => {
            startPollingClaim({
               claimId: data.claim_id,
               tabId,
               successType: "DISPLAY_URL_RESULT",
               timeoutMessage: "DISPLAY_URL_RESULT",
               timeoutPayload: {
                  verdict: "UNVERIFIED",
                  summary: "Verification timed out. Please try again.",
                  confidence_score: 0,
                  source_type: "Timeout",
                  source_url: "#",
               },
               maxPolls: 20,
               pollEveryMs: 3000,
            });
         })
         .catch((err) => {
            console.error("URL verification failed:", err);
            sendTabMessage(tabId, {
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
