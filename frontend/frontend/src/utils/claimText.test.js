import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { getAnalyzedClaimText, getOriginalMaterialText } from "./claimText.js";

test("prefers the analyzed proposition over legacy context", () => {
   assert.equal(
      getAnalyzedClaimText({
         claim_type: "URL",
         analyzed_claim: "  Concise proposition.  ",
         context_text: "Long source material.",
      }),
      "Concise proposition.",
   );
});

test("falls back only to legacy TEXT context", () => {
   assert.equal(
      getAnalyzedClaimText({ claim_type: "TEXT", analyzed_claim: null, context_text: "  Legacy claim.  " }),
      "Legacy claim.",
   );
   assert.equal(getAnalyzedClaimText({ context_text: "  " }), "");
   assert.equal(getAnalyzedClaimText(null), "");
});

test("legacy non-TEXT context is not presented as an analyzed claim", () => {
   const article = "Historical article paragraph. ".repeat(120);
   for (const claimType of ["URL", "FILE", "IMAGE", "VIDEO"]) {
      const claim = { claim_type: claimType, analyzed_claim: null, context_text: article };
      assert.equal(getAnalyzedClaimText(claim), "");
      assert.equal(getOriginalMaterialText(claim), article.trim());
   }
});

test("caption and AI summary are never substituted for the claim", () => {
   assert.equal(
      getAnalyzedClaimText({
         claim_type: "URL",
         analyzed_claim: null,
         context_text: "Historical article body.",
         caption: "Community discussion caption.",
         ai_summary: "Automated assessment summary.",
      }),
      "",
   );
});

test("original material prefers stored source context over legacy context", () => {
   assert.equal(
      getOriginalMaterialText({ source_context: "  Submitted source.  ", context_text: "Legacy text." }),
      "Submitted source.",
   );
});

test("UserHub uses a truthful unavailable state for historical URL claims", () => {
   const source = readFileSync(
      new URL("../Pages/UserHub.jsx", import.meta.url),
      "utf8",
   );

   assert.doesNotMatch(source, /No text extracted/);
   assert.match(
      source,
      /Analyzed claim is unavailable for this historical record\./,
   );
});
