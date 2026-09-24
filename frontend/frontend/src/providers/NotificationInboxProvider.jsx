import { useCallback, useEffect, useRef, useState } from "react";
import NotificationInboxContext from "../context/NotificationInboxContext";
import { useAuth } from "../hooks/useAuth";
import {
   getNotificationUnreadCount,
   markAllNotificationsRead,
   markNotificationRead,
} from "../utils/api";

export function NotificationInboxProvider({ children }) {
   const { authFetch, loading: authLoading, token, user } = useAuth();
   const [unreadCount, setUnreadCount] = useState(0);
   const [unreadCountLoading, setUnreadCountLoading] = useState(false);
   const [unreadCountError, setUnreadCountError] = useState(null);
   const sessionRef = useRef(null);
   const markReadRequestsRef = useRef(new Map());
   const authReady = !authLoading && Boolean(token && user);

   const refreshUnreadCount = useCallback(async () => {
      if (!authReady || sessionRef.current !== token) {
         setUnreadCount(0);
         setUnreadCountLoading(false);
         setUnreadCountError(null);
         return 0;
      }

      const session = token;
      setUnreadCountLoading(true);
      setUnreadCountError(null);

      try {
         const data = await getNotificationUnreadCount(authFetch);
         const nextCount = Math.max(0, Number(data?.unread_count) || 0);
         if (sessionRef.current === session) {
            setUnreadCount(nextCount);
         }
         return nextCount;
      } catch (error) {
         if (sessionRef.current === session) {
            setUnreadCountError(error);
         }
         throw error;
      } finally {
         if (sessionRef.current === session) {
            setUnreadCountLoading(false);
         }
      }
   }, [authFetch, authReady, token]);

   useEffect(() => {
      sessionRef.current = authReady ? token : null;
      markReadRequestsRef.current.clear();

      if (!authReady) {
         setUnreadCount(0);
         setUnreadCountLoading(false);
         setUnreadCountError(null);
         return;
      }

      refreshUnreadCount().catch(() => {});
   }, [authReady, refreshUnreadCount, token]);

   const markRead = useCallback(
      (notificationId, { wasRead = false } = {}) => {
         if (wasRead) {
            return Promise.resolve(null);
         }
         if (!authReady) {
            return Promise.reject(new Error("Authentication is required."));
         }

         const existingRequest = markReadRequestsRef.current.get(notificationId);
         if (existingRequest) {
            return existingRequest;
         }

         const session = token;
         const request = markNotificationRead(authFetch, notificationId)
            .then((notification) => {
               if (sessionRef.current === session) {
                  setUnreadCount((count) => Math.max(0, count - 1));
                  refreshUnreadCount().catch(() => {});
               }
               return notification;
            })
            .finally(() => {
               markReadRequestsRef.current.delete(notificationId);
            });

         markReadRequestsRef.current.set(notificationId, request);
         return request;
      },
      [authFetch, authReady, refreshUnreadCount, token],
   );

   const markAllRead = useCallback(async () => {
      if (!authReady) {
         throw new Error("Authentication is required.");
      }
      const session = token;
      const result = await markAllNotificationsRead(authFetch);
      if (sessionRef.current === session) {
         setUnreadCount(0);
         setUnreadCountError(null);
      }
      return result;
   }, [authFetch, authReady, token]);

   return (
      <NotificationInboxContext.Provider
         value={{
            unreadCount,
            unreadCountLoading,
            unreadCountError,
            refreshUnreadCount,
            markRead,
            markAllRead,
         }}
      >
         {children}
      </NotificationInboxContext.Provider>
   );
}
