import assert from "node:assert/strict";
import test from "node:test";

import { classifyExtensionError, extensionErrorPresentation } from "./userFacingError.js";

test("classifies verification transport failures", () => {
   assert.equal(classifyExtensionError({ status: 401 }), "auth");
   assert.equal(classifyExtensionError({ status: 403 }), "permission");
   assert.equal(classifyExtensionError({ status: 404 }), "not_found");
   assert.equal(classifyExtensionError({ status: 409 }), "conflict");
   assert.equal(classifyExtensionError({ status: 429 }), "rate_limit");
   assert.equal(classifyExtensionError({ status: 503 }), "service");
});

test("null status still allows network classification", () => {
   assert.equal(
      classifyExtensionError({ status: null, error: { message: "Failed to fetch" } }),
      "network",
   );
});

test("known URL threat maps to security alert", () => {
   const result = extensionErrorPresentation({
      status: 400,
      payload: {
         detail: "This URL was flagged for a known security threat and cannot be analyzed.",
         url_safety: { status: "UNSAFE" },
      },
   });
   assert.equal(result.kind, "security_threat");
   assert.match(result.message, /known security threat/i);
});

test("does not expose server diagnostics", () => {
   const result = extensionErrorPresentation({
      status: 500,
      payload: { detail: "IntegrityError: duplicate key value" },
   });
   assert.equal(result.kind, "service");
   assert.equal(result.message, "TruthLens analysis is temporarily unavailable. Try again shortly.");
});
