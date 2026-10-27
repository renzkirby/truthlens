export const INTAKE_CLASSIFICATION_ALL = "";
export const INTAKE_CLASSIFICATION_UNCLASSIFIED = "UNCLASSIFIED";

export const INTAKE_CLASSIFICATION_OPTIONS = [
   { value: INTAKE_CLASSIFICATION_ALL, label: "All classifications" },
   { value: "CIVICS", label: "Civics & Governance" },
   { value: "ELECTIONS", label: "Elections" },
   { value: "LAW", label: "Law" },
   { value: "HEALTH", label: "Health" },
   { value: "SCIENCE", label: "Science" },
   { value: "TECHNOLOGY", label: "Technology" },
   { value: "EDUCATION", label: "Education" },
   { value: "ECONOMY", label: "Economy" },
   { value: "ENVIRONMENT", label: "Environment" },
   { value: "DISASTERS", label: "Disasters & Public Safety" },
   { value: "SPORTS", label: "Sports" },
   { value: "CULTURE", label: "Culture & Entertainment" },
   { value: INTAKE_CLASSIFICATION_UNCLASSIFIED, label: "Unclassified" },
];

export function buildVerificationIntakeQuery({
   organizationId,
   limit,
   offset,
   classification = INTAKE_CLASSIFICATION_ALL,
} = {}) {
   const query = new URLSearchParams({
      organization_id: String(organizationId ?? ""),
      limit: String(limit ?? ""),
      offset: String(offset ?? 0),
   });

   if (classification) {
      query.set("classification", classification);
   }

   return query.toString();
}
