import { fetchClaimResult } from "./modules/api.js";
import {
   buildAuthHeaders,
   clearAuthSession,
   getAuthSession,
   isTrustedWebOrigin,
   saveAuthSession,
} from "./modules/auth.js";
import { state } from "./modules/state.js";

console.log("TruthLens background service worker loaded");

const GUEST_SCANS_STORAGE_KEY = "guest_scans";
const GUEST_SCANS_CAP = 3;
const GUEST_SCAN_SYNC_ENDPOINT = "auth/guest-scan-sync/";
const GUEST_SCAN_SYNC_STATUS_STORAGE_KEY = "guest_scan_sync_status";

let isGuestScanSyncInProgress = false;

function storageLocalGet(keys) {
   return new Promise((resolve) => {
      chrome.storage.local.get(keys, (result) => {
         resolve(result || {});
      });
   });
}

function storageLocalSet(payload) {
   return new Promise((resolve) => {
      chrome.storage.local.set(payload, () => resolve());
   });
}

function storageLocalRemove(keys) {
   return new Promise((resolve) => {
      chrome.storage.local.remove(keys, () => resolve());
   });
}

async function writeGuestScanSyncStatus(payload) {
   await storageLocalSet({
      [GUEST_SCAN_SYNC_STATUS_STORAGE_KEY]: {
         ...payload,
         updated_at: new Date().toISOString(),
      },
   });
}

function normalizeGuestScanRecord({ verdictPayload, scanType }) {
   if (!verdictPayload || typeof verdictPayload !== "object") {
      return null;
   }

   const verdict = verdictPayload.final_verdict || verdictPayload.verdict || "UNVERIFIED";
   const confidenceScore = Number(verdictPayload.confidence_score ?? 0);

   return {
      scan_type: scanType,
      verdict,
      summary: verdictPayload.summary || "",
      confidence_score: Number.isFinite(confidenceScore) ? confidenceScore : 0,
      source_type: verdictPayload.source_type || "Unknown",
      source_url: verdictPayload.source_url || "",
      claim_id: verdictPayload.id || verdictPayload.claim_id || null,
      thread_id: verdictPayload.thread_id || null,
      scanned_at: new Date().toISOString(),
   };
}

async function appendGuestScan(verdictPayload, scanType) {
   const nextRecord = normalizeGuestScanRecord({ verdictPayload, scanType });
   if (!nextRecord) {
      return;
   }

   const stored = await storageLocalGet([GUEST_SCANS_STORAGE_KEY]);
   const existing = Array.isArray(stored[GUEST_SCANS_STORAGE_KEY])
      ? stored[GUEST_SCANS_STORAGE_KEY]
      : [];
   const capped = [...existing, nextRecord].slice(-GUEST_SCANS_CAP);

   await storageLocalSet({
      [GUEST_SCANS_STORAGE_KEY]: capped,
   });
}

async function shouldUseGuestCaching() {
   try {
      const session = await getAuthSession();
      return !session?.accessToken;
   } catch (_error) {
      return false;
   }
}

async function fetchAuthenticatedUsername() {
   const headersWithAuth = await buildAuthHeaders({ "content-type": "application/json" });
   if (!headersWithAuth.Authorization) {
      return null;
   }

   const response = await fetch(`${state.API_BASE_URL}/auth/me/`, {
      method: "GET",
      headers: headersWithAuth,
   });

   if (response.status === 401) {
      await clearAuthSession();
      return null;
   }

   if (!response.ok) {
      return null;
   }

   const payload = await response.json().catch(() => null);
   if (!payload || typeof payload.username !== "string") {
      return null;
   }

   return payload.username;
}

async function syncGuestScansWithBackend() {
   const stored = await storageLocalGet([GUEST_SCANS_STORAGE_KEY]);
   const guestScans = Array.isArray(stored[GUEST_SCANS_STORAGE_KEY])
      ? stored[GUEST_SCANS_STORAGE_KEY]
      : [];

   if (!guestScans.length) {
      return { synced: 0, skipped: true, reason: "no_guest_scans" };
   }

   const headersWithAuth = await buildAuthHeaders({ "content-type": "application/json" });
   if (!headersWithAuth.Authorization) {
      return { synced: 0, skipped: true, reason: "missing_access_token" };
   }

   let syncedCount = 0;
   let remainingScans = [...guestScans];

   for (const scan of guestScans) {
      const response = await fetch(`${state.API_BASE_URL}/${GUEST_SCAN_SYNC_ENDPOINT}`, {
         method: "POST",
         headers: headersWithAuth,
         body: JSON.stringify({ scan }),
      });

      const responseData = await response.json().catch(() => ({}));

      if (response.status === 401) {
         await clearAuthSession();
         throw new Error(responseData?.detail || "Authentication expired during guest sync.");
      }

      if (!response.ok) {
         throw new Error(responseData?.detail || responseData?.error || "Guest scan sync failed.");
      }

      syncedCount += 1;
      remainingScans = remainingScans.slice(1);
      await storageLocalSet({ [GUEST_SCANS_STORAGE_KEY]: remainingScans });
   }

   await storageLocalRemove([GUEST_SCANS_STORAGE_KEY]);
   return { synced: syncedCount, skipped: false };
}

async function maybeSyncGuestScansAfterLogin() {
   if (isGuestScanSyncInProgress) {
      return { synced: 0, skipped: true, reason: "sync_in_progress" };
   }

   isGuestScanSyncInProgress = true;
   try {
      const syncResult = await syncGuestScansWithBackend();

      if (syncResult?.synced > 0) {
         await writeGuestScanSyncStatus({
            status: "success",
            synced_count: syncResult.synced,
         });
      }

      return syncResult;
   } catch (error) {
      console.warn("Guest scan sync failed:", error);
      const syncErrorMessage = error?.message || "Guest scan sync failed.";
      await writeGuestScanSyncStatus({
         status: "error",
         synced_count: 0,
         error: syncErrorMessage,
      });

      return {
         synced: 0,
         skipped: false,
         error: syncErrorMessage,
      };
   } finally {
      isGuestScanSyncInProgress = false;
   }
}

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
   onResolved,
   onTimeout,
   maxPolls = 20,
   pollEveryMs = 3000,
}) {
   let pollCount = 0;

   const pollInterval = setInterval(async () => {
      pollCount++;
      if (pollCount > maxPolls) {
         clearInterval(pollInterval);
         console.error("Polling timed out");

         if (typeof onTimeout === "function") {
            try {
               await onTimeout(timeoutPayload);
            } catch (cacheError) {
               console.warn("Failed to cache guest timeout verdict:", cacheError);
            }
         }

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

         if (typeof onResolved === "function") {
            try {
               await onResolved(claim);
            } catch (cacheError) {
               console.warn("Failed to cache guest scan verdict:", cacheError);
            }
         }

         sendTabMessage(tabId, {
            type: successType,
            data: claim,
         });
      }
   }, pollEveryMs);
}

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "SYNC_GUEST_SCANS_NOW") {
      (async () => {
         const session = await getAuthSession();
         if (!session?.accessToken) {
            sendResponse({ accepted: false, error: "No authenticated session." });
            return;
         }

         const guestSync = await maybeSyncGuestScansAfterLogin();
         sendResponse({ accepted: true, guestSync });
      })().catch((error) => {
         sendResponse({ accepted: false, error: error?.message || "Guest sync retry failed." });
      });

      return true;
   }

   if (request.type === "GET_AUTH_CONTEXT") {
      (async () => {
         const session = await getAuthSession();
         const hasAccessToken = Boolean(session?.accessToken);
         if (!hasAccessToken) {
            sendResponse({ accepted: true, isGuest: true, username: null });
            return;
         }

         const username = await fetchAuthenticatedUsername();
         sendResponse({ accepted: true, isGuest: false, username });
      })().catch((error) => {
         sendResponse({ accepted: false, error: error?.message || "Failed to load auth context." });
      });

      return true;
   }

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
            await storageLocalRemove([GUEST_SCAN_SYNC_STATUS_STORAGE_KEY]);
            sendResponse({ accepted: true, mode: "cleared" });
            return;
         }

         await saveAuthSession({
            accessToken,
            refreshToken,
            origin: senderOrigin,
         });

         const guestSync = await maybeSyncGuestScansAfterLogin();
         sendResponse({ accepted: true, mode: "stored", guestSync });
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

      (async () => {
         const shouldCacheGuestScan = await shouldUseGuestCaching();

         try {
            const res = await postJsonWithAuthFallback("analyze/", payload);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
               throw new Error(data?.detail || data?.error || "Snippet verification failed.");
            }

            if (data.cached && data.match) {
               if (shouldCacheGuestScan) {
                  appendGuestScan(data.match, "SNIPPET").catch((cacheError) => {
                     console.warn("Failed to cache guest snippet verdict:", cacheError);
                  });
               }

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
               onResolved: shouldCacheGuestScan
                  ? (claim) => appendGuestScan(claim, "SNIPPET")
                  : null,
               maxPolls: 50,
               pollEveryMs: 3000,
            });
         } catch (err) {
            console.error("Snippet verification failed:", err);
            sendTabMessage(tabId, {
               type: "DISPLAY_SNIPPET_ERROR",
               message: "Failed to analyze image. Please try again later.",
            });
         }
      })();

      return true;
   }

   if (request.type === "VERIFY_DEEPFAKE") {
      const tabId = request.tabId ?? sender?.tab?.id;
      const payload = request.payload;

      if (!Number.isInteger(tabId)) {
         sendResponse({ accepted: false, error: "No active tab" });
         return false;
      }
      sendResponse({ accepted: true });

      (async () => {
         try {
            const res = await postJsonWithAuthFallback("test-deepfake/", payload);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data?.error || "Deepfake check failed");

            sendTabMessage(tabId, { type: "DISPLAY_DEEPFAKE_RESULT", data });
         } catch (err) {
            sendTabMessage(tabId, { type: "DISPLAY_SNIPPET_ERROR", message: err.message });
         }
      })();
      return true;
   }

   if (request.type === "VERIFY_URL") {
      const { url, tabId } = request;

      (async () => {
         const shouldCacheGuestScan = await shouldUseGuestCaching();

         try {
            const res = await postJsonWithAuthFallback("verify-url/", { url: url });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
               throw new Error(data?.detail || "URL verification failed.");
            }

            const timeoutFallback = {
               verdict: "UNVERIFIED",
               summary: "Verification timed out. Please try again.",
               confidence_score: 0,
               source_type: "Timeout",
               source_url: "#",
            };

            startPollingClaim({
               claimId: data.claim_id,
               tabId,
               successType: "DISPLAY_URL_RESULT",
               timeoutMessage: "DISPLAY_URL_RESULT",
               timeoutPayload: timeoutFallback,
               onResolved: shouldCacheGuestScan ? (claim) => appendGuestScan(claim, "URL") : null,
               onTimeout: shouldCacheGuestScan
                  ? (timeoutData) => appendGuestScan(timeoutData, "URL")
                  : null,
               maxPolls: 20,
               pollEveryMs: 3000,
            });
         } catch (err) {
            console.error("URL verification failed:", err);

            const errorFallback = {
               verdict: "UNVERIFIED",
               summary: "Verification failed. Please try again.",
               confidence_score: 0,
               source_type: "Error",
               source_url: "#",
            };

            if (shouldCacheGuestScan) {
               appendGuestScan(errorFallback, "URL").catch((cacheError) => {
                  console.warn("Failed to cache guest URL fallback verdict:", cacheError);
               });
            }

            sendTabMessage(tabId, {
               type: "DISPLAY_URL_RESULT",
               data: errorFallback,
            });
         }
      })();

      return true;
   }

   if (request.type === "VERIFY_FILE") {
      const tabId = request.tabId ?? sender?.tab?.id; // <--- Grabs the tabId we passed from the popup
      const payload = request.payload;
      const endpoint= "verify-file/";

      sendResponse({ accepted: true, success: true });
(async () => {
         // Also adding guest scan caching support so file scans save to the local library!
         const shouldCacheGuestScan = await shouldUseGuestCaching();

         try {
            const res = await postJsonWithAuthFallback(endpoint, payload);
            const data = await res.json().catch(() => ({}));
            
            if (!res.ok) {
               throw new Error(data?.error || data?.detail || "File verification failed.");
            }

            // Start polling using the exact tabId
            startPollingClaim({
               claimId: data.claim_id,
               tabId: tabId, 
               successType: "DISPLAY_SNIPPET_RESULT", 
               timeoutMessage: "DISPLAY_SNIPPET_ERROR",
               onResolved: shouldCacheGuestScan ? (claim) => appendGuestScan(claim, "FILE") : null,
               maxPolls: 40, 
               pollEveryMs: 3000,
            });
         } catch (err) {
            console.error("File verification failed:", err);
            sendTabMessage(tabId, { 
               type: "DISPLAY_SNIPPET_ERROR", 
               message: err.message || "Failed to process document." 
            });
         }
      })();

      return true;
   }
});   