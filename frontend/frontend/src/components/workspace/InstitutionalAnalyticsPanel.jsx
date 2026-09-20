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
const utcDateFormatter = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeZone: "UTC" });
const VERDICTS = ["FACT", "FAKE", "MISLEADING", "SATIRE"];
const UTC_DAY_MS = 24 * 60 * 60 * 1000;
const TREND_COUNT_FIELDS = {
   assignment: ["claimed", "released", "completed"],
   evidence_review: ["decisions", "verified", "rejected"],
   adjudication: ["started", "verdicts_issued"],
   publication: ["initial_published"],
};

function isMeasurement(value) {
   return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isCount(value) {
   return isMeasurement(value) && Number.isInteger(value);
}

function getUtcDateString(date) {
   return date.toISOString().slice(0, 10);
}

function utcDateValue(value) {
   const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value ?? "");
   if (!match) return null;
   const timestamp = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
   return getUtcDateString(new Date(timestamp)) === value ? timestamp : null;
}

function shiftUtcDate(value, amount) {
   const timestamp = utcDateValue(value);
   return timestamp === null ? "" : getUtcDateString(new Date(timestamp + amount * UTC_DAY_MS));
}

function formatUtcInstant(date) {
   return date.toISOString().replace(/\.(\d{3})Z$/, (_match, milliseconds) => `.${milliseconds}000Z`);
}

function createAppliedPeriod(mode, startDate, endDate, instant = new Date(), retryVersion = 0) {
   const today = getUtcDateString(instant);
   return {
      mode,
      startDate,
      endDate,
      retryVersion,
      createdAfter: `${startDate}T00:00:00.000000Z`,
      createdBefore:
         endDate === today ? formatUtcInstant(instant) : `${endDate}T23:59:59.999999Z`,
   };
}

function createPresetPeriod(days, mode, instant = new Date()) {
   const endDate = getUtcDateString(instant);
   return createAppliedPeriod(mode, shiftUtcDate(endDate, -(days - 1)), endDate, instant);
}

function validateCustomPeriod(startDate, endDate, instant = new Date()) {
   const start = utcDateValue(startDate);
   const end = utcDateValue(endDate);
   if (start === null || end === null) return "Enter both a valid start date and end date.";
   if (start > end) return "Start date must be on or before end date.";
   if (endDate > getUtcDateString(instant)) return "End date cannot be in the future.";
   if ((end - start) / UTC_DAY_MS + 1 > 90) {
      return "The reporting period cannot include more than 90 UTC calendar dates.";
   }
   return "";
}

function listUtcDates(startDate, endDate) {
   const start = utcDateValue(startDate);
   const end = utcDateValue(endDate);
   if (start === null || end === null || start > end) return [];
   const dates = [];
   for (let timestamp = start; timestamp <= end; timestamp += UTC_DAY_MS) {
      dates.push(getUtcDateString(new Date(timestamp)));
   }
   return dates;
}

function normalizeUtcBoundary(value) {
   const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z$/.exec(value ?? "");
   if (!match) return null;
   const [year, month, day, hour, minute, second] = match.slice(1, 7).map(Number);
   const fraction = (match[7] ?? "").padEnd(6, "0");
   const date = new Date(Date.UTC(year, month - 1, day, hour, minute, second, Number(fraction.slice(0, 3))));
   if (
      date.getUTCFullYear() !== year ||
      date.getUTCMonth() !== month - 1 ||
      date.getUTCDate() !== day ||
      date.getUTCHours() !== hour ||
      date.getUTCMinutes() !== minute ||
      date.getUTCSeconds() !== second
   ) {
      return null;
   }
   return `${value.slice(0, 19)}.${fraction}Z`;
}

function hasTrendCounts(value) {
   return (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      Object.entries(TREND_COUNT_FIELDS).every(
         ([category, fields]) =>
            value[category] !== null &&
            typeof value[category] === "object" &&
            !Array.isArray(value[category]) &&
            fields.every((field) => isCount(value[category][field])),
      )
   );
}

function isTrendResponseContract(value, organizationId, period) {
   const trend = value?.trend;
   const basis = trend?.measurement_basis;
   const expectedDates = listUtcDates(period.startDate, period.endDate);
   return (
      value !== null &&
      typeof value === "object" &&
      String(value.organization_id) === String(organizationId) &&
      trend !== null &&
      typeof trend === "object" &&
      basis?.source === "ACCOUNTABILITY_EVENT" &&
      basis?.coverage === "INSTRUMENTATION_ERA_ONLY" &&
      basis?.historical_backfill === false &&
      basis?.granularity === "DAY" &&
      basis?.bucket_timezone === "UTC" &&
      normalizeUtcBoundary(basis?.created_after) === normalizeUtcBoundary(period.createdAfter) &&
      normalizeUtcBoundary(basis?.created_before) === normalizeUtcBoundary(period.createdBefore) &&
      hasTrendCounts(trend.totals) &&
      Array.isArray(trend.daily) &&
      trend.daily.length === expectedDates.length &&
      trend.daily.every(
         (bucket, index) => bucket?.date === expectedDates[index] && utcDateValue(bucket.date) !== null && hasTrendCounts(bucket),
      )
   );
}

function formatUtcDate(value) {
   const timestamp = utcDateValue(value);
   return timestamp === null ? value : utcDateFormatter.format(new Date(timestamp));
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

function ActivityTrendsSection({ authFetch, authIdentity, organizationId, requestUrl }) {
   const sectionHeadingId = useId();
   const startDateId = useId();
   const endDateId = useId();
   const customHelpId = useId();
   const customErrorId = useId();
   const [appliedPeriod, setAppliedPeriod] = useState(() => createPresetPeriod(7, "last-7"));
   const [periodMode, setPeriodMode] = useState("last-7");
   const [draftRange, setDraftRange] = useState(() => ({
      startDate: appliedPeriod.startDate,
      endDate: appliedPeriod.endDate,
   }));
   const [validationMessage, setValidationMessage] = useState("");
   const [trendResult, setTrendResult] = useState(null);
   const trendGenerationRef = useRef(0);
   const query = new URLSearchParams({
      created_after: appliedPeriod.createdAfter,
      created_before: appliedPeriod.createdBefore,
   });
   const trendRequestUrl = `${requestUrl}?${query.toString()}`;
   const requestKey = JSON.stringify([
      authIdentity,
      organizationId,
      appliedPeriod.createdAfter,
      appliedPeriod.createdBefore,
      appliedPeriod.retryVersion,
   ]);

   useEffect(() => {
      const generation = ++trendGenerationRef.current;
      let cancelled = false;

      queueMicrotask(() => {
         if (!cancelled && trendGenerationRef.current === generation) {
            setTrendResult({ key: requestKey, status: "loading" });
         }
      });

      async function loadTrend() {
         try {
            const data = await authFetch(trendRequestUrl, { method: "GET" });
            if (cancelled || trendGenerationRef.current !== generation) return;
            if (!isTrendResponseContract(data, organizationId, appliedPeriod)) {
               throw new Error("Unexpected activity trend response contract.");
            }
            setTrendResult({ key: requestKey, status: "ready", trend: data.trend });
         } catch (error) {
            if (cancelled || trendGenerationRef.current !== generation) return;
            let status = "error";
            if (error?.status === 401 || error?.status === 403) status = "denied";
            if (error?.status === 404) status = "not-found";
            setTrendResult({ key: requestKey, status });
         }
      }

      loadTrend();
      return () => {
         cancelled = true;
      };
   }, [appliedPeriod, authFetch, organizationId, requestKey, trendRequestUrl]);

   const currentResult = trendResult?.key === requestKey ? trendResult : null;
   const status = currentResult?.status ?? "loading";
   const trend = status === "ready" ? currentResult.trend : null;
   const today = getUtcDateString(new Date());
   const includesCurrentUtcDay = appliedPeriod.endDate === today;
   const expectedDateCount = listUtcDates(appliedPeriod.startDate, appliedPeriod.endDate).length;

   function applyPreset(days, mode) {
      const nextPeriod = createPresetPeriod(days, mode);
      setPeriodMode(mode);
      setValidationMessage("");
      setDraftRange({ startDate: nextPeriod.startDate, endDate: nextPeriod.endDate });
      setAppliedPeriod(nextPeriod);
   }

   function selectPeriodMode(mode) {
      if (mode === "last-7") {
         applyPreset(7, mode);
      } else if (mode === "last-30") {
         applyPreset(30, mode);
      } else {
         setPeriodMode("custom");
         setValidationMessage("");
      }
   }

   function updateDraftRange(field, value) {
      const nextRange = { ...draftRange, [field]: value };
      setDraftRange(nextRange);
      setValidationMessage(validateCustomPeriod(nextRange.startDate, nextRange.endDate));
   }

   function applyCustomPeriod(event) {
      event.preventDefault();
      const instant = new Date();
      const message = validateCustomPeriod(draftRange.startDate, draftRange.endDate, instant);
      setValidationMessage(message);
      if (message) return;
      setAppliedPeriod(createAppliedPeriod("custom", draftRange.startDate, draftRange.endDate, instant));
   }

   function retryTrend() {
      setAppliedPeriod((period) =>
         createAppliedPeriod(
            period.mode,
            period.startDate,
            period.endDate,
            new Date(),
            period.retryVersion + 1,
         ),
      );
   }

   const summaryMeasurements = trend
      ? [
           ["Investigations taken", trend.totals.assignment.claimed],
           ["Evidence review decisions", trend.totals.evidence_review.decisions],
           ["Verdicts issued", trend.totals.adjudication.verdicts_issued],
           ["Initial publications recorded", trend.totals.publication.initial_published],
        ]
      : [];
   const hasNoRecordedActivity =
      trend &&
      Object.entries(TREND_COUNT_FIELDS).every(([category, fields]) =>
         fields.every((field) => trend.totals[category][field] === 0),
      );

   return (
      <section className="institutional-analytics__section institutional-analytics__trends" aria-labelledby={sectionHeadingId}>
         <header className="institutional-analytics__section-header">
            <h4 id={sectionHeadingId}>Activity over time</h4>
            <p>Explore eligible verification activity recorded during a selected UTC reporting period.</p>
         </header>

         <fieldset className="institutional-analytics__period-controls">
            <legend>Reporting period</legend>
            <p className="institutional-analytics__period-help">
               Presets use UTC calendar days, including the current partial UTC day—not rolling hour intervals.
            </p>
            <div className="institutional-analytics__period-options">
               {[
                  ["last-7", "Last 7 days"],
                  ["last-30", "Last 30 days"],
                  ["custom", "Custom range"],
               ].map(([value, label]) => (
                  <label key={value} className="institutional-analytics__period-option">
                     <input
                        type="radio"
                        name={`${sectionHeadingId}-reporting-period`}
                        value={value}
                        checked={periodMode === value}
                        onChange={() => selectPeriodMode(value)}
                     />
                     <span>{label}</span>
                  </label>
               ))}
            </div>
         </fieldset>

         {periodMode === "custom" && (
            <form className="institutional-analytics__custom-period" onSubmit={applyCustomPeriod} noValidate>
               <div className="institutional-analytics__date-field">
                  <label htmlFor={startDateId}>Start date</label>
                  <input
                     id={startDateId}
                     type="date"
                     value={draftRange.startDate}
                     max={today}
                     required
                     aria-invalid={validationMessage ? "true" : undefined}
                     aria-describedby={`${customHelpId}${validationMessage ? ` ${customErrorId}` : ""}`}
                     onChange={(event) => updateDraftRange("startDate", event.target.value)}
                  />
               </div>
               <div className="institutional-analytics__date-field">
                  <label htmlFor={endDateId}>End date</label>
                  <input
                     id={endDateId}
                     type="date"
                     value={draftRange.endDate}
                     max={today}
                     required
                     aria-invalid={validationMessage ? "true" : undefined}
                     aria-describedby={`${customHelpId}${validationMessage ? ` ${customErrorId}` : ""}`}
                     onChange={(event) => updateDraftRange("endDate", event.target.value)}
                  />
               </div>
               <Button type="submit" variant="secondary" className="institutional-analytics__apply-period">
                  Apply period
               </Button>
               <p id={customHelpId} className="institutional-analytics__custom-help">
                  Dates are inclusive UTC calendar dates; the maximum period is 90 dates.
               </p>
               {validationMessage && (
                  <p id={customErrorId} className="institutional-analytics__validation-error" role="alert">
                     {validationMessage}
                  </p>
               )}
            </form>
         )}

         <div className="institutional-analytics__selected-period">
            <span>UTC reporting period</span>
            <p>
               <time dateTime={appliedPeriod.startDate}>
                  {formatUtcDate(appliedPeriod.startDate)} ({appliedPeriod.startDate})
               </time>{" "}
               to{" "}
               <time dateTime={appliedPeriod.endDate}>
                  {formatUtcDate(appliedPeriod.endDate)} ({appliedPeriod.endDate})
               </time>
            </p>
            {includesCurrentUtcDay && <p>The current UTC day is still in progress.</p>}
         </div>

         {status === "loading" ? (
            <p className="institutional-analytics__trend-state" role="status">
               Loading activity for this reporting period…
            </p>
         ) : status === "denied" ? (
            <div className="institutional-analytics__trend-state" role="alert">
               <h5>Activity trends access unavailable</h5>
               <p>Your current session does not have access to activity trends for this organization.</p>
            </div>
         ) : status === "not-found" ? (
            <div className="institutional-analytics__trend-state" role="alert">
               <h5>Organization activity unavailable</h5>
               <p>This organization could not be found or is no longer available to your current session.</p>
            </div>
         ) : status === "error" ? (
            <div className="institutional-analytics__trend-state" role="alert">
               <h5>Activity trends are temporarily unavailable</h5>
               <p>The selected-period activity could not be loaded. Your other Analytics measurements remain available.</p>
               <Button variant="secondary" onClick={retryTrend}>
                  Retry activity trends
               </Button>
            </div>
         ) : (
            <div className="institutional-analytics__trend-results">
               <dl className="institutional-analytics__trend-summary">
                  {summaryMeasurements.map(([label, value]) => (
                     <div key={label}>
                        <dt>{label}</dt>
                        <dd>{formatCount(value)}</dd>
                        <dd className="institutional-analytics__trend-summary-note">Observed during the selected period.</dd>
                     </div>
                  ))}
               </dl>

               {hasNoRecordedActivity && (
                  <div className="institutional-analytics__trend-empty">
                     <h5>No eligible verification activity was recorded during this reporting period.</h5>
                     <p>Earlier work may exist outside the selected dates or outside the instrumentation coverage.</p>
                  </div>
               )}

               <details className="institutional-analytics__daily-details">
                  <summary>Daily activity breakdown ({countFormatter.format(expectedDateCount)} UTC dates)</summary>
                  <p>Each row preserves the backend&apos;s UTC calendar-day bucket, including zero-activity dates.</p>
                  <div
                     className="institutional-analytics__daily-table-region"
                     role="region"
                     tabIndex="0"
                     aria-label="Scrollable daily activity table"
                  >
                     <table className="institutional-analytics__daily-table">
                        <caption>Eligible event counts by UTC calendar date</caption>
                        <thead>
                           <tr>
                              <th scope="col">UTC date</th>
                              <th scope="col">Investigations taken</th>
                              <th scope="col">Evidence review decisions</th>
                              <th scope="col">Verdicts issued</th>
                              <th scope="col">Initial publications recorded</th>
                           </tr>
                        </thead>
                        <tbody>
                           {trend.daily.map((bucket) => (
                              <tr key={bucket.date}>
                                 <th scope="row">
                                    <time dateTime={bucket.date}>{bucket.date}</time>
                                 </th>
                                 <td>{formatCount(bucket.assignment.claimed)}</td>
                                 <td>{formatCount(bucket.evidence_review.decisions)}</td>
                                 <td>{formatCount(bucket.adjudication.verdicts_issued)}</td>
                                 <td>{formatCount(bucket.publication.initial_published)}</td>
                              </tr>
                           ))}
                        </tbody>
                     </table>
                  </div>
                  <p className="institutional-analytics__scroll-hint">Scroll within the table to review every column.</p>
               </details>

               <p className="institutional-analytics__trend-coverage">
                  Counts are eligible accountability events observed during this UTC period. Coverage is limited to the
                  instrumentation era; historical activity has not been backfilled.
               </p>
            </div>
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

               <ActivityTrendsSection
                  authFetch={authFetch}
                  authIdentity={authIdentity}
                  organizationId={organizationId}
                  requestUrl={requestUrl}
               />

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
