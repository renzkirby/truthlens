import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import AuthShell from "../components/auth/AuthShell";
import AccountStatus from "../components/account/AccountStatus.jsx";
import Icons from "../components/Icons.jsx";
import Button from "../components/ui/Button.jsx";
import Input from "../components/ui/Input.jsx";
import { resolveApiEndpoint } from "../utils/api";
import "../components/account/AccountForm.css";

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
            <AccountStatus
               tone="success"
               icon={<Icons name="check-circle" size={24} aria-hidden="true" />}
               eyebrow="Password updated"
               title="You're ready to sign in"
               description="Your TruthLens password has been changed successfully."
               actions={
                  <Link to="/login" className="account-status__action account-status__action--primary">
                     Sign in
                  </Link>
               }
               live="polite"
            />
         ) : (
            <div className="account-form">
               <div className="account-form__header">
                  <p className="account-form__eyebrow">Secure your account</p>

                  <h1 className="account-form__title">Create a new password</h1>
               </div>

               <form onSubmit={handleSubmit}>
                  {error && (
                     <div className="account-form__alert" role="alert" aria-live="polite">
                        <Icons name="alert-triangle" size={16} aria-hidden="true" />

                        <span>{error}</span>
                     </div>
                  )}

                  <div className="account-field account-field--icon-toggle">
                     <label className="account-field__label" htmlFor="new-password">
                        New password
                     </label>

                     <Input
                        id="new-password"
                        type={showPassword ? "text" : "password"}
                        density="comfortable"
                        surface="subtle"
                        leadingIcon={<Icons name="lock" size={18} aria-hidden="true" />}
                        trailingAdornment={
                           <button
                              type="button"
                              className="account-password-toggle"
                              onClick={() => setShowPassword((current) => !current)}
                              aria-label={showPassword ? "Hide new password" : "Show new password"}
                              aria-pressed={showPassword}
                              disabled={isSubmitting}
                           >
                              <Icons name={showPassword ? "eye-off" : "eye"} size={16} aria-hidden="true" />
                           </button>
                        }
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
                  </div>

                  <div className="account-field account-field--icon-toggle">
                     <label className="account-field__label" htmlFor="confirm-password">
                        Confirm new password
                     </label>

                     <Input
                        id="confirm-password"
                        type={showConfirmPassword ? "text" : "password"}
                        density="comfortable"
                        surface="subtle"
                        leadingIcon={<Icons name="lock" size={18} aria-hidden="true" />}
                        trailingAdornment={
                           <button
                              type="button"
                              className="account-password-toggle"
                              onClick={() => setShowConfirmPassword((current) => !current)}
                              aria-label={
                                 showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"
                              }
                              aria-pressed={showConfirmPassword}
                              disabled={isSubmitting}
                           >
                              <Icons name={showConfirmPassword ? "eye-off" : "eye"} size={16} aria-hidden="true" />
                           </button>
                        }
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
                  </div>

                  <Button
                     type="submit"
                     variant="primary"
                     density="comfortable"
                     loading={isSubmitting}
                     loadingLabel="Updating password…"
                     trailingIcon={<Icons name="arrow-right" size={18} aria-hidden="true" />}
                     fullWidth
                     disabled={isSubmitting}
                  >
                     Reset password
                  </Button>
               </form>

               <div className="account-form__prompt">
                  <Link to="/login">Back to sign in</Link>
               </div>
            </div>
         )}
      </AuthShell>
   );
}

export default ResetPasswordPage;
