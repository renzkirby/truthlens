import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

const INITIAL_FILTERS = {
   q: "",
   verification_status: "",
   partner_status: "",
   organization_type: "",
   public_profile_enabled: "",
};

function ManagementOrganizationsPage() {
   const [draftQuery, setDraftQuery] = useState("");
   const [filters, setFilters] = useState(INITIAL_FILTERS);
   const [page, setPage] = useState(1);
   const requestUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_ORGANIZATIONS"));
      Object.entries(filters).forEach(([key, value]) => {
         if (value) url.searchParams.set(key, value);
      });
      url.searchParams.set("page", page);
      return url.toString();
   }, [filters, page]);
   const { data, loading, error, retry } = useManagementRequest(requestUrl);

   const updateFilter = (name, value) => {
      setFilters((current) => ({ ...current, [name]: value }));
      setPage(1);
   };

   const submitSearch = (event) => {
      event.preventDefault();
      updateFilter("q", draftQuery.trim());
   };

   const clearFilters = () => {
      setDraftQuery("");
      setFilters(INITIAL_FILTERS);
      setPage(1);
   };

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Partner Organizations"
            subtitle="Inspect institutional identity and platform trust."
         />

         <section className="management-filter-panel" aria-label="Organization filters">
            <form className="management-search" onSubmit={submitSearch}>
               <label htmlFor="organization-search">Search organizations</label>
               <div>
                  <Input
                     id="organization-search"
                     value={draftQuery}
                     onChange={(event) => setDraftQuery(event.target.value)}
                     placeholder="Name or slug"
                     leadingIcon={<Icons name="search" />}
                  />
                  <Button type="submit" variant="secondary">Search</Button>
               </div>
            </form>
            <div className="management-filters">
               <label>
                  <span>Verification</span>
                  <Select value={filters.verification_status} onChange={(event) => updateFilter("verification_status", event.target.value)}>
                     <option value="">All statuses</option>
                     <option value="UNVERIFIED">Unverified</option>
                     <option value="PENDING">Pending Verification</option>
                     <option value="VERIFIED">Verified</option>
                     <option value="REJECTED">Rejected</option>
                  </Select>
               </label>
               <label>
                  <span>Partner status</span>
                  <Select value={filters.partner_status} onChange={(event) => updateFilter("partner_status", event.target.value)}>
                     <option value="">All statuses</option>
                     <option value="NONE">Not a Partner</option>
                     <option value="ACTIVE">Active</option>
                     <option value="SUSPENDED">Suspended</option>
                     <option value="FORMER">Former Partner</option>
                  </Select>
               </label>
               <label>
                  <span>Organization type</span>
                  <Select value={filters.organization_type} onChange={(event) => updateFilter("organization_type", event.target.value)}>
                     <option value="">All types</option>
                     <option value="FACT_CHECKING">Fact-Checking Organization</option>
                     <option value="NEWS">News Organization</option>
                     <option value="UNIVERSITY">University</option>
                     <option value="RESEARCH">Research Organization</option>
                     <option value="NGO">Non-Governmental Organization</option>
                     <option value="GOVERNMENT">Government Organization</option>
                     <option value="OTHER">Other</option>
                  </Select>
               </label>
               <label>
                  <span>Public profile</span>
                  <Select value={filters.public_profile_enabled} onChange={(event) => updateFilter("public_profile_enabled", event.target.value)}>
                     <option value="">Any state</option>
                     <option value="true">Enabled</option>
                     <option value="false">Disabled</option>
                  </Select>
               </label>
               <Button variant="ghost" density="compact" onClick={clearFilters}>Clear filters</Button>
            </div>
         </section>

         <ManagementRequestState
            loading={loading}
            error={error}
            onRetry={retry}
            empty={data?.count === 0}
            emptyMessage="No organizations match the current search and filters."
         >
            <section className="management-table-wrap" aria-label="Partner organizations">
               <table className="management-table">
                  <thead><tr><th>Organization</th><th>Type</th><th>Verification</th><th>Partner status</th><th>Public profile</th><th>Updated</th></tr></thead>
                  <tbody>
                     {data?.results?.map((organization) => (
                        <tr key={organization.id}>
                           <td data-label="Organization">
                              <Link to={`/management/organizations/${organization.id}`} className="management-record-link">
                                 <strong>{organization.name}</strong><small>{organization.slug}</small>
                              </Link>
                           </td>
                           <td data-label="Type">{organization.organization_type_label}</td>
                           <td data-label="Verification"><ManagementStatus value={organization.verification_status} label={organization.verification_status_label} /></td>
                           <td data-label="Partner status"><ManagementStatus value={organization.partner_status} label={organization.partner_status_label} /></td>
                           <td data-label="Public profile">{organization.public_profile_enabled ? "Enabled" : "Disabled"}</td>
                           <td data-label="Updated">{formatManagementDate(organization.updated_at)}</td>
                        </tr>
                     ))}
                  </tbody>
               </table>
               <ManagementPagination count={data?.count || 0} page={page} onPageChange={setPage} />
            </section>
         </ManagementRequestState>
      </div>
   );
}

export default ManagementOrganizationsPage;
