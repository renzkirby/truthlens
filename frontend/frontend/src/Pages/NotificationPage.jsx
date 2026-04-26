import { useMemo, useState } from "react";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import "./NotificationPage.css";

const NotificationSkeleton = () => {
   return (
      <div className="notifications-list box-panel">
         {[1, 2, 3, 4].map((i) => (
            <article key={i} className="notification-item is-unread">
               <div className="notification-item-icon" style={{ background: "transparent", border: "none" }}>
                  <div className="skeleton-box" style={{ width: "32px", height: "32px", borderRadius: "50%" }}></div>
               </div>
               <div className="notification-item-copy">
                  <div className="skeleton-box" style={{ width: "200px", height: "16px", marginBottom: "8px" }}></div>
                  <div className="skeleton-box" style={{ width: "100%", height: "14px" }}></div>
               </div>
               <div className="notification-item-meta" style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <div className="skeleton-box" style={{ width: "40px", height: "12px" }}></div>
               </div>
            </article>
         ))}
      </div>
   );
};

function NotificationPage() {
   const [activeFilter, setActiveFilter] = useState("all");
   const [loading, setLoading] = useState(false); // No API integration yet

   const sampleNotifications = [
      {
         id: "n-1",
         type: "comment",
         title: "New Comment On Your Thread",
         detail: "@alex added a counterpoint to your climate claim discussion.",
         time: "4m ago",
         isRead: false,
      },
      {
         id: "n-2",
         type: "verification",
         title: "Claim Verification Updated",
         detail: "A moderator has updated the verdict confidence for one of your posts.",
         time: "18m ago",
         isRead: false,
      },
      {
         id: "n-3",
         type: "evidence",
         title: "New Evidence Submission",
         detail: "A community member submitted additional source evidence on your thread.",
         time: "1h ago",
         isRead: true,
      },
      {
         id: "n-4",
         type: "system",
         title: "Account Security Reminder",
         detail: "Review your account settings and keep your contact details up to date.",
         time: "Yesterday",
         isRead: true,
      },
   ];

   const filteredNotifications = useMemo(() => {
      if (activeFilter === "unread") {
         return sampleNotifications.filter((n) => !n.isRead);
      }
      return sampleNotifications;
   }, [activeFilter]);

   const unreadCount = sampleNotifications.filter((n) => !n.isRead).length;

   const getNotificationIcon = (type) => {
      if (type === "comment") return "message-square";
      if (type === "verification") return "badge-check";
      if (type === "evidence") return "paperclip";
      return "bell";
   };

   return (
      <div className="notifications-layout">
         <NavigationBar />

         <main className="notification-container">
            <header className="notifications-header">
               <div>
                  <h1 className="notifications-title">Notifications</h1>
                  <p className="notifications-subtitle">
                     Stay up to date with moderation activity and community engagement.
                  </p>
               </div>
               <span className="notification-count-pill">{unreadCount} unread</span>
            </header>

            <section className="notifications-toolbar box-panel">
               <div className="notification-filter-rail">
                  <button
                     type="button"
                     className={`notification-filter-btn ${activeFilter === "all" ? "active" : ""}`}
                     onClick={() => setActiveFilter("all")}>
                     <Icons
                        name="inbox"
                        size={16}
                     />
                     All
                  </button>
                  <button
                     type="button"
                     className={`notification-filter-btn ${activeFilter === "unread" ? "active" : ""}`}
                     onClick={() => setActiveFilter("unread")}>
                     <Icons
                        name="circle"
                        size={12}
                     />
                     Unread
                  </button>
               </div>

               <button
                  type="button"
                  className="mark-read-btn">
                  <Icons
                     name="check-circle"
                     size={16}
                  />
                  Mark all as read
               </button>
            </section>

            {loading ? (
               <NotificationSkeleton />
            ) : (
               <section className="notifications-list box-panel">
                  {filteredNotifications.length === 0 ? (
                     <div className="notification-empty-state">
                        <Icons
                           name="bell-off"
                           size={28}
                           color="#94a3b8"
                        />
                        <h2>No unread notifications</h2>
                        <p>Everything is up to date. New alerts will appear here.</p>
                     </div>
                  ) : (
                     filteredNotifications.map((item) => (
                        <article
                           key={item.id}
                           className={`notification-item ${item.isRead ? "is-read" : "is-unread"}`}>
                           <div className="notification-item-icon">
                              <Icons
                                 name={getNotificationIcon(item.type)}
                                 size={16}
                              />
                           </div>

                           <div className="notification-item-copy">
                              <h2>{item.title}</h2>
                              <p>{item.detail}</p>
                           </div>

                           <div className="notification-item-meta">
                              <span>{item.time}</span>
                              {!item.isRead && (
                                 <span
                                    className="notification-unread-dot"
                                    aria-hidden="true"
                                 />
                              )}
                           </div>
                        </article>
                     ))
                  )}
               </section>
            )}
         </main>
      </div>
   );
}

export default NotificationPage;
