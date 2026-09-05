export const WorkspaceCapability = Object.freeze({
   REVIEW_SAFETY: "REVIEW_SAFETY",
   CLAIM_VERIFICATION_WORK: "CLAIM_VERIFICATION_WORK",
   REVIEW_EVIDENCE: "REVIEW_EVIDENCE",
   ADJUDICATE: "ADJUDICATE",
   CREATE_FACT_CHECK_DRAFT: "CREATE_FACT_CHECK_DRAFT",
   PUBLISH_FACT_CHECK: "PUBLISH_FACT_CHECK",
   MANAGE_ORGANIZATION: "MANAGE_ORGANIZATION",
});

export function getWorkspace(user) {
   const workspace = user?.workspace;

   if (!workspace || typeof workspace !== "object") {
      return null;
   }

   return workspace;
}

export function canAccessWorkspace(user) {
   return getWorkspace(user)?.can_access === true;
}

export function isPlatformSafetyModerator(user) {
   return getWorkspace(user)?.is_platform_safety_moderator === true;
}

export function getPlatformCapabilities(user) {
   const capabilities = getWorkspace(user)?.platform_capabilities;

   return Array.isArray(capabilities) ? capabilities : [];
}

export function hasPlatformCapability(user, capability) {
   return getPlatformCapabilities(user).includes(capability);
}

export function getWorkspaceMemberships(user) {
   const memberships = getWorkspace(user)?.memberships;

   return Array.isArray(memberships) ? memberships : [];
}

export function getWorkspaceMembership(user, organizationId) {
   if (!organizationId) {
      return null;
   }

   return (
      getWorkspaceMemberships(user).find(
         (membership) => String(membership?.organization?.id) === String(organizationId),
      ) || null
   );
}

export function getOrganizationCapabilities(user, organizationId) {
   const membership = getWorkspaceMembership(user, organizationId);

   return Array.isArray(membership?.capabilities) ? membership.capabilities : [];
}

export function hasOrganizationCapability(user, organizationId, capability) {
   return getOrganizationCapabilities(user, organizationId).includes(capability);
}

export function getDefaultWorkspaceOrganizationId(user) {
   const workspace = getWorkspace(user);

   if (workspace?.default_organization_id) {
      return String(workspace.default_organization_id);
   }

   const firstMembership = getWorkspaceMemberships(user)[0];

   return firstMembership?.organization?.id ? String(firstMembership.organization.id) : null;
}
