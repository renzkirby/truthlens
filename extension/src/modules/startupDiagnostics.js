const STARTUP_LOG_PREFIX = "[TruthLens startup]";

export function diagnosticNowMs() {
   if (typeof performance !== "undefined" && typeof performance.now === "function") {
      return performance.now();
   }

   return Date.now();
}

export function diagnosticDurationMs(startedAt) {
   return Math.max(0, diagnosticNowMs() - startedAt);
}

export function logStartupTiming(event, details = {}) {
   const hasPerformance = typeof performance !== "undefined" && typeof performance.now === "function";
   const contextAgeMs = hasPerformance ? performance.now() : null;
   const timestampMs =
      hasPerformance && Number.isFinite(performance.timeOrigin)
         ? performance.timeOrigin + contextAgeMs
         : Date.now();

   const payload = {
      event,
      timestampMs: Math.round(timestampMs),
      contextAgeMs: contextAgeMs === null ? null : Number(contextAgeMs.toFixed(2)),
      ...details,
   };

   if (hasPerformance && typeof performance.mark === "function") {
      performance.mark(`truthlens:${event}`);
   }

   console.info(STARTUP_LOG_PREFIX, payload);
   return payload;
}
