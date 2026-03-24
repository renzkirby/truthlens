/**
 * Custom Hook: useFetchClaims
 * ══════════════════════════════════════════════════════════════════
 * Encapsulates all claim data fetching logic (especially user's own claims).
 * Eliminates code duplication across components that fetch claims.
 *
 * Features:
 *   - Automatic loading/error state management
 *   - Supports both "my claims" and general claims endpoints
 *   - Consistent error handling
 *
 * Usage:
 *   const { claims, loading, error } = useFetchClaims(authFetch, "my-claims");
 */

import { useEffect, useState } from "react";
import { useEndpoint } from "../utils/api";

/**
 * Hook to fetch claims from the API.
 *
 * @param {function} authFetch - Authenticated fetch function from AuthContext
 * @param {string} claimType - Type of claims: "my-claims" or "claims" (default)
 * @returns {object} { claims, loading, error, refetch }
 *   - claims: Array of claim objects
 *   - loading: Boolean indicating fetch in progress
 *   - error: Error message string or null
 *   - refetch: Function to manually trigger a refetch
 */
function useFetchClaims(authFetch, claimType = "claims") {
   const [claims, setClaims] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);

   // ── Determine endpoint based on claimType ──
   const getEndpointUrl = () => {
      if (claimType === "my-claims") {
         return useEndpoint("MY_CLAIMS");
      }
      return useEndpoint("CLAIMS");
   };

   // ── Fetch claims from API ──
   const fetchClaims = async () => {
      try {
         setLoading(true);
         setError(null);

         const url = getEndpointUrl();
         const data = await authFetch(url, { method: "GET" });

         setClaims(data || []);
      } catch (err) {
         console.error(`Failed to fetch ${claimType}:`, err);
         setError(`Failed to load ${claimType}`);
      } finally {
         setLoading(false);
      }
   };

   // ── Auto-fetch on component mount or endpoint change ──
   useEffect(() => {
      if (authFetch) {
         fetchClaims();
      }
   }, [authFetch, claimType]);

   // ── Return state + refetch ability ──
   return {
      claims,
      loading,
      error,
      refetch: fetchClaims,
   };
}

export default useFetchClaims;
