import monaSansAssetPath from "@fontsource-variable/mona-sans/files/mona-sans-latin-wght-normal.woff2?url";

const TRUTHLENS_FONT_FAMILY = "Mona Sans Variable";
let fontLoadPromise = null;

function fontIsLoaded() {
   return Boolean(
      document.fonts?.check &&
      document.fonts.check(`13px "${TRUTHLENS_FONT_FAMILY}"`),
   );
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
      !document.fonts ||
      typeof chrome === "undefined" ||
      !chrome.runtime?.getURL
   ) {
      return Promise.resolve(false);
   }

   const fontUrl = chrome.runtime.getURL(monaSansAssetPath);

   fontLoadPromise = new FontFace(
      TRUTHLENS_FONT_FAMILY,
      `url("${fontUrl}") format("woff2")`,
      {
         style: "normal",
         weight: "200 900",
         stretch: "75% 125%",
      },
   )
      .load()
      .then((fontFace) => {
         document.fonts.add(fontFace);
         const loaded = fontIsLoaded();

         if (import.meta.env.DEV) {
            console.info("[TruthLens Local] Mona Sans loaded:", loaded);
         }

         return loaded;
      })
      .catch((error) => {
         if (import.meta.env.DEV) {
            console.warn("[TruthLens Local] Mona Sans failed to load", error);
         }
         return false;
      });

   return fontLoadPromise;
}
