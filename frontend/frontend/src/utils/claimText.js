export function getAnalyzedClaimText(claim, fallback = "") {
   for (const value of [claim?.analyzed_claim, claim?.context_text, fallback]) {
      if (typeof value === "string" && value.trim()) return value.trim();
   }
   return "";
}
