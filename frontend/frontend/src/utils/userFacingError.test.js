import assert from "node:assert/strict";
import test from "node:test";

import {
   classifyUserFacingError,
   safeUserFacingDetail,
   userFacingErrorMessage,
   userFacingFieldError,
} from "./userFacingError.js";

test("classifies common HTTP errors", () => {
   assert.equal(classifyUserFacingError({ status: 401 }), "auth");
   assert.equal(classifyUserFacingError({ status: 403 }), "permission");
   assert.equal(classifyUserFacingError({ status: 404 }), "not_found");
   assert.equal(classifyUserFacingError({ status: 409 }), "conflict");
   assert.equal(classifyUserFacingError({ status: 429 }), "rate_limit");
   assert.equal(classifyUserFacingError({ status: 503 }), "service");
});

test("preserves safe validation and conflict detail", () => {
   assert.equal(
      userFacingErrorMessage({ status: 400, detail: "Choose a valid discussion category." }),
      "Choose a valid discussion category.",
   );
   assert.equal(
      userFacingErrorMessage({ status: 409, detail: "This discussion changed. Refresh it before editing." }),
      "This discussion changed. Refresh it before editing.",
   );
});

test("sanitizes structured field detail", () => {
   assert.equal(
      userFacingFieldError(
         { email: ["Enter a valid email address."] },
         "email",
      ),
      "Enter a valid email address.",
   );
   assert.equal(
      safeUserFacingDetail(["", "Choose a supported file type."]),
      "Choose a supported file type.",
   );
   assert.equal(
      userFacingFieldError(
         { password: ["IntegrityError: password constraint failed"] },
         "password",
      ),
      "",
   );
});

test("uses stable application-code fallbacks when safe detail is absent", () => {
   assert.equal(
      userFacingErrorMessage({ status: 409, code: "ASSIGNMENT_CONFLICT" }),
      "This investigation is no longer available for this action. Refresh the investigation and review its current status.",
   );
   assert.equal(
      userFacingErrorMessage({ status: 403, code: "OUTSIDE_SPECIALIZATIONS" }),
      "Your account doesn't have permission to perform this action.",
   );
   assert.equal(
      userFacingErrorMessage({ status: 400, failure_code: "URL_POLICY_BLOCKED" }),
      "This URL cannot be processed because it does not meet TruthLens URL safety requirements.",
   );
});

test("does not surface internal server diagnostics", () => {
   const message = userFacingErrorMessage({
      status: 500,
      detail: "IntegrityError: duplicate key value violates constraint",
   });
   assert.equal(message, "TruthLens is temporarily unavailable. Try again shortly.");
   assert.doesNotMatch(message, /IntegrityError|constraint/i);
});

test("distinguishes network and timeout failures", () => {
   assert.equal(classifyUserFacingError({ status: null, message: "Network Error" }), "network");
   assert.equal(classifyUserFacingError({ code: "ECONNABORTED", message: "timeout exceeded" }), "timeout");
});

test("known URL threats are security failures with specific safe copy", () => {
   assert.equal(classifyUserFacingError({ failure_code: "URL_KNOWN_THREAT" }), "security");
   assert.equal(
      userFacingErrorMessage({ failure_code: "URL_KNOWN_THREAT" }),
      "This URL was flagged for a known security threat and cannot be analyzed.",
   );
});
