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
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "../components/Icons.jsx";
import { useGoogleLogin } from "@react-oauth/google";

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
            console.log("Registration validation response:", data);

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
      <>
         <div className="register-layout">
            {/* Left Side */}
            <div className="register-left">
               <div className="register-logo">
                  <img src={LogoImage} alt="TruthLens Logo" style={{ height: "40px", width: "auto" }} />
                  <span className="logo-text">TruthLens</span>
               </div>

               <div className="register-hero">
                  <h1 className="hero-title">
                     Join the Fight
                     <br />
                     Against
                     <br />
                     Misinformation.
                  </h1>
                  <p className="hero-subtitle">
                     Create your account and start contributing by verifying claims alongside a global community.
                  </p>
               </div>

               <div className="register-features">
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons name="sparkles" size={18} />
                     </div>
                     <span>AI-powered claim detection in real time</span>
                  </div>
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons name="users" size={18} />
                     </div>
                     <span>Community-driven evidence and voting</span>
                  </div>
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons name="trophy" size={18} />
                     </div>
                     <span>Earn Trust Score for contributing verified facts</span>
                  </div>
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons name="globe" size={18} />
                     </div>
                     <span>Browser extension for on-the-fly fact checking</span>
                  </div>
               </div>

               <div className="register-footer-link">WWW.TRUTHLENS-DEV.VERCEL.APP</div>

               <div className="bg-circle circle-1"></div>
               <div className="bg-circle circle-2"></div>
               <div className="bg-circle circle-3"></div>
            </div>

            {/* Right Side */}
            <div className="register-right">
               <div className="form-container">
                  <div className="form-header">
                     <p className="greeting-text">Hello! Let's get started.</p>
                     <h2 className="form-title">
                        <span>Create</span> your account
                     </h2>
                  </div>

                  <form
                     onSubmit={(e) => {
                        e.preventDefault();
                        handleSubmit();
                     }}
                  >
                     {error && (
                        <div className="error-message" role="alert">
                           <Icons name="alert-triangle" size={16} />
                           <span>{error}</span>
                        </div>
                     )}

                     <div className="input-group">
                        <label htmlFor="register-username">Username</label>

                        <div className="input-wrapper">
                           <Icons name="user" size={18} className="input-icon" />

                           <input
                              id="register-username"
                              type="text"
                              name="username"
                              autoComplete="username"
                              placeholder="Choose a unique username..."
                              value={formValues.username}
                              onChange={handleInputChange}
                              aria-invalid={Boolean(fieldErrors.username)}
                              aria-describedby={fieldErrors.username ? "register-username-error" : undefined}
                              required
                           />
                        </div>

                        {fieldErrors.username && (
                           <p id="register-username-error" className="field-error">
                              {fieldErrors.username}
                           </p>
                        )}
                     </div>

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
                           <p id="register-email-error" className="field-error">
                              {fieldErrors.email}
                           </p>
                        )}
                     </div>

                     <div className="input-group">
                        <label htmlFor="register-password">Password</label>

                        <div className="input-wrapper">
                           <Icons name="shield" size={18} className="input-icon" />

                           <input
                              id="register-password"
                              type={showPassword ? "text" : "password"}
                              name="password"
                              autoComplete="new-password"
                              placeholder="••••••••"
                              value={formValues.password}
                              onChange={handleInputChange}
                              aria-invalid={Boolean(fieldErrors.password)}
                              aria-describedby={fieldErrors.password ? "register-password-error" : undefined}
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
                              <Icons name={showPassword ? "eye-off" : "eye"} size={16} />
                              {showPassword ? "Hide" : "Show"}
                           </button>
                        </div>

                        {fieldErrors.password && (
                           <p id="register-password-error" className="field-error">
                              {fieldErrors.password}
                           </p>
                        )}
                     </div>

                     <button type="submit" className="submit-btn" disabled={isSigningIn}>
                        {!isSigningIn && (
                           <>
                              CREATE ACCOUNT <Icons name="arrow-right" size={18} />
                           </>
                        )}
                        {isSigningIn && (
                           <>
                              <div className="sign-in-loading">
                                 <span className="sign-in-spinner"></span>
                                 <p>Creating Account...</p>
                              </div>
                           </>
                        )}
                     </button>
                  </form>

                  <div className="signin-prompt">
                     Already registered?{" "}
                     <Link to="/login" state={{ from: location.state?.from }}>
                        Sign In
                     </Link>
                  </div>

                  <div className="divider">
                     <span>OR CONTINUE WITH</span>
                  </div>

                  <div className="social-login">
                     <button
                        type="button"
                        className="social-btn"
                        onClick={() => loginWithGoogle()}
                        disabled={isSigningIn}
                     >
                        <span className="social-icon">G</span> Google
                     </button>
                  </div>
               </div>
            </div>
         </div>
      </>
   );
}

export default RegisterPage;
