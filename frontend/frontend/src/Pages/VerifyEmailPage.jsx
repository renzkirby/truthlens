import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import Icons from "../components/Icons";
import AuthShell from "../components/auth/AuthShell";
import { resolveApiEndpoint } from "../utils/api";
import "./VerifyEmailPage.css";

const verificationRequests = new Map();

function requestEmailVerification(token) {
   if (verificationRequests.has(token)) {
      return verificationRequests.get(token);
   }

   const request = (async () => {
      const endpoint = new URL(resolveApiEndpoint("VERIFY_EMAIL"));

      endpoint.searchParams.set("token", token);

      const response = await fetch(endpoint.toString(), {
         method: "GET",
      });

      const data = await response.json().catch(() => ({}));

      return {
         ok: response.ok,
         data,
      };
   })();

   verificationRequests.set(token, request);

   return request;
}

function VerifyEmailPage() {
   const [searchParams] = useSearchParams();
   const token = searchParams.get("token");
   const { user, refreshUser } = useAuth();

   const [status, setStatus] = useState("loading");
   const [message, setMessage] = useState("");
   const isAuthenticated = Boolean(user);

   useEffect(() => {
      let isActive = true;

      const verify = async () => {
         if (!token) {
            setStatus("invalid");
            setMessage("This verification link is missing its token.");
            return;
         }

         try {
            const { ok, data } = await requestEmailVerification(token);

            if (!isActive) return;

            if (ok && data?.status === "verified") {
               if (isAuthenticated) {
                  try {
                     await refreshUser();
                  } catch (error) {
                     console.error("Failed to refresh verified user:", error);
                  }
               }

               if (!isActive) return;

               setStatus("success");
               setMessage(data?.detail || "Your email has been verified successfully.");

               return;
            }

            if (data?.status === "expired") {
               setStatus("expired");
               setMessage(data?.detail || "This verification link has expired.");
               return;
            }

            setStatus("invalid");
            setMessage(data?.detail || "This verification link is invalid or has already been used.");
         } catch (error) {
            console.error("Email verification failed:", error);

            if (!isActive) return;

            setStatus("error");
            setMessage("We couldn't verify your email right now. Please try again.");
         }
      };

      verify();

      return () => {
         isActive = false;
      };
   }, [token, isAuthenticated, refreshUser]);

   const content = {
      loading: {
         icon: "loader",
         title: "Verifying your email",
         description: "Please wait while we confirm your email address.",
      },
      success: {
         icon: "check-circle",
         title: "Email verified",
         description: message,
      },
      expired: {
         icon: "clock",
         title: "Verification link expired",
         description: message,
      },
      invalid: {
         icon: "alert-circle",
         title: "Verification link unavailable",
         description: message,
      },
      error: {
         icon: "alert-triangle",
         title: "Verification unavailable",
         description: message,
      },
   };

   const current = content[status];

   return (
      <AuthShell
         eyebrow="Account Security"
         title="Confirm your email address."
         description="Email verification helps TruthLens confirm that the address connected to your account belongs to you."
         highlights={[
            "Confirm account ownership",
            "Keep account recovery reliable",
            "Support trusted account activity",
         ]}
      >
         <div className="verify-email-panel">
            <div className="verify-email-card" aria-live="polite" aria-busy={status === "loading"}>
               <div className={`verify-email-icon verify-email-icon--${status}`}>
                  {status === "loading" ? (
                     <span className="verify-email-spinner" aria-hidden="true" />
                  ) : (
                     <Icons name={current.icon} size={28} aria-hidden="true" />
                  )}
               </div>

               <h1>{current.title}</h1>

               <p>{current.description}</p>

               {status === "success" && (
                  <div className="verify-email-actions">
                     {user ? (
                        <Link to="/community" className="verify-email-btn verify-email-btn--primary">
                           Continue to TruthLens
                        </Link>
                     ) : (
                        <Link to="/login" className="verify-email-btn verify-email-btn--primary">
                           Sign in to TruthLens
                        </Link>
                     )}
                  </div>
               )}

               {(status === "expired" || status === "invalid") && (
                  <div className="verify-email-actions">
                     <Link to="/login" className="verify-email-btn verify-email-btn--primary">
                        Sign in to resend verification email
                     </Link>
                  </div>
               )}

               {status === "error" && (
                  <button
                     type="button"
                     className="verify-email-btn verify-email-btn--primary"
                     onClick={() => window.location.reload()}
                  >
                     Try again
                  </button>
               )}
            </div>
         </div>
      </AuthShell>
   );
}

export default VerifyEmailPage;
