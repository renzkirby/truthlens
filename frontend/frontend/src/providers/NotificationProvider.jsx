// src/providers/NotificationProvider.jsx
import { useCallback, useState } from "react";
import NotificationContext from "../context/NotificationContext";

export function NotificationProvider({ children }) {
   const [toasts, setToasts] = useState([]);

   const removeToast = useCallback((id) => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
   }, []);

   const addToast = useCallback((options) => {
      const { type = "info", title = "", message = "", duration = 3000 } = options;

      const id = `toast-${Date.now()}-${Math.random()}`;

      setToasts((prev) => [
         ...prev,
         {
            id,
            type,
            title,
            message,
            duration,
         },
      ]);

      return id;
   }, []);

   return (
      <NotificationContext.Provider value={{ toasts, addToast, removeToast }}>{children}</NotificationContext.Provider>
   );
}
