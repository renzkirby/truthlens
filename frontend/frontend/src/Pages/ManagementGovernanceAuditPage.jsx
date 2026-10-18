import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
} from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import {
   formatManagementCapability,
   formatManagementDate,
   formatManagementGovernanceAction,
   MANAGEMENT_GOVERNANCE_ACTIONS,
} from "../utils/management";

const PAGE_SIZE = 20;
const FILTER_KEYS = ["organization", "action_type", "actor", "created_after", "created_before"];

function readFilters(searchParams) {
   return Object.fromEntries(FILTER_KEYS.map((key) => [key, searchParams.get(key) || ""]));
}

function normalizedPage(searchParams) {
   const value = Number(searchParams.get("page") || 1);
   return Number.isInteger(value) && value > 0 ? value : 1;
}

function apiDate(value) {
   if (!value) return "";
   const date = new Date(value);
   return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

function ManagementGovernanceAuditPage() {
   const location = useLocation();
   const [searchParams, setSearchParams] = useSearchParams();
   const searchKey = searchParams.toString();
   const appliedFilters = useMemo(
      () => readFilters(new URLSearchParams(searchKey)),
      [searchKey],
   );
   const page = normalizedPage(searchParams);
   const [draftFilters, setDraftFilters] = useState(appliedFilters);

   useEffect(() => {
      setDraftFilters(appliedFilters);
   }, [appliedFilters]);

   const requestUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_GOVERNANCE_AUDIT"));
      FILTER_KEYS.forEach((key) => {
         const value = appliedFilters[key];
         if (!value) return;
         url.searchParams.set(
            key,
            key === "created_after" || key === "created_before" ? apiDate(value) : value,
         );
      });
      url.searchParams.set("limit", PAGE_SIZE);
      url.searchParams.set("offset", (page - 1) * PAGE_SIZE);
      return url.toString();
   }, [appliedFilters, page]);
   const { data, loading, error, retry } = useManagementRequest(requestUrl);

   const updateDraft = (key, value) => {
      setDraftFilters((current) => ({ ...current, [key]: value }));
   };

   const applyFilters = (event) => {
      event.preventDefault();
      const next = new URLSearchParams();
      FILTER_KEYS.forEach((key) => {
         const value = draftFilters[key].trim();
         if (value) next.set(key, value);
      });
      setSearchParams(next);
   };

   const clearFilters = () => {
      setSearchParams(new URLSearchParams());
   };

   const changePage = (nextPage) => {
      const next = new URLSearchParams(searchParams);
      if (nextPage > 1) next.set("page", String(nextPage));
      else next.delete("page");
      setSearchParams(next);
   };

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Governance Audit"
            subtitle="Inspect attributable platform actions affecting Partner Organization governance."
         />

         <aside className="management-boundary-note" aria-label="Governance audit boundary">
            <Icons name="shield-check" size={20} />
            <div>
               <strong>Read-only platform-governance history</strong>
               <p>
                  This record covers controlled Partner Organization governance actions. It is not a general view of user activity.
               </p>
            </div>
         </aside>

         <form className="management-filter-panel" aria-label="Governance audit filters" onSubmit={applyFilters}>
            <div className="management-audit-filters">
               <label>
                  <span>Organization</span>
                  <Input
                     value={draftFilters.organization}
                     onChange={(event) => updateDraft("organization", event.target.value)}
                     placeholder="Organization name"
                  />
               </label>
               <label>
                  <span>Action</span>
                  <Select
                     value={draftFilters.action_type}
                     onChange={(event) => updateDraft("action_type", event.target.value)}
                  >
                     <option value="">All governance actions</option>
                     {MANAGEMENT_GOVERNANCE_ACTIONS.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                     ))}
                  </Select>
               </label>
               <label>
                  <span>Actor</span>
                  <Input
                     value={draftFilters.actor}
                     onChange={(event) => updateDraft("actor", event.target.value)}
                     placeholder="Username"
                  />
               </label>
               <label>
                  <span>Created after</span>
                  <Input
                     type="datetime-local"
                     value={draftFilters.created_after}
                     onChange={(event) => updateDraft("created_after", event.target.value)}
                  />
               </label>
               <label>
                  <span>Created before</span>
                  <Input
                     type="datetime-local"
                     value={draftFilters.created_before}
                     onChange={(event) => updateDraft("created_before", event.target.value)}
                  />
               </label>
            </div>
            <div className="management-filter-actions">
               <Button type="button" variant="ghost" density="compact" onClick={clearFilters}>
                  Clear filters
               </Button>
               <Button type="submit" variant="secondary">Apply filters</Button>
            </div>
         </form>

         <ManagementRequestState
            loading={loading}
            error={error}
            onRetry={retry}
            empty={data?.count === 0}
            emptyMessage="No platform-governance events match the current filters."
         >
            <section className="management-table-wrap" aria-label="Governance audit events">
               <table className="management-table management-table--wide">
                  <thead>
                     <tr>
                        <th>Action</th>
                        <th>Organization</th>
                        <th>Actor</th>
                        <th>Occurred</th>
                        <th>Capability</th>
                        <th>Resource</th>
                        <th><span className="management-visually-hidden">Details</span></th>
                     </tr>
                  </thead>
                  <tbody>
                     {data?.results?.map((event) => (
                        <tr key={event.id}>
                           <td data-label="Action">
                              <strong>
                                 {formatManagementGovernanceAction(event.action_type, event.action_label)}
                              </strong>
                           </td>
                           <td data-label="Organization">{event.subject_organization?.name || "Organization unavailable"}</td>
                           <td data-label="Actor" className="management-table__username">
                              {event.actor?.username ? `@${event.actor.username}` : "System"}
                              {event.actor?.historical ? <small>Historical snapshot</small> : null}
                           </td>
                           <td data-label="Occurred">{formatManagementDate(event.created_at)}</td>
                           <td data-label="Capability">{formatManagementCapability(event.authority.capability)}</td>
                           <td data-label="Resource">{event.resource.label}</td>
                           <td data-label="Details">
                              <Link
                                 className="management-inline-link"
                                 to={`/management/audit/${event.id}`}
                                 state={{ from: `${location.pathname}${location.search}` }}
                              >
                                 View details
                              </Link>
                           </td>
                        </tr>
                     ))}
                  </tbody>
               </table>
               <ManagementPagination
                  count={data?.count || 0}
                  page={page}
                  pageSize={PAGE_SIZE}
                  onPageChange={changePage}
               />
            </section>
         </ManagementRequestState>
      </div>
   );
}

export default ManagementGovernanceAuditPage;
