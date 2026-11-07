export const TRUTHLENS_CONTENT_FONT_FAMILY = "TruthLens Mona Sans";

function normalizeFontFamilyName(value) {
   const family = String(value ?? "").trim();

   if (
      family.length >= 2 &&
      ((family.startsWith('"') && family.endsWith('"')) ||
         (family.startsWith("'") && family.endsWith("'")))
   ) {
      return family.slice(1, -1);
   }

   return family;
}

export function findLoadedTruthLensFontFace(fontFaces) {
   if (!fontFaces || typeof fontFaces[Symbol.iterator] !== "function") {
      return null;
   }

   for (const fontFace of fontFaces) {
      if (
         normalizeFontFamilyName(fontFace?.family) ===
            TRUTHLENS_CONTENT_FONT_FAMILY &&
         fontFace?.status === "loaded"
      ) {
         return fontFace;
      }
   }

   return null;
}
