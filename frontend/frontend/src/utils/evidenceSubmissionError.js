const MAX_SAFE_MESSAGE_LENGTH = 200;

function firstSafeString(value) {
   const candidates = Array.isArray(value) ? value : [value];
   return candidates
      .find((item) => typeof item === "string" && item.trim())
      ?.trim() || "";
}

export function evidenceSubmissionErrorMessage(error) {
   const status = Number(error?.status);
   if (!Number.isInteger(status) || status < 400 || status >= 500) {
      return "We couldn't submit this evidence. Please review it and try again.";
   }

   const urlError = firstSafeString(error?.evidence_url);
   if (urlError) {
      const normalized = urlError.toLowerCase();

      if (
         normalized.includes("flagged as unsafe") ||
         normalized.includes("known security threat")
      ) {
         return "This source URL was flagged for a known security threat and cannot be submitted.";
      }

      if (
         normalized.includes("local urls are not allowed") ||
         normalized.includes("private network urls are not allowed")
      ) {
         return "Local or private-network URLs cannot be submitted as evidence.";
      }

      if (
         urlError.length <= MAX_SAFE_MESSAGE_LENGTH &&
         !/<[a-z][\s\S]*>|traceback|stack trace|internal server|exception|sql|django/i.test(urlError)
      ) {
         return urlError;
      }
   }

   const detail = firstSafeString(error?.detail);
   if (
      detail &&
      detail.length <= MAX_SAFE_MESSAGE_LENGTH &&
      !/<[a-z][\s\S]*>|traceback|stack trace|internal server|exception|sql|django|request failed|network error/i.test(detail)
   ) {
      return detail;
   }

   return "We couldn't submit this evidence. Please review it and try again.";
}
