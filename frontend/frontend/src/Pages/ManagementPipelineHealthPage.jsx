import { useEffect, useMemo } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
   ManagementPageHeader,
   ManagementPagination,
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

const WINDOW_OPTIONS = [
   ["24h", "Last 24 hours"],
   ["7d", "Last 7 days"],
   ["30d", "Last 30 days"],
];
const VALID_WINDOWS = new Set(WINDOW_OPTIONS.map(([value]) => value));
const VALID_STATUSES = new Set(["", "PENDING", "RUNNING", "COMPLETED", "ABSTAINED", "FAILED", "CANCELLED"]);
const VALID_CLAIM_TYPES = new Set(["", "TEXT", "IMAGE", "VIDEO", "URL", "FILE"]);
const STATUS_ORDER = ["PENDING", "RUNNING", "COMPLETED", "ABSTAINED", "FAILED", "CANCELLED"];

function requestUrl(endpoint, params) {
   const url = new URL(resolveApiEndpoint(endpoint));
   Object.entries(params).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) url.searchParams.set(key, value);
   });
   return url.toString();
}

function Metric({ label, value }) {
   return (
      <article>
         <span>{label}</span>
         <strong>{value}</strong>
      </article>
   );
}

function ManagementPipelineHealthPage() {
   const [searchParams, setSearchParams] = useSearchParams();
   const location = useLocation();
   const requestedWindow = searchParams.get("window") || "7d";
   const windowValue = VALID_WINDOWS.has(requestedWindow) ? requestedWindow : "7d";
   const requestedStatus = searchParams.get("status") || "";
   const statusFilter = VALID_STATUSES.has(requestedStatus) ? requestedStatus : "";
   const requestedClaimType = searchParams.get("claim_type") || "";
   const claimTypeFilter = VALID_CLAIM_TYPES.has(requestedClaimType) ? requestedClaimType : "";
   const parsedPage = Number.parseInt(searchParams.get("page") || "1", 10);
   const page = Number.isInteger(parsedPage) && parsedPage > 0 ? parsedPage : 1;

   useEffect(() => {
      const next = new URLSearchParams(searchParams);
      let changed = false;
      if (next.get("window") !== windowValue) {
         next.set("window", windowValue);
         changed = true;
      }
      if (requestedStatus && !VALID_STATUSES.has(requestedStatus)) {
         next.delete("status");
         changed = true;
      }
      if (requestedClaimType && !VALID_CLAIM_TYPES.has(requestedClaimType)) {
         next.delete("claim_type");
         changed = true;
      }
      if (searchParams.has("page") && page === 1 && searchParams.get("page") !== "1") {
         next.delete("page");
         changed = true;
      }
      if (changed) setSearchParams(next, { replace: true });
   }, [page, requestedClaimType, requestedStatus, searchParams, setSearchParams, windowValue]);

   const overviewUrl = useMemo(
      () => requestUrl("MANAGEMENT_PIPELINE_OVERVIEW", { window: windowValue }),
      [windowValue],
   );
   const runsUrl = useMemo(
      () => requestUrl("MANAGEMENT_PIPELINE_RUNS", {
         window: windowValue,
         status: statusFilter,
         claim_type: claimTypeFilter,
         page,
      }),
      [claimTypeFilter, page, statusFilter, windowValue],
   );
   const overviewRequest = useManagementRequest(overviewUrl);
   const runsRequest = useManagementRequest(runsUrl);

   const updateQuery = (updates, { resetPage = false } = {}) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(updates).forEach(([key, value]) => {
         if (!value || value === "1") next.delete(key);
         else next.set(key, value);
      });
      if (resetPage) next.delete("page");
      setSearchParams(next);
   };

   const overview = overviewRequest.data;
   const runs = runsRequest.data;

   return (
      <div className="management-page management-pipeline-page">
         <ManagementPageHeader
            title="Pipeline Health"
            subtitle="Operational telemetry for recent verification runs, pipeline stages, and provider fallback behavior."
            actions={(
               <label className="management-window-control">
                  <span>Time window</span>
                  <select
                     value={windowValue}
                     onChange={(event) => updateQuery({ window: event.target.value }, { resetPage: true })}
                  >
                     {WINDOW_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
               </label>
            )}
         />

         <div className="management-boundary-note">
            <Icons name="info" size={19} />
            <div>
               <strong>Read-only operational telemetry</strong>
               <p>
                  This view summarizes actual verification executions. It does not actively probe services or expose claim content, user activity, prompts, or evidence bodies.
               </p>
            </div>
         </div>

         <ManagementRequestState
            loading={overviewRequest.loading}
            error={overviewRequest.error}
            onRetry={overviewRequest.retry}
         >
            {overview ? (
               <>
                  <section className="management-pipeline-metrics" aria-label="Pipeline summary">
                     <Metric label="Total runs" value={overview.runs.total} />
                     <Metric label="Completed" value={overview.runs.statuses.COMPLETED} />
                     <Metric label="Abstained" value={overview.runs.statuses.ABSTAINED} />
                     <Metric label="Failed" value={overview.runs.statuses.FAILED} />
                     <Metric label="Median duration" value={formatManagementDuration(overview.runs.median_duration_ms)} />
                     <Metric label="P95 duration" value={formatManagementDuration(overview.runs.p95_duration_ms)} />
                  </section>

                  <section className="management-section">
                     <div className="management-section__heading">
                        <h2>Run outcomes</h2>
                        <p>Every lifecycle state remains distinct; abstention is not counted as failure. Abstained means verification completed without a decisive verdict; the user may still receive an UNVERIFIED or out-of-scope result.</p>
                     </div>
                     <div className="management-outcome-strip">
                        {STATUS_ORDER.map((runStatus) => (
                           <div key={runStatus}>
                              <ManagementStatus value={runStatus} />
                              <strong>{overview.runs.statuses[runStatus]}</strong>
                           </div>
                        ))}
                     </div>
                  </section>

                  <section className="management-section">
                     <div className="management-section__heading">
                        <h2>Stage performance</h2>
                        <p>Observed stage timing, ordered by the slowest P95 duration.</p>
                     </div>
                     {overview.stages.length ? (
                        <div className="management-table-wrap management-section__table">
                           <table className="management-table">
                              <thead><tr><th>Stage</th><th>Samples</th><th>Failures</th><th>Median</th><th>P95</th><th>Max</th></tr></thead>
                              <tbody>
                                 {overview.stages.map((stage) => (
                                    <tr key={stage.stage}>
                                       <td data-label="Stage"><strong>{formatManagementOperationalLabel(stage.stage)}</strong></td>
                                       <td data-label="Samples">{stage.samples}</td>
                                       <td data-label="Failures" className={stage.failures ? "management-value--critical" : ""}>{stage.failures}</td>
                                       <td data-label="Median">{formatManagementDuration(stage.median_duration_ms)}</td>
                                       <td data-label="P95">{formatManagementDuration(stage.p95_duration_ms)}</td>
                                       <td data-label="Max">{formatManagementDuration(stage.max_duration_ms)}</td>
                                    </tr>
                                 ))}
                              </tbody>
                           </table>
                        </div>
                     ) : <div className="management-inline-empty">No stage telemetry was recorded in this window.</div>}
                  </section>

                  <section className="management-section">
                     <div className="management-section__heading">
                        <h2>Provider health</h2>
                        <p>Provider outcomes inferred from real LLM calls. Groq usage represents configured fallback activity, not failure.</p>
                     </div>
                     <div className="management-fallback-summary" aria-label="Groq fallback summary">
                        <div><span>Groq attempts</span><strong>{overview.fallback.groq_attempts}</strong></div>
                        <div><span>Groq successes</span><strong>{overview.fallback.groq_successes}</strong></div>
                        <div><span>Runs using Groq</span><strong>{overview.fallback.runs_using_groq}</strong></div>
                     </div>
                     {overview.providers.length ? (
                        <div className="management-table-wrap management-section__table">
                           <table className="management-table">
                              <thead><tr><th>Operation</th><th>Provider</th><th>Attempts</th><th>Successes</th><th>Failures</th><th>Median</th><th>P95</th><th>Max</th></tr></thead>
                              <tbody>
                                 {overview.providers.map((provider) => (
                                    <tr key={`${provider.operation}-${provider.provider}`}>
                                       <td data-label="Operation"><strong>{formatManagementOperationalLabel(provider.operation)}</strong></td>
                                       <td data-label="Provider">{formatManagementOperationalLabel(provider.provider)}</td>
                                       <td data-label="Attempts">{provider.attempts}</td>
                                       <td data-label="Successes">{provider.successes}</td>
                                       <td data-label="Failures" className={provider.failures ? "management-value--critical" : ""}>{provider.failures}</td>
                                       <td data-label="Median">{formatManagementDuration(provider.median_duration_ms)}</td>
                                       <td data-label="P95">{formatManagementDuration(provider.p95_duration_ms)}</td>
                                       <td data-label="Max">{formatManagementDuration(provider.max_duration_ms)}</td>
                                    </tr>
                                 ))}
                              </tbody>
                           </table>
                        </div>
                     ) : <div className="management-inline-empty">No provider telemetry was recorded in this window.</div>}
                  </section>
               </>
            ) : null}
         </ManagementRequestState>

         <section className="management-section">
            <div className="management-section__heading">
               <h2>Recent runs</h2>
               <p>Inspect lifecycle state and the ordered operational timeline without opening claim content.</p>
            </div>
            <div className="management-filter-panel management-pipeline-filters">
               <div className="management-filters management-filters--compact">
                  <label>
                     <span>Status</span>
                     <select value={statusFilter} onChange={(event) => updateQuery({ status: event.target.value }, { resetPage: true })}>
                        <option value="">All statuses</option>
                        {STATUS_ORDER.map((value) => <option key={value} value={value}>{formatManagementOperationalLabel(value)}</option>)}
                     </select>
                  </label>
                  <label>
                     <span>Claim type</span>
                     <select value={claimTypeFilter} onChange={(event) => updateQuery({ claim_type: event.target.value }, { resetPage: true })}>
                        <option value="">All claim types</option>
                        {["TEXT", "IMAGE", "VIDEO", "URL", "FILE"].map((value) => <option key={value} value={value}>{formatManagementClaimType(value)}</option>)}
                     </select>
                  </label>
               </div>
            </div>
            <ManagementRequestState
               loading={runsRequest.loading}
               error={runsRequest.error}
               onRetry={runsRequest.retry}
               empty={runs?.count === 0}
               emptyMessage="No verification runs match the selected window and filters."
            >
               {runs ? (
                  <div className="management-table-wrap">
                     <table className="management-table">
                        <thead><tr><th>Run</th><th>Claim type</th><th>Status</th><th>Started</th><th>Duration</th><th>Failure stage</th><th>Details</th></tr></thead>
                        <tbody>
                           {runs.results.map((run) => (
                              <tr key={run.id}>
                                 <td data-label="Run"><span className="management-run-id" title={run.id} aria-label={`Run ${run.id}`}>{run.id.slice(0, 8)}</span></td>
                                 <td data-label="Claim type">{formatManagementClaimType(run.claim_type)}</td>
                                 <td data-label="Status"><ManagementStatus value={run.status} /></td>
                                 <td data-label="Started">{formatManagementDate(run.started_at)}</td>
                                 <td data-label="Duration">{formatManagementDuration(run.duration_ms)}</td>
                                 <td data-label="Failure stage">{run.failure_stage ? formatManagementOperationalLabel(run.failure_stage) : "—"}</td>
                                 <td data-label="Details">
                                    <Link className="management-inline-link" to={`/management/pipeline/runs/${run.id}`} state={{ from: `${location.pathname}${location.search}` }}>Inspect run</Link>
                                 </td>
                              </tr>
                           ))}
                        </tbody>
                     </table>
                     <ManagementPagination count={runs.count} page={page} onPageChange={(nextPage) => updateQuery({ page: String(nextPage) })} />
                  </div>
               ) : null}
            </ManagementRequestState>
         </section>
      </div>
   );
}

export default ManagementPipelineHealthPage;
