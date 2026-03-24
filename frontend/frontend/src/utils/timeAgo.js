/**
 * Utility: timeAgo.js
 * ══════════════════════════════════════════════════════════════════
 * Centralized helper for human-readable relative time display.
 * Used throughout the application for timestamps on claims, threads, comments.
 *
 * Example:
 *   timeAgo("2024-01-15T10:30:00Z") => "2h ago"
 */

/**
 * Convert ISO date string to human-readable relative time format.
 * @param {string} dateString - ISO 8601 formatted date string
 * @returns {string} Human-readable time (e.g., "2m ago", "Just now")
 */
function timeAgo(dateString) {
   // Handle null or undefined input
   if (!dateString) return "—";

   // Calculate time difference in milliseconds
   const now = new Date();
   const past = new Date(dateString);
   const diffMs = now.getTime() - past.getTime();

   // Convert to different time units
   const diffSecs = Math.floor(diffMs / 1000);
   const diffMins = Math.floor(diffSecs / 60);
   const diffHours = Math.floor(diffMins / 60);
   const diffDays = Math.floor(diffHours / 24);
   const diffWeeks = Math.floor(diffDays / 7);

   // Return appropriate unit (prefer largest relevant unit)
   if (diffSecs < 1) return "Just now";
   if (diffMins < 1) return `${diffSecs}s ago`;
   if (diffHours < 1) return `${diffMins}m ago`;
   if (diffDays < 1) return `${diffHours}h ago`;
   if (diffWeeks < 1) return `${diffDays}d ago`;
   if (diffWeeks < 52) return `${diffWeeks}w ago`;
   return `${Math.floor(diffDays / 365)}y ago`;
}

export default timeAgo;
