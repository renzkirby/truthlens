import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Icons from "../components/Icons";
import Button from "../components/ui/Button";
import { useAuth } from "../hooks/useAuth";
import { useNotificationInbox } from "../hooks/useNotificationInbox";
import { getNotifications, resolveApiEndpoint } from "../utils/api";
import "./NotificationPage.css";

const timestampFormatter = new Intl.DateTimeFormat(undefined, {
   dateStyle: "medium",
   timeStyle: "short",
});

function formatTimestamp(value) {
   const timestamp = new Date(value);
   return Number.isNaN(timestamp.getTime()) ? "Time unavailable" : timestampFormatter.format(timestamp);
}

function cursorFromNextPage(nextPage) {
   if (!nextPage) return null;

   try {
      const expected = new URL(resolveApiEndpoint("NOTIFICATIONS"));
      const candidate = new URL(nextPage, expected);
      if (candidate.origin !== expected.origin || candidate.pathname !== expected.pathname) {
         return null;
      }
      return candidate.searchParams.get("cursor");
   } catch {
      return null;
   }
}

function safeInternalDestination(destination) {
   if (typeof destination !== "string" || !destination.startsWith("/") || destination.startsWith("//")) {
      return null;
   }

   try {
      const candidate = new URL(destination, window.location.origin);
      if (candidate.origin !== window.location.origin) return null;
      return `${candidate.pathname}${candidate.search}${candidate.hash}`;
   } catch {
      return null;
   }
}

function mergeNotifications(current, incoming) {
   const rows = new Map(current.map((notification) => [notification.id, notification]));
   incoming.forEach((notification) => rows.set(notification.id, notification));
   return Array.from(rows.values());
}

function NotificationItem({ notification, pending, onActivate }) {
   const destination = safeInternalDestination(notification.destination);
   const actionable = !notification.is_read || Boolean(destination);
   const content = (
      <>
         <span className="tl-notification-item__indicator" aria-hidden="true" />
         <span className="tl-notification-item__icon" aria-hidden="true">
            <Icons name="bell" size={18} />
         </span>
         <span className="tl-notification-item__content">
            <span className="tl-notification-item__heading">
               <span className="tl-notification-item__title">{notification.title}</span>
               {!notification.is_read && <span className="tl-notification-item__unread-label">Unread</span>}
            </span>
            <span className="tl-notification-item__message">{notification.message}</span>
            <span className="tl-notification-item__meta">
               <span>{notification.category}</span>
               <span aria-hidden="true">·</span>
               <time dateTime={notification.created_at}>{formatTimestamp(notification.created_at)}</time>
            </span>
         </span>
         {destination && (
            <span className="tl-notification-item__arrow" aria-hidden="true">
               <Icons name="chevron-right" size={18} />
            </span>
         )}
      </>
   );

   return (
      <li className={`tl-notification-item ${notification.is_read ? "is-read" : "is-unread"}`}>
         {actionable ? (
            <button
               type="button"
               className="tl-notification-item__action"
               onClick={() => onActivate(notification, destination)}
               disabled={pending}
               aria-busy={pending || undefined}
            >
               {content}
            </button>
         ) : (
            <div className="tl-notification-item__static">{content}</div>
         )}
      </li>
   );
}

function NotificationPage() {
   const { authFetch } = useAuth();
   const { unreadCount, markRead, markAllRead } = useNotificationInbox();
   const navigate = useNavigate();
   const [filter, setFilter] = useState("all");
   const [notifications, setNotifications] = useState([]);
   const [nextCursor, setNextCursor] = useState(null);
   const [initialLoading, setInitialLoading] = useState(true);
   const [loadingMore, setLoadingMore] = useState(false);
   const [markingAll, setMarkingAll] = useState(false);
   const [pendingIds, setPendingIds] = useState(() => new Set());
   const [error, setError] = useState(null);
   const [actionError, setActionError] = useState(null);
   const requestIdRef = useRef(0);

   const loadNotifications = useCallback(
      async ({ cursor = null, append = false } = {}) => {
         const requestId = ++requestIdRef.current;
         if (append) {
            setLoadingMore(true);
         } else {
            setInitialLoading(true);
            setNotifications([]);
            setNextCursor(null);
         }
         setError(null);

         try {
            const page = await getNotifications(authFetch, { filter, cursor });
            if (requestId !== requestIdRef.current) return;
            const rows = Array.isArray(page?.results) ? page.results : [];
            setNotifications((current) => (append ? mergeNotifications(current, rows) : rows));
            setNextCursor(cursorFromNextPage(page?.next));
         } catch (requestError) {
            if (requestId === requestIdRef.current) {
               setError(requestError);
            }
         } finally {
            if (requestId === requestIdRef.current) {
               setInitialLoading(false);
               setLoadingMore(false);
            }
         }
      },
      [authFetch, filter],
   );

   useEffect(() => {
      loadNotifications();
      return () => {
         requestIdRef.current += 1;
      };
   }, [loadNotifications]);

   const handleActivate = async (notification, destination) => {
      setActionError(null);
      if (!notification.is_read) {
         setPendingIds((current) => new Set(current).add(notification.id));
         try {
            const updated = await markRead(notification.id, { wasRead: notification.is_read });
            setNotifications((current) => {
               if (filter === "unread") {
                  return current.filter((item) => item.id !== notification.id);
               }
               return current.map((item) =>
                  item.id === notification.id ? { ...item, ...updated, is_read: true } : item,
               );
            });
         } catch (readError) {
            setActionError(readError);
            return;
         } finally {
            setPendingIds((current) => {
               const next = new Set(current);
               next.delete(notification.id);
               return next;
            });
         }
      }

      if (destination) {
         navigate(destination);
      }
   };

   const handleMarkAllRead = async () => {
      setMarkingAll(true);
      setActionError(null);
      try {
         await markAllRead();
         setNotifications((current) =>
            filter === "unread" ? [] : current.map((item) => ({ ...item, is_read: true })),
         );
         if (filter === "unread") {
            setNextCursor(null);
         }
      } catch (markAllError) {
         setActionError(markAllError);
      } finally {
         setMarkingAll(false);
      }
   };

   const emptyMessage =
      filter === "unread"
         ? "You have no unread notifications."
         : "Your notification inbox is empty.";

   return (
      <main className="tl-notifications-page">
         <div className="tl-notifications-page__content">
            <header className="tl-notifications-page__header">
               <div>
                  <h1 className="tl-notifications-page__title">Notifications</h1>
                  <p className="tl-notifications-page__summary" aria-live="polite">
                     {unreadCount === 1 ? "1 unread notification" : `${unreadCount} unread notifications`}
                  </p>
               </div>
               {unreadCount > 0 && (
                  <Button
                     variant="secondary"
                     density="compact"
                     loading={markingAll}
                     loadingLabel="Marking all…"
                     onClick={handleMarkAllRead}
                  >
                     Mark all as read
                  </Button>
               )}
            </header>

            <div className="tl-notifications-page__filters" aria-label="Notification filters">
               {[
                  ["all", "All"],
                  ["unread", "Unread"],
               ].map(([value, label]) => (
                  <button
                     key={value}
                     type="button"
                     className={`tl-notifications-page__filter ${filter === value ? "active" : ""}`}
                     onClick={() => setFilter(value)}
                     aria-pressed={filter === value}
                  >
                     {label}
                  </button>
               ))}
            </div>

            {actionError && (
               <div className="tl-notifications-page__notice" role="alert">
                  <span>We couldn’t update that notification. Please try again.</span>
                  <button type="button" onClick={() => setActionError(null)} aria-label="Dismiss error">
                     <Icons name="x" size={16} />
                  </button>
               </div>
            )}

            {initialLoading ? (
               <section className="tl-notifications-page__state" aria-live="polite" aria-busy="true">
                  <Icons name="loader" size={24} className="tl-notifications-page__spinner" />
                  <p>Loading notifications…</p>
               </section>
            ) : error && notifications.length === 0 ? (
               <section className="tl-notifications-page__state" role="alert">
                  <Icons name="alert-circle" size={28} />
                  <h2>Notifications couldn’t be loaded</h2>
                  <p>Please check your connection and try again.</p>
                  <Button variant="secondary" density="compact" onClick={() => loadNotifications()}>
                     Retry
                  </Button>
               </section>
            ) : notifications.length === 0 ? (
               <section className="tl-notifications-page__state" aria-live="polite">
                  <Icons name={filter === "unread" ? "check-circle" : "bell"} size={28} />
                  <h2>
                     {filter === "unread"
                        ? nextCursor
                           ? "More unread notifications are available"
                           : "You’re all caught up"
                        : "No notifications yet"}
                  </h2>
                  <p>
                     {filter === "unread" && nextCursor
                        ? "Load the next page to continue reviewing your inbox."
                        : emptyMessage}
                  </p>
                  {nextCursor && (
                     <Button
                        variant="secondary"
                        density="compact"
                        loading={loadingMore}
                        loadingLabel="Loading…"
                        onClick={() => loadNotifications({ cursor: nextCursor, append: true })}
                     >
                        Load more
                     </Button>
                  )}
               </section>
            ) : (
               <>
                  <ul
                     className="tl-notifications-list"
                     aria-label={`${filter === "unread" ? "Unread" : "All"} notifications`}
                  >
                     {notifications.map((notification) => (
                        <NotificationItem
                           key={notification.id}
                           notification={notification}
                           pending={pendingIds.has(notification.id)}
                           onActivate={handleActivate}
                        />
                     ))}
                  </ul>

                  {error && (
                     <div className="tl-notifications-page__load-error" role="alert">
                        <span>More notifications couldn’t be loaded.</span>
                        <button
                           type="button"
                           onClick={() => loadNotifications({ cursor: nextCursor, append: true })}
                        >
                           Try again
                        </button>
                     </div>
                  )}

                  {nextCursor && !error && (
                     <div className="tl-notifications-page__load-more">
                        <Button
                           variant="secondary"
                           loading={loadingMore}
                           loadingLabel="Loading…"
                           onClick={() => loadNotifications({ cursor: nextCursor, append: true })}
                        >
                           Load more
                        </Button>
                     </div>
                  )}
               </>
            )}
         </div>
      </main>
   );
}

export default NotificationPage;
