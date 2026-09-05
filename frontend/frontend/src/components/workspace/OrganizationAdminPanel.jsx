import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import Icons from "../Icons.jsx";

import { resolveApiEndpoint } from "../../utils/api";

import "./OrganizationAdminPanel.css";

function formatLabel(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value) {
   if (!value) {
      return "Not recorded";
   }

   const date = new Date(value);

   if (Number.isNaN(date.getTime())) {
      return "Not recorded";
   }

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
   }).format(date);
}

function getStatusIcon(status) {
   switch (status) {
      case "ACTIVE":
         return "user-check";

      case "PENDING":
         return "clock";

      case "SUSPENDED":
         return "alert-circle";

      default:
         return "user";
   }
}
const OWNER_INVITABLE_ROLES = [
   {
      value: "ADMIN",
      label: "Administrator",
   },
   {
      value: "LEAD_VERIFIER",
      label: "Lead Verifier",
   },
   {
      value: "MODERATOR",
      label: "Verifier / Moderator",
   },
   {
      value: "RESEARCHER",
      label: "Researcher",
   },
   {
      value: "CONTRIBUTOR",
      label: "Contributor",
   },
];

const ADMIN_INVITABLE_ROLES = OWNER_INVITABLE_ROLES.filter((role) => role.value !== "ADMIN");

function getInvitableRoles(membershipRole) {
   if (membershipRole === "OWNER") {
      return OWNER_INVITABLE_ROLES;
   }

   if (membershipRole === "ADMIN") {
      return ADMIN_INVITABLE_ROLES;
   }

   return [];
}

function InvitationAdminCard({ invitation, busy, onResend, onCancel }) {
   const isPending = invitation.status === "PENDING";
   const actionsDisabled = busy || invitation._optimistic === true;

   return (
      <article className="org-invitation-card">
         <div className="org-invitation-identity">
            <div className="org-invitation-icon">
               <Icons name="mail" size={17} />
            </div>

            <div>
               <strong>{invitation.email}</strong>

               <span>{formatLabel(invitation.invited_role)}</span>
            </div>
         </div>

         <div className="org-invitation-details">
            <div>
               <span>Status</span>

               <span className={`org-invitation-status ${String(invitation.status || "UNKNOWN").toLowerCase()}`}>
                  {formatLabel(invitation.status)}
               </span>
            </div>

            <div>
               <span>Sent</span>

               <strong>{formatDate(invitation.last_sent_at)}</strong>
            </div>

            <div>
               <span>Expires</span>

               <strong>{formatDate(invitation.expires_at)}</strong>
            </div>

            <div>
               <span>Deliveries</span>

               <strong>{invitation.send_count ?? 1}</strong>
            </div>
         </div>

         {isPending && (
            <div className="org-invitation-actions">
               <button type="button" onClick={() => onResend(invitation)} disabled={actionsDisabled}>
                  <Icons name="send" size={14} />
                  Resend
               </button>

               <button type="button" className="danger" onClick={() => onCancel(invitation)} disabled={actionsDisabled}>
                  <Icons name="x-circle" size={14} />
                  Cancel
               </button>
            </div>
         )}
      </article>
   );
}

function OrganizationAdminPanel({ organizationId, membershipRole }) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();

   const [requestVersion, setRequestVersion] = useState(0);

   const [roster, setRoster] = useState({
      organization: null,
      count: 0,
      summary: {
         active: 0,
         pending: 0,
         suspended: 0,
      },
      results: [],
   });
   const [invitations, setInvitations] = useState([]);
   const [invitationsLoading, setInvitationsLoading] = useState(true);
   const [invitationsError, setInvitationsError] = useState("");
   const [showInviteForm, setShowInviteForm] = useState(false);
   const [inviteForm, setInviteForm] = useState({
      email: "",
      invited_role: "",
   });
   const [inviteError, setInviteError] = useState("");
   const [isSendingInvite, setIsSendingInvite] = useState(false);
   const [invitationActionId, setInvitationActionId] = useState(null);
   const [cancelTarget, setCancelTarget] = useState(null);
   const [loading, setLoading] = useState(true);

   const [errorMessage, setErrorMessage] = useState("");

   const invitableRoles = useMemo(() => getInvitableRoles(membershipRole), [membershipRole]);
   const invitationsUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      return resolveApiEndpoint("ORGANIZATION_INVITATIONS", organizationId);
   }, [organizationId]);

   useEffect(() => {
      if (!invitationsUrl) {
         return undefined;
      }

      let cancelled = false;

      setInvitationsLoading(true);
      setInvitationsError("");

      authFetch(invitationsUrl, {
         method: "GET",
      })
         .then((data) => {
            if (cancelled) {
               return;
            }

            setInvitations(Array.isArray(data?.results) ? data.results : []);
         })
         .catch((error) => {
            if (cancelled) {
               return;
            }

            setInvitations([]);

            setInvitationsError(error?.message || "Unable to load organization invitations.");
         })
         .finally(() => {
            if (!cancelled) {
               setInvitationsLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, invitationsUrl, requestVersion]);

   useEffect(() => {
      if (!cancelTarget) {
         return undefined;
      }

      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !invitationActionId) {
            setCancelTarget(null);
         }
      };

      document.addEventListener("keydown", handleKeyDown);

      return () => {
         document.removeEventListener("keydown", handleKeyDown);
      };
   }, [cancelTarget, invitationActionId]);

   const membersUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      return resolveApiEndpoint("ORGANIZATION_MEMBERS", organizationId);
   }, [organizationId]);

   useEffect(() => {
      if (!membersUrl) {
         return undefined;
      }

      let cancelled = false;

      authFetch(membersUrl, {
         method: "GET",
      })
         .then((data) => {
            if (cancelled) {
               return;
            }

            setRoster({
               organization: data?.organization ?? null,
               count: Number(data?.count ?? 0),
               summary: {
                  active: Number(data?.summary?.active ?? 0),
                  pending: Number(data?.summary?.pending ?? 0),
                  suspended: Number(data?.summary?.suspended ?? 0),
               },
               results: Array.isArray(data?.results) ? data.results : [],
            });

            setErrorMessage("");
         })
         .catch((error) => {
            if (cancelled) {
               return;
            }

            setErrorMessage(error?.message || "Unable to load organization members.");

            setRoster({
               organization: null,
               count: 0,
               summary: {
                  active: 0,
                  pending: 0,
                  suspended: 0,
               },
               results: [],
            });
         })
         .finally(() => {
            if (!cancelled) {
               setLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, membersUrl, requestVersion]);

   const refresh = () => {
      setLoading(true);
      setErrorMessage("");

      setRequestVersion((current) => current + 1);
   };

   if (!organizationId) {
      return (
         <div className="org-admin-state">
            <Icons name="users" size={25} />

            <h3>No organization selected</h3>

            <p>Select an organization before viewing its member roster.</p>
         </div>
      );
   }

   if (loading) {
      return (
         <div className="org-admin-state" aria-live="polite">
            <Icons name="loader" size={21} className="org-admin-spinner" />

            <span>Loading organization members...</span>
         </div>
      );
   }

   if (errorMessage) {
      return (
         <div className="org-admin-error" role="alert">
            <Icons name="alert-circle" size={18} />

            <div>
               <strong>Member roster unavailable</strong>

               <span>{errorMessage}</span>

               <button type="button" onClick={refresh}>
                  <Icons name="refresh-cw" size={14} />
                  Try again
               </button>
            </div>
         </div>
      );
   }

   const handleInviteSubmit = async (event) => {
      event.preventDefault();

      if (isSendingInvite || !invitationsUrl) {
         return;
      }

      const email = inviteForm.email.trim().toLowerCase();

      if (!email || !inviteForm.invited_role) {
         setInviteError("Enter an email address and select a role.");

         return;
      }

      const optimisticId = `pending-invitation-${Date.now()}`;
      const now = new Date();
      const optimisticInvitation = {
         id: optimisticId,
         email,
         invited_role: inviteForm.invited_role,
         status: "PENDING",
         last_sent_at: now.toISOString(),
         expires_at: new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(),
         send_count: 1,
         _optimistic: true,
      };

      setIsSendingInvite(true);
      setInviteError("");
      setInvitationsError("");
      setInvitations((current) => [optimisticInvitation, ...current]);

      try {
         const createdInvitation = await authFetch(invitationsUrl, {
            method: "POST",
            headers: {
               "Content-Type": "application/json",
            },
            body: {
               email,
               invited_role: inviteForm.invited_role,
            },
         });

         setInvitations((current) =>
            current.map((invitation) =>
               invitation.id === optimisticId ? { ...createdInvitation, _optimistic: false } : invitation,
            ),
         );

         setInviteForm({
            email: "",
            invited_role: "",
         });
         setShowInviteForm(false);

         addToast({
            type: "success",
            title: "Invitation sent",
            message: `An invitation was sent to ${email}.`,
         });
      } catch (error) {
         console.error("Failed to send organization invitation:", error);

         setInvitations((current) => current.filter((invitation) => invitation.id !== optimisticId));

         addToast({
            type: "error",
            title: "Invitation not sent",
            message: error?.message || "Unable to send this invitation.",
         });
      } finally {
         setIsSendingInvite(false);
      }
   };

   const handleResendInvitation = async (invitation) => {
      if (!invitation?.id || invitationActionId || invitation._optimistic) {
         return;
      }

      const snapshot = invitation;
      const now = new Date();
      const optimisticInvitation = {
         ...invitation,
         last_sent_at: now.toISOString(),
         expires_at: new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(),
         send_count: Number(invitation.send_count ?? 1) + 1,
      };

      setInvitationActionId(invitation.id);
      setInvitations((current) => current.map((item) => (item.id === invitation.id ? optimisticInvitation : item)));

      try {
         const updatedInvitation = await authFetch(
            resolveApiEndpoint("ORGANIZATION_INVITATION_RESEND", organizationId, invitation.id),
            {
               method: "POST",
            },
         );

         if (updatedInvitation?.id) {
            setInvitations((current) => current.map((item) => (item.id === invitation.id ? updatedInvitation : item)));
         }

         addToast({
            type: "success",
            title: "Invitation resent",
            message: `A new invitation link was sent to ${invitation.email}.`,
         });
      } catch (error) {
         console.error("Failed to resend invitation:", error);

         setInvitations((current) => current.map((item) => (item.id === invitation.id ? snapshot : item)));

         addToast({
            type: "error",
            title: "Invitation not resent",
            message: error?.message || "Unable to resend this invitation.",
         });
      } finally {
         setInvitationActionId(null);
      }
   };

   const handleCancelInvitation = async () => {
      const invitation = cancelTarget;

      if (!invitation?.id || invitationActionId || invitation._optimistic) {
         return;
      }

      const snapshot = invitation;
      const optimisticInvitation = {
         ...invitation,
         status: "CANCELLED",
      };

      setCancelTarget(null);
      setInvitationActionId(invitation.id);
      setInvitations((current) => current.map((item) => (item.id === invitation.id ? optimisticInvitation : item)));

      try {
         const updatedInvitation = await authFetch(
            resolveApiEndpoint("ORGANIZATION_INVITATION_CANCEL", organizationId, invitation.id),
            {
               method: "POST",
            },
         );

         if (updatedInvitation?.id) {
            setInvitations((current) => current.map((item) => (item.id === invitation.id ? updatedInvitation : item)));
         }

         addToast({
            type: "success",
            title: "Invitation cancelled",
            message: `The invitation for ${invitation.email} is no longer active.`,
         });
      } catch (error) {
         console.error("Failed to cancel invitation:", error);

         setInvitations((current) => current.map((item) => (item.id === invitation.id ? snapshot : item)));

         addToast({
            type: "error",
            title: "Invitation not cancelled",
            message: error?.message || "Unable to cancel this invitation.",
         });
      } finally {
         setInvitationActionId(null);
      }
   };

   return (
      <div className="organization-admin-panel">
         <div className="org-admin-toolbar">
            <div>
               <strong>Organization members</strong>

               <span>Manage active memberships and invite new members.</span>
            </div>

            <div className="org-admin-toolbar-actions">
               <button
                  type="button"
                  className="org-admin-invite-button"
                  onClick={() => setShowInviteForm((current) => !current)}
               >
                  <Icons name="user-plus" size={15} />
                  Invite member
               </button>

               <button type="button" onClick={refresh}>
                  <Icons name="refresh-cw" size={15} />
                  Refresh
               </button>
            </div>
         </div>

         {showInviteForm && (
            <form className="org-invite-admin-form" onSubmit={handleInviteSubmit}>
               <div className="org-invite-admin-form-header">
                  <div>
                     <strong>Invite organization member</strong>

                     <span>TruthLens will email an invitation link to this address.</span>
                  </div>

                  <button
                     type="button"
                     className="org-invite-admin-close"
                     onClick={() => {
                        setShowInviteForm(false);
                        setInviteError("");
                     }}
                     aria-label="Close invitation form"
                  >
                     <Icons name="x" size={17} />
                  </button>
               </div>

               <div className="org-invite-admin-fields">
                  <div>
                     <label htmlFor="org-invite-email">Email address</label>

                     <input
                        id="org-invite-email"
                        type="email"
                        value={inviteForm.email}
                        onChange={(event) =>
                           setInviteForm((current) => ({
                              ...current,
                              email: event.target.value,
                           }))
                        }
                        placeholder="researcher@example.com"
                        autoComplete="email"
                        disabled={isSendingInvite}
                        required
                     />
                  </div>

                  <div>
                     <label htmlFor="org-invite-role">Organization role</label>

                     <select
                        id="org-invite-role"
                        value={inviteForm.invited_role}
                        onChange={(event) =>
                           setInviteForm((current) => ({
                              ...current,
                              invited_role: event.target.value,
                           }))
                        }
                        disabled={isSendingInvite}
                        required
                     >
                        <option value="">Select a role</option>

                        {invitableRoles.map((role) => (
                           <option key={role.value} value={role.value}>
                              {role.label}
                           </option>
                        ))}
                     </select>
                  </div>
               </div>

               <div className="org-invite-admin-notice">
                  <Icons name="info" size={16} />

                  <span>
                     Membership is activated only after the recipient signs in with the invited email address, verifies
                     that email, and explicitly accepts the invitation.
                  </span>
               </div>

               {inviteError && (
                  <div className="org-admin-error" role="alert">
                     <Icons name="alert-circle" size={17} />

                     <span>{inviteError}</span>
                  </div>
               )}

               <div className="org-invite-admin-form-actions">
                  <button type="button" onClick={() => setShowInviteForm(false)} disabled={isSendingInvite}>
                     Cancel
                  </button>

                  <button type="submit" className="primary" disabled={isSendingInvite}>
                     {isSendingInvite ? "Sending invitation…" : "Send invitation"}
                  </button>
               </div>
            </form>
         )}

         <div className="org-admin-summary" aria-label="Membership summary">
            <div>
               <span>Total</span>

               <strong>{roster.count}</strong>
            </div>

            <div>
               <span>Active</span>

               <strong>{roster.summary.active}</strong>
            </div>

            <div>
               <span>Pending</span>

               <strong>{roster.summary.pending}</strong>
            </div>

            <div>
               <span>Suspended</span>

               <strong>{roster.summary.suspended}</strong>
            </div>
         </div>

         {roster.results.length === 0 ? (
            <div className="org-admin-state">
               <Icons name="users" size={25} />

               <h3>No current members</h3>

               <p>Current organization memberships will appear here.</p>
            </div>
         ) : (
            <div className="org-member-list">
               {roster.results.map((membership) => {
                  const user = membership?.user ?? {};

                  return (
                     <article key={membership.id} className="org-member-card">
                        <div className="org-member-identity">
                           <div className="org-member-avatar">
                              <Icons name="user" size={18} />
                           </div>

                           <div>
                              <strong>@{user.username || "unknown"}</strong>

                              <span>{user.email || "No email available"}</span>
                           </div>
                        </div>

                        <div className="org-member-details">
                           <div>
                              <span>Role</span>

                              <strong>{formatLabel(membership.role)}</strong>
                           </div>

                           <div>
                              <span>Status</span>

                              <span
                                 className={`org-member-status ${String(membership.status || "UNKNOWN").toLowerCase()}`}
                              >
                                 <Icons name={getStatusIcon(membership.status)} size={13} />

                                 {formatLabel(membership.status)}
                              </span>
                           </div>

                           <div>
                              <span>Joined</span>

                              <strong>{formatDate(membership.joined_at)}</strong>
                           </div>

                           <div>
                              <span>Approved by</span>

                              <strong>
                                 {membership?.approved_by?.username
                                    ? `@${membership.approved_by.username}`
                                    : "Not recorded"}
                              </strong>
                           </div>
                        </div>
                     </article>
                  );
               })}
            </div>
         )}
         <section className="org-invitation-admin-section">
            <div className="org-invitation-admin-heading">
               <div>
                  <strong>Organization invitations</strong>

                  <span>Manage pending and historical invitations.</span>
               </div>
            </div>

            {invitationsLoading ? (
               <div className="org-admin-state">
                  <Icons name="loader" size={20} className="org-admin-spinner" />

                  <span>Loading invitations...</span>
               </div>
            ) : invitationsError ? (
               <div className="org-admin-error" role="alert">
                  <Icons name="alert-circle" size={18} />

                  <div>
                     <strong>Invitations unavailable</strong>

                     <span>{invitationsError}</span>

                     <button type="button" onClick={refresh}>
                        Try again
                     </button>
                  </div>
               </div>
            ) : invitations.length === 0 ? (
               <div className="org-admin-state">
                  <Icons name="mail" size={25} />

                  <h3>No invitations yet</h3>

                  <p>Invitations you send will appear here.</p>
               </div>
            ) : (
               <div className="org-invitation-list">
                  {invitations.map((invitation) => (
                     <InvitationAdminCard
                        key={invitation.id}
                        invitation={invitation}
                        busy={invitationActionId === invitation.id}
                        onResend={handleResendInvitation}
                        onCancel={setCancelTarget}
                     />
                  ))}
               </div>
            )}
         </section>
         {cancelTarget && (
            <div
               className="org-admin-modal-backdrop"
               onMouseDown={(event) => {
                  if (event.target === event.currentTarget && !invitationActionId) {
                     setCancelTarget(null);
                  }
               }}
            >
               <div
                  className="org-admin-confirm-modal"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="cancel-invitation-title"
                  aria-describedby="cancel-invitation-description"
               >
                  <div className="org-admin-confirm-icon" aria-hidden="true">
                     <Icons name="alert-triangle" size={20} />
                  </div>

                  <div className="org-admin-confirm-copy">
                     <h3 id="cancel-invitation-title">Cancel invitation?</h3>

                     <p id="cancel-invitation-description">
                        The invitation for <strong>{cancelTarget.email}</strong> will stop working immediately. They
                        will need a new invitation if access is still required later.
                     </p>
                  </div>

                  <div className="org-admin-confirm-actions">
                     <button type="button" onClick={() => setCancelTarget(null)} disabled={Boolean(invitationActionId)}>
                        Keep invitation
                     </button>

                     <button
                        type="button"
                        className="danger"
                        onClick={handleCancelInvitation}
                        disabled={Boolean(invitationActionId)}
                        autoFocus
                     >
                        <Icons name="x-circle" size={15} />
                        Cancel invitation
                     </button>
                  </div>
               </div>
            </div>
         )}
      </div>
   );
}

export default OrganizationAdminPanel;
