import test from "node:test";
import assert from "node:assert/strict";

import { getAnalyzedClaimText } from "./claimText.js";

test("prefers the analyzed proposition over legacy context", () => {
   assert.equal(
      getAnalyzedClaimText({
         analyzed_claim: "  Concise proposition.  ",
         context_text: "Long source material.",
      }),
      "Concise proposition.",
   );
});

test("falls back to legacy context and then caller text", () => {
   assert.equal(
      getAnalyzedClaimText({ analyzed_claim: null, context_text: "  Legacy claim.  " }),
      "Legacy claim.",
   );
   assert.equal(getAnalyzedClaimText({ context_text: "  " }, " Discussion "), "Discussion");
   assert.equal(getAnalyzedClaimText(null), "");
});
