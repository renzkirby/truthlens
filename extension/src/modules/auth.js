import { state } from "./state.js";

export const AUTH_STORAGE_KEYS = {
   ACCESS_TOKEN: "truthlens_access_token",
   REFRESH_TOKEN: "truthlens_refresh_token",
   LAST_SYNC_ORIGIN: "truthlens_last_sync_origin",
   LAST_SYNC_AT: "truthlens_last_sync_at",
};

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

export async function clearAuthSession() {
   await storageRemove([
      AUTH_STORAGE_KEYS.ACCESS_TOKEN,
      AUTH_STORAGE_KEYS.REFRESH_TOKEN,
      AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN,
      AUTH_STORAGE_KEYS.LAST_SYNC_AT,
   ]);
}

export async function buildAuthHeaders(baseHeaders = {}) {
   const session = await getAuthSession();
   if (!session.accessToken) {
      return { ...baseHeaders };
   }

   return {
      ...baseHeaders,
      Authorization: `Bearer ${session.accessToken}`,
   };
}
