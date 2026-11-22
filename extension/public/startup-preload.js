(function () {
   const now = typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : 0;
   const timeOrigin =
      typeof performance !== "undefined" && Number.isFinite(performance.timeOrigin)
         ? performance.timeOrigin
         : Date.now() - now;

   window.__truthlensPopupBootstrap = {
      contextAgeMs: now,
      timestampMs: Math.round(timeOrigin + now),
   };

   console.info("[TruthLens startup]", {
      event: "popup_html_bootstrap",
      context: "popup",
      contextAgeMs: Number(now.toFixed(2)),
      timestampMs: Math.round(timeOrigin + now),
      readyState: document.readyState,
   });
})();
