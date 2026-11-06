const MAX_SAFE_DETAIL_LENGTH = 240;
const UNSAFE_DETAIL_PATTERN =
   /<[^>]+>|traceback|stack trace|django|internal server error|exception at|request failed with status code|network error|unexpected token|parse error|\b(?:valueerror|typeerror|runtimeerror|databaseerror|integrityerror|operationalerror|programmingerror)\b|\bsql\b|\bat\s+\S+\s*\([^)]*:\d+:\d+\)/i;
const NETWORK_PATTERN = /network error|failed to fetch|load failed|network request failed|connection refused|err_network/i;
const TIMEOUT_PATTERN = /timeout|timed out|econnaborted|etimedout/i;

const KNOWN_CODE_MESSAGES = {
   URL_KNOWN_THREAT: "This URL was flagged for a known security threat and cannot be analyzed.",
   URL_POLICY_BLOCKED: "This URL cannot be processed because it does not meet TruthLens URL safety requirements.",
};

function cleanDetail(value) {
   if (typeof value !== "string") return "";
   const compact = value.trim().replace(/\s+/g, " ");
   if (!compact || compact.length > MAX_SAFE_DETAIL_LENGTH || UNSAFE_DETAIL_PATTERN.test(compact)) return "";
   return compact;
}

function normalizedErrorCode({ payload = null, error = null, failureCode = "" } = {}) {
   return String(failureCode || payload?.failure_code || error?.code || "").trim().toUpperCase();
}

export function classifyExtensionError({ status = null, payload = null, error = null, failureCode = "" } = {}) {
   const numericStatus =
      status === null || status === undefined || status === ""
         ? null
         : Number.isInteger(Number(status))
           ? Number(status)
           : null;
   const code = normalizedErrorCode({ payload, error, failureCode });
   const message = String(error?.message || "");
   const safetyStatus = payload?.url_safety?.status;

   if (code === "URL_KNOWN_THREAT" || safetyStatus === "UNSAFE" || safetyStatus === "KNOWN_THREAT") return "security_threat";
   if (code === "URL_POLICY_BLOCKED") return "input";
   if (numericStatus === 401) return "auth";
   if (numericStatus === 403) return "permission";
   if (numericStatus === 404) return "not_found";
   if (numericStatus === 409) return "conflict";
   if (numericStatus === 429) return "rate_limit";
   if ([400, 413, 415, 422].includes(numericStatus)) return "input";
   if (numericStatus !== null && numericStatus >= 500) return "service";
   if (TIMEOUT_PATTERN.test(code) || TIMEOUT_PATTERN.test(message)) return "timeout";
   if (NETWORK_PATTERN.test(code) || NETWORK_PATTERN.test(message)) return "network";
   return "service";
}

export function extensionErrorPresentation({
   status = null,
   payload = null,
   error = null,
   failureCode = "",
   fallback = "TruthLens couldn't complete this analysis.",
   inputMessage = null,
   notFoundMessage = null,
} = {}) {
   const kind = classifyExtensionError({ status, payload, error, failureCode });
   const code = normalizedErrorCode({ payload, error, failureCode });
   const safeDetail = cleanDetail(payload?.detail) || cleanDetail(payload?.error) || cleanDetail(error?.message);
   const codeMessage = KNOWN_CODE_MESSAGES[code] || "";

   const messages = {
      security_threat:
         safeDetail ||
         codeMessage ||
         "This URL was flagged for a known security threat and cannot be analyzed.",
      input:
         safeDetail ||
         codeMessage ||
         inputMessage ||
         "Check the submitted content and try again.",
      auth: "Your TruthLens session has expired. Sign in again before starting another verification.",
      permission: "Your account doesn't have permission to perform this verification.",
      not_found:
         notFoundMessage ||
         "This verification is no longer available. Start a new verification.",
      conflict:
         safeDetail ||
         "This verification changed while it was running. Start a new verification.",
      rate_limit:
         "Too many verification requests were made in a short period. Wait a moment before trying again.",
      timeout:
         "Verification took longer than expected. Try again when you're ready.",
      network:
         "TruthLens couldn't be reached. Check your internet connection and try again.",
      service:
         "TruthLens analysis is temporarily unavailable. Try again shortly.",
   };

   return { kind, message: messages[kind] || fallback };
}
