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
   const apiClientRef = useRef(
      axios.create({
         timeout: 30000,
      }),
   );

   const login = (access, refresh, rememberMe = false) => {
      storeAuthTokens(access, refresh, rememberMe);

      if (!access) {
         setToken(null);
         return Promise.resolve(null);
      }

      setToken(access);

      return fetchUser(access);
   };

   const logout = () => {
      clearAuthTokens();

      setToken(null);
      setUser(null);
      setLoading(false);
   };

   useEffect(() => {
      const apiClient = apiClientRef.current;
      let isRefreshing = false;
      let pendingRequests = [];

      const requestInterceptor = apiClient.interceptors.request.use((config) => {
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

               updateAuthTokens(newAccessToken, nextRefreshToken);
               setToken(newAccessToken);

               pendingRequests.forEach(({ resolve }) => resolve(newAccessToken));
               pendingRequests = [];

               originalRequest.headers = originalRequest.headers || {};
               originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
               return apiClient(originalRequest);
            } catch (refreshError) {
               pendingRequests.forEach(({ reject }) => reject(refreshError));
               pendingRequests = [];
               logout();
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
   }, []);

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
         });

         return response.status === 204 ? null : response.data;
      } catch (error) {
         const responseData = error?.response?.data;

         const detailMessage =
            (typeof responseData === "object" && responseData?.detail) ||
            (typeof responseData === "string" ? responseData : null);

         throw new Error(detailMessage || error.message || "Request failed");
      }
   }, []);

   const fetchUser = async (accessToken) => {
      try {
         const response = await apiClientRef.current.get(`${API_BASE_URL}/auth/me/`, {
            headers: {
               Authorization: `Bearer ${accessToken}`,
            },
         });
         const data = response.data;
         const normalizedTrustScore = Number(data?.trust_breakdown?.trust_score ?? data?.trust_score ?? 0);
         const normalizedUser = {
            ...data,
            trust_score: normalizedTrustScore,
         };
         setUser(normalizedUser);
         return normalizedUser; // Return user data so caller can use it
      } catch (error) {
         console.error("Failed to fetch user:", error);
         return null;
      } finally {
         setLoading(false);
      }
   };

   const refreshUser = useCallback(() => {
      const activeToken = token || getAccessToken();

      if (!activeToken) {
         return Promise.resolve(null);
      }

      return fetchUser(activeToken);
   }, [token]);

   useEffect(() => {
      const savedToken = getAccessToken();

      if (savedToken) {
         fetchUser(savedToken);
      } else {
         setLoading(false);
      }
   }, []);

   return (
      <AuthContext.Provider value={{ token, login, logout, authFetch, user, loading, refreshUser }}>
         {children}
      </AuthContext.Provider>
   );
}
