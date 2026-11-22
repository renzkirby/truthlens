import { useEffect, useRef, useState } from "react";
import {
   Bold,
   Heading2,
   Heading3,
   Italic,
   Link,
   List,
   ListOrdered,
   Quote,
   Redo2,
   Underline,
   Undo2,
   Unlink,
} from "lucide-react";
import { getRichTextProfile } from "./editorProfiles";
import { safeRichTextHref } from "./documentUtils";

function ToolbarButton({
   label,
   active = false,
   disabled = false,
   onClick,
   children,
}) {
   return (
      <button
         type="button"
         className={`tl-richtext-toolbar__button${active ? " is-active" : ""}`}
         aria-label={label}
         aria-pressed={active ? "true" : undefined}
         title={label}
         disabled={disabled}
         onMouseDown={(event) => event.preventDefault()}
         onClick={onClick}
      >
         {children}
      </button>
   );
}

export default function RichTextToolbar({ editor, profile = "discussion" }) {
   const [linkDialogOpen, setLinkDialogOpen] = useState(false);
   const [linkValue, setLinkValue] = useState("");
   const [linkError, setLinkError] = useState("");
   const linkInputRef = useRef(null);

   const rules = getRichTextProfile(profile);
   const linkActive = Boolean(editor?.isActive("link"));

   useEffect(() => {
      if (!linkDialogOpen) return undefined;

      const frame = window.requestAnimationFrame(() => {
         linkInputRef.current?.focus();
         linkInputRef.current?.select();
      });

      const handleEscape = (event) => {
         if (event.key !== "Escape") return;
         setLinkDialogOpen(false);
         setLinkError("");
         editor?.commands.focus();
      };

      document.addEventListener("keydown", handleEscape);
      return () => {
         window.cancelAnimationFrame(frame);
         document.removeEventListener("keydown", handleEscape);
      };
   }, [editor, linkDialogOpen]);

   if (!editor) return null;

   const openLinkDialog = () => {
      setLinkValue(editor.getAttributes("link")?.href || "");
      setLinkError("");
      setLinkDialogOpen(true);
   };

   const closeLinkDialog = () => {
      setLinkDialogOpen(false);
      setLinkError("");
      editor.commands.focus();
   };

   const applyLink = (event) => {
      event.preventDefault();
      const href = safeRichTextHref(linkValue.trim());

      if (!href) {
         setLinkError("Enter a complete http:// or https:// link.");
         return;
      }

      editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
      setLinkDialogOpen(false);
      setLinkError("");
   };

   return (
      <div className="tl-richtext-toolbar" role="toolbar" aria-label="Text formatting">
         {rules.headings.includes(2) && (
            <ToolbarButton
               label="Heading 2"
               active={editor.isActive("heading", { level: 2 })}
               onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
            >
               <Heading2 size={17} strokeWidth={2} />
            </ToolbarButton>
         )}
         {rules.headings.includes(3) && (
            <ToolbarButton
               label="Heading 3"
               active={editor.isActive("heading", { level: 3 })}
               onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
            >
               <Heading3 size={17} strokeWidth={2} />
            </ToolbarButton>
         )}

         <ToolbarButton
            label="Bold"
            active={editor.isActive("bold")}
            onClick={() => editor.chain().focus().toggleBold().run()}
         >
            <Bold size={17} strokeWidth={2.2} />
         </ToolbarButton>
         <ToolbarButton
            label="Italic"
            active={editor.isActive("italic")}
            onClick={() => editor.chain().focus().toggleItalic().run()}
         >
            <Italic size={17} strokeWidth={2.1} />
         </ToolbarButton>
         {rules.underline && (
            <ToolbarButton
               label="Underline"
               active={editor.isActive("underline")}
               onClick={() => editor.chain().focus().toggleUnderline().run()}
            >
               <Underline size={17} strokeWidth={2} />
            </ToolbarButton>
         )}

         <span className="tl-richtext-toolbar__separator" aria-hidden="true" />

         <ToolbarButton
            label="Bulleted list"
            active={editor.isActive("bulletList")}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
         >
            <List size={18} strokeWidth={2} />
         </ToolbarButton>
         {rules.orderedList && (
            <ToolbarButton
               label="Numbered list"
               active={editor.isActive("orderedList")}
               onClick={() => editor.chain().focus().toggleOrderedList().run()}
            >
               <ListOrdered size={18} strokeWidth={2} />
            </ToolbarButton>
         )}
         <ToolbarButton
            label="Block quote"
            active={editor.isActive("blockquote")}
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
         >
            <Quote size={17} strokeWidth={2} />
         </ToolbarButton>

         <span className="tl-richtext-toolbar__separator" aria-hidden="true" />

         <ToolbarButton
            label="Add or edit link"
            active={linkActive}
            onClick={openLinkDialog}
         >
            <Link size={17} strokeWidth={2} />
         </ToolbarButton>
         <ToolbarButton
            label="Remove link"
            disabled={!linkActive}
            onClick={() => editor.chain().focus().extendMarkRange("link").unsetLink().run()}
         >
            <Unlink size={17} strokeWidth={2} />
         </ToolbarButton>

         {rules.undoRedo && (
            <>
               <span className="tl-richtext-toolbar__separator" aria-hidden="true" />
               <ToolbarButton
                  label="Undo"
                  disabled={!editor.can().chain().focus().undo().run()}
                  onClick={() => editor.chain().focus().undo().run()}
               >
                  <Undo2 size={17} strokeWidth={2} />
               </ToolbarButton>
               <ToolbarButton
                  label="Redo"
                  disabled={!editor.can().chain().focus().redo().run()}
                  onClick={() => editor.chain().focus().redo().run()}
               >
                  <Redo2 size={17} strokeWidth={2} />
               </ToolbarButton>
            </>
         )}

         {linkDialogOpen ? (
            <div
               className="tl-richtext-link-popover"
               role="dialog"
               aria-modal="false"
               aria-labelledby="tl-richtext-link-title"
            >
               <form onSubmit={applyLink}>
                  <div className="tl-richtext-link-popover__heading">
                     <strong id="tl-richtext-link-title">{linkActive ? "Edit link" : "Add link"}</strong>
                     <span>Use a complete http:// or https:// address.</span>
                  </div>
                  <label className="tl-richtext-link-popover__field">
                     <span>URL</span>
                     <input
                        ref={linkInputRef}
                        type="url"
                        inputMode="url"
                        autoComplete="url"
                        value={linkValue}
                        onChange={(event) => {
                           setLinkValue(event.target.value);
                           if (linkError) setLinkError("");
                        }}
                        aria-invalid={linkError ? "true" : undefined}
                        aria-describedby={linkError ? "tl-richtext-link-error" : undefined}
                        placeholder="https://example.com"
                     />
                  </label>
                  {linkError ? (
                     <p id="tl-richtext-link-error" className="tl-richtext-link-popover__error" role="alert">
                        {linkError}
                     </p>
                  ) : null}
                  <div className="tl-richtext-link-popover__actions">
                     <button type="button" className="tl-richtext-link-popover__cancel" onClick={closeLinkDialog}>
                        Cancel
                     </button>
                     <button type="submit" className="tl-richtext-link-popover__apply">
                        {linkActive ? "Update link" : "Add link"}
                     </button>
                  </div>
               </form>
            </div>
         ) : null}
      </div>
   );
}
