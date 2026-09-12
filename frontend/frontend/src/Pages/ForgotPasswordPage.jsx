import { useState } from "react";
import { Link } from "react-router-dom";
import AuthShell from "../components/auth/AuthShell";
import AccountStatus from "../components/account/AccountStatus.jsx";
import Icons from "../components/Icons.jsx";
import Button from "../components/ui/Button.jsx";
import Input from "../components/ui/Input.jsx";
import { resolveApiEndpoint } from "../utils/api";
import "../components/account/AccountForm.css";

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
            <AccountStatus
               tone="info"
               icon={<Icons name="mail-check" size={24} aria-hidden="true" />}
               eyebrow="Check your email"
               title="Reset instructions sent"
               description={
                  <>
                     If an account exists for <strong>{email}</strong>, we've sent password reset instructions.
                  </>
               }
               actions={
                  <Link to="/login" className="account-status__action account-status__action--primary">
                     Back to sign in
                  </Link>
               }
               live="polite"
            />
         ) : (
            <div className="account-form">
               <div className="account-form__header">
                  <p className="account-form__eyebrow">Forgot your password?</p>

                  <h1 className="account-form__title">Reset your password</h1>

                  <p className="account-form__description">
                     Enter the email address associated with your TruthLens account.
                  </p>
               </div>

               <form onSubmit={handleSubmit}>
                  {error && (
                     <div className="account-form__alert" role="alert" aria-live="polite">
                        <Icons name="alert-triangle" size={16} aria-hidden="true" />

                        <span>{error}</span>
                     </div>
                  )}

                  <div className="account-field">
                     <label className="account-field__label" htmlFor="reset-email">
                        Email address
                     </label>

                     <Input
                        id="reset-email"
                        type="email"
                        name="email"
                        density="comfortable"
                        surface="subtle"
                        leadingIcon={<Icons name="mail" size={18} aria-hidden="true" />}
                        placeholder="you@example.com"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        autoComplete="email"
                        disabled={isSubmitting}
                        required
                     />
                  </div>

                  <Button
                     type="submit"
                     variant="primary"
                     density="comfortable"
                     loading={isSubmitting}
                     loadingLabel="Sending instructions…"
                     trailingIcon={<Icons name="arrow-right" size={18} aria-hidden="true" />}
                     fullWidth
                     disabled={isSubmitting}
                  >
                     Send reset instructions
                  </Button>
               </form>

               <div className="account-form__prompt">
                  Remember your password? <Link to="/login">Back to sign in</Link>
               </div>
            </div>
         )}
      </AuthShell>
   );
}

export default ForgotPasswordPage;
