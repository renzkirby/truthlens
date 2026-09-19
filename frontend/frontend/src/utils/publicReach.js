import { resolveApiEndpoint } from "./api";

// One random identifier per interaction, held only in the page instance.
// If secure randomness is unavailable, skip telemetry rather than invent an ID.
export function createPublicReachEventId() {
   try {
      if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
      const bytes = new Uint8Array(16);
      globalThis.crypto.getRandomValues(bytes);
      bytes[6] = (bytes[6] & 0x0f) | 0x40;
      bytes[8] = (bytes[8] & 0x3f) | 0x80;
      const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
   } catch {
      return null;
   }
}

export async function recordPublicReach({ clientEventId, eventType, sourceSurface, organizationSlug, publicationId = null }) {
   if (!clientEventId) return;
   try {
      await fetch(resolveApiEndpoint("PUBLIC_REACH_EVENTS"), {
         method: "POST",
         credentials: "omit",
         referrerPolicy: "no-referrer",
         keepalive: true,
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({
            client_event_id: clientEventId,
            event_type: eventType,
            source_surface: sourceSurface,
            organization_slug: organizationSlug,
            publication_id: publicationId,
         }),
      });
   } catch {
      // Best effort only: never touch page, routing, or authentication state.
   }
}
