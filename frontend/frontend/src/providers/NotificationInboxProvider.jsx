import { useCallback, useEffect, useRef, useState } from "react";
import NotificationInboxContext from "../context/NotificationInboxContext";
import { useAuth } from "../hooks/useAuth";
import {
   getNotifications,
   getNotificationUnreadCount,
   markAllNotificationsRead,
   markNotificationRead,
} from "../utils/api";
import { NOTIFICATION_SSE_ENABLED } from "../utils/constants";
import { consumeNotificationStream } from "../utils/notificationStream";

const REALTIME_REFRESH_DELAY_MS = 250;
const REALTIME_RECONNECT_MAX_MS = 30000;

export function NotificationInboxProvider({ children }) {
   const { authFetch, loading: authLoading, token, user } = useAuth();
   const [unreadCount, setUnreadCount] = useState(0);
   const [unreadCountLoading, setUnreadCountLoading] = useState(false);
   const [unreadCountError, setUnreadCountError] = useState(null);
   const [recentNotifications, setRecentNotifications] = useState([]);
   const [recentNotificationsLoading, setRecentNotificationsLoading] = useState(false);
   const [recentNotificationsError, setRecentNotificationsError] = useState(null);
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

   const refreshRecentNotifications = useCallback(async () => {
      if (!authReady || sessionRef.current !== token) {
         setRecentNotifications([]);
         setRecentNotificationsLoading(false);
         setRecentNotificationsError(null);
         return [];
      }

      const session = token;
      setRecentNotificationsLoading(true);
      setRecentNotificationsError(null);
      try {
         const page = await getNotifications(authFetch, { filter: "all", pageSize: 8 });
         const rows = Array.isArray(page?.results) ? page.results : [];
         if (sessionRef.current === session) {
            setRecentNotifications(rows);
         }
         return rows;
      } catch (error) {
         if (sessionRef.current === session) {
            setRecentNotificationsError(error);
         }
         throw error;
      } finally {
         if (sessionRef.current === session) {
            setRecentNotificationsLoading(false);
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
         setRecentNotifications([]);
         setRecentNotificationsLoading(false);
         setRecentNotificationsError(null);
         return;
      }

      refreshUnreadCount().catch(() => {});
   }, [authReady, refreshUnreadCount, token]);

   useEffect(() => {
      if (!NOTIFICATION_SSE_ENABLED || !authReady) return undefined;

      let disposed = false;
      let controller = null;
      let reconnectTimer = null;
      let refreshTimer = null;
      let reconnectAttempt = 0;

      const reconcileInbox = () => {
         if (disposed || refreshTimer !== null) return;
         refreshTimer = window.setTimeout(() => {
            refreshTimer = null;
            Promise.allSettled([
               refreshUnreadCount(),
               refreshRecentNotifications(),
            ]);
         }, REALTIME_REFRESH_DELAY_MS);
      };

      const scheduleReconnect = (connect) => {
         if (disposed) return;
         const delay = Math.min(
            1000 * (2 ** reconnectAttempt),
            REALTIME_RECONNECT_MAX_MS,
         );
         reconnectAttempt += 1;
         reconnectTimer = window.setTimeout(connect, delay);
      };

      const connect = async () => {
         if (disposed) return;
         controller?.abort();
         controller = new AbortController();
         try {
            await consumeNotificationStream({
               signal: controller.signal,
               onConnected: () => { reconnectAttempt = 0; },
               onInboxChanged: reconcileInbox,
            });
            if (!disposed) {
               reconcileInbox();
               scheduleReconnect(connect);
            }
         } catch (error) {
            if (!disposed && error?.name !== "AbortError") {
               reconcileInbox();
               scheduleReconnect(connect);
            }
         }
      };

      connect();
      return () => {
         disposed = true;
         controller?.abort();
         if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
         if (refreshTimer !== null) window.clearTimeout(refreshTimer);
      };
   }, [
      authReady,
      refreshRecentNotifications,
      refreshUnreadCount,
      token,
   ]);

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
                  setRecentNotifications((rows) => rows.map((item) =>
                     item.id === notificationId
                        ? { ...item, ...notification, is_read: true }
                        : item,
                  ));
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
         setRecentNotifications((rows) => rows.map((item) => ({
            ...item,
            is_read: true,
            read_at: item.read_at || new Date().toISOString(),
         })));
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
            recentNotifications,
            recentNotificationsLoading,
            recentNotificationsError,
            refreshRecentNotifications,
            markRead,
            markAllRead,
         }}
      >
         {children}
      </NotificationInboxContext.Provider>
   );
}
