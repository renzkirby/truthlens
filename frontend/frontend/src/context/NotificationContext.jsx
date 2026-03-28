import { createContext, useContext, useState, useCallback } from "react";

const NotificationContext = createContext(null);

export function NotificationProvider({ children }) {
   const [toasts, setToasts] = useState([]);

   /**
    * Remove a toast notification
    */
   const removeToast = useCallback((id) => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
   }, []);

   /**
    * Add a toast notification
    * @param {Object} options - Toast configuration
    * @param {string} options.type - 'success', 'error', 'info', 'warning'
    * @param {string} options.title - Toast title/main message
    * @param {string} options.message - Optional detailed message
    * @param {number} options.duration - Auto-close delay in ms (0 = never auto-close)
    * @returns {string} Toast ID for manual removal
    */
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
            duration, // Store duration in toast so Toast component can handle auto-dismiss
         },
      ]);

      return id;
   }, []);

   const value = {
      toasts,
      addToast,
      removeToast,
   };

   return <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>;
}

export function useNotification() {
   const context = useContext(NotificationContext);
   if (!context) {
      throw new Error("useNotification must be used within NotificationProvider");
   }
   return context;
}
