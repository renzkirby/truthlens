const MAX_SAFE_DETAIL_LENGTH = 240;

const UNSAFE_DETAIL_PATTERN =
   /<[^>]+>|traceback|stack trace|django|internal server error|exception at|request failed with status code|network error|unexpected token|parse error|\b(?:valueerror|typeerror|runtimeerror|databaseerror|integrityerror|operationalerror|programmingerror)\b|\bsql\b|\bat\s+\S+\s*\([^)]*:\d+:\d+\)/i;

const NETWORK_PATTERN = /network error|failed to fetch|load failed|network request failed|connection refused|err_network/i;
const TIMEOUT_PATTERN = /timeout|timed out|econnaborted|etimedout/i;

const KNOWN_ERROR_CODE_MESSAGES = {
   URL_KNOWN_THREAT: "This URL was flagged for a known security threat and cannot be analyzed.",
   URL_POLICY_BLOCKED: "This URL cannot be processed because it does not meet TruthLens URL safety requirements.",
   INSUFFICIENT_CONTEXT:
      "TruthLens needs more context to identify the exact factual claim. Add identifying details and try again.",
   OUTSIDE_SPECIALIZATIONS:
      "This investigation is outside your organization's selected verification specializations.",
   ASSIGNMENT_CONFLICT:
      "This investigation is no longer available for this action. Refresh the investigation and review its current status.",
   STALE_EDIT_GENERATION:
      "This information changed while you were working. Refresh the latest version before continuing.",
   DRAFT_UPDATE_NO_LONGER_ALLOWED:
      "This draft can no longer be updated in its current state. Refresh the investigation and review the latest status.",
};

function cleanString(value) {
   if (typeof value !== "string") return "";
   const compact = value.trim().replace(/\s+/g, " ");
   if (!compact || compact.length > MAX_SAFE_DETAIL_LENGTH || UNSAFE_DETAIL_PATTERN.test(compact)) {
      return "";
   }
   return compact;
}

export function safeUserFacingDetail(value) {
   if (Array.isArray(value)) {
      return value.map(safeUserFacingDetail).find(Boolean) || "";
   }

   if (typeof value === "string") {
      return cleanString(value);
   }

   return "";
}

export function userFacingFieldError(error, field) {
   return safeUserFacingDetail(error?.[field]);
}

function errorStatus(error) {
   const rawStatus = error?.status;
   if (rawStatus === null || rawStatus === undefined || rawStatus === "") return null;
   const value = Number(rawStatus);
   return Number.isInteger(value) ? value : null;
}

function errorCode(error) {
   return String(error?.code || error?.failure_code || "").trim().toUpperCase();
}

function knownErrorCodeMessage(error) {
   return KNOWN_ERROR_CODE_MESSAGES[errorCode(error)] || "";
}

export function classifyUserFacingError(error) {
   const status = errorStatus(error);
   const code = errorCode(error);
   const message = String(error?.message || "");

   if (code === "URL_KNOWN_THREAT" || error?.url_safety?.status === "UNSAFE" || error?.url_safety?.status === "KNOWN_THREAT") {
      return "security";
   }
   if (code === "URL_POLICY_BLOCKED") return "validation";
   if (status === 401) return "auth";
   if (status === 403) return "permission";
   if (status === 404) return "not_found";
   if (status === 409) return "conflict";
   if (status === 429) return "rate_limit";
   if ([400, 413, 415, 422].includes(status)) return "validation";
   if (status !== null && status >= 500) return "service";
   if (TIMEOUT_PATTERN.test(code) || TIMEOUT_PATTERN.test(message)) return "timeout";
   if (NETWORK_PATTERN.test(code) || NETWORK_PATTERN.test(message)) return "network";
   return "unknown";
}

export function getUserFacingError(error, options = {}) {
   const {
      fallback = "We couldn't complete that action. Try again.",
      validationMessage = null,
      notFoundMessage = null,
      conflictMessage = null,
      permissionMessage = null,
      authMessage = null,
      serviceMessage = null,
      rateLimitMessage = null,
      networkMessage = null,
      timeoutMessage = null,
      securityMessage = null,
   } = options;

   const kind = classifyUserFacingError(error);
   const detail = safeUserFacingDetail(error?.detail) || safeUserFacingDetail(error?.message);
   const codeMessage = knownErrorCodeMessage(error);

   const defaults = {
      security:
         securityMessage ||
         codeMessage ||
         "TruthLens blocked this request because it did not pass a security check.",
      validation:
         detail ||
         codeMessage ||
         validationMessage ||
         "Check the information you entered and try again.",
      auth: authMessage || "Your session has expired. Sign in again to continue.",
      permission:
         permissionMessage ||
         "Your account doesn't have permission to perform this action.",
      not_found:
         notFoundMessage ||
         "This item is no longer available.",
      conflict:
         detail ||
         codeMessage ||
         conflictMessage ||
         "This information changed while you were working. Refresh the page and try again.",
      rate_limit:
         rateLimitMessage ||
         "Too many requests were made in a short period. Wait a moment before trying again.",
      timeout:
         timeoutMessage ||
         "TruthLens took too long to respond. Try again.",
      network:
         networkMessage ||
         "TruthLens couldn't be reached. Check your internet connection and try again.",
      service:
         serviceMessage ||
         "TruthLens is temporarily unavailable. Try again shortly.",
      unknown: codeMessage || fallback,
   };

   return {
      kind,
      message: defaults[kind] || fallback,
      retryable: ["rate_limit", "timeout", "network", "service", "unknown"].includes(kind),
   };
}

export function userFacingErrorMessage(error, options = {}) {
   return getUserFacingError(error, options).message;
}
