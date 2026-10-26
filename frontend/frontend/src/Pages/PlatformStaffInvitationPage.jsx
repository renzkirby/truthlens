import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import AccountStatus from "../components/account/AccountStatus.jsx";
import Icons from "../components/Icons.jsx";
import Button from "../components/ui/Button.jsx";
import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import { createAuthReturnState } from "../utils/authNavigation";

import "./OrganizationInvitationPage.css";

function formatExpiration(value) {
   if (!value) return "Unknown";
   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Unknown";
   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function getSignedInIdentity(user) {
   const username = typeof user?.username === "string" ? user.username.trim() : "";
   const email = typeof user?.email === "string" ? user.email.trim() : "";
   if (username && email) return `@${username} (${email})`;
   if (username) return `@${username}`;
   if (email) return email;
   return "your current account";
}

function PlatformStaffInvitationPage() {
   const { token } = useParams();
   const location = useLocation();
   const navigate = useNavigate();
   const {
      token: authToken,
      user,
      loading: authLoading,
      authFetch,
      refreshUser,
      logout,
   } = useAuth();

   const [invitation, setInvitation] = useState(null);
   const [loadState, setLoadState] = useState("loading");
   const [acceptanceState, setAcceptanceState] = useState("idle");
   const [actionMessage, setActionMessage] = useState("");
   const [isAccepting, setIsAccepting] = useState(false);
   const [isSendingVerification, setIsSendingVerification] = useState(false);
   const [isCheckingVerification, setIsCheckingVerification] = useState(false);

   const detailEndpoint = token
      ? resolveApiEndpoint("PLATFORM_STAFF_INVITATION_DETAIL", token)
      : null;
   const acceptEndpoint = token
      ? resolveApiEndpoint("PLATFORM_STAFF_INVITATION_ACCEPT", token)
      : null;

   const loadInvitation = useCallback(async () => {
      if (!detailEndpoint) {
         setInvitation(null);
         setLoadState("invalid");
         return;
      }

      setLoadState("loading");
      try {
         if (authToken && !authLoading) {
            const data = await authFetch(detailEndpoint, { method: "GET" });
            setInvitation(data);
            setLoadState("ready");
            return;
         }

         const response = await fetch(detailEndpoint, { method: "GET" });
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
         if (error?.status === 404) {
            setInvitation(null);
            setLoadState("invalid");
            return;
         }
         setInvitation(null);
         setLoadState("error");
      }
   }, [authFetch, authLoading, authToken, detailEndpoint]);

   useEffect(() => {
      loadInvitation();
   }, [loadInvitation]);

   const goToAuthentication = (destination) => {
      navigate(destination, { state: createAuthReturnState(location) });
   };

   const handleUseAnotherAccount = () => {
      logout();
      navigate("/login", {
         replace: true,
         state: createAuthReturnState(location),
      });
   };

   const handleSendVerification = async () => {
      if (isSendingVerification) return;
      setIsSendingVerification(true);
      setActionMessage("");
      try {
         const response = await authFetch(resolveApiEndpoint("SEND_VERIFICATION"), {
            method: "POST",
         });
         setActionMessage(response?.detail || "Verification email sent. Check your inbox.");
      } catch (error) {
         setActionMessage(error?.message || "Unable to send a verification email right now.");
      } finally {
         setIsSendingVerification(false);
      }
   };

   const handleCheckVerification = async () => {
      if (isCheckingVerification) return;
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
      } catch {
         setActionMessage("Unable to refresh your account right now.");
      } finally {
         setIsCheckingVerification(false);
      }
   };

   const handleAccept = async () => {
      if (!acceptEndpoint || isAccepting) return;
      setIsAccepting(true);
      setAcceptanceState("idle");
      setActionMessage("");
      try {
         const result = await authFetch(acceptEndpoint, { method: "POST" });
         await refreshUser();
         setInvitation(result?.invitation || invitation);
         setAcceptanceState("accepted");
      } catch (error) {
         const message = error?.message || "Unable to accept this invitation.";
         const normalized = message.toLowerCase();

         if (error?.status === 404) {
            setInvitation(null);
            setLoadState("invalid");
         } else if (error?.status === 403 && normalized.includes("verify your email")) {
            setAcceptanceState("verification-required");
            setActionMessage(message);
         } else if (error?.status === 403) {
            setAcceptanceState("wrong-account");
            setActionMessage(message);
         } else if (error?.status === 409) {
            setAcceptanceState("conflict");
            setActionMessage(message);
         } else {
            setAcceptanceState("error");
            setActionMessage(message);
         }
      } finally {
         setIsAccepting(false);
      }
   };

   if (loadState === "loading") {
      return (
         <div className="org-invite-card org-invite-card--state">
            <AccountStatus
               tone="info"
               loading
               title="Loading invitation"
               description="Confirming your TruthLens Platform Staff invitation."
               live="polite"
               busy
            />
         </div>
      );
   }

   if (loadState === "invalid") {
      return (
         <div className="org-invite-card org-invite-card--state" role="alert">
            <AccountStatus
               tone="warning"
               icon={<Icons name="alert-triangle" size={28} aria-hidden="true" />}
               eyebrow="TruthLens Platform Governance"
               title="Invitation unavailable"
               description="This invitation link is invalid, cancelled, already used, or replaced by a newer invitation."
               actions={
                  <Button
                     type="button"
                     variant="secondary"
                     density="comfortable"
                     fullWidth
                     onClick={() => navigate("/community")}
                  >
                     Go to TruthLens
                  </Button>
               }
            />
         </div>
      );
   }

   if (loadState === "error") {
      return (
         <div className="org-invite-card org-invite-card--state" role="alert">
            <AccountStatus
               tone="critical"
               icon={<Icons name="alert-triangle" size={28} aria-hidden="true" />}
               title="Invitation temporarily unavailable"
               description="TruthLens couldn't load this Platform Staff invitation right now."
               actions={
                  <Button
                     type="button"
                     variant="primary"
                     density="comfortable"
                     fullWidth
                     onClick={loadInvitation}
                  >
                     Try again
                  </Button>
               }
            />
         </div>
      );
   }

   const isExpired = invitation?.status === "EXPIRED";
   const isAuthenticated = Boolean(authToken);
   const accountMismatch =
      isAuthenticated && invitation?.recipient_matches_current_user === false;
   const signedInIdentity = getSignedInIdentity(user);

   if (acceptanceState === "accepted") {
      return (
         <div className="org-invite-card org-invite-card--state">
            <AccountStatus
               tone="success"
               icon={<Icons name="check-circle" size={30} aria-hidden="true" />}
               eyebrow="Platform Safety access activated"
               title="You're now a Platform Safety Moderator"
               description="Your account can access Safety Review and Safety Audit. Partner Organization authority remains separate."
               actions={
                  <Button
                     type="button"
                     variant="primary"
                     density="comfortable"
                     fullWidth
                     onClick={() => navigate("/management/safety", { replace: true })}
                  >
                     Open Platform Safety Console
                  </Button>
               }
               live="polite"
            />
         </div>
      );
   }

   return (
      <div className="org-invite-card">
         <header className="org-invite-header">
            <div className="org-invite-brand">
               <Icons name="shield-check" size={18} aria-hidden="true" />
               <span>TruthLens Platform Governance</span>
            </div>

            <p className="org-invite-eyebrow">Platform Staff invitation</p>
            <h1>You've been invited to join Platform Safety</h1>
            <p className="org-invite-intro">
               Review the role and account requirements before accepting.
            </p>
         </header>

         <section className="org-invite-organization" aria-label="Platform role">
            <div className="org-invite-logo org-invite-logo--fallback" aria-hidden="true">
               <Icons name="shield-user" size={24} />
            </div>
            <div className="org-invite-org-copy">
               <strong>{invitation.platform_role_label}</strong>
               {invitation.invited_by?.username ? (
                  <span>Invited by @{invitation.invited_by.username}</span>
               ) : null}
            </div>
         </section>

         <dl className="org-invite-details">
            <div>
               <dt>Platform role</dt>
               <dd>{invitation.platform_role_label}</dd>
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

         <div className="org-invite-membership-note">
            <Icons name="shield" size={18} aria-hidden="true" />
            <p>
               Platform Safety reviews whether Community content or accounts violate platform policy.
               It does not determine factual truth and does not grant Partner Organization authority.
               While this role is active, this staff identity does not participate in Community
               reputation or ordinary Community contributions.
            </p>
         </div>

         {isExpired ? (
            <div className="org-invite-message org-invite-message--warning" role="status">
               <Icons name="clock" size={18} aria-hidden="true" />
               <div>
                  <strong>This invitation has expired.</strong>
                  <p>Contact a Platform Admin if you still need Platform Safety access.</p>
               </div>
            </div>
         ) : authLoading ? (
            <div className="org-invite-message" aria-live="polite">
               Checking your TruthLens account…
            </div>
         ) : !isAuthenticated ? (
            <div className="org-invite-actions">
               <p>
                  Sign in with the account that should receive Platform Safety access, or
                  create a TruthLens account using the invited email address.
               </p>
               <Button
                  type="button"
                  variant="primary"
                  density="comfortable"
                  fullWidth
                  onClick={() => goToAuthentication("/login")}
               >
                  Sign in
               </Button>
               <Button
                  type="button"
                  variant="secondary"
                  density="comfortable"
                  fullWidth
                  onClick={() => goToAuthentication("/register")}
               >
                  Create account
               </Button>
            </div>
         ) : !user ? (
            <div className="org-invite-message org-invite-message--critical" role="alert">
               <p>TruthLens couldn't load your account information.</p>
               <Button
                  type="button"
                  variant="secondary"
                  density="comfortable"
                  fullWidth
                  onClick={() => refreshUser()}
               >
                  Reload account
               </Button>
            </div>
         ) : accountMismatch || acceptanceState === "wrong-account" ? (
            <div className="org-invite-actions">
               <div className="org-invite-message org-invite-message--critical" role="alert">
                  <Icons name="alert-triangle" size={18} aria-hidden="true" />
                  <div>
                     <strong>This invitation belongs to another account</strong>
                     <p>
                        {actionMessage || (
                           <>
                              You're signed in as <strong>{signedInIdentity}</strong>, but the
                              invitation was issued to a different email address.
                           </>
                        )}
                     </p>
                  </div>
               </div>
               <Button
                  type="button"
                  variant="primary"
                  density="comfortable"
                  fullWidth
                  onClick={handleUseAnotherAccount}
               >
                  Switch account
               </Button>
            </div>
         ) : !user.is_email_verified || acceptanceState === "verification-required" ? (
            <div className="org-invite-actions">
               <div className="org-invite-message org-invite-message--warning" role="status">
                  <Icons name="mail" size={18} aria-hidden="true" />
                  <div>
                     <strong>Verify your email first</strong>
                     <p>
                        Platform Safety access cannot be activated until the invited email
                        address on your TruthLens account has been verified.
                     </p>
                  </div>
               </div>

               {actionMessage ? (
                  <p className="org-invite-action-message" aria-live="polite">
                     {actionMessage}
                  </p>
               ) : null}

               <Button
                  type="button"
                  variant="primary"
                  density="comfortable"
                  fullWidth
                  onClick={handleSendVerification}
                  loading={isSendingVerification}
                  loadingLabel="Sending…"
               >
                  Send verification email
               </Button>
               <Button
                  type="button"
                  variant="secondary"
                  density="comfortable"
                  fullWidth
                  onClick={handleCheckVerification}
                  loading={isCheckingVerification}
                  loadingLabel="Checking…"
               >
                  I've verified my email
               </Button>
            </div>
         ) : (
            <div className="org-invite-actions">
               <div className="org-invite-account">
                  <span>Signed in as</span>
                  <strong>{signedInIdentity}</strong>
               </div>

               {(acceptanceState === "conflict" || acceptanceState === "error") ? (
                  <div className="org-invite-message org-invite-message--critical" role="alert">
                     <Icons name="alert-triangle" size={18} aria-hidden="true" />
                     <p>{actionMessage}</p>
                  </div>
               ) : null}

               <Button
                  type="button"
                  variant="primary"
                  density="comfortable"
                  fullWidth
                  onClick={handleAccept}
                  loading={isAccepting}
                  loadingLabel="Accepting invitation…"
               >
                  Accept Platform Staff invitation
               </Button>
            </div>
         )}
      </div>
   );
}

export default PlatformStaffInvitationPage;
