import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, useLocation, Link } from "react-router-dom";
import LogoImage from "../assets/truthlens_logo.png";
import Icons from "../components/Icons.jsx";
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

   const handleInputChange = (event) => {
      const { name, value } = event.target;
      setFormValues({
         ...formValues,
         [name]: value,
      });
   };

   const handleSubmit = async () => {
      const response = await fetch("http://localhost:8000/api/auth/register/", {
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
                     Create your account and start earning Trust Score by verifying claims alongside
                     a global community.
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

               <div className="register-footer-link">WWW.TRUTHLENS.APP</div>

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
                        className="submit-btn">
                        CREATE ACCOUNT{" "}
                        <Icons
                           name="arrow-right"
                           size={18}
                        />
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
                        className="social-btn">
                        <span className="social-icon">G</span> Google
                     </button>
                     <button
                        type="button"
                        className="social-btn">
                        <span className="social-icon">f</span> Facebook
                     </button>
                  </div>
               </div>
            </div>
         </div>
      </>
   );
}

export default RegisterPage;
