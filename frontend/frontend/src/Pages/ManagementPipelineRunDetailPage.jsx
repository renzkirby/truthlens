import { useLocation, useParams } from "react-router-dom";

import {
   DetailList,
   ManagementPageHeader,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import {
   formatManagementClaimType,
   formatManagementDate,
   formatManagementDuration,
   formatManagementOperationalLabel,
} from "../utils/management";

function TelemetryMetadata({ metadata }) {
   const entries = Object.entries(metadata || {});
   if (!entries.length) return null;
   return (
      <dl className="management-telemetry-metadata">
         {entries.map(([key, value]) => (
            <div key={key}>
               <dt>{formatManagementOperationalLabel(key)}</dt>
               <dd>{typeof value === "boolean" ? (value ? "Yes" : "No") : value}</dd>
            </div>
         ))}
      </dl>
   );
}

function ManagementPipelineRunDetailPage() {
   const { runId } = useParams();
   const location = useLocation();
   const requestedBackTarget = location.state?.from;
   const backTo = (
      typeof requestedBackTarget === "string" && requestedBackTarget.startsWith("/management/pipeline")
   ) ? requestedBackTarget : "/management/pipeline";
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_PIPELINE_RUN_DETAIL", runId),
   );

   return (
      <div className="management-page management-pipeline-detail-page">
         <ManagementPageHeader
            title="Verification Run"
            subtitle={data ? `Run ${data.id}` : "Operational lifecycle and telemetry timeline"}
            backTo={backTo}
            backLabel="Pipeline Health"
         />
         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections">
                  <section className="management-detail-section">
                     <div className="management-section__title-row">
                        <h2>Lifecycle</h2>
                        <ManagementStatus value={data.status} />
                     </div>
                     <DetailList items={[
                        { label: "Run ID", value: data.id },
                        { label: "Claim ID", value: data.claim_id },
                        { label: "Claim type", value: formatManagementClaimType(data.claim_type) },
                        { label: "Pipeline version", value: data.pipeline_version },
                        { label: "Status", value: formatManagementOperationalLabel(data.status) },
                        { label: "Started", value: formatManagementDate(data.started_at) },
                        { label: "Completed", value: formatManagementDate(data.completed_at) },
                        { label: "Duration", value: formatManagementDuration(data.duration_ms) },
                        { label: "Failure stage", value: data.failure_stage ? formatManagementOperationalLabel(data.failure_stage) : "Not recorded" },
                        { label: "Failure code", value: data.failure_code || "Not recorded" },
                        { label: "Abstention reason", value: data.abstention_reason ? formatManagementOperationalLabel(data.abstention_reason) : "Not recorded" },
                        { label: "Created", value: formatManagementDate(data.created_at) },
                     ]} />
                  </section>

                  <section className="management-detail-section">
                     <div className="management-section__heading">
                        <h2>Telemetry timeline</h2>
                        <p>Events are shown in recorded sequence. Content, prompts, responses, evidence bodies, and user identity are excluded.</p>
                     </div>
                     {data.telemetry_events.length ? (
                        <ol className="management-telemetry-timeline">
                           {data.telemetry_events.map((event) => {
                              const providerEvent = event.event_type === "LLM_PROVIDER_CALL";
                              return (
                                 <li key={event.sequence}>
                                    <div className="management-telemetry-timeline__marker" aria-hidden="true">{event.sequence}</div>
                                    <div className="management-telemetry-timeline__content">
                                       <div className="management-telemetry-timeline__heading">
                                          <div>
                                             <span className="management-telemetry-kind">{providerEvent ? "Provider call" : "Pipeline stage"}</span>
                                             <h3>{formatManagementOperationalLabel(providerEvent ? event.operation : event.stage)}</h3>
                                          </div>
                                          <strong>{formatManagementDuration(event.duration_ms)}</strong>
                                       </div>
                                       <div className="management-telemetry-facts">
                                          {providerEvent ? <span><Icons name="activity" size={15} /> {formatManagementOperationalLabel(event.provider)}</span> : null}
                                          <span>Outcome: {formatManagementOperationalLabel(event.outcome)}</span>
                                          <span>{formatManagementDate(event.occurred_at)}</span>
                                          {providerEvent && event.provider_call_id ? <span title={event.provider_call_id}>Call {event.provider_call_id.slice(0, 8)}</span> : null}
                                       </div>
                                       {providerEvent && event.error_label ? (
                                          <div className="management-telemetry-error">Safe error label: {event.error_label}</div>
                                       ) : null}
                                       {!providerEvent ? <TelemetryMetadata metadata={event.metadata} /> : null}
                                    </div>
                                 </li>
                              );
                           })}
                        </ol>
                     ) : <div className="management-inline-empty">No durable telemetry was recorded for this run.</div>}
                  </section>
               </div>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}

export default ManagementPipelineRunDetailPage;
