function fieldValue(line, separator) {
   if (separator === -1) return "";
   const value = line.slice(separator + 1);
   return value.startsWith(" ") ? value.slice(1) : value;
}

export function createSseParser({ onEvent, onComment } = {}) {
   let buffer = "";
   let eventName = "message";
   let dataLines = [];
   let firstLine = true;

   const dispatch = () => {
      if (dataLines.length) {
         onEvent?.({ event: eventName || "message", data: dataLines.join("\n") });
      }
      eventName = "message";
      dataLines = [];
   };

   const processLine = (rawLine) => {
      let line = rawLine;
      if (firstLine) {
         firstLine = false;
         if (line.startsWith("\uFEFF")) line = line.slice(1);
      }
      if (line === "") {
         dispatch();
         return;
      }
      if (line.startsWith(":")) {
         const comment = line.slice(1);
         onComment?.(comment.startsWith(" ") ? comment.slice(1) : comment);
         return;
      }

      const separator = line.indexOf(":");
      const field = separator === -1 ? line : line.slice(0, separator);
      const value = fieldValue(line, separator);
      if (field === "event") eventName = value;
      if (field === "data") dataLines.push(value);
   };

   const processBuffer = (final) => {
      let lineStart = 0;
      let index = 0;
      while (index < buffer.length) {
         const character = buffer[index];
         if (character === "\r") {
            if (!final && index === buffer.length - 1) break;
            processLine(buffer.slice(lineStart, index));
            if (buffer[index + 1] === "\n") index += 1;
            lineStart = index + 1;
         } else if (character === "\n") {
            processLine(buffer.slice(lineStart, index));
            lineStart = index + 1;
         }
         index += 1;
      }

      buffer = buffer.slice(lineStart);
      if (final && buffer) {
         processLine(buffer);
         buffer = "";
      }
   };

   return {
      push(chunk) {
         buffer += chunk;
         processBuffer(false);
      },
      finish() {
         processBuffer(true);
         eventName = "message";
         dataLines = [];
      },
   };
}

export async function consumeSseBody(body, { onConnected, onEvent } = {}) {
   const reader = body.getReader();
   const decoder = new TextDecoder();
   let connected = false;
   const markConnected = () => {
      if (!connected) {
         connected = true;
         onConnected?.();
      }
   };
   const parser = createSseParser({
      onComment: (comment) => {
         if (comment === "connected" || comment === "heartbeat") markConnected();
      },
      onEvent: (event) => {
         markConnected();
         onEvent?.(event);
      },
   });

   try {
      while (true) {
         const { value, done } = await reader.read();
         if (done) break;
         parser.push(decoder.decode(value, { stream: true }));
      }
      parser.push(decoder.decode());
      parser.finish();
   } finally {
      reader.releaseLock();
   }
}
