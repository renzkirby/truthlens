export function getEffectiveVerdict(claim) {
   if (!claim) return null;
   return claim.final_verdict || claim.verdict || claim.ai_verdict || null;
}

export function getAiVerdict(claim) {
   if (!claim) return null;
   return claim.ai_verdict || claim.verdict || null;
}
