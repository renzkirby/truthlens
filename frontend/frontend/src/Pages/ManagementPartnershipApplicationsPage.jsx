import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import {
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

import "./ManagementPartnershipApplications.css";

function readPage(searchParams) {
   const value = Number.parseInt(searchParams.get("page") || "1", 10);
   return Number.isInteger(value) && value > 0 ? value : 1;
}

export default function ManagementPartnershipApplicationsPage() {
   const [searchParams, setSearchParams] = useSearchParams();
   const page = readPage(searchParams);
   const statusFilter = searchParams.get("status") || "";
   const queryFilter = searchParams.get("q") || "";
   const [draftQuery, setDraftQuery] = useState(queryFilter);

   const requestUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_PARTNERSHIP_APPLICATIONS"));
      if (statusFilter) url.searchParams.set("status", statusFilter);
      if (queryFilter) url.searchParams.set("q", queryFilter);
      url.searchParams.set("page", page);
      return url.toString();
   }, [page, queryFilter, statusFilter]);

   const { data, loading, error, retry } = useManagementRequest(requestUrl);

   const updateFilter = (name, value) => {
      const next = new URLSearchParams(searchParams);
      if (value) next.set(name, value);
      else next.delete(name);
      next.delete("page");
      setSearchParams(next);
   };

   const submitSearch = (event) => {
      event.preventDefault();
      updateFilter("q", draftQuery.trim());
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
            title="Partner Applications"
            subtitle="Review institutional partnership requests before any organization receives professional verification authority."
         />

         <aside className="management-boundary-note">
            <div>
               <strong>Application approval is the platform trust decision</strong>
               <p>
                  Approval authorizes secure Organization Admin onboarding. The organization remains Pending Verification
                  and Not a Partner until the approved representative accepts that invitation.
               </p>
            </div>
         </aside>

         <section className="management-filter-panel" aria-label="Partnership application filters">
            <form className="management-search" onSubmit={submitSearch}>
               <label htmlFor="partnership-application-search">Search applications</label>
               <div>
                  <Input
                     id="partnership-application-search"
                     value={draftQuery}
                     onChange={(event) => setDraftQuery(event.target.value)}
                     placeholder="Organization, applicant, or email"
                  />
                  <Button type="submit" variant="secondary">Search</Button>
               </div>
            </form>

            <div className="management-filters">
               <label>
                  <span>Status</span>
                  <Select
                     value={statusFilter}
                     onChange={(event) => updateFilter("status", event.target.value)}
                  >
                     <option value="">All applications</option>
                     <option value="SUBMITTED">Submitted</option>
                     <option value="UNDER_REVIEW">Under Review</option>
                     <option value="APPROVED">Approved for Onboarding</option>
                     <option value="REJECTED">Rejected</option>
                  </Select>
               </label>
               <Button
                  variant="ghost"
                  density="compact"
                  onClick={() => {
                     setDraftQuery("");
                     setSearchParams(new URLSearchParams());
                  }}
               >
                  Clear filters
               </Button>
            </div>
         </section>

         <ManagementRequestState
            loading={loading}
            error={error}
            onRetry={retry}
            empty={data?.count === 0}
            emptyMessage="No partnership applications match the current search and filters."
         >
            <section className="management-table-wrap" aria-label="Partner Applications">
               <table className="management-table">
                  <thead>
                     <tr>
                        <th>Organization</th>
                        <th>Applicant</th>
                        <th>Status</th>
                        <th>Organization state</th>
                        <th>Submitted</th>
                     </tr>
                  </thead>
                  <tbody>
                     {data?.results?.map((application) => (
                        <tr key={application.id}>
                           <td data-label="Organization">
                              <Link
                                 className="management-record-link"
                                 to={"/management/partnership-applications/" + application.id}
                              >
                                 <strong>{application.organization.name}</strong>
                                 <small>{application.organization.organization_type_label}</small>
                              </Link>
                           </td>
                           <td data-label="Applicant">
                              <strong>{application.applicant_full_name}</strong>
                              <small className="management-cell-subtext">{application.applicant_email}</small>
                           </td>
                           <td data-label="Status">
                              <ManagementStatus value={application.status} label={application.status_label} />
                           </td>
                           <td data-label="Organization state">
                              <div className="management-application-state">
                                 <ManagementStatus
                                    value={application.organization.verification_status}
                                    label={application.organization.verification_status_label}
                                 />
                                 <ManagementStatus
                                    value={application.organization.partner_status}
                                    label={application.organization.partner_status_label}
                                 />
                              </div>
                           </td>
                           <td data-label="Submitted">{formatManagementDate(application.created_at)}</td>
                        </tr>
                     ))}
                  </tbody>
               </table>
               <ManagementPagination
                  count={data?.count || 0}
                  page={page}
                  onPageChange={changePage}
               />
            </section>
         </ManagementRequestState>
      </div>
   );
}
