/**
 * Login Page (Authentication)
 *
 * Features:
 * - Username/email and password authentication
 * - Persistent sessions with Remember Me
 * - Show/hide password toggle
 * - Password reset flow
 * - Google OAuth authentication
 * - Redirect to requested route after login
 * - Success/error feedback
 */

import { useState, useEffect } from "react";
import { useAuth } from "../hooks/useAuth";
import { useNavigate, useLocation, Link } from "react-router-dom";
import Icons from "../components/Icons.jsx";
import { useGoogleLogin } from "@react-oauth/google";
import AuthShell from "../components/auth/AuthShell.jsx";
import { useNotification } from "../hooks/useNotification";
// ── Utilities & Constants ──
import { resolveApiEndpoint } from "../utils/api";
import { canAccessWorkspace } from "../utils/workspace";
import { resolveAuthDestination } from "../utils/authNavigation";

// ── Styles ──
import "./LoginPage.css";

function LoginPage() {
   const { login, user, loading } = useAuth();
   const navigate = useNavigate();
   const location = useLocation();
   const [showPassword, setShowPassword] = useState(false);
   const [isSigningIn, setIsSigningIn] = useState(false);
   const [justLoggedIn, setJustLoggedIn] = useState(false);
   const loginEndpoint = resolveApiEndpoint("LOGIN");
   const googleLoginEndpoint = resolveApiEndpoint("GOOGLE_LOGIN");
   const from = resolveAuthDestination(location.state?.from, null);

   const [error, setError] = useState(null);
   const [formValues, setFormValues] = useState({
      username: "",
      password: "",
      remember_me: false,
   });
   const { addToast } = useNotification();

   // When user data loads after login, redirect to appropriate dashboard
   useEffect(() => {
      if (justLoggedIn && user && !loading) {
         setJustLoggedIn(false);

         addToast({
            type: "success",
            title: "Signed in",
            message: "Welcome back to TruthLens.",
            duration: 3000,
         });

         const destination = from || (canAccessWorkspace(user) ? "/workspace" : "/community");

         navigate(destination, {
            replace: true,
         });
      }
   }, [user, loading, justLoggedIn, from, navigate, addToast]);

   const handleInputChange = (event) => {
      const { name, value } = event.target;
      setFormValues({
         ...formValues,
         [name]: value,
      });
   };

   /**
    * Handle remember me checkbox toggle
    * @param {Event} e - Checkbox change event
    */
   const handleCheckbox = (e) => {
      setFormValues({
         ...formValues,
         remember_me: e.target.checked,
      });
   };

   /**
    * Handle form submission and authentication
    * Posts credentials to backend, stores tokens, redirects on success
    */
   const handleSubmit = async () => {
      setIsSigningIn(true);
      setError(null);

      try {
         const response = await fetch(loginEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               username: formValues.username,
               password: formValues.password,
               remember_me: formValues.remember_me,
            }),
         });

         const data = await response.json().catch(() => ({}));

         if (response.ok && data?.access && data?.refresh) {
            login(data.access, data.refresh, formValues.remember_me);
            setJustLoggedIn(true); // Flag that we're waiting for user data to load
            return;
         }

         setError(data?.detail || "Invalid credentials. Please try again.");
      } catch (err) {
         setError("Unable to sign in right now. Please try again.");
         console.error("Login error:", err);
      } finally {
         setIsSigningIn(false);
      }
   };

   // ── Google OAuth Hook ──
   const loginWithGoogle = useGoogleLogin({
      onSuccess: async (tokenResponse) => {
         // console.log("Google Access Token:", tokenResponse.access_token);
         setIsSigningIn(true);
         setError(null);

         try {
            const response = await fetch(googleLoginEndpoint, {
               method: "POST",
               headers: { "Content-Type": "application/json" },
               body: JSON.stringify({
                  access_token: tokenResponse.access_token,
               }),
            });

            const data = await response.json().catch(() => ({}));

            // console.log("Django Authentication Response:", data);

            if (response.ok && data?.access) {
               // If refresh is empty or undefined, it just passes null/undefined to AuthContext
               login(data.access, data.refresh, true);
               setJustLoggedIn(true);
               return;
            }

            setError(data?.detail || "Unable to sign in with Google right now. Please try again.");
         } catch (err) {
            console.error("Google Login error:", err);
            setError("Unable to sign in with Google right now. Please try again.");
         } finally {
            setIsSigningIn(false);
         }
      },
      onError: () => {
         setError("Google sign-in failed. Please try again.");
         console.error("Google Sign-In Error");
      },
   });

   return (
      <>
         <AuthShell
            eyebrow="TruthLens Community"
            title="The internet deserves better evidence."
            description="Sign in to continue investigating claims, contributing evidence, and helping the community reach better conclusions."
            highlights={[
               "Review questionable information with AI-assisted analysis",
               "Contribute evidence to community investigations",
               "Build trust through meaningful participation",
            ]}
         >
            {/* Right Side: Login Form */}
            <div className="login-right">
               <div className="form-container">
                  <div className="form-header">
                     <p className="greeting-text">Welcome back</p>
                     <h2 className="form-title">Sign in to your TruthLens account</h2>
                  </div>

                  <form
                     onSubmit={(e) => {
                        e.preventDefault();
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

                     <div className="input-group">
                        <label htmlFor="login-identifier">Username or email</label>

                        <div className="input-wrapper">
                           <Icons name="mail" size={18} className="input-icon" aria-hidden="true" />

                           <input
                              id="login-identifier"
                              type="text"
                              name="username"
                              placeholder="Enter your username or email"
                              value={formValues.username}
                              onChange={handleInputChange}
                              autoComplete="username"
                              disabled={isSigningIn}
                              aria-invalid={undefined}
                              required
                           />
                        </div>
                     </div>

                     <div className="input-group password-group">
                        <label htmlFor="login-password">Password</label>

                        <div className="input-wrapper">
                           <Icons name="lock" size={18} className="input-icon" aria-hidden="true" />

                           <input
                              id="login-password"
                              type={showPassword ? "text" : "password"}
                              name="password"
                              placeholder="Enter your password"
                              value={formValues.password}
                              onChange={handleInputChange}
                              autoComplete="current-password"
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

                        <Link to="/forgot-password" className="forgot-password">
                           Forgot password?
                        </Link>
                     </div>

                     <div className="form-options">
                        <label className="remember-me">
                           <input
                              type="checkbox"
                              checked={formValues.remember_me}
                              onChange={handleCheckbox}
                              disabled={isSigningIn}
                           />
                           <span className="custom-checkbox" aria-hidden="true">
                              <Icons name="check" size={13} />
                           </span>
                           <span>Remember me</span>
                        </label>
                     </div>

                     <button type="submit" className="submit-btn" disabled={isSigningIn} aria-busy={isSigningIn}>
                        {isSigningIn ? (
                           <span className="sign-in-loading">
                              <span className="sign-in-spinner" aria-hidden="true" />
                              <span>Signing in…</span>
                           </span>
                        ) : (
                           <>
                              <span>Sign in</span>
                              <Icons name="arrow-right" size={18} aria-hidden="true" />
                           </>
                        )}
                     </button>
                  </form>

                  <div className="signup-prompt">
                     Don't have an account?{" "}
                     <Link to="/register" state={from ? { from } : undefined}>
                        Create Account
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
      </>
   );
}

export default LoginPage;
