import { getAccessToken } from "./authStorage";
import { resolveApiEndpoint } from "./api";

function createSseParser(onEvent) {
   let buffer = "";

   return (chunk, final = false) => {
      buffer += chunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      if (final && buffer && !buffer.endsWith("\n\n")) buffer += "\n\n";
      const frames = buffer.split("\n\n");
      buffer = final ? "" : frames.pop();

      for (const frame of frames) {
         let event = "message";
         const data = [];
         for (const line of frame.split("\n")) {
            if (!line || line.startsWith(":")) continue;
            const separator = line.indexOf(":");
            const field = separator === -1 ? line : line.slice(0, separator);
            const value = separator === -1
               ? ""
               : line.slice(separator + 1).replace(/^ /, "");
            if (field === "event") event = value;
            if (field === "data") data.push(value);
         }
         if (data.length) onEvent({ event, data: data.join("\n") });
      }
   };
}

export async function consumeNotificationStream({ signal, onInboxChanged, onOpen }) {
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

   onOpen?.();
   const reader = response.body.getReader();
   const decoder = new TextDecoder();
   const parse = createSseParser(({ event }) => {
      if (event === "notification.inbox_changed") onInboxChanged?.();
   });

   try {
      while (true) {
         const { value, done } = await reader.read();
         if (done) break;
         parse(decoder.decode(value, { stream: true }));
      }
      parse(decoder.decode(), true);
   } finally {
      reader.releaseLock();
   }
}
