import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
   DetailList,
   ManagementConfirmDialog,
   ManagementFeedback,
   ManagementPageHeader,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import {
   formatManagementDate,
   formatVerificationDomain,
} from "../utils/management";

function FieldError({ id, children }) {
   if (!children) return null;
   return <span id={id} className="management-field-error">{children}</span>;
}

function OrganizationGovernanceSection({
   organization,
   onRefresh,
   onFeedback,
}) {
   const lifecycle = organization.lifecycle || {};
   const actions = lifecycle.actions || {};
   const impact = lifecycle.impact || {};
   const blockers = lifecycle.end_partnership_blockers || [];
   const activeFactualCorrections = lifecycle.active_factual_corrections || [];
   const [confirmationAction, setConfirmationAction] = useState(null);
   const [correctionConfirmation, setCorrectionConfirmation] = useState(null);
   const [endConfirmationOpen, setEndConfirmationOpen] = useState(false);
   const { mutate, pending, error, reset } = useManagementMutation();

   const lifecycleLabels = {
      ACTIVE_PARTNER: "Active Partner",
      SUSPENDED_PARTNER: "Suspended Partner",
      FORMER_PARTNER: "Former Partner",
      RETIREMENT_REQUIRED: "Retirement Required",
      REJECTED: "Rejected",
      ONBOARDING: "Onboarding",
   };
   const accessLabels = {
      ENABLED: "Verification Workspace enabled",
      DISABLED: "Verification Workspace disabled",
      SETUP_ONLY: "Organization setup only",
   };
   const isCurrentPartner = ["ACTIVE", "SUSPENDED"].includes(organization.partner_status);
   const isRetirementRequired = lifecycle.state === "RETIREMENT_REQUIRED";
   const isFormerPartner = lifecycle.state === "FORMER_PARTNER";
   const canShowEndAction = isCurrentPartner || isRetirementRequired;

   const governanceActions = [
      {
         key: "verify",
         allowed: actions.can_verify,
         label: "Verify organization",
         endpoint: "MANAGEMENT_ORGANIZATION_VERIFY",
         description: "Approve the organization’s institutional verification. This does not activate a partnership by itself.",
         warning: "Verification establishes the organization’s approved institutional status. Partnership activation remains a separate governance action.",
         success: "Organization verification approved.",
         variant: "primary",
      },
      {
         key: "reject",
         allowed: actions.can_reject_verification,
         label: "Reject verification",
         endpoint: "MANAGEMENT_ORGANIZATION_REJECT_VERIFICATION",
         description: "Reject an onboarding verification review before the organization becomes an active Partner.",
         warning: "The organization will remain outside Partner verification operations. This does not delete its institutional record.",
         success: "Organization verification rejected.",
         variant: "destructive",
      },
      {
         key: "activate",
         allowed: actions.can_activate_partnership,
         label: "Activate partnership",
         endpoint: "MANAGEMENT_ORGANIZATION_ACTIVATE_PARTNERSHIP",
         description: "Enable Partner status after institutional verification has been approved.",
         warning: "Eligible active organization members will gain the Partner capabilities assigned to their roles.",
         success: "Partnership activated.",
         variant: "primary",
      },
      {
         key: "suspend",
         allowed: actions.can_suspend_partnership,
         label: "Suspend partnership",
         endpoint: "MANAGEMENT_ORGANIZATION_SUSPEND_PARTNERSHIP",
         description: "Temporarily disable Partner verification authority without ending the partnership.",
         warning: "Current memberships and investigation ownership are retained. Members cannot perform Partner verification work until the partnership is reinstated or ended.",
         success: "Partnership suspended.",
         variant: "destructive",
      },
      {
         key: "reinstate",
         allowed: actions.can_reinstate_partnership,
         label: "Reinstate partnership",
         endpoint: "MANAGEMENT_ORGANIZATION_REINSTATE_PARTNERSHIP",
         description: isFormerPartner
            ? "Restore active Partner status after a former partnership."
            : "Restore active Partner authority after a suspension.",
         warning: isFormerPartner
            ? "Historical memberships remain historical and are not reactivated automatically. Current members must be provisioned or invited through the normal organization workflow."
            : "Existing current memberships remain unchanged and eligible role capabilities become active again.",
         success: "Partnership reinstated.",
         variant: "primary",
      },
   ].filter((action) => action.allowed);

   const selectedAction = governanceActions.find(
      (action) => action.key === confirmationAction,
   );

   const executeGovernanceAction = async () => {
      if (!selectedAction) return;

      const result = await mutate(
         resolveApiEndpoint(selectedAction.endpoint, organization.id),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      setConfirmationAction(null);
      onFeedback(selectedAction.success);
      onRefresh();
   };

   const cancelCorrectionForRetirement = async () => {
      if (!correctionConfirmation) return;

      const result = await mutate(
         resolveApiEndpoint(
            "MANAGEMENT_ORGANIZATION_CANCEL_FACTUAL_CORRECTION_FOR_RETIREMENT",
            organization.id,
            correctionConfirmation.id,
         ),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      setCorrectionConfirmation(null);
      onFeedback(
         "Factual correction cancelled for retirement. The current published fact-check remains authoritative historical work.",
      );
      onRefresh();
   };

   const endPartnership = async () => {
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATION_END_PARTNERSHIP", organization.id),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      setEndConfirmationOpen(false);
      onFeedback(
         `Partnership ended. ${result.data.transition.ended_memberships} current membership(s) ended, ${result.data.transition.cancelled_invitations} pending invitation(s) cancelled, and ${result.data.transition.requeued_investigations} investigation(s) returned to intake.`,
      );
      onRefresh();
   };

   const endImpactSummary = [
      `${impact.current_memberships ?? 0} current membership(s) will end`,
      `${impact.pending_invitations ?? 0} pending invitation(s) will be cancelled`,
      `${impact.active_investigations ?? 0} active investigation(s) will return to intake`,
      "completed adjudications, published fact-checks, authorship, and provenance will be retained",
   ].join("; ");

   return (
      <section className="management-detail-section management-governance-section">
         <div className="management-governance-heading">
            <div>
               <span className="management-governance-eyebrow">Platform-controlled lifecycle</span>
               <h2>Organization Governance</h2>
               <p className="management-section__description">
                  Govern verification approval and partnership lifecycle without rewriting historical authorship or verification provenance.
               </p>
            </div>
            <ManagementStatus
               value={organization.partner_status}
               label={lifecycleLabels[lifecycle.state] || organization.partner_status_label}
            />
         </div>

         <div className="management-governance-status-grid">
            <article>
               <span>Verification</span>
               <ManagementStatus
                  value={organization.verification_status}
                  label={
                     isFormerPartner && organization.verification_status === "VERIFIED"
                        ? "Previously verified"
                        : organization.verification_status_label
                  }
               />
            </article>
            <article>
               <span>Partnership</span>
               <ManagementStatus
                  value={organization.partner_status}
                  label={organization.partner_status_label}
               />
            </article>
            <article>
               <span>Operational access</span>
               <strong>{accessLabels[lifecycle.operational_access] || "Not recorded"}</strong>
            </article>
         </div>

         {isRetirementRequired ? (
            <ManagementFeedback tone="error">
               This organization has prior Partner verification work but is still recorded as “Not a Partner.”
               Complete the governed retirement flow before any later reinstatement.
            </ManagementFeedback>
         ) : null}

         {governanceActions.length ? (
            <div className="management-governance-actions">
               <div>
                  <strong>Available governance actions</strong>
                  <p>
                     Only transitions valid for the organization’s current lifecycle state are available.
                  </p>
               </div>
               <div className="management-governance-action-buttons">
                  {governanceActions.map((action) => (
                     <Button
                        key={action.key}
                        variant={action.variant}
                        disabled={pending}
                        onClick={() => {
                           reset();
                           setConfirmationAction(action.key);
                        }}
                     >
                        {action.label}
                     </Button>
                  ))}
               </div>
            </div>
         ) : null}

         {canShowEndAction ? (
            <div className="management-governance-action">
               <div>
                  <strong>End partnership</strong>
                  <p>
                     End future Partner authority and relinquish unfinished verification ownership.
                     Completed work remains attributed to this organization and its original authors.
                  </p>
                  <DetailList items={[
                     { label: "Current memberships", value: String(impact.current_memberships ?? 0) },
                     { label: "Pending invitations", value: String(impact.pending_invitations ?? 0) },
                     { label: "Active investigations", value: String(impact.active_investigations ?? 0) },
                     { label: "Active factual corrections", value: String(impact.active_factual_corrections ?? 0) },
                  ]} />
                  {blockers.length ? (
                     <div className="management-governance-blockers" role="status">
                        {blockers.map((blocker) => (
                           <p key={blocker.code}>{blocker.message}</p>
                        ))}
                     </div>
                  ) : null}
                  {activeFactualCorrections.length ? (
                     <div className="management-governance-correction-list">
                        {activeFactualCorrections.map((correction) => (
                           <article
                              key={correction.id}
                              className="management-governance-correction"
                           >
                              <div>
                                 <span>Active factual correction</span>
                                 <strong>
                                    {correction.predecessor_headline || "Published fact-check"}
                                 </strong>
                                 <p>{correction.correction_reason}</p>
                                 <small>
                                    Requested {formatManagementDate(correction.requested_at)}
                                 </small>
                              </div>
                              <Button
                                 variant="destructive"
                                 density="compact"
                                 disabled={pending}
                                 onClick={() => {
                                    reset();
                                    setCorrectionConfirmation(correction);
                                 }}
                              >
                                 Cancel correction for retirement
                              </Button>
                           </article>
                        ))}
                     </div>
                  ) : null}
               </div>
               <Button
                  variant="destructive"
                  disabled={!actions.can_end_partnership || pending}
                  onClick={() => {
                     reset();
                     setEndConfirmationOpen(true);
                  }}
               >
                  End partnership
               </Button>
            </div>
         ) : null}

         <ManagementConfirmDialog
            open={Boolean(correctionConfirmation)}
            title="Cancel this factual correction for retirement?"
            description={
               correctionConfirmation
                  ? `This will cancel the active correction for “${correctionConfirmation.predecessor_headline || "the published fact-check"}”.`
                  : "This will cancel the active factual correction."
            }
            warning="The correction request and its adjudication case will become terminal and cannot be resumed. Any saved proposal and all provenance will be preserved. The currently published fact-check will remain the authoritative historical publication until a separate future correction is completed."
            error={error?.message}
            confirmLabel="Cancel correction"
            confirmVariant="destructive"
            processing={pending}
            onConfirm={cancelCorrectionForRetirement}
            onClose={() => setCorrectionConfirmation(null)}
         />
         <ManagementConfirmDialog
            open={Boolean(selectedAction)}
            title={selectedAction ? `${selectedAction.label}?` : "Confirm governance action"}
            description={selectedAction?.description}
            warning={selectedAction?.warning}
            error={error?.message}
            confirmLabel={selectedAction?.label || "Confirm"}
            confirmVariant={selectedAction?.variant || "primary"}
            processing={pending}
            onConfirm={executeGovernanceAction}
            onClose={() => setConfirmationAction(null)}
         />
         <ManagementConfirmDialog
            open={endConfirmationOpen}
            title="End this Partner Organization’s partnership?"
            description="This is an operational retirement action. Historical verification records and published work will not be deleted."
            warning={endImpactSummary}
            error={error?.message}
            confirmLabel="End partnership"
            confirmVariant="destructive"
            processing={pending}
            onConfirm={endPartnership}
            onClose={() => setEndConfirmationOpen(false)}
         />
      </section>
   );
}

function VerificationScopeSection({ organization }) {
   const specializations = organization.verification_specializations || [];
   return (
      <section className="management-detail-section">
         <h2>Organization verification specializations</h2>
         <p className="management-section__description">
            The Organization Admin manages these investigation subjects in the partner workspace.
            Platform administration oversees partnership status and onboarding, not the
            organization's subject choices.
         </p>
         <DetailList items={[
            { label: "Selected subjects", value: specializations.length
               ? specializations.map(formatVerificationDomain).join(", ") : "Not configured" },
            { label: "Managed by", value: "Organization Admin" },
         ]} />
      </section>
   );
}

function OrganizationAdminState({
   organizationId,
   primaryAdmin,
   adminOnboarding,
   onRefresh,
   onFeedback,
   returnFocusAfterRefreshRef,
}) {
   const [provisioningOpen, setProvisioningOpen] = useState(false);
   const [resendConfirmationOpen, setResendConfirmationOpen] = useState(false);
   const [cancelConfirmationOpen, setCancelConfirmationOpen] = useState(false);
   const [email, setEmail] = useState("");
   const cancelInvitationButtonRef = useRef(null);
   const provisionButtonRef = useRef(null);
   const { mutate, pending, error, reset } = useManagementMutation();
   const adminOnboardingAllowed = adminOnboarding?.allowed !== false;
   const adminOnboardingMessage = adminOnboarding?.message
      || "Organization Admin onboarding is unavailable in the current lifecycle state.";

   useEffect(() => {
      if (
         adminOnboardingAllowed
         && primaryAdmin?.state === "NONE"
         && returnFocusAfterRefreshRef.current
         && provisionButtonRef.current
      ) {
         returnFocusAfterRefreshRef.current = false;
         provisionButtonRef.current.focus();
      }
   }, [
      adminOnboardingAllowed,
      primaryAdmin?.state,
      returnFocusAfterRefreshRef,
   ]);

   const submitProvision = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_PRIMARY_ADMIN_PROVISION", organizationId),
         { method: "POST", body: { email } },
      );
      if (!result.ok) return;

      setProvisioningOpen(false);
      setEmail("");
      onFeedback(`Organization Admin invitation sent to ${result.data.email}.`);
      onRefresh();
   };

   const resend = async () => {
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_PRIMARY_ADMIN_RESEND", organizationId),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      setResendConfirmationOpen(false);
      onFeedback(`A new invitation link was sent to ${result.data.email}.`);
      onRefresh();
   };

   const cancelInvitation = async () => {
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_PRIMARY_ADMIN_CANCEL", organizationId),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;

      returnFocusAfterRefreshRef.current = true;
      setCancelConfirmationOpen(false);
      onFeedback("Organization Admin invitation cancelled.");
      onRefresh();
   };

   if (primaryAdmin?.state === "CURRENT") {
      const membership = primaryAdmin.membership;
      return (
         <>
            <div className="management-section__title-row">
               <h2>Organization Admins</h2>
               <ManagementStatus value={membership.status} />
            </div>
            <p className="management-section__description">
               Platform onboarding is complete. Additional Admins are managed through the organization's membership controls.
            </p>
            <DetailList items={[
               { label: "Current Admins", value: String(primaryAdmin.current_count || 1) },
               { label: "Admin record", value: `@${membership.user.username}` },
               { label: "Email", value: membership.user.email },
               { label: "Role", value: membership.role_label },
               { label: "Joined", node: formatManagementDate(membership.joined_at) },
               { label: "Approved", node: formatManagementDate(membership.approved_at) },
            ]} />
            <Link className="management-inline-link" to={`/management/memberships/${membership.id}`}>View membership record</Link>
         </>
      );
   }

   if (primaryAdmin?.state === "PENDING") {
      const invitation = primaryAdmin.invitation;
      return (
         <>
            <div className="management-section__title-row">
               <h2>Organization Admin</h2>
               <ManagementStatus value={invitation.status} />
            </div>
            <p className="management-section__description">An Organization Admin onboarding invitation is awaiting acceptance.</p>
            <DetailList items={[
               { label: "Email", value: invitation.email },
               { label: "Role", value: invitation.role_label },
               { label: "Sent", node: formatManagementDate(invitation.last_sent_at) },
               { label: "Expires", node: formatManagementDate(invitation.expires_at) },
               { label: "Deliveries", value: String(invitation.send_count) },
            ]} />
            <div className="management-record-actions">
               <Link className="management-inline-link" to={`/management/invitations/${invitation.id}`}>View invitation record</Link>
               <div className="management-inline-actions">
                  {adminOnboardingAllowed ? (
                     <Button
                        variant="secondary"
                        onClick={() => {
                           reset();
                           setResendConfirmationOpen(true);
                        }}
                     >
                        Resend invitation
                     </Button>
                  ) : null}
                  <Button
                     ref={cancelInvitationButtonRef}
                     variant="destructive"
                     onClick={() => {
                        reset();
                        setCancelConfirmationOpen(true);
                     }}
                  >
                     Cancel invitation
                  </Button>
               </div>
            </div>
            {!adminOnboardingAllowed ? (
               <ManagementFeedback tone="error">
                  {adminOnboardingMessage}
               </ManagementFeedback>
            ) : null}
            {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
            <ManagementConfirmDialog
               open={adminOnboardingAllowed && resendConfirmationOpen}
               title="Resend Organization Admin invitation?"
               description={`Send a new invitation link to ${invitation.email}?`}
               warning="Resending invalidates the previous invitation link."
               error={error?.message}
               confirmLabel="Resend invitation"
               processing={pending}
               onConfirm={resend}
               onClose={() => setResendConfirmationOpen(false)}
            />
            <ManagementConfirmDialog
               open={cancelConfirmationOpen}
               title="Cancel Organization Admin invitation?"
               description="Cancel the pending onboarding invitation for this organization?"
               warning="The current invitation link will stop working immediately. The organization will return to having no assigned Organization Admin until a new invitation is issued."
               error={error?.message}
               confirmLabel="Cancel invitation"
               confirmVariant="destructive"
               processing={pending}
               returnFocusRef={cancelInvitationButtonRef}
               onConfirm={cancelInvitation}
               onClose={() => setCancelConfirmationOpen(false)}
            />
         </>
      );
   }

   if (!adminOnboardingAllowed) {
      return (
         <>
            <h2>Organization Admin onboarding</h2>
            <p className="management-section__description">
               New Organization Admin authority cannot be created in this lifecycle state.
            </p>
            <ManagementFeedback tone="error">
               {adminOnboardingMessage}
            </ManagementFeedback>
         </>
      );
   }

   return (
      <>
         <h2>Organization Admin onboarding</h2>
         <p className="management-section__description">
            Provision the organization's first Admin. Additional Admins can be invited later by an existing Admin.
         </p>
         {!provisioningOpen ? (
            <div className="management-empty-action">
               <p>Not yet assigned</p>
               <Button
                  ref={provisionButtonRef}
                  onClick={() => {
                     reset();
                     setProvisioningOpen(true);
                  }}
               >
                  Provision Organization Admin
               </Button>
            </div>
         ) : (
            <form className="management-provision-form" onSubmit={submitProvision}>
               <div className="management-provision-form__intro">
                  <strong>Invite the organization’s first Admin</strong>
                  <p>
                     The recipient uses their own TruthLens account, and the invited email must match their verified account when accepting. TruthLens does not create or know their password. This role does not imply legal or business ownership.
                  </p>
               </div>
               <label className="management-form-field">
                  <span>Email</span>
                  <Input
                     type="email"
                     value={email}
                     onChange={(event) => {
                        reset();
                        setEmail(event.target.value);
                     }}
                     invalid={Boolean(error?.fields.email)}
                     aria-describedby={error?.fields.email ? "primary-admin-email-error" : undefined}
                     autoComplete="email"
                     required
                     disabled={pending}
                  />
                  <FieldError id="primary-admin-email-error">{error?.fields.email}</FieldError>
               </label>
               <div className="management-inline-actions">
                  <Button
                     variant="secondary"
                     disabled={pending}
                     onClick={() => {
                        reset();
                        setEmail("");
                        setProvisioningOpen(false);
                     }}
                  >
                     Cancel
                  </Button>
                  <Button type="submit" loading={pending} loadingLabel="Sending invitation…">
                     Send invitation
                  </Button>
               </div>
               {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
            </form>
         )}
      </>
   );
}

function ManagementOrganizationDetailPage() {
   const { organizationId } = useParams();
   const [feedback, setFeedback] = useState("");
   const returnFocusAfterPrimaryAdminRefreshRef = useRef(false);
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_ORGANIZATION_DETAIL", organizationId),
   );
   const showFeedback = useCallback((message) => setFeedback(message), []);

   return (
      <div className="management-page">
         <ManagementPageHeader
            title={data?.name || "Organization"}
            subtitle={data ? `${data.organization_type_label} · ${data.slug}` : "Institutional governance record"}
            backTo="/management/organizations"
            backLabel="Partner Organizations"
            actions={data ? (
               <Link
                  className="tl-button tl-button--secondary tl-button--compact"
                  to={`/management/audit?${new URLSearchParams({ organization: data.name }).toString()}`}
               >
                  View governance audit
               </Link>
            ) : null}
         />
         {feedback ? <ManagementFeedback>{feedback}</ManagementFeedback> : null}
         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections">
                  <OrganizationGovernanceSection
                     organization={data}
                     onRefresh={retry}
                     onFeedback={showFeedback}
                  />
                  <VerificationScopeSection organization={data} />
                  <section className="management-detail-section">
                     <OrganizationAdminState
                        organizationId={data.id}
                        primaryAdmin={data.organization_admin ?? data.primary_admin}
                        adminOnboarding={data.lifecycle?.admin_onboarding}
                        onRefresh={retry}
                        onFeedback={showFeedback}
                        returnFocusAfterRefreshRef={returnFocusAfterPrimaryAdminRefreshRef}
                     />
                  </section>
                  <section className="management-detail-section">
                     <h2>Institutional Identity</h2>
                     <DetailList items={[
                        { label: "Name", value: data.name },
                        { label: "Slug", value: data.slug },
                        { label: "Type", value: data.organization_type_label },
                        { label: "Organization ID", value: data.id },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Organization-managed Public Profile</h2>
                     <DetailList items={[
                        { label: "Description", value: data.description },
                        { label: "Website", node: data.website ? <a href={data.website} target="_blank" rel="noreferrer">{data.website}</a> : "Not provided" },
                        { label: "Logo URL", value: data.logo_url || "Not provided" },
                        { label: "Legacy descriptive interests (not authorization)", value: data.expertise_areas?.length ? data.expertise_areas.join(", ") : "Not provided" },
                        { label: "Public profile", value: data.public_profile_enabled ? "Enabled" : "Disabled" },
                        { label: "Public logo", value: data.public_logo_enabled ? "Enabled" : "Disabled" },
                     ]} />
                  </section>
                  <section className="management-detail-section">
                     <h2>Record Metadata</h2>
                     <DetailList items={[
                        { label: "Created", node: formatManagementDate(data.created_at) },
                        { label: "Last updated", node: formatManagementDate(data.updated_at) },
                     ]} />
                  </section>
               </div>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}

export default ManagementOrganizationDetailPage;
