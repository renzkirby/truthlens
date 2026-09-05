import { useEffect, useMemo, useRef, useState } from "react";

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

const OWNER_MANAGEABLE_ROLES = [
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

const ADMIN_MANAGEABLE_ROLES = OWNER_MANAGEABLE_ROLES.filter((role) => role.value !== "ADMIN");

const OWNER_INVITABLE_ROLES = OWNER_MANAGEABLE_ROLES;
const ADMIN_INVITABLE_ROLES = ADMIN_MANAGEABLE_ROLES;

const SUMMARY_KEY_BY_STATUS = {
   ACTIVE: "active",
   PENDING: "pending",
   SUSPENDED: "suspended",
};

function getManageableRoles(membershipRole) {
   if (membershipRole === "OWNER") {
      return OWNER_MANAGEABLE_ROLES;
   }

   if (membershipRole === "ADMIN") {
      return ADMIN_MANAGEABLE_ROLES;
   }

   return [];
}

function getInvitableRoles(membershipRole) {
   if (membershipRole === "OWNER") {
      return OWNER_INVITABLE_ROLES;
   }

   if (membershipRole === "ADMIN") {
      return ADMIN_INVITABLE_ROLES;
   }

   return [];
}

function canManageMembership(actorRole, targetMembership) {
   if (!targetMembership || targetMembership.role === "OWNER") {
      return false;
   }

   if (actorRole === "OWNER") {
      return true;
   }

   if (actorRole === "ADMIN") {
      return ["LEAD_VERIFIER", "MODERATOR", "RESEARCHER", "CONTRIBUTOR"].includes(targetMembership.role);
   }

   return false;
}

function transitionSummary(summary, previousStatus, nextStatus) {
   if (previousStatus === nextStatus) {
      return summary;
   }

   const nextSummary = {
      ...summary,
   };

   const previousKey = SUMMARY_KEY_BY_STATUS[previousStatus];
   const nextKey = SUMMARY_KEY_BY_STATUS[nextStatus];

   if (previousKey) {
      nextSummary[previousKey] = Math.max(0, Number(nextSummary[previousKey] ?? 0) - 1);
   }

   if (nextKey) {
      nextSummary[nextKey] = Number(nextSummary[nextKey] ?? 0) + 1;
   }

   return nextSummary;
}

function getUsername(membership) {
   return membership?.user?.username || "member";
}

function getFocusableElements(container) {
   if (!container) {
      return [];
   }

   return Array.from(
      container.querySelectorAll(
         [
            "button:not([disabled])",
            "select:not([disabled])",
            "input:not([disabled])",
            "textarea:not([disabled])",
            "a[href]",
            '[tabindex]:not([tabindex="-1"])',
         ].join(","),
      ),
   ).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
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

               <button
                  type="button"
                  className="danger"
                  onClick={(event) => onCancel(invitation, event)}
                  disabled={actionsDisabled}
               >
                  <Icons name="x-circle" size={14} />
                  Cancel
               </button>
            </div>
         )}
      </article>
   );
}

function AdminConfirmDialog({
   dialogRef,
   titleId,
   descriptionId,
   title,
   children,
   confirmLabel,
   confirmIcon,
   confirmClassName = "",
   busy = false,
   onClose,
   onConfirm,
   tone = "warning",
}) {
   return (
      <div
         className="org-admin-modal-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !busy) {
               onClose();
            }
         }}
      >
         <div
            ref={dialogRef}
            className="org-admin-confirm-modal"
            role="dialog"
            tabIndex={-1}
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
         >
            <div className={`org-admin-confirm-icon ${tone}`} aria-hidden="true">
               <Icons name={tone === "danger" ? "alert-triangle" : "shield"} size={20} />
            </div>

            <div className="org-admin-confirm-copy">
               <h3 id={titleId}>{title}</h3>

               <div id={descriptionId}>{children}</div>
            </div>

            <div className="org-admin-confirm-actions">
               <button type="button" onClick={onClose} disabled={busy} data-autofocus="true">
                  Keep membership
               </button>

               <button type="button" className={confirmClassName} onClick={onConfirm} disabled={busy}>
                  {confirmIcon && <Icons name={confirmIcon} size={15} />}
                  {busy ? "Working…" : confirmLabel}
               </button>
            </div>
         </div>
      </div>
   );
}

function OrganizationAdminPanel({ organizationId, membershipRole }) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();

   const dialogRef = useRef(null);
   const dialogReturnFocusRef = useRef(null);
   const refreshButtonRef = useRef(null);
   const memberMenuRef = useRef(null);
   const memberManageButtonRefs = useRef(new Map());

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

   const [memberMenuId, setMemberMenuId] = useState(null);
   const [memberActionId, setMemberActionId] = useState(null);
   const [roleTarget, setRoleTarget] = useState(null);
   const [roleValue, setRoleValue] = useState("");
   const [suspendTarget, setSuspendTarget] = useState(null);
   const [restoreTarget, setRestoreTarget] = useState(null);
   const [removeTarget, setRemoveTarget] = useState(null);

   const [loading, setLoading] = useState(true);
   const [errorMessage, setErrorMessage] = useState("");

   const invitableRoles = useMemo(() => getInvitableRoles(membershipRole), [membershipRole]);

   const manageableRoles = useMemo(() => getManageableRoles(membershipRole), [membershipRole]);

   const invitationsUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      return resolveApiEndpoint("ORGANIZATION_INVITATIONS", organizationId);
   }, [organizationId]);

   const membersUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      return resolveApiEndpoint("ORGANIZATION_MEMBERS", organizationId);
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

   useEffect(() => {
      if (!memberMenuId) {
         return undefined;
      }

      const menu = memberMenuRef.current;

      const firstMenuItem = menu?.querySelector('[role="menuitem"]');

      if (firstMenuItem) {
         requestAnimationFrame(() => {
            firstMenuItem.focus();
         });
      }

      const closeMenu = () => {
         setMemberMenuId(null);
      };

      const handleDocumentKeyDown = (event) => {
         if (event.key !== "Escape") {
            return;
         }

         const trigger = memberManageButtonRefs.current.get(memberMenuId);

         setMemberMenuId(null);

         requestAnimationFrame(() => {
            if (trigger && document.contains(trigger)) {
               trigger.focus();
            }
         });
      };

      document.addEventListener("click", closeMenu);
      document.addEventListener("keydown", handleDocumentKeyDown);

      return () => {
         document.removeEventListener("click", closeMenu);
         document.removeEventListener("keydown", handleDocumentKeyDown);
      };
   }, [memberMenuId]);

   const dialogOpen = Boolean(cancelTarget || roleTarget || suspendTarget || restoreTarget || removeTarget);

   useEffect(() => {
      if (!dialogOpen) {
         return undefined;
      }

      const returnTarget = dialogReturnFocusRef.current || document.activeElement;

      const refreshButton = refreshButtonRef.current;

      const previousBodyOverflow = document.body.style.overflow;

      document.body.style.overflow = "hidden";

      const focusInitialControl = () => {
         const dialog = dialogRef.current;

         if (!dialog) {
            return;
         }

         const preferred = dialog.querySelector('[data-autofocus="true"]');
         const focusable = getFocusableElements(dialog);

         (preferred || focusable[0] || dialog).focus();
      };

      requestAnimationFrame(focusInitialControl);

      const handleDialogKeyDown = (event) => {
         if (event.key === "Escape") {
            if (invitationActionId || memberActionId) {
               return;
            }

            event.preventDefault();

            setCancelTarget(null);
            setRoleTarget(null);
            setRoleValue("");
            setSuspendTarget(null);
            setRestoreTarget(null);
            setRemoveTarget(null);

            return;
         }

         if (event.key !== "Tab") {
            return;
         }

         const dialog = dialogRef.current;
         const focusable = getFocusableElements(dialog);

         if (focusable.length === 0) {
            event.preventDefault();
            dialog?.focus();
            return;
         }

         const first = focusable[0];
         const last = focusable[focusable.length - 1];
         const active = document.activeElement;

         if (event.shiftKey && active === first) {
            event.preventDefault();
            last.focus();
         } else if (!event.shiftKey && active === last) {
            event.preventDefault();
            first.focus();
         }
      };

      document.addEventListener("keydown", handleDialogKeyDown);

      return () => {
         document.removeEventListener("keydown", handleDialogKeyDown);
         document.body.style.overflow = previousBodyOverflow;

         requestAnimationFrame(() => {
            if (returnTarget && document.contains(returnTarget)) {
               returnTarget.focus();
               return;
            }

            if (refreshButton && document.contains(refreshButton)) {
               refreshButton.focus();
            }
         });
      };
   }, [dialogOpen, invitationActionId, memberActionId]);

   const refresh = () => {
      setLoading(true);
      setInvitationsLoading(true);
      setErrorMessage("");
      setInvitationsError("");
      setMemberMenuId(null);

      setRequestVersion((current) => current + 1);
   };

   const replaceRosterMembership = (updatedMembership) => {
      if (!updatedMembership?.id) {
         return;
      }

      setRoster((current) => {
         const index = current.results.findIndex((membership) => membership.id === updatedMembership.id);

         if (index < 0) {
            return current;
         }

         const previousMembership = current.results[index];
         const results = [...current.results];

         results[index] = updatedMembership;

         return {
            ...current,
            summary: transitionSummary(current.summary, previousMembership.status, updatedMembership.status),
            results,
         };
      });
   };

   const removeRosterMembership = (membershipId) => {
      setRoster((current) => {
         const membership = current.results.find((item) => item.id === membershipId);

         if (!membership) {
            return current;
         }

         return {
            ...current,
            count: Math.max(0, Number(current.count ?? 0) - 1),
            summary: transitionSummary(current.summary, membership.status, null),
            results: current.results.filter((item) => item.id !== membershipId),
         };
      });
   };

   const restoreRosterMembership = (membership, originalIndex) => {
      if (!membership?.id) {
         return;
      }

      setRoster((current) => {
         if (current.results.some((item) => item.id === membership.id)) {
            return current;
         }

         const results = [...current.results];
         const safeIndex = Math.max(0, Math.min(Number(originalIndex ?? results.length), results.length));

         results.splice(safeIndex, 0, membership);

         return {
            ...current,
            count: Number(current.count ?? 0) + 1,
            summary: transitionSummary(current.summary, null, membership.status),
            results,
         };
      });
   };

   const rememberMemberDialogTrigger = (membershipId) => {
      dialogReturnFocusRef.current = memberManageButtonRefs.current.get(membershipId) || null;
   };

   const openRoleDialog = (membership) => {
      rememberMemberDialogTrigger(membership.id);
      setMemberMenuId(null);
      setRoleValue("");
      setRoleTarget(membership);
   };

   const openSuspendDialog = (membership) => {
      rememberMemberDialogTrigger(membership.id);
      setMemberMenuId(null);
      setSuspendTarget(membership);
   };

   const openRestoreDialog = (membership) => {
      rememberMemberDialogTrigger(membership.id);
      setMemberMenuId(null);
      setRestoreTarget(membership);
   };

   const openRemoveDialog = (membership) => {
      rememberMemberDialogTrigger(membership.id);
      setMemberMenuId(null);
      setRemoveTarget(membership);
   };

   const openInvitationCancelDialog = (invitation, event) => {
      dialogReturnFocusRef.current = event?.currentTarget || null;
      setCancelTarget(invitation);
   };

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
               invitation.id === optimisticId
                  ? {
                       ...createdInvitation,
                       _optimistic: false,
                    }
                  : invitation,
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

   const handleRoleChange = async () => {
      const membership = roleTarget;

      if (!membership?.id || !roleValue || memberActionId) {
         return;
      }

      const snapshot = membership;
      const requestedRole = roleValue;

      setRoleTarget(null);
      setRoleValue("");
      setMemberActionId(membership.id);

      replaceRosterMembership({
         ...membership,
         role: requestedRole,
      });

      try {
         const updatedMembership = await authFetch(
            resolveApiEndpoint("ORGANIZATION_MEMBER_ROLE", organizationId, membership.id),
            {
               method: "PATCH",
               headers: {
                  "Content-Type": "application/json",
               },
               body: {
                  role: requestedRole,
               },
            },
         );

         replaceRosterMembership(updatedMembership);

         addToast({
            type: "success",
            title: "Role updated",
            message: `@${getUsername(membership)} is now ${formatLabel(updatedMembership.role)}.`,
         });
      } catch (error) {
         replaceRosterMembership(snapshot);

         addToast({
            type: "error",
            title: "Role not updated",
            message: error?.message || "Unable to change this organization role.",
         });
      } finally {
         setMemberActionId(null);
      }
   };

   const handleSuspendMembership = async () => {
      const membership = suspendTarget;

      if (!membership?.id || memberActionId) {
         return;
      }

      const snapshot = membership;

      setSuspendTarget(null);
      setMemberActionId(membership.id);

      replaceRosterMembership({
         ...membership,
         status: "SUSPENDED",
      });

      try {
         const updatedMembership = await authFetch(
            resolveApiEndpoint("ORGANIZATION_MEMBER_SUSPEND", organizationId, membership.id),
            {
               method: "POST",
            },
         );

         replaceRosterMembership(updatedMembership);

         addToast({
            type: "success",
            title: "Membership suspended",
            message: `@${getUsername(membership)} no longer has active organization authority.`,
         });
      } catch (error) {
         replaceRosterMembership(snapshot);

         addToast({
            type: "error",
            title: "Membership not suspended",
            message: error?.message || "Unable to suspend this membership.",
         });
      } finally {
         setMemberActionId(null);
      }
   };

   const handleRestoreMembership = async () => {
      const membership = restoreTarget;

      if (!membership?.id || memberActionId) {
         return;
      }

      const snapshot = membership;

      setRestoreTarget(null);
      setMemberActionId(membership.id);

      replaceRosterMembership({
         ...membership,
         status: "ACTIVE",
      });

      try {
         const updatedMembership = await authFetch(
            resolveApiEndpoint("ORGANIZATION_MEMBER_RESTORE", organizationId, membership.id),
            {
               method: "POST",
            },
         );

         replaceRosterMembership(updatedMembership);

         addToast({
            type: "success",
            title: "Membership restored",
            message: `@${getUsername(membership)} has active organization access again.`,
         });
      } catch (error) {
         replaceRosterMembership(snapshot);

         addToast({
            type: "error",
            title: "Membership not restored",
            message: error?.message || "Unable to restore this membership.",
         });
      } finally {
         setMemberActionId(null);
      }
   };

   const handleRemoveMembership = async () => {
      const membership = removeTarget;

      if (!membership?.id || memberActionId) {
         return;
      }

      const snapshot = membership;
      const originalIndex = roster.results.findIndex((item) => item.id === membership.id);

      setRemoveTarget(null);
      setMemberActionId(membership.id);
      removeRosterMembership(membership.id);

      try {
         await authFetch(resolveApiEndpoint("ORGANIZATION_MEMBER_REMOVE", organizationId, membership.id), {
            method: "POST",
         });

         addToast({
            type: "success",
            title: "Member removed",
            message: `@${getUsername(membership)} was removed from the organization.`,
         });
      } catch (error) {
         restoreRosterMembership(snapshot, originalIndex);

         addToast({
            type: "error",
            title: "Member not removed",
            message: error?.message || "Unable to remove this membership.",
         });
      } finally {
         setMemberActionId(null);
      }
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

   const organizationName = roster?.organization?.name || "this organization";

   return (
      <div className="organization-admin-panel">
         <div className="org-admin-toolbar">
            <div>
               <strong>Organization members</strong>

               <span>Manage institutional memberships and invite new members.</span>
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

               <button ref={refreshButtonRef} type="button" onClick={refresh}>
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
                  const manageable = canManageMembership(membershipRole, membership);
                  const busy = memberActionId === membership.id;
                  const menuOpen = memberMenuId === membership.id;

                  return (
                     <article
                        key={membership.id}
                        className={`org-member-card ${busy ? "is-busy" : ""}`}
                        aria-busy={busy ? "true" : undefined}
                     >
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

                        <div className="org-member-actions">
                           {manageable ? (
                              <>
                                 <button
                                    ref={(node) => {
                                       if (node) {
                                          memberManageButtonRefs.current.set(membership.id, node);
                                       } else {
                                          memberManageButtonRefs.current.delete(membership.id);
                                       }
                                    }}
                                    type="button"
                                    className="org-member-manage-button"
                                    aria-haspopup="menu"
                                    aria-expanded={menuOpen}
                                    aria-controls={menuOpen ? `member-menu-${membership.id}` : undefined}
                                    disabled={Boolean(memberActionId)}
                                    onClick={(event) => {
                                       event.stopPropagation();
                                       setMemberMenuId((current) => (current === membership.id ? null : membership.id));
                                    }}
                                    onKeyDown={(event) => {
                                       if (event.key === "ArrowDown") {
                                          event.preventDefault();
                                          event.stopPropagation();
                                          setMemberMenuId(membership.id);
                                       }
                                    }}
                                 >
                                    {busy ? (
                                       <Icons name="loader" size={14} className="org-admin-spinner" />
                                    ) : (
                                       <Icons name="settings" size={14} />
                                    )}
                                    Manage
                                    <Icons name="chevron-down" size={13} />
                                 </button>

                                 {menuOpen && !busy && (
                                    <div
                                       ref={memberMenuRef}
                                       id={`member-menu-${membership.id}`}
                                       className="org-member-menu"
                                       role="menu"
                                       aria-label={`Manage @${user.username || "member"}`}
                                       onClick={(event) => event.stopPropagation()}
                                       onBlur={(event) => {
                                          if (!event.currentTarget.contains(event.relatedTarget)) {
                                             setMemberMenuId(null);
                                          }
                                       }}
                                       onKeyDown={(event) => {
                                          if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
                                             return;
                                          }

                                          event.preventDefault();

                                          const items = Array.from(
                                             event.currentTarget.querySelectorAll('[role="menuitem"]:not([disabled])'),
                                          );

                                          if (items.length === 0) {
                                             return;
                                          }

                                          const currentIndex = items.indexOf(document.activeElement);
                                          let nextIndex = currentIndex;

                                          if (event.key === "Home") {
                                             nextIndex = 0;
                                          } else if (event.key === "End") {
                                             nextIndex = items.length - 1;
                                          } else if (event.key === "ArrowDown") {
                                             nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % items.length;
                                          } else if (event.key === "ArrowUp") {
                                             nextIndex =
                                                currentIndex < 0
                                                   ? items.length - 1
                                                   : (currentIndex - 1 + items.length) % items.length;
                                          }

                                          items[nextIndex].focus();
                                       }}
                                    >
                                       <button type="button" role="menuitem" onClick={() => openRoleDialog(membership)}>
                                          <Icons name="pencil" size={14} />
                                          Change role
                                       </button>

                                       {membership.status === "ACTIVE" && (
                                          <button
                                             type="button"
                                             role="menuitem"
                                             onClick={() => openSuspendDialog(membership)}
                                          >
                                             <Icons name="user-minus" size={14} />
                                             Suspend membership
                                          </button>
                                       )}

                                       {membership.status === "SUSPENDED" && (
                                          <button
                                             type="button"
                                             role="menuitem"
                                             onClick={() => openRestoreDialog(membership)}
                                          >
                                             <Icons name="user-check" size={14} />
                                             Restore membership
                                          </button>
                                       )}

                                       {membership.status !== "LEFT" && (
                                          <button
                                             type="button"
                                             role="menuitem"
                                             className="danger"
                                             onClick={() => openRemoveDialog(membership)}
                                          >
                                             <Icons name="trash" size={14} />
                                             Remove from organization
                                          </button>
                                       )}
                                    </div>
                                 )}
                              </>
                           ) : (
                              <span className="org-member-protected-label">
                                 {membership.role === "OWNER" ? "Ownership protected" : "Managed by owner"}
                              </span>
                           )}
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
                        onCancel={openInvitationCancelDialog}
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
                  ref={dialogRef}
                  className="org-admin-confirm-modal"
                  role="dialog"
                  tabIndex={-1}
                  aria-modal="true"
                  aria-labelledby="cancel-invitation-title"
                  aria-describedby="cancel-invitation-description"
               >
                  <div className="org-admin-confirm-icon danger" aria-hidden="true">
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
                     <button
                        type="button"
                        onClick={() => setCancelTarget(null)}
                        disabled={Boolean(invitationActionId)}
                        data-autofocus="true"
                     >
                        Keep invitation
                     </button>

                     <button
                        type="button"
                        className="danger"
                        onClick={handleCancelInvitation}
                        disabled={Boolean(invitationActionId)}
                     >
                        <Icons name="x-circle" size={15} />
                        {invitationActionId ? "Cancelling…" : "Cancel invitation"}
                     </button>
                  </div>
               </div>
            </div>
         )}

         {roleTarget && (
            <div
               className="org-admin-modal-backdrop"
               onMouseDown={(event) => {
                  if (event.target === event.currentTarget && !memberActionId) {
                     setRoleTarget(null);
                     setRoleValue("");
                  }
               }}
            >
               <div
                  ref={dialogRef}
                  className="org-admin-confirm-modal org-admin-role-modal"
                  role="dialog"
                  tabIndex={-1}
                  aria-modal="true"
                  aria-labelledby="change-member-role-title"
                  aria-describedby="change-member-role-description"
               >
                  <div className="org-admin-confirm-icon neutral" aria-hidden="true">
                     <Icons name="pencil" size={20} />
                  </div>

                  <div className="org-admin-confirm-copy">
                     <h3 id="change-member-role-title">Change organization role</h3>

                     <p id="change-member-role-description">
                        Change <strong>@{getUsername(roleTarget)}</strong> from{" "}
                        <strong>{formatLabel(roleTarget.role)}</strong>. Role changes take effect immediately and may
                        grant or revoke organization-scoped verification capabilities.
                     </p>
                  </div>

                  <div className="org-admin-role-field">
                     <label htmlFor="org-member-role-select">New role</label>

                     <select
                        id="org-member-role-select"
                        value={roleValue}
                        onChange={(event) => setRoleValue(event.target.value)}
                        disabled={Boolean(memberActionId)}
                        data-autofocus="true"
                     >
                        <option value="">Select a new role</option>

                        {manageableRoles
                           .filter((role) => role.value !== roleTarget.role)
                           .map((role) => (
                              <option key={role.value} value={role.value}>
                                 {role.label}
                              </option>
                           ))}
                     </select>
                  </div>

                  <div className="org-admin-authority-note">
                     <Icons name="shield" size={16} />
                     <span>
                        This changes institutional authority only. It does not alter the person's TruthLens account,
                        password, profile, or trust score.
                     </span>
                  </div>

                  <div className="org-admin-confirm-actions">
                     <button
                        type="button"
                        onClick={() => {
                           setRoleTarget(null);
                           setRoleValue("");
                        }}
                        disabled={Boolean(memberActionId)}
                     >
                        Cancel
                     </button>

                     <button
                        type="button"
                        className="primary"
                        onClick={handleRoleChange}
                        disabled={!roleValue || Boolean(memberActionId)}
                     >
                        <Icons name="check" size={15} />
                        Update role
                     </button>
                  </div>
               </div>
            </div>
         )}

         {suspendTarget && (
            <AdminConfirmDialog
               dialogRef={dialogRef}
               titleId="suspend-membership-title"
               descriptionId="suspend-membership-description"
               title="Suspend membership?"
               confirmLabel="Suspend membership"
               confirmIcon="user-minus"
               confirmClassName="danger"
               busy={memberActionId === suspendTarget.id}
               onClose={() => setSuspendTarget(null)}
               onConfirm={handleSuspendMembership}
               tone="danger"
            >
               <p>
                  <strong>@{getUsername(suspendTarget)}</strong> will immediately lose the organization-scoped
                  capabilities associated with the <strong>{formatLabel(suspendTarget.role)}</strong> role.
               </p>

               <p>Their TruthLens account remains active. You can restore this organization membership later.</p>
            </AdminConfirmDialog>
         )}

         {restoreTarget && (
            <AdminConfirmDialog
               dialogRef={dialogRef}
               titleId="restore-membership-title"
               descriptionId="restore-membership-description"
               title="Restore membership?"
               confirmLabel="Restore membership"
               confirmIcon="user-check"
               confirmClassName="primary"
               busy={memberActionId === restoreTarget.id}
               onClose={() => setRestoreTarget(null)}
               onConfirm={handleRestoreMembership}
               tone="warning"
            >
               <p>
                  Restoring <strong>@{getUsername(restoreTarget)}</strong> immediately restores the organization-scoped
                  capabilities associated with the <strong>{formatLabel(restoreTarget.role)}</strong> role.
               </p>
            </AdminConfirmDialog>
         )}

         {removeTarget && (
            <AdminConfirmDialog
               dialogRef={dialogRef}
               titleId="remove-membership-title"
               descriptionId="remove-membership-description"
               title="Remove from organization?"
               confirmLabel="Remove from organization"
               confirmIcon="trash"
               confirmClassName="danger"
               busy={memberActionId === removeTarget.id}
               onClose={() => setRemoveTarget(null)}
               onConfirm={handleRemoveMembership}
               tone="danger"
            >
               <p>
                  <strong>@{getUsername(removeTarget)}</strong> will no longer be a member of{" "}
                  <strong>{organizationName}</strong>.
               </p>

               <p>
                  Their TruthLens account will not be deleted. To rejoin later, they must receive and accept a new
                  organization invitation.
               </p>
            </AdminConfirmDialog>
         )}
      </div>
   );
}

export default OrganizationAdminPanel;
