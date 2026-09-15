function normalizeUserId(value) {
   if (typeof value === "string" && value.trim()) {
      return value.trim();
   }
   return typeof value === "number" && Number.isFinite(value) ? String(value) : null;
}

export function getAuthSessionIdentity(user, token) {
   if (token) {
      try {
         const encodedPayload = token.split(".")[1];
         const normalizedPayload = encodedPayload.replaceAll("-", "+").replaceAll("_", "/");
         const paddedPayload = normalizedPayload.padEnd(Math.ceil(normalizedPayload.length / 4) * 4, "=");
         const payload = JSON.parse(window.atob(paddedPayload));
         const userId = normalizeUserId(payload?.user_id) ?? normalizeUserId(payload?.sub);

         if (userId !== null) {
            return `user:${userId}`;
         }
      } catch {
         // Fall through to a non-secret authenticated-session marker.
      }
   }

   const userId = normalizeUserId(user?.id);
   if (userId !== null) {
      return `user:${userId}`;
   }

   return token ? "session:authenticated" : "session:anonymous";
}
