import { useNotification } from "../context/NotificationContext";
import Icons from "./Icons";
import { useState, useEffect } from "react";
import "./Toast.css";

function Toast() {
   const { toasts, removeToast } = useNotification();
   const [removingToasts, setRemovingToasts] = useState(new Set());

   /**
    * Handle toast removal with animation
    */
   const handleRemoveToast = (id) => {
      // Mark toast as removing to trigger animation
      setRemovingToasts((prev) => new Set(prev).add(id));

      // Actually remove after animation completes (300ms)
      setTimeout(() => {
         removeToast(id);
         setRemovingToasts((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
         });
      }, 300);
   };

   /**
    * Auto-dismiss toasts based on their duration
    */
   useEffect(() => {
      const timers = [];

      toasts.forEach((toast) => {
         if (toast.duration > 0 && !removingToasts.has(toast.id)) {
            const timer = setTimeout(() => {
               handleRemoveToast(toast.id);
            }, toast.duration);

            timers.push(timer);
         }
      });

      return () => {
         timers.forEach((timer) => clearTimeout(timer));
      };
   }, [toasts, removingToasts]);

   const getIcon = (type) => {
      const iconMap = {
         success: "check-circle",
         error: "alert-circle",
         info: "info",
         warning: "alert-triangle",
      };
      return iconMap[type] || "info";
   };

   const getColor = (type) => {
      const colorMap = {
         success: "#10b981",
         error: "#dc2626",
         info: "#0284c7",
         warning: "#f59e0b",
      };
      return colorMap[type] || "#6b7280";
   };

   return (
      <div className="toast-container">
         {toasts.map((toast) => (
            <div
               key={toast.id}
               className={`toast toast-${toast.type} ${
                  removingToasts.has(toast.id) ? "removing" : ""
               }`}>
               <div className="toast-icon">
                  <Icons
                     name={getIcon(toast.type)}
                     size={18}
                     color={getColor(toast.type)}
                  />
               </div>

               <div className="toast-content">
                  {toast.title && <div className="toast-title">{toast.title}</div>}
                  {toast.message && <div className="toast-message">{toast.message}</div>}
               </div>

               <button
                  className="toast-close"
                  onClick={() => handleRemoveToast(toast.id)}
                  aria-label="Close notification">
                  <Icons
                     name="x"
                     size={16}
                     color="#6b7280"
                  />
               </button>
            </div>
         ))}
      </div>
   );
}

export default Toast;
