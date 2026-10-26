export function canAccessManagementConsole(user) {
   return user?.management_console?.can_access === true;
}

export function isPlatformSafetyModerator(user) {
   return user?.community_identity?.platform_role === "PLATFORM_SAFETY_MODERATOR";
}

export function canAccessPlatformSafetyConsole(user) {
   return canAccessManagementConsole(user) || isPlatformSafetyModerator(user);
}

export function formatManagementDate(value, { dateOnly = false } = {}) {
   if (!value) return "Not recorded";

   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Not recorded";

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      ...(dateOnly ? {} : { timeStyle: "short" }),
   }).format(date);
}

export function managementStatusTone(status) {
   if (["ACTIVE", "VERIFIED", "ACCEPTED", "COMPLETED"].includes(status)) return "success";
   if (["PENDING", "RUNNING", "UNVERIFIED"].includes(status)) return "warning";
   if (["SUSPENDED", "REJECTED", "CANCELLED", "EXPIRED", "FAILED"].includes(status)) return "critical";
   return "neutral";
}

export function formatManagementDuration(value) {
   if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "Not recorded";
   }
   const milliseconds = Math.max(0, Number(value));
   if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
   if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(milliseconds < 10000 ? 1 : 0)} s`;
   const minutes = Math.floor(milliseconds / 60000);
   const seconds = Math.round((milliseconds % 60000) / 1000);
   return `${minutes}m ${seconds}s`;
}

export function formatManagementOperationalLabel(value) {
   if (!value) return "Not recorded";
   return String(value)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatManagementClaimType(value) {
   return {
      TEXT: "Text",
      IMAGE: "Image",
      VIDEO: "Video",
      URL: "URL",
      FILE: "File",
   }[value] || value || "Not recorded";
}

export const MANAGEMENT_ORGANIZATION_TYPES = [
   ["FACT_CHECKING", "Fact-Checking Organization"],
   ["NEWS", "News Organization"],
   ["UNIVERSITY", "University"],
   ["RESEARCH", "Research Organization"],
   ["NGO", "Non-Governmental Organization"],
   ["GOVERNMENT", "Government Organization"],
   ["OTHER", "Other"],
];

export const MANAGEMENT_VERIFICATION_DOMAINS = [
   ["CIVICS", "Civics & Governance"],
   ["ELECTIONS", "Elections"],
   ["LAW", "Law & Justice"],
   ["HEALTH", "Health & Medicine"],
   ["SCIENCE", "Science"],
   ["TECHNOLOGY", "Technology"],
   ["EDUCATION", "Education"],
   ["ECONOMY", "Economy & Business"],
   ["ENVIRONMENT", "Environment"],
   ["DISASTERS", "Disasters & Public Safety"],
   ["SPORTS", "Sports"],
   ["CULTURE", "Culture & Entertainment"],
];

const VERIFICATION_DOMAIN_LABELS = new Map(MANAGEMENT_VERIFICATION_DOMAINS);

export function formatVerificationDomain(code) {
   return VERIFICATION_DOMAIN_LABELS.get(code) || code;
}

export const MANAGEMENT_VERIFICATION_STATUSES = [
   ["UNVERIFIED", "Unverified"],
   ["PENDING", "Pending Verification"],
   ["VERIFIED", "Verified"],
   ["REJECTED", "Rejected"],
];

export const MANAGEMENT_PARTNER_STATUSES = [
   ["NONE", "Not a Partner"],
   ["ACTIVE", "Active"],
   ["SUSPENDED", "Suspended"],
   ["FORMER", "Former Partner"],
];

export const MANAGEMENT_GOVERNANCE_ACTIONS = [
   ["ORGANIZATION_CREATED", "Organization Created"],
   ["ORGANIZATION_PLATFORM_TRUST_UPDATED", "Organization Platform Trust Updated"],
   ["ORGANIZATION_VERIFICATION_SCOPE_APPROVED", "Organization Verification Scope Approved (legacy)"],
   ["ORGANIZATION_VERIFICATION_SPECIALIZATIONS_UPDATED", "Organization Verification Specializations Updated"],
   ["CLAIM_INVESTIGATION_CLASSIFIED", "Claim Investigation Classified"],
   ["ORGANIZATION_INVITATION_CREATED", "Organization Admin Invitation Created"],
   ["ORGANIZATION_INVITATION_RESENT", "Organization Admin Invitation Resent"],
   ["ORGANIZATION_INVITATION_CANCELLED", "Organization Admin Invitation Cancelled"],
   ["PLATFORM_SAFETY_MODERATOR_REVOKED", "Platform Safety Moderator Revoked"],
   ["PLATFORM_STAFF_INVITATION_CREATED", "Platform Staff Invitation Created"],
   ["PLATFORM_STAFF_INVITATION_RESENT", "Platform Staff Invitation Resent"],
   ["PLATFORM_STAFF_INVITATION_CANCELLED", "Platform Staff Invitation Cancelled"],
];

const MANAGEMENT_GOVERNANCE_ACTION_LABELS = new Map(MANAGEMENT_GOVERNANCE_ACTIONS);

export function formatManagementGovernanceAction(actionType, fallbackLabel) {
   return MANAGEMENT_GOVERNANCE_ACTION_LABELS.get(actionType)
      || fallbackLabel
      || actionType
      || "Unknown governance action";
}

const AUDIT_VALUE_LABELS = {
   UNVERIFIED: "Unverified",
   PENDING: "Pending",
   VERIFIED: "Verified",
   REJECTED: "Rejected",
   NONE: "Not a Partner",
   ACTIVE: "Active",
   SUSPENDED: "Suspended",
   FORMER: "Former Partner",
   FACT_CHECKING: "Fact-Checking Organization",
   NEWS: "News Organization",
   UNIVERSITY: "University",
   RESEARCH: "Research Organization",
   NGO: "Non-Governmental Organization",
   GOVERNMENT: "Government Organization",
   OTHER: "Other",
   ORGANIZATION_ADMIN_ONBOARDING: "Organization Admin onboarding",
   PRIMARY_ADMIN_ONBOARDING: "Organization Admin onboarding",
   ADMIN: "Administrator",
   OWNER: "Administrator",
   MODERATOR: "Verification Reviewer",
   CONTRIBUTOR: "Former Contributor",
   COMMUNITY_USER: "Community User",
   PLATFORM_SAFETY_MODERATOR: "Platform Safety Moderator",
   CANCELLED: "Cancelled",
};

export function formatManagementAuditValue(value) {
   if (value === null || value === undefined || value === "") return "Not set";
   if (typeof value === "boolean") return value ? "Yes" : "No";
   if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
   if (typeof value === "object") return "Structured value";
   return AUDIT_VALUE_LABELS[value] || String(value);
}

export function formatManagementCapability(value) {
   if (value === "MANAGE_PARTNER_ORGANIZATION") return "Manage Partner Organization";
   if (value === "MANAGE_VERIFICATION_SPECIALIZATIONS") return "Manage Verification Specializations";
   if (value === "PROVISION_PARTNER_ORGANIZATION") return "Provision Partner Organization";
   if (value === "MANAGE_PLATFORM_STAFF") return "Manage Platform Staff";
   return value || "Not recorded";
}
