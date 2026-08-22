import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import AuthShell from "../components/auth/AuthShell";
import Icons from "../components/Icons.jsx";
import { resolveApiEndpoint } from "../utils/api";
import "./LoginPage.css";

function ResetPasswordPage() {
   const { uid, token } = useParams();

   const [showPassword, setShowPassword] = useState(false);
   const [showConfirmPassword, setShowConfirmPassword] = useState(false);

   const [formValues, setFormValues] = useState({
      newPassword: "",
      confirmPassword: "",
   });

   const [isSubmitting, setIsSubmitting] = useState(false);
   const [error, setError] = useState(null);
   const [success, setSuccess] = useState(false);

   const handleSubmit = async (event) => {
      event.preventDefault();

      if (formValues.newPassword !== formValues.confirmPassword) {
         setError("Passwords do not match.");
         return;
      }

      setIsSubmitting(true);
      setError(null);

      try {
         const response = await fetch(resolveApiEndpoint("PASSWORD_RESET_CONFIRM"), {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: JSON.stringify({
               uid,
               token,
               new_password: formValues.newPassword,
               confirm_password: formValues.confirmPassword,
            }),
         });

         const data = await response.json().catch(() => ({}));

         if (!response.ok) {
            const detail = Array.isArray(data?.detail) ? data.detail.join(" ") : data?.detail;

            throw new Error(detail || "Unable to reset your password. Please request a new link.");
         }

         setSuccess(true);
      } catch (err) {
         console.error("Password reset failed:", err);

         setError(err.message || "Unable to reset your password. Please request a new link.");
      } finally {
         setIsSubmitting(false);
      }
   };

   return (
      <AuthShell
         eyebrow="Account recovery"
         title="Choose a new password."
         description="Create a strong password that you don't use elsewhere."
         highlights={[
            "Your reset link is single-use",
            "Password strength is validated securely",
            "Your TruthLens account history remains unchanged",
         ]}
      >
         {success ? (
            <div className="auth-status">
               <div className="auth-status-icon" aria-hidden="true">
                  <Icons name="check-circle" size={24} />
               </div>

               <p className="greeting-text">Password updated</p>

               <h2 className="form-title">You're ready to sign in</h2>

               <p className="form-description">Your TruthLens password has been changed successfully.</p>

               <Link to="/login" className="submit-btn auth-link-button">
                  Sign in
               </Link>
            </div>
         ) : (
            <>
               <div className="form-header">
                  <p className="greeting-text">Secure your account</p>

                  <h2 className="form-title">Create a new password</h2>
               </div>

               <form onSubmit={handleSubmit}>
                  {error && (
                     <div className="error-message" role="alert" aria-live="polite">
                        <Icons name="alert-triangle" size={16} aria-hidden="true" />

                        <span>{error}</span>
                     </div>
                  )}

                  <div className="input-group">
                     <label htmlFor="new-password">New password</label>

                     <div className="input-wrapper">
                        <Icons name="lock" size={18} className="input-icon" aria-hidden="true" />

                        <input
                           id="new-password"
                           type={showPassword ? "text" : "password"}
                           value={formValues.newPassword}
                           placeholder="Enter your new password"
                           onChange={(event) =>
                              setFormValues((current) => ({
                                 ...current,
                                 newPassword: event.target.value,
                              }))
                           }
                           autoComplete="new-password"
                           disabled={isSubmitting}
                           required
                        />

                        <button
                           type="button"
                           className="show-password-btn"
                           onClick={() => setShowPassword((current) => !current)}
                           aria-label={showPassword ? "Hide new password" : "Show new password"}
                           aria-pressed={showPassword}
                           disabled={isSubmitting}
                        >
                           <Icons name={showPassword ? "eye-off" : "eye"} size={16} aria-hidden="true" />
                        </button>
                     </div>
                  </div>

                  <div className="input-group">
                     <label htmlFor="confirm-password">Confirm new password</label>

                     <div className="input-wrapper">
                        <Icons name="lock" size={18} className="input-icon" aria-hidden="true" />

                        <input
                           id="confirm-password"
                           type={showConfirmPassword ? "text" : "password"}
                           value={formValues.confirmPassword}
                           placeholder="Confirm your new password"
                           onChange={(event) =>
                              setFormValues((current) => ({
                                 ...current,
                                 confirmPassword: event.target.value,
                              }))
                           }
                           autoComplete="new-password"
                           disabled={isSubmitting}
                           required
                        />

                        <button
                           type="button"
                           className="show-password-btn"
                           onClick={() => setShowConfirmPassword((current) => !current)}
                           aria-label={
                              showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"
                           }
                           aria-pressed={showConfirmPassword}
                           disabled={isSubmitting}
                        >
                           <Icons name={showConfirmPassword ? "eye-off" : "eye"} size={16} aria-hidden="true" />
                        </button>
                     </div>
                  </div>

                  <button type="submit" className="submit-btn" disabled={isSubmitting} aria-busy={isSubmitting}>
                     {isSubmitting ? (
                        <span className="sign-in-loading">
                           <span className="sign-in-spinner" aria-hidden="true" />
                           <span>Updating password…</span>
                        </span>
                     ) : (
                        <>
                           <span>Reset password</span>
                           <Icons name="arrow-right" size={18} aria-hidden="true" />
                        </>
                     )}
                  </button>
               </form>

               <div className="signup-prompt">
                  <Link to="/login">Back to sign in</Link>
               </div>
            </>
         )}
      </AuthShell>
   );
}

export default ResetPasswordPage;
