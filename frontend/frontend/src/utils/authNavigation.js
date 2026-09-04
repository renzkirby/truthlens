export function resolveAuthDestination(from, fallback = "/community") {
   if (!from) {
      return fallback;
   }

   const destination =
      typeof from === "string" ? from : from.pathname ? `${from.pathname}${from.search || ""}${from.hash || ""}` : "";

   // Authentication return destinations must
   // remain internal TruthLens routes.
   //
   // Reject protocol-relative URLs such as:
   // //malicious.example
   if (!destination.startsWith("/") || destination.startsWith("//")) {
      return fallback;
   }

   return destination;
}

export function createAuthReturnState(location) {
   if (!location?.pathname) {
      return undefined;
   }

   return {
      from: {
         pathname: location.pathname,
         search: location.search || "",
         hash: location.hash || "",
      },
   };
}
