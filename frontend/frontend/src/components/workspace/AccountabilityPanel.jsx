import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import { userFacingErrorMessage } from "../../utils/userFacingError";
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

const PROFESSIONAL_FIELD_LABELS = {
   assigned_to_id: "Assigned reviewer",
   status: "Status",
   evidence_status: "Evidence decision",
   verdict: "Verdict",
   publication_status: "Publication status",
   verification_status: "Organization verification",
   partner_status: "Partnership status",
   role: "Role",
   public_profile_enabled: "Public profile",
   is_active: "Account status",
   version: "Version",
};

const PROFESSIONAL_VALUE_LABELS = {
   PENDING: "Pending",
   AVAILABLE: "Available",
   ACTIVE: "Active",
   COMPLETED: "Completed",
   CANCELLED: "Cancelled",
   SUSPENDED: "Suspended",
   LEFT: "Left organization",
   UNVERIFIED: "Unverified",
   VERIFIED: "Approved",
   REJECTED: "Rejected",
   FACT: "Fact",
   FAKE: "False",
   MISLEADING: "Misleading",
   SATIRE: "Satire",
   ADMIN: "Administrator",
   LEAD_VERIFIER: "Lead Verifier",
   VERIFICATION_REVIEWER: "Verification Reviewer",
   RESEARCHER: "Researcher",
   DRAFT: "Draft",
   SUBMITTED: "Submitted",
   PUBLISHED: "Published",
   RETURNED_FOR_REWORK: "Returned for rework",
};

const CAPABILITY_LABELS = {
   REVIEW_SAFETY: "Safety review",
   CLAIM_VERIFICATION_WORK: "Investigation work",
   REVIEW_EVIDENCE: "Evidence review",
   ADJUDICATE: "Adjudication",
   CREATE_FACT_CHECK_DRAFT: "Fact-check drafting",
   PUBLISH_FACT_CHECK: "Fact-check publishing",
   MANAGE_ORGANIZATION: "Partner Organization administration",
};

const EVENT_SUMMARIES = {
   SAFETY_CASE_CLAIMED: (actor) => `${actor} took responsibility for reviewing this Safety case.`,
   SAFETY_CASE_RELEASED: (actor) => `${actor} released this Safety case back to the review queue.`,
   SAFETY_CASE_ESCALATED: (actor) => `${actor} escalated this Safety case for further review.`,
   VERIFICATION_ASSIGNMENT_CLAIMED: (actor) => `${actor} took responsibility for this investigation.`,
   VERIFICATION_ASSIGNMENT_RELEASED: (actor) => `${actor} released this investigation back to the organization queue.`,
   VERIFICATION_ASSIGNMENT_COMPLETED: () => "The investigation assignment was completed.",
   EVIDENCE_VERIFIED: (actor) => `${actor} approved this evidence for use in the investigation.`,
   EVIDENCE_REJECTED: (actor) => `${actor} rejected this evidence for use in the investigation.`,
   EVIDENCE_REOPENED: (actor) => `${actor} reopened this evidence for another review.`,
   ADJUDICATION_STARTED: (actor) => `${actor} began the authoritative claim decision.`,
   VERDICT_ISSUED: (actor) => `${actor} recorded the first authoritative verdict for this investigation.`,
   VERDICT_REVISED: (actor) => `${actor} recorded a revised authoritative verdict.`,
   ARTICLE_DRAFT_CREATED: (actor) => `${actor} created a fact-check draft from completed investigation work.`,
   ARTICLE_SUBMITTED: (actor) => `${actor} submitted the fact-check draft for publication review.`,
   ARTICLE_PUBLISHED: (actor) => `${actor} published the fact check.`,
};

function professionalFieldLabel(key) {
   return PROFESSIONAL_FIELD_LABELS[key] || displayKey(key);
}

function professionalEnumLabel(value) {
   if (value === null || value === undefined || value === "") return "Not recorded";
   const text = String(value);
   return PROFESSIONAL_VALUE_LABELS[text] || displayKey(text);
}

function authorityLabelForEvent(event) {
   if (event.authority?.organization?.name) {
      return event.authority.organization.name;
   }
   if (event.authority?.scope === "PLATFORM") return "Platform Staff";
   if (event.authority?.scope === "SYSTEM") return "TruthLens system";
   if (event.authority?.scope === "ORGANIZATION") return "Partner Organization";
   return professionalEnumLabel(event.authority?.scope);
}

function capabilityLabel(value) {
   if (!value) return "Not applicable";
   return CAPABILITY_LABELS[value] || displayKey(value);
}

function isTechnicalStateKey(key) {
   if (key === "assigned_to_id") return false;
   return (
      key.endsWith("_id")
      || key.endsWith("_ids")
      || key.startsWith("expected_")
      || ["decision_id", "case_id", "revision_number", "edit_generation"].includes(key)
   );
}

function professionalValue(event, key, value) {
   if (key === "assigned_to_id") {
      if (value === null || value === undefined || value === "") return "Unassigned";
      if (
         event.actor?.id
         && String(value) === String(event.actor.id)
         && event.actor?.username
      ) {
         return `@${event.actor.username}`;
      }
      return "Assigned reviewer recorded";
   }
   if (value === null || value === undefined || value === "") return "Not recorded";
   if (typeof value === "boolean") return value ? "Yes" : "No";
   if (typeof value === "number") return String(value);
   if (typeof value === "string") return professionalEnumLabel(value);
   return "Recorded in technical details";
}

function buildProfessionalChanges(event) {
   return buildStateChanges(event.previous_state, event.new_state)
      .filter((change) => !isTechnicalStateKey(change.key))
      .filter((change) => {
         const simpleBefore = change.before === null || ["string", "number", "boolean", "undefined"].includes(typeof change.before);
         const simpleAfter = change.after === null || ["string", "number", "boolean", "undefined"].includes(typeof change.after);
         return simpleBefore && simpleAfter;
      })
      .map((change) => ({
         ...change,
         label: professionalFieldLabel(change.key),
         beforeLabel: professionalValue(event, change.key, change.before),
         afterLabel: professionalValue(event, change.key, change.after),
      }));
}

function professionalEventSummary(event, actorLabel) {
   const buildSummary = EVENT_SUMMARIES[event.action_type];
   return buildSummary ? buildSummary(actorLabel) : "";
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

function StateChanges({ event }) {
   const changes = buildProfessionalChanges(event);

   if (changes.length === 0) {
      return (
         <section className="accountability-expanded-section">
            <h4>What changed</h4>
            <p className="accountability-detail-note">
               No additional professional state change needs to be shown for this action.
               Internal identifiers and system state remain available in Technical record.
            </p>
         </section>
      );
   }

   return (
      <section className="accountability-expanded-section">
         <h4>What changed</h4>
         <div className="accountability-change-list" role="list">
            {changes.map((change) => (
               <div className="accountability-change-row" role="listitem" key={change.key}>
                  <div className="accountability-change-field">{change.label}</div>
                  <div className="accountability-change-value">
                     <span className="accountability-change-label">Before</span>
                     <span>{change.beforeLabel}</span>
                  </div>
                  <span className="accountability-change-arrow" aria-hidden="true">
                     <Icons name="arrow-right" size={18} />
                  </span>
                  <div className="accountability-change-value">
                     <span className="accountability-change-label">After</span>
                     <span>{change.afterLabel}</span>
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
   const authorityLabel = authorityLabelForEvent(event);
   const eventSummary = professionalEventSummary(event, actorLabel);

   return (
      <li>
         <article className={`accountability-event${expanded ? " accountability-event--expanded" : ""}`}>
            <header className="accountability-event-header">
               <div className="accountability-event-title">
                  <div className="accountability-badges">
                     <span>{event.domain_label || displayKey(event.domain)}</span>
                  </div>
                  <h3>{event.action_label || displayKey(event.action_type)}</h3>
                  {eventSummary ? <p className="accountability-event-summary">{eventSummary}</p> : null}
               </div>
               {validTimestamp ? (
                  <time dateTime={timestamp.toISOString()}>{formatDateTime(event.created_at)}</time>
               ) : (
                  <span>Time unavailable</span>
               )}
            </header>

            <dl className="accountability-event-meta">
               <div>
                  <dt>Performed by</dt>
                  <dd>
                     <span>{actorLabel}</span>
                     {event.actor?.historical ? <span className="accountability-historical">Historical identity</span> : null}
                  </dd>
               </div>
               <div>
                  <dt>Affected record</dt>
                  <dd>
                     <strong>{event.resource?.label || displayKey(event.resource?.type || "Record")}</strong>
                  </dd>
               </div>
               <div>
                  <dt>Authority</dt>
                  <dd>{authorityLabel}</dd>
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
                  {expanded ? "Hide record details" : "View record details"}
               </Button>
            </div>

            {expanded ? (
               <div className="accountability-expanded" id={detailId}>
                  <StateChanges event={event} />

                  {hasReasonOrNotes ? (
                     <section className="accountability-expanded-section">
                        <h4>Reason and notes</h4>
                        <dl className="accountability-reason-list">
                           {event.reason_code ? (
                              <div>
                                 <dt>Reason</dt>
                                 <dd>{displayKey(event.reason_code)}</dd>
                              </div>
                           ) : null}
                           {event.notes ? (
                              <div>
                                 <dt>Notes</dt>
                                 <dd>{event.notes}</dd>
                              </div>
                           ) : null}
                        </dl>
                     </section>
                  ) : null}

                  <details className="accountability-context-disclosure">
                     <summary>
                        <span>Technical record</span>
                        <span className="accountability-context-hint">For traceability and troubleshooting</span>
                     </summary>
                     <div className="accountability-context-content">
                        <dl className="accountability-record-details">
                           <div>
                              <dt>Event ID</dt>
                              <dd>{event.id || "Not recorded"}</dd>
                           </div>
                           <div>
                              <dt>Authority</dt>
                              <dd>{authorityLabel}</dd>
                           </div>
                           <div>
                              <dt>Capability</dt>
                              <dd>{capabilityLabel(event.authority?.capability)}</dd>
                           </div>
                           <div>
                              <dt>Resource type</dt>
                              <dd>{event.resource?.label || displayKey(event.resource?.type || "Not recorded")}</dd>
                           </div>
                           <div>
                              <dt>Resource ID</dt>
                              <dd>{resourceId || "Not recorded"}</dd>
                           </div>
                        </dl>
                        {hasContext ? (
                           <div className="accountability-technical-context">
                              <h5>Internal references</h5>
                              <StructuredValue value={event.context} />
                           </div>
                        ) : null}
                     </div>
                  </details>
               </div>
            ) : null}
         </article>
      </li>
   );
}

function ActionFilterMenu({ id, value, options, onChange }) {
   const rootRef = useRef(null);
   const [open, setOpen] = useState(false);
   const selected = options.find((option) => option.value === value);

   useEffect(() => {
      if (!open) {
         return undefined;
      }

      const closeIfOutside = (event) => {
         if (!rootRef.current?.contains(event.target)) {
            setOpen(false);
         }
      };
      const closeOnEscape = (event) => {
         if (event.key === "Escape") {
            setOpen(false);
            rootRef.current?.querySelector("button")?.focus();
         }
      };

      document.addEventListener("pointerdown", closeIfOutside);
      document.addEventListener("keydown", closeOnEscape);
      return () => {
         document.removeEventListener("pointerdown", closeIfOutside);
         document.removeEventListener("keydown", closeOnEscape);
      };
   }, [open]);

   const choose = (nextValue) => {
      onChange(nextValue);
      setOpen(false);
   };

   return (
      <div ref={rootRef} className="accountability-action-filter">
         <button
            id={id}
            type="button"
            className="accountability-action-filter-trigger"
            aria-label="Action filter"
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen((current) => !current)}
            onKeyDown={(event) => {
               if (event.key === "ArrowDown" && !open) {
                  event.preventDefault();
                  setOpen(true);
               }
            }}
         >
            <span>{selected?.label || "All visible actions"}</span>
            <Icons name="chevron-down" size={16} aria-hidden="true" />
         </button>

         {open ? (
            <div className="accountability-action-filter-menu" role="menu" aria-label="Filter by action">
               <button
                  type="button"
                  role="menuitemradio"
                  aria-checked={!value}
                  className={!value ? "is-selected" : ""}
                  onClick={() => choose("")}
               >
                  <span>All visible actions</span>
                  {!value ? <Icons name="check" size={15} aria-hidden="true" /> : null}
               </button>
               {options.map((option) => {
                  const active = option.value === value;
                  return (
                     <button
                        key={option.value}
                        type="button"
                        role="menuitemradio"
                        aria-checked={active}
                        className={active ? "is-selected" : ""}
                        onClick={() => choose(option.value)}
                     >
                        <span>{option.label}</span>
                        {active ? <Icons name="check" size={15} aria-hidden="true" /> : null}
                     </button>
                  );
               })}
            </div>
         ) : null}
      </div>
   );
}

function AccountabilityPanel({ scope, organizationId, organizationName }) {
   const { authFetch, token, user } = useAuth();
   const [draftFilters, setDraftFilters] = useState({ ...EMPTY_FILTERS });
   const [appliedFilters, setAppliedFilters] = useState({ ...EMPTY_FILTERS });
   const [filtersOpen, setFiltersOpen] = useState(false);
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
            setErrorMessage(userFacingErrorMessage(error, {
               fallback: "We couldn't load accountability history. Try again.",
               authMessage: "Your session has expired. Sign in again to load accountability history.",
               permissionMessage: "You don't have permission to view this accountability history.",
               serviceMessage: "Accountability history is temporarily unavailable. Try again shortly.",
            }));
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
   const appliedFilterCount = Object.values(appliedFilters).filter(Boolean).length;

   return (
      <div className="accountability-panel">
         <section className="accountability-boundary-note" aria-label="Accountability record scope">
            <Icons name="activity" size={18} />
            <div>
               <strong>Read-only accountability record</strong>
               <p>
                  Review attributable actions recorded for <strong>{scopeLabel}</strong>. This history supports
                  accountable review of authorized operations; it is not a general user-surveillance view.
               </p>
            </div>
         </section>

         <section className="accountability-history-controls">
            <div className="accountability-history-heading">
               <div>
                  <h3>Recorded actions</h3>
                  <p>See what changed, who performed the action, when it happened, and which record was affected.</p>
               </div>
               <Button
                  type="button"
                  variant="secondary"
                  leadingIcon={<Icons name="filter" size={16} aria-hidden="true" />}
                  onClick={() => setFiltersOpen((current) => !current)}
                  aria-expanded={filtersOpen}
                  aria-controls="accountability-filter-panel"
               >
                  {appliedFilterCount > 0 ? `Filters (${appliedFilterCount})` : "Filters"}
               </Button>
            </div>

            {filtersOpen ? (
               <form id="accountability-filter-panel" className="accountability-filters" onSubmit={applyFilters}>
                  <div className="accountability-filter-grid">
               <label htmlFor="accountability-domain">
                  <span>Activity area</span>
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
               <div className="accountability-filter-field">
                  <span>Action</span>
                  <ActionFilterMenu
                     id="accountability-action"
                     value={draftFilters.action_type}
                     options={visibleActions}
                     onChange={(value) => updateDraftFilter("action_type", value)}
                  />
               </div>
               <label htmlFor="accountability-resource">
                  <span>Record type</span>
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
                     placeholder="Search username…"
                  />
               </label>
               <label htmlFor="accountability-created-after">
                  <span>From</span>
                  <Input
                     id="accountability-created-after"
                     type="datetime-local"
                     value={draftFilters.created_after}
                     onChange={(event) => updateDraftFilter("created_after", event.target.value)}
                  />
               </label>
               <label htmlFor="accountability-created-before">
                  <span>To</span>
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
                  </div>
               </form>
            ) : null}

            <div className="accountability-results-toolbar">
               <div className="accountability-status" aria-live="polite" aria-atomic="true">
            {isBlockingLoad
               ? "Loading accountability history."
               : isRefreshing
                 ? "Refreshing accountability history."
                 : errorMessage
                   ? errorMessage
                   : effectiveAccessDenied
                     ? "Accountability access is no longer available."
                     : `Showing ${rangeStart} to ${rangeEnd} of ${page.count} recorded actions.`}
               </div>
               <Button
                  type="button"
                  variant="ghost"
                  leadingIcon={<Icons name="refresh" size={15} aria-hidden="true" />}
                  onClick={refresh}
                  loading={isRefreshing}
                  loadingLabel="Refreshing…"
                  disabled={isBlockingLoad}
               >
                  Refresh
               </Button>
            </div>
         </section>

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
               <h3>No recorded actions found</h3>
               <p>No recorded actions match the current filters.</p>
            </section>
         ) : (
            <ul className="accountability-feed">
               {page.results.map((event) => (
                  <AccountabilityEvent key={event.id} event={event} />
               ))}
            </ul>
         )}

         {!effectiveAccessDenied && !errorMessage && !isBlockingLoad && page.results.length > 0 ? (
            <nav className="accountability-pagination" aria-label="Accountability history pages">
               <Button
                  variant="secondary"
                  onClick={() => setOffset((current) => Math.max(0, current - PAGE_SIZE))}
                  disabled={!hasPrevious || loading}
               >
                  Previous
               </Button>
               <span>{rangeStart}–{rangeEnd} of {page.count}</span>
               <Button
                  variant="secondary"
                  onClick={() => setOffset((current) => current + PAGE_SIZE)}
                  disabled={!hasNext || loading}
               >
                  Next
               </Button>
            </nav>
         ) : null}
      </div>
   );
}

export default AccountabilityPanel;
