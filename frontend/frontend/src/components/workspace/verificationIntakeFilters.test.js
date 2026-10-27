import assert from "node:assert/strict";
import test from "node:test";

import {
   INTAKE_CLASSIFICATION_ALL,
   INTAKE_CLASSIFICATION_OPTIONS,
   INTAKE_CLASSIFICATION_UNCLASSIFIED,
   buildVerificationIntakeQuery,
} from "./verificationIntakeFilters.js";

test("intake exposes all internal subject classifications plus Unclassified", () => {
   assert.deepEqual(
      INTAKE_CLASSIFICATION_OPTIONS.map((option) => option.value),
      [
         "",
         "CIVICS",
         "ELECTIONS",
         "LAW",
         "HEALTH",
         "SCIENCE",
         "TECHNOLOGY",
         "EDUCATION",
         "ECONOMY",
         "ENVIRONMENT",
         "DISASTERS",
         "SPORTS",
         "CULTURE",
         "UNCLASSIFIED",
      ],
   );
});

test("All classifications omits the classification query parameter", () => {
   const query = new URLSearchParams(
      buildVerificationIntakeQuery({
         organizationId: "org-1",
         limit: 10,
         offset: 20,
         classification: INTAKE_CLASSIFICATION_ALL,
      }),
   );

   assert.equal(query.get("organization_id"), "org-1");
   assert.equal(query.get("limit"), "10");
   assert.equal(query.get("offset"), "20");
   assert.equal(query.get("classification"), null);
});

test("domain and Unclassified filters are sent to the intake API", () => {
   for (const classification of ["SCIENCE", "LAW", INTAKE_CLASSIFICATION_UNCLASSIFIED]) {
      const query = new URLSearchParams(
         buildVerificationIntakeQuery({
            organizationId: "org-1",
            limit: 10,
            offset: 0,
            classification,
         }),
      );

      assert.equal(query.get("classification"), classification);
   }
});
