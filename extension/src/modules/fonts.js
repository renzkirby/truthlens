import monaSansInlineUrl from "@fontsource-variable/mona-sans/files/mona-sans-latin-wght-normal.woff2?inline";

const TRUTHLENS_FONT_FAMILY = "Mona Sans Variable";
let fontLoadPromise = null;

function fontIsLoaded() {
   return Boolean(
      document.fonts?.check &&
      document.fonts.check(`13px "${TRUTHLENS_FONT_FAMILY}"`),
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
   if (fontIsLoaded()) {
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
            TRUTHLENS_FONT_FAMILY,
            fontBytes,
            {
               style: "normal",
               weight: "200 900",
            },
         ).load(),
      )
      .then((fontFace) => {
         document.fonts.add(fontFace);
         const loaded = fontIsLoaded();

         if (import.meta.env.DEV) {
            console.info("[TruthLens Local] Mona Sans loaded:", loaded);
         }

         if (!loaded) {
            fontLoadPromise = null;
         }

         return loaded;
      })
      .catch((error) => {
         fontLoadPromise = null;

         if (import.meta.env.DEV) {
            console.warn("[TruthLens Local] Mona Sans failed to load", error);
         }

         return false;
      });

   return fontLoadPromise;
}
