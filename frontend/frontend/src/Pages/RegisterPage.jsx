/**
 * Register Page (Account Creation)
 * ══════════════════════════════════════════════════════════════════
 * User registration interface for creating new TruthLens accounts.
 *
 * Features:
 *   - Username, email, and password input
 *   - Show/hide password toggle
 *   - Account creation with backend validation
 *   - Switch to login if user already has account
 *   - Social login options (placeholder)
 *   - Redirect to requested page after registration
 *
 * State:
 *   - Form inputs: username, email, password
 *   - UI state: showPassword
 *   - Error handling for registration failures
 */

import { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { useNavigate, useLocation, Link } from "react-router-dom";
import Icons from "../components/Icons.jsx";
import { useGoogleLogin } from "@react-oauth/google";
import AuthShell from "../components/auth/AuthShell.jsx";

// ── Utilities & Constants ──
import { resolveApiEndpoint } from "../utils/api";

// ── Styles ──
import "./RegisterPage.css";

function RegisterPage() {
   const { login } = useAuth();
   const navigate = useNavigate();
   const location = useLocation();
   const from = location.state?.from ? location.state.from.pathname + location.state.from.search : "/community";
   const [error, setError] = useState("");
   const [fieldErrors, setFieldErrors] = useState({});
   const [showPassword, setShowPassword] = useState(false);
   const [formValues, setFormValues] = useState({
      username: "",
      email: "",
      password: "",
   });

   const googleLoginEndpoint = resolveApiEndpoint("GOOGLE_LOGIN");
   const [isSigningIn, setIsSigningIn] = useState(false);

   // ── Google OAuth Hook ──
   const loginWithGoogle = useGoogleLogin({
      onSuccess: async (tokenResponse) => {
         if (isSigningIn) return;

         setIsSigningIn(true);
         setError("");
         setFieldErrors({});

         try {
            const response = await fetch(googleLoginEndpoint, {
               method: "POST",
               headers: {
                  "Content-Type": "application/json",
               },
               body: JSON.stringify({
                  access_token: tokenResponse.access_token,
               }),
            });

            const data = await response.json().catch(() => ({}));

            if (!response.ok || !data?.access) {
               setError(data?.detail || "Unable to continue with Google right now. Please try again.");
               return;
            }

            const authenticatedUser = await login(data.access, data.refresh);

            if (!authenticatedUser) {
               throw new Error("Unable to load the authenticated user.");
            }

            if (authenticatedUser.has_completed_onboarding === false) {
               navigate("/onboarding", {
                  replace: true,
                  state: {
                     from: location.state?.from,
                  },
               });

               return;
            }

            navigate(from, {
               replace: true,
            });
         } catch (err) {
            console.error("Google registration error:", err);

            setError("Unable to continue with Google right now. Please try again.");
         } finally {
            setIsSigningIn(false);
         }
      },

      onError: () => {
         console.error("Google Sign-In Error");

         setError("Google sign-in failed. Please try again.");
      },
   });

   const handleInputChange = (event) => {
      const { name, value } = event.target;

      setFormValues((current) => ({
         ...current,
         [name]: value,
      }));

      setFieldErrors((current) => ({
         ...current,
         [name]: "",
      }));

      setError("");
   };

   const redirectAfterRegister = (isNewAccount = false) => {
      if (isNewAccount) {
         navigate("/onboarding", {
            replace: true,
            state: {
               from: location.state?.from,
            },
         });
         return;
      }

      navigate(from, { replace: true });
   };

   const normalizeRegistrationErrors = (data) => {
      const fields = {};

      if (!data || typeof data !== "object") {
         return {
            form: "Unable to create your account. Please try again.",
            fields,
         };
      }

      if (data.username) {
         fields.username = Array.isArray(data.username) ? data.username.join(" ") : String(data.username);
      }

      if (data.email) {
         fields.email = Array.isArray(data.email) ? data.email.join(" ") : String(data.email);
      }

      if (data.password) {
         fields.password = Array.isArray(data.password) ? data.password.join(" ") : String(data.password);
      }

      return {
         form:
            typeof data.detail === "string"
               ? data.detail
               : typeof data.non_field_errors?.[0] === "string"
                 ? data.non_field_errors[0]
                 : "",
         fields,
      };
   };
   /**
    * Handle form submission and account creation
    * Posts credentials to backend, stores tokens, redirects on success
    */
   const handleSubmit = async () => {
      if (isSigningIn) return;

      setIsSigningIn(true);
      setError("");
      setFieldErrors({});

      const registerEndpoint = resolveApiEndpoint("REGISTER");

      try {
         const response = await fetch(registerEndpoint, {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: JSON.stringify({
               username: formValues.username.trim(),
               email: formValues.email.trim().toLowerCase(),
               password: formValues.password,
            }),
         });

         const data = await response.json().catch(() => ({}));

         if (!response.ok) {
            const normalized = normalizeRegistrationErrors(data);

            setFieldErrors(normalized.fields);

            if (normalized.form || Object.keys(normalized.fields).length === 0) {
               setError(
                  normalized.form || "Unable to create your account. Please check your information and try again.",
               );
            }

            return;
         }

         if (!data?.access || !data?.refresh) {
            throw new Error("Registration succeeded without authentication tokens.");
         }

         await login(data.access, data.refresh);

         redirectAfterRegister(true);
      } catch (err) {
         console.error("Registration error:", err);

         setError("Unable to register right now. Please try again.");
      } finally {
         setIsSigningIn(false);
      }
   };

   return (
      <AuthShell
         eyebrow="TruthLens Community"
         title="Build a more credible information space."
         description="Create your account to investigate questionable claims, contribute evidence, and take part in community verification."
         highlights={[
            "Review claims with AI-assisted analysis",
            "Contribute evidence to community investigations",
            "Build credibility through meaningful participation",
         ]}
      >
         <div className="register-right">
            <div className="form-container">
               <div className="form-header">
                  <p className="greeting-text">Join TruthLens</p>

                  <h2 className="form-title">Create your account</h2>

                  <p className="form-description">Get started with a free TruthLens account.</p>
               </div>

               <form
                  onSubmit={(event) => {
                     event.preventDefault();
                     handleSubmit();
                  }}
                  noValidate
               >
                  {error && (
                     <div className="error-message" role="alert" aria-live="polite">
                        <Icons name="alert-triangle" size={16} aria-hidden="true" />

                        <span>{error}</span>
                     </div>
                  )}

                  {/* username */}
                  <div className="input-group">
                     <label htmlFor="register-username">Username</label>
                     <div className="input-wrapper">
                        <Icons name="user" size={18} className="input-icon" />
                        <input
                           id="register-username"
                           type="text"
                           name="username"
                           autoComplete="username"
                           placeholder="Choose a username"
                           value={formValues.username}
                           onChange={handleInputChange}
                           aria-invalid={Boolean(fieldErrors.username)}
                           aria-describedby={fieldErrors.username ? "register-username-error" : undefined}
                           disabled={isSigningIn}
                           required
                        />
                     </div>
                     {fieldErrors.username && (
                        <p id="register-username-error" className="field-error" role="alert">
                           {fieldErrors.username}
                        </p>
                     )}
                  </div>

                  {/* email */}
                  <div className="input-group">
                     <label htmlFor="register-email">Email Address</label>
                     <div className="input-wrapper">
                        <Icons name="mail" size={18} className="input-icon" />
                        <input
                           id="register-email"
                           type="email"
                           name="email"
                           autoComplete="email"
                           placeholder="you@example.com"
                           value={formValues.email}
                           onChange={handleInputChange}
                           aria-invalid={Boolean(fieldErrors.email)}
                           aria-describedby={fieldErrors.email ? "register-email-error" : undefined}
                           disabled={isSigningIn}
                           required
                        />
                     </div>
                     {fieldErrors.email && (
                        <p id="register-email-error" className="field-error" role="alert">
                           {fieldErrors.email}
                        </p>
                     )}
                  </div>

                  {/* password */}
                  <div className="input-group">
                     <label htmlFor="register-password">Password</label>
                     <div className="input-wrapper">
                        <Icons name="shield" size={18} className="input-icon" />
                        <input
                           id="register-password"
                           type={showPassword ? "text" : "password"}
                           name="password"
                           autoComplete="new-password"
                           placeholder="Create a strong password"
                           value={formValues.password}
                           onChange={handleInputChange}
                           aria-invalid={Boolean(fieldErrors.password)}
                           aria-describedby={
                              fieldErrors.password ? "register-password-error" : "register-password-hint"
                           }
                           disabled={isSigningIn}
                           required
                        />
                        <button
                           type="button"
                           className="show-password-btn"
                           onClick={() => setShowPassword((current) => !current)}
                           aria-label={showPassword ? "Hide password" : "Show password"}
                           aria-pressed={showPassword}
                           disabled={isSigningIn}
                        >
                           <Icons name={showPassword ? "eye-off" : "eye"} size={16} aria-hidden="true" />

                           <span>{showPassword ? "Hide" : "Show"}</span>
                        </button>
                     </div>
                     {fieldErrors.password ? (
                        <p id="register-password-error" className="field-error">
                           {fieldErrors.password}
                        </p>
                     ) : (
                        <p id="register-password-hint" className="field-hint">
                           Use a password that is difficult to guess and not commonly used.
                        </p>
                     )}
                  </div>

                  <button type="submit" className="submit-btn" disabled={isSigningIn} aria-busy={isSigningIn}>
                     {isSigningIn ? (
                        <span className="sign-in-loading">
                           <span className="sign-in-spinner" aria-hidden="true" />
                           <span>Creating account…</span>
                        </span>
                     ) : (
                        <>
                           <span>Create account</span>

                           <Icons name="arrow-right" size={18} aria-hidden="true" />
                        </>
                     )}
                  </button>
               </form>

               <div className="signin-prompt">
                  Already have an account?{" "}
                  <Link
                     to="/login"
                     state={{
                        from: location.state?.from,
                     }}
                  >
                     Sign in
                  </Link>
               </div>

               <div className="divider">
                  <span>OR</span>
               </div>

               <button
                  type="button"
                  className="gsi-material-button"
                  onClick={() => loginWithGoogle()}
                  disabled={isSigningIn}
                  aria-label="Continue with Google"
               >
                  <div className="gsi-material-button-state" />

                  <div className="gsi-material-button-content-wrapper">
                     <div className="gsi-material-button-icon">
                        <svg
                           version="1.1"
                           xmlns="http://www.w3.org/2000/svg"
                           viewBox="0 0 48 48"
                           aria-hidden="true"
                           focusable="false"
                        >
                           <path
                              fill="#EA4335"
                              d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
                           />

                           <path
                              fill="#4285F4"
                              d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
                           />

                           <path
                              fill="#FBBC05"
                              d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
                           />

                           <path
                              fill="#34A853"
                              d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
                           />

                           <path fill="none" d="M0 0h48v48H0z" />
                        </svg>
                     </div>

                     <span className="gsi-material-button-contents">Continue with Google</span>

                     <span className="gsi-material-button-hidden-text" aria-hidden="true">
                        Continue with Google
                     </span>
                  </div>
               </button>
            </div>
         </div>
      </AuthShell>
   );
}

export default RegisterPage;
