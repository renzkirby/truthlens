import assert from "node:assert/strict";
import test from "node:test";

import {
   VERDICT_PRESENTATIONS,
   getConfidenceLevel,
   getVerdictPresentation,
} from "./verdictPresentation.js";

test("defines all TruthLens verdict presentations", () => {
   assert.deepEqual(
      Object.keys(VERDICT_PRESENTATIONS),
      ["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED", "OUT_OF_SCOPE"],
   );
});

test("uses the approved redesign palette and definitions", () => {
   assert.equal(getVerdictPresentation("FACT").accent, "#10b981");
   assert.equal(getVerdictPresentation("FAKE").accent, "#ef4444");
   assert.equal(getVerdictPresentation("MISLEADING").accent, "#f97316");
   assert.equal(getVerdictPresentation("SATIRE").accent, "#8b5cf6");
   assert.equal(getVerdictPresentation("UNVERIFIED").accent, "#e0c85a");

   assert.match(
      getVerdictPresentation("MISLEADING").description,
      /context/i,
   );
   assert.match(
      getVerdictPresentation("SATIRE").description,
      /satire|parody/i,
   );
   assert.match(
      getVerdictPresentation("UNVERIFIED").description,
      /not enough/i,
   );
});

test("unknown verdicts fall back to unverified presentation", () => {
   assert.equal(
      getVerdictPresentation("UNKNOWN"),
      VERDICT_PRESENTATIONS.UNVERIFIED,
   );
});

test("confidence level labels are deterministic", () => {
   assert.equal(getConfidenceLevel(97), "High");
   assert.equal(getConfidenceLevel(80), "High");
   assert.equal(getConfidenceLevel(79), "Moderate");
   assert.equal(getConfidenceLevel(60), "Moderate");
   assert.equal(getConfidenceLevel(59), "Low");
   assert.equal(getConfidenceLevel(49), "Low");
   assert.equal(getConfidenceLevel(undefined), "Unavailable");
});
