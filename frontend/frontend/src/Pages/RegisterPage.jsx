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
import { useAuth } from "../context/AuthContext";
import { useNavigate, useLocation, Link } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "../components/Icons.jsx";
import { useGoogleLogin } from "@react-oauth/google";

// ── Utilities & Constants ──
import { useEndpoint } from "../utils/api";

// ── Styles ──
import "./RegisterPage.css";

function RegisterPage() {
   const { login } = useAuth();
   const navigate = useNavigate();
   const location = useLocation();
   const from = location.state?.from
      ? location.state.from.pathname + location.state.from.search
      : "/community";
   const [error, setError] = useState(null);
   const [showPassword, setShowPassword] = useState(false);
   const [formValues, setFormValues] = useState({
      username: "",
      email: "",
      password: "",
   });

   const googleLoginEndpoint = useEndpoint("GOOGLE_LOGIN");
   const [isSigningIn, setIsSigningIn] = useState(false);

   // ── Google OAuth Hook ──
   const loginWithGoogle = useGoogleLogin({
      onSuccess: async (tokenResponse) => {
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

            if (response.ok && data?.access) {
               login(data.access, data.refresh);
               navigate(from, { replace: true });
               return;
            }

            setError(data?.detail || "Unable to register with Google right now. Please try again.");
         } catch (err) {
            setError("Unable to register with Google right now. Please try again.");
         } finally {
            setIsSigningIn(false);
         }
      },
      onError: () => {
         setError("Google sign-in failed. Please try again.");
         console.error("Google Sign-In Error");
      },
   });

   const handleInputChange = (event) => {
      const { name, value } = event.target;
      setFormValues({
         ...formValues,
         [name]: value,
      });
   };

   /**
    * Handle form submission and account creation
    * Posts credentials to backend, stores tokens, redirects on success
    */
   const handleSubmit = async () => {
      setIsSigningIn(true);
      setError(null);
      const registerEndpoint = useEndpoint("REGISTER");

      try {
         const response = await fetch(registerEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               username: formValues.username,
               email: formValues.email,
               password: formValues.password,
            }),
         });

         const data = await response.json();
         if (response.ok) {
            login(data.access, data.refresh);
            navigate(from, { replace: true });
         } else {
            setError(data.detail || "Something went wrong");
         }
      } catch (err) {
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
                  <img
                     src={LogoImage}
                     alt="TruthLens Logo"
                     style={{ height: "40px", width: "auto" }}
                  />
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
                     Create your account and start contributing by verifying claims alongside a
                     global community.
                  </p>
               </div>

               <div className="register-features">
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons
                           name="sparkles"
                           size={18}
                        />
                     </div>
                     <span>AI-powered claim detection in real time</span>
                  </div>
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons
                           name="users"
                           size={18}
                        />
                     </div>
                     <span>Community-driven evidence and voting</span>
                  </div>
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons
                           name="trophy"
                           size={18}
                        />
                     </div>
                     <span>Earn Trust Score for contributing verified facts</span>
                  </div>
                  <div className="feature-item">
                     <div className="feature-icon">
                        <Icons
                           name="globe"
                           size={18}
                        />
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
                        <label>Username</label>
                        <div className="input-wrapper">
                           <Icons
                              name="user"
                              size={18}
                              className="input-icon"
                           />
                           <input
                              type="text"
                              name="username"
                              placeholder="Choose a unique username..."
                              value={formValues.username}
                              onChange={handleInputChange}
                              required
                           />
                        </div>
                     </div>

                     <div className="input-group">
                        <label>Email Address</label>
                        <div className="input-wrapper">
                           <Icons
                              name="mail"
                              size={18}
                              className="input-icon"
                           />
                           <input
                              type="email"
                              name="email"
                              placeholder="you@example.com"
                              value={formValues.email}
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
                                 name="eye"
                                 size={16}
                              />
                              {showPassword ? "Hide" : "Show"}
                           </button>
                        </div>
                     </div>

                     <button
                        type="submit"
                        className="submit-btn"
                        disabled={isSigningIn}>
                        {!isSigningIn && (
                           <>
                              CREATE ACCOUNT{" "}
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
                                 <p>Creating Account...</p>
                              </div>
                           </>
                        )}
                     </button>
                  </form>

                  <div className="signin-prompt">
                     Already registered?{" "}
                     <Link
                        to="/login"
                        state={{ from: location.state?.from }}>
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

export default RegisterPage;
