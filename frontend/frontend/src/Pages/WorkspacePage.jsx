import { useMemo, useState } from "react";

import { useAuth } from "../hooks/useAuth";
import NavigationBar from "../components/NavigationBar.jsx";
import Icons from "../components/Icons.jsx";

import {
   WorkspaceCapability,
   getDefaultWorkspaceOrganizationId,
   getPlatformCapabilities,
   getWorkspaceMembership,
   getWorkspaceMemberships,
} from "../utils/workspace";

import "./WorkspacePage.css";
import VerificationIntakePanel from "../components/workspace/VerificationIntakePanel.jsx";
import OrganizationWorkloadPanel from "../components/workspace/OrganizationWorkloadPanel.jsx";

const WORKLOAD_CAPABILITIES = [
   WorkspaceCapability.CLAIM_VERIFICATION_WORK,
   WorkspaceCapability.REVIEW_EVIDENCE,
   WorkspaceCapability.ADJUDICATE,
   WorkspaceCapability.CREATE_FACT_CHECK_DRAFT,
   WorkspaceCapability.PUBLISH_FACT_CHECK,
];

const WORKSPACE_SECTIONS = [
   {
      id: "safety",
      label: "Safety Review",
      description: "Review reports, abuse, spam, misuse, and platform policy issues.",
      icon: "shield",
      scope: "platform",
      capability: WorkspaceCapability.REVIEW_SAFETY,
   },
   {
      id: "intake",
      label: "Verification Intake",
      description: "Claim available community investigations for your partner organization.",
      icon: "scan-line",
      scope: "organization",
      capability: WorkspaceCapability.CLAIM_VERIFICATION_WORK,
   },
   {
      id: "workload",
      label: "Organization Workload",
      description: "Track active investigations currently owned by your partner organization.",
      icon: "inbox",
      scope: "organization",
      capabilities: WORKLOAD_CAPABILITIES,
   },
   {
      id: "evidence",
      label: "Evidence Review",
      description: "Review evidence submitted to organization-owned investigations.",
      icon: "paperclip",
      scope: "organization",
      capability: WorkspaceCapability.REVIEW_EVIDENCE,
   },
   {
      id: "adjudication",
      label: "Adjudication",
      description: "Evaluate reviewed evidence and make authoritative factual decisions.",
      icon: "list-checks",
      scope: "organization",
      capability: WorkspaceCapability.ADJUDICATE,
   },
   {
      id: "drafting",
      label: "Drafting",
      description: "Prepare fact-check drafts from completed investigation work.",
      icon: "file-text",
      scope: "organization",
      capability: WorkspaceCapability.CREATE_FACT_CHECK_DRAFT,
   },
   {
      id: "publishing",
      label: "Publishing",
      description: "Review and publish completed fact checks for the selected organization.",
      icon: "check-circle",
      scope: "organization",
      capability: WorkspaceCapability.PUBLISH_FACT_CHECK,
   },
   {
      id: "organization",
      label: "Organization",
      description: "Manage partner organization administration and membership.",
      icon: "settings",
      scope: "organization",
      capability: WorkspaceCapability.MANAGE_ORGANIZATION,
   },
];

function formatRole(role) {
   if (!role) {
      return "Member";
   }

   return role
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(" ");
}

function WorkspacePage() {
   const { user } = useAuth();

   const memberships = useMemo(() => getWorkspaceMemberships(user), [user]);

   const platformCapabilities = useMemo(() => getPlatformCapabilities(user), [user]);

   const defaultOrganizationId = useMemo(() => getDefaultWorkspaceOrganizationId(user), [user]);

   const [requestedSectionId, setRequestedSectionId] = useState(null);

   const [requestedOrganizationId, setRequestedOrganizationId] = useState(null);

   const selectedOrganizationId = useMemo(() => {
      if (memberships.length === 0) {
         return null;
      }

      const requestedMembership = requestedOrganizationId
         ? memberships.find((membership) => String(membership?.organization?.id) === String(requestedOrganizationId))
         : null;

      if (requestedMembership) {
         return String(requestedMembership.organization.id);
      }

      const defaultMembership = defaultOrganizationId
         ? memberships.find((membership) => String(membership?.organization?.id) === String(defaultOrganizationId))
         : null;

      if (defaultMembership) {
         return String(defaultMembership.organization.id);
      }

      const firstOrganizationId = memberships[0]?.organization?.id;

      return firstOrganizationId ? String(firstOrganizationId) : null;
   }, [memberships, requestedOrganizationId, defaultOrganizationId]);

   const selectedMembership = useMemo(
      () => getWorkspaceMembership(user, selectedOrganizationId),
      [user, selectedOrganizationId],
   );

   const organizationCapabilities = useMemo(() => {
      const capabilities = selectedMembership?.capabilities;

      return Array.isArray(capabilities) ? capabilities : [];
   }, [selectedMembership]);

   const visibleSections = useMemo(
      () =>
         WORKSPACE_SECTIONS.filter((section) => {
            if (section.scope === "platform") {
               return platformCapabilities.includes(section.capability);
            }

            if (Array.isArray(section.capabilities)) {
               return section.capabilities.some((capability) => organizationCapabilities.includes(capability));
            }

            return organizationCapabilities.includes(section.capability);
         }),
      [platformCapabilities, organizationCapabilities],
   );

   const activeSectionId = useMemo(() => {
      if (visibleSections.length === 0) {
         return null;
      }

      const requestedSection = requestedSectionId
         ? visibleSections.find((section) => section.id === requestedSectionId)
         : null;

      return requestedSection?.id ?? visibleSections[0].id;
   }, [visibleSections, requestedSectionId]);

   const activeSection = visibleSections.find((section) => section.id === activeSectionId) ?? null;

   const selectedOrganization = selectedMembership?.organization ?? null;

   return (
      <div className="workspace-page">
         <NavigationBar />

         <main className="workspace-container">
            <header className="workspace-header">
               <div className="workspace-header-copy">
                  <div className="workspace-title-row">
                     <div className="workspace-title-icon">
                        <Icons name="shield" size={21} />
                     </div>

                     <div>
                        <p className="workspace-eyebrow">TruthLens Operations</p>

                        <h1>Verification Workspace</h1>
                     </div>
                  </div>

                  <p className="workspace-description">
                     Access operational tools according to your platform and partner organization permissions.
                  </p>
               </div>

               {memberships.length > 0 ? (
                  <div className="workspace-organization-control">
                     <label htmlFor="workspace-organization">Organization</label>

                     <select
                        id="workspace-organization"
                        value={selectedOrganizationId ?? ""}
                        onChange={(event) => setRequestedOrganizationId(event.target.value)}
                     >
                        {memberships.map((membership) => (
                           <option key={membership.organization.id} value={membership.organization.id}>
                              {membership.organization.name}
                           </option>
                        ))}
                     </select>

                     {selectedMembership && (
                        <span className="workspace-role-label">{formatRole(selectedMembership.role)}</span>
                     )}
                  </div>
               ) : (
                  <div className="workspace-platform-context">
                     <Icons name="shield" size={15} />

                     <span>Platform Safety</span>
                  </div>
               )}
            </header>

            <section className="workspace-context-bar">
               <div>
                  <span className="workspace-context-label">Platform permissions</span>

                  <strong>{platformCapabilities.length}</strong>
               </div>

               <div>
                  <span className="workspace-context-label">Organization permissions</span>

                  <strong>{organizationCapabilities.length}</strong>
               </div>

               <div>
                  <span className="workspace-context-label">Active organization</span>

                  <strong>{selectedOrganization?.name ?? "None"}</strong>
               </div>
            </section>

            <div className="workspace-body">
               <aside className="workspace-sidebar">
                  <div className="workspace-sidebar-heading">Available tools</div>

                  <nav className="workspace-navigation" aria-label="Workspace sections">
                     {visibleSections.map((section) => (
                        <button
                           key={section.id}
                           type="button"
                           className={`workspace-nav-item ${activeSectionId === section.id ? "active" : ""}`}
                           onClick={() => setRequestedSectionId(section.id)}
                        >
                           <span className="workspace-nav-icon">
                              <Icons name={section.icon} size={17} />
                           </span>

                           <span className="workspace-nav-copy">
                              <strong>{section.label}</strong>

                              <small>{section.scope === "platform" ? "Platform" : "Organization"}</small>
                           </span>
                        </button>
                     ))}
                  </nav>
               </aside>

               <section className="workspace-content">
                  {activeSection ? (
                     <>
                        <div className="workspace-content-header">
                           <div>
                              <span className="workspace-scope-badge">
                                 {activeSection.scope === "platform"
                                    ? "Platform authority"
                                    : (selectedOrganization?.name ?? "Organization authority")}
                              </span>

                              <h2>{activeSection.label}</h2>

                              <p>{activeSection.description}</p>
                           </div>
                        </div>

                        {activeSection.id === "intake" ? (
                           <VerificationIntakePanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                           />
                        ) : activeSection.id === "workload" ? (
                           <OrganizationWorkloadPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              canReleaseInvestigation={organizationCapabilities.includes(
                                 WorkspaceCapability.CLAIM_VERIFICATION_WORK,
                              )}
                           />
                        ) : (
                           <div className="workspace-placeholder">
                              <div className="workspace-placeholder-icon">
                                 <Icons name={activeSection.icon} size={24} />
                              </div>

                              <div>
                                 <strong>Workspace foundation ready</strong>

                                 <p>This section is authorized and ready for its workflow integration.</p>

                                 <code>{activeSection.capability}</code>
                              </div>
                           </div>
                        )}
                     </>
                  ) : (
                     <div className="workspace-empty-state">
                        <Icons name="lock" size={24} />

                        <h2>No workspace tools available</h2>

                        <p>Your current authorization context does not expose any operational section.</p>
                     </div>
                  )}
               </section>
            </div>
         </main>
      </div>
   );
}

export default WorkspacePage;
