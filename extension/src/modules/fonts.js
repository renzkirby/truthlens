import monaSansInlineUrl from "@fontsource-variable/mona-sans/files/mona-sans-latin-wght-normal.woff2?inline";
import {
   TRUTHLENS_CONTENT_FONT_FAMILY,
   findLoadedTruthLensFontFace,
} from "./fontRegistration.js";

let fontLoadPromise = null;

function fontIsRegistered() {
   return Boolean(
      document.fonts &&
         findLoadedTruthLensFontFace(document.fonts),
   );
}

async function inlineFontBytes() {
   const response = await fetch(monaSansInlineUrl);
   if (!response.ok) {
      throw new Error(
         `Inline Mona Sans data could not be read (HTTP ${response.status}).`,
      );
   }

   return response.arrayBuffer();
}

export function loadTruthLensFont() {
   if (fontIsRegistered()) {
      return Promise.resolve(true);
   }

   if (fontLoadPromise) {
      return fontLoadPromise;
   }

   if (
      typeof FontFace !== "function" ||
      !document.fonts
   ) {
      return Promise.resolve(false);
   }

   fontLoadPromise = inlineFontBytes()
      .then((fontBytes) =>
         new FontFace(
            TRUTHLENS_CONTENT_FONT_FAMILY,
            fontBytes,
            {
               style: "normal",
               weight: "200 900",
            },
         ).load(),
      )
      .then((fontFace) => {
         document.fonts.add(fontFace);

         const registered =
            fontFace.status === "loaded" &&
            (typeof document.fonts.has === "function"
               ? document.fonts.has(fontFace)
               : fontIsRegistered());

         if (import.meta.env.DEV) {
            console.info("[TruthLens Local] Mona Sans registered:", registered, {
               family: TRUTHLENS_CONTENT_FONT_FAMILY,
               status: fontFace.status,
            });
         }

         if (!registered) {
            fontLoadPromise = null;
         }

         return registered;
      })
      .catch((error) => {
         fontLoadPromise = null;

         if (import.meta.env.DEV) {
            console.warn("[TruthLens Local] Mona Sans failed to register", error);
         }

         return false;
      });

   return fontLoadPromise;
}
