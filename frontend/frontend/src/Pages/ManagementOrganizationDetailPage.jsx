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
import Select from "../components/ui/Select";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import {
   formatManagementDate,
   MANAGEMENT_PARTNER_STATUSES,
   MANAGEMENT_VERIFICATION_STATUSES,
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
   returnFocusAfterRefreshRef,
}) {
   const lifecycle = organization.lifecycle || {};
   const impact = lifecycle.impact || {};
   const blockers = lifecycle.end_partnership_blockers || [];
   const [editing, setEditing] = useState(false);
   const [legacyConfirmationOpen, setLegacyConfirmationOpen] = useState(false);
   const [endConfirmationOpen, setEndConfirmationOpen] = useState(false);
   const editButtonRef = useRef(null);
   const endButtonRef = useRef(null);
   const saveButtonRef = useRef(null);
   const [values, setValues] = useState({
      verification_status: organization.verification_status,
      partner_status: organization.partner_status,
   });
   const { mutate, pending, error, reset } = useManagementMutation();

   useEffect(() => {
      if (returnFocusAfterRefreshRef.current && editButtonRef.current) {
         returnFocusAfterRefreshRef.current = false;
         editButtonRef.current.focus();
      }
   }, [returnFocusAfterRefreshRef]);

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
   const canUseLegacyEditor = !isFormerPartner && !isRetirementRequired;
   const partnerStatusOptions = MANAGEMENT_PARTNER_STATUSES.filter(([value]) => {
      if (value === "FORMER") return false;
      if (isCurrentPartner) return ["ACTIVE", "SUSPENDED"].includes(value);
      if (organization.partner_status === "NONE") return ["NONE", "ACTIVE"].includes(value);
      return value === organization.partner_status;
   });

   const hasChanges =
      values.verification_status !== organization.verification_status ||
      values.partner_status !== organization.partner_status;
   const isHighImpactChange =
      (
         values.verification_status !== organization.verification_status &&
         values.verification_status === "REJECTED"
      ) ||
      (
         values.partner_status !== organization.partner_status &&
         values.partner_status === "SUSPENDED"
      );

   const beginEditing = () => {
      reset();
      setValues({
         verification_status: organization.verification_status,
         partner_status: organization.partner_status,
      });
      setEditing(true);
   };

   const cancelEditing = () => {
      if (pending) return;
      reset();
      setLegacyConfirmationOpen(false);
      setEditing(false);
   };

   const saveLegacyChanges = async () => {
      const body = {};
      if (values.verification_status !== organization.verification_status) {
         body.verification_status = values.verification_status;
      }
      if (values.partner_status !== organization.partner_status) {
         body.partner_status = values.partner_status;
      }

      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATION_PLATFORM_TRUST", organization.id),
         { method: "PATCH", body },
      );
      if (!result.ok) return false;

      returnFocusAfterRefreshRef.current = true;
      setLegacyConfirmationOpen(false);
      setEditing(false);
      onFeedback("Organization governance status updated.");
      onRefresh();
      return true;
   };

   const submitLegacyChanges = (event) => {
      event.preventDefault();
      if (!hasChanges || pending) return;
      if (isHighImpactChange) {
         setLegacyConfirmationOpen(true);
         return;
      }
      saveLegacyChanges();
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
               Complete the governed retirement flow instead of changing raw status fields.
            </ManagementFeedback>
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
               </div>
               <Button
                  ref={endButtonRef}
                  variant="destructive"
                  disabled={!lifecycle.can_end_partnership || pending}
                  onClick={() => {
                     reset();
                     setEndConfirmationOpen(true);
                  }}
               >
                  End partnership
               </Button>
            </div>
         ) : null}

         {canUseLegacyEditor ? (
            <div className="management-governance-legacy">
               <div className="management-governance-legacy__heading">
                  <div>
                     <strong>Remaining status controls</strong>
                     <p>
                        Temporary compatibility controls while Verify, Activate, Suspend, and Reject are migrated to dedicated governance actions.
                        Former Partner is intentionally unavailable here.
                     </p>
                  </div>
                  {!editing ? (
                     <Button
                        ref={editButtonRef}
                        variant="secondary"
                        density="compact"
                        onClick={beginEditing}
                     >
                        Manage remaining statuses
                     </Button>
                  ) : null}
               </div>

               {editing ? (
                  <form className="management-trust-editor" onSubmit={submitLegacyChanges}>
                     <label className="management-form-field">
                        <span>Verification status</span>
                        <Select
                           value={values.verification_status}
                           onChange={(event) => {
                              reset();
                              setValues((current) => ({
                                 ...current,
                                 verification_status: event.target.value,
                              }));
                           }}
                           invalid={Boolean(error?.fields.verification_status)}
                           aria-describedby={error?.fields.verification_status ? "governance-verification-error" : undefined}
                           disabled={pending}
                        >
                           {MANAGEMENT_VERIFICATION_STATUSES.map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                           ))}
                        </Select>
                        <FieldError id="governance-verification-error">{error?.fields.verification_status}</FieldError>
                     </label>
                     <label className="management-form-field">
                        <span>Partner status</span>
                        <Select
                           value={values.partner_status}
                           onChange={(event) => {
                              reset();
                              setValues((current) => ({
                                 ...current,
                                 partner_status: event.target.value,
                              }));
                           }}
                           invalid={Boolean(error?.fields.partner_status)}
                           aria-describedby={error?.fields.partner_status ? "governance-partner-error" : undefined}
                           disabled={pending}
                        >
                           {partnerStatusOptions.map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                           ))}
                        </Select>
                        <FieldError id="governance-partner-error">{error?.fields.partner_status}</FieldError>
                     </label>
                     <div className="management-inline-actions">
                        <Button variant="secondary" disabled={pending} onClick={cancelEditing}>Cancel</Button>
                        <Button
                           ref={saveButtonRef}
                           type="submit"
                           loading={pending}
                           loadingLabel="Saving…"
                           disabled={!hasChanges}
                        >
                           Save changes
                        </Button>
                     </div>
                     {isHighImpactChange ? (
                        <p className="management-governance-inline-warning">
                           This status change affects current organization authority. End Partnership must use the dedicated action above.
                        </p>
                     ) : null}
                     {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
                  </form>
               ) : null}
            </div>
         ) : null}

         <ManagementConfirmDialog
            open={legacyConfirmationOpen}
            title="Confirm governance status change"
            description="Review the selected verification and partnership statuses before applying this compatibility transition."
            warning="Rejected and suspended statuses affect current organization authority. Former Partner cannot be set here and must use the dedicated End partnership lifecycle action."
            error={error?.message}
            confirmLabel="Apply status change"
            confirmVariant="destructive"
            processing={pending}
            returnFocusRef={saveButtonRef}
            onConfirm={saveLegacyChanges}
            onClose={() => setLegacyConfirmationOpen(false)}
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
            returnFocusRef={endButtonRef}
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

   useEffect(() => {
      if (
         primaryAdmin?.state === "NONE"
         && returnFocusAfterRefreshRef.current
         && provisionButtonRef.current
      ) {
         returnFocusAfterRefreshRef.current = false;
         provisionButtonRef.current.focus();
      }
   }, [primaryAdmin?.state, returnFocusAfterRefreshRef]);

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
                  <Button
                     variant="secondary"
                     onClick={() => {
                        reset();
                        setResendConfirmationOpen(true);
                     }}
                  >
                     Resend invitation
                  </Button>
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
            {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
            <ManagementConfirmDialog
               open={resendConfirmationOpen}
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
   const returnFocusAfterTrustRefreshRef = useRef(false);
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
                     returnFocusAfterRefreshRef={returnFocusAfterTrustRefreshRef}
                  />
                  <VerificationScopeSection organization={data} />
                  <section className="management-detail-section">
                     <OrganizationAdminState
                        organizationId={data.id}
                        primaryAdmin={data.organization_admin ?? data.primary_admin}
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
