import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import { getAuthSessionIdentity } from "../../utils/authIdentity";
import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";
import Input from "../ui/Input.jsx";
import Select from "../ui/Select.jsx";

import "./AccountabilityPanel.css";

const PAGE_SIZE = 25;
const EMPTY_FILTERS = Object.freeze({
   domain: "",
   action_type: "",
   resource_type: "",
   actor: "",
   created_after: "",
   created_before: "",
});


function formatDateTime(value) {
   const date = value ? new Date(value) : null;
   if (!date || Number.isNaN(date.getTime())) {
      return "Time unavailable";
   }
   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function toIsoDateTime(value) {
   if (!value) {
      return "";
   }
   const date = new Date(value);
   return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

function displayKey(value) {
   return String(value)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function compactIdentifier(value) {
   if (!value) {
      return "Identifier unavailable";
   }

   const text = String(value);
   if (text.length <= 20) {
      return text;
   }

   return `${text.slice(0, 8)}…${text.slice(-6)}`;
}

function isEmptyRecord(value) {
   return !value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length === 0;
}

function valuesEqual(left, right) {
   if (left === right) {
      return true;
   }

   try {
      return JSON.stringify(left) === JSON.stringify(right);
   } catch {
      return false;
   }
}

function buildStateChanges(previousState, newState) {
   const previous =
      previousState && typeof previousState === "object" && !Array.isArray(previousState) ? previousState : {};
   const next = newState && typeof newState === "object" && !Array.isArray(newState) ? newState : {};
   const keys = Array.from(new Set([...Object.keys(previous), ...Object.keys(next)]));

   return keys
      .filter((key) => !valuesEqual(previous[key], next[key]))
      .map((key) => ({
         key,
         before: Object.prototype.hasOwnProperty.call(previous, key) ? previous[key] : null,
         after: Object.prototype.hasOwnProperty.call(next, key) ? next[key] : null,
      }));
}

function PrimitiveValue({ value }) {
   if (value === null || value === undefined || value === "") {
      return <span className="accountability-empty-value">Not recorded</span>;
   }
   if (typeof value === "boolean") {
      return value ? "Yes" : "No";
   }
   return <span>{String(value)}</span>;
}

function StructuredValue({ value }) {
   if (Array.isArray(value)) {
      if (value.length === 0) {
         return <span className="accountability-empty-value">None recorded</span>;
      }
      return (
         <ol className="accountability-nested-list">
            {value.map((item, index) => (
               <li key={index}>
                  <StructuredValue value={item} />
               </li>
            ))}
         </ol>
      );
   }
   if (value && typeof value === "object") {
      const entries = Object.entries(value);
      if (entries.length === 0) {
         return <span className="accountability-empty-value">None recorded</span>;
      }
      return (
         <dl className="accountability-data-list">
            {entries.map(([key, nested]) => (
               <div key={key}>
                  <dt>{displayKey(key)}</dt>
                  <dd>
                     <StructuredValue value={nested} />
                  </dd>
               </div>
            ))}
         </dl>
      );
   }
   return <PrimitiveValue value={value} />;
}

function StateChanges({ previousState, newState }) {
   const changes = buildStateChanges(previousState, newState);

   if (changes.length === 0) {
      return (
         <section className="accountability-expanded-section">
            <h4>Changes</h4>
            <p className="accountability-detail-note">No field-level state changes were recorded for this event.</p>
         </section>
      );
   }

   return (
      <section className="accountability-expanded-section">
         <h4>Changes</h4>
         <div className="accountability-change-list" role="list">
            {changes.map((change) => (
               <div className="accountability-change-row" role="listitem" key={change.key}>
                  <div className="accountability-change-field">{displayKey(change.key)}</div>
                  <div className="accountability-change-value">
                     <span className="accountability-change-label">Before</span>
                     <StructuredValue value={change.before} />
                  </div>
                  <span className="accountability-change-arrow" aria-hidden="true">
                     →
                  </span>
                  <div className="accountability-change-value">
                     <span className="accountability-change-label">After</span>
                     <StructuredValue value={change.after} />
                  </div>
               </div>
            ))}
         </div>
      </section>
   );
}

function AccountabilityEvent({ event }) {
   const [expanded, setExpanded] = useState(false);
   const actorLabel = event.actor?.username ? `@${event.actor.username}` : "System";
   const timestamp = event.created_at ? new Date(event.created_at) : null;
   const validTimestamp = timestamp && !Number.isNaN(timestamp.getTime());
   const detailId = `accountability-event-${event.id}-details`;
   const resourceId = event.resource?.id || "";
   const hasReasonOrNotes = Boolean(event.reason_code || event.notes);
   const hasContext = !isEmptyRecord(event.context);

   return (
      <li>
         <article className={`accountability-event${expanded ? " accountability-event--expanded" : ""}`}>
            <header className="accountability-event-header">
               <div className="accountability-event-title">
                  <div className="accountability-badges">
                     <span>{event.domain_label || event.domain}</span>
                     <span>{event.authority?.scope || "Unknown scope"}</span>
                  </div>
                  <h3>{event.action_label || event.action_type}</h3>
               </div>
               {validTimestamp ? (
                  <time dateTime={timestamp.toISOString()}>{formatDateTime(event.created_at)}</time>
               ) : (
                  <span>Time unavailable</span>
               )}
            </header>

            <dl className="accountability-event-meta accountability-event-meta--compact">
               <div>
                  <dt>Actor</dt>
                  <dd>
                     <span>{actorLabel}</span>
                     {event.actor?.historical ? <span className="accountability-historical">Historical</span> : null}
                  </dd>
               </div>
               <div>
                  <dt>Capability</dt>
                  <dd>{event.authority?.capability || "Not applicable"}</dd>
               </div>
               <div>
                  <dt>Authority</dt>
                  <dd>{event.authority?.organization?.name || event.authority?.scope || "Not applicable"}</dd>
               </div>
               <div>
                  <dt>Resource</dt>
                  <dd>
                     <strong>{event.resource?.label || event.resource?.type}</strong>
                     <code title={resourceId || undefined}>{compactIdentifier(resourceId)}</code>
                  </dd>
               </div>
            </dl>

            <div className="accountability-event-actions">
               <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setExpanded((current) => !current)}
                  aria-expanded={expanded}
                  aria-controls={detailId}
                  trailingIcon={<Icons name={expanded ? "chevron-up" : "chevron-down"} size={16} aria-hidden="true" />}
               >
                  {expanded ? "Hide details" : "View details"}
               </Button>
            </div>

            {expanded ? (
               <div className="accountability-expanded" id={detailId}>
                  <StateChanges previousState={event.previous_state} newState={event.new_state} />

                  <section className="accountability-expanded-section">
                     <h4>Reason / notes</h4>
                     {hasReasonOrNotes ? (
                        <dl className="accountability-reason-list">
                           {event.reason_code ? (
                              <div>
                                 <dt>Reason code</dt>
                                 <dd>{event.reason_code}</dd>
                              </div>
                           ) : null}
                           {event.notes ? (
                              <div>
                                 <dt>Notes</dt>
                                 <dd>{event.notes}</dd>
                              </div>
                           ) : null}
                        </dl>
                     ) : (
                        <p className="accountability-detail-note">No reason or notes were recorded.</p>
                     )}
                  </section>

                  {hasContext ? (
                     <details className="accountability-context-disclosure">
                        <summary>
                           <span>Additional context</span>
                           <span className="accountability-context-hint">Technical metadata</span>
                        </summary>
                        <div className="accountability-context-content">
                           <StructuredValue value={event.context} />
                        </div>
                     </details>
                  ) : null}
               </div>
            ) : null}
         </article>
      </li>
   );
}

function AccountabilityPanel({ scope, organizationId, organizationName }) {
   const { authFetch, token, user } = useAuth();
   const [draftFilters, setDraftFilters] = useState({ ...EMPTY_FILTERS });
   const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_FILTERS });
   const [offset, setOffset] = useState(0);
   const [requestVersion, setRequestVersion] = useState(0);
   const [page, setPage] = useState({
      count: 0,
      limit: PAGE_SIZE,
      offset: 0,
      filter_options: { domains: [], actions: [], resources: [] },
      results: [],
   });
   const [loadedRequestKey, setLoadedRequestKey] = useState("");
   const [loading, setLoading] = useState(false);
   const [errorMessage, setErrorMessage] = useState("");
   const [accessDenied, setAccessDenied] = useState(false);
   const requestSequenceRef = useRef(0);

   const requestUrl = useMemo(() => {
      if (scope === "organization" && !organizationId) {
         return null;
      }
      const query = new URLSearchParams({
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });
      if (scope === "organization") {
         query.set("organization_id", String(organizationId));
      }
      for (const [key, value] of Object.entries(appliedFilters)) {
         if (!value) {
            continue;
         }
         query.set(key, key === "created_after" || key === "created_before" ? toIsoDateTime(value) : value);
      }
      const endpoint = scope === "platform" ? "ACCOUNTABILITY_PLATFORM_SAFETY" : "ACCOUNTABILITY_ORGANIZATION";
      return `${resolveApiEndpoint(endpoint)}?${query.toString()}`;
   }, [appliedFilters, offset, organizationId, scope]);

   const authIdentity = getAuthSessionIdentity(user, token);
   const requestKey = `${authIdentity}:${scope}:${organizationId || "platform"}:${requestUrl || "unavailable"}:${requestVersion}`;

   useEffect(() => {
      const sequence = requestSequenceRef.current + 1;
      requestSequenceRef.current = sequence;
      if (!requestUrl) {
         return undefined;
      }

      let cancelled = false;

      // React's set-state-in-effect rule intentionally rejects synchronous
      // state updates in an effect body. Queue the request-state transition so
      // the effect remains responsible for external synchronization (the fetch)
      // while the callback updates React state without a cascading render.
      queueMicrotask(() => {
         if (cancelled || requestSequenceRef.current !== sequence) {
            return;
         }
         setLoading(true);
         setErrorMessage("");
         setAccessDenied(false);
      });

      authFetch(requestUrl, { method: "GET" })
         .then((data) => {
            if (cancelled || requestSequenceRef.current !== sequence) {
               return;
            }
            setPage({
               count: Number(data?.count ?? 0),
               limit: Number(data?.limit ?? PAGE_SIZE),
               offset: Number(data?.offset ?? offset),
               filter_options: {
                  domains: Array.isArray(data?.filter_options?.domains) ? data.filter_options.domains : [],
                  actions: Array.isArray(data?.filter_options?.actions) ? data.filter_options.actions : [],
                  resources: Array.isArray(data?.filter_options?.resources) ? data.filter_options.resources : [],
               },
               results: Array.isArray(data?.results) ? data.results : [],
            });
            setLoadedRequestKey(requestKey);
            setLoading(false);
         })
         .catch((error) => {
            if (cancelled || requestSequenceRef.current !== sequence) {
               return;
            }
            setLoading(false);
            if (error?.status === 401 || error?.status === 403) {
               setAccessDenied(true);
               setPage((current) => ({ ...current, count: 0, results: [] }));
               setLoadedRequestKey("");
               return;
            }
            setErrorMessage(error?.message || "Unable to load accountability history.");
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, offset, requestKey, requestUrl, requestVersion]);

   const visibleActions = useMemo(
      () =>
         page.filter_options.actions.filter((action) => !draftFilters.domain || action.domain === draftFilters.domain),
      [draftFilters.domain, page.filter_options.actions],
   );

   const updateDraftFilter = (key, value) => {
      setDraftFilters((current) => {
         const next = { ...current, [key]: value };
         if (key === "domain") {
            const selectedAction = page.filter_options.actions.find((action) => action.value === current.action_type);
            if (selectedAction && value && selectedAction.domain !== value) {
               next.action_type = "";
            }
         }
         return next;
      });
   };

   const applyFilters = (event) => {
      event.preventDefault();
      setOffset(0);
      setAppliedFilters({ ...draftFilters });
   };

   const clearFilters = () => {
      setDraftFilters({ ...EMPTY_FILTERS });
      setAppliedFilters({ ...EMPTY_FILTERS });
      setOffset(0);
   };

   const refresh = () => {
      setErrorMessage("");
      setRequestVersion((current) => current + 1);
   };

   const targetUnavailable = scope === "organization" && !organizationId;
   const effectiveAccessDenied = accessDenied || targetUnavailable;
   const hasCurrentPage = loadedRequestKey === requestKey;
   const isBlockingLoad = loading && !hasCurrentPage;
   const isRefreshing = loading && hasCurrentPage;
   const hasPrevious = offset > 0;
   const hasNext = offset + page.results.length < page.count;
   const rangeStart = page.results.length === 0 ? 0 : offset + 1;
   const rangeEnd = Math.min(offset + page.results.length, page.count);
   const scopeLabel = scope === "platform" ? "Platform Safety" : organizationName || "this organization";

   return (
      <div className="accountability-panel">
         <p className="accountability-boundary-note">
            <Icons name="activity" size={17} />
            <span>
               Read-only accountability history for <strong>{scopeLabel}</strong>. Entries reflect attributable actions
               recorded when each operation occurred.
            </span>
         </p>

         <form className="accountability-filters" onSubmit={applyFilters}>
            <div className="accountability-filter-grid">
               <label htmlFor="accountability-domain">
                  <span>Domain</span>
                  <Select
                     id="accountability-domain"
                     value={draftFilters.domain}
                     onChange={(event) => updateDraftFilter("domain", event.target.value)}
                  >
                     <option value="">All visible domains</option>
                     {page.filter_options.domains.map((option) => (
                        <option key={option.value} value={option.value}>
                           {option.label}
                        </option>
                     ))}
                  </Select>
               </label>
               <label htmlFor="accountability-action">
                  <span>Action</span>
                  <Select
                     id="accountability-action"
                     value={draftFilters.action_type}
                     onChange={(event) => updateDraftFilter("action_type", event.target.value)}
                  >
                     <option value="">All visible actions</option>
                     {visibleActions.map((option) => (
                        <option key={option.value} value={option.value}>
                           {option.label}
                        </option>
                     ))}
                  </Select>
               </label>
               <label htmlFor="accountability-resource">
                  <span>Resource</span>
                  <Select
                     id="accountability-resource"
                     value={draftFilters.resource_type}
                     onChange={(event) => updateDraftFilter("resource_type", event.target.value)}
                  >
                     <option value="">All visible resources</option>
                     {page.filter_options.resources.map((option) => (
                        <option key={option.value} value={option.value}>
                           {option.label}
                        </option>
                     ))}
                  </Select>
               </label>
               <label htmlFor="accountability-actor">
                  <span>Actor</span>
                  <Input
                     id="accountability-actor"
                     value={draftFilters.actor}
                     onChange={(event) => updateDraftFilter("actor", event.target.value)}
                     placeholder="Username contains…"
                  />
               </label>
               <label htmlFor="accountability-created-after">
                  <span>Created after</span>
                  <Input
                     id="accountability-created-after"
                     type="datetime-local"
                     value={draftFilters.created_after}
                     onChange={(event) => updateDraftFilter("created_after", event.target.value)}
                  />
               </label>
               <label htmlFor="accountability-created-before">
                  <span>Created before</span>
                  <Input
                     id="accountability-created-before"
                     type="datetime-local"
                     value={draftFilters.created_before}
                     onChange={(event) => updateDraftFilter("created_before", event.target.value)}
                  />
               </label>
            </div>
            <div className="accountability-filter-actions">
               <Button type="submit" disabled={loading}>
                  Apply filters
               </Button>
               <Button type="button" variant="secondary" onClick={clearFilters} disabled={loading}>
                  Clear filters
               </Button>
               <Button
                  type="button"
                  variant="ghost"
                  onClick={refresh}
                  loading={isRefreshing}
                  loadingLabel="Refreshing…"
                  disabled={isBlockingLoad}
               >
                  Refresh
               </Button>
            </div>
         </form>

         <div className="accountability-status" aria-live="polite" aria-atomic="true">
            {isBlockingLoad
               ? "Loading accountability history."
               : isRefreshing
                 ? "Refreshing accountability history."
                 : errorMessage
                   ? errorMessage
                   : effectiveAccessDenied
                     ? "Accountability access is no longer available."
                     : `Showing ${rangeStart} to ${rangeEnd} of ${page.count} events.`}
         </div>

         {effectiveAccessDenied ? (
            <section className="accountability-state accountability-state--denied" role="status">
               <Icons name="lock" size={23} />
               <h3>Accountability access unavailable</h3>
               <p>
                  Your current authority no longer permits this accountability history. Refresh your workspace access
                  before trying again.
               </p>
               <Button variant="secondary" onClick={refresh}>
                  Retry access check
               </Button>
            </section>
         ) : errorMessage ? (
            <section className="accountability-state accountability-state--error" role="alert">
               <Icons name="alert-circle" size={23} />
               <h3>Accountability history could not be loaded</h3>
               <p>{errorMessage}</p>
               <Button variant="secondary" onClick={refresh}>
                  Retry
               </Button>
            </section>
         ) : isBlockingLoad ? (
            <section className="accountability-state" role="status">
               <Icons name="loader" size={23} className="accountability-spinner" />
               <h3>Loading accountability history</h3>
               <p>The latest authorized events are being retrieved.</p>
            </section>
         ) : page.results.length === 0 ? (
            <section className="accountability-state" role="status">
               <Icons name="activity" size={23} />
               <h3>No accountability events found</h3>
               <p>No authorized events match the current filters.</p>
            </section>
         ) : (
            <ul className="accountability-feed">
               {page.results.map((event) => (
                  <AccountabilityEvent key={event.id} event={event} />
               ))}
            </ul>
         )}

         {!effectiveAccessDenied && !errorMessage && !isBlockingLoad ? (
            <nav className="accountability-pagination" aria-label="Accountability history pages">
               <span>
                  {rangeStart}–{rangeEnd} of {page.count}
               </span>
               <div>
                  <Button
                     variant="secondary"
                     onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                     disabled={!hasPrevious || loading}
                  >
                     Previous
                  </Button>
                  <Button
                     variant="secondary"
                     onClick={() => setOffset((current) => current + PAGE_SIZE)}
                     disabled={!hasNext || loading}
                  >
                     Next
                  </Button>
               </div>
            </nav>
         ) : null}
      </div>
   );
}

export default AccountabilityPanel;
