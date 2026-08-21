import React, { useState } from "react";
import "./LandingPage.css";
import LogoImage from "../assets/truthlens_logo.png";
import { Link } from "react-router-dom";

import {
   Shield,
   ShieldCheck,
   Download,
   ArrowDown,
   Image,
   ScanSearch,
   Scissors,
   Search,
   SearchCheck,
   FileText,
   Zap,
   Users,
   BrainCircuit,
   BookOpenCheck,
   MessagesSquare,
   PanelsTopLeft,
   Scale,
   Target,
   Eye,
   UsersRound,
   ArrowRight,
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

         {/* Features Section */}
         <section id="features" className="features-section">
            <div className="features-container">
               <div className="features-header">
                  <span className="section-label">FEATURES</span>

                  <h2 className="features-title">
                     Built to help you question what you see online.
                  </h2>

                  <p className="features-description">
                     TruthLens combines AI-assisted analysis, supporting
                     evidence, community participation, and browser-based tools
                     to help you investigate questionable content with more
                     context.
                  </p>
               </div>

               <div className="features-grid">
                  {/* Claim Analysis */}
                  <article className="feature-card">
                     <div className="feature-card-header">
                        <div className="feature-icon">
                           <BrainCircuit
                              size={27}
                              strokeWidth={1.8}
                              aria-hidden="true"
                           />
                        </div>

                        <span className="feature-index">01</span>
                     </div>

                     <h3 className="feature-title">Claim Analysis</h3>

                     <p className="feature-description">
                        Investigate suspicious claims, images, URLs, and other
                        supported content using AI-assisted verification.
                     </p>

                     <div className="feature-meta">
                        <span>Images</span>
                        <span>Claims</span>
                        <span>URLs</span>
                     </div>
                  </article>

                  {/* Evidence */}
                  <article className="feature-card">
                     <div className="feature-card-header">
                        <div className="feature-icon">
                           <BookOpenCheck
                              size={27}
                              strokeWidth={1.8}
                              aria-hidden="true"
                           />
                        </div>

                        <span className="feature-index">02</span>
                     </div>

                     <h3 className="feature-title">Evidence & Context</h3>

                     <p className="feature-description">
                        Go beyond a simple verdict by reviewing supporting
                        sources, explanations, and additional context behind an
                        analysis.
                     </p>

                     <div className="feature-meta">
                        <span>Sources</span>
                        <span>Context</span>
                        <span>Evidence</span>
                     </div>
                  </article>

                  {/* Community */}
                  <article className="feature-card">
                     <div className="feature-card-header">
                        <div className="feature-icon">
                           <MessagesSquare
                              size={27}
                              strokeWidth={1.8}
                              aria-hidden="true"
                           />
                        </div>

                        <span className="feature-index">03</span>
                     </div>

                     <h3 className="feature-title">Community Verification</h3>

                     <p className="feature-description">
                        Participate in investigations, contribute evidence, and
                        help provide additional context when claims need human
                        review.
                     </p>

                     <div className="feature-meta">
                        <span>Evidence</span>
                        <span>Discussion</span>
                        <span>Review</span>
                     </div>
                  </article>

                  {/* Extension */}
                  <article className="feature-card feature-card-highlight">
                     <div className="feature-card-header">
                        <div className="feature-icon">
                           <PanelsTopLeft
                              size={27}
                              strokeWidth={1.8}
                              aria-hidden="true"
                           />
                        </div>

                        <span className="feature-index">04</span>
                     </div>

                     <h3 className="feature-title">Browser Extension</h3>

                     <p className="feature-description">
                        Start an investigation directly from the content you're
                        browsing without leaving the page to begin the process.
                     </p>

                     <div className="feature-meta">
                        <span>Chrome</span>
                        <span>Snipping</span>
                        <span>On-page</span>
                     </div>
                  </article>
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

         {/* Trust & Transparency Section */}
         <section id="trust" className="trust-section">
            <div className="trust-container">
               {/* Section Introduction */}
               <div className="trust-intro">
                  <span className="section-label">TRUST & TRANSPARENCY</span>

                  <h2 className="trust-title">
                     Trust the process, not just the verdict.
                  </h2>

                  <p className="trust-description">
                     TruthLens is designed to give you more than a label.
                     Analysis is supported by context, evidence, and
                     opportunities for human review so you can better understand
                     how a result was reached.
                  </p>

                  <div className="trust-principle">
                     <ShieldCheck
                        size={20}
                        strokeWidth={1.8}
                        aria-hidden="true"
                     />

                     <p>
                        AI assists the investigation. Evidence and human
                        judgment provide additional context when a claim needs
                        closer review.
                     </p>
                  </div>
               </div>

               {/* Transparency Principles */}
               <div className="trust-grid">
                  {/* Evidence */}
                  <article className="trust-card">
                     <div className="trust-card-icon">
                        <SearchCheck
                           size={25}
                           strokeWidth={1.8}
                           aria-hidden="true"
                        />
                     </div>

                     <div className="trust-card-content">
                        <span className="trust-card-label">EVIDENCE</span>

                        <h3>Evidence-first results</h3>

                        <p>
                           Supporting sources and relevant context help you look
                           beyond the verdict and examine the information behind
                           it.
                        </p>
                     </div>
                  </article>

                  {/* Explainability */}
                  <article className="trust-card">
                     <div className="trust-card-icon">
                        <BrainCircuit
                           size={25}
                           strokeWidth={1.8}
                           aria-hidden="true"
                        />
                     </div>

                     <div className="trust-card-content">
                        <span className="trust-card-label">EXPLAINABILITY</span>

                        <h3>Understand the analysis</h3>

                        <p>
                           TruthLens provides explanations and context so
                           results are easier to evaluate instead of presenting
                           a verdict as a black box.
                        </p>
                     </div>
                  </article>

                  {/* Community */}
                  <article className="trust-card">
                     <div className="trust-card-icon">
                        <MessagesSquare
                           size={25}
                           strokeWidth={1.8}
                           aria-hidden="true"
                        />
                     </div>

                     <div className="trust-card-content">
                        <span className="trust-card-label">COMMUNITY</span>

                        <h3>More perspectives when needed</h3>

                        <p>
                           Users can contribute evidence and discussion when a
                           claim needs additional context or closer examination.
                        </p>
                     </div>
                  </article>

                  {/* Moderation */}
                  <article className="trust-card">
                     <div className="trust-card-icon">
                        <Scale size={25} strokeWidth={1.8} aria-hidden="true" />
                     </div>

                     <div className="trust-card-content">
                        <span className="trust-card-label">OVERSIGHT</span>

                        <h3>Moderator-reviewed resolutions</h3>

                        <p>
                           Moderation provides an additional review layer for
                           disputed investigations and verified community
                           evidence.
                        </p>
                     </div>
                  </article>
               </div>
            </div>
         </section>

         {/* About / Mission Section */}
         <section id="about" className="about-section">
            <div className="about-container">
               {/* Mission Content */}
               <div className="about-content">
                  <span className="section-label">OUR MISSION</span>

                  <h2 className="about-title">
                     Better information starts with better questions.
                  </h2>

                  <p className="about-lead">
                     TruthLens was created to help people slow down, investigate
                     questionable content, and make more informed decisions
                     before believing or sharing what they encounter online.
                  </p>

                  <p className="about-description">
                     We believe verification should provide more than a verdict.
                     People should be able to examine context, supporting
                     evidence, and different perspectives while understanding
                     the role AI plays in the analysis.
                  </p>
               </div>

               {/* Mission Principles */}
               <div className="about-principles">
                  <div className="about-principle">
                     <div className="about-principle-icon">
                        <Eye size={24} strokeWidth={1.8} aria-hidden="true" />
                     </div>

                     <div>
                        <span className="about-principle-label">QUESTION</span>

                        <h3>Look beyond the first impression</h3>

                        <p>
                           Suspicious content deserves examination before it
                           becomes something we accept or pass along.
                        </p>
                     </div>
                  </div>

                  <div className="about-principle">
                     <div className="about-principle-icon">
                        <Target
                           size={24}
                           strokeWidth={1.8}
                           aria-hidden="true"
                        />
                     </div>

                     <div>
                        <span className="about-principle-label">
                           UNDERSTAND
                        </span>

                        <h3>Context matters</h3>

                        <p>
                           A useful verification process should help explain
                           what is known, what is uncertain, and what evidence
                           supports the result.
                        </p>
                     </div>
                  </div>

                  <div className="about-principle">
                     <div className="about-principle-icon">
                        <UsersRound
                           size={24}
                           strokeWidth={1.8}
                           aria-hidden="true"
                        />
                     </div>

                     <div>
                        <span className="about-principle-label">
                           PARTICIPATE
                        </span>

                        <h3>Verification is not only automated</h3>

                        <p>
                           AI can assist the process, while community
                           participation and human review can provide additional
                           perspective when needed.
                        </p>
                     </div>
                  </div>
               </div>
            </div>

            {/* Mission Statement */}
            <div className="about-statement">
               <div className="about-statement-inner">
                  <span>TruthLens exists to encourage one simple habit:</span>

                  <strong>investigate before you amplify.</strong>
               </div>
            </div>
         </section>

         {/* Final CTA Section */}
         <section className="final-cta">
            <div className="final-cta-container">
               <div className="final-cta-content">
                  <span className="final-cta-label">READY TO INVESTIGATE?</span>

                  <h2 className="final-cta-title">
                     See something suspicious?
                     <span>Check it before you share it.</span>
                  </h2>

                  <p className="final-cta-description">
                     Add TruthLens to Chrome to start investigating questionable
                     content directly from your browser, or create an account to
                     participate in the wider verification community.
                  </p>

                  <div className="final-cta-actions">
                     <a
                        href="https://chromewebstore.google.com/detail/truthlens/dhkeknpnigghagekhdcpknbggfpbmkgo"
                        className="final-cta-primary"
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

                     <Link to="/register" className="final-cta-secondary">
                        Create an account
                        <ArrowRight
                           size={18}
                           strokeWidth={2}
                           aria-hidden="true"
                        />
                     </Link>
                  </div>

                  <div className="final-cta-note">
                     <ShieldCheck
                        size={16}
                        strokeWidth={1.8}
                        aria-hidden="true"
                     />

                     <span>
                        AI-assisted verification with supporting evidence and
                        human review.
                     </span>
                  </div>
               </div>
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
