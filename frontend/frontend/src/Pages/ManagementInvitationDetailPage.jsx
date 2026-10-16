import { Link, useParams } from "react-router-dom";

import { DetailList, ManagementPageHeader, ManagementRequestState, ManagementStatus } from "../components/management/ManagementUi";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

function ManagementInvitationDetailPage() {
   const { invitationId } = useParams();
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_INVITATION_DETAIL", invitationId),
   );

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Invitation"
            subtitle={data ? `${data.organization.name} · ${data.email}` : "Organization invitation record"}
            backTo="/management/invitations"
            backLabel="Invitations"
         />
         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections management-detail-sections--two-column">
                  <section className="management-detail-section">
                     <div className="management-section__title-row"><h2>Invitation</h2><ManagementStatus value={data.status} /></div>
                     <DetailList items={[
                        { label: "Organization", node: <Link to={`/management/organizations/${data.organization.id}`}>{data.organization.name}</Link> },
                        { label: "Email", value: data.email },
                        { label: "Invited role", value: data.invited_role_label },
                        { label: "Purpose", value: data.purpose_label },
                        { label: "Invited by", value: data.invited_by ? `@${data.invited_by.username}` : "System" },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Delivery</h2>
                     <DetailList items={[
                        { label: "Last sent", node: formatManagementDate(data.last_sent_at) },
                        { label: "Expires", node: formatManagementDate(data.expires_at) },
                        { label: "Delivery count", value: String(data.send_count) },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Outcome</h2>
                     <DetailList items={[
                        { label: "Accepted by", value: data.accepted_by ? `@${data.accepted_by.username}` : "Not accepted" },
                        { label: "Accepted at", node: formatManagementDate(data.accepted_at) },
                        { label: "Cancelled by", value: data.cancelled_by ? `@${data.cancelled_by.username}` : "Not cancelled" },
                        { label: "Cancelled at", node: formatManagementDate(data.cancelled_at) },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Record Metadata</h2>
                     <DetailList items={[
                        { label: "Invitation ID", value: data.id },
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

export default ManagementInvitationDetailPage;
