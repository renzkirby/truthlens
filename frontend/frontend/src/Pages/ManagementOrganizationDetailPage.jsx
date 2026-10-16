import { Link, useParams } from "react-router-dom";

import {
   DetailList,
   ManagementPageHeader,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

function PrimaryAdminState({ primaryAdmin }) {
   if (primaryAdmin?.state === "CURRENT") {
      const membership = primaryAdmin.membership;
      return (
         <>
            <div className="management-section__title-row">
               <h2>Primary Admin</h2>
               <ManagementStatus value={membership.status} />
            </div>
            <p className="management-section__description">
               Highest organization authority within TruthLens. This role does not imply legal or business ownership of the organization.
            </p>
            <DetailList items={[
               { label: "Username", value: `@${membership.user.username}` },
               { label: "Email", value: membership.user.email },
               { label: "Role", value: membership.role_label },
               { label: "Joined", node: formatManagementDate(membership.joined_at) },
               { label: "Approved", node: formatManagementDate(membership.approved_at) },
            ]} />
            <Link className="management-inline-link" to={`/management/memberships/${membership.id}`}>View membership record</Link>
         </>
      );
   }

   if (primaryAdmin?.state === "PENDING") {
      const invitation = primaryAdmin.invitation;
      return (
         <>
            <div className="management-section__title-row">
               <h2>Primary Admin</h2>
               <ManagementStatus value={invitation.status} />
            </div>
            <p className="management-section__description">A Primary Admin onboarding invitation is awaiting acceptance.</p>
            <DetailList items={[
               { label: "Email", value: invitation.email },
               { label: "Role", value: invitation.role_label },
               { label: "Sent", node: formatManagementDate(invitation.last_sent_at) },
               { label: "Expires", node: formatManagementDate(invitation.expires_at) },
               { label: "Deliveries", value: String(invitation.send_count) },
            ]} />
            <Link className="management-inline-link" to={`/management/invitations/${invitation.id}`}>View invitation record</Link>
         </>
      );
   }

   return (
      <>
         <h2>Primary Admin</h2>
         <p className="management-section__description">Highest organization authority within TruthLens.</p>
         <p className="management-empty-value">Not yet assigned</p>
      </>
   );
}

function ManagementOrganizationDetailPage() {
   const { organizationId } = useParams();
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_ORGANIZATION_DETAIL", organizationId),
   );

   return (
      <div className="management-page">
         <ManagementPageHeader
            title={data?.name || "Organization"}
            subtitle={data ? `${data.organization_type_label} · ${data.slug}` : "Institutional governance record"}
            backTo="/management/organizations"
            backLabel="Partner Organizations"
         />
         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections">
                  <section className="management-detail-section management-detail-section--trust">
                     <h2>Platform Trust</h2>
                     <div className="management-trust-statuses">
                        <div><span>Verification</span><ManagementStatus value={data.verification_status} label={data.verification_status_label} /></div>
                        <div><span>Partner status</span><ManagementStatus value={data.partner_status} label={data.partner_status_label} /></div>
                     </div>
                  </section>
                  <section className="management-detail-section"><PrimaryAdminState primaryAdmin={data.primary_admin} /></section>
                  <section className="management-detail-section">
                     <h2>Institutional Identity</h2>
                     <DetailList items={[
                        { label: "Name", value: data.name },
                        { label: "Slug", value: data.slug },
                        { label: "Type", value: data.organization_type_label },
                        { label: "Organization ID", value: data.id },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Organization-managed Public Profile</h2>
                     <DetailList items={[
                        { label: "Description", value: data.description },
                        { label: "Website", node: data.website ? <a href={data.website} target="_blank" rel="noreferrer">{data.website}</a> : "Not provided" },
                        { label: "Logo URL", value: data.logo_url || "Not provided" },
                        { label: "Expertise", value: data.expertise_areas?.length ? data.expertise_areas.join(", ") : "Not provided" },
                        { label: "Public profile", value: data.public_profile_enabled ? "Enabled" : "Disabled" },
                        { label: "Public logo", value: data.public_logo_enabled ? "Enabled" : "Disabled" },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Record Metadata</h2>
                     <DetailList items={[
                        { label: "Created", node: formatManagementDate(data.created_at) },
                        { label: "Last updated", node: formatManagementDate(data.updated_at) },
                     ]} />
                  </section>
               </div>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}

export default ManagementOrganizationDetailPage;
