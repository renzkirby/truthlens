import assert from "node:assert/strict";
import test from "node:test";

import {
   CAMPUS_AFFAIRS_TOPIC,
   CONTEXT_TOPIC_FILTERS,
   SUBJECT_TOPIC_FILTERS,
   TOPIC_ALL,
   TOPIC_FILTERS,
   buildCommunityFeedQuery,
} from "./communityFeedFilters.js";

test("Campus Affairs is exposed as a context filter, not a subject topic", () => {
   assert.equal(
      SUBJECT_TOPIC_FILTERS.some((topic) => topic.value === CAMPUS_AFFAIRS_TOPIC),
      false,
   );
   assert.deepEqual(CONTEXT_TOPIC_FILTERS, [
      { value: CAMPUS_AFFAIRS_TOPIC, label: "Campus Affairs" },
   ]);
   assert.equal(
      TOPIC_FILTERS.find((topic) => topic.value === CAMPUS_AFFAIRS_TOPIC)?.label,
      "Campus Affairs",
   );
});

test("Campus Affairs combines with existing Community filters", () => {
   const query = new URLSearchParams(
      buildCommunityFeedQuery({
         searchTerm: " campus clinic ",
         sortOrder: "oldest",
         topic: CAMPUS_AFFAIRS_TOPIC,
         assessmentSource: "human",
         claimType: "URL",
      }),
   );

   assert.equal(query.get("search"), "campus clinic");
   assert.equal(query.get("sort"), "oldest");
   assert.equal(query.get("topic"), CAMPUS_AFFAIRS_TOPIC);
   assert.equal(query.get("assessment_source"), "human");
   assert.equal(query.get("claim_type"), "URL");
});

test("All Topics omits the topic query parameter", () => {
   const query = new URLSearchParams(
      buildCommunityFeedQuery({
         topic: TOPIC_ALL,
      }),
   );

   assert.equal(query.get("topic"), null);
   assert.equal(query.get("sort"), "newest");
});
