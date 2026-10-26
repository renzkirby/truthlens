import { useMemo, useRef, useState } from "react";

import {
   ManagementConfirmDialog,
   ManagementFeedback,
   ManagementFormDialog,
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";

import "./ManagementPlatformStaffPage.css";

function ManagementPlatformStaffPage() {
   const [page, setPage] = useState(1);
   const [addOpen, setAddOpen] = useState(false);
   const [candidateDraft, setCandidateDraft] = useState("");
   const [candidateQuery, setCandidateQuery] = useState("");
   const [selectedCandidate, setSelectedCandidate] = useState(null);
   const [revokeTarget, setRevokeTarget] = useState(null);
   const [feedback, setFeedback] = useState("");
   const addButtonRef = useRef(null);
   const revokeButtonRef = useRef(null);

   const staffUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF"));
      url.searchParams.set("page", page);
      return url.toString();
   }, [page]);
   const {
      data: staffData,
      loading: staffLoading,
      error: staffError,
      retry: refreshStaff,
   } = useManagementRequest(staffUrl);

   const candidateUrl = useMemo(() => {
      const url = new URL(resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF_CANDIDATES"));
      if (candidateQuery) url.searchParams.set("q", candidateQuery);
      return url.toString();
   }, [candidateQuery]);
   const {
      data: candidateData,
      loading: candidatesLoading,
      error: candidatesError,
      retry: refreshCandidates,
   } = useManagementRequest(candidateUrl);

   const {
      mutate: grantRole,
      pending: grantPending,
      error: grantError,
      reset: resetGrant,
   } = useManagementMutation();
   const {
      mutate: revokeRole,
      pending: revokePending,
      error: revokeError,
      reset: resetRevoke,
   } = useManagementMutation();

   const closeAdd = () => {
      if (grantPending) return;
      setAddOpen(false);
      setCandidateDraft("");
      setCandidateQuery("");
      setSelectedCandidate(null);
      resetGrant();
   };

   const openAdd = () => {
      setFeedback("");
      setCandidateDraft("");
      setCandidateQuery("");
      setSelectedCandidate(null);
      resetGrant();
      setAddOpen(true);
   };

   const searchCandidates = (event) => {
      event.preventDefault();
      const query = candidateDraft.trim();
      setSelectedCandidate(null);
      resetGrant();
      if (query.length < 2) return;
      setCandidateQuery(query);
   };

   const grantSelectedCandidate = async () => {
      if (!selectedCandidate || grantPending) return;
      const result = await grantRole(
         resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF"),
         {
            method: "POST",
            body: { user_id: selectedCandidate.id },
         },
      );
      if (!result.ok) return;

      const username = result.data?.username || selectedCandidate.username;
      setFeedback(`@${username} is now a Platform Safety Moderator.`);
      closeAdd();
      refreshStaff();
      refreshCandidates();
   };

   const beginRevoke = (member, event) => {
      revokeButtonRef.current = event.currentTarget;
      setFeedback("");
      resetRevoke();
      setRevokeTarget(member);
   };

   const revokeModerator = async () => {
      if (!revokeTarget || revokePending) return;
      const result = await revokeRole(
         resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF_DETAIL", revokeTarget.id),
         { method: "DELETE" },
      );
      if (!result.ok) return;

      setFeedback(`Platform Safety access was revoked for @${revokeTarget.username}.`);
      setRevokeTarget(null);
      refreshStaff();
      refreshCandidates();
   };

   return (
      <div className="management-page management-platform-staff-page">
         <ManagementPageHeader
            title="Platform Staff"
            subtitle="Manage platform-governance identities and Platform Safety access."
            actions={(
               <Button
                  ref={addButtonRef}
                  leadingIcon={<Icons name="user-plus" size={17} />}
                  onClick={openAdd}
               >
                  Add Safety Moderator
               </Button>
            )}
         />

         <section className="management-platform-staff-boundary">
            <span aria-hidden="true"><Icons name="shield-user" size={20} /></span>
            <div>
               <h2>Platform roles are separate from Community and partner roles</h2>
               <p>
                  Platform Safety Moderators can review Safety cases and Safety Audit history.
                  They do not become Platform Admins, gain Partner Organization authority, or
                  participate in Community reputation while the platform role is active.
               </p>
            </div>
         </section>

         {feedback ? <ManagementFeedback>{feedback}</ManagementFeedback> : null}

         <ManagementRequestState
            loading={staffLoading}
            error={staffError}
            onRetry={refreshStaff}
            empty={staffData?.count === 0}
            emptyMessage="No platform staff records are available."
         >
            <section className="management-table-wrap" aria-label="Platform staff">
               <table className="management-table">
                  <thead>
                     <tr>
                        <th>Account</th>
                        <th>Platform role</th>
                        <th>Console access</th>
                        <th>Status</th>
                        <th>Community identity</th>
                        <th>Actions</th>
                     </tr>
                  </thead>
                  <tbody>
                     {staffData?.results?.map((member) => (
                        <tr key={member.id}>
                           <td data-label="Account">
                              <span className="management-person">
                                 <strong>@{member.username}</strong>
                                 <small>{member.email || "No email recorded"}</small>
                              </span>
                           </td>
                           <td data-label="Platform role">
                              <strong>{member.platform_role_label}</strong>
                           </td>
                           <td data-label="Console access">{member.access_label}</td>
                           <td data-label="Status">
                              <ManagementStatus
                                 value={member.is_active ? "ACTIVE" : "INACTIVE"}
                                 label={member.is_active ? "Active" : "Inactive"}
                              />
                           </td>
                           <td data-label="Community identity">Not applicable</td>
                           <td data-label="Actions" className="management-platform-staff-actions">
                              {member.can_revoke ? (
                                 <Button
                                    variant="secondary"
                                    density="compact"
                                    onClick={(event) => beginRevoke(member, event)}
                                 >
                                    Revoke Safety access
                                 </Button>
                              ) : (
                                 <span className="management-platform-staff-fixed">Admin-managed</span>
                              )}
                           </td>
                        </tr>
                     ))}
                  </tbody>
               </table>
               <ManagementPagination
                  count={staffData?.count || 0}
                  page={page}
                  onPageChange={setPage}
               />
            </section>
         </ManagementRequestState>

         <ManagementFormDialog
            open={addOpen}
            title="Add Platform Safety Moderator"
            description="Find an existing active TruthLens account and grant Platform Safety access."
            processing={grantPending}
            returnFocusRef={addButtonRef}
            onClose={closeAdd}
         >
            <form className="management-platform-staff-search" onSubmit={searchCandidates}>
               <label htmlFor="platform-staff-candidate-search">
                  Search existing account
               </label>
               <div>
                  <Input
                     id="platform-staff-candidate-search"
                     value={candidateDraft}
                     onChange={(event) => setCandidateDraft(event.target.value)}
                     placeholder="Username or email"
                     leadingIcon={<Icons name="search" />}
                     disabled={grantPending}
                  />
                  <Button
                     type="submit"
                     variant="secondary"
                     disabled={candidateDraft.trim().length < 2 || grantPending}
                  >
                     Search
                  </Button>
               </div>
               <small>Enter at least two characters. Platform Admin accounts and existing Safety Moderators are excluded.</small>
            </form>

            {candidateQuery ? (
               <div className="management-platform-staff-candidates" aria-live="polite">
                  {candidatesLoading ? (
                     <p>Searching accounts…</p>
                  ) : candidatesError ? (
                     <ManagementFeedback tone="error">{candidatesError}</ManagementFeedback>
                  ) : candidateData?.results?.length ? (
                     candidateData.results.map((candidate) => (
                        <button
                           key={candidate.id}
                           type="button"
                           className={`management-platform-staff-candidate ${
                              selectedCandidate?.id === candidate.id ? "selected" : ""
                           }`}
                           aria-pressed={selectedCandidate?.id === candidate.id}
                           disabled={grantPending}
                           onClick={() => {
                              resetGrant();
                              setSelectedCandidate(candidate);
                           }}
                        >
                           <span>
                              <strong>@{candidate.username}</strong>
                              <small>{candidate.email || "No email recorded"}</small>
                           </span>
                           <span>{selectedCandidate?.id === candidate.id ? "Selected" : "Select"}</span>
                        </button>
                     ))
                  ) : (
                     <p>No eligible active accounts matched that search.</p>
                  )}
               </div>
            ) : null}

            {selectedCandidate ? (
               <div className="management-platform-staff-grant">
                  <div>
                     <strong>Grant Platform Safety access to @{selectedCandidate.username}?</strong>
                     <p>
                        Their Community participation and reputation persona will be unavailable
                        while this platform role is active. Existing historical records remain preserved.
                     </p>
                  </div>
                  <Button
                     loading={grantPending}
                     loadingLabel="Granting…"
                     onClick={grantSelectedCandidate}
                  >
                     Grant Safety access
                  </Button>
               </div>
            ) : null}

            {grantError ? <ManagementFeedback tone="error">{grantError.message}</ManagementFeedback> : null}
         </ManagementFormDialog>

         <ManagementConfirmDialog
            open={Boolean(revokeTarget)}
            title="Revoke Platform Safety access?"
            description={
               revokeTarget
                  ? `@${revokeTarget.username} will no longer be able to access Safety Review or Safety Audit through this platform role.`
                  : ""
            }
            warning="This changes only the Platform Safety role. Any legitimate Partner Organization membership remains unchanged."
            error={revokeError?.message}
            confirmLabel="Revoke Safety access"
            confirmVariant="destructive"
            processing={revokePending}
            returnFocusRef={revokeButtonRef}
            onConfirm={revokeModerator}
            onClose={() => {
               if (revokePending) return;
               setRevokeTarget(null);
               resetRevoke();
            }}
         />
      </div>
   );
}

export default ManagementPlatformStaffPage;
