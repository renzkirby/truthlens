import "./NotificationPage.css";

function NotificationPage() {
   return (
      <main className="tl-notifications-page">
         <div className="tl-notifications-page__content">
            <section
               className="tl-notifications-page__state"
               aria-labelledby="tl-notifications-title"
            >
               <h1 id="tl-notifications-title" className="tl-notifications-page__title">
                  Notifications
               </h1>
               <p className="tl-notifications-page__lead">
                  Account activity notifications are not available yet.
               </p>
               <p className="tl-notifications-page__description">
                  TruthLens is not currently collecting or delivering account activity notifications.
               </p>
               <p className="tl-notifications-page__supporting">
                  Community, verification, and Workspace functionality continue independently.
               </p>
            </section>
         </div>
      </main>
   );
}

export default NotificationPage;
