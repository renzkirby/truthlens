import test from "node:test";
import assert from "node:assert/strict";

import { evidenceSubmissionErrorMessage } from "./evidenceSubmissionError.js";

test("maps known-threat evidence URL errors to security copy", () => {
   assert.equal(
      evidenceSubmissionErrorMessage({
         status: 400,
         evidence_url: ["This evidence URL is flagged as unsafe and cannot be submitted."],
      }),
      "This source URL was flagged for a known security threat and cannot be submitted.",
   );
});

test("maps local/private URL policy errors to network-safety copy", () => {
   for (const message of [
      "Local URLs are not allowed.",
      "Private network URLs are not allowed.",
   ]) {
      assert.equal(
         evidenceSubmissionErrorMessage({ status: 400, evidence_url: [message] }),
         "Local or private-network URLs cannot be submitted as evidence.",
      );
   }
});

test("preserves other bounded evidence URL validation messages", () => {
   assert.equal(
      evidenceSubmissionErrorMessage({
         status: 400,
         evidence_url: ["Only http/https URLs are allowed."],
      }),
      "Only http/https URLs are allowed.",
   );
});

test("does not expose server-shaped errors", () => {
   assert.equal(
      evidenceSubmissionErrorMessage({
         status: 500,
         evidence_url: ["Traceback: internal server exception"],
      }),
      "We couldn't submit this evidence. Please review it and try again.",
   );
});
