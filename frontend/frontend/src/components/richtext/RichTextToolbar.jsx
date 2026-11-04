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
   if (!editor) return null;
   const rules = getRichTextProfile(profile);

   const setLink = () => {
      const previous = editor.getAttributes("link")?.href || "";
      const entered = window.prompt("Paste a link (https://…)", previous);
      if (entered === null) return;
      if (!entered.trim()) {
         editor.chain().focus().extendMarkRange("link").unsetLink().run();
         return;
      }
      const href = safeRichTextHref(entered.trim());
      if (!href) {
         window.alert("Use a complete http:// or https:// link.");
         return;
      }
      editor.chain().focus().extendMarkRange("link").setLink({ href }).run();
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
            active={editor.isActive("link")}
            onClick={setLink}
         >
            <Link size={17} strokeWidth={2} />
         </ToolbarButton>
         <ToolbarButton
            label="Remove link"
            disabled={!editor.isActive("link")}
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
      </div>
   );
}
