import { createContext, useContext, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
   const [token, setToken] = useState(localStorage.getItem("access") || null);

   const login = (access, refresh) => {
      localStorage.setItem("access", access);
      localStorage.setItem("refresh", refresh);
      setToken(access);
   };

   const logout = () => {
      localStorage.removeItem("access");
      localStorage.removeItem("refresh");
      setToken(null);
   };

   const authFetch = async (url, options = {}) => {
      const response = await fetch(url, {
         method: options.method,
         headers: {
            ...options.headers,
            Authorization: `Bearer ${token}`,
         },
         body: options.body,
      });

      const data = await response.json();

      if (response.status == 401) {
         const refreshResponse = await fetch("http://localhost:8000/api/auth/refresh/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh: localStorage.getItem("refresh") }),
         });

         const refreshToken = await refreshResponse.json();

         if (refreshResponse.ok) {
            login(refreshToken.access, localStorage.getItem("refresh"));
            return authFetch(url, options);
         } else {
            logout();
         }
      } else {
         return data;
      }
   };

   return (
      <AuthContext.Provider value={{ token, login, logout, authFetch }}>
         {children}
      </AuthContext.Provider>
   );
}

export function useAuth() {
   return useContext(AuthContext);
}
