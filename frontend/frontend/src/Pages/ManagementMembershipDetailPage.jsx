import { Link, useParams } from "react-router-dom";

import { DetailList, ManagementPageHeader, ManagementRequestState, ManagementStatus } from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

function ManagementMembershipDetailPage() {
   const { membershipId } = useParams();
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_MEMBERSHIP_DETAIL", membershipId),
   );

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Membership Record"
            subtitle={data ? `${data.organization.name} · @${data.user.username}` : "Organization membership record"}
            backTo="/management/memberships"
            backLabel="Membership Records"
         />
         <aside className="management-boundary-note" aria-label="Membership record boundary">
            <Icons name="info" size={19} />
            <div>
               <strong>Review record only</strong>
               <p>
                  This page records the member’s role, status, and admission history. Membership
                  changes are managed by the Partner Organization through its own administration workflow.
               </p>
            </div>
         </aside>

         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections management-detail-sections--two-column">
                  <section className="management-detail-section">
                     <div className="management-section__title-row"><h2>Membership</h2><ManagementStatus value={data.status} /></div>
                     <DetailList items={[
                        { label: "Organization", node: <Link to={`/management/organizations/${data.organization.id}`}>{data.organization.name}</Link> },
                        { label: "Member", value: `@${data.user.username}` },
                        { label: "Email", value: data.user.email },
                        { label: "Role", value: data.role_label },
                        { label: "Status", value: data.status },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Admission History</h2>
                     <DetailList items={[
                        { label: "Joined", node: formatManagementDate(data.joined_at) },
                        { label: "Approved", node: formatManagementDate(data.approved_at) },
                        { label: "Approved by", value: data.approved_by ? `@${data.approved_by.username}` : "Not recorded" },
                     ]} />
                  </section>
               </div>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}

export default ManagementMembershipDetailPage;
