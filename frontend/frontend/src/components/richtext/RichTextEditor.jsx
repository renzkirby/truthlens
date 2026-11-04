import { useEffect, useMemo, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import RichTextToolbar from "./RichTextToolbar";
import { getRichTextProfile } from "./editorProfiles";
import {
   richTextEditorContent,
   richTextEnvelopeFromDoc,
   richTextToPlain,
   safeRichTextHref,
} from "./documentUtils";
import "./RichTextEditor.css";

export default function RichTextEditor({
   value,
   fallbackText = "",
   profile = "discussion",
   onChange,
   ariaLabel = "Rich text editor",
   placeholder = "",
   disabled = false,
   invalid = false,
   className = "",
}) {
   const rules = getRichTextProfile(profile);
   const [empty, setEmpty] = useState(() => !richTextToPlain(value, fallbackText));

   const extensions = useMemo(
      () => [
         StarterKit.configure({
            heading: rules.headings.length
               ? { levels: rules.headings }
               : false,
            orderedList: rules.orderedList ? {} : false,
            underline: rules.underline ? {} : false,
            strike: false,
            code: false,
            codeBlock: false,
            horizontalRule: false,
            link: {
               openOnClick: false,
               autolink: true,
               linkOnPaste: true,
               defaultProtocol: "https",
               isAllowedUri: (url) => Boolean(safeRichTextHref(url)),
               HTMLAttributes: {
                  rel: "noopener noreferrer nofollow",
                  target: "_blank",
               },
            },
         }),
      ],
      [rules.headings, rules.orderedList, rules.underline],
   );

   const editor = useEditor({
      extensions,
      content: richTextEditorContent(value, fallbackText),
      editable: !disabled,
      shouldRerenderOnTransaction: true,
      editorProps: {
         attributes: {
            "aria-label": ariaLabel,
            spellcheck: "true",
         },
      },
      onUpdate: ({ editor: instance }) => {
         const envelope = richTextEnvelopeFromDoc(instance.getJSON());
         setEmpty(instance.isEmpty);
         onChange?.(envelope, richTextToPlain(envelope));
      },
      onCreate: ({ editor: instance }) => setEmpty(instance.isEmpty),
   });

   useEffect(() => {
      if (!editor) return;
      editor.setEditable(!disabled);
   }, [disabled, editor]);

   useEffect(() => {
      if (!editor) return;
      const nextContent = richTextEditorContent(value, fallbackText);
      if (JSON.stringify(editor.getJSON()) === JSON.stringify(nextContent)) return;
      editor.commands.setContent(nextContent, { emitUpdate: false });
      setEmpty(editor.isEmpty);
   }, [editor, fallbackText, value]);

   const classes = [
      "tl-richtext-editor",
      rules.compact ? "tl-richtext-editor--compact" : "",
      invalid ? "tl-richtext-editor--invalid" : "",
      disabled ? "tl-richtext-editor--disabled" : "",
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <div className={classes} data-profile={profile}>
         {!disabled ? <RichTextToolbar editor={editor} profile={profile} /> : null}
         <div className="tl-richtext-editor__canvas">
            {empty && placeholder ? (
               <span className="tl-richtext-editor__placeholder" aria-hidden="true">
                  {placeholder}
               </span>
            ) : null}
            <EditorContent editor={editor} />
         </div>
      </div>
   );
}
