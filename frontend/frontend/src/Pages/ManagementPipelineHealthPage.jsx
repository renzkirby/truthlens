import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import Button from "../components/ui/Button";
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
const SUPPORTED_CLAIM_TYPES = ["TEXT", "IMAGE", "URL", "FILE"];
const VALID_CLAIM_TYPES = new Set(["", ...SUPPORTED_CLAIM_TYPES]);
const STATUS_ORDER = ["PENDING", "RUNNING", "COMPLETED", "ABSTAINED", "FAILED", "CANCELLED"];

function requestUrl(endpoint, params) {
   const url = new URL(resolveApiEndpoint(endpoint));
   Object.entries(params).forEach(([key, value]) => {
      if (value !== "" && value !== null && value !== undefined) url.searchParams.set(key, value);
   });
   return url.toString();
}

function parseLocalDateInput(value) {
   if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
   const [year, month, day] = value.split("-").map(Number);
   const date = new Date(year, month - 1, day);
   if (
      Number.isNaN(date.getTime())
      || date.getFullYear() !== year
      || date.getMonth() !== month - 1
      || date.getDate() !== day
   ) {
      return null;
   }
   return date;
}

function isValidDateInput(value) {
   return parseLocalDateInput(value) !== null;
}

function localDayBounds(value) {
   const start = parseLocalDateInput(value);
   if (!start) return { startedAfter: "", startedBefore: "" };
   const end = new Date(start);
   end.setDate(end.getDate() + 1);
   return {
      startedAfter: start.toISOString(),
      startedBefore: end.toISOString(),
   };
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
   const [showAllStages, setShowAllStages] = useState(false);
   const [showAllProviders, setShowAllProviders] = useState(false);
   const location = useLocation();
   const requestedWindow = searchParams.get("window") || "7d";
   const windowValue = VALID_WINDOWS.has(requestedWindow) ? requestedWindow : "7d";
   const requestedStatus = searchParams.get("status") || "";
   const statusFilter = VALID_STATUSES.has(requestedStatus) ? requestedStatus : "";
   const requestedClaimType = searchParams.get("claim_type") || "";
   const claimTypeFilter = VALID_CLAIM_TYPES.has(requestedClaimType) ? requestedClaimType : "";
   const requestedStartedOn = searchParams.get("started_on") || "";
   const startedOnFilter = isValidDateInput(requestedStartedOn) ? requestedStartedOn : "";
   const { startedAfter, startedBefore } = localDayBounds(startedOnFilter);
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
      if (requestedStartedOn && !isValidDateInput(requestedStartedOn)) {
         next.delete("started_on");
         changed = true;
      }
      if (searchParams.has("page") && page === 1 && searchParams.get("page") !== "1") {
         next.delete("page");
         changed = true;
      }
      if (changed) setSearchParams(next, { replace: true });
   }, [page, requestedClaimType, requestedStartedOn, requestedStatus, searchParams, setSearchParams, windowValue]);

   const overviewUrl = useMemo(
      () => requestUrl("MANAGEMENT_PIPELINE_OVERVIEW", { window: windowValue }),
      [windowValue],
   );
   const runsUrl = useMemo(
      () => requestUrl("MANAGEMENT_PIPELINE_RUNS", {
         window: windowValue,
         status: statusFilter,
         claim_type: claimTypeFilter,
         started_after: startedAfter,
         started_before: startedBefore,
         page,
         page_size: 15,
      }),
      [claimTypeFilter, page, startedAfter, startedBefore, statusFilter, windowValue],
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
   const hasRunFilters = Boolean(statusFilter || claimTypeFilter || startedOnFilter);
   const stagePreview = overview?.stages?.slice(0, 6) || [];
   const providerPreview = useMemo(() => {
      if (!overview?.providers?.length) return [];
      return [...overview.providers]
         .sort((left, right) => (
            right.failures - left.failures
            || right.attempts - left.attempts
            || left.operation.localeCompare(right.operation)
            || left.provider.localeCompare(right.provider)
         ))
         .slice(0, 6);
   }, [overview]);
   const stagesToDisplay = showAllStages ? (overview?.stages || []) : stagePreview;
   const providersToDisplay = showAllProviders ? (overview?.providers || []) : providerPreview;
   const providerFailureOperations = overview?.providers?.filter(
      (provider) => provider.failures > 0,
   ).length || 0;
   const slowestStage = overview?.stages?.[0] || null;

   return (
      <div className="management-page management-pipeline-page">
         <ManagementPageHeader
            title="Verification System Health"
            subtitle="Monitor whether automated verification is completing successfully and investigate failed or slow runs."
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
               <strong>Use this page to diagnose verification operations</strong>
               <p>
                  Start with failed runs and the Attention needed summary. Stage and provider details are
                  diagnostic information for troubleshooting; this page does not expose claim content,
                  user activity, prompts, or evidence bodies.
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
                  <section className="management-pipeline-summary" aria-label="Pipeline summary">
                     <div className="management-pipeline-metrics">
                        <Metric label="Total runs" value={overview.runs.total} />
                        <Metric label="Completed" value={overview.runs.statuses.COMPLETED} />
                        <Metric label="Abstained" value={overview.runs.statuses.ABSTAINED} />
                        <Metric label="Failed" value={overview.runs.statuses.FAILED} />
                        <Metric label="Median duration" value={formatManagementDuration(overview.runs.median_duration_ms)} />
                        <Metric label="P95 duration" value={formatManagementDuration(overview.runs.p95_duration_ms)} />
                     </div>
                     <div className="management-pipeline-status-summary" aria-label="Run outcomes">
                        {STATUS_ORDER.map((runStatus) => (
                           <span key={runStatus}>
                              <ManagementStatus value={runStatus} />
                              <strong>{overview.runs.statuses[runStatus]}</strong>
                           </span>
                        ))}
                     </div>
                     <p className="management-pipeline-summary__note">
                        Abstained runs completed without a decisive verdict and are not counted as failures.
                     </p>
                  </section>

                  <section className="management-section management-attention-section">
                     <div className="management-section__heading">
                        <h2>Attention needed</h2>
                        <p>Immediate operational signals from the selected reporting window.</p>
                     </div>
                     <div className="management-attention-grid">
                        <article>
                           <Icons name={overview.runs.statuses.FAILED ? "alert-circle" : "check-circle"} size={19} />
                           <div>
                              <strong>{overview.runs.statuses.FAILED} failed runs</strong>
                              <span>{overview.runs.statuses.FAILED ? "Review failed executions and their failure stages." : "No failed verification runs in this window."}</span>
                           </div>
                        </article>
                        <article>
                           <Icons name={providerFailureOperations ? "activity" : "check-circle"} size={19} />
                           <div>
                              <strong>{providerFailureOperations} provider operations with failures</strong>
                              <span>{providerFailureOperations ? "Fallbacks may still have completed these runs successfully." : "No provider-operation failures were recorded."}</span>
                           </div>
                        </article>
                        <article>
                           <Icons name="clock" size={19} />
                           <div>
                              <strong>{slowestStage ? formatManagementOperationalLabel(slowestStage.stage) : "No stage timing yet"}</strong>
                              <span>
                                 {slowestStage
                                    ? `Slowest P95: ${formatManagementDuration(slowestStage.p95_duration_ms)} across ${slowestStage.samples} samples.`
                                    : "No stage telemetry was recorded in this window."}
                              </span>
                           </div>
                        </article>
                     </div>
                  </section>

                  <section className="management-section">
                     <div className="management-section__heading management-section__heading--with-action">
                        <div>
                           <h2>Stage performance</h2>
                           <p>Slowest stages by P95. Expand only when deeper timing analysis is needed.</p>
                        </div>
                        {overview.stages.length > 6 ? (
                           <Button
                              variant="secondary"
                              density="compact"
                              aria-expanded={showAllStages}
                              onClick={() => setShowAllStages((current) => !current)}
                           >
                              {showAllStages ? "Show top 6" : `View all ${overview.stages.length} stages`}
                           </Button>
                        ) : null}
                     </div>
                     {overview.stages.length ? (
                        <div className="management-table-wrap management-section__table">
                           <table className="management-table">
                              <thead><tr><th>Stage</th><th>Samples</th><th>Failures</th><th>Median</th><th>P95</th><th>Max</th></tr></thead>
                              <tbody>
                                 {stagesToDisplay.map((stage) => (
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
                     <div className="management-section__heading management-section__heading--with-action">
                        <div>
                           <h2>Provider health</h2>
                           <p>Failure-bearing and high-use provider operations are prioritized in the compact view.</p>
                        </div>
                        {overview.providers.length > 6 ? (
                           <Button
                              variant="secondary"
                              density="compact"
                              aria-expanded={showAllProviders}
                              onClick={() => setShowAllProviders((current) => !current)}
                           >
                              {showAllProviders ? "Show priority rows" : "View all provider operations"}
                           </Button>
                        ) : null}
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
                                 {providersToDisplay.map((provider) => (
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
                        {SUPPORTED_CLAIM_TYPES.map((value) => <option key={value} value={value}>{formatManagementClaimType(value)}</option>)}
                     </select>
                  </label>
                  <label>
                     <span>Started on</span>
                     <input
                        type="date"
                        value={startedOnFilter}
                        onChange={(event) => updateQuery({ started_on: event.target.value }, { resetPage: true })}
                     />
                  </label>
               </div>
               {hasRunFilters ? (
                  <div className="management-pipeline-filters__actions">
                     <Button
                        variant="secondary"
                        density="compact"
                        onClick={() => updateQuery(
                           { status: "", claim_type: "", started_on: "" },
                           { resetPage: true },
                        )}
                     >
                        Clear filters
                     </Button>
                  </div>
               ) : null}
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
                     <ManagementPagination count={runs.count} page={page} pageSize={15} onPageChange={(nextPage) => updateQuery({ page: String(nextPage) })} />
                  </div>
               ) : null}
            </ManagementRequestState>
         </section>
      </div>
   );
}

export default ManagementPipelineHealthPage;
