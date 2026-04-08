import { createContext, useContext, useEffect, useState } from "react";
import { API_BASE_URL } from "../utils/constants";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
   const [token, setToken] = useState(localStorage.getItem("access") || null);
   const [user, setUser] = useState(null);
   const [loading, setLoading] = useState(!!localStorage.getItem("access")); // Loading if we have a saved token

   const login = (access, refresh) => {
      localStorage.setItem("access", access);
      localStorage.setItem("refresh", refresh);
      setToken(access);
      fetchUser(access);
   };

   const logout = () => {
      localStorage.removeItem("access");
      localStorage.removeItem("refresh");
      setToken(null);
      setUser(null);
      setLoading(false);
   };

   const authFetch = async (url, options = {}, accessToken = null) => {
      const currentToken = accessToken || token;

      const response = await fetch(url, {
         method: options.method,
         headers: {
            ...options.headers,
            Authorization: `Bearer ${currentToken}`,
         },
         body: options.body,
      });

      let data = null;
      if (response.status !== 204) {
         const contentType = response.headers.get("content-type") || "";
         if (contentType.includes("application/json")) {
            data = await response.json();
         } else {
            const text = await response.text();
            data = text ? { detail: text } : null;
         }
      }

      if (response.status == 401) {
         const refreshResponse = await fetch(`${VITE_API_BASE_URL}/auth/refresh/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh: localStorage.getItem("refresh") }),
         });

         const refreshToken = await refreshResponse.json();

         if (refreshResponse.ok) {
            login(refreshToken.access, localStorage.getItem("refresh"));
            return authFetch(url, options, refreshToken.access);
         } else {
            logout();
            throw new Error("Session expired");
         }
      }

      if (!response.ok) {
         throw new Error(data?.detail || "Request failed");
      }

      return data;
   };

   const fetchUser = async (accessToken) => {
      try {
         const response = await fetch(`${VITE_API_BASE_URL}/auth/me/`, {
            headers: { Authorization: `Bearer ${accessToken}` },
         });
         const data = await response.json();
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
