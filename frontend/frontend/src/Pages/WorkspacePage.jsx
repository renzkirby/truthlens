import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import Icons from "../components/Icons.jsx";
import Select from "../components/ui/Select.jsx";

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
import OrganizationAdminPanel from "../components/workspace/OrganizationAdminPanel.jsx";
import SafetyReviewPanel from "../components/workspace/SafetyReviewPanel.jsx";
import EvidenceReviewPanel from "../components/workspace/EvidenceReviewPanel.jsx";
import AdjudicationReviewPanel from "../components/workspace/AdjudicationReviewPanel.jsx";
import DraftingPanel from "../components/workspace/DraftingPanel.jsx";
import PublishingPanel from "../components/workspace/PublishingPanel.jsx";
import PublicationsPanel from "../components/workspace/PublicationsPanel.jsx";
import FactualCorrectionPanel, { CorrectionDialog } from "../components/workspace/FactualCorrectionPanel.jsx";

const WORKLOAD_CAPABILITIES = [
   WorkspaceCapability.CLAIM_VERIFICATION_WORK,
   WorkspaceCapability.REVIEW_EVIDENCE,
   WorkspaceCapability.ADJUDICATE,
   WorkspaceCapability.CREATE_FACT_CHECK_DRAFT,
   WorkspaceCapability.PUBLISH_FACT_CHECK,
];

const FACTUAL_CORRECTION_CAPABILITIES = [
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
      id: "publications",
      label: "Publications",
      description: "Browse the selected organization's institutional publication library and version history.",
      icon: "book-open",
      scope: "organization",
      capabilities: [WorkspaceCapability.CREATE_FACT_CHECK_DRAFT, WorkspaceCapability.PUBLISH_FACT_CHECK],
   },
   {
      id: "factual-corrections",
      label: "Factual Corrections",
      description: "Review evidence, prepare proposals, and complete factual corrections in a dedicated workflow.",
      icon: "badge-check",
      scope: "organization",
      capabilities: FACTUAL_CORRECTION_CAPABILITIES,
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

let pendingFallbackHistoryTraversal = null;
let allowedFallbackHistoryIndex = null;

function WorkspacePage() {
   const { user } = useAuth();
   const location = useLocation();
   const navigate = useNavigate();
   const { requestId: routeRequestId } = useParams();
   const isCorrectionRoute = location.pathname.startsWith("/workspace/factual-corrections");
   const routeQuery = useMemo(() => new URLSearchParams(location.search), [location.search]);
   const routeOrganizationId = routeQuery.get("organization_id");
   const routeStatus = ["ACTIVE", "COMPLETED", "CANCELLED", "ALL"].includes(routeQuery.get("status"))
      ? routeQuery.get("status")
      : "ACTIVE";
   const routeOffset = /^\d+$/.test(routeQuery.get("offset") || "") ? Number(routeQuery.get("offset")) : 0;

   const memberships = useMemo(() => getWorkspaceMemberships(user), [user]);

   const platformCapabilities = useMemo(() => getPlatformCapabilities(user), [user]);

   const defaultOrganizationId = useMemo(() => getDefaultWorkspaceOrganizationId(user), [user]);

   const [requestedSectionId, setRequestedSectionId] = useState(null);

   const [requestedOrganizationId, setRequestedOrganizationId] = useState(null);

   const [draftingHandoff, setDraftingHandoff] = useState(null);

   const [publicationHandoff, setPublicationHandoff] = useState(null);

   const [correctionDirty, setCorrectionDirty] = useState(false);

   const [navigationPromptOpen, setNavigationPromptOpen] = useState(false);

   const [fallbackTraversalVersion, setFallbackTraversalVersion] = useState(0);

   const navigationResolverRef = useRef(null);

   const discardCorrectionDraftRef = useRef(null);

   const workspaceInstanceRef = useRef(Symbol("factual-correction-workspace"));

   const allowedNavigationUrlRef = useRef(null);

   const acceptedHistoryIndexRef = useRef(
      typeof window !== "undefined" && Number.isInteger(window.history.state?.idx)
         ? window.history.state.idx
         : null,
   );

   const acceptedHistoryUrlRef = useRef(typeof window !== "undefined" ? window.location.href : "");

   const requestNavigationConfirmation = useCallback(
      () =>
         new Promise((resolve) => {
            if (navigationResolverRef.current) {
               resolve(false);
               return;
            }
            navigationResolverRef.current = resolve;
            setNavigationPromptOpen(true);
         }),
      [],
   );

   const resolveNavigationConfirmation = useCallback((confirmed) => {
      const resolve = navigationResolverRef.current;
      navigationResolverRef.current = null;
      setNavigationPromptOpen(false);
      if (confirmed) {
         discardCorrectionDraftRef.current?.();
      }
      resolve?.(confirmed);
   }, []);

   const handleCorrectionDirtyChange = useCallback((dirty, discardDraft) => {
      setCorrectionDirty(dirty);
      discardCorrectionDraftRef.current = dirty && typeof discardDraft === "function" ? discardDraft : null;
   }, []);

   const withCorrectionDirtyGuard = useCallback(
      async (continuation) => {
         if (!isCorrectionRoute || !correctionDirty) {
            continuation();
            return;
         }

         if (await requestNavigationConfirmation()) {
            continuation();
         }
      },
      [correctionDirty, isCorrectionRoute, requestNavigationConfirmation],
   );

   const selectedOrganizationId = useMemo(() => {
      if (memberships.length === 0) {
         return null;
      }

      const requestedId = isCorrectionRoute ? routeOrganizationId : requestedOrganizationId;
      const requestedMembership = requestedId
         ? memberships.find((membership) => {
              const isRequested = String(membership?.organization?.id) === String(requestedId);
              if (!isRequested || !isCorrectionRoute) {
                 return isRequested;
              }
              const capabilities = Array.isArray(membership?.capabilities) ? membership.capabilities : [];
              return FACTUAL_CORRECTION_CAPABILITIES.some((capability) => capabilities.includes(capability));
           })
         : null;

      if (requestedMembership) {
         return String(requestedMembership.organization.id);
      }

      const eligibleMemberships = isCorrectionRoute
         ? memberships.filter((membership) => {
              const capabilities = Array.isArray(membership?.capabilities) ? membership.capabilities : [];
              return FACTUAL_CORRECTION_CAPABILITIES.some((capability) => capabilities.includes(capability));
           })
         : memberships;

      const defaultMembership = defaultOrganizationId
         ? eligibleMemberships.find((membership) => String(membership?.organization?.id) === String(defaultOrganizationId))
         : null;

      if (defaultMembership) {
         return String(defaultMembership.organization.id);
      }

      const firstOrganizationId = eligibleMemberships[0]?.organization?.id;

      return firstOrganizationId ? String(firstOrganizationId) : null;
   }, [defaultOrganizationId, isCorrectionRoute, memberships, requestedOrganizationId, routeOrganizationId]);

   const selectedMembership = useMemo(
      () => getWorkspaceMembership(user, selectedOrganizationId),
      [user, selectedOrganizationId],
   );

   const organizationCapabilities = useMemo(() => {
      const capabilities = selectedMembership?.capabilities;

      return Array.isArray(capabilities) ? capabilities : [];
   }, [selectedMembership]);

   const canAccessFactualCorrections = FACTUAL_CORRECTION_CAPABILITIES.some((capability) =>
      organizationCapabilities.includes(capability),
   );

   const organizationOptions = useMemo(
      () =>
         isCorrectionRoute
            ? memberships.filter((membership) => {
                 const capabilities = Array.isArray(membership?.capabilities) ? membership.capabilities : [];
                 return FACTUAL_CORRECTION_CAPABILITIES.some((capability) => capabilities.includes(capability));
              })
            : memberships,
      [isCorrectionRoute, memberships],
   );

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

   const visibleSectionGroups = useMemo(
      () =>
         [
            {
               scope: "platform",
               label: "Platform Safety",
               sections: visibleSections.filter((section) => section.scope === "platform"),
            },
            {
               scope: "organization",
               label: "Organization tools",
               sections: visibleSections.filter((section) => section.scope === "organization"),
            },
         ].filter((group) => group.sections.length > 0),
      [visibleSections],
   );

   const activeSectionId = useMemo(() => {
      if (visibleSections.length === 0) {
         return null;
      }

      if (isCorrectionRoute && visibleSections.some((section) => section.id === "factual-corrections")) {
         return "factual-corrections";
      }

      const requestedSection = requestedSectionId
         ? visibleSections.find((section) => section.id === requestedSectionId)
         : null;

      return requestedSection?.id ?? visibleSections[0].id;
   }, [isCorrectionRoute, visibleSections, requestedSectionId]);

   const activeSection = visibleSections.find((section) => section.id === activeSectionId) ?? null;

   const isPlatformSection = activeSection?.scope === "platform";

   const selectedOrganization = selectedMembership?.organization ?? null;

   const buildCorrectionLocation = useCallback(
      ({ requestId = null, status = routeStatus, offset = routeOffset } = {}) => {
         const query = new URLSearchParams({
            organization_id: selectedOrganizationId,
            status,
            offset: String(offset),
         });
         const path = requestId
            ? `/workspace/factual-corrections/${encodeURIComponent(requestId)}`
            : "/workspace/factual-corrections";
         return `${path}?${query.toString()}`;
      },
      [routeOffset, routeStatus, selectedOrganizationId],
   );

   const navigateWithOneShotAllowance = useCallback(
      (destination, options) => {
         const allowedUrl = new URL(destination, window.location.href).href;
         allowedNavigationUrlRef.current = allowedUrl;
         navigate(destination, options);
         queueMicrotask(() => {
            if (allowedNavigationUrlRef.current === allowedUrl) {
               allowedNavigationUrlRef.current = null;
            }
         });
      },
      [navigate],
   );

   const navigateCorrection = useCallback(
      ({ requestId = null, status = routeStatus, offset = routeOffset, replace = false } = {}) => {
         navigateWithOneShotAllowance(buildCorrectionLocation({ requestId, status, offset }), { replace });
      },
      [buildCorrectionLocation, navigateWithOneShotAllowance, routeOffset, routeStatus],
   );

   useEffect(() => {
      if (pendingFallbackHistoryTraversal || !isCorrectionRoute || !selectedOrganizationId) {
         return;
      }

      const requestedMembership = routeOrganizationId
         ? memberships.find((membership) => String(membership?.organization?.id) === String(routeOrganizationId))
         : null;
      const requestedCapabilities = Array.isArray(requestedMembership?.capabilities)
         ? requestedMembership.capabilities
         : [];
      const requestedOrganizationIsAuthorized =
         requestedMembership &&
         FACTUAL_CORRECTION_CAPABILITIES.some((capability) => requestedCapabilities.includes(capability));
      const queryIsCanonical =
         String(routeOrganizationId) === String(selectedOrganizationId) &&
         routeQuery.get("status") === routeStatus &&
         routeQuery.get("offset") === String(routeOffset);

      if (!queryIsCanonical) {
         navigateCorrection({
            requestId: routeOrganizationId && !requestedOrganizationIsAuthorized ? null : routeRequestId,
            status: routeStatus,
            offset: routeOrganizationId && !requestedOrganizationIsAuthorized ? 0 : routeOffset,
            replace: true,
         });
      }
   }, [
      isCorrectionRoute,
      memberships,
      navigateCorrection,
      routeOffset,
      routeOrganizationId,
      routeQuery,
      routeRequestId,
      routeStatus,
      selectedOrganizationId,
   ]);

   useEffect(() => {
      if (
         !pendingFallbackHistoryTraversal &&
         isCorrectionRoute &&
         user &&
         (!selectedOrganizationId || !canAccessFactualCorrections)
      ) {
         navigate("/workspace", { replace: true });
      }
   }, [canAccessFactualCorrections, isCorrectionRoute, navigate, selectedOrganizationId, user]);

   useEffect(() => {
      if (!isCorrectionRoute || !correctionDirty) {
         return undefined;
      }

      const navigationApi = window.navigation;
      if (navigationApi?.addEventListener) {
         const handleNavigate = (event) => {
            if (!event.canIntercept || event.downloadRequest || event.hashChange) {
               return;
            }
            const destination = new URL(event.destination.url);
            if (allowedNavigationUrlRef.current === destination.href) {
               allowedNavigationUrlRef.current = null;
               return;
            }
            event.intercept({
               focusReset: "manual",
               handler: async () => {
                  const confirmed = await requestNavigationConfirmation();
                  if (!confirmed) {
                     throw new DOMException("Navigation cancelled", "AbortError");
                  }
               },
            });
         };
         navigationApi.addEventListener("navigate", handleNavigate);
         return () => navigationApi.removeEventListener("navigate", handleNavigate);
      }

      const handlePopState = (event) => {
         const nextIndex = Number.isInteger(event.state?.idx) ? event.state.idx : null;
         const currentUrl = window.location.href;

         if (allowedFallbackHistoryIndex !== null && nextIndex === allowedFallbackHistoryIndex) {
            allowedFallbackHistoryIndex = null;
            acceptedHistoryIndexRef.current = nextIndex;
            return;
         }

         const pendingTraversal = pendingFallbackHistoryTraversal;
         if (pendingTraversal) {
            if (currentUrl === pendingTraversal.acceptedUrl) {
               acceptedHistoryIndexRef.current = pendingTraversal.acceptedIndex;
               setFallbackTraversalVersion((version) => version + 1);
               return;
            }
            if (nextIndex !== null) {
               window.history.go(pendingTraversal.acceptedIndex - nextIndex);
            }
            return;
         }

         const currentIndex = acceptedHistoryIndexRef.current;
         if (nextIndex === null || currentIndex === null || nextIndex === currentIndex) {
            acceptedHistoryIndexRef.current = nextIndex;
            return;
         }

         const delta = nextIndex - currentIndex;
         pendingFallbackHistoryTraversal = {
            acceptedIndex: currentIndex,
            acceptedUrl: acceptedHistoryUrlRef.current,
            targetIndex: nextIndex,
            delta,
            promptRequested: false,
            promptOwner: null,
         };
         setFallbackTraversalVersion((version) => version + 1);
         window.history.go(-delta);
      };

      const handleDocumentClick = (event) => {
         const anchor = event.target.closest?.("a[href]");
         if (!anchor || anchor.target === "_blank" || anchor.download || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
         }
         const destination = new URL(anchor.href, window.location.href);
         if (destination.origin !== window.location.origin) {
            return;
         }
         event.preventDefault();
         event.stopPropagation();
         withCorrectionDirtyGuard(() =>
            navigateWithOneShotAllowance(`${destination.pathname}${destination.search}${destination.hash}`),
         );
      };
      window.addEventListener("popstate", handlePopState, true);
      document.addEventListener("click", handleDocumentClick, true);
      return () => {
         window.removeEventListener("popstate", handlePopState, true);
         document.removeEventListener("click", handleDocumentClick, true);
      };
   }, [correctionDirty, isCorrectionRoute, navigateWithOneShotAllowance, requestNavigationConfirmation, withCorrectionDirtyGuard]);

   useEffect(() => {
      if (pendingFallbackHistoryTraversal) {
         return;
      }
      const currentIndex = window.history.state?.idx;
      if (Number.isInteger(currentIndex)) {
         acceptedHistoryIndexRef.current = currentIndex;
         acceptedHistoryUrlRef.current = window.location.href;
      }
   }, [location.hash, location.key, location.pathname, location.search]);

   useEffect(() => {
      const pendingTraversal = pendingFallbackHistoryTraversal;
      if (
         !pendingTraversal ||
         !correctionDirty ||
         window.location.href !== pendingTraversal.acceptedUrl
      ) {
         return;
      }

      if (pendingTraversal.promptRequested && pendingTraversal.promptOwner === workspaceInstanceRef.current) {
         return;
      }

      pendingTraversal.promptRequested = true;
      pendingTraversal.promptOwner = workspaceInstanceRef.current;
      requestNavigationConfirmation().then((confirmed) => {
         if (pendingFallbackHistoryTraversal !== pendingTraversal) {
            return;
         }
         pendingFallbackHistoryTraversal = null;
         if (!confirmed) {
            return;
         }
         allowedFallbackHistoryIndex = pendingTraversal.targetIndex;
         window.history.go(pendingTraversal.delta);
      });
   }, [correctionDirty, fallbackTraversalVersion, location.hash, location.key, location.pathname, location.search, requestNavigationConfirmation]);

   const openRevisionInDrafting = (revision) => {
      const revisionId = revision?.fact_check_id || revision?.id || revision?.resource_id;

      if (!revisionId) {
         return;
      }

      setDraftingHandoff({
         resourceType: "FACT_CHECK",
         resourceId: String(revisionId),
      });
      setRequestedSectionId("drafting");
   };

   const openCurrentPublication = (publication) => {
      const publicationId =
         publication?.selected_publication_id ||
         publication?.current_publication_id ||
         publication?.publication_id ||
         publication?.id;

      if (!publicationId) {
         return;
      }

      const openPublication = () => {
         setPublicationHandoff(String(publicationId));
         setRequestedSectionId("publications");
         if (isCorrectionRoute) {
            navigateWithOneShotAllowance("/workspace");
         }
      };

      if (isCorrectionRoute) {
         withCorrectionDirtyGuard(openPublication);
         return;
      }
      openPublication();
   };

   const handleOrganizationChange = (nextOrganizationId) => {
      withCorrectionDirtyGuard(() => {
         setRequestedOrganizationId(nextOrganizationId);
         if (isCorrectionRoute) {
            const query = new URLSearchParams({ organization_id: nextOrganizationId, status: "ACTIVE", offset: "0" });
            navigateWithOneShotAllowance(`/workspace/factual-corrections?${query.toString()}`);
         }
      });
   };

   const handleSectionChange = (sectionId) => {
      if (sectionId === "factual-corrections") {
         if (!isCorrectionRoute) {
            navigateCorrection({ requestId: null, status: "ACTIVE", offset: 0 });
         }
         return;
      }

      withCorrectionDirtyGuard(() => {
         setRequestedSectionId(sectionId);
         if (isCorrectionRoute) {
            navigateWithOneShotAllowance("/workspace");
         }
      });
   };

   return (
      <div className="workspace-view">
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

               {isPlatformSection ? (
                  <div className="workspace-platform-context">
                     <Icons name="shield" size={15} />

                     <span>Platform Safety · Platform-wide</span>
                  </div>
               ) : memberships.length > 0 ? (
                  <div className="workspace-organization-control">
                     <label htmlFor="workspace-organization">Organization</label>

                     <Select
                        id="workspace-organization"
                        density="standard"
                        value={selectedOrganizationId ?? ""}
                        onChange={(event) => handleOrganizationChange(event.target.value)}
                     >
                        {organizationOptions.map((membership) => (
                           <option key={membership.organization.id} value={membership.organization.id}>
                              {membership.organization.name}
                           </option>
                        ))}
                     </Select>

                     {selectedMembership && (
                        <span className="workspace-role-label">Your role: {formatRole(selectedMembership.role)}</span>
                     )}
                  </div>
               ) : (
                  <div className="workspace-platform-context">
                     <Icons name="shield" size={15} />

                     <span>Platform Safety</span>
                  </div>
               )}
            </header>

            <div className="workspace-body">
               <aside className="workspace-sidebar">
                  <div className="workspace-sidebar-heading">Available tools</div>

                  <nav className="workspace-navigation" aria-label="Workspace sections">
                     {visibleSectionGroups.map((group) => (
                        <section key={group.scope} className="workspace-nav-group">
                           <h2>{group.label}</h2>

                           <div className="workspace-nav-group-items">
                              {group.sections.map((section) => (
                                 <button
                                    key={section.id}
                                    type="button"
                                    className={`workspace-nav-item ${activeSectionId === section.id ? "active" : ""}`}
                                    aria-pressed={activeSectionId === section.id}
                                    onClick={() => handleSectionChange(section.id)}
                                 >
                                    <span className="workspace-nav-icon">
                                       <Icons name={section.icon} size={17} />
                                    </span>

                                    <span className="workspace-nav-copy">
                                       <strong>{section.label}</strong>
                                    </span>
                                 </button>
                              ))}
                           </div>
                        </section>
                     ))}
                  </nav>
               </aside>

               <section className="workspace-content">
                  {activeSection ? (
                     <>
                        <div className="workspace-content-header">
                           <div>
                              <span className="workspace-scope-context">
                                 {activeSection.scope === "platform"
                                    ? "Platform Safety"
                                    : selectedOrganization?.name
                                      ? `Organization · ${selectedOrganization.name}`
                                      : "Organization"}
                              </span>

                              <h2>{activeSection.label}</h2>

                              <p>{activeSection.description}</p>
                           </div>
                        </div>

                        {activeSection.id === "safety" ? (
                           <SafetyReviewPanel />
                        ) : activeSection.id === "intake" ? (
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
                        ) : activeSection.id === "evidence" && organizationCapabilities.includes(
                             WorkspaceCapability.REVIEW_EVIDENCE,
                          ) ? (
                           <EvidenceReviewPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              canReviewEvidence
                           />
                        ) : activeSection.id === "adjudication" && organizationCapabilities.includes(
                             WorkspaceCapability.ADJUDICATE,
                          ) ? (
                           <AdjudicationReviewPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              canAdjudicate
                           />
                        ) : activeSection.id === "drafting" && organizationCapabilities.includes(
                             WorkspaceCapability.CREATE_FACT_CHECK_DRAFT,
                          ) ? (
                           <DraftingPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              initialSelection={draftingHandoff}
                              onInitialSelectionConsumed={() => setDraftingHandoff(null)}
                           />
                        ) : activeSection.id === "publishing" && organizationCapabilities.includes(
                             WorkspaceCapability.PUBLISH_FACT_CHECK,
                          ) ? (
                           <PublishingPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              onPublicationPublished={openCurrentPublication}
                           />
                        ) : activeSection.id === "publications" ? (
                           <PublicationsPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              initialPublicationId={publicationHandoff}
                              onInitialPublicationConsumed={() => setPublicationHandoff(null)}
                              onRevisionCreated={openRevisionInDrafting}
                              onCorrectionOpened={(correctionRequestId) =>
                                 navigateCorrection({ requestId: correctionRequestId, status: "ACTIVE", offset: 0 })
                              }
                            />
                        ) : activeSection.id === "factual-corrections" ? (
                           <FactualCorrectionPanel
                              organizationId={selectedOrganizationId}
                              organizationName={selectedOrganization?.name}
                              requestId={routeRequestId || null}
                              status={routeStatus}
                              offset={routeOffset}
                              onNavigate={navigateCorrection}
                              onDirtyChange={handleCorrectionDirtyChange}
                              onOpenPublication={openCurrentPublication}
                           />
                        ) : activeSection.id === "organization" ? (
                           <OrganizationAdminPanel
                              key={selectedOrganizationId ?? "no-organization"}
                              organizationId={selectedOrganizationId}
                              membershipRole={selectedMembership?.role}
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
            <CorrectionDialog
               open={navigationPromptOpen}
               title="Discard unsaved correction proposal changes?"
               description="This navigation would leave the proposal editor. Your unsaved text will be lost, while the last saved server proposal remains unchanged."
               confirmLabel="Discard and continue"
               confirmVariant="destructive"
               onClose={() => resolveNavigationConfirmation(false)}
               onConfirm={() => resolveNavigationConfirmation(true)}
            />
      </div>
   );
}

export default WorkspacePage;
