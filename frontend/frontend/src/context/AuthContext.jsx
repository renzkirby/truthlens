import { createContext, useContext, useEffect, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
   const [token, setToken] = useState(localStorage.getItem("access") || null);
   const [user, setUser] = useState(null);

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
         const refreshResponse = await fetch("http://localhost:8000/api/auth/refresh/", {
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
      const response = await fetch("http://localhost:8000/api/auth/me/", {
         headers: { Authorization: `Bearer ${accessToken}` },
      });
      const data = await response.json();
      setUser(data);
   };

   useEffect(() => {
      const savedToken = localStorage.getItem("access");
      if (savedToken) {
         fetchUser(savedToken);
      }
   }, []);

   return (
      <AuthContext.Provider value={{ token, login, logout, authFetch, user }}>
         {children}
      </AuthContext.Provider>
   );
}

export function useAuth() {
   return useContext(AuthContext);
}
