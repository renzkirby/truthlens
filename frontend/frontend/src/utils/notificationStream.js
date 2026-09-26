import { getAccessToken } from "./authStorage";
import { resolveApiEndpoint } from "./api";
import { consumeSseBody } from "./notificationStreamCore";

export async function consumeNotificationStream({ signal, onInboxChanged, onConnected }) {
   const accessToken = getAccessToken();
   if (!accessToken) throw new Error("Authentication is required for notification streaming.");

   const response = await fetch(resolveApiEndpoint("NOTIFICATION_STREAM"), {
      method: "GET",
      headers: {
         Accept: "text/event-stream",
         Authorization: `Bearer ${accessToken}`,
      },
      cache: "no-store",
      signal,
   });
   if (!response.ok) {
      const error = new Error(`Notification stream failed with status ${response.status}.`);
      error.status = response.status;
      throw error;
   }
   if (!response.body) throw new Error("Notification stream response has no body.");

   await consumeSseBody(response.body, {
      onConnected,
      onEvent: ({ event }) => {
         if (event === "notification.inbox_changed") onInboxChanged?.();
      },
   });
}
