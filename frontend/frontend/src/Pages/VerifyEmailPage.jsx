import { Link, useSearchParams } from "react-router-dom";
import NavigationBar from "../components/NavigationBar";
import Icons from "../components/Icons";
import "./VerifyEmailPage.css";

function VerifyEmailPage() {
   const [searchParams] = useSearchParams();
   const statusParam = (searchParams.get("status") || "pending").toLowerCase();

   const statusMap = {
      success: {
         title: "Email Verified",
         subtitle: "Your account is now trusted for protected actions in TruthLens.",
         icon: "check-circle",
         tone: "success",
      },
      expired: {
         title: "Verification Link Expired",
         subtitle: "Request a fresh verification link from your profile settings.",
         icon: "alert-circle",
         tone: "warning",
      },
      failed: {
         title: "Verification Failed",
         subtitle: "The link looks invalid. Try again or request a new one.",
         icon: "x-circle",
         tone: "danger",
      },
      pending: {
         title: "Verify Your Email",
         subtitle: "Open the verification message in your inbox to complete account setup.",
         icon: "mail",
         tone: "neutral",
      },
   };

   const current = statusMap[statusParam] || statusMap.pending;

   return (
      <div className="verify-email-layout">
         <NavigationBar />

         <main className="verify-email-container">
            <section className={`verify-email-card ${current.tone}`}>
               <div className="verify-email-icon-wrap">
                  <Icons
                     name={current.icon}
                     size={24}
                  />
               </div>

               <h1 className="verify-email-title">{current.title}</h1>
               <p className="verify-email-subtitle">{current.subtitle}</p>

               <div className="verify-email-actions">
                  <Link
                     to="/settings"
                     className="verify-email-btn primary">
                     <Icons
                        name="settings"
                        size={16}
                     />
                     Account Settings
                  </Link>
                  <Link
                     to="/community"
                     className="verify-email-btn secondary">
                     <Icons
                        name="globe"
                        size={16}
                     />
                     Go To Community
                  </Link>
               </div>
            </section>
         </main>
      </div>
   );
}

export default VerifyEmailPage;
