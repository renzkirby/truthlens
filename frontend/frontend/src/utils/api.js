/**
 * Utility: api.js
 * ══════════════════════════════════════════════════════════════════
 * Centralized API URL builder and helper functions.
 * Abstracts URL construction to a single place for easier maintenance.
 *
 * Example:
 *   buildApiUrl("threads/") => "http://localhost:8000/api/threads/"
 *   buildApiUrl("moderation/threads", threadId, "resolve") => "http://localhost:8000/api/moderation/threads/{id}/resolve/"
 */

import { API_BASE_URL, API_ENDPOINTS } from "./constants";

/**
 * Build full API URL from base and relative path.
 * Handles trailing slashes automatically.
 *
 * @param {string} path - Relative path (e.g., "claims/", "threads/")
 * @returns {string} Full API URL (e.g., "http://localhost:8000/api/claims/")
 */
export function buildApiUrl(path) {
   const cleanBase = API_BASE_URL.replace(/\/$/, ""); // Remove trailing slash
   const cleanPath = path.replace(/^\//, ""); // Remove leading slash
   return `${cleanBase}/${cleanPath}`;
}

/**
 * Use predefined endpoint constant with optional path parameters.
 *
 * @param {string} endpoint - Endpoint key from API_ENDPOINTS
 * @param {...string} params - Substitution parameters
 * @returns {string} Built endpoint URL
 *
 * Example:
 *   useEndpoint("CLAIMS") => "http://localhost:8000/api/claims/"
 *   useEndpoint("THREADS") => "http://localhost:8000/api/threads/"
 */
export function useEndpoint(endpoint, ...params) {
   const path = API_ENDPOINTS[endpoint];
   if (typeof path === "function") {
      return buildApiUrl(path(...params));
   }
   return buildApiUrl(path);
}
