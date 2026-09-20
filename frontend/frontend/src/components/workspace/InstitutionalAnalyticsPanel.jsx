import { useEffect, useId, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import { getAuthSessionIdentity } from "../../utils/authIdentity";
import Button from "../ui/Button.jsx";

import "./InstitutionalAnalyticsPanel.css";

const countFormatter = new Intl.NumberFormat(undefined);
const percentFormatter = new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 });
const secondsFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
const dateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "long" });
const VERDICTS = ["FACT", "FAKE", "MISLEADING", "SATIRE"];

function isMeasurement(value) {
   return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isCount(value) {
   return isMeasurement(value) && Number.isInteger(value);
}

function isCurrentStateContract(value) {
   return (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      value.measurement_basis?.source === "PERSISTED_OPERATIONAL_RECORDS" &&
      value.measurement_basis?.coverage === "CURRENT_STATE" &&
      isCount(value.published_fact_checks?.distinct_claims) &&
      isCount(value.factual_corrections?.active_requests) &&
      isCount(value.investigations?.active_assignments) &&
      isCount(value.publication_work?.distinct_claims)
   );
}

function formatCount(value) {
   return isMeasurement(value) ? countFormatter.format(value) : "Not available";
}

function formatPercent(value) {
   return isMeasurement(value) && value <= 1 ? percentFormatter.format(value) : "Not available";
}

function formatDuration(seconds) {
   if (!isMeasurement(seconds)) return "Not available";
   if (seconds > 0 && seconds < 0.1) return "<0.1 sec";
   if (seconds < 60) return `${secondsFormatter.format(seconds)} sec`;

   const units = [
      [86400, "day"],
      [3600, "hr"],
      [60, "min"],
      [1, "sec"],
   ];
   const firstUnit = units.findIndex(([size]) => seconds >= size);
   let remaining = Math.floor(seconds);
   return units
      .slice(firstUnit, firstUnit + 2)
      .map(([size, label]) => {
         const amount = Math.floor(remaining / size);
         remaining %= size;
         return amount ? `${countFormatter.format(amount)} ${label === "day" && amount !== 1 ? "days" : label}` : null;
      })
      .filter(Boolean)
      .join(" ");
}

function MetricList({ items, compact = false }) {
   return (
      <dl className={`institutional-analytics__metrics${compact ? " institutional-analytics__metrics--compact" : ""}`}>
         {items.map(([label, value]) => (
            <div key={label}>
               <dt>{label}</dt>
               <dd>{value}</dd>
            </div>
         ))}
      </dl>
   );
}

function EmptyMessage({ children }) {
   return <p className="institutional-analytics__empty-message">{children}</p>;
}

const BASIS_LABELS = {
   source: "Source",
   coverage: "Coverage",
   historical_backfill: "Historical backfill",
   identity_source: "Reviewer identity source",
   first_observed_claimed_at: "First observed assignment claim",
   last_observed_claimed_at: "Last observed assignment claim",
   first_observed_activity_at: "First observed activity",
   last_observed_activity_at: "Last observed activity",
   first_observed_participation_at: "First observed participation",
   last_observed_participation_at: "Last observed participation",
   first_observed_resolution_at: "First observed resolution",
   last_observed_resolution_at: "Last observed resolution",
};

const BASIS_VALUES = {
   PERSISTED_OPERATIONAL_RECORDS: "Persisted operational records",
   CURRENT_STATE: "Current state",
   ACCOUNTABILITY_EVENT: "Accountability events",
   INSTRUMENTATION_ERA_ONLY: "Recorded since institutional tracking began",
   OBSERVED_AUTHORITATIVE_RESOLUTION_EVENTS_ONLY: "Observed authoritative resolution events only",
   DURABLE_ACTOR_ID_SNAPSHOT_EVENTS_ONLY: "Events with durable reviewer identity snapshots only",
   ACTOR_ID_SNAPSHOT: "Durable reviewer identity snapshots",
};

function BasisValue({ field, value }) {
   if (field.endsWith("_at")) {
      const date = typeof value === "string" && value ? new Date(value) : null;
      return date && !Number.isNaN(date.getTime()) ? (
         <time dateTime={value}>{dateFormatter.format(date)}</time>
      ) : (
         "Not observed"
      );
   }
   if (typeof value === "boolean") return value ? "Yes" : "No";
   return typeof value === "string" ? (BASIS_VALUES[value] ?? value) : "Not available";
}

function MeasurementBasis({ title, basis, fields }) {
   const returnedFields = fields.filter((field) => Object.hasOwn(basis ?? {}, field));
   return (
      <section className="institutional-analytics__basis">
         <h5>{title}</h5>
         {returnedFields.length ? (
            <dl>
               {returnedFields.map((field) => (
                  <div key={field}>
                     <dt>{BASIS_LABELS[field]}</dt>
                     <dd>
                        <BasisValue field={field} value={basis[field]} />
                     </dd>
                  </div>
               ))}
            </dl>
         ) : (
            <p>Measurement basis not available from current observations.</p>
         )}
      </section>
   );
}

function InstitutionalAnalyticsPanel({ organizationId, organizationName }) {
   const { authFetch, token, user } = useAuth();
   const headingId = useId();
   const [retryVersion, setRetryVersion] = useState(0);
   const [result, setResult] = useState(null);
   const generationRef = useRef(0);
   const authIdentity = getAuthSessionIdentity(user, token);
   const requestUrl = organizationId ? resolveApiEndpoint("ORGANIZATION_VERIFICATION_ANALYTICS", organizationId) : null;
   const requestKey = JSON.stringify([authIdentity, organizationId, requestUrl, retryVersion]);

   useEffect(() => {
      const generation = ++generationRef.current;
      let cancelled = false;
      if (!requestUrl) return undefined;

      // The identity guard hides old data immediately, before effects run.
      // Queue request state to follow the workspace's effect/lint convention.
      queueMicrotask(() => {
         if (!cancelled && generationRef.current === generation) {
            setResult({ key: requestKey, status: "loading" });
         }
      });

      async function load() {
         try {
            const data = await authFetch(requestUrl, { method: "GET" });
            if (cancelled || generationRef.current !== generation) return;
            if (
               !data ||
               String(data.organization_id) !== String(organizationId) ||
               !isCurrentStateContract(data.current_state)
            ) {
               throw new Error("Unexpected analytics response contract.");
            }
            setResult({ key: requestKey, status: "ready", data });
         } catch (error) {
            if (cancelled || generationRef.current !== generation) return;
            setResult({
               key: requestKey,
               status: error?.status === 401 || error?.status === 403 ? "denied" : "error",
            });
         }
      }
      load();
      return () => {
         cancelled = true;
      };
   }, [authFetch, organizationId, requestKey, requestUrl]);

   const currentResult = result?.key === requestKey ? result : null;
   const status = currentResult?.status ?? "loading";
   const data = status === "ready" ? currentResult.data : null;
   const currentState = data?.current_state;
   const attempts = data?.attempts;
   const reliability = data?.reliability;
   const turnaround = data?.completed_turnaround;
   const activity = data?.activity;
   const reviewers = data?.reviewer_participation;
   const resolution = data?.resolution_distribution?.latest_observed_resolutions;
   const currentStateCounts = currentState
      ? [
           currentState.published_fact_checks.distinct_claims,
           currentState.factual_corrections.active_requests,
           currentState.investigations.active_assignments,
           currentState.publication_work.distinct_claims,
        ]
      : [];
   const currentStateIsEmpty = currentStateCounts.length === 4 && currentStateCounts.every((count) => count === 0);
   const commonBasisFields = ["source", "coverage", "historical_backfill"];
   const hasTerminalAttempts = isMeasurement(attempts?.terminal) && attempts.terminal > 0;
   const hasCompletedTurnaround = isMeasurement(turnaround?.count) && turnaround.count > 0;
   const hasRecordedOutcomes = isMeasurement(resolution?.count) && resolution.count > 0;

   return (
      <section className="institutional-analytics" aria-labelledby={headingId}>
         <header className="institutional-analytics__header">
            <h3 id={headingId}>Organization overview</h3>
            <p>
               Current work{organizationName ? ` at ${organizationName}` : ""} and eligible recorded activity, presented
               separately so the measurements remain clear.
            </p>
         </header>

         {!requestUrl ? (
            <p className="institutional-analytics__state">Select an organization to review institutional analytics.</p>
         ) : status === "loading" ? (
            <p className="institutional-analytics__state" role="status">
               Loading institutional analytics…
            </p>
         ) : status === "denied" ? (
            <div className="institutional-analytics__state" role="alert">
               <h4>Institutional analytics access unavailable</h4>
               <p>Your current session does not have access to analytics for this organization.</p>
            </div>
         ) : status === "error" ? (
            <div className="institutional-analytics__state" role="alert">
               <h4>Institutional analytics are temporarily unavailable</h4>
               <p>The required organization measurements could not be loaded. Try again to reload Analytics.</p>
               <Button variant="secondary" onClick={() => setRetryVersion((version) => version + 1)}>
                  Retry Analytics
               </Button>
            </div>
         ) : (
            <div className="institutional-analytics__dashboard">
               <section className="institutional-analytics__section institutional-analytics__section--current">
                  <header className="institutional-analytics__section-header">
                     <span className="institutional-analytics__coverage-label institutional-analytics__coverage-label--current">
                        Current operational records
                     </span>
                     <h4>Your organization at a glance</h4>
                     <p>Publication and verification work in your organization right now.</p>
                  </header>

                  <dl className="institutional-analytics__current-grid">
                     <div className="institutional-analytics__current-card">
                        <dt>Published fact-checks</dt>
                        <dd className="institutional-analytics__current-value">
                           {formatCount(currentState.published_fact_checks.distinct_claims)}
                        </dd>
                        <dd className="institutional-analytics__current-description">
                           Current published fact-check records for distinct claims.
                        </dd>
                     </div>
                     <div className="institutional-analytics__current-card">
                        <dt>Active factual corrections</dt>
                        <dd className="institutional-analytics__current-value">
                           {formatCount(currentState.factual_corrections.active_requests)}
                        </dd>
                        <dd className="institutional-analytics__current-description">
                           Correction requests currently in progress.
                        </dd>
                     </div>
                     <div className="institutional-analytics__current-card">
                        <dt>Active investigations</dt>
                        <dd className="institutional-analytics__current-value">
                           {formatCount(currentState.investigations.active_assignments)}
                        </dd>
                        <dd className="institutional-analytics__current-description">
                           Currently active organization-assigned verification work.
                        </dd>
                     </div>
                     <div className="institutional-analytics__current-card">
                        <dt>Open publication work</dt>
                        <dd className="institutional-analytics__current-value">
                           {formatCount(currentState.publication_work.distinct_claims)}
                        </dd>
                        <dd className="institutional-analytics__current-description">
                           Claims with initial or editorial publication drafts or reviews in progress.
                        </dd>
                     </div>
                  </dl>

                  {currentStateIsEmpty && (
                     <EmptyMessage>No current verification or publication work is recorded for this organization.</EmptyMessage>
                  )}
                  <p className="institutional-analytics__overlap-note">
                     These categories describe different types of work and may overlap.
                  </p>
               </section>

               <section className="institutional-analytics__section">
                  <header className="institutional-analytics__section-header">
                     <span className="institutional-analytics__coverage-label">Recorded activity since tracking began</span>
                     <h4>Institutional activity since tracking began</h4>
                     <p>
                        These are eligible actions recorded since institutional tracking began. Earlier work has not
                        been reconstructed.
                     </p>
                  </header>

                  <div className="institutional-analytics__activity-grid">
                     <section className="institutional-analytics__activity-group">
                        <h5>Evidence review</h5>
                        <dl className="institutional-analytics__principal-metric">
                           <dt>Evidence review decisions</dt>
                           <dd>{formatCount(activity?.evidence_review?.decisions)}</dd>
                        </dl>
                        <MetricList
                           compact
                           items={[
                              ["Evidence verified", formatCount(activity?.evidence_review?.verified)],
                              ["Evidence rejected", formatCount(activity?.evidence_review?.rejected)],
                           ]}
                        />
                        <p className="institutional-analytics__supporting-copy">
                           Evidence verified means submissions verified by reviewers, not claims proven FACT.
                        </p>
                     </section>

                     <section className="institutional-analytics__activity-group">
                        <h5>Adjudication and publication</h5>
                        <dl className="institutional-analytics__principal-metric">
                           <dt>Verdicts issued</dt>
                           <dd>{formatCount(activity?.adjudication?.verdicts_issued)}</dd>
                        </dl>
                        <MetricList
                           compact
                           items={[
                              ["Adjudications started", formatCount(activity?.adjudication?.started)],
                              ["Initial publications recorded", formatCount(activity?.publication?.initial_published)],
                           ]}
                        />
                        <p className="institutional-analytics__supporting-copy">
                           These are recorded events, not totals of all current decisions or published fact-checks.
                        </p>
                     </section>

                     <section className="institutional-analytics__activity-group">
                        <h5>Reviewer participation</h5>
                        <dl className="institutional-analytics__principal-metric">
                           <dt>Unique observed reviewers</dt>
                           <dd>{formatCount(reviewers?.unique_reviewers)}</dd>
                        </dl>
                        <MetricList
                           compact
                           items={[
                              ["Evidence-review reviewers", formatCount(reviewers?.by_stage?.evidence_review)],
                              ["Adjudication reviewers", formatCount(reviewers?.by_stage?.adjudication)],
                           ]}
                        />
                        <p className="institutional-analytics__supporting-copy">
                           Distinct recorded identities, not current staff headcount. One reviewer may appear in both stages.
                        </p>
                     </section>
                  </div>
               </section>

               <div className="institutional-analytics__support-grid">
                  <section className="institutional-analytics__section institutional-analytics__support-panel">
                     <header className="institutional-analytics__section-header">
                        <h4>Verification workflow</h4>
                        <p>Recorded assignment attempts, not the current investigation inventory.</p>
                     </header>

                     <dl className="institutional-analytics__workflow-summary">
                        <div>
                           <dt>Investigations taken</dt>
                           <dd>{formatCount(attempts?.claimed)}</dd>
                        </div>
                        <div>
                           <dt>Completed investigations</dt>
                           <dd>{formatCount(attempts?.completed)}</dd>
                        </div>
                        <div>
                           <dt>Returned to shared intake</dt>
                           <dd>{formatCount(attempts?.released)}</dd>
                        </div>
                     </dl>

                     <dl className="institutional-analytics__supporting-row">
                        <div>
                           <dt>Observed investigations without a recorded completion or release</dt>
                           <dd>{formatCount(attempts?.active)}</dd>
                        </div>
                     </dl>
                     <p className="institutional-analytics__supporting-copy">
                        This recorded-history count can differ from the current active-investigation count.
                     </p>

                     <div className="institutional-analytics__workflow-details">
                        <section className="institutional-analytics__workflow-group">
                           <h5>Completion and return proportions</h5>
                           {attempts?.terminal === 0 ? (
                              <EmptyMessage>
                                 Completion and release percentages will appear after an observed investigation is completed
                                 or returned.
                              </EmptyMessage>
                           ) : hasTerminalAttempts ? (
                              <div className="institutional-analytics__rate-grid">
                                 <p>
                                    Of observed investigations that ended in completion or release, {" "}
                                    <strong>{formatPercent(reliability?.terminal_completion_rate)}</strong> were completed.
                                 </p>
                                 <p>
                                    Of observed investigations that ended in completion or release, {" "}
                                    <strong>{formatPercent(reliability?.terminal_release_rate)}</strong> were returned to
                                    shared intake.
                                 </p>
                              </div>
                           ) : (
                              <EmptyMessage>Completion and release measurements are unavailable.</EmptyMessage>
                           )}
                        </section>

                        <section className="institutional-analytics__workflow-group">
                           <h5>Completed-investigation turnaround</h5>
                           <p className="institutional-analytics__supporting-copy">
                              Measured from assignment claim to assignment completion, not from original claim creation to
                              publication.
                           </p>
                           {turnaround?.count === 0 ? (
                              <EmptyMessage>
                                 Turnaround measurements will appear after a completed investigation is recorded.
                              </EmptyMessage>
                           ) : hasCompletedTurnaround ? (
                              <>
                                 <dl className="institutional-analytics__turnaround-primary">
                                    <div>
                                       <dt>Median</dt>
                                       <dd>{formatDuration(turnaround?.median_seconds)}</dd>
                                    </div>
                                    <div>
                                       <dt>Average</dt>
                                       <dd>{formatDuration(turnaround?.average_seconds)}</dd>
                                    </div>
                                 </dl>
                                 <MetricList
                                    compact
                                    items={[
                                       ["Minimum", formatDuration(turnaround?.minimum_seconds)],
                                       ["Maximum", formatDuration(turnaround?.maximum_seconds)],
                                       ["Completed attempts measured", formatCount(turnaround?.count)],
                                    ]}
                                 />
                              </>
                           ) : (
                              <EmptyMessage>Completed-investigation turnaround is unavailable.</EmptyMessage>
                           )}
                        </section>
                     </div>
                  </section>

                  <section className="institutional-analytics__section institutional-analytics__support-panel">
                     <header className="institutional-analytics__section-header">
                        <h4>Recorded decision outcomes</h4>
                        <p>Latest observed authoritative decisions, not a measure of organizational performance.</p>
                     </header>

                     {resolution?.count === 0 ? (
                        <div className="institutional-analytics__outcomes-empty">
                           <h5>No recorded decision outcomes yet.</h5>
                           <p>
                              Verdict distribution will appear when qualifying authoritative decisions are recorded during
                              the measurement period.
                           </p>
                        </div>
                     ) : hasRecordedOutcomes ? (
                        <>
                           <p className="institutional-analytics__outcome-total">
                              <strong>{formatCount(resolution.count)}</strong> recorded outcomes
                           </p>
                           <dl className="institutional-analytics__outcome-list">
                              {VERDICTS.map((verdict) => (
                                 <div key={verdict}>
                                    <dt>{verdict}</dt>
                                    <dd>{formatCount(resolution?.by_verdict?.[verdict])}</dd>
                                 </div>
                              ))}
                           </dl>
                        </>
                     ) : (
                        <EmptyMessage>Recorded decision outcome measurements are unavailable.</EmptyMessage>
                     )}
                  </section>

               </div>

               <details className="institutional-analytics__notes">
                  <summary>How these measurements are calculated</summary>
                  <div className="institutional-analytics__notes-content">
                     <p className="institutional-analytics__notes-lead">
                        Current records describe work as it stands now. Historical measurements count eligible events
                        recorded since tracking began; earlier activity has not been reconstructed.
                     </p>
                     <dl className="institutional-analytics__notes-definitions">
                        <div>
                           <dt>Current operational records</dt>
                           <dd>Published fact-checks, active corrections and assignments, and open publication work.
                              Categories can overlap and should not be added together.</dd>
                        </div>
                        <div>
                           <dt>Recorded workflow and publication activity</dt>
                           <dd>Only eligible observed events. Current publications and investigations can differ from
                              their recorded-history counterparts.</dd>
                        </div>
                        <div>
                           <dt>Reviewer participation</dt>
                           <dd>Durable reviewer identities in eligible events, including applicable correction or
                              verdict-revision work. Not current staff headcount; reviewers can appear in both stages.</dd>
                        </div>
                        <div>
                           <dt>Decision outcomes</dt>
                           <dd>Latest observed authoritative resolution events, not necessarily all historical decisions
                              and not a measure of factual quality.</dd>
                        </div>
                     </dl>
                     <p className="institutional-analytics__notes-clarification">
                        A published fact-check stays in the published count while a correction is active. A correction
                        contributes to open publication work only when a separate qualifying draft or review exists.
                     </p>
                     <details className="institutional-analytics__coverage-details">
                        <summary>Detailed sources, coverage, and observed dates</summary>
                        <p>These definitions and dates describe the basis of each measurement, not a guaranteed start
                           date for the tracking system.</p>
                        <div className="institutional-analytics__basis-grid">
                           <MeasurementBasis
                           title="Current operational records"
                           basis={currentState?.measurement_basis}
                           fields={["source", "coverage"]}
                        />
                        <MeasurementBasis
                           title="Verification workflow"
                           basis={data.measurement_basis}
                           fields={[...commonBasisFields, "first_observed_claimed_at", "last_observed_claimed_at"]}
                        />
                        <MeasurementBasis
                           title="Institutional activity"
                           basis={activity?.measurement_basis}
                           fields={[...commonBasisFields, "first_observed_activity_at", "last_observed_activity_at"]}
                        />
                        <MeasurementBasis
                           title="Reviewer participation"
                           basis={reviewers?.measurement_basis}
                           fields={[
                              ...commonBasisFields,
                              "identity_source",
                              "first_observed_participation_at",
                              "last_observed_participation_at",
                           ]}
                        />
                        <MeasurementBasis
                           title="Recorded decision outcomes"
                           basis={data.resolution_distribution?.measurement_basis}
                           fields={[...commonBasisFields, "first_observed_resolution_at", "last_observed_resolution_at"]}
                        />
                        </div>
                     </details>
                  </div>
               </details>
            </div>
         )}
      </section>
   );
}

export default InstitutionalAnalyticsPanel;
