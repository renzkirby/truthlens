import { state } from "./state.js";

export const AUTH_STORAGE_KEYS = {
   ACCESS_TOKEN: "truthlens_access_token",
   REFRESH_TOKEN: "truthlens_refresh_token",
   PERSISTENCE: "truthlens_auth_persistence",
   SESSION_ID: "truthlens_auth_session_id",
   SESSION_STARTED_AT: "truthlens_auth_session_started_at",
   LAST_SYNC_ORIGIN: "truthlens_last_sync_origin",
   LAST_SYNC_AT: "truthlens_last_sync_at",
};

const SESSION_PERSISTENCE = "session";
const LOCAL_PERSISTENCE = "local";
const AUTH_STORAGE_KEY_LIST = Object.values(AUTH_STORAGE_KEYS);

let refreshInFlight = null;

const createIdentifier = () => {
   if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
   }

   return `truthlens-extension-${Date.now()}-${Math.random().toString(36).slice(2)}`;
};

const normalizePersistence = (value) =>
   value === LOCAL_PERSISTENCE ? LOCAL_PERSISTENCE : SESSION_PERSISTENCE;

const getSessionStorageArea = () => chrome.storage.session || null;

function storageGet(area, keys) {
   if (!area) {
      return Promise.resolve({});
   }

   return new Promise((resolve) => {
      area.get(keys, (result) => {
         resolve(result || {});
      });
   });
}

function storageSet(area, payload) {
   if (!area) {
      return Promise.resolve();
   }

   return new Promise((resolve) => {
      area.set(payload, () => resolve());
   });
}

function storageRemove(area, keys) {
   if (!area) {
      return Promise.resolve();
   }

   return new Promise((resolve) => {
      area.remove(keys, () => resolve());
   });
}

function hasAuthMaterial(stored) {
   return Boolean(
      stored?.[AUTH_STORAGE_KEYS.ACCESS_TOKEN] ||
      stored?.[AUTH_STORAGE_KEYS.REFRESH_TOKEN],
   );
}

function normalizeStoredSession(stored, fallbackPersistence) {
   const persistence = normalizePersistence(
      stored?.[AUTH_STORAGE_KEYS.PERSISTENCE] || fallbackPersistence,
   );

   return {
      accessToken: stored?.[AUTH_STORAGE_KEYS.ACCESS_TOKEN] || null,
      refreshToken: stored?.[AUTH_STORAGE_KEYS.REFRESH_TOKEN] || null,
      persistence,
      sessionId: stored?.[AUTH_STORAGE_KEYS.SESSION_ID] || null,
      sessionStartedAt: stored?.[AUTH_STORAGE_KEYS.SESSION_STARTED_AT] || null,
      lastSyncOrigin: stored?.[AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN] || null,
      lastSyncAt: stored?.[AUTH_STORAGE_KEYS.LAST_SYNC_AT] || null,
   };
}

function storageAreaForPersistence(persistence) {
   if (normalizePersistence(persistence) === LOCAL_PERSISTENCE) {
      return chrome.storage.local;
   }

   return getSessionStorageArea() || chrome.storage.local;
}

export function isTrustedWebOrigin(origin) {
   if (!origin || typeof origin !== "string") return false;
   return state.WEB_APP_ORIGINS.includes(origin);
}

export async function getAuthSession() {
   const sessionArea = getSessionStorageArea();
   const [localStored, sessionStored] = await Promise.all([
      storageGet(chrome.storage.local, AUTH_STORAGE_KEY_LIST),
      storageGet(sessionArea, AUTH_STORAGE_KEY_LIST),
   ]);

   if (hasAuthMaterial(localStored)) {
      return normalizeStoredSession(localStored, LOCAL_PERSISTENCE);
   }

   if (hasAuthMaterial(sessionStored)) {
      return normalizeStoredSession(sessionStored, SESSION_PERSISTENCE);
   }

   return {
      accessToken: null,
      refreshToken: null,
      persistence: null,
      sessionId: null,
      sessionStartedAt: null,
      lastSyncOrigin: null,
      lastSyncAt: null,
   };
}

export async function saveAuthSession({
   accessToken = null,
   refreshToken = null,
   origin = null,
}) {
   const current = await getAuthSession();
   const persistence = normalizePersistence(current.persistence);
   const area = storageAreaForPersistence(persistence);

   const updates = {
      [AUTH_STORAGE_KEYS.PERSISTENCE]: persistence,
      [AUTH_STORAGE_KEYS.LAST_SYNC_AT]: new Date().toISOString(),
   };

   if (origin || current.lastSyncOrigin) {
      updates[AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN] = origin || current.lastSyncOrigin;
   }

   if (accessToken) {
      updates[AUTH_STORAGE_KEYS.ACCESS_TOKEN] = accessToken;
   }

   if (refreshToken) {
      updates[AUTH_STORAGE_KEYS.REFRESH_TOKEN] = refreshToken;
   }

   if (current.sessionId) {
      updates[AUTH_STORAGE_KEYS.SESSION_ID] = current.sessionId;
   }

   if (current.sessionStartedAt) {
      updates[AUTH_STORAGE_KEYS.SESSION_STARTED_AT] = current.sessionStartedAt;
   }

   await storageSet(area, updates);
}

export async function replaceAuthSession({
   accessToken = null,
   refreshToken = null,
   origin = null,
   persistence = SESSION_PERSISTENCE,
   sessionId = null,
   sessionStartedAt = null,
   updatedAt = null,
}) {
   await clearAuthSession();

   if (!accessToken && !refreshToken) {
      return;
   }

   const normalizedPersistence = normalizePersistence(persistence);
   const area = storageAreaForPersistence(normalizedPersistence);
   const startedAt = Number(sessionStartedAt) || Date.now();

   await storageSet(area, {
      [AUTH_STORAGE_KEYS.ACCESS_TOKEN]: accessToken || null,
      [AUTH_STORAGE_KEYS.REFRESH_TOKEN]: refreshToken || null,
      [AUTH_STORAGE_KEYS.PERSISTENCE]: normalizedPersistence,
      [AUTH_STORAGE_KEYS.SESSION_ID]: sessionId || createIdentifier(),
      [AUTH_STORAGE_KEYS.SESSION_STARTED_AT]: startedAt,
      [AUTH_STORAGE_KEYS.LAST_SYNC_ORIGIN]: origin || null,
      [AUTH_STORAGE_KEYS.LAST_SYNC_AT]:
         Number(updatedAt) > 0
            ? new Date(Number(updatedAt)).toISOString()
            : new Date().toISOString(),
   });
}

export async function clearAuthSession() {
   await Promise.all([
      storageRemove(chrome.storage.local, AUTH_STORAGE_KEY_LIST),
      storageRemove(getSessionStorageArea(), AUTH_STORAGE_KEY_LIST),
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

async function performTokenRefresh(refreshToken, expectedSessionId) {
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
      const accessToken =
         typeof payload?.access === "string" && payload.access.trim()
            ? payload.access.trim()
            : null;

      if (response.status === 400 || response.status === 401) {
         const current = await getAuthSession();

         if (!expectedSessionId || current.sessionId === expectedSessionId) {
            await clearAuthSession();
         }

         return null;
      }

      if (!response.ok || !accessToken) {
         return null;
      }

      const current = await getAuthSession();

      if (
         expectedSessionId &&
         current.sessionId &&
         current.sessionId !== expectedSessionId
      ) {
         return current.accessToken || null;
      }

      if (current.refreshToken && current.refreshToken !== refreshToken) {
         return current.accessToken || null;
      }

      const rotatedRefreshToken =
         typeof payload?.refresh === "string" && payload.refresh.trim()
            ? payload.refresh.trim()
            : refreshToken;

      await saveAuthSession({
         accessToken,
         refreshToken: rotatedRefreshToken,
      });

      return accessToken;
   } catch {
      // Network/provider outages must not silently destroy an otherwise
      // recoverable browser identity. The next authenticated request can retry.
      return null;
   }
}

async function refreshAccessToken(failedAccessToken) {
   const currentSession = await getAuthSession();

   if (
      failedAccessToken &&
      currentSession.accessToken &&
      currentSession.accessToken !== failedAccessToken
   ) {
      return currentSession.accessToken;
   }

   if (!currentSession.refreshToken) {
      await clearAuthSession();
      return null;
   }

   if (!refreshInFlight) {
      refreshInFlight = performTokenRefresh(
         currentSession.refreshToken,
         currentSession.sessionId,
      ).finally(() => {
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
         const current = await getAuthSession();

         if (!session.sessionId || current.sessionId === session.sessionId) {
            await clearAuthSession();
         }
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
