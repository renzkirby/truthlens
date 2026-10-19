import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
   DetailList,
   ManagementConfirmDialog,
   ManagementFeedback,
   ManagementFormDialog,
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
   MANAGEMENT_VERIFICATION_DOMAINS,
   formatVerificationDomain,
} from "../utils/management";

function FieldError({ id, children }) {
   if (!children) return null;
   return <span id={id} className="management-field-error">{children}</span>;
}

function PlatformTrustSection({
   organization,
   onRefresh,
   onFeedback,
   returnFocusAfterRefreshRef,
}) {
   const [editing, setEditing] = useState(false);
   const [confirmationOpen, setConfirmationOpen] = useState(false);
   const editButtonRef = useRef(null);
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
         ["SUSPENDED", "FORMER"].includes(values.partner_status)
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
      setConfirmationOpen(false);
      setEditing(false);
   };

   const saveChanges = async () => {
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
      if (!result.ok) return;

      returnFocusAfterRefreshRef.current = true;
      setConfirmationOpen(false);
      setEditing(false);
      onFeedback("Platform trust updated.");
      onRefresh();
   };

   const submit = (event) => {
      event.preventDefault();
      if (!hasChanges || pending) return;
      if (isHighImpactChange) {
         setConfirmationOpen(true);
         return;
      }
      saveChanges();
   };

   return (
      <section className="management-detail-section management-detail-section--trust">
         <div className="management-trust-heading">
            <h2>Platform Trust</h2>
            {!editing ? (
               <Button ref={editButtonRef} variant="secondary" density="compact" onClick={beginEditing}>
                  Edit platform trust
               </Button>
            ) : null}
         </div>

         {!editing ? (
            <div className="management-trust-statuses">
               <div><span>Verification</span><ManagementStatus value={organization.verification_status} label={organization.verification_status_label} /></div>
               <div><span>Partner status</span><ManagementStatus value={organization.partner_status} label={organization.partner_status_label} /></div>
            </div>
         ) : (
            <form className="management-trust-editor" onSubmit={submit}>
               <label className="management-form-field">
                  <span>Verification status</span>
                  <Select
                     value={values.verification_status}
                     onChange={(event) => {
                        reset();
                        setValues((current) => ({ ...current, verification_status: event.target.value }));
                     }}
                     invalid={Boolean(error?.fields.verification_status)}
                     aria-describedby={error?.fields.verification_status ? "trust-verification-error" : undefined}
                     disabled={pending}
                  >
                     {MANAGEMENT_VERIFICATION_STATUSES.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                     ))}
                  </Select>
                  <FieldError id="trust-verification-error">{error?.fields.verification_status}</FieldError>
               </label>
               <label className="management-form-field">
                  <span>Partner status</span>
                  <Select
                     value={values.partner_status}
                     onChange={(event) => {
                        reset();
                        setValues((current) => ({ ...current, partner_status: event.target.value }));
                     }}
                     invalid={Boolean(error?.fields.partner_status)}
                     aria-describedby={error?.fields.partner_status ? "trust-partner-error" : undefined}
                     disabled={pending}
                  >
                     {MANAGEMENT_PARTNER_STATUSES.map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                     ))}
                  </Select>
                  <FieldError id="trust-partner-error">{error?.fields.partner_status}</FieldError>
               </label>
               <div className="management-inline-actions">
                  <Button variant="secondary" disabled={pending} onClick={cancelEditing}>Cancel</Button>
                  <Button ref={saveButtonRef} type="submit" loading={pending} loadingLabel="Saving…" disabled={!hasChanges}>
                     Save changes
                  </Button>
               </div>
               {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
            </form>
         )}

         <ManagementConfirmDialog
            open={confirmationOpen}
            title="Confirm high-impact trust change"
            description="Review the selected governance statuses before saving this organization record."
            warning="Rejected, suspended, and former statuses are high-impact platform trust choices. Confirm that the selected values are intentional."
            error={error?.message}
            confirmLabel="Save trust changes"
            confirmVariant="destructive"
            processing={pending}
            returnFocusRef={saveButtonRef}
            onConfirm={saveChanges}
            onClose={() => setConfirmationOpen(false)}
         />
      </section>
   );
}


function VerificationScopeSection({ organization, onRefresh, onFeedback }) {
   const [editing, setEditing] = useState(false);
   const editButtonRef = useRef(null);
   const [domains, setDomains] = useState([]);
   const [jurisdictions, setJurisdictions] = useState("");
   const [rationale, setRationale] = useState("");
   const { mutate, pending, error, reset } = useManagementMutation();

   const startEditing = () => {
      setDomains(organization.approved_verification_domains || []);
      setJurisdictions((organization.approved_verification_jurisdictions || []).join(", "));
      setRationale("");
      reset();
      setEditing(true);
   };
   const close = () => { if (!pending) { reset(); setEditing(false); } };
   const save = async (event) => {
      event.preventDefault();
      const list = [...new Set(jurisdictions.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean))];
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATION_VERIFICATION_SCOPE", organization.id),
         { method: "PATCH", body: {
            domains, jurisdictions: list, rationale: rationale.trim(),
         } },
      );
      if (!result.ok) return;
      setEditing(false);
      onFeedback("Authorized investigation scope reviewed and saved.");
      onRefresh();
   };
   const approved = organization.approved_verification_domains || [];
   const requested = organization.requested_verification_domains || [];
   const requestedLocations = organization.requested_verification_jurisdictions || [];
   const active = organization.active_verification_domains || [];
   const activeLocations = organization.active_verification_jurisdictions || [];
   return (
      <section className="management-detail-section">
         <div className="management-trust-heading">
            <h2>Authorized Investigation Specializations</h2>
            <Button ref={editButtonRef} variant="secondary" density="compact" onClick={startEditing}>
               Review platform approval
            </Button>
         </div>
         <p className="management-section__description">
            Organization leadership requests and activates specializations;
            the platform independently approves the maximum investigation scope.
         </p>
         <DetailList items={[
            { label: "Platform-approved subjects", value: approved.length ? approved.map(formatVerificationDomain).join(", ") : "None approved" },
            { label: "Approved geographic coverage", value: (organization.approved_verification_jurisdictions || []).join(", ") || "None approved" },
            { label: "Requested subjects", value: requested.length ? requested.map(formatVerificationDomain).join(", ") : "No request" },
            { label: "Requested geographic coverage", value: requestedLocations.join(", ") || "No request" },
            { label: "Currently active subjects", value: (organization.active_scope_configured ? active : approved).map(formatVerificationDomain).join(", ") || "None active" },
            { label: "Currently active geographic coverage", value: (organization.active_scope_configured ? activeLocations : (organization.approved_verification_jurisdictions || [])).join(", ") || "None active" },
         ]} />
         <ManagementFormDialog open={editing} title="Review platform-approved investigation scope"
            description="Grant only specializations and geographic coverage supported by the organization's qualifications. New approvals do not override an explicit active selection."
            onClose={close} processing={pending} returnFocusRef={editButtonRef}>
            <form className="management-modal-form" onSubmit={save}>
               {requested.length ? (
                  <p className="management-scope-request-summary">
                     Organization request: {requested.map(formatVerificationDomain).join(", ")}
                     {requestedLocations.length ? ` · ${requestedLocations.join(", ")}` : ""}
                  </p>
               ) : <p className="management-scope-request-summary">
                  No new request from the organization is recorded. Review institutional qualifications before granting authority.
               </p>}
               <fieldset className="management-modal-fieldset" disabled={pending}>
                  <legend>Platform-approved subject matter</legend>
                  <p>Select all subject areas the institution is authorized to investigate.</p>
                  <div className="management-scope-options">
                     {MANAGEMENT_VERIFICATION_DOMAINS.map(([code, label]) => (
                        <label key={code} className={`management-scope-option ${domains.includes(code) ? "is-selected" : ""}`}>
                           <input type="checkbox" checked={domains.includes(code)}
                              onChange={(event) => {
                                 reset();
                                 setDomains((current) => event.target.checked
                                    ? [...current, code] : current.filter((entry) => entry !== code));
                              }} />
                           <span>{label}</span>
                        </label>
                     ))}
                  </div>
               </fieldset>
               <label className="management-form-field">
                  <strong>Approved geographic coverage</strong>
                  <Input value={jurisdictions} placeholder="PH, PH-NCR or GLOBAL"
                     disabled={pending} onChange={(event) => { reset(); setJurisdictions(event.target.value); }} />
                  <small>Comma-separated codes. GLOBAL grants worldwide authority.</small>
               </label>
               <label className="management-form-field">
                  <strong>Reason for platform decision</strong>
                  <textarea rows={3} maxLength={2000} minLength={12}
                     disabled={pending} value={rationale}
                     onChange={(event) => { reset(); setRationale(event.target.value); }}
                     required placeholder="Document evidence of qualifications or reason for revocation" />
               </label>
               {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
               <div className="management-dialog__actions">
                  <Button variant="secondary" type="button" disabled={pending} onClick={close}>Cancel</Button>
                  <Button type="submit" disabled={pending || rationale.trim().length < 12 || Boolean(domains.length) !== Boolean(jurisdictions.trim())}
                     loading={pending} loadingLabel="Saving…">Save platform approval</Button>
               </div>
            </form>
         </ManagementFormDialog>
      </section>
   );
}

function PrimaryAdminState({
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
      onFeedback(`Primary Admin invitation sent to ${result.data.email}.`);
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
      onFeedback("Primary Admin invitation cancelled.");
      onRefresh();
   };

   if (primaryAdmin?.state === "CURRENT") {
      const membership = primaryAdmin.membership;
      return (
         <>
            <div className="management-section__title-row">
               <h2>Primary Admin</h2>
               <ManagementStatus value={membership.status} />
            </div>
            <p className="management-section__description">
               Highest organization authority within TruthLens. This role does not imply legal or business ownership of the organization.
            </p>
            <DetailList items={[
               { label: "Username", value: `@${membership.user.username}` },
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
               <h2>Primary Admin</h2>
               <ManagementStatus value={invitation.status} />
            </div>
            <p className="management-section__description">A Primary Admin onboarding invitation is awaiting acceptance.</p>
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
               title="Resend Primary Admin invitation?"
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
               title="Cancel Primary Admin invitation?"
               description="Cancel the pending onboarding invitation for this organization?"
               warning="The current invitation link will stop working immediately. The organization will return to having no assigned Primary Admin until a new invitation is issued."
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
         <h2>Primary Admin</h2>
         <p className="management-section__description">Highest organization authority within TruthLens.</p>
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
                  Provision Primary Admin
               </Button>
            </div>
         ) : (
            <form className="management-provision-form" onSubmit={submitProvision}>
               <div className="management-provision-form__intro">
                  <strong>Invite the organization’s first Primary Admin</strong>
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
                  <PlatformTrustSection
                     organization={data}
                     onRefresh={retry}
                     onFeedback={showFeedback}
                     returnFocusAfterRefreshRef={returnFocusAfterTrustRefreshRef}
                  />
                  <VerificationScopeSection
                     organization={data}
                     onRefresh={retry}
                     onFeedback={showFeedback}
                  />
                  <section className="management-detail-section">
                     <PrimaryAdminState
                        organizationId={data.id}
                        primaryAdmin={data.primary_admin}
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
                        { label: "Expertise", value: data.expertise_areas?.length ? data.expertise_areas.join(", ") : "Not provided" },
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
