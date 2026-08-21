import React, { useState } from "react";
import "./LandingPage.css";
import LogoImage from "../assets/truthlens_logo.png";
import { Link } from "react-router-dom";

import {
   Shield,
   Download,
   ArrowDown,
   Image,
   ScanSearch,
   Scissors,
   Search,
   FileText,
   Zap,
   Users,
} from "lucide-react";

const TruthLens = () => {
   const [isMenuOpen, setIsMenuOpen] = useState(false);

   return (
      <div className="landing-page">
         {/* Navbar */}
         <nav className="navbar" aria-label="Main navigation">
            <div className="navbar-content">
               {/* Brand */}
               <Link
                  to="/landing-page"
                  className="navbar-brand"
                  aria-label="TruthLens home"
               >
                  <img src={LogoImage} alt="" className="navbar-logo" />

                  <span className="navbar-brand-name">TruthLens</span>
               </Link>

               {/* Desktop Navigation */}
               <div className="nav-links">
                  <a href="#features">Features</a>

                  <Link to="/community">Community</Link>

                  <a href="#about">About</a>
               </div>

               {/* Desktop Actions */}
               <div className="nav-actions">
                  <Link to="/login" className="login-btn">
                     Login
                  </Link>

                  <Link to="/register" className="get-started-btn">
                     Get Started
                  </Link>
               </div>

               {/* Mobile Menu Button */}
               <button
                  type="button"
                  className={`mobile-menu-toggle ${isMenuOpen ? "is-open" : ""}`}
                  aria-label={
                     isMenuOpen
                        ? "Close navigation menu"
                        : "Open navigation menu"
                  }
                  aria-expanded={isMenuOpen}
                  aria-controls="mobile-navigation"
                  onClick={() => setIsMenuOpen((prev) => !prev)}
               >
                  <span></span>
                  <span></span>
                  <span></span>
               </button>

               {/* Mobile Navigation */}
               <div
                  id="mobile-navigation"
                  className={`mobile-navigation ${isMenuOpen ? "is-open" : ""}`}
               >
                  <a href="#features" onClick={() => setIsMenuOpen(false)}>
                     Features
                  </a>

                  <Link to="/community" onClick={() => setIsMenuOpen(false)}>
                     Community
                  </Link>

                  <a href="#about" onClick={() => setIsMenuOpen(false)}>
                     About
                  </a>

                  <div className="mobile-nav-actions">
                     <Link
                        to="/login"
                        className="login-btn"
                        onClick={() => setIsMenuOpen(false)}
                     >
                        Login
                     </Link>

                     <Link
                        to="/register"
                        className="get-started-btn"
                        onClick={() => setIsMenuOpen(false)}
                     >
                        Get Started
                     </Link>
                  </div>
               </div>
            </div>
         </nav>

         {/* Hero Section */}
         <section className="hero-section">
            <div className="hero-container">
               {/* Hero Content */}
               <div className="hero-content">
                  <div className="hero-badge">
                     <Shield size={15} strokeWidth={2} aria-hidden="true" />
                     AI-POWERED MEDIA LITERACY
                  </div>

                  <h1 className="hero-title">
                     Verify what you see.
                     <span className="hero-highlight">
                        Understand what you share.
                     </span>
                  </h1>

                  <p className="hero-subtitle">
                     TruthLens helps you investigate suspicious images, claims,
                     and online content directly from your browser using
                     AI-assisted analysis and supporting evidence.
                  </p>

                  {/* Primary Actions */}
                  <div className="hero-buttons">
                     <a
                        href="https://chromewebstore.google.com/detail/truthlens/dhkeknpnigghagekhdcpknbggfpbmkgo"
                        className="download-btn"
                        target="_blank"
                        rel="noopener noreferrer"
                     >
                        <Download
                           size={18}
                           strokeWidth={2}
                           aria-hidden="true"
                        />
                        Add to Chrome
                     </a>

                     <a href="#how-it-works" className="demo-btn">
                        <ArrowDown
                           size={18}
                           strokeWidth={2}
                           aria-hidden="true"
                        />
                        See how it works
                     </a>
                  </div>

                  {/* Product Capability Strip */}
                  <div className="hero-capabilities">
                     <div className="hero-capability">
                        <div className="capability-icon">
                           <svg
                              width="16"
                              height="16"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              aria-hidden="true"
                           >
                              <rect x="3" y="3" width="18" height="18" rx="2" />
                              <circle cx="8.5" cy="8.5" r="1.5" />
                              <polyline points="21 15 16 10 5 21" />
                           </svg>
                        </div>

                        <span>Image verification</span>
                     </div>

                     <div className="hero-capability">
                        <div className="capability-icon">
                           <svg
                              width="16"
                              height="16"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              aria-hidden="true"
                           >
                              <path d="M4 4h6v6H4z" />
                              <path d="M14 14h6v6h-6z" />
                              <path d="m14 4 6 6" />
                              <path d="M20 4v6h-6" />
                              <path d="m4 20 6-6" />
                              <path d="M4 14v6h6" />
                           </svg>
                        </div>

                        <span>Claim analysis</span>
                     </div>

                     <div className="hero-capability">
                        <div className="capability-icon">
                           <svg
                              width="16"
                              height="16"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              aria-hidden="true"
                           >
                              <circle cx="12" cy="12" r="9" />
                              <path d="M12 8v4l3 2" />
                           </svg>
                        </div>

                        <span>Evidence-aware results</span>
                     </div>
                  </div>
               </div>

               {/* Hero Product Visualization */}
               <div className="hero-visual">
                  <div className="hero-visual-glow"></div>

                  <div className="extension-window">
                     {/* Extension Header */}
                     <div className="extension-header">
                        <div className="extension-brand">
                           <img
                              src={LogoImage}
                              alt=""
                              className="extension-logo"
                           />

                           <span>TruthLens</span>
                        </div>

                        <div className="extension-status">
                           <span className="status-dot"></span>
                           Ready
                        </div>
                     </div>

                     {/* Extension Content */}
                     <div className="extension-body">
                        <div className="extension-intro">
                           <span className="extension-eyebrow">
                              VERIFY IMAGE
                           </span>

                           <h2>Check what you're seeing.</h2>

                           <p>
                              Select a suspicious image or claim on the page to
                              start an investigation.
                           </p>
                        </div>

                        {/* Snipping Action */}
                        <div className="verification-card">
                           <div className="verification-icon">
                              <Image
                                 size={26}
                                 strokeWidth={1.8}
                                 aria-hidden="true"
                              />
                           </div>

                           <div className="verification-copy">
                              <strong>Verify Image</strong>

                              <span>Draw a box around the claim</span>
                           </div>
                        </div>

                        <button
                           type="button"
                           className="extension-snip-button"
                           aria-label="Start snipping"
                        >
                           <Scissors
                              size={17}
                              strokeWidth={2}
                              aria-hidden="true"
                           />
                           Start Snipping
                        </button>

                        {/* Other Extension Capabilities */}
                        <div className="extension-tools">
                           <div className="extension-tool">
                              <span className="tool-icon">
                                 <Search
                                    size={15}
                                    strokeWidth={2}
                                    aria-hidden="true"
                                 />
                              </span>

                              <span>Analyze URL</span>

                              <span className="tool-arrow">→</span>
                           </div>

                           <div className="extension-tool">
                              <span className="tool-icon">
                                 <FileText
                                    size={15}
                                    strokeWidth={2}
                                    aria-hidden="true"
                                 />
                              </span>

                              <span>Upload File</span>

                              <span className="tool-arrow">→</span>
                           </div>

                           <div className="extension-tool">
                              <span className="tool-icon">
                                 <ScanSearch
                                    size={15}
                                    strokeWidth={2}
                                    aria-hidden="true"
                                 />
                              </span>

                              <span>Deepfake Detection</span>

                              <span className="tool-arrow">→</span>
                           </div>
                        </div>
                     </div>

                     {/* Extension Footer */}
                     <div className="extension-footer">
                        <span>TruthLens browser extension</span>

                        <span>AI-assisted verification</span>
                     </div>
                  </div>

                  {/* Decorative Floating Element */}
                  <div className="hero-floating-note">
                     <span className="floating-note-icon">✓</span>

                     <div>
                        <strong>Investigate before you share.</strong>
                        <span>Evidence first. Decisions second.</span>
                     </div>
                  </div>
               </div>
            </div>
         </section>

         {/* How It Works Section */}
         <section id="how-it-works" className="how-it-works">
            <div className="section-header">
               <span className="section-label">HOW IT WORKS</span>

               <h2 className="section-title">
                  Three steps to better-informed decisions
               </h2>

               <p className="section-description">
                  TruthLens helps you move from suspicious content to clearer
                  context through a simple verification workflow.
               </p>
            </div>

            <div className="steps-grid">
               {/* Step 1 */}
               <article className="step-card">
                  <div className="step-icon-wrapper">
                     <Scissors size={28} strokeWidth={1.8} aria-hidden="true" />
                  </div>

                  <span className="step-number">01 — SNIP</span>

                  <h3 className="step-title">Select the content</h3>

                  <p className="step-desc">
                     Capture a suspicious image or claim directly from the page
                     using the TruthLens browser extension.
                  </p>
               </article>

               {/* Step 2 */}
               <article className="step-card">
                  <div className="step-icon-wrapper">
                     <Zap size={28} strokeWidth={1.8} aria-hidden="true" />
                  </div>

                  <span className="step-number">02 — ANALYZE</span>

                  <h3 className="step-title">Analyze the evidence</h3>

                  <p className="step-desc">
                     TruthLens evaluates the submitted content using AI-assisted
                     analysis and supporting evidence.
                  </p>
               </article>

               {/* Step 3 */}
               <article className="step-card">
                  <div className="step-icon-wrapper">
                     <Users size={28} strokeWidth={1.8} aria-hidden="true" />
                  </div>

                  <span className="step-number">03 — UNDERSTAND</span>

                  <h3 className="step-title">Review the context</h3>

                  <p className="step-desc">
                     Examine the result, supporting context, and community
                     activity before deciding what to trust or share.
                  </p>
               </article>
            </div>
         </section>

         {/* Recent Investigations Section */}
         <section className="investigations-section">
            <div className="investigations-header">
               <div>
                  <span className="section-label">LIVE FROM THE COMMUNITY</span>
                  <h2 className="section-title">Recent Investigations</h2>
               </div>
               <button className="view-all-btn">View All →</button>
            </div>

            <div className="investigations-grid">
               {/* Card 1 */}
               <div className="inv-card">
                  <div className="inv-image border-fake">
                     <svg
                        width="24"
                        height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="#9ca3af"
                        strokeWidth="2"
                     >
                        <rect
                           x="3"
                           y="3"
                           width="18"
                           height="18"
                           rx="2"
                           ry="2"
                        />
                        <circle cx="8.5" cy="8.5" r="1.5" />
                        <polyline points="21 15 16 10 5 21" />
                     </svg>
                     <div className="inv-badge badge-fake outline">
                        <svg
                           width="12"
                           height="12"
                           viewBox="0 0 24 24"
                           fill="none"
                           stroke="currentColor"
                           strokeWidth="2"
                        >
                           <circle cx="12" cy="12" r="10" />
                           <line x1="15" y1="9" x2="9" y2="15" />
                           <line x1="9" y1="9" x2="15" y2="15" />
                        </svg>
                        Fake / False
                     </div>
                  </div>
                  <div className="inv-content">
                     <h3>Valencia flooding photo</h3>
                     <p>
                        Aerial photo is from 2021 Hurricane Ida, not 2024 Spain
                        floods.
                     </p>
                     <div className="ai-confidence">
                        <svg
                           width="14"
                           height="14"
                           viewBox="0 0 24 24"
                           fill="none"
                           stroke="currentColor"
                           strokeWidth="2"
                        >
                           <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                        </svg>
                        AI Confidence: <strong>94 %</strong>
                     </div>
                  </div>
               </div>

               {/* Card 2 */}
               <div className="inv-card">
                  <div className="inv-image border-misleading">
                     <svg
                        width="24"
                        height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="#9ca3af"
                        strokeWidth="2"
                     >
                        <rect
                           x="3"
                           y="3"
                           width="18"
                           height="18"
                           rx="2"
                           ry="2"
                        />
                        <circle cx="8.5" cy="8.5" r="1.5" />
                        <polyline points="21 15 16 10 5 21" />
                     </svg>
                     <div className="inv-badge badge-misleading outline">
                        <svg
                           width="12"
                           height="12"
                           viewBox="0 0 24 24"
                           fill="none"
                           stroke="currentColor"
                           strokeWidth="2"
                        >
                           <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                           <line x1="12" y1="9" x2="12" y2="13" />
                           <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                        Misleading
                     </div>
                  </div>
                  <div className="inv-content">
                     <h3>Mask effectiveness study</h3>
                     <p>
                        Study cited has not been peer-reviewed and contradicts
                        CDC guidelines.
                     </p>
                     <div className="ai-confidence">
                        <svg
                           width="14"
                           height="14"
                           viewBox="0 0 24 24"
                           fill="none"
                           stroke="currentColor"
                           strokeWidth="2"
                        >
                           <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                        </svg>
                        AI Confidence: <strong>62 %</strong>
                     </div>
                  </div>
               </div>

               {/* Card 3 */}
               <div className="inv-card">
                  <div className="inv-image border-fact">
                     <svg
                        width="24"
                        height="24"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="#9ca3af"
                        strokeWidth="2"
                     >
                        <rect
                           x="3"
                           y="3"
                           width="18"
                           height="18"
                           rx="2"
                           ry="2"
                        />
                        <circle cx="8.5" cy="8.5" r="1.5" />
                        <polyline points="21 15 16 10 5 21" />
                     </svg>
                     <div className="inv-badge badge-fact outline">
                        <svg
                           width="12"
                           height="12"
                           viewBox="0 0 24 24"
                           fill="none"
                           stroke="currentColor"
                           strokeWidth="2"
                        >
                           <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                           <polyline points="22 4 12 14.01 9 11.01" />
                        </svg>
                        Fact
                     </div>
                  </div>
                  <div className="inv-content">
                     <h3>Unemployment figures</h3>
                     <p>
                        BLS data confirms headline claim is accurate within
                        margin of error.
                     </p>
                     <div className="ai-confidence">
                        <svg
                           width="14"
                           height="14"
                           viewBox="0 0 24 24"
                           fill="none"
                           stroke="currentColor"
                           strokeWidth="2"
                        >
                           <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                        </svg>
                        AI Confidence: <strong>97 %</strong>
                     </div>
                  </div>
               </div>
            </div>
         </section>

         {/* Trust Score CTA */}
         <section className="trust-cta">
            <div className="trust-content">
               <div className="trust-circle">
                  <span className="score-number">82</span>
               </div>
               <span className="trust-label">TRUST SCORE</span>
               <h2>Build Your Trust Score</h2>
               <p>
                  Every piece of evidence you submit, every vote you cast — it
                  all builds your credibility score. Trusted contributors have
                  more weight in community decisions.
               </p>
               <button className="join-btn">Join the Community →</button>
            </div>
         </section>

         {/* Footer */}
         <footer className="footer">
            <div className="footer-content">
               <div className="footer-left">
                  <svg
                     width="24"
                     height="24"
                     viewBox="0 0 24 24"
                     fill="none"
                     xmlns="http://www.w3.org/2000/svg"
                     className="footer-logo"
                  >
                     <circle
                        cx="11"
                        cy="11"
                        r="8"
                        stroke="#ffffff"
                        strokeWidth="2.5"
                     />
                     <line
                        x1="16.5"
                        y1="16.5"
                        x2="21"
                        y2="21"
                        stroke="#ffffff"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                     />
                  </svg>
                  <span>
                     © 2025 TruthLens. Fighting misinformation together.
                  </span>
               </div>
               <div className="footer-links">
                  <a href="#privacy">Privacy</a>
                  <a href="#terms">Terms</a>
                  <a href="#contact">Contact</a>
               </div>
            </div>
         </footer>
      </div>
   );
};

export default TruthLens;
