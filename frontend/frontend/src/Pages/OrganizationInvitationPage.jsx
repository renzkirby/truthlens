import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import Icons from "../components/Icons.jsx";

import { resolveApiEndpoint } from "../utils/api";
import { createAuthReturnState } from "../utils/authNavigation";
import { canAccessWorkspace } from "../utils/workspace";

import "./OrganizationInvitationPage.css";

function formatExpiration(value) {
   if (!value) {
      return "Unknown";
   }

   const date = new Date(value);

   if (Number.isNaN(date.getTime())) {
      return "Unknown";
   }

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function getOrganizationInitials(name = "") {
   const words = name.trim().split(/\s+/).filter(Boolean);

   if (!words.length) {
      return "TL";
   }

   return words
      .slice(0, 2)
      .map((word) => word[0])
      .join("")
      .toUpperCase();
}

function OrganizationInvitationPage() {
   const { token } = useParams();
   const location = useLocation();
   const navigate = useNavigate();

   const { token: authToken, user, loading: authLoading, authFetch, refreshUser, logout } = useAuth();

   const [invitation, setInvitation] = useState(null);

   const [loadState, setLoadState] = useState("loading");

   const [isAccepting, setIsAccepting] = useState(false);

   const [acceptanceState, setAcceptanceState] = useState("idle");

   const [actionMessage, setActionMessage] = useState("");

   const [acceptedUser, setAcceptedUser] = useState(null);

   const [isSendingVerification, setIsSendingVerification] = useState(false);

   const [isCheckingVerification, setIsCheckingVerification] = useState(false);

   const invitationDetailEndpoint = token ? resolveApiEndpoint("ORGANIZATION_INVITATION_DETAIL", token) : null;

   const invitationAcceptEndpoint = token ? resolveApiEndpoint("ORGANIZATION_INVITATION_ACCEPT", token) : null;

   const loadInvitation = useCallback(async () => {
      if (!invitationDetailEndpoint) {
         setInvitation(null);
         setLoadState("invalid");
         return;
      }

      setLoadState("loading");

      try {
         const response = await fetch(invitationDetailEndpoint, {
            method: "GET",
         });

         const data = await response.json().catch(() => ({}));

         if (response.status === 404) {
            setInvitation(null);
            setLoadState("invalid");
            return;
         }

         if (!response.ok) {
            throw new Error(data?.detail || "Unable to load invitation.");
         }

         setInvitation(data);
         setLoadState("ready");
      } catch (error) {
         console.error("Failed to load organization invitation:", error);

         setInvitation(null);
         setLoadState("error");
      }
   }, [invitationDetailEndpoint]);

   useEffect(() => {
      loadInvitation();
   }, [loadInvitation]);

   const goToAuthentication = (destination) => {
      navigate(destination, {
         state: createAuthReturnState(location),
      });
   };

   const handleUseAnotherAccount = () => {
      logout();

      navigate("/login", {
         replace: true,
         state: createAuthReturnState(location),
      });
   };

   const handleSendVerification = async () => {
      if (isSendingVerification) {
         return;
      }

      setIsSendingVerification(true);
      setActionMessage("");

      try {
         const response = await authFetch(resolveApiEndpoint("SEND_VERIFICATION"), {
            method: "POST",
         });

         setActionMessage(response?.detail || "Verification email sent. Check your inbox.");
      } catch (error) {
         console.error("Failed to send verification email:", error);

         setActionMessage(error?.message || "Unable to send a verification email right now.");
      } finally {
         setIsSendingVerification(false);
      }
   };

   const handleCheckVerification = async () => {
      if (isCheckingVerification) {
         return;
      }

      setIsCheckingVerification(true);
      setActionMessage("");

      try {
         const updatedUser = await refreshUser();

         if (updatedUser?.is_email_verified) {
            setAcceptanceState("idle");

            setActionMessage("Your email is verified. You can now accept the invitation.");
         } else {
            setActionMessage("Your email is not verified yet.");
         }
      } catch (error) {
         console.error("Failed to refresh account:", error);

         setActionMessage("Unable to refresh your account right now.");
      } finally {
         setIsCheckingVerification(false);
      }
   };

   const handleAccept = async () => {
      if (!invitationAcceptEndpoint || isAccepting) {
         return;
      }

      setIsAccepting(true);
      setAcceptanceState("idle");
      setActionMessage("");

      try {
         const result = await authFetch(invitationAcceptEndpoint, {
            method: "POST",
         });

         const updatedUser = await refreshUser();

         setAcceptedUser(updatedUser || user);

         setInvitation(result?.invitation || invitation);

         setAcceptanceState("accepted");
      } catch (error) {
         console.error("Failed to accept organization invitation:", error);

         const message = error?.message || "Unable to accept this invitation.";

         const normalizedMessage = message.toLowerCase();

         if (error?.status === 404) {
            setInvitation(null);
            setLoadState("invalid");
            return;
         }

         if (error?.status === 403 && normalizedMessage.includes("verify your email")) {
            setAcceptanceState("verification-required");

            setActionMessage(message);
            return;
         }

         if (error?.status === 403) {
            setAcceptanceState("wrong-account");

            setActionMessage(message);
            return;
         }

         if (error?.status === 409) {
            setAcceptanceState("conflict");

            setActionMessage(message);
            return;
         }

         setAcceptanceState("error");
         setActionMessage(message);
      } finally {
         setIsAccepting(false);
      }
   };

   if (loadState === "loading") {
      return (
         <div className="org-invite-page">
            <main className="org-invite-card org-invite-card--state" aria-busy="true" aria-live="polite">
               <span className="org-invite-spinner" aria-hidden="true" />

               <h1>Loading invitation</h1>

               <p>Confirming your TruthLens organization invitation.</p>
            </main>
         </div>
      );
   }

   if (loadState === "invalid") {
      return (
         <div className="org-invite-page">
            <main className="org-invite-card org-invite-card--state" role="alert">
               <div className="org-invite-state-icon">
                  <Icons name="alert-triangle" size={28} aria-hidden="true" />
               </div>

               <p className="org-invite-eyebrow">TruthLens Partner Network</p>

               <h1>Invitation unavailable</h1>

               <p>
                  This invitation link is invalid, has been cancelled, has already been used, or was replaced by a newer
                  invitation.
               </p>

               <button
                  type="button"
                  className="org-invite-button org-invite-button--secondary"
                  onClick={() => navigate("/community")}
               >
                  Go to TruthLens
               </button>
            </main>
         </div>
      );
   }

   if (loadState === "error") {
      return (
         <div className="org-invite-page">
            <main className="org-invite-card org-invite-card--state" role="alert">
               <div className="org-invite-state-icon">
                  <Icons name="alert-triangle" size={28} aria-hidden="true" />
               </div>

               <h1>Invitation temporarily unavailable</h1>

               <p>TruthLens couldn't load this invitation right now.</p>

               <button type="button" className="org-invite-button org-invite-button--primary" onClick={loadInvitation}>
                  Try again
               </button>
            </main>
         </div>
      );
   }

   const organization = invitation?.organization || {};

   const isExpired = invitation?.status === "EXPIRED";

   const isAuthenticated = Boolean(authToken);

   const effectiveUser = acceptedUser || user;

   const successDestination = canAccessWorkspace(effectiveUser) ? "/workspace" : "/dashboard";

   if (acceptanceState === "accepted") {
      return (
         <div className="org-invite-page">
            <main className="org-invite-card org-invite-card--state" aria-live="polite">
               <div className="org-invite-state-icon org-invite-state-icon--success">
                  <Icons name="check-circle" size={30} aria-hidden="true" />
               </div>

               <p className="org-invite-eyebrow">Membership activated</p>

               <h1>You're now part of {organization.name}</h1>

               <p>
                  Your TruthLens account now has the organization role <strong>{invitation.invited_role_label}</strong>.
               </p>

               <button
                  type="button"
                  className="org-invite-button org-invite-button--primary"
                  onClick={() =>
                     navigate(successDestination, {
                        replace: true,
                     })
                  }
               >
                  {successDestination === "/workspace" ? "Open Verification Workspace" : "Go to Dashboard"}
               </button>
            </main>
         </div>
      );
   }

   return (
      <div className="org-invite-page">
         <main className="org-invite-card">
            <header className="org-invite-header">
               <div className="org-invite-brand">
                  <Icons name="shield" size={18} aria-hidden="true" />

                  <span>TruthLens Partner Network</span>
               </div>

               <p className="org-invite-eyebrow">Organization invitation</p>

               <h1>You've been invited to join {organization.name}</h1>

               <p className="org-invite-intro">Review the organization and role below before accepting.</p>
            </header>

            <section className="org-invite-organization" aria-label="Inviting organization">
               {organization.logo_url ? (
                  <img
                     src={organization.logo_url}
                     alt={`${organization.name} logo`}
                     className="org-invite-logo"
                     referrerPolicy="no-referrer"
                  />
               ) : (
                  <div className="org-invite-logo org-invite-logo--fallback" aria-hidden="true">
                     {getOrganizationInitials(organization.name)}
                  </div>
               )}

               <div className="org-invite-org-copy">
                  <strong>{organization.name}</strong>

                  {invitation.invited_by?.username && <span>Invited by @{invitation.invited_by.username}</span>}
               </div>
            </section>

            <dl className="org-invite-details">
               <div>
                  <dt>Organization role</dt>

                  <dd>{invitation.invited_role_label}</dd>
               </div>

               <div>
                  <dt>Status</dt>

                  <dd>{isExpired ? "Expired" : "Pending"}</dd>
               </div>

               <div>
                  <dt>Expires</dt>

                  <dd>{formatExpiration(invitation.expires_at)}</dd>
               </div>
            </dl>

            <div className="org-invite-authority-note">
               <Icons name="shield" size={18} aria-hidden="true" />

               <p>
                  Accepting this invitation adds organization-scoped institutional authority to your personal TruthLens
                  account according to the assigned role. Your personal account remains separate from the organization.
               </p>
            </div>

            {isExpired ? (
               <div className="org-invite-message org-invite-message--warning" role="status">
                  <Icons name="clock" size={18} aria-hidden="true" />

                  <div>
                     <strong>This invitation has expired.</strong>

                     <p>Contact an organization administrator if you still need access.</p>
                  </div>
               </div>
            ) : authLoading ? (
               <div className="org-invite-message" aria-live="polite">
                  Checking your TruthLens account…
               </div>
            ) : !isAuthenticated ? (
               <div className="org-invite-actions">
                  <p>
                     Sign in with the account that should receive this organization membership, or create a TruthLens
                     account.
                  </p>

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--primary"
                     onClick={() => goToAuthentication("/login")}
                  >
                     Sign in
                  </button>

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--secondary"
                     onClick={() => goToAuthentication("/register")}
                  >
                     Create account
                  </button>
               </div>
            ) : !user ? (
               <div className="org-invite-message org-invite-message--warning" role="alert">
                  <p>TruthLens couldn't load your account information.</p>

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--secondary"
                     onClick={() => refreshUser()}
                  >
                     Reload account
                  </button>
               </div>
            ) : !user.is_email_verified || acceptanceState === "verification-required" ? (
               <div className="org-invite-actions">
                  <div className="org-invite-message org-invite-message--warning" role="status">
                     <Icons name="mail" size={18} aria-hidden="true" />

                     <div>
                        <strong>Verify your email first</strong>

                        <p>
                           Institutional membership cannot be activated until the email address on your TruthLens
                           account has been verified.
                        </p>
                     </div>
                  </div>

                  {actionMessage && (
                     <p className="org-invite-action-message" aria-live="polite">
                        {actionMessage}
                     </p>
                  )}

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--primary"
                     onClick={handleSendVerification}
                     disabled={isSendingVerification}
                  >
                     {isSendingVerification ? "Sending…" : "Send verification email"}
                  </button>

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--secondary"
                     onClick={handleCheckVerification}
                     disabled={isCheckingVerification}
                  >
                     {isCheckingVerification ? "Checking…" : "I've verified my email"}
                  </button>
               </div>
            ) : acceptanceState === "wrong-account" ? (
               <div className="org-invite-actions">
                  <div className="org-invite-message org-invite-message--danger" role="alert">
                     <Icons name="alert-triangle" size={18} aria-hidden="true" />

                     <div>
                        <strong>This invitation belongs to another account</strong>

                        <p>{actionMessage || "Sign in with the account this invitation was issued to."}</p>
                     </div>
                  </div>

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--primary"
                     onClick={handleUseAnotherAccount}
                  >
                     Sign in with another account
                  </button>
               </div>
            ) : (
               <div className="org-invite-actions">
                  <div className="org-invite-account">
                     <span>Signed in as</span>

                     <strong>{user.email}</strong>
                  </div>

                  {(acceptanceState === "conflict" || acceptanceState === "error") && (
                     <div className="org-invite-message org-invite-message--danger" role="alert">
                        <Icons name="alert-triangle" size={18} aria-hidden="true" />

                        <p>{actionMessage}</p>
                     </div>
                  )}

                  <button
                     type="button"
                     className="org-invite-button org-invite-button--primary"
                     onClick={handleAccept}
                     disabled={isAccepting}
                     aria-busy={isAccepting}
                  >
                     {isAccepting ? "Accepting invitation…" : "Accept invitation"}
                  </button>

                  <p className="org-invite-consent">Membership is not activated until you explicitly accept.</p>
               </div>
            )}
         </main>
      </div>
   );
}

export default OrganizationInvitationPage;
