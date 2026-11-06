const VERDICT_PRESENTATIONS = Object.freeze({
   FACT: Object.freeze({
      accent: "#10b981",
      ink: "#065f46",
      tint: "#ecfdf5",
      chip: "#059669",
      className: "fact",
      label: "Fact",
      description: "Available evidence supports the claim.",
   }),
   FAKE: Object.freeze({
      accent: "#ef4444",
      ink: "#991b1b",
      tint: "#fef2f2",
      chip: "#ef4444",
      className: "fake",
      label: "Fake",
      description: "Available evidence contradicts the claim.",
   }),
   MISLEADING: Object.freeze({
      accent: "#f97316",
      ink: "#9a3412",
      tint: "#fff7ed",
      chip: "#f26a0a",
      className: "misleading",
      label: "Misleading",
      description: "Partly accurate, but important context is missing or distorted.",
   }),
   SATIRE: Object.freeze({
      accent: "#8b5cf6",
      ink: "#5b21b6",
      tint: "#f5f3ff",
      chip: "#8b5cf6",
      className: "satire",
      label: "Satire",
      description: "Presented as satire or parody, not factual reporting.",
   }),
   UNVERIFIED: Object.freeze({
      accent: "#e0c85a",
      ink: "#5c4700",
      tint: "#faf5e1",
      chip: "#b08d1a",
      className: "unverified",
      label: "Unverified",
      description: "Evidence is not enough to confirm or refute the claim.",
   }),
   OUT_OF_SCOPE: Object.freeze({
      accent: "#9ca3af",
      ink: "#374151",
      tint: "#f3f4f6",
      chip: "#6b7280",
      className: "out-of-scope",
      label: "Out of Scope",
      description: "No sufficiently verifiable public factual claim was identified.",
   }),
});

export function getVerdictPresentation(verdict) {
   return VERDICT_PRESENTATIONS[verdict] || VERDICT_PRESENTATIONS.UNVERIFIED;
}

export function getConfidenceLevel(value) {
   const numericValue = Number(value);
   if (!Number.isFinite(numericValue)) return "Unavailable";
   if (numericValue >= 80) return "High";
   if (numericValue >= 60) return "Moderate";
   return "Low";
}

export { VERDICT_PRESENTATIONS };
