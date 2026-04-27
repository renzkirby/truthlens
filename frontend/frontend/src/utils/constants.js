/**
 * Constants: constants.js
 * ══════════════════════════════════════════════════════════════════
 * Centralized configuration and constants used across the application.
 * Includes verdict configurations, options, and other shared constants.
 *
 * This eliminates duplication and makes updates easier—change once, updates everywhere.
 */

// ── Verdict Options ──
// Valid verdict values used throughout the app
export const VERDICT_OPTIONS = ["FACT", "FAKE", "MISLEADING", "SATIRE", "UNVERIFIED"];

// ── Thread Status Options ──
// Valid thread/moderation lifecycle states
export const STATUS_OPTIONS = ["OPEN", "CLOSED", "REJECTED", "PENDING"];

// ── Verdict Configuration ──
// Maps each verdict type to its visual properties (color, background, label)
// Used in Dashboard, CommunityFeed, ThreadDetailPage, ModerationPage
export const VERDICT_CONFIG = {
   FACT: {
      color: "var(--verdict-fact-text)",
      bg: "var(--verdict-fact-bg)",
      border: "var(--verdict-fact-border)",
      label: "Fact",
      desc: "This claim has been confirmed by trusted sources.",
      icon: "check-circle",
   },
   FAKE: {
      color: "var(--verdict-fake-text)",
      bg: "var(--verdict-fake-bg)",
      border: "var(--verdict-fake-border)",
      label: "Fake",
      desc: "This claim has been debunked.",
      icon: "x-circle",
   },
   MISLEADING: {
      color: "var(--verdict-misleading-text)",
      bg: "var(--verdict-misleading-bg)",
      border: "var(--verdict-misleading-border)",
      label: "Misleading",
      desc: "This claim contains partial truths but lacks context.",
      icon: "alert-triangle",
   },
   SATIRE: {
      color: "var(--verdict-satire-text)",
      bg: "var(--verdict-satire-bg)",
      border: "var(--verdict-satire-border)",
      label: "Satire",
      desc: "This is satire or parody content.",
      icon: "wand",
   },
   UNVERIFIED: {
      color: "var(--verdict-unverified-text)",
      bg: "var(--verdict-unverified-bg)",
      border: "var(--verdict-unverified-border)",
      label: "Unverified",
      desc: "Insufficient evidence to confirm or deny.",
      icon: "help-circle",
   },
   PENDING: {
      color: "var(--text-muted)",
      bg: "var(--bg-subtle)",
      border: "var(--border-default)",
      label: "Pending",
      desc: "Analysis in progress...",
      icon: "clock",
   },
};

// ── Action Text Mapping ──
// Maps verdict state to user-facing action text in community feed
export const ACTION_TEXT_MAP = {
   FACT: "Verified",
   FAKE: "Verified",
   MISLEADING: "Verified",
   SATIRE: "Verified",
   UNVERIFIED: "Needs Evidence",
   PENDING: "Processing",
};

// ── API Configuration ──
// Centralized API base URL (easily switch between environments)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

// Common API endpoints (relative paths)
export const API_ENDPOINTS = {
   // Auth & User
   LOGIN: "auth/login/",
   REGISTER: "auth/register/",
   PROFILE: "auth/profile/",
   MY_CLAIMS: "auth/my-claims/",
   GOOGLE_LOGIN: "auth/google/",

   // Claims & Threads
   CLAIMS: "claims/",
   THREADS: "threads/",

   // Moderation
   MOD_QUEUE: "moderation/queue/",
   MOD_VERDICT_QUEUE: "moderation/verdict-queue/",
   MOD_RESOLVE_THREAD: (threadId) => `moderation/threads/${threadId}/resolve/`,

   // Other
   POLLING: "polling/",
};

// ── Flag Reason Options ──
// Options for flagging/escalating claims to the community
// Maps verdict types to visual properties for flag selection buttons
export const ESCALATION_OPTIONS = [
   {
      value: "INCORRECT_VERDICT",
      label: "Incorrect Verdict",
      desc: "AI gave an incorrect or unverified verdict",
      icon: "alert-circle",
   },
   {
      value: "LOW_CONFIDENCE",
      label: "Low Confidence",
      desc: "AI confidence score is too low",
      icon: "bar-chart-2",
   },
   {
      value: "MISSING_CONTEXT",
      label: "Missing Context",
      desc: "The context provided is incomplete",
      icon: "help-circle",
   },
   {
      value: "OUTDATED_INFO",
      label: "Outdated Information",
      desc: "The analysis relied on outdated news",
      icon: "clock",
   },
   {
      value: "OTHER",
      label: "Other",
      desc: "Other miscellaneous reasons",
      icon: "more-horizontal",
   },
];

// ── Verdict Colors Mapping ──
// Simple color lookup for verdict values (used in results, badges, etc.)
export const VERDICT_COLORS = {
   FACT: VERDICT_CONFIG.FACT.color,
   FAKE: VERDICT_CONFIG.FAKE.color,
   MISLEADING: VERDICT_CONFIG.MISLEADING.color,
   SATIRE: VERDICT_CONFIG.SATIRE.color,
   UNVERIFIED: VERDICT_CONFIG.UNVERIFIED.color,
   PENDING: VERDICT_CONFIG.PENDING.color,
};

// ── Moderation State Transitions ──
// Valid status transitions for moderation workflow
export const MODERATION_TRANSITIONS = {
   PENDING: new Set(["OPEN", "CLOSED", "REJECTED"]),
   OPEN: new Set(["CLOSED", "REJECTED"]),
   CLOSED: new Set(["OPEN"]),
   REJECTED: new Set([]),
};

// ── Verdict Metadata (Lowercase) ──
// Maps lowercase verdict names to their configuration (for case-insensitive lookups)
export const VERDICT_META = {
   fact: VERDICT_CONFIG.FACT,
   fake: VERDICT_CONFIG.FAKE,
   misleading: VERDICT_CONFIG.MISLEADING,
   satire: VERDICT_CONFIG.SATIRE,
   unverified: VERDICT_CONFIG.UNVERIFIED,
   pending: VERDICT_CONFIG.PENDING,
};

// ── Evidence Verdict Metadata ──
// Maps evidence submission types to their visual properties and icons
// Used in ThreadDetailPage for evidence type selection
export const EVIDENCE_VERDICT_META = {
   FACT: {
      color: "#0e9f6e",
      bg: "#ecfdf5",
      border: "#6ee7b7",
      icon: "check-circle",
      label: "Fact",
   },
   FAKE: {
      color: "#e02424",
      bg: "#fef2f2",
      border: "#fca5a5",
      icon: "x-circle",
      label: "Fake",
   },
   MISLEADING: {
      color: "#d97706",
      bg: "#fffbeb",
      border: "#fde68a",
      icon: "alert-triangle",
      label: "Misleading",
   },
   SATIRE: {
      color: "#7c3aed",
      bg: "#f5f3ff",
      border: "#c4b5fd",
      icon: "wand",
      label: "Satire",
   },
   UNVERIFIED: {
      color: "#6b7280",
      bg: "#f9fafb",
      border: "#e5e7eb",
      icon: "help-circle",
      label: "Unverified",
   },
};
