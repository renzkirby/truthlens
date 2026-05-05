/**
 * Login Page (Authentication)
 * ══════════════════════════════════════════════════════════════════
 * User authentication interface for existing TruthLens members.
 *
 * Features:
 *   - Email/username and password authentication
 *   - Remember me toggling for persistent sessions
 *   - Show/hide password toggle
 *   - Forgot password link (placeholder)
 *   - Social login options (placeholder)
 *   - Redirect to requested page after login
 *
 * State:
 *   - Form inputs: username, password, remember_me
 *   - UI state: showPassword, isSigningIn
 *   - Error handling for failed logins
 */

import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, useLocation, Link } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "../components/Icons.jsx";
import { useGoogleLogin } from "@react-oauth/google";

// ── Utilities & Constants ──
import { useEndpoint } from "../utils/api";

// ── Styles ──
import "./LoginPage.css";

function LoginPage() {
   const { login, user, loading } = useAuth();
   const navigate = useNavigate();
   const location = useLocation();
   const [showPassword, setShowPassword] = useState(false);
   const [isSigningIn, setIsSigningIn] = useState(false);
   const [justLoggedIn, setJustLoggedIn] = useState(false);
   const loginEndpoint = useEndpoint("LOGIN");
   const googleLoginEndpoint = useEndpoint("GOOGLE_LOGIN");
   const from = location.state?.from
      ? location.state.from.pathname + location.state.from.search
      : null;

   const [error, setError] = useState(null);
   const [formValues, setFormValues] = useState({
      username: "",
      password: "",
      remember_me: false,
   });

   // When user data loads after login, redirect to appropriate dashboard
   useEffect(() => {
      if (justLoggedIn && user && !loading) {
         setJustLoggedIn(false);
         const isModerator = user.role === "MOD" || user.role === "MODERATOR";
         const destination = from || (isModerator ? "/moderation" : "/");
         navigate(destination, { replace: true });
      }
   }, [user, loading, justLoggedIn, from, navigate]);

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
            login(data.access, data.refresh);
            setJustLoggedIn(true); // Flag that we're waiting for user data to load
            return;
         }

         setError(data?.detail || "Invalid credentials. Please try again.");
      } catch (err) {
         setError("Unable to sign in right now. Please try again.");
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
               login(data.access, data.refresh);
               setJustLoggedIn(true);
               return;
            }

            setError(data?.detail || "Unable to sign in with Google right now. Please try again.");
         } catch (err) {
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
         <div className="login-layout">
            {/* Left Side: Branding and Stats */}
            <div className="login-left">
               <div className="login-logo">
                  <img
                     src={LogoImage}
                     alt="TruthLens Logo"
                     style={{ height: "40px", width: "auto" }}
                  />
                  <span className="logo-text">TruthLens</span>
               </div>

               <div className="login-hero">
                  <h1 className="hero-title">
                     The Internet
                     <br />
                     Deserves
                     <br />
                     the Truth.
                  </h1>
                  <p className="hero-subtitle">
                     Welcome back. Your community is counting on you to keep the information
                     ecosystem honest.
                  </p>
               </div>

               <div className="login-stats">
                  <div className="stat-pill">
                     <div className="stat-icon">
                        <Icons
                           name="scan-line"
                           size={20}
                        />
                     </div>
                     <div className="stat-info">
                        <span className="stat-number">128K+</span>
                        <span className="stat-label">Claims Analyzed</span>
                     </div>
                  </div>
                  <div className="stat-pill">
                     <div className="stat-icon">
                        <Icons
                           name="check-circle"
                           size={20}
                        />
                     </div>
                     <div className="stat-info">
                        <span className="stat-number">94K+</span>
                        <span className="stat-label">Facts Verified</span>
                     </div>
                  </div>
                  <div className="stat-pill">
                     <div className="stat-icon">
                        <Icons
                           name="users"
                           size={20}
                        />
                     </div>
                     <div className="stat-info">
                        <span className="stat-number">32K+</span>
                        <span className="stat-label">Community Members</span>
                     </div>
                  </div>
               </div>

               <div className="login-footer-link">WWW.TRUTHLENS-DEV.VERCEL.APP</div>

               {/* Background Decorative Circles */}
               <div className="bg-circle circle-1"></div>
               <div className="bg-circle circle-2"></div>
               <div className="bg-circle circle-3"></div>
            </div>

            {/* Right Side: Login Form */}
            <div className="login-right">
               <div className="form-container">
                  <div className="form-header">
                     <p className="greeting-text">Hello! Welcome back.</p>
                     <h2 className="form-title">
                        <span>Sign in</span> to your account
                     </h2>
                  </div>

                  <form
                     onSubmit={(e) => {
                        e.preventDefault();
                        handleSubmit();
                     }}>
                     {error && (
                        <div className="error-message">
                           <Icons
                              name="alert-triangle"
                              size={16}
                           />{" "}
                           {error}
                        </div>
                     )}

                     <div className="input-group">
                        <label>Email Address / Username</label>
                        <div className="input-wrapper">
                           <Icons
                              name="mail"
                              size={18}
                              className="input-icon"
                           />
                           <input
                              type="text"
                              name="username"
                              placeholder="you@example.com"
                              value={formValues.username}
                              onChange={handleInputChange}
                              required
                           />
                        </div>
                     </div>

                     <div className="input-group">
                        <label>Password</label>
                        <div className="input-wrapper">
                           <Icons
                              name="shield"
                              size={18}
                              className="input-icon"
                           />
                           <input
                              type={showPassword ? "text" : "password"}
                              name="password"
                              placeholder="••••••••"
                              value={formValues.password}
                              onChange={handleInputChange}
                              required
                           />
                           <button
                              type="button"
                              className="show-password-btn"
                              onClick={() => setShowPassword(!showPassword)}>
                              <Icons
                                 name={showPassword ? "eye-off" : "eye"}
                                 size={16}
                              />
                              {showPassword ? "Hide" : "Show"}
                           </button>
                        </div>
                     </div>

                     <div className="form-options">
                        <label className="remember-me">
                           <input
                              type="checkbox"
                              checked={formValues.remember_me}
                              onChange={handleCheckbox}
                           />
                           <span>Remember me</span>
                        </label>
                        <a
                           href="#"
                           className="forgot-password">
                           Forgot Password?
                        </a>
                     </div>

                     <button
                        type="submit"
                        className="submit-btn"
                        disabled={isSigningIn}>
                        {!isSigningIn && (
                           <>
                              SIGN IN{" "}
                              <Icons
                                 name="arrow-right"
                                 size={18}
                              />
                           </>
                        )}
                        {isSigningIn && (
                           <>
                              <div className="sign-in-loading">
                                 <span className="sign-in-spinner"></span>
                                 <p>Signing In...</p>
                              </div>
                           </>
                        )}
                     </button>
                  </form>

                  <div className="signup-prompt">
                     Don't have an account?{" "}
                     <Link
                        to="/register"
                        state={{ from: location.state?.from }}>
                        Create Account
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
                        disabled={isSigningIn}>
                        <span className="social-icon">G</span> Google
                     </button>
                  </div>
               </div>
            </div>
         </div>
      </>
   );
}

export default LoginPage;
