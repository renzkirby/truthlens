import monaSansAssetPath from "@fontsource-variable/mona-sans/files/mona-sans-latin-wght-normal.woff2?url";

const TRUTHLENS_FONT_FAMILY = "Mona Sans Variable";
let fontLoadPromise = null;

function fontIsLoaded() {
   return Boolean(
      document.fonts?.check &&
      document.fonts.check(`13px "${TRUTHLENS_FONT_FAMILY}"`),
   );
}

function extensionAssetUrl(assetPath) {
   const normalizedPath = String(assetPath || "").replace(/^\/+/, "");
   return chrome.runtime.getURL(normalizedPath);
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

   const fontUrl = extensionAssetUrl(monaSansAssetPath);

   fontLoadPromise = fetch(fontUrl)
      .then((response) => {
         if (!response.ok) {
            throw new Error(
               `Font request failed with HTTP ${response.status} for ${fontUrl}`,
            );
         }

         return response.arrayBuffer();
      })
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
