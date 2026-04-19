(() => {
   const BRIDGE_SOURCE = "TRUTHLENS_WEB_AUTH_BRIDGE";
   const EXTENSION_SOURCE = "TRUTHLENS_EXTENSION";

   if (window.__truthLensAuthBridgeLoaded) {
      return;
   }
   window.__truthLensAuthBridgeLoaded = true;

   const readTokenSnapshot = () => ({
      access: window.localStorage.getItem("access") || null,
      refresh: window.localStorage.getItem("refresh") || null,
   });

   const isSameSnapshot = (a, b) => a?.access === b?.access && a?.refresh === b?.refresh;

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
      if (!event.key || event.key === "access" || event.key === "refresh") {
         publishSnapshot("storage_event");
      }
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
