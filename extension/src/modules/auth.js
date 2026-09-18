import { state } from "./state.js";

export const AUTH_STORAGE_KEYS = {
   ACCESS_TOKEN: "truthlens_access_token",
   REFRESH_TOKEN: "truthlens_refresh_token",
   LAST_SYNC_ORIGIN: "truthlens_last_sync_origin",
   LAST_SYNC_AT: "truthlens_last_sync_at",
};

let refreshInFlight = null;

function storageGet(keys) {
   return new Promise((resolve) => {
      chrome.storage.local.get(keys, (result) => {
         resolve(result || {});
      });
   });
}

function storageSet(payload) {
   return new Promise((resolve) => {
      chrome.storage.local.set(payload, () => resolve());
   });
}

function storageRemove(keys) {
   return new Promise((resolve) => {
      chrome.storage.local.remove(keys, () => resolve());
   });
}

export function isTrustedWebOrigin(origin) {
   if (!origin || typeof origin !== "string") return false;
   return state.WEB_APP_ORIGINS.includes(origin);
}

export async function getAuthSession() {
   const stored = await storageGet([
      AUTH_STORAGE_KEYS.ACCESS_TOKEN,
      AUTH_STORAGE_KEYS.REFRESH_TOKEN,
      AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN,
      AUTH_STORAGE_KEYS.LAST_SYNC_AT,
   ]);

   return {
      accessToken: stored[AUTH_STORAGE_KEYS.ACCESS_TOKEN] || null,
      refreshToken: stored[AUTH_STORAGE_KEYS.REFRESH_TOKEN] || null,
      lastSyncOrigin: stored[AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN] || null,
      lastSyncAt: stored[AUTH_STORAGE_KEYS.LAST_SYNC_AT] || null,
   };
}

export async function saveAuthSession({ accessToken = null, refreshToken = null, origin = null }) {
   const updates = {
      [AUTH_STORAGE_KEYS.LAST_SYNC_AT]: new Date().toISOString(),
   };

   if (origin) {
      updates[AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN] = origin;
   }

   if (accessToken) {
      updates[AUTH_STORAGE_KEYS.ACCESS_TOKEN] = accessToken;
   }

   if (refreshToken) {
      updates[AUTH_STORAGE_KEYS.REFRESH_TOKEN] = refreshToken;
   }

   await storageSet(updates);
}

export async function replaceAuthSession({ accessToken = null, refreshToken = null, origin = null }) {
   await storageSet({
      [AUTH_STORAGE_KEYS.ACCESS_TOKEN]: accessToken || null,
      [AUTH_STORAGE_KEYS.REFRESH_TOKEN]: refreshToken || null,
      [AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN]: origin || null,
      [AUTH_STORAGE_KEYS.LAST_SYNC_AT]: new Date().toISOString(),
   });
}

export async function clearAuthSession() {
   await storageRemove([
      AUTH_STORAGE_KEYS.ACCESS_TOKEN,
      AUTH_STORAGE_KEYS.REFRESH_TOKEN,
      AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN,
      AUTH_STORAGE_KEYS.LAST_SYNC_AT,
   ]);
}

function headersWithAccessToken(baseHeaders, accessToken) {
   const headers = new Headers(baseHeaders || {});
   headers.delete("Authorization");

   if (accessToken) {
      headers.set("Authorization", `Bearer ${accessToken}`);
   }

   return headers;
}

async function performTokenRefresh(refreshToken) {
   try {
      const response = await fetch(`${state.API_BASE_URL}/token/refresh/`, {
         method: "POST",
         headers: {
            "content-type": "application/json",
         },
         body: JSON.stringify({
            refresh: refreshToken,
         }),
      });

      const payload = await response.json().catch(() => null);

      const accessToken = typeof payload?.access === "string" && payload.access.trim() ? payload.access.trim() : null;

      if (!response.ok || !accessToken) {
         await clearAuthSession();
         return null;
      }

      const rotatedRefreshToken =
         typeof payload?.refresh === "string" && payload.refresh.trim() ? payload.refresh.trim() : refreshToken;

      await saveAuthSession({
         accessToken,
         refreshToken: rotatedRefreshToken,
      });

      return accessToken;
   } catch {
      await clearAuthSession();
      return null;
   }
}

async function refreshAccessToken(failedAccessToken) {
   const currentSession = await getAuthSession();

   if (failedAccessToken && currentSession.accessToken && currentSession.accessToken !== failedAccessToken) {
      return currentSession.accessToken;
   }

   if (!currentSession.refreshToken) {
      await clearAuthSession();
      return null;
   }

   if (!refreshInFlight) {
      refreshInFlight = performTokenRefresh(currentSession.refreshToken).finally(() => {
         refreshInFlight = null;
      });
   }

   return refreshInFlight;
}

export async function authenticatedFetch(
   url,
   options = {},
   { allowGuestAfterAuthFailure = false, requireAuth = false } = {},
) {
   const baseHeaders = headersWithAccessToken(options.headers, null);
   const session = await getAuthSession();

   if (!session.accessToken) {
      if (requireAuth) {
         throw new Error("Authenticated extension session is required.");
      }

      return fetch(url, {
         ...options,
         headers: baseHeaders,
      });
   }

   const response = await fetch(url, {
      ...options,
      headers: headersWithAccessToken(baseHeaders, session.accessToken),
   });

   if (response.status !== 401) {
      return response;
   }

   const refreshedAccessToken = await refreshAccessToken(session.accessToken);

   if (refreshedAccessToken) {
      const retryResponse = await fetch(url, {
         ...options,
         headers: headersWithAccessToken(baseHeaders, refreshedAccessToken),
      });

      if (retryResponse.status === 401) {
         await clearAuthSession();
      }

      return retryResponse;
   }

   if (allowGuestAfterAuthFailure) {
      return fetch(url, {
         ...options,
         headers: baseHeaders,
      });
   }

   return response;
}
