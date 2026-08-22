import { useState } from "react";
import { Link } from "react-router-dom";
import AuthShell from "../components/auth/AuthShell";
import Icons from "../components/Icons.jsx";
import { resolveApiEndpoint } from "../utils/api";
import "./LoginPage.css";

function ForgotPasswordPage() {
   const [email, setEmail] = useState("");
   const [isSubmitting, setIsSubmitting] = useState(false);
   const [error, setError] = useState(null);
   const [success, setSuccess] = useState(false);

   const handleSubmit = async (event) => {
      event.preventDefault();

      setIsSubmitting(true);
      setError(null);

      try {
         const response = await fetch(resolveApiEndpoint("PASSWORD_RESET"), {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: JSON.stringify({ email }),
         });

         const data = await response.json().catch(() => ({}));

         if (!response.ok) {
            throw new Error(data?.detail || "Unable to process the request.");
         }

         setSuccess(true);
      } catch (err) {
         console.error("Password reset request failed:", err);
         setError(err.message || "Unable to process the request. Please try again.");
      } finally {
         setIsSubmitting(false);
      }
   };

   return (
      <AuthShell
         eyebrow="Account recovery"
         title="Regain access securely."
         description="We'll help you return to your TruthLens account without compromising your security."
         highlights={[
            "Secure one-time password reset link",
            "Your existing account and contributions stay intact",
            "Reset links expire automatically",
         ]}
      >
         {success ? (
            <div className="auth-status">
               <div className="auth-status-icon" aria-hidden="true">
                  <Icons name="mail-check" size={24} />
               </div>

               <p className="greeting-text">Check your email</p>

               <h2 className="form-title">Reset instructions sent</h2>

               <p className="form-description">
                  If an account exists for <strong>{email}</strong>, we've sent password reset instructions.
               </p>

               <Link to="/login" className="submit-btn auth-link-button">
                  Back to sign in
               </Link>
            </div>
         ) : (
            <>
               <div className="form-header">
                  <p className="greeting-text">Forgot your password?</p>

                  <h2 className="form-title">Reset your password</h2>

                  <p className="form-description">Enter the email address associated with your TruthLens account.</p>
               </div>

               <form onSubmit={handleSubmit}>
                  {error && (
                     <div className="error-message" role="alert" aria-live="polite">
                        <Icons name="alert-triangle" size={16} aria-hidden="true" />

                        <span>{error}</span>
                     </div>
                  )}

                  <div className="input-group">
                     <label htmlFor="reset-email">Email address</label>

                     <div className="input-wrapper">
                        <Icons name="mail" size={18} className="input-icon" aria-hidden="true" />

                        <input
                           id="reset-email"
                           type="email"
                           name="email"
                           placeholder="you@example.com"
                           value={email}
                           onChange={(event) => setEmail(event.target.value)}
                           autoComplete="email"
                           disabled={isSubmitting}
                           required
                        />
                     </div>
                  </div>

                  <button type="submit" className="submit-btn" disabled={isSubmitting} aria-busy={isSubmitting}>
                     {isSubmitting ? (
                        <span className="sign-in-loading">
                           <span className="sign-in-spinner" aria-hidden="true" />
                           <span>Sending instructions…</span>
                        </span>
                     ) : (
                        <>
                           <span>Send reset instructions</span>
                           <Icons name="arrow-right" size={18} aria-hidden="true" />
                        </>
                     )}
                  </button>
               </form>

               <div className="signup-prompt">
                  Remember your password? <Link to="/login">Back to sign in</Link>
               </div>
            </>
         )}
      </AuthShell>
   );
}

export default ForgotPasswordPage;
