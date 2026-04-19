import { createContext, useContext, useEffect, useRef, useState } from "react";
import axios from "axios";
import { API_BASE_URL } from "../utils/constants";

const AuthContext = createContext(null);
const API_ROOT_URL = API_BASE_URL.replace(/\/api\/?$/, "");
const TOKEN_REFRESH_URL = `${API_ROOT_URL}/api/token/refresh/`;

export function AuthProvider({ children }) {
   const [token, setToken] = useState(localStorage.getItem("access") || null);
   const [user, setUser] = useState(null);
   const [loading, setLoading] = useState(!!localStorage.getItem("access")); // Loading if we have a saved token
   const apiClientRef = useRef(
      axios.create({
         timeout: 30000,
      }),
   );

   const login = (access, refresh) => {
      if (access) {
         localStorage.setItem("access", access);
         setToken(access);
         fetchUser(access);
      }
      if (refresh) {
         localStorage.setItem("refresh", refresh);
      }
   };

   const logout = () => {
      localStorage.removeItem("access");
      localStorage.removeItem("refresh");
      setToken(null);
      setUser(null);
      setLoading(false);
   };

   useEffect(() => {
      const apiClient = apiClientRef.current;
      let isRefreshing = false;
      let pendingRequests = [];

      const requestInterceptor = apiClient.interceptors.request.use((config) => {
         const accessToken = localStorage.getItem("access");
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

            const refreshToken = localStorage.getItem("refresh");
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

               localStorage.setItem("access", newAccessToken);
               localStorage.setItem("refresh", nextRefreshToken);
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

   const authFetch = async (url, options = {}, accessToken = null) => {
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
   };

   const fetchUser = async (accessToken) => {
      try {
         const response = await apiClientRef.current.get(`${API_BASE_URL}/auth/me/`, {
            headers: {
               Authorization: `Bearer ${accessToken}`,
            },
         });
         const data = response.data;
         const normalizedTrustScore = Number(
            data?.trust_breakdown?.trust_score ?? data?.trust_score ?? 0,
         );
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

   const refreshUser = () => {
      const activeToken = token || localStorage.getItem("access");
      if (!activeToken) return Promise.resolve(null);
      return fetchUser(activeToken);
   };

   useEffect(() => {
      const savedToken = localStorage.getItem("access");
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

export function useAuth() {
   return useContext(AuthContext);
}
