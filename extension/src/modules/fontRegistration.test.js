import assert from "node:assert/strict";
import test from "node:test";

import {
   TRUTHLENS_CONTENT_FONT_FAMILY,
   findLoadedTruthLensFontFace,
} from "./fontRegistration.js";

test("finds the loaded TruthLens content font face", () => {
   const expected = {
      family: TRUTHLENS_CONTENT_FONT_FAMILY,
      status: "loaded",
   };

   assert.equal(
      findLoadedTruthLensFontFace([
         { family: "Other Font", status: "loaded" },
         expected,
      ]),
      expected,
   );
});

test("accepts browser-normalized quoted family names", () => {
   const expected = {
      family: `"${TRUTHLENS_CONTENT_FONT_FAMILY}"`,
      status: "loaded",
   };

   assert.equal(findLoadedTruthLensFontFace([expected]), expected);
});

test("does not treat an unloaded matching face as ready", () => {
   assert.equal(
      findLoadedTruthLensFontFace([
         {
            family: TRUTHLENS_CONTENT_FONT_FAMILY,
            status: "loading",
         },
      ]),
      null,
   );
});

test("does not confuse the popup family with the injected UI family", () => {
   assert.equal(
      findLoadedTruthLensFontFace([
         {
            family: "Mona Sans Variable",
            status: "loaded",
         },
      ]),
      null,
   );
});

test("handles missing font-face collections safely", () => {
   assert.equal(findLoadedTruthLensFontFace(null), null);
});
