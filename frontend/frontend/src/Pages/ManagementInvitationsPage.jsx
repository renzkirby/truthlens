import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ManagementPageHeader, ManagementPagination, ManagementRequestState, ManagementStatus } from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

function ManagementInvitationsPage() {
   const [draftQuery, setDraftQuery] = useState("");
   const [filters, setFilters] = useState({ q: "", status: "", purpose: "", invited_role: "" });
   const [page, setPage] = useState(1);
   const requestUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_INVITATIONS"));
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
         <ManagementPageHeader title="Invitations" subtitle="Inspect organization membership and Organization Admin onboarding invitations." />
         <section className="management-filter-panel" aria-label="Invitation filters">
            <form className="management-search" onSubmit={(event) => { event.preventDefault(); updateFilter("q", draftQuery.trim()); }}>
               <label htmlFor="invitation-search">Search invitations</label>
               <div>
                  <Input id="invitation-search" value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} placeholder="Organization, email, or inviter" leadingIcon={<Icons name="search" />} />
                  <Button type="submit" variant="secondary">Search</Button>
               </div>
            </form>
            <div className="management-filters">
               <label><span>Status</span><Select value={filters.status} onChange={(event) => updateFilter("status", event.target.value)}><option value="">All statuses</option><option value="PENDING">Pending</option><option value="ACCEPTED">Accepted</option><option value="CANCELLED">Cancelled</option><option value="EXPIRED">Expired</option></Select></label>
               <label><span>Purpose</span><Select value={filters.purpose} onChange={(event) => updateFilter("purpose", event.target.value)}><option value="">All purposes</option><option value="MEMBERSHIP">Membership</option><option value="ORGANIZATION_ADMIN_ONBOARDING">Organization Admin onboarding</option></Select></label>
               <label><span>Invited role</span><Select value={filters.invited_role} onChange={(event) => updateFilter("invited_role", event.target.value)}><option value="">All roles</option><option value="ADMIN">Administrator</option><option value="LEAD_VERIFIER">Lead Verifier</option><option value="VERIFICATION_REVIEWER">Verification Reviewer</option><option value="RESEARCHER">Researcher</option></Select></label>
               <Button variant="ghost" density="compact" onClick={() => { setDraftQuery(""); setFilters({ q: "", status: "", purpose: "", invited_role: "" }); setPage(1); }}>Clear filters</Button>
            </div>
         </section>

         <ManagementRequestState loading={loading} error={error} onRetry={retry} empty={data?.count === 0} emptyMessage="No invitations match the current search and filters.">
            <section className="management-table-wrap" aria-label="Organization invitations">
               <table className="management-table management-table--wide">
                  <thead><tr><th>Organization</th><th>Email</th><th>Invited role</th><th>Purpose</th><th>Status</th><th>Invited by</th><th>Expires</th><th>Created</th></tr></thead>
                  <tbody>
                     {data?.results?.map((invitation) => (
                        <tr key={invitation.id}>
                           <td data-label="Organization"><Link className="management-record-link" to={`/management/invitations/${invitation.id}`}><strong>{invitation.organization.name}</strong></Link></td>
                           <td data-label="Email">{invitation.email}</td>
                           <td data-label="Invited role">{invitation.invited_role_label}</td>
                           <td data-label="Purpose">{invitation.purpose_label}</td>
                           <td data-label="Status"><ManagementStatus value={invitation.status} /></td>
                           <td data-label="Invited by" className="management-table__username">{invitation.invited_by ? `@${invitation.invited_by.username}` : "System"}</td>
                           <td data-label="Expires">{formatManagementDate(invitation.expires_at)}</td>
                           <td data-label="Created">{formatManagementDate(invitation.created_at)}</td>
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

export default ManagementInvitationsPage;
