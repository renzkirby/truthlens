/**
 * Custom Hook: useFetchThreads
 * ══════════════════════════════════════════════════════════════════
 * Encapsulates all thread data fetching logic.
 * Eliminates code duplication across components that fetch threads.
 *
 * Features:
 *   - Automatic loading/error state management
 *   - Single API call point (easier to modify)
 *   - Consistent error handling
 *
 * Usage:
 *   const { threads, loading, error } = useFetchThreads(authFetch);
 */

import { useCallback, useEffect, useState } from "react";
import { resolveApiEndpoint } from "../utils/api";

/**
 * Hook to fetch all threads from the API.
 *
 * @param {function} authFetch - Authenticated fetch function from AuthContext
 * @returns {object} { threads, loading, error, refetch }
 *   - threads: Array of thread objects
 *   - loading: Boolean indicating fetch in progress
 *   - error: Error message string or null
 *   - refetch: Function to manually trigger a refetch
 */
const normalizeThreadResponse = (payload) => {
   if (Array.isArray(payload)) return payload;
   if (payload && Array.isArray(payload.results)) return payload.results;
   return [];
};

function useFetchThreads(authFetch) {
   const [threads, setThreads] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);

   // ── Fetch threads from API ──
   const fetchThreads = useCallback(async () => {
      try {
         setLoading(true);
         setError(null);

         const url = resolveApiEndpoint("THREADS");
         const data = await authFetch(url, { method: "GET" });

         setThreads(normalizeThreadResponse(data));
      } catch (err) {
         console.error("Failed to fetch threads:", err);
         setError("Failed to load threads");
      } finally {
         setLoading(false);
      }
   }, [authFetch]);

   // ── Auto-fetch on component mount ──
   useEffect(() => {
      if (authFetch) {
         fetchThreads();
      }
   }, [authFetch, fetchThreads]);

   // ── Return state + refetch ability ──
   return {
      threads,
      loading,
      error,
      refetch: fetchThreads,
   };
}

export default useFetchThreads;
