import { Fragment } from "react";
import { isRichTextEnvelope, safeRichTextHref } from "./documentUtils";
import "./RichTextEditor.css";

function renderMarkedText(node, key) {
   let content = node.text || "";
   const marks = Array.isArray(node.marks) ? node.marks : [];

   marks.forEach((mark, index) => {
      const markKey = `${key}-mark-${index}`;
      if (mark?.type === "bold") {
         content = <strong key={markKey}>{content}</strong>;
      } else if (mark?.type === "italic") {
         content = <em key={markKey}>{content}</em>;
      } else if (mark?.type === "underline") {
         content = <u key={markKey}>{content}</u>;
      } else if (mark?.type === "link") {
         const href = safeRichTextHref(mark?.attrs?.href);
         if (href) {
            content = (
               <a
                  key={markKey}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer nofollow"
               >
                  {content}
               </a>
            );
         }
      }
   });

   return <Fragment key={key}>{content}</Fragment>;
}

function renderNode(node, key) {
   if (!node || typeof node !== "object") return null;
   if (node.type === "text") return renderMarkedText(node, key);
   if (node.type === "hardBreak") return <br key={key} />;

   const children = (node.content || []).map((child, index) =>
      renderNode(child, `${key}-${index}`),
   );

   if (node.type === "paragraph") return <p key={key}>{children}</p>;
   if (node.type === "heading") {
      const level = node?.attrs?.level === 3 ? 3 : 2;
      return level === 3
         ? <h3 key={key}>{children}</h3>
         : <h2 key={key}>{children}</h2>;
   }
   if (node.type === "blockquote") return <blockquote key={key}>{children}</blockquote>;
   if (node.type === "bulletList") return <ul key={key}>{children}</ul>;
   if (node.type === "orderedList") {
      const start = Number(node?.attrs?.start) || 1;
      return <ol key={key} start={start}>{children}</ol>;
   }
   if (node.type === "listItem") return <li key={key}>{children}</li>;
   if (node.type === "doc") return <Fragment key={key}>{children}</Fragment>;
   return null;
}

function PlainFallback({ value }) {
   const text = String(value || "");
   if (!text.trim()) return null;
   return text
      .replace(/\r\n?/g, "\n")
      .split("\n\n")
      .map((paragraph, index) => (
         <p key={`plain-${index}`}>
            {paragraph.split("\n").map((line, lineIndex) => (
               <Fragment key={`plain-${index}-${lineIndex}`}>
                  {lineIndex > 0 ? <br /> : null}
                  {line}
               </Fragment>
            ))}
         </p>
      ));
}

export default function RichTextRenderer({
   value,
   fallbackText = "",
   profile = "discussion",
   className = "",
}) {
   const classes = [
      "tl-richtext-renderer",
      profile === "publication" ? "tl-richtext-renderer--publication" : "",
      profile === "comment" ? "tl-richtext-renderer--compact" : "",
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <div className={classes}>
         {isRichTextEnvelope(value)
            ? renderNode(value.doc, "rich-doc")
            : <PlainFallback value={fallbackText} />}
      </div>
   );
}
