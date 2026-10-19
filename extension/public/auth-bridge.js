(() => {
   const BRIDGE_SOURCE = "TRUTHLENS_WEB_AUTH_BRIDGE";
   const EXTENSION_SOURCE = "TRUTHLENS_EXTENSION";
   const AUTH_STORAGE_CHANGED_EVENT = "truthlens:auth-storage-changed";
   const SESSION_ID_KEY = "truthlens_auth_session_id";
   const SESSION_STARTED_AT_KEY = "truthlens_auth_session_started_at";
   const UPDATED_AT_KEY = "truthlens_auth_updated_at";

   if (window.__truthLensAuthBridgeLoaded) {
      return;
   }
   window.__truthLensAuthBridgeLoaded = true;

   const readFromStorage = (storage, persistence) => {
      const access = storage.getItem("access") || null;
      const refresh = storage.getItem("refresh") || null;

      if (!access && !refresh) {
         return null;
      }

      return {
         access,
         refresh,
         persistence,
         sessionId: storage.getItem(SESSION_ID_KEY) || null,
         sessionStartedAt: Number(storage.getItem(SESSION_STARTED_AT_KEY)) || null,
         updatedAt: Number(storage.getItem(UPDATED_AT_KEY)) || null,
      };
   };

   const readTokenSnapshot = () =>
      readFromStorage(window.localStorage, "local") ||
      readFromStorage(window.sessionStorage, "session") || {
         access: null,
         refresh: null,
         persistence: null,
         sessionId: null,
         sessionStartedAt: null,
         updatedAt: null,
      };

   const isSameSnapshot = (a, b) =>
      a?.access === b?.access &&
      a?.refresh === b?.refresh &&
      a?.persistence === b?.persistence &&
      a?.sessionId === b?.sessionId &&
      a?.sessionStartedAt === b?.sessionStartedAt &&
      a?.updatedAt === b?.updatedAt;

   let lastSnapshot = null;

   const publishSnapshot = (reason) => {
      const snapshot = readTokenSnapshot();
      if (isSameSnapshot(snapshot, lastSnapshot)) {
         return;
      }

      lastSnapshot = snapshot;
      window.postMessage(
         {
            source: BRIDGE_SOURCE,
            type: "TOKENS_UPDATED",
            payload: {
               ...snapshot,
               reason,
               origin: window.location.origin,
            },
         },
         window.location.origin,
      );
   };

   window.addEventListener("storage", (event) => {
      if (
         !event.key ||
         event.key === "access" ||
         event.key === "refresh" ||
         event.key === SESSION_ID_KEY ||
         event.key === SESSION_STARTED_AT_KEY ||
         event.key === UPDATED_AT_KEY
      ) {
         publishSnapshot("storage_event");
      }
   });

   window.addEventListener(AUTH_STORAGE_CHANGED_EVENT, () => {
      publishSnapshot("app_auth_change");
   });

   window.addEventListener("message", (event) => {
      if (event.source !== window) {
         return;
      }

      const data = event.data;
      if (!data || data.source !== EXTENSION_SOURCE) {
         return;
      }

      if (data.type === "REQUEST_TOKENS") {
         lastSnapshot = null;
         publishSnapshot("extension_request");
      }
   });

   publishSnapshot("init");
   window.setInterval(() => publishSnapshot("heartbeat"), 3000);
})();
