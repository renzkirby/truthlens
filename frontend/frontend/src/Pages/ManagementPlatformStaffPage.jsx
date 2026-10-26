import { useRef, useState } from "react";

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
import { formatManagementDate } from "../utils/management";

import "./ManagementPlatformStaffPage.css";

function ManagementPlatformStaffPage() {
   const [page, setPage] = useState(1);
   const [inviteOpen, setInviteOpen] = useState(false);
   const [inviteEmail, setInviteEmail] = useState("");
   const [revokeTarget, setRevokeTarget] = useState(null);
   const [cancelInvitationTarget, setCancelInvitationTarget] = useState(null);
   const [feedback, setFeedback] = useState("");

   const inviteButtonRef = useRef(null);
   const revokeButtonRef = useRef(null);
   const cancelInvitationButtonRef = useRef(null);

   const staffUrl = new URL(resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF"));
   staffUrl.searchParams.set("page", page);
   const {
      data: staffData,
      loading: staffLoading,
      error: staffError,
      retry: refreshStaff,
   } = useManagementRequest(staffUrl.toString());

   const {
      data: invitationData,
      loading: invitationLoading,
      error: invitationError,
      retry: refreshInvitations,
   } = useManagementRequest(resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF_INVITATIONS"));

   const {
      mutate: sendInvitation,
      pending: invitationPending,
      error: invitationMutationError,
      reset: resetInvitationMutation,
   } = useManagementMutation();

   const {
      mutate: manageInvitation,
      pending: invitationActionPending,
      error: invitationActionError,
      reset: resetInvitationAction,
   } = useManagementMutation();

   const {
      mutate: revokeRole,
      pending: revokePending,
      error: revokeError,
      reset: resetRevoke,
   } = useManagementMutation();

   const openInvite = () => {
      setFeedback("");
      setInviteEmail("");
      resetInvitationMutation();
      setInviteOpen(true);
   };

   const closeInvite = () => {
      if (invitationPending) return;
      setInviteOpen(false);
      setInviteEmail("");
      resetInvitationMutation();
   };

   const submitInvitation = async (event) => {
      event.preventDefault();
      const email = inviteEmail.trim();
      if (!email || invitationPending) return;

      const result = await sendInvitation(
         resolveApiEndpoint("MANAGEMENT_PLATFORM_STAFF_INVITATIONS"),
         { method: "POST", body: { email } },
      );
      if (!result.ok) return;

      setFeedback(`Platform Safety Moderator invitation sent to ${result.data.email}.`);
      setInviteOpen(false);
      setInviteEmail("");
      refreshInvitations();
   };

   const resendInvitation = async (invitation) => {
      if (invitationActionPending) return;
      resetInvitationAction();
      const result = await manageInvitation(
         resolveApiEndpoint(
            "MANAGEMENT_PLATFORM_STAFF_INVITATION_RESEND",
            invitation.id,
         ),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      setFeedback(`Invitation resent to ${invitation.email}.`);
      refreshInvitations();
   };

   const confirmCancelInvitation = (invitation, event) => {
      cancelInvitationButtonRef.current = event.currentTarget;
      setFeedback("");
      resetInvitationAction();
      setCancelInvitationTarget(invitation);
   };

   const cancelInvitation = async () => {
      if (!cancelInvitationTarget || invitationActionPending) return;
      const result = await manageInvitation(
         resolveApiEndpoint(
            "MANAGEMENT_PLATFORM_STAFF_INVITATION_CANCEL",
            cancelInvitationTarget.id,
         ),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      setFeedback(`Invitation to ${cancelInvitationTarget.email} was cancelled.`);
      setCancelInvitationTarget(null);
      refreshInvitations();
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
   };

   return (
      <div className="management-page management-platform-staff-page">
         <ManagementPageHeader
            title="Platform Staff"
            subtitle="Manage platform-governance identities and Platform Safety access."
            actions={(
               <Button
                  ref={inviteButtonRef}
                  leadingIcon={<Icons name="mail" size={17} />}
                  onClick={openInvite}
               >
                  Invite Safety Moderator
               </Button>
            )}
         />

         <section className="management-platform-staff-boundary">
            <span aria-hidden="true"><Icons name="shield-user" size={20} /></span>
            <div>
               <h2>Platform roles are separate from Community and partner roles</h2>
               <p>
                  Platform Safety Moderators can review Safety cases and Safety Audit history.
                  They do not become Platform Admins or gain Partner Organization authority.
                  While this platform role is active, the staff account does not participate
                  in Community reputation.
               </p>
            </div>
         </section>

         {feedback ? <ManagementFeedback>{feedback}</ManagementFeedback> : null}

         <section className="management-platform-staff-section">
            <div className="management-platform-staff-section__heading">
               <div>
                  <h2>Current Platform Staff</h2>
                  <p>Active platform-governance identities and their console access.</p>
               </div>
            </div>

            <ManagementRequestState
               loading={staffLoading}
               error={staffError}
               onRetry={refreshStaff}
               empty={staffData?.count === 0}
               emptyMessage="No platform staff records are available."
            >
               <section className="management-table-wrap" aria-label="Current Platform Staff">
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
         </section>

         <section className="management-platform-staff-section">
            <div className="management-platform-staff-section__heading">
               <div>
                  <h2>Platform Staff invitations</h2>
                  <p>
                     Invitations are email-bound, expire automatically, and grant Safety access
                     only after the recipient accepts with a verified matching account.
                  </p>
               </div>
               {invitationData?.summary?.pending ? (
                  <span className="management-platform-staff-pending">
                     {invitationData.summary.pending} pending
                  </span>
               ) : null}
            </div>

            {invitationActionError ? (
               <ManagementFeedback tone="error">
                  {invitationActionError.message}
               </ManagementFeedback>
            ) : null}

            <ManagementRequestState
               loading={invitationLoading}
               error={invitationError}
               onRetry={refreshInvitations}
               empty={invitationData?.count === 0}
               emptyMessage="No Platform Staff invitations have been issued yet."
            >
               <section className="management-table-wrap" aria-label="Platform Staff invitations">
                  <table className="management-table">
                     <thead>
                        <tr>
                           <th>Recipient</th>
                           <th>Role</th>
                           <th>Status</th>
                           <th>Last sent</th>
                           <th>Expires</th>
                           <th>Actions</th>
                        </tr>
                     </thead>
                     <tbody>
                        {invitationData?.results?.map((invitation) => (
                           <tr key={invitation.id}>
                              <td data-label="Recipient">
                                 <strong>{invitation.email}</strong>
                              </td>
                              <td data-label="Role">{invitation.platform_role_label}</td>
                              <td data-label="Status">
                                 <ManagementStatus value={invitation.status} />
                              </td>
                              <td data-label="Last sent">
                                 {formatManagementDate(invitation.last_sent_at)}
                                 {invitation.send_count > 1 ? (
                                    <small className="management-platform-staff-send-count">
                                       {invitation.send_count} sends
                                    </small>
                                 ) : null}
                              </td>
                              <td data-label="Expires">
                                 {formatManagementDate(invitation.expires_at)}
                              </td>
                              <td data-label="Actions" className="management-platform-staff-actions">
                                 {invitation.status === "PENDING" ? (
                                    <div className="management-platform-staff-inline-actions">
                                       <Button
                                          variant="secondary"
                                          density="compact"
                                          disabled={invitationActionPending}
                                          onClick={() => resendInvitation(invitation)}
                                       >
                                          Resend
                                       </Button>
                                       <Button
                                          variant="ghost"
                                          density="compact"
                                          disabled={invitationActionPending}
                                          onClick={(event) =>
                                             confirmCancelInvitation(invitation, event)
                                          }
                                       >
                                          Cancel
                                       </Button>
                                    </div>
                                 ) : (
                                    <span className="management-platform-staff-fixed">
                                       No action needed
                                    </span>
                                 )}
                              </td>
                           </tr>
                        ))}
                     </tbody>
                  </table>
               </section>
            </ManagementRequestState>
         </section>

         <ManagementFormDialog
            open={inviteOpen}
            title="Invite Platform Safety Moderator"
            description="Send a secure invitation to the email address that should receive Platform Safety access."
            processing={invitationPending}
            returnFocusRef={inviteButtonRef}
            onClose={closeInvite}
         >
            <form className="management-platform-staff-invite-form" onSubmit={submitInvitation}>
               <label htmlFor="platform-staff-invite-email">Email address</label>
               <Input
                  id="platform-staff-invite-email"
                  type="email"
                  value={inviteEmail}
                  onChange={(event) => {
                     resetInvitationMutation();
                     setInviteEmail(event.target.value);
                  }}
                  placeholder="moderator@example.com"
                  leadingIcon={<Icons name="mail" />}
                  disabled={invitationPending}
                  required
               />

               <div className="management-platform-staff-invite-note">
                  <Icons name="shield-check" size={18} aria-hidden="true" />
                  <p>
                     The recipient must sign in or create a TruthLens account with this email,
                     verify it, and accept the invitation. No Community or Partner Organization
                     authority is granted by sending the invitation.
                  </p>
               </div>

               {invitationMutationError ? (
                  <ManagementFeedback tone="error">
                     {invitationMutationError.message}
                  </ManagementFeedback>
               ) : null}

               <div className="management-inline-actions">
                  <Button
                     type="button"
                     variant="secondary"
                     disabled={invitationPending}
                     onClick={closeInvite}
                  >
                     Cancel
                  </Button>
                  <Button
                     type="submit"
                     loading={invitationPending}
                     loadingLabel="Sending…"
                     disabled={!inviteEmail.trim()}
                  >
                     Send invitation
                  </Button>
               </div>
            </form>
         </ManagementFormDialog>

         <ManagementConfirmDialog
            open={Boolean(cancelInvitationTarget)}
            title="Cancel Platform Staff invitation?"
            description={
               cancelInvitationTarget
                  ? `The invitation sent to ${cancelInvitationTarget.email} will no longer be usable.`
                  : ""
            }
            warning="Cancelling this invitation does not change any existing account or organization membership."
            error={invitationActionError?.message}
            confirmLabel="Cancel invitation"
            confirmVariant="destructive"
            processing={invitationActionPending}
            returnFocusRef={cancelInvitationButtonRef}
            onConfirm={cancelInvitation}
            onClose={() => {
               if (invitationActionPending) return;
               setCancelInvitationTarget(null);
               resetInvitationAction();
            }}
         />

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
