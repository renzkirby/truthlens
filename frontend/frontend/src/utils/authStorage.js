const AUTH_CHANNEL_NAME = "truthlens-auth-session-v1";
const AUTH_BRIDGE_EVENT_NAME = "truthlens:auth-storage-changed";
const AUTH_SESSION_ID_KEY = "truthlens_auth_session_id";
const AUTH_SESSION_STARTED_AT_KEY = "truthlens_auth_session_started_at";
const AUTH_UPDATED_AT_KEY = "truthlens_auth_updated_at";
const AUTH_REQUEST_TIMEOUT_MS = 180;

const createIdentifier = () => {
   if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
   }

   return `truthlens-${Date.now()}-${Math.random().toString(36).slice(2)}`;
};

const AUTH_TAB_ID = createIdentifier();
let authChannel = null;
const authChannelListeners = new Set();

const parseTimestamp = (value) => {
   const parsed = Number(value);
   return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
};

const decodeJwtPayload = (token) => {
   if (typeof token !== "string" || !token.includes(".") || typeof atob !== "function") {
      return null;
   }

   try {
      const encoded = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = encoded.padEnd(Math.ceil(encoded.length / 4) * 4, "=");
      return JSON.parse(atob(padded));
   } catch {
      return null;
   }
};

const tokenIssuedAt = (token) => {
   const payload = decodeJwtPayload(token);
   const issuedAtSeconds = Number(payload?.iat);
   return Number.isFinite(issuedAtSeconds) && issuedAtSeconds > 0 ? issuedAtSeconds * 1000 : 0;
};

const deriveLegacySessionId = (access, refresh) => {
   const payload = decodeJwtPayload(refresh) || decodeJwtPayload(access);
   const userId = payload?.user_id ?? payload?.sub ?? null;

   return userId !== null && userId !== undefined
      ? `legacy-user-${String(userId)}`
      : "legacy-browser-session";
};

const readStorageSnapshot = (storage, rememberMe) => {
   if (!storage) {
      return null;
   }

   const access = storage.getItem("access") || null;
   const refresh = storage.getItem("refresh") || null;

   if (!access && !refresh) {
      return null;
   }

   const tokenTimestamp = tokenIssuedAt(access) || tokenIssuedAt(refresh);
   const sessionStartedAt =
      parseTimestamp(storage.getItem(AUTH_SESSION_STARTED_AT_KEY)) ||
      tokenIssuedAt(refresh) ||
      tokenTimestamp;
   const updatedAt =
      parseTimestamp(storage.getItem(AUTH_UPDATED_AT_KEY)) ||
      tokenTimestamp ||
      sessionStartedAt;
   const sessionId =
      storage.getItem(AUTH_SESSION_ID_KEY) ||
      deriveLegacySessionId(access, refresh);

   return {
      access,
      refresh,
      rememberMe,
      sessionId,
      sessionStartedAt,
      updatedAt,
   };
};

const rawClearAuthTokens = () => {
   if (typeof localStorage !== "undefined") {
      localStorage.removeItem("access");
      localStorage.removeItem("refresh");
      localStorage.removeItem(AUTH_SESSION_ID_KEY);
      localStorage.removeItem(AUTH_SESSION_STARTED_AT_KEY);
      localStorage.removeItem(AUTH_UPDATED_AT_KEY);
   }

   if (typeof sessionStorage !== "undefined") {
      sessionStorage.removeItem("access");
      sessionStorage.removeItem("refresh");
      sessionStorage.removeItem(AUTH_SESSION_ID_KEY);
      sessionStorage.removeItem(AUTH_SESSION_STARTED_AT_KEY);
      sessionStorage.removeItem(AUTH_UPDATED_AT_KEY);
   }
};

const writeSnapshot = (storage, snapshot) => {
   if (!storage) {
      return;
   }

   if (snapshot.access) {
      storage.setItem("access", snapshot.access);
   }

   if (snapshot.refresh) {
      storage.setItem("refresh", snapshot.refresh);
   }

   if (snapshot.sessionId) {
      storage.setItem(AUTH_SESSION_ID_KEY, snapshot.sessionId);
   }

   if (snapshot.sessionStartedAt) {
      storage.setItem(AUTH_SESSION_STARTED_AT_KEY, String(snapshot.sessionStartedAt));
   }

   if (snapshot.updatedAt) {
      storage.setItem(AUTH_UPDATED_AT_KEY, String(snapshot.updatedAt));
   }
};

const notifyAuthBridge = () => {
   if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") {
      return;
   }

   try {
      window.dispatchEvent(new CustomEvent(AUTH_BRIDGE_EVENT_NAME));
   } catch {
      window.dispatchEvent(new Event(AUTH_BRIDGE_EVENT_NAME));
   }
};

const handleChannelMessage = (event) => {
   const message = event?.data;

   if (!message || message.senderTabId === AUTH_TAB_ID) {
      return;
   }

   if (message.type === "SESSION_REQUEST") {
      const snapshot = getAuthSnapshot();

      if (snapshot && authChannel) {
         authChannel.postMessage({
            type: "SESSION_RESPONSE",
            senderTabId: AUTH_TAB_ID,
            targetTabId: message.senderTabId,
            requestId: message.requestId,
            snapshot,
         });
      }
   }

   authChannelListeners.forEach((listener) => {
      listener(message);
   });
};

const ensureAuthChannel = () => {
   if (authChannel || typeof BroadcastChannel === "undefined") {
      return authChannel;
   }

   authChannel = new BroadcastChannel(AUTH_CHANNEL_NAME);
   authChannel.addEventListener("message", handleChannelMessage);
   return authChannel;
};

const publishMessage = (message) => {
   const channel = ensureAuthChannel();

   if (!channel) {
      return;
   }

   channel.postMessage({
      ...message,
      senderTabId: AUTH_TAB_ID,
   });
};

export const getAuthSnapshot = () => {
   const rememberedSnapshot =
      typeof localStorage !== "undefined"
         ? readStorageSnapshot(localStorage, true)
         : null;

   if (rememberedSnapshot) {
      return rememberedSnapshot;
   }

   return typeof sessionStorage !== "undefined"
      ? readStorageSnapshot(sessionStorage, false)
      : null;
};

export const getAccessToken = () => getAuthSnapshot()?.access || null;

export const getRefreshToken = () => getAuthSnapshot()?.refresh || null;

export const getAuthStorage = () => {
   const snapshot = getAuthSnapshot();

   if (snapshot?.rememberMe && typeof localStorage !== "undefined") {
      return localStorage;
   }

   return typeof sessionStorage !== "undefined" ? sessionStorage : null;
};

export const isSameAuthSnapshot = (left, right) =>
   Boolean(left) === Boolean(right) &&
   (!left ||
      (left.access === right.access &&
         left.refresh === right.refresh &&
         left.rememberMe === right.rememberMe &&
         left.sessionId === right.sessionId &&
         left.sessionStartedAt === right.sessionStartedAt &&
         left.updatedAt === right.updatedAt));

export const chooseFreshestAuthSnapshot = (...snapshots) =>
   snapshots.filter(Boolean).reduce((preferred, candidate) => {
      if (!preferred) {
         return candidate;
      }

      if (candidate.sessionId !== preferred.sessionId) {
         if (candidate.sessionStartedAt !== preferred.sessionStartedAt) {
            return candidate.sessionStartedAt > preferred.sessionStartedAt
               ? candidate
               : preferred;
         }
      }

      if (candidate.updatedAt !== preferred.updatedAt) {
         return candidate.updatedAt > preferred.updatedAt ? candidate : preferred;
      }

      return preferred;
   }, null);

export const shouldApplyAuthClear = (currentSnapshot, message) => {
   if (!currentSnapshot) {
      return true;
   }

   if (!message?.sessionId || message.sessionId === currentSnapshot.sessionId) {
      return true;
   }

   const clearedStartedAt = parseTimestamp(message.sessionStartedAt);
   return !clearedStartedAt || clearedStartedAt >= currentSnapshot.sessionStartedAt;
};

export const applyAuthSnapshot = (
   snapshot,
   { broadcast = false, reason = "sync" } = {},
) => {
   if (!snapshot?.access && !snapshot?.refresh) {
      clearAuthTokens({ broadcast, reason });
      return null;
   }

   const now = Date.now();
   const normalized = {
      access: snapshot.access || null,
      refresh: snapshot.refresh || null,
      rememberMe: snapshot.rememberMe === true,
      sessionId:
         snapshot.sessionId ||
         deriveLegacySessionId(snapshot.access, snapshot.refresh) ||
         createIdentifier(),
      sessionStartedAt:
         parseTimestamp(snapshot.sessionStartedAt) ||
         tokenIssuedAt(snapshot.refresh) ||
         tokenIssuedAt(snapshot.access) ||
         now,
      updatedAt:
         parseTimestamp(snapshot.updatedAt) ||
         tokenIssuedAt(snapshot.access) ||
         tokenIssuedAt(snapshot.refresh) ||
         now,
   };

   rawClearAuthTokens();

   const storage = normalized.rememberMe
      ? typeof localStorage !== "undefined"
         ? localStorage
         : null
      : typeof sessionStorage !== "undefined"
         ? sessionStorage
         : null;

   writeSnapshot(storage, normalized);
   notifyAuthBridge();

   if (broadcast) {
      publishMessage({
         type: "SESSION_UPDATED",
         reason,
         snapshot: normalized,
      });
   }

   return normalized;
};

export const storeAuthTokens = (
   access,
   refresh,
   rememberMe = false,
   { broadcast = true, reason = "login" } = {},
) => {
   const now = Date.now();

   return applyAuthSnapshot(
      {
         access: access || null,
         refresh: refresh || null,
         rememberMe: rememberMe === true,
         sessionId: createIdentifier(),
         sessionStartedAt: now,
         updatedAt: now,
      },
      { broadcast, reason },
   );
};

export const updateAuthTokens = (
   access,
   refresh,
   { broadcast = true, reason = "refresh" } = {},
) => {
   const current = getAuthSnapshot();
   const now = Date.now();

   return applyAuthSnapshot(
      {
         access: access || current?.access || null,
         refresh: refresh || current?.refresh || null,
         rememberMe: current?.rememberMe === true,
         sessionId: current?.sessionId || createIdentifier(),
         sessionStartedAt: current?.sessionStartedAt || now,
         updatedAt: now,
      },
      { broadcast, reason },
   );
};

export const clearAuthTokens = (
   { broadcast = true, reason = "logout" } = {},
) => {
   const previousSnapshot = getAuthSnapshot();

   rawClearAuthTokens();
   notifyAuthBridge();

   if (broadcast) {
      publishMessage({
         type: "SESSION_CLEARED",
         reason,
         sessionId: previousSnapshot?.sessionId || null,
         sessionStartedAt: previousSnapshot?.sessionStartedAt || 0,
         endedAt: Date.now(),
      });
   }
};

export const subscribeToAuthSessionSync = (listener) => {
   if (typeof listener !== "function") {
      return () => {};
   }

   const channel = ensureAuthChannel();

   if (!channel) {
      return () => {};
   }

   authChannelListeners.add(listener);

   return () => {
      authChannelListeners.delete(listener);
   };
};

export const requestSharedAuthSession = (timeoutMs = AUTH_REQUEST_TIMEOUT_MS) => {
   const channel = ensureAuthChannel();

   if (!channel) {
      return Promise.resolve(null);
   }

   const requestId = createIdentifier();
   const responses = [];

   return new Promise((resolve) => {
      const listener = (message) => {
         if (
            message?.type !== "SESSION_RESPONSE" ||
            message.targetTabId !== AUTH_TAB_ID ||
            message.requestId !== requestId ||
            !message.snapshot
         ) {
            return;
         }

         responses.push(message.snapshot);
      };

      authChannelListeners.add(listener);

      channel.postMessage({
         type: "SESSION_REQUEST",
         senderTabId: AUTH_TAB_ID,
         requestId,
      });

      window.setTimeout(() => {
         authChannelListeners.delete(listener);
         resolve(chooseFreshestAuthSnapshot(...responses));
      }, timeoutMs);
   });
};

export const publishCurrentAuthSession = (reason = "sync") => {
   const snapshot = getAuthSnapshot();

   if (!snapshot) {
      return;
   }

   publishMessage({
      type: "SESSION_UPDATED",
      reason,
      snapshot,
   });
};
