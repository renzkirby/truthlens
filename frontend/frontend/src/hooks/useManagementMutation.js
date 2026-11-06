import { useCallback, useRef, useState } from "react";

import { useAuth } from "./useAuth";
import {
   safeUserFacingDetail,
   userFacingErrorMessage,
} from "../utils/userFacingError";

const ERROR_METADATA_KEYS = new Set([
   "detail",
   "message",
   "stack",
   "status",
   "code",
   "failure_code",
   "url_safety",
]);

function firstErrorMessage(value) {
   return safeUserFacingDetail(value);
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

   const fieldMessage = fields.non_field_errors || Object.values(fields)[0] || "";

   return {
      message:
         safeUserFacingDetail(requestError?.detail) ||
         fieldMessage ||
         userFacingErrorMessage(requestError, {
            fallback: "We couldn't complete this management action. Try again.",
            authMessage: "Your session has expired. Sign in again before continuing.",
            permissionMessage: "Your account doesn't have permission to perform this management action.",
            conflictMessage: "This record changed before your action was completed. Refresh it and try again.",
            serviceMessage: "Management actions are temporarily unavailable. Try again shortly.",
         }),
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

