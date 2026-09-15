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

export function AuthProvider({ children }) {
   const [token, setToken] = useState(getAccessToken() || null);
   const [user, setUser] = useState(null);
   const [loading, setLoading] = useState(Boolean(getAccessToken()));
   const authGenerationRef = useRef(0);
   const sessionHydratingRef = useRef(Boolean(getAccessToken()));
   const apiClientRef = useRef(
      axios.create({
         timeout: 30000,
      }),
   );

   const logout = useCallback(() => {
      authGenerationRef.current += 1;
      sessionHydratingRef.current = false;
      clearAuthTokens();

      setToken(null);
      setUser(null);
      setLoading(false);
   }, []);

   const fetchUser = useCallback(async (accessToken, generation = authGenerationRef.current) => {
      try {
         const response = await apiClientRef.current.get(`${API_BASE_URL}/auth/me/`, {
            _authGeneration: generation,
            headers: {
               Authorization: `Bearer ${accessToken}`,
            },
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
      } finally {
         if (authGenerationRef.current === generation) {
            setLoading(false);
         }
      }
   }, []);

   const login = async (access, refresh, rememberMe = false) => {
      const generation = ++authGenerationRef.current;
      sessionHydratingRef.current = true;
      setToken(null);
      setUser(null);
      setLoading(true);

      try {
         storeAuthTokens(access, refresh, rememberMe);

         if (!access) {
            throw new Error("Missing access token");
         }

         const hydratedUser = await fetchUser(access, generation);

         if (authGenerationRef.current !== generation) {
            throw new Error("Authentication session changed");
         }

         sessionHydratingRef.current = false;
         setToken(getAccessToken());
         return hydratedUser;
      } catch {
         if (authGenerationRef.current === generation) {
            logout();
         }

         const error = new Error("Unable to initialize your authenticated session. Please sign in again.");
         error.code = "SESSION_INITIALIZATION_FAILED";
         throw error;
      }
   };

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

            if (
               requestUrl.includes("/api/token/refresh/") ||
               requestUrl.includes("/auth/refresh/") ||
               originalRequest._retry
            ) {
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
                  { headers: { "Content-Type": "application/json" } },
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

               if (originalRequest._authGeneration === authGenerationRef.current) {
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
      const savedToken = getAccessToken();

      if (savedToken) {
         const generation = authGenerationRef.current;

         fetchUser(savedToken, generation)
            .then(() => {
               if (authGenerationRef.current === generation) {
                  sessionHydratingRef.current = false;
                  setToken(getAccessToken());
               }
            })
            .catch(() => {
               if (authGenerationRef.current === generation) {
                  logout();
               }
            });
      } else {
         sessionHydratingRef.current = false;
         setLoading(false);
      }
   }, [fetchUser, logout]);

   return (
      <AuthContext.Provider value={{ token, login, logout, authFetch, user, loading, refreshUser }}>
         {children}
      </AuthContext.Provider>
   );
}
