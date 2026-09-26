import test from "node:test";
import assert from "node:assert/strict";

import { consumeSseBody, createSseParser } from "./notificationStreamCore.js";

function parseChunks(chunks) {
   const events = [];
   const comments = [];
   const parser = createSseParser({
      onEvent: (event) => events.push(event),
      onComment: (comment) => comments.push(comment),
   });
   for (const chunk of chunks) parser.push(chunk);
   parser.finish();
   return { comments, events };
}

test("parses a CRLF event at every possible text chunk boundary", () => {
   const frame = "event: notification.inbox_changed\r\ndata: {}\r\n\r\n";
   for (let split = 0; split <= frame.length; split += 1) {
      assert.deepEqual(
         parseChunks([frame.slice(0, split), frame.slice(split)]).events,
         [{ event: "notification.inbox_changed", data: "{}" }],
         `split ${split}`,
      );
   }
});

test("handles CR, LF, partial fields, multiline data, and multiple events", () => {
   const frame = [
      ": connected\r",
      "event: first\r",
      "data: line one\r",
      "data: line two\r\r",
      "event: second\n",
      "data: done\n\n",
   ].join("");
   const chunks = Array.from(frame);
   assert.deepEqual(parseChunks(chunks), {
      comments: ["connected"],
      events: [
         { event: "first", data: "line one\nline two" },
         { event: "second", data: "done" },
      ],
   });
});

test("streaming decoding preserves split UTF-8 and confirms a connected frame", async () => {
   const bytes = new TextEncoder().encode(
      ": connected\r\nevent: notification.inbox_changed\r\ndata: café 🔎\r\n\r\n",
   );
   const body = new ReadableStream({
      start(controller) {
         for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
         controller.close();
      },
   });
   const events = [];
   let connected = 0;
   await consumeSseBody(body, {
      onConnected: () => { connected += 1; },
      onEvent: (event) => events.push(event),
   });
   assert.equal(connected, 1);
   assert.deepEqual(events, [{
      event: "notification.inbox_changed",
      data: "café 🔎",
   }]);
});

test("body failures before the connected frame do not report a healthy stream", async () => {
   let connected = 0;
   for (let attempt = 0; attempt < 3; attempt += 1) {
      const body = new ReadableStream({
         start(controller) {
            controller.error(new Error("subscription failed"));
         },
      });
      await assert.rejects(
         consumeSseBody(body, { onConnected: () => { connected += 1; } }),
         /subscription failed/,
      );
   }
   assert.equal(connected, 0);
});
