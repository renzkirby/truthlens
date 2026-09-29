function trimmedText(value) {
   return typeof value === "string" ? value.trim() : "";
}

export function getAnalyzedClaimText(claim) {
   const analyzedClaim = trimmedText(claim?.analyzed_claim);
   if (analyzedClaim) return analyzedClaim;

   // Historical non-TEXT context may be a full article or other source material.
   if (trimmedText(claim?.claim_type).toUpperCase() === "TEXT") {
      const legacyText = trimmedText(claim?.context_text);
      if (legacyText) return legacyText;
   }
   return "";
}

export function getOriginalMaterialText(claim) {
   return trimmedText(claim?.source_context) || trimmedText(claim?.context_text);
}
