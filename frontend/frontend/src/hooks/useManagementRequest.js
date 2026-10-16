import { useCallback, useEffect, useState } from "react";

import { useAuth } from "./useAuth";

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
                  error: requestError.message || "The management data could not be loaded.",
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
