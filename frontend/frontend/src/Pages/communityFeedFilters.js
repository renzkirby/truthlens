export const TOPIC_ALL = "ALL";
export const CAMPUS_AFFAIRS_TOPIC = "CAMPUS_AFFAIRS";

export const SUBJECT_TOPIC_FILTERS = [
   { value: "POLITICS_GOVERNMENT_LAW", label: "Politics, Governance & Law" },
   { value: "BUSINESS_ECONOMY", label: "Business & Economy" },
   { value: "HEALTH_MEDICINE", label: "Health & Medicine" },
   { value: "SCIENCE_TECHNOLOGY", label: "Science & Technology" },
   { value: "EDUCATION", label: "Education" },
   { value: "ENVIRONMENT_SAFETY", label: "Environment & Public Safety" },
   { value: "SPORTS", label: "Sports" },
   { value: "CULTURE_ENTERTAINMENT", label: "Culture & Entertainment" },
];

export const CONTEXT_TOPIC_FILTERS = [
   { value: CAMPUS_AFFAIRS_TOPIC, label: "Campus Affairs" },
];

export const TOPIC_FILTERS = [
   { value: TOPIC_ALL, label: "All Topics" },
   ...SUBJECT_TOPIC_FILTERS,
   ...CONTEXT_TOPIC_FILTERS,
];

export function buildCommunityFeedQuery({
   searchTerm = "",
   sortOrder = "newest",
   topic = TOPIC_ALL,
   assessmentSource = "ALL",
   claimType = "ALL",
} = {}) {
   const query = new URLSearchParams();
   const normalizedSearch = typeof searchTerm === "string" ? searchTerm.trim() : "";

   if (normalizedSearch) query.set("search", normalizedSearch);
   query.set("sort", sortOrder || "newest");
   if (topic && topic !== TOPIC_ALL) query.set("topic", topic);
   if (assessmentSource && assessmentSource !== "ALL") {
      query.set("assessment_source", assessmentSource);
   }
   if (claimType && claimType !== "ALL") query.set("claim_type", claimType);

   return query.toString();
}
