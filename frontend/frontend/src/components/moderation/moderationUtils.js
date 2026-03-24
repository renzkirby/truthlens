export const VERDICT_CONFIG = {
   FACT: {
      color: "var(--verdict-fact-text)",
      bg: "var(--verdict-fact-bg)",
      border: "var(--verdict-fact-border)",
      label: "FACT",
   },
   FAKE: {
      color: "var(--verdict-fake-text)",
      bg: "var(--verdict-fake-bg)",
      border: "var(--verdict-fake-border)",
      label: "FAKE",
   },
   MISLEADING: {
      color: "var(--verdict-misleading-text)",
      bg: "var(--verdict-misleading-bg)",
      border: "var(--verdict-misleading-border)",
      label: "MISLEADING",
   },
   UNVERIFIED: {
      color: "var(--verdict-unverified-text)",
      bg: "var(--verdict-unverified-bg)",
      border: "var(--verdict-unverified-border)",
      label: "UNVERIFIED",
   },
   SATIRE: {
      color: "var(--verdict-satire-text)",
      bg: "var(--verdict-satire-bg)",
      border: "var(--verdict-satire-border)",
      label: "SATIRE",
   },
   OUT_OF_SCOPE: {
      color: "var(--verdict-unverified-text)",
      bg: "var(--verdict-unverified-bg)",
      border: "var(--verdict-unverified-border)",
      label: "OUT OF SCOPE",
   },
};

export function timeAgo(dateStr) {
   if (!dateStr) return "-";
   const diff = Date.now() - new Date(dateStr).getTime();
   const mins = Math.floor(diff / 60000);
   const hours = Math.floor(diff / 3600000);
   const days = Math.floor(diff / 86400000);
   if (mins < 1) return "Just now";
   if (mins < 60) return `${mins}m ago`;
   if (hours < 24) return `${hours}h ago`;
   if (days < 7) return `${days}d ago`;
   return `${Math.floor(days / 7)}w ago`;
}
