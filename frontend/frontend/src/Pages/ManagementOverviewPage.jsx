import { Link } from "react-router-dom";

import { ManagementPageHeader, ManagementRequestState } from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";

const DESTINATIONS = [
   {
      to: "/management/safety",
      title: "Safety Review",
      description: "Review reported Community content and decide whether platform action is required.",
      icon: "shield-check",
      primary: true,
   },
   {
      to: "/management/pipeline",
      title: "Verification System Health",
      description: "Check whether automated verification is completing successfully and investigate failures.",
      icon: "activity",
   },
   {
      to: "/management/organizations",
      title: "Partner Organizations",
      description: "Review eligibility, verification status, partnership status, and governance records.",
      icon: "landmark",
   },
   {
      to: "/management/platform-staff",
      title: "Platform Staff",
      description: "Manage the people authorized to operate TruthLens at the platform level.",
      icon: "shield-user",
   },
   {
      to: "/management/memberships",
      title: "Membership Records",
      description: "Review Partner Organization roles, status, and admission history.",
      icon: "users",
   },
   {
      to: "/management/invitations",
      title: "Invitation Records",
      description: "Review invitation delivery, status, and onboarding outcomes.",
      icon: "mail",
   },
   {
      to: "/management/audit",
      title: "Governance History",
      description: "Review the permanent history of platform and partnership governance decisions.",
      icon: "shield-check",
   },
];

function attentionValue(request, selector) {
   if (request.loading) return "…";
   if (request.error) return "Unavailable";
   return selector(request.data);
}

function ManagementOverviewPage() {
   const overviewRequest = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_OVERVIEW"),
   );
   const safetyRequest = useManagementRequest(
      resolveApiEndpoint("SAFETY_CASES"),
   );
   const invitationRequest = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF_INVITATIONS"),
   );
   const pipelineRequest = useManagementRequest(
      `${resolveApiEndpoint("MANAGEMENT_PIPELINE_OVERVIEW")}?window=24h`,
   );

   const organizations = overviewRequest.data?.organizations;
   const activeSafetyCases = attentionValue(
      safetyRequest,
      (data) => Number(data?.count ?? 0),
   );
   const pendingStaffInvitations = attentionValue(
      invitationRequest,
      (data) => Number(data?.summary?.pending ?? 0),
   );
   const failedVerificationRuns = attentionValue(
      pipelineRequest,
      (data) => Number(data?.runs?.statuses?.FAILED ?? 0),
   );

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Management Console"
            subtitle="Operate TruthLens, review work that needs attention, and manage platform governance."
         />

         <aside className="management-boundary-note" aria-label="Platform Staff authority">
            <Icons name="shield-user" size={20} />
            <div>
               <strong>Platform Staff authority is separate from Partner Organization roles</strong>
               <p>
                  Platform Staff operate and govern TruthLens at the platform level. A person may also
                  belong to a Partner Organization, but that professional role does not grant Platform
                  Staff authority, and Platform Staff access does not grant Partner Organization authority.
               </p>
            </div>
         </aside>

         <section className="management-section management-attention-section" aria-labelledby="operator-attention-heading">
            <div className="management-section__heading">
               <h2 id="operator-attention-heading">Needs attention</h2>
               <p>Start here before opening detailed records or diagnostics.</p>
            </div>
            <div className="management-attention-grid">
               <article>
                  <Icons name="shield-check" size={19} />
                  <div>
                     <strong>{activeSafetyCases} active Safety Review cases</strong>
                     <span>Reported Community content waiting for review or resolution.</span>
                     <Link className="management-inline-link" to="/management/safety">Open Safety Review</Link>
                  </div>
               </article>
               <article>
                  <Icons name="landmark" size={19} />
                  <div>
                     <strong>{organizations?.pending_verification ?? "…"} organizations pending verification</strong>
                     <span>Organizations that still require an institutional verification decision.</span>
                     <Link className="management-inline-link" to="/management/organizations?verification_status=PENDING">Review organizations</Link>
                  </div>
               </article>
               <article>
                  <Icons name="alert-circle" size={19} />
                  <div>
                     <strong>{organizations?.suspended_partners ?? "…"} suspended Partner Organizations</strong>
                     <span>Partnerships currently operating under suspension.</span>
                     <Link className="management-inline-link" to="/management/organizations?partner_status=SUSPENDED">Review suspensions</Link>
                  </div>
               </article>
               <article>
                  <Icons name="activity" size={19} />
                  <div>
                     <strong>{failedVerificationRuns} failed verification runs in 24 hours</strong>
                     <span>Technical verification failures that may require operational review.</span>
                     <Link className="management-inline-link" to="/management/pipeline?window=24h&status=FAILED">Open system health</Link>
                  </div>
               </article>
               <article>
                  <Icons name="mail" size={19} />
                  <div>
                     <strong>{pendingStaffInvitations} pending Platform Staff invitations</strong>
                     <span>Invitations awaiting acceptance for Platform Safety access.</span>
                     <Link className="management-inline-link" to="/management/platform-staff">Review Platform Staff</Link>
                  </div>
               </article>
            </div>
         </section>

         <ManagementRequestState
            loading={overviewRequest.loading}
            error={overviewRequest.error}
            onRetry={overviewRequest.retry}
         >
            <section className="management-section" aria-labelledby="partner-summary-heading">
               <div className="management-section__heading">
                  <h2 id="partner-summary-heading">Partner Organization summary</h2>
                  <p>Current institutional partnership states across TruthLens.</p>
               </div>
               <div className="management-metrics" aria-label="Partner Organization summary">
                  <article>
                     <span>Total Organizations</span>
                     <strong>{organizations?.total ?? 0}</strong>
                  </article>
                  <article>
                     <span>Active Partners</span>
                     <strong>{organizations?.active_partners ?? 0}</strong>
                  </article>
                  <article>
                     <span>Pending Verification</span>
                     <strong>{organizations?.pending_verification ?? 0}</strong>
                  </article>
                  <article>
                     <span>Suspended Partners</span>
                     <strong>{organizations?.suspended_partners ?? 0}</strong>
                  </article>
               </div>
            </section>
         </ManagementRequestState>

         <section className="management-section" aria-labelledby="console-areas-heading">
            <div className="management-section__heading">
               <h2 id="console-areas-heading">Management areas</h2>
               <p>Choose a task area. Detailed technical or audit information stays inside the relevant page.</p>
            </div>
            <div className="management-destinations">
               {DESTINATIONS.map((destination) => (
                  <Link
                     key={destination.to}
                     to={destination.to}
                     className={`management-destination ${destination.primary ? "management-destination--primary" : ""}`}
                  >
                     <Icons name={destination.icon} size={22} />
                     <span>
                        <strong>{destination.title}</strong>
                        <small>{destination.description}</small>
                     </span>
                     <Icons name="arrow-right" size={18} />
                  </Link>
               ))}
            </div>
         </section>
      </div>
   );
}

export default ManagementOverviewPage;
