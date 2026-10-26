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

function ManagementMembershipsPage() {
   const [draftQuery, setDraftQuery] = useState("");
   const [filters, setFilters] = useState({ q: "", role: "", status: "" });
   const [page, setPage] = useState(1);
   const requestUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_MEMBERSHIPS"));
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

   return (
      <div className="management-page">
         <ManagementPageHeader title="Memberships" subtitle="Inspect organization roles and membership status." />
         <section className="management-filter-panel" aria-label="Membership filters">
            <form className="management-search" onSubmit={(event) => { event.preventDefault(); updateFilter("q", draftQuery.trim()); }}>
               <label htmlFor="membership-search">Search memberships</label>
               <div>
                  <Input id="membership-search" value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} placeholder="Organization, username, or email" leadingIcon={<Icons name="search" />} />
                  <Button type="submit" variant="secondary">Search</Button>
               </div>
            </form>
            <div className="management-filters management-filters--compact">
               <label>
                  <span>Role</span>
                  <Select value={filters.role} onChange={(event) => updateFilter("role", event.target.value)}>
                     <option value="">All roles</option>
                     <option value="ADMIN">Administrator</option>
                     <option value="LEAD_VERIFIER">Lead Verifier</option>
                     <option value="VERIFICATION_REVIEWER">Verification Reviewer</option>
                     <option value="RESEARCHER">Researcher</option>
                  </Select>
               </label>
               <label>
                  <span>Status</span>
                  <Select value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}>
                     <option value="">All statuses</option>
                     <option value="PENDING">Pending</option>
                     <option value="ACTIVE">Active</option>
                     <option value="SUSPENDED">Suspended</option>
                     <option value="LEFT">Left Organization</option>
                  </Select>
               </label>
               <Button variant="ghost" density="compact" onClick={() => { setDraftQuery(""); setFilters({ q: "", role: "", status: "" }); setPage(1); }}>Clear filters</Button>
            </div>
         </section>

         <ManagementRequestState loading={loading} error={error} onRetry={retry} empty={data?.count === 0} emptyMessage="No memberships match the current search and filters.">
            <section className="management-table-wrap" aria-label="Organization memberships">
               <table className="management-table">
                  <thead><tr><th>Organization</th><th>Member</th><th>Role</th><th>Status</th><th>Joined</th><th>Approved</th></tr></thead>
                  <tbody>
                     {data?.results?.map((membership) => (
                        <tr key={membership.id}>
                           <td data-label="Organization"><Link className="management-record-link" to={`/management/memberships/${membership.id}`}><strong>{membership.organization.name}</strong></Link></td>
                           <td data-label="Member"><span className="management-person"><strong>@{membership.user.username}</strong><small>{membership.user.email}</small></span></td>
                           <td data-label="Role">{membership.role_label}</td>
                           <td data-label="Status"><ManagementStatus value={membership.status} /></td>
                           <td data-label="Joined">{formatManagementDate(membership.joined_at)}</td>
                           <td data-label="Approved">{formatManagementDate(membership.approved_at)}</td>
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

export default ManagementMembershipsPage;
