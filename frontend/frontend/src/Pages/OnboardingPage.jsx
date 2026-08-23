/**
 * OnboardingPage.jsx
 * ══════════════════════════════════════════════════════════════════
 * First-time user onboarding flow for TruthLens.
 *
 * Features:
 *   - 5-step guided tour of TruthLens features
 *   - Progress indicator with step dots
 *   - Skip option on every step
 *   - Completion stored in localStorage ("tl_onboarding_complete")
 *   - Redirects to /community on finish or skip
 *
 * Steps:
 *   1. Welcome — what TruthLens is
 *   2. Browser Extension — snipping tool and URL verifier
 *   3. Web Platform — Verify page
 *   4. Community & Trust Score — how contributions work
 *   5. Ready — CTA to get started
 */

import { useState } from "react";
import { Navigate, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import Icons from "../components/Icons.jsx";
import "./OnboardingPage.css";
import { resolveApiEndpoint } from "../utils/api";

// ── Step Definitions ──────────────────────────────────────────────
const STEPS = [
   {
      id: "welcome",
      label: "Welcome",
      icon: "sparkles",
      accentColor: "var(--brand-primary)",
      accentBg: "#ede9fe",
      title: (username) => `Welcome to TruthLens${username ? `, @${username}` : ""}!`,
      subtitle: "You've just joined a community dedicated to fighting misinformation — one claim at a time.",
      body: "TruthLens is an AI-powered fact-checking platform that helps you verify what's real and what's fake before you share it. In the next few steps, we'll show you exactly how it works.",
      visual: "welcome",
   },
   {
      id: "extension",
      label: "Extension",
      icon: "puzzle",
      accentColor: "#0e9f6e",
      accentBg: "#d1fae5",
      title: () => "Verify Anything, Anywhere",
      subtitle: "The TruthLens Chrome extension lets you fact-check without leaving your feed.",
      body: "Use the Snipping Tool to draw a box over any suspicious image or post. The extension reads the text, runs it through our AI pipeline, and delivers a verdict — FACT, FAKE, MISLEADING, SATIRE, or UNVERIFIED — directly on the page.",
      visual: "extension",
   },
   {
      id: "web",
      label: "Web Platform",
      icon: "scan-line",
      accentColor: "#7c3aed",
      accentBg: "#ede9fe",
      title: () => "Verify on the Web Platform",
      subtitle: "Paste a URL or upload an image directly from your browser.",
      body: "Head to the Verify page to submit links and images without the extension. Our AI pipeline extracts the claim, cross-references it against live news sources and official fact-check databases, and returns a verdict with a confidence score and source citations.",
      visual: "verify",
   },
   {
      id: "community",
      label: "Community",
      icon: "users",
      accentColor: "#d97706",
      accentBg: "#fef3c7",
      title: () => "Your Voice Matters",
      subtitle: "When AI isn't sure, the community steps in.",
      body: "Claims that return UNVERIFIED are escalated to the Community Feed, where contributors like you can submit evidence, vote on its credibility, and help reach a final verdict. Every accurate contribution you make increases your Trust Score — your measure of credibility on the platform.",
      visual: "community",
   },
   {
      id: "ready",
      label: "Ready",
      icon: "rocket",
      accentColor: "var(--brand-primary)",
      accentBg: "#ede9fe",
      title: (username) => `You're all set${username ? `, @${username}` : ""}!`,
      subtitle: "Start fighting misinformation today.",
      body: "Explore the Community Feed to see what others are investigating, or head straight to the Verify page to fact-check your first claim. The truth is out there — let's find it together.",
      visual: "ready",
   },
];

// ── Visual Components per Step ────────────────────────────────────
function StepVisual({ type }) {
   if (type === "welcome") {
      return (
         <div className="ob-visual ob-visual--welcome">
            <div className="ob-lens-ring ob-lens-ring--outer" />
            <div className="ob-lens-ring ob-lens-ring--middle" />
            <div className="ob-lens-core">
               <Icons name="sparkles" size={36} color="var(--brand-primary)" />
            </div>
            <div className="ob-verdict-chip ob-chip--fact">
               <Icons name="check-circle" size={13} /> FACT
            </div>
            <div className="ob-verdict-chip ob-chip--fake">
               <Icons name="x-circle" size={13} /> FAKE
            </div>
            <div className="ob-verdict-chip ob-chip--misleading">
               <Icons name="alert-triangle" size={13} /> MISLEADING
            </div>
            <div className="ob-verdict-chip ob-chip--satire">
               <Icons name="wand" size={13} /> SATIRE
            </div>
            <div className="ob-verdict-chip ob-chip--unverified">
               <Icons name="help-circle" size={13} /> UNVERIFIED
            </div>
         </div>
      );
   }

   if (type === "extension") {
      return (
         <div className="ob-visual ob-visual--extension">
            <div className="ob-browser-mockup">
               <div className="ob-browser-bar">
                  <span className="ob-browser-dot" />
                  <span className="ob-browser-dot" />
                  <span className="ob-browser-dot" />
                  <div className="ob-browser-url">facebook.com/feed</div>
               </div>
               <div className="ob-browser-content">
                  <div className="ob-fake-post">
                     <div className="ob-post-header">
                        <div className="ob-post-avatar" />
                        <div className="ob-post-meta">
                           <div className="ob-skeleton ob-skeleton--name" />
                           <div className="ob-skeleton ob-skeleton--time" />
                        </div>
                     </div>
                     <div className="ob-skeleton ob-skeleton--line" />
                     <div className="ob-skeleton ob-skeleton--line ob-skeleton--short" />
                     <div className="ob-snip-overlay">
                        <Icons name="scissors" size={14} color="#4f46e5" />
                        <span>Snipping...</span>
                     </div>
                  </div>
               </div>
            </div>
            <div className="ob-result-card">
               <div className="ob-result-header">
                  <Icons name="scan-line" size={14} color="#4f46e5" />
                  <span>TruthLens</span>
               </div>
               <div className="ob-result-verdict ob-result-verdict--fake">
                  This post is <strong>FAKE</strong>
               </div>
               <div className="ob-result-bar">
                  <div className="ob-result-fill" style={{ width: "89%" }} />
               </div>
               <span className="ob-result-conf">89% confidence</span>
            </div>
         </div>
      );
   }

   if (type === "verify") {
      return (
         <div className="ob-visual ob-visual--verify">
            <div className="ob-verify-card">
               <div className="ob-verify-tabs">
                  <div className="ob-vtab ob-vtab--active">URL</div>
                  <div className="ob-vtab">Image</div>
                  <div className="ob-vtab">Text</div>
               </div>
               <div className="ob-verify-input">
                  <Icons name="link" size={14} color="#6b7280" />
                  <span className="ob-verify-placeholder">Paste a URL to verify...</span>
               </div>
               <div className="ob-verify-btn">
                  <Icons name="scan-line" size={14} color="#fff" />
                  Verify
               </div>
               <div className="ob-verify-result">
                  <div className="ob-verify-badge ob-verify-badge--misleading">MISLEADING</div>
                  <p className="ob-verify-summary">
                     The photo is real but was taken in 2019, not during the 2024 event.
                  </p>
                  <div className="ob-verify-source">
                     <Icons name="external-link" size={12} color="#6b7280" />
                     <span>Source: Reuters Fact Check</span>
                  </div>
               </div>
            </div>
         </div>
      );
   }

   if (type === "community") {
      return (
         <div className="ob-visual ob-visual--community">
            <div className="ob-thread-card">
               <div className="ob-thread-badge ob-thread-badge--unverified">UNVERIFIED</div>
               <p className="ob-thread-claim">"Viral photo shows flooding in Cebu — but is it from last week?"</p>
               <div className="ob-evidence-row">
                  <div className="ob-evidence-item">
                     <div className="ob-ev-avatar" />
                     <div className="ob-ev-text">
                        <div className="ob-skeleton ob-skeleton--ev-title" />
                        <div className="ob-skeleton ob-skeleton--ev-sub" />
                     </div>
                     <div className="ob-vote-pill ob-vote-pill--up">
                        <Icons name="thumbs-up" size={11} /> 12
                     </div>
                  </div>
                  <div className="ob-evidence-item">
                     <div className="ob-ev-avatar" />
                     <div className="ob-ev-text">
                        <div className="ob-skeleton ob-skeleton--ev-title" />
                        <div className="ob-skeleton ob-skeleton--ev-sub" />
                     </div>
                     <div className="ob-vote-pill ob-vote-pill--up">
                        <Icons name="thumbs-up" size={11} /> 8
                     </div>
                  </div>
               </div>
               <div className="ob-trust-row">
                  <Icons name="trophy" size={13} color="#d97706" />
                  <span>Your Trust Score increases with every accurate vote</span>
               </div>
            </div>
         </div>
      );
   }

   if (type === "ready") {
      return (
         <div className="ob-visual ob-visual--ready">
            <div className="ob-ready-ring">
               <Icons name="check-circle" size={48} color="#0e9f6e" />
            </div>
            <div className="ob-stats-row">
               <div className="ob-stat-chip">
                  <span className="ob-stat-num">12k+</span>
                  <span className="ob-stat-label">Claims Verified</span>
               </div>
               <div className="ob-stat-chip">
                  <span className="ob-stat-num">500+</span>
                  <span className="ob-stat-label">Contributors</span>
               </div>
               <div className="ob-stat-chip">
                  <span className="ob-stat-num">98%</span>
                  <span className="ob-stat-label">Accuracy</span>
               </div>
            </div>
         </div>
      );
   }

   return null;
}

// ── Main Component ────────────────────────────────────────────────
export default function OnboardingPage() {
   const [currentStep, setCurrentStep] = useState(0);
   const [exiting, setExiting] = useState(false);
   const [direction, setDirection] = useState("forward");
   const navigate = useNavigate();
   const { user, loading, authFetch, refreshUser } = useAuth();
   const onboardingCompleteEndpoint = resolveApiEndpoint("ONBOARDING_COMPLETE");
   const [isCompleting, setIsCompleting] = useState(false);
   const [completionError, setCompletionError] = useState("");

   const location = useLocation();

   const rawDestination = location.state?.from;

   const onboardingDestination =
      typeof rawDestination === "string"
         ? rawDestination
         : rawDestination?.pathname
           ? `${rawDestination.pathname}${rawDestination.search || ""}${rawDestination.hash || ""}`
           : "/community";

   const step = STEPS[currentStep];
   const isFirst = currentStep === 0;
   const isLast = currentStep === STEPS.length - 1;

   if (loading || !user) {
      return null;
   }

   if (user.has_completed_onboarding) {
      return <Navigate to={onboardingDestination} replace />;
   }

   const completeOnboarding = async () => {
      if (isCompleting) return;

      setIsCompleting(true);
      setCompletionError("");

      try {
         await authFetch(onboardingCompleteEndpoint, {
            method: "POST",
         });

         await refreshUser();

         navigate(onboardingDestination, {
            replace: true,
         });
      } catch (error) {
         console.error("Failed to complete onboarding:", error);

         setCompletionError("We couldn't finish onboarding right now. Please try again.");
      } finally {
         setIsCompleting(false);
      }
   };

   const goToStep = (nextIndex, dir = "forward") => {
      setDirection(dir);
      setExiting(true);
      setTimeout(() => {
         setCurrentStep(nextIndex);
         setExiting(false);
      }, 220);
   };

   const handleNext = () => {
      if (isLast) {
         completeOnboarding();
      } else {
         goToStep(currentStep + 1, "forward");
      }
   };

   const handleBack = () => {
      if (!isFirst) {
         goToStep(currentStep - 1, "back");
      }
   };

   const handleSkip = () => {
      completeOnboarding();
   };

   const handleDotClick = (index) => {
      if (index === currentStep) return;
      goToStep(index, index > currentStep ? "forward" : "back");
   };

   console.log("Onboarding received from:", location.state?.from);

   console.log("Onboarding destination:", onboardingDestination);

   return (
      <div className="ob-page">
         {/* Skip button — always visible except on last step */}
         {!isLast && (
            <button className="ob-skip-btn" onClick={handleSkip} disabled={isCompleting}>
               {isCompleting ? "Finishing..." : "Skip for now"}
            </button>
         )}

         {/* Step counter */}
         <div className="ob-step-counter">
            Step {currentStep + 1} of {STEPS.length}
         </div>

         {/* Main card */}
         <div
            className={`ob-card ${exiting ? (direction === "forward" ? "ob-card--exit-left" : "ob-card--exit-right") : "ob-card--enter"}`}
         >
            {/* Left — text content */}
            <div className="ob-content">
               {/* Icon badge */}
               <div className="ob-icon-badge" style={{ backgroundColor: step.accentBg, color: step.accentColor }}>
                  <Icons name={step.icon} size={22} color={step.accentColor} />
               </div>

               <h1 className="ob-title">{step.title(user?.username)}</h1>

               <p className="ob-subtitle">{step.subtitle}</p>

               <p className="ob-body">{step.body}</p>

               {completionError && (
                  <p className="ob-completion-error" role="alert">
                     {completionError}
                  </p>
               )}

               {/* Navigation */}
               <div className="ob-nav">
                  {!isFirst && (
                     <button className="ob-btn ob-btn--back" onClick={handleBack}>
                        <Icons name="arrow-left" size={16} />
                        Back
                     </button>
                  )}

                  <button
                     className="ob-btn ob-btn--next"
                     onClick={handleNext}
                     disabled={isCompleting}
                     style={{
                        backgroundColor: step.accentColor,
                     }}
                  >
                     {isLast ? (isCompleting ? "Finishing..." : "Go to Community Feed") : "Next"}
                  </button>
               </div>

               {/* Dot indicators */}
               <div className="ob-dots" role="tablist" aria-label="Onboarding steps">
                  {STEPS.map((s, i) => (
                     <button
                        key={s.id}
                        role="tab"
                        aria-selected={i === currentStep}
                        aria-label={`Step ${i + 1}: ${s.label}`}
                        className={`ob-dot ${i === currentStep ? "ob-dot--active" : ""} ${i < currentStep ? "ob-dot--done" : ""}`}
                        style={
                           i === currentStep
                              ? { backgroundColor: step.accentColor }
                              : i < currentStep
                                ? { backgroundColor: `${step.accentColor}60` }
                                : {}
                        }
                        onClick={() => handleDotClick(i)}
                     />
                  ))}
               </div>
            </div>

            {/* Right — visual */}
            <div className="ob-visual-panel">
               <StepVisual type={step.visual} />
            </div>
         </div>

         {/* Background decoration */}
         <div className="ob-bg-blob ob-bg-blob--1" />
         <div className="ob-bg-blob ob-bg-blob--2" />
      </div>
   );
}
