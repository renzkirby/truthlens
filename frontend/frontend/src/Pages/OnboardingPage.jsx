/**
 * First-time authenticated-user onboarding flow.
 *
 * - Five-step product introduction
 * - Account-level completion persisted by the backend
 * - Can be completed or skipped once
 * - Preserves the destination that initiated registration
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
      subtitle: "A better way to investigate questionable information.",
      body: "TruthLens combines AI-assisted analysis with community evidence to help you evaluate claims before deciding what to trust or share. Here's a quick look at the tools available to you.",
      visual: "welcome",
   },
   {
      id: "extension",
      label: "Extension",
      icon: "puzzle",
      accentColor: "#0e9f6e",
      accentBg: "#d1fae5",
      title: () => "Investigate Without Leaving the Page",
      subtitle: "Use the TruthLens Chrome extension while browsing the web.",
      body: "Analyze supported pages, URLs, images, and selected content directly from your browser. TruthLens returns an AI-assisted verdict, supporting information, and a confidence indicator when available.",
      visual: "extension",
   },
   {
      id: "web",
      label: "Analysis",
      icon: "scan-line",
      accentColor: "#7c3aed",
      accentBg: "#ede9fe",
      title: () => "Explore the Full Analysis",
      subtitle: "Review more context, evidence, and sources behind a result.",
      body: "TruthLens lets you inspect analyzed claims in more detail, including available evidence, source information, confidence signals, and the reasoning behind the result.",
      visual: "verify",
   },
   {
      id: "community",
      label: "Community",
      icon: "users",
      accentColor: "#d97706",
      accentBg: "#fef3c7",
      title: () => "Add Human Evidence",
      subtitle: "Some claims benefit from more than automated analysis.",
      body: "Community investigations let contributors discuss claims, submit evidence, and evaluate supporting material. Meaningful participation contributes to your reputation and Trust Score on TruthLens.",
      visual: "community",
   },
   {
      id: "ready",
      label: "Ready",
      icon: "rocket",
      accentColor: "var(--brand-primary)",
      accentBg: "#ede9fe",
      title: (username) => `You're ready${username ? `, @${username}` : ""}.`,
      subtitle: "Start investigating with the tools that brought you here.",
      body: "You can explore community investigations, review a full analysis, or continue the action you started before creating your account.",
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
               <span className="ob-result-conf">Confidence indicator</span>
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
                     <span>Supporting source</span>
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
            <div className="ob-ready-actions">
               <div className="ob-ready-item">
                  <Icons name="scan-line" size={16} />
                  <span>Review detailed analysis</span>
               </div>

               <div className="ob-ready-item">
                  <Icons name="users" size={16} />
                  <span>Join community investigations</span>
               </div>

               <div className="ob-ready-item">
                  <Icons name="puzzle" size={16} />
                  <span>Use TruthLens while browsing</span>
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

   return (
      <div className="ob-page">
         {/* Skip button — always visible except on last step */}
         {!isLast && (
            <button className="ob-skip-btn" onClick={handleSkip} disabled={isCompleting}>
               {isCompleting ? "Finishing..." : "Skip introduction"}
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
                     {isLast ? (isCompleting ? "Finishing..." : "Continue to TruthLens") : "Next"}
                  </button>
               </div>

               {/* Dot indicators */}
               <nav className="ob-dots" aria-label="Onboarding steps">
                  {STEPS.map((s, i) => (
                     <button
                        key={s.id}
                        type="button"
                        aria-current={i === currentStep ? "step" : undefined}
                        aria-label={`Go to step ${i + 1}: ${s.label}`}
                        className={`ob-dot ${i === currentStep ? "ob-dot--active" : ""} ${
                           i < currentStep ? "ob-dot--done" : ""
                        }`}
                        style={
                           i <= currentStep
                              ? {
                                   backgroundColor: s.accentColor,
                                }
                              : {}
                        }
                        onClick={() => handleDotClick(i)}
                     />
                  ))}
               </nav>
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
