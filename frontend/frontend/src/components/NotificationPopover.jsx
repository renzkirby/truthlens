import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useNotificationInbox } from "../hooks/useNotificationInbox";
import Icons from "./Icons.jsx";
import "./NotificationPopover.css";

const PANEL_ID = "tl-notification-popover";
const relativeTime = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

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

function formatRelativeTimestamp(value) {
   const timestamp = new Date(value);
   if (Number.isNaN(timestamp.getTime())) return "Time unavailable";
   const seconds = Math.round((timestamp.getTime() - Date.now()) / 1000);
   if (Math.abs(seconds) < 60) return relativeTime.format(seconds, "second");
   const minutes = Math.round(seconds / 60);
   if (Math.abs(minutes) < 60) return relativeTime.format(minutes, "minute");
   const hours = Math.round(minutes / 60);
   if (Math.abs(hours) < 24) return relativeTime.format(hours, "hour");
   const days = Math.round(hours / 24);
   if (Math.abs(days) < 30) return relativeTime.format(days, "day");
   const months = Math.round(days / 30);
   if (Math.abs(months) < 12) return relativeTime.format(months, "month");
   return relativeTime.format(Math.round(months / 12), "year");
}

function NotificationAvatar({ actor }) {
   const initial = actor?.username?.trim()?.[0]?.toUpperCase();
   if (!actor) {
      return <span className="tl-notification-popover__system-icon"><Icons name="bell" size={18} /></span>;
   }
   return (
      <span className="tl-notification-popover__avatar" aria-hidden="true">
         <span>{initial || <Icons name="user" size={17} />}</span>
         {actor.avatar_url && (
            <img
               src={actor.avatar_url}
               alt=""
               referrerPolicy="no-referrer"
               onError={(event) => { event.currentTarget.hidden = true; }}
            />
         )}
      </span>
   );
}

export default function NotificationPopover({ open, onOpenChange, unreadCount, active }) {
   const {
      recentNotifications,
      recentNotificationsLoading,
      recentNotificationsError,
      refreshRecentNotifications,
      refreshUnreadCount,
      markRead,
      markAllRead,
   } = useNotificationInbox();
   const navigate = useNavigate();
   const wrapperRef = useRef(null);
   const triggerRef = useRef(null);
   const [pendingId, setPendingId] = useState(null);
   const [markingAll, setMarkingAll] = useState(false);
   const [actionError, setActionError] = useState(null);

   const refresh = useCallback(() => {
      setActionError(null);
      Promise.allSettled([refreshRecentNotifications(), refreshUnreadCount()]);
   }, [refreshRecentNotifications, refreshUnreadCount]);

   useEffect(() => {
      if (!open) return undefined;
      refresh();
      const handlePointerDown = (event) => {
         if (!wrapperRef.current?.contains(event.target)) onOpenChange(false);
      };
      const handleKeyDown = (event) => {
         if (event.key === "Escape") {
            onOpenChange(false);
            triggerRef.current?.focus();
         }
      };
      document.addEventListener("mousedown", handlePointerDown);
      document.addEventListener("keydown", handleKeyDown);
      return () => {
         document.removeEventListener("mousedown", handlePointerDown);
         document.removeEventListener("keydown", handleKeyDown);
      };
   }, [open, onOpenChange, refresh]);

   const activate = async (notification) => {
      const destination = safeInternalDestination(notification.destination);
      setActionError(null);
      setPendingId(notification.id);
      try {
         if (!notification.is_read) {
            await markRead(notification.id, { wasRead: false });
         }
         onOpenChange(false);
         if (destination) navigate(destination);
      } catch (error) {
         setActionError(error);
      } finally {
         setPendingId(null);
      }
   };

   const handleMarkAll = async () => {
      setMarkingAll(true);
      setActionError(null);
      try {
         await markAllRead();
      } catch (error) {
         setActionError(error);
      } finally {
         setMarkingAll(false);
      }
   };

   const label = unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications";

   return (
      <div className="tl-notification-popover" ref={wrapperRef}>
         <button
            ref={triggerRef}
            type="button"
            className={`tl-app-nav__notifications ${active || open ? "active" : ""}`}
            aria-label={label}
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-controls={PANEL_ID}
            onClick={() => onOpenChange(!open)}
         >
            <Icons name="bell" size={20} />
            {unreadCount > 0 && (
               <span className="tl-app-nav__notification-badge" aria-hidden="true">
                  {unreadCount > 99 ? "99+" : unreadCount}
               </span>
            )}
         </button>

         {open && (
            <section
               id={PANEL_ID}
               className="tl-notification-popover__panel"
               role="dialog"
               aria-label="Recent notifications"
            >
               <header className="tl-notification-popover__header">
                  <h2>Notifications</h2>
                  {unreadCount > 0 && (
                     <button type="button" onClick={handleMarkAll} disabled={markingAll}>
                        {markingAll ? "Marking…" : "Mark all as read"}
                     </button>
                  )}
               </header>

               {actionError && <p className="tl-notification-popover__notice" role="alert">We couldn’t update notifications. Please try again.</p>}

               <div className="tl-notification-popover__body">
                  {recentNotificationsLoading && recentNotifications.length === 0 ? (
                     <div className="tl-notification-popover__state" aria-live="polite" aria-busy="true">
                        <Icons name="loader" className="tl-notification-popover__spinner" />
                        <span>Loading notifications…</span>
                     </div>
                  ) : recentNotificationsError && recentNotifications.length === 0 ? (
                     <div className="tl-notification-popover__state" role="alert">
                        <Icons name="alert-circle" />
                        <span>Notifications couldn’t be loaded.</span>
                        <button type="button" onClick={refresh}>Retry</button>
                     </div>
                  ) : recentNotifications.length === 0 ? (
                     <div className="tl-notification-popover__state" aria-live="polite">
                        <Icons name="bell-off" />
                        <span>No notifications yet.</span>
                     </div>
                  ) : (
                     <ul className="tl-notification-popover__list">
                        {recentNotifications.map((notification) => {
                           const actionable = !notification.is_read || safeInternalDestination(notification.destination);
                           const content = (
                              <>
                                 <NotificationAvatar actor={notification.actor} />
                                 <span className="tl-notification-popover__copy">
                                    <strong>{notification.title}</strong>
                                    <span>{notification.message}</span>
                                    <time dateTime={notification.created_at}>{formatRelativeTimestamp(notification.created_at)}</time>
                                 </span>
                                 {!notification.is_read && <span className="tl-notification-popover__unread" aria-label="Unread" />}
                              </>
                           );
                           return (
                              <li key={notification.id} className={notification.is_read ? "is-read" : "is-unread"}>
                                 {actionable ? (
                                    <button type="button" onClick={() => activate(notification)} disabled={pendingId === notification.id}>
                                       {content}
                                    </button>
                                 ) : <div>{content}</div>}
                              </li>
                           );
                        })}
                     </ul>
                  )}
               </div>

               <button
                  type="button"
                  className="tl-notification-popover__footer"
                  onClick={() => { onOpenChange(false); navigate("/notifications"); }}
               >
                  View all notifications
               </button>
            </section>
         )}
      </div>
   );
}
