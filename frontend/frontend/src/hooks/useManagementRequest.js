import { useCallback, useEffect, useState } from "react";

import { useAuth } from "./useAuth";
import { userFacingErrorMessage } from "../utils/userFacingError";

export function useManagementRequest(url) {
   const { authFetch } = useAuth();
   const [requestVersion, setRequestVersion] = useState(0);
   const requestKey = `${url}::${requestVersion}`;
   const [result, setResult] = useState({ key: null, data: null, error: "" });

   const retry = useCallback(() => setRequestVersion((version) => version + 1), []);

   useEffect(() => {
      let active = true;

      authFetch(url, { method: "GET" })
         .then((payload) => {
            if (active) setResult({ key: requestKey, data: payload, error: "" });
         })
         .catch((requestError) => {
            if (active) {
               setResult({
                  key: requestKey,
                  data: null,
                  error: userFacingErrorMessage(requestError, {
                     fallback: "We couldn't load this management information. Try again.",
                     authMessage: "Your session has expired. Sign in again to load Management Console data.",
                     permissionMessage: "Your account doesn't have permission to view this management information.",
                     serviceMessage: "Management Console data is temporarily unavailable. Try again shortly.",
                  }),
               });
            }
         });

      return () => {
         active = false;
      };
   }, [authFetch, requestKey, url]);

   return {
      data: result.key === requestKey ? result.data : null,
      loading: result.key !== requestKey,
      error: result.key === requestKey ? result.error : "",
      retry,
   };
}
