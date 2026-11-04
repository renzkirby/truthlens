export const RICH_TEXT_SCHEMA_VERSION = 1;

export function emptyRichTextDocument() {
   return {
      schema_version: RICH_TEXT_SCHEMA_VERSION,
      doc: {
         type: "doc",
         content: [{ type: "paragraph" }],
      },
   };
}

function textNode(value) {
   return value ? { type: "text", text: value } : null;
}

export function plainTextToRichText(value) {
   const source = String(value || "").replace(/\r\n?/g, "\n");
   const paragraphs = source.split("\n\n").map((paragraph) => {
      const content = [];
      paragraph.split("\n").forEach((line, index) => {
         if (index > 0) content.push({ type: "hardBreak" });
         const node = textNode(line);
         if (node) content.push(node);
      });
      return content.length > 0
         ? { type: "paragraph", content }
         : { type: "paragraph" };
   });

   return {
      schema_version: RICH_TEXT_SCHEMA_VERSION,
      doc: {
         type: "doc",
         content: paragraphs.length > 0 ? paragraphs : [{ type: "paragraph" }],
      },
   };
}

export function isRichTextEnvelope(value) {
   return Boolean(
      value
      && typeof value === "object"
      && value.schema_version === RICH_TEXT_SCHEMA_VERSION
      && value.doc
      && value.doc.type === "doc",
   );
}

export function richTextEditorContent(value, fallbackText = "") {
   if (isRichTextEnvelope(value)) return value.doc;
   return plainTextToRichText(fallbackText).doc;
}

export function richTextEnvelopeFromDoc(doc) {
   return {
      schema_version: RICH_TEXT_SCHEMA_VERSION,
      doc: doc && doc.type === "doc" ? doc : emptyRichTextDocument().doc,
   };
}

function inlinePlain(node) {
   return (node?.content || [])
      .map((child) => {
         if (child?.type === "text") return child.text || "";
         if (child?.type === "hardBreak") return "\n";
         return "";
      })
      .join("");
}

function listItemPlain(node, ordered, number) {
   const lines = [];
   (node?.content || []).forEach((child, index) => {
      if (child?.type === "paragraph") {
         const prefix = index === 0 ? (ordered ? `${number}. ` : "- ") : "";
         lines.push(`${prefix}${inlinePlain(child)}`);
      } else if (child?.type === "bulletList" || child?.type === "orderedList") {
         blockPlain(child)
            .split("\n")
            .filter(Boolean)
            .forEach((line) => lines.push(`  ${line}`));
      }
   });
   return lines.filter((line) => line.trim()).join("\n");
}

function blockPlain(node) {
   if (!node) return "";
   if (node.type === "paragraph" || node.type === "heading") return inlinePlain(node);
   if (node.type === "blockquote") {
      return (node.content || [])
         .map(blockPlain)
         .flatMap((value) => value.split("\n"))
         .filter((line) => line.trim())
         .map((line) => `> ${line}`)
         .join("\n");
   }
   if (node.type === "bulletList" || node.type === "orderedList") {
      const ordered = node.type === "orderedList";
      const start = Number(node?.attrs?.start) || 1;
      return (node.content || [])
         .map((item, index) => listItemPlain(item, ordered, start + index))
         .filter(Boolean)
         .join("\n");
   }
   if (node.type === "text") return node.text || "";
   if (node.type === "hardBreak") return "\n";
   return "";
}

export function richTextToPlain(value, fallbackText = "") {
   if (!isRichTextEnvelope(value)) return String(fallbackText || "").trim();
   return (value.doc.content || [])
      .map(blockPlain)
      .map((block) => block.trim())
      .filter(Boolean)
      .join("\n\n")
      .trim();
}

export function richTextHasContent(value, fallbackText = "") {
   return Boolean(richTextToPlain(value, fallbackText));
}

export function safeRichTextHref(value) {
   if (typeof value !== "string") return null;
   try {
      const parsed = new URL(value);
      if (!["http:", "https:"].includes(parsed.protocol)) return null;
      return parsed.href;
   } catch {
      return null;
   }
}
