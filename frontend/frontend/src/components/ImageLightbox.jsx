import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import Icons from "./Icons.jsx";
import "./ImageLightbox.css";

const FOCUSABLE_SELECTOR = [
   "a[href]",
   "button:not([disabled])",
   "input:not([disabled])",
   "select:not([disabled])",
   "textarea:not([disabled])",
   '[tabindex]:not([tabindex="-1"])',
].join(", ");

function ImageLightbox({
   open,
   src,
   alt = "",
   ariaLabel = "Image viewer",
   onClose,
   returnFocusRef,
   variant = "media",
}) {
   const dialogRef = useRef(null);
   const closeButtonRef = useRef(null);
   const onCloseRef = useRef(onClose);
   const [imageFailed, setImageFailed] = useState(false);

   useEffect(() => {
      onCloseRef.current = () => {
         setImageFailed(false);
         onClose();
      };
   }, [onClose]);

   useEffect(() => {
      if (!open) return undefined;

      const returnFocusTarget = returnFocusRef?.current || document.activeElement;
      const previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";

      const focusFrame = window.requestAnimationFrame(() => closeButtonRef.current?.focus());

      const handleKeyDown = (event) => {
         if (event.key === "Escape") {
            event.preventDefault();
            onCloseRef.current?.();
            return;
         }

         if (event.key !== "Tab") return;

         const dialog = dialogRef.current;
         const focusable = Array.from(dialog?.querySelectorAll(FOCUSABLE_SELECTOR) || []).filter(
            (element) => !element.hasAttribute("hidden"),
         );

         if (!focusable.length) {
            event.preventDefault();
            dialog?.focus();
            return;
         }

         const first = focusable[0];
         const last = focusable[focusable.length - 1];
         const focusIsOutside = !dialog?.contains(document.activeElement);

         if (event.shiftKey && (document.activeElement === first || focusIsOutside)) {
            event.preventDefault();
            last.focus();
         } else if (!event.shiftKey && (document.activeElement === last || focusIsOutside)) {
            event.preventDefault();
            first.focus();
         }
      };

      document.addEventListener("keydown", handleKeyDown);

      return () => {
         window.cancelAnimationFrame(focusFrame);
         document.removeEventListener("keydown", handleKeyDown);
         document.body.style.overflow = previousBodyOverflow;

         window.requestAnimationFrame(() => {
            if (returnFocusTarget?.isConnected) returnFocusTarget.focus();
         });
      };
   }, [open, returnFocusRef]);

   if (!open) return null;

   const closeFromBackdrop = (event) => {
      if (event.target === event.currentTarget) onCloseRef.current?.();
   };

   return createPortal(
      <div
         ref={dialogRef}
         className={`image-lightbox image-lightbox--${variant}`}
         role="dialog"
         aria-modal="true"
         aria-label={ariaLabel}
         tabIndex={-1}
         onClick={closeFromBackdrop}
      >
         <button
            ref={closeButtonRef}
            type="button"
            className="image-lightbox__close"
            aria-label="Close image viewer"
            onClick={() => onCloseRef.current?.()}
         >
            <span aria-hidden="true">
               <Icons name="x" size={24} />
            </span>
         </button>

         <div className="image-lightbox__stage" onClick={closeFromBackdrop}>
            {src && !imageFailed ? (
               <img
                  className="image-lightbox__image"
                  src={src}
                  alt={alt}
                  decoding="async"
                  onError={() => setImageFailed(true)}
               />
            ) : (
               <div className="image-lightbox__unavailable" role="status">
                  <span aria-hidden="true">
                     <Icons name="image" size={28} />
                  </span>
                  <p>This image could not be displayed.</p>
               </div>
            )}
         </div>
      </div>,
      document.body,
   );
}

export default ImageLightbox;
