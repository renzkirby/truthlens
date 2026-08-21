import { useContext } from "react";
import NotificationContext from "../context/NotificationContext";

export function useNotification() {
   const context = useContext(NotificationContext);

   if (!context) {
      throw new Error("useNotification must be used within NotificationProvider");
   }

   return context;
}
