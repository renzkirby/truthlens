import { useCallback, useRef, useState } from "react";

import { useAuth } from "./useAuth";

const ERROR_METADATA_KEYS = new Set(["detail", "message", "stack", "status"]);

function firstErrorMessage(value) {
   if (Array.isArray(value)) return value.map(firstErrorMessage).find(Boolean) || "";
   if (typeof value === "string") return value;
   return "";
}

function normalizeManagementMutationError(requestError) {
   const fields = {};

   Object.entries(requestError || {}).forEach(([key, value]) => {
      if (ERROR_METADATA_KEYS.has(key)) return;
      if (
         key === "name" &&
         requestError instanceof Error &&
         typeof value === "string" &&
         value === requestError.constructor.name
      ) {
         return;
      }
      const message = firstErrorMessage(value);
      if (message) fields[key] = message;
   });

   return {
      message:
         requestError?.detail ||
         fields.non_field_errors ||
         requestError?.message ||
         "The management action could not be completed.",
      fields,
      status: requestError?.status ?? null,
   };
}

export function useManagementMutation() {
   const { authFetch } = useAuth();
   const pendingRef = useRef(false);
   const [pending, setPending] = useState(false);
   const [error, setError] = useState(null);
   const [success, setSuccess] = useState("");

   const reset = useCallback(() => {
      if (pendingRef.current) return;
      setError(null);
      setSuccess("");
   }, []);

   const mutate = useCallback(async (url, options, successMessage = "") => {
      if (pendingRef.current) return { ok: false, duplicate: true };

      pendingRef.current = true;
      setPending(true);
      setError(null);
      setSuccess("");

      try {
         const data = await authFetch(url, options);
         setSuccess(successMessage);
         return { ok: true, data };
      } catch (requestError) {
         const normalizedError = normalizeManagementMutationError(requestError);
         setError(normalizedError);
         return { ok: false, error: normalizedError };
      } finally {
         pendingRef.current = false;
         setPending(false);
      }
   }, [authFetch]);

   return { mutate, pending, error, success, reset };
}

