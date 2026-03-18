import { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import Icons from "./Icons.jsx";
import "./NotificationPopup.css";

// ─────────────────────────────────────────────────────────────────────────────
// NOTIFICATION SYSTEM — IMPLEMENTATION NOTES
//
// To make this component fully functional, the following needs to be built:
//
// 1. BACKEND — New Notification model in models.py:
//    class Notification(models.Model):
//        class NotificationType(models.TextChoices):
//            NEW_EVIDENCE  = "NEW_EVIDENCE",  "New Evidence Submitted"
//            NEW_COMMENT   = "NEW_COMMENT",   "New Comment"
//            THREAD_CLOSED = "THREAD_CLOSED", "Thread Closed"
//            CLAIM_VERIFIED = "CLAIM_VERIFIED", "Claim Verified"
//
//        recipient  = models.ForeignKey(User, on_delete=CASCADE, related_name="notifications")
//        type       = models.CharField(max_length=20, choices=NotificationType.choices)
//        message    = models.TextField()
//        is_read    = models.BooleanField(default=False)
//        link       = models.CharField(max_length=500, blank=True)  # e.g. /thread?thread_id=xxx
//        created_at = models.DateTimeField(auto_now_add=True)
//
// 2. BACKEND — Django signals in a new signals.py file:
//    from django.db.models.signals import post_save
//    from django.dispatch import receiver
//
//    @receiver(post_save, sender=EvidenceSubmission)
//    def notify_thread_author_on_evidence(sender, instance, created, **kwargs):
//        if created:
//            Notification.objects.create(
//                recipient=instance.thread.author,
//                type="NEW_EVIDENCE",
//                message=f"@{instance.contributor.username} submitted evidence on your thread.",
//                link=f"/thread?thread_id={instance.thread.id}"
//            )
//
//    @receiver(post_save, sender=ThreadComment)
//    def notify_thread_author_on_comment(sender, instance, created, **kwargs):
//        if created:
//            Notification.objects.create(
//                recipient=instance.thread.author,
//                type="NEW_COMMENT",
//                message=f"@{instance.commenter.username} commented on your thread.",
//                link=f"/thread?thread_id={instance.thread.id}"
//            )
//
//    Remember to register signals in apps.py:
//    def ready(self):
//        import api.signals
//
// 3. BACKEND — New endpoints in urls.py:
//    path("notifications/",            views.NotificationListView.as_view()),
//    path("notifications/mark-read/",  views.mark_all_read),
//    path("notifications/<id>/read/",  views.mark_one_read),
//
// 4. FRONTEND — Replace the empty notifications array below with:
//    const { authFetch } = useAuth();
//    useEffect(() => {
//        authFetch("http://localhost:8000/api/notifications/")
//            .then(data => setNotifications(data || []));
//    }, []);
//
// 5. FRONTEND — Mark as read when notification is clicked:
//    authFetch(`http://localhost:8000/api/notifications/${notif.id}/read/`, {
//        method: "POST"
//    });
// ─────────────────────────────────────────────────────────────────────────────

// ── Icon map for notification types ──────────────────────────────────────────
// TODO: Use these when rendering real notifications
const NOTIF_ICONS = {
   NEW_EVIDENCE:   "paperclip",
   NEW_COMMENT:    "message-square",
   THREAD_CLOSED:  "check-circle",
   CLAIM_VERIFIED: "badge-check",
};

// ── Relative time helper ──────────────────────────────────────────────────────
function timeAgo(dateStr) {
   if (!dateStr) return "—";
   const diff  = Date.now() - new Date(dateStr).getTime();
   const mins  = Math.floor(diff / 60000);
   const hours = Math.floor(diff / 3600000);
   const days  = Math.floor(diff / 86400000);
   if (mins  < 1)  return "Just now";
   if (mins  < 60) return `${mins}m ago`;
   if (hours < 24) return `${hours}h ago`;
   if (days  < 7)  return `${days}d ago`;
   return `${Math.floor(days / 7)}w ago`;
}

// ── Main Component ────────────────────────────────────────────────────────────
function NotificationPopup() {
   const [isOpen, setIsOpen]               = useState(false);
   const [notifications, setNotifications] = useState([]);
   // TODO: Replace empty array above with authFetch call to /api/notifications/

   const containerRef = useRef(null);
   const navigate     = useNavigate();
   const location     = useLocation();

   // Unread count — drives the badge on the bell icon
   // TODO: This will work automatically once real notifications are fetched
   const unreadCount = notifications.filter((n) => !n.is_read).length;

   // ── Close popup when clicking outside ────────────────────────────────────
   useEffect(() => {
      function handleClickOutside(e) {
         if (containerRef.current && !containerRef.current.contains(e.target)) {
            setIsOpen(false);
         }
      }
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
   }, []);

   // ── Close popup on Escape key ─────────────────────────────────────────────
   useEffect(() => {
      function handleEscape(e) {
         if (e.key === "Escape") setIsOpen(false);
      }
      document.addEventListener("keydown", handleEscape);
      return () => document.removeEventListener("keydown", handleEscape);
   }, []);

   // ── Close popup on route change ───────────────────────────────────────────
   useEffect(() => {
      setIsOpen(false);
   }, [location.pathname]);

   // ── Mark all as read ──────────────────────────────────────────────────────
   const handleMarkAllRead = async () => {
      // TODO: Replace with real API call:
      // await authFetch("http://localhost:8000/api/notifications/mark-read/", {
      //    method: "POST"
      // });
      // setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      console.log("TODO: POST /api/notifications/mark-read/");
   };

   // ── Mark one as read and navigate ─────────────────────────────────────────
   const handleNotifClick = async (notif) => {
      // TODO: Replace with real API call:
      // await authFetch(`http://localhost:8000/api/notifications/${notif.id}/read/`, {
      //    method: "POST"
      // });
      // setNotifications((prev) =>
      //    prev.map((n) => n.id === notif.id ? { ...n, is_read: true } : n)
      // );
      if (notif.link) navigate(notif.link);
      setIsOpen(false);
   };

   return (
      <div className="notif-container" ref={containerRef}>

         {/* ── Bell button ── */}
         <button
            className={`nav-icon-btn ${isOpen ? "open" : ""}`}
            onClick={() => setIsOpen((v) => !v)}
            aria-label="Notifications"
         >
            <Icons name="bell" size={20} color="#9ca3af" />

            {/* Unread badge — shows when there are unread notifications
                TODO: Uncomment when real notifications are implemented */}
            {/* {unreadCount > 0 && (
               <span className="notif-badge">
                  {unreadCount > 9 ? "9+" : unreadCount}
               </span>
            )} */}
         </button>

         {/* ── Popup panel ── */}
         {isOpen && (
            <div className="notif-popup" role="dialog" aria-label="Notifications">

               {/* Header */}
               <div className="notif-popup-header">
                  <span className="notif-popup-title">
                     Notifications
                     {unreadCount > 0 && (
                        <span className="notif-header-count">{unreadCount}</span>
                     )}
                  </span>
                  <button
                     className="notif-mark-all-btn"
                     onClick={handleMarkAllRead}
                     disabled={unreadCount === 0}
                  >
                     Mark all as read
                  </button>
               </div>

               {/* Notification list */}
               <div className="notif-list">
                  {notifications.length === 0 ? (

                     // ── Empty state ───────────────────────────────────────
                     <div className="notif-empty-state">
                        <Icons name="bell-off" size={28} color="#9ca3af" />
                        <p className="notif-empty-title">No notifications yet</p>
                        <p className="notif-empty-subtitle">
                           You'll be notified when someone comments on your
                           thread, submits evidence, or your claim gets verified.
                        </p>
                     </div>

                  ) : (

                     // ── Real notification items ───────────────────────────
                     // TODO: This renders when real notifications are fetched.
                     // Each item shows icon, message, timestamp, and unread dot.
                     notifications.map((notif) => (
                        <div
                           key={notif.id}
                           className={`notif-item ${!notif.is_read ? "unread" : ""}`}
                           onClick={() => handleNotifClick(notif)}
                        >
                           <div className="notif-item-icon">
                              <Icons
                                 name={NOTIF_ICONS[notif.type] || "bell"}
                                 size={14}
                              />
                           </div>
                           <div className="notif-item-body">
                              <p className="notif-item-message">{notif.message}</p>
                              <span className="notif-item-time">
                                 {timeAgo(notif.created_at)}
                              </span>
                           </div>
                           {!notif.is_read && (
                              <span className="notif-unread-dot" />
                           )}
                        </div>
                     ))
                  )}
               </div>

               {/* Footer */}
               <div className="notif-popup-footer">
                  <Link
                     to="/notifications"
                     className="notif-see-all-link"
                     onClick={() => setIsOpen(false)}
                  >
                     See all notifications
                  </Link>
               </div>

            </div>
         )}
      </div>
   );
}

export default NotificationPopup;