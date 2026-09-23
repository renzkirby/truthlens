import { fetchClaimResult } from "./modules/api.js";
import {
   authenticatedFetch,
   getAuthSession,
   isTrustedWebOrigin,
   replaceAuthSession,
   clearAuthSession,
} from "./modules/auth.js";
import { state } from "./modules/state.js";

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

   const rawClaimId = verdictPayload.id || verdictPayload.claim_id;
   const claimId = typeof rawClaimId === "string" ? rawClaimId.trim() : "";
   if (!claimId) {
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
      claim_id: claimId,
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
   const existing = Array.isArray(stored[GUEST_SCANS_STORAGE_KEY]) ? stored[GUEST_SCANS_STORAGE_KEY] : [];
   const capped = [...existing, nextRecord].slice(-GUEST_SCANS_CAP);

   await storageLocalSet({
      [GUEST_SCANS_STORAGE_KEY]: capped,
   });
}

async function cacheGuestScanIfCurrentGuest(verdictPayload, scanType) {
   try {
      const session = await getAuthSession();
      if (session?.accessToken) {
         return false;
      }

      await appendGuestScan(verdictPayload, scanType);
      return true;
   } catch {
      return false;
   }
}

async function persistGuestScanQueue(scans) {
   if (!scans.length) {
      await storageLocalRemove([GUEST_SCANS_STORAGE_KEY]);
      return;
   }

   await storageLocalSet({ [GUEST_SCANS_STORAGE_KEY]: scans });
}

function hasUsableGuestClaimId(scan) {
   return typeof scan?.claim_id === "string" && Boolean(scan.claim_id.trim());
}

async function fetchAuthenticatedUsername() {
   const session = await getAuthSession();
   if (!session.accessToken) {
      return null;
   }

   const response = await authenticatedFetch(
      `${state.API_BASE_URL}/auth/me/`,
      {
         method: "GET",
         headers: { "content-type": "application/json" },
      },
      { requireAuth: true },
   );

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
   const guestScans = Array.isArray(stored[GUEST_SCANS_STORAGE_KEY]) ? stored[GUEST_SCANS_STORAGE_KEY] : [];

   if (!guestScans.length) {
      return { synced: 0, discarded: 0, skipped: true, reason: "no_guest_scans" };
   }

   const session = await getAuthSession();
   if (!session.accessToken) {
      return { synced: 0, discarded: 0, skipped: true, reason: "missing_access_token" };
   }

   let syncedCount = 0;
   let discardedCount = 0;
   let remainingScans = [...guestScans];

   while (remainingScans.length) {
      const scan = remainingScans[0];

      if (!hasUsableGuestClaimId(scan)) {
         discardedCount += 1;
         remainingScans = remainingScans.slice(1);
         await persistGuestScanQueue(remainingScans);
         continue;
      }

      const response = await authenticatedFetch(
         `${state.API_BASE_URL}/${GUEST_SCAN_SYNC_ENDPOINT}`,
         {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ scan }),
         },
         { requireAuth: true },
      );

      const responseData = await response.json().catch(() => ({}));

      if (response.status === 401) {
         throw new Error(responseData?.detail || "Authentication expired during guest sync.");
      }

      if (response.status === 400 || response.status === 404) {
         discardedCount += 1;
         remainingScans = remainingScans.slice(1);
         await persistGuestScanQueue(remainingScans);
         continue;
      }

      if (!response.ok) {
         throw new Error(responseData?.detail || responseData?.error || "Guest scan sync failed.");
      }

      syncedCount += 1;
      remainingScans = remainingScans.slice(1);
      await persistGuestScanQueue(remainingScans);
   }

   return { synced: syncedCount, discarded: discardedCount, skipped: false };
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
   } catch {
      return null;
   }
}

async function postJsonWithAuth(path, payload) {
   const url = `${state.API_BASE_URL}/${path}`;
   return authenticatedFetch(
      url,
      {
         method: "POST",
         headers: { "content-type": "application/json" },
         body: JSON.stringify(payload),
      },
      { allowGuestAfterAuthFailure: true },
   );
}

function startPollingClaim({
   claimId,
   tabId,
   successType,
   timeoutMessage,
   onResolved,
   maxPolls = 20,
   pollEveryMs = 3000,
}) {
   let pollCount = 0;
   let isPollInFlight = false;

   const stopWithError = (message) => {
      clearInterval(pollInterval);
      sendTabMessage(tabId, {
         type: timeoutMessage,
         message,
      });
   };

   const pollInterval = setInterval(async () => {
      if (isPollInFlight) {
         return;
      }

      if (pollCount >= maxPolls) {
         console.error("Polling timed out");
         stopWithError("Verification timed out. Please try again.");
         return;
      }

      pollCount++;
      isPollInFlight = true;

      try {
         const claim = await fetchClaimResult(claimId);
         if (claim.verdict === "PENDING") {
            return;
         }

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
      } catch (error) {
         const errorStatus = Number.isInteger(error?.status) ? error.status : null;
         const isTerminalFailure = errorStatus !== null && errorStatus < 500;

         if (isTerminalFailure) {
            const message =
               errorStatus === 404
                  ? "The claim result was not found. Please start the verification again."
                  : "Unable to retrieve the verification result. Please try again.";
            stopWithError(message);
            return;
         }

         console.warn("Transient claim polling failure:", error?.message || error);
         if (pollCount >= maxPolls) {
            stopWithError("Unable to retrieve the verification result. Please try again.");
         }
      } finally {
         isPollInFlight = false;
      }
   }, pollEveryMs);
}

async function recordExtensionPublicReach(request) {
   const allowedFields = ["type", "event_type", "source_surface", "organization_slug", "publication_id"];
   if (
      !request ||
      Object.keys(request).some((key) => !allowedFields.includes(key)) ||
      !["EXTENSION_PUBLICATION_IMPRESSION", "EXTENSION_PUBLICATION_CLICK"].includes(request.event_type) ||
      !["EXTENSION_OFFICIAL_FACT_CHECK", "EXTENSION_RELATED_FACT_CHECK"].includes(request.source_surface) ||
      typeof request.organization_slug !== "string" ||
      !/^[a-zA-Z0-9_-]{1,255}$/.test(request.organization_slug) ||
      typeof request.publication_id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(request.publication_id) ||
      !state.API_BASE_URL
   )
      return;
   try {
      await fetch(`${state.API_BASE_URL}/public-reach/events/`, {
         method: "POST",
         credentials: "omit",
         referrerPolicy: "no-referrer",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({
            client_event_id: crypto.randomUUID(),
            event_type: request.event_type,
            source_surface: request.source_surface,
            organization_slug: request.organization_slug,
            publication_id: request.publication_id,
         }),
      });
   } catch {
      // Best effort only, with no auth session access, refresh, clearing, or retry.
   }
}

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "RECORD_PUBLIC_REACH") {
      recordExtensionPublicReach(request)
         .then(() => sendResponse({ accepted: true }))
         .catch(() => sendResponse({ accepted: false }));
      return true;
   }
   if (request.type === "REQUEST_WEB_AUTH_SESSION") {
      (async () => {
         const session = await getAuthSession();

         sendResponse({
            accepted: true,
            access: session?.accessToken || null,
            refresh: session?.refreshToken || null,
         });
      })().catch((error) => {
         sendResponse({
            accepted: false,
            error: error?.message || "Failed to restore auth session.",
         });
      });

      return true;
   }

   if (request.type === "SYNC_GUEST_SCANS_NOW") {
      (async () => {
         const session = await getAuthSession();
         if (!session?.accessToken) {
            sendResponse({
               accepted: false,
               error: "No authenticated session.",
            });
            return;
         }

         const guestSync = await maybeSyncGuestScansAfterLogin();
         sendResponse({ accepted: true, guestSync });
      })().catch((error) => {
         sendResponse({
            accepted: false,
            error: error?.message || "Guest sync retry failed.",
         });
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
         const currentSession = await getAuthSession();

         if (!currentSession?.accessToken) {
            sendResponse({ accepted: true, isGuest: true, username: null });
            return;
         }

         sendResponse({ accepted: true, isGuest: false, username });
      })().catch((error) => {
         sendResponse({
            accepted: false,
            error: error?.message || "Failed to load auth context.",
         });
      });

      return true;
   }

   if (request.type === "SYNC_AUTH_TOKEN") {
      const payload = request.payload || {};
      const senderOrigin = resolveSenderOrigin(sender);

      if (!isTrustedWebOrigin(senderOrigin)) {
         sendResponse({
            accepted: false,
            error: "Untrusted origin for token sync.",
         });
         return false;
      }

      const accessToken = typeof payload.access === "string" && payload.access.trim() ? payload.access : null;
      const refreshToken = typeof payload.refresh === "string" && payload.refresh.trim() ? payload.refresh : null;

      (async () => {
         if (!accessToken && !refreshToken) {
            await clearAuthSession();
            await storageLocalRemove([GUEST_SCAN_SYNC_STATUS_STORAGE_KEY]);
            sendResponse({ accepted: true, mode: "cleared" });
            return;
         }

         await replaceAuthSession({
            accessToken,
            refreshToken,
            origin: senderOrigin,
         });

         const guestSync = await maybeSyncGuestScansAfterLogin();
         sendResponse({ accepted: true, mode: "stored", guestSync });
      })().catch((error) => {
         sendResponse({
            accepted: false,
            error: error?.message || "Token sync failed.",
         });
      });

      return true;
   }

   if (request.type === "CAPTURE_SCREENSHOT") {
      chrome.tabs.captureVisibleTab(null, { format: "png" }, function (dataUrl) {
         if (chrome.runtime.lastError) {
            console.error("Screenshot error:", chrome.runtime.lastError);
            sendResponse({ error: chrome.runtime.lastError.message });
            return;
         }

         sendResponse({ screenshot: dataUrl });
      });

      return true;
   }

   if (request.type === "VERIFY_SNIPPET") {
      const tabId = request.tabId ?? sender?.tab?.id;
      const payload = request.payload;

      if (!Number.isInteger(tabId)) {
         sendResponse({
            accepted: false,
            error: "No active tab found for snippet verification.",
         });
         return false;
      }

      if (!payload?.image_data) {
         sendResponse({
            accepted: false,
            error: "Missing screenshot payload.",
         });
         return false;
      }

      sendResponse({ accepted: true });

      (async () => {
         try {
            const res = await postJsonWithAuth("analyze/", payload);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
               throw new Error(data?.detail || data?.error || "Snippet verification failed.");
            }

            if (data.cached && data.match) {
               cacheGuestScanIfCurrentGuest(data.match, "SNIPPET").catch((cacheError) => {
                  console.warn("Failed to cache guest snippet verdict:", cacheError);
               });

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
               onResolved: (claim) => cacheGuestScanIfCurrentGuest(claim, "SNIPPET"),
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
            const res = await postJsonWithAuth("test-deepfake/", payload);
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data?.error || "Deepfake check failed");

            sendTabMessage(tabId, { type: "DISPLAY_DEEPFAKE_RESULT", data });
         } catch (err) {
            sendTabMessage(tabId, {
               type: "DISPLAY_SNIPPET_ERROR",
               message: err.message,
            });
         }
      })();
      return true;
   }

   if (request.type === "VERIFY_URL") {
      const { url, tabId } = request;

      (async () => {
         try {
            const res = await postJsonWithAuth("verify-url/", {
               url: url,
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
               throw new Error(data?.detail || "URL verification failed.");
            }

            // Add this inside VERIFY_URL and VERIFY_FILE in background.js
            if (data.cached && data.match) {
               cacheGuestScanIfCurrentGuest(data.match, "URL").catch(console.warn);

               // IMPORTANT: Make sure your content.js is listening for these specific message types!
               sendTabMessage(tabId, {
                  type: "DISPLAY_URL_CACHED_RESULT",
                  data: data.match,
               });
               return;
            }

            startPollingClaim({
               claimId: data.claim_id,
               tabId,
               successType: "DISPLAY_URL_RESULT",
               timeoutMessage: "DISPLAY_URL_ERROR",
               onResolved: (claim) => cacheGuestScanIfCurrentGuest(claim, "URL"),
               maxPolls: 50,
               pollEveryMs: 3000,
            });
         } catch (err) {
            console.error("URL verification failed:", err);

            sendTabMessage(tabId, {
               type: "DISPLAY_URL_ERROR",
               message: "Unable to verify this URL. Please try again.",
            });
         }
      })();

      return true;
   }

   if (request.type === "VERIFY_FILE") {
      const tabId = request.tabId ?? sender?.tab?.id; // <--- Grabs the tabId we passed from the popup
      const payload = request.payload;
      const endpoint = "verify-file/";

      sendResponse({ accepted: true, success: true });
      (async () => {
         // Also adding guest scan caching support so file scans save to the local library!
         try {
            const res = await postJsonWithAuth(endpoint, payload);
            const data = await res.json().catch(() => ({}));

            if (!res.ok) {
               throw new Error(data?.error || data?.detail || "File verification failed.");
            }

            // Add this inside VERIFY_URL and VERIFY_FILE in background.js
            if (data.cached && data.match) {
               cacheGuestScanIfCurrentGuest(data.match, "FILE").catch(console.warn);

               // IMPORTANT: Make sure your content.js is listening for these specific message types!
               sendTabMessage(tabId, {
                  type: "DISPLAY_SNIPPET_CACHED_RESULT",
                  data: data.match,
               });
               return;
            }

            // Start polling using the exact tabId
            startPollingClaim({
               claimId: data.claim_id,
               tabId: tabId,
               successType: "DISPLAY_SNIPPET_RESULT",
               timeoutMessage: "DISPLAY_SNIPPET_ERROR",
               onResolved: (claim) => cacheGuestScanIfCurrentGuest(claim, "FILE"),
               maxPolls: 40,
               pollEveryMs: 3000,
            });
         } catch (err) {
            console.error("File verification failed:", err);
            sendTabMessage(tabId, {
               type: "DISPLAY_SNIPPET_ERROR",
               message: err.message || "Failed to process document.",
            });
         }
      })();

      return true;
   }
});
