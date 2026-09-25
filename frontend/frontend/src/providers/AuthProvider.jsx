import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import AuthContext from "../context/AuthContext";
import { API_BASE_URL } from "../utils/constants";
import {
   getAccessToken,
   getRefreshToken,
   storeAuthTokens,
   updateAuthTokens,
   clearAuthTokens,
} from "../utils/authStorage";

const API_ROOT_URL = API_BASE_URL.replace(/\/api\/?$/, "");
const TOKEN_REFRESH_URL = `${API_ROOT_URL}/api/token/refresh/`;
const AUTH_REQUEST_TIMEOUT_MS = 30000;
const SESSION_RETRY_DELAY_MS = 15000;

const getFailureStatus = (error) => error?.response?.status ?? error?.status ?? null;

const isTransientAuthFailure = (error) => {
   const status = getFailureStatus(error);

   return !error?.response || status === 408 || status === 429 || status >= 500;
};

const isRefreshEndpointUrl = (url = "") =>
   url.includes("/api/token/refresh/") || url.includes("/auth/refresh/");

const isDefinitiveRefreshFailure = (error) => {
   const status = getFailureStatus(error);
   const requestUrl = error?.config?.url || "";

   return isRefreshEndpointUrl(requestUrl) && (status === 400 || status === 401);
};

const createSessionInitializationError = () => {
   const error = new Error("Unable to initialize your authenticated session. Please sign in again.");
   error.code = "SESSION_INITIALIZATION_FAILED";
   return error;
};

export function AuthProvider({ children }) {
   const [token, setToken] = useState(getAccessToken() || null);
   const [user, setUser] = useState(null);
   const [loading, setLoading] = useState(Boolean(getAccessToken() || getRefreshToken()));
   const [sessionRestoreError, setSessionRestoreError] = useState(null);
   const authGenerationRef = useRef(0);
   const sessionHydratingRef = useRef(Boolean(getAccessToken() || getRefreshToken()));
   const hydrationPromiseRef = useRef(null);
   const automaticRetryCountRef = useRef(0);
   const apiClientRef = useRef(
      axios.create({
         timeout: AUTH_REQUEST_TIMEOUT_MS,
      }),
   );

   const logout = useCallback(() => {
      authGenerationRef.current += 1;
      sessionHydratingRef.current = false;
      hydrationPromiseRef.current = null;
      automaticRetryCountRef.current = 0;
      clearAuthTokens();

      setToken(null);
      setUser(null);
      setLoading(false);
      setSessionRestoreError(null);
   }, []);

   const fetchUser = useCallback(async (accessToken, generation = authGenerationRef.current) => {
      const headers = accessToken
         ? { Authorization: `Bearer ${accessToken}` }
         : {};
      const response = await apiClientRef.current.get(`${API_BASE_URL}/auth/me/`, {
         _authGeneration: generation,
         headers,
      });
      const data = response.data;

      if (!data || typeof data !== "object" || Array.isArray(data)) {
         throw new Error("Invalid authenticated user response");
      }

      const normalizedTrustScore = Number(data?.trust_breakdown?.trust_score ?? data?.trust_score ?? 0);
      const normalizedUser = {
         ...data,
         trust_score: normalizedTrustScore,
      };

      if (authGenerationRef.current !== generation) {
         throw new Error("Authentication session changed");
      }

      setUser(normalizedUser);
      return normalizedUser;
   }, []);

   useEffect(() => {
      const apiClient = apiClientRef.current;
      let isRefreshing = false;
      let pendingRequests = [];

      const requestInterceptor = apiClient.interceptors.request.use((config) => {
         config._authGeneration ??= authGenerationRef.current;

         if (config._authGeneration !== authGenerationRef.current) {
            return Promise.reject(new Error("Authentication session changed"));
         }

         const accessToken = getAccessToken();
         config.headers = config.headers || {};

         if (accessToken && !config.headers.Authorization) {
            config.headers.Authorization = `Bearer ${accessToken}`;
         }

         return config;
      });

      const responseInterceptor = apiClient.interceptors.response.use(
         (response) => response,
         async (error) => {
            const originalRequest = error?.config;
            const statusCode = error?.response?.status;
            const requestUrl = originalRequest?.url || "";

            if (originalRequest && originalRequest._authGeneration !== authGenerationRef.current) {
               return Promise.reject(error);
            }

            if (!originalRequest || statusCode !== 401) {
               return Promise.reject(error);
            }

            if (isRefreshEndpointUrl(requestUrl) || originalRequest._retry) {
               logout();
               return Promise.reject(error);
            }

            const refreshToken = getRefreshToken();
            if (!refreshToken) {
               logout();
               return Promise.reject(error);
            }

            originalRequest._retry = true;

            if (isRefreshing) {
               return new Promise((resolve, reject) => {
                  pendingRequests.push({ resolve, reject });
               })
                  .then((newAccessToken) => {
                     if (originalRequest._authGeneration !== authGenerationRef.current) {
                        throw new Error("Authentication session changed");
                     }

                     originalRequest.headers = originalRequest.headers || {};
                     originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
                     return apiClient(originalRequest);
                  })
                  .catch((refreshError) => Promise.reject(refreshError));
            }

            isRefreshing = true;

            try {
               const refreshResponse = await axios.post(
                  TOKEN_REFRESH_URL,
                  { refresh: refreshToken },
                  {
                     headers: { "Content-Type": "application/json" },
                     timeout: AUTH_REQUEST_TIMEOUT_MS,
                  },
               );

               const newAccessToken = refreshResponse?.data?.access;
               const nextRefreshToken = refreshResponse?.data?.refresh || refreshToken;

               if (!newAccessToken) {
                  throw new Error("Session refresh failed");
               }

               if (originalRequest._authGeneration !== authGenerationRef.current) {
                  throw new Error("Authentication session changed");
               }

               updateAuthTokens(newAccessToken, nextRefreshToken);

               if (!sessionHydratingRef.current) {
                  setToken(newAccessToken);
               }

               pendingRequests.forEach(({ resolve }) => resolve(newAccessToken));
               pendingRequests = [];

               originalRequest.headers = originalRequest.headers || {};
               originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
               return apiClient(originalRequest);
            } catch (refreshError) {
               pendingRequests.forEach(({ reject }) => reject(refreshError));
               pendingRequests = [];

               if (
                  originalRequest._authGeneration === authGenerationRef.current &&
                  isDefinitiveRefreshFailure(refreshError)
               ) {
                  logout();
               }

               return Promise.reject(refreshError);
            } finally {
               isRefreshing = false;
            }
         },
      );

      return () => {
         apiClient.interceptors.request.eject(requestInterceptor);
         apiClient.interceptors.response.eject(responseInterceptor);
      };
   }, [logout]);

   const hydrateSession = useCallback(async (accessToken, generation) => {
      const activeHydration = hydrationPromiseRef.current;

      if (activeHydration?.generation === generation) {
         return activeHydration.promise;
      }

      sessionHydratingRef.current = true;
      setLoading(true);
      setSessionRestoreError(null);

      const hydrationPromise = fetchUser(accessToken, generation)
         .then((hydratedUser) => {
            if (authGenerationRef.current !== generation) {
               throw new Error("Authentication session changed");
            }

            sessionHydratingRef.current = false;
            automaticRetryCountRef.current = 0;
            setToken(getAccessToken());
            setLoading(false);
            setSessionRestoreError(null);
            return hydratedUser;
         })
         .catch((error) => {
            if (authGenerationRef.current === generation && (getAccessToken() || getRefreshToken())) {
               sessionHydratingRef.current = true;
               setLoading(true);
               setSessionRestoreError({
                  message: isTransientAuthFailure(error)
                     ? "TruthLens is temporarily unavailable. Your sign-in is still saved."
                     : "We could not restore your session yet. Your sign-in is still saved.",
               });
            }

            throw error;
         })
         .finally(() => {
            if (hydrationPromiseRef.current?.promise === hydrationPromise) {
               hydrationPromiseRef.current = null;
            }
         });

      hydrationPromiseRef.current = {
         generation,
         promise: hydrationPromise,
      };

      return hydrationPromise;
   }, [fetchUser]);

   const retrySessionRestore = useCallback(() => {
      const savedAccess = getAccessToken();
      const savedRefresh = getRefreshToken();

      if (!savedAccess && !savedRefresh) {
         logout();
         return Promise.resolve(null);
      }

      const generation = authGenerationRef.current;
      return hydrateSession(savedAccess, generation).catch(() => null);
   }, [hydrateSession, logout]);

   const login = async (access, refresh, rememberMe = false) => {
      const generation = ++authGenerationRef.current;
      sessionHydratingRef.current = true;
      hydrationPromiseRef.current = null;
      automaticRetryCountRef.current = 0;
      setToken(null);
      setUser(null);
      setLoading(true);
      setSessionRestoreError(null);

      if (!access || !refresh) {
         if (authGenerationRef.current === generation) {
            logout();
         }

         throw createSessionInitializationError();
      }

      storeAuthTokens(access, refresh, rememberMe === true);

      try {
         return await hydrateSession(access, generation);
      } catch {
         if (authGenerationRef.current !== generation || (!getAccessToken() && !getRefreshToken())) {
            throw createSessionInitializationError();
         }

         // Credentials remain valid unless the interceptor observed a
         // definitive authentication failure. Recovery continues in-place.
         return null;
      }
   };

   const authFetch = useCallback(async (url, options = {}, accessToken = null) => {
      try {
         const headers = {
            ...(options.headers || {}),
         };

         if (accessToken) {
            headers.Authorization = `Bearer ${accessToken}`;
         }

         const response = await apiClientRef.current.request({
            url,
            method: options.method || "GET",
            headers,
            data: options.body,
            _authGeneration: authGenerationRef.current,
         });

         return response.status === 204 ? null : response.data;
      } catch (error) {
         const responseData = error?.response?.data;

         const detailMessage =
            (typeof responseData === "object" && responseData?.detail) ||
            (typeof responseData === "string" ? responseData : null);

         const normalizedError = new Error(detailMessage || error.message || "Request failed");
         normalizedError.status = error?.response?.status ?? null;

         if (responseData && typeof responseData === "object") {
            Object.assign(normalizedError, responseData);
         }

         throw normalizedError;
      }
   }, []);

   const refreshUser = useCallback(() => {
      const activeToken = getAccessToken();

      if (!activeToken) {
         return Promise.resolve(null);
      }

      return fetchUser(activeToken).catch(() => null);
   }, [fetchUser]);

   useEffect(() => {
      const savedAccess = getAccessToken();
      const savedRefresh = getRefreshToken();

      if (savedAccess || savedRefresh) {
         const generation = authGenerationRef.current;
         hydrateSession(savedAccess, generation).catch(() => null);
      } else {
         sessionHydratingRef.current = false;
         setLoading(false);
      }
   }, [hydrateSession]);

   useEffect(() => {
      if (!sessionRestoreError) {
         return undefined;
      }

      const recoverSession = () => {
         retrySessionRestore();
      };
      const recoverVisibleSession = () => {
         if (document.visibilityState === "visible") {
            recoverSession();
         }
      };
      const retryTimer = automaticRetryCountRef.current < 1
         ? window.setTimeout(() => {
            automaticRetryCountRef.current += 1;
            recoverSession();
         }, SESSION_RETRY_DELAY_MS)
         : null;

      window.addEventListener("online", recoverSession);
      document.addEventListener("visibilitychange", recoverVisibleSession);

      return () => {
         if (retryTimer !== null) {
            window.clearTimeout(retryTimer);
         }

         window.removeEventListener("online", recoverSession);
         document.removeEventListener("visibilitychange", recoverVisibleSession);
      };
   }, [retrySessionRestore, sessionRestoreError]);

   return (
      <AuthContext.Provider
         value={{
            token,
            login,
            logout,
            authFetch,
            user,
            loading,
            refreshUser,
            sessionRestoreError,
            retrySessionRestore,
         }}
      >
         {children}
      </AuthContext.Provider>
   );
}
