import { Link, useLocation, useParams } from "react-router-dom";

import {
   ManagementAuditSecondaryContext,
   ManagementAuditStateTransition,
} from "../components/management/ManagementAuditUi";
import {
   DetailList,
   ManagementPageHeader,
   ManagementRequestState,
} from "../components/management/ManagementUi";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import {
   formatManagementCapability,
   formatManagementDate,
   formatManagementGovernanceAction,
} from "../utils/management";

function ManagementGovernanceAuditDetailPage() {
   const { eventId } = useParams();
   const location = useLocation();
   const requestedBackTarget = location.state?.from;
   const backTo = (
      typeof requestedBackTarget === "string" && requestedBackTarget.startsWith("/management/audit")
   ) ? requestedBackTarget : "/management/audit";
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_GOVERNANCE_AUDIT_DETAIL", eventId),
   );
   const actionLabel = data
      ? formatManagementGovernanceAction(data.action_type, data.action_label)
      : "Governance audit event";

   return (
      <div className="management-page">
         <ManagementPageHeader
            title={actionLabel}
            subtitle={data?.subject_organization?.name || "Platform-governance record"}
            backTo={backTo}
            backLabel="Governance Audit"
         />
         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections">
                  <section className="management-detail-section">
                     <h2>Governance action</h2>
                     <DetailList items={[
                        { label: "Action", value: actionLabel },
                        {
                           label: "Affected Organization",
                           node: data.subject_organization?.id ? (
                              <Link to={`/management/organizations/${data.subject_organization.id}`}>
                                 {data.subject_organization.name || "Organization record"}
                              </Link>
                           ) : (data.subject_organization?.name || "Organization unavailable"),
                        },
                        {
                           label: "Actor",
                           value: data.actor?.username
                              ? `@${data.actor.username}${data.actor.historical ? " (historical snapshot)" : ""}`
                              : "System",
                        },
                        { label: "Occurred at", node: formatManagementDate(data.created_at) },
                        { label: "Authority", value: "Platform" },
                        { label: "Platform capability", value: formatManagementCapability(data.authority.capability) },
                     ]} />
                  </section>

                  <section className="management-detail-section">
                     <h2>State transition</h2>
                     <p className="management-section__description">
                        Recorded values before and after this attributable governance action.
                     </p>
                     <ManagementAuditStateTransition
                        actionType={data.action_type}
                        previousState={data.previous_state}
                        newState={data.new_state}
                     />
                  </section>

                  <section className="management-detail-section">
                     <h2>Audit record</h2>
                     <DetailList items={[
                        { label: "Resource type", value: data.resource.label },
                        { label: "Resource ID", value: data.resource.id },
                        { label: "Event ID", value: data.id },
                        { label: "Domain", value: data.domain_label },
                        { label: "Reason code", value: data.reason_code || "Not recorded" },
                     ]} />
                     <ManagementAuditSecondaryContext
                        notes={data.notes}
                        context={data.context}
                     />
                  </section>
               </div>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}

export default ManagementGovernanceAuditDetailPage;
