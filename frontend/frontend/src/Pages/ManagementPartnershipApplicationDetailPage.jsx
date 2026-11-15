import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";

import {
   DetailList,
   ManagementFeedback,
   ManagementPageHeader,
   ManagementRequestState,
   ManagementStatus,
} from "../components/management/ManagementUi";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Textarea from "../components/ui/Textarea";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementDate } from "../utils/management";

import "./ManagementPartnershipApplications.css";

function ReviewActions({ application, onRefresh }) {
   const { mutate, pending, error, success, reset } = useManagementMutation();
   const [approvedAdminEmail, setApprovedAdminEmail] = useState(
      application.approved_admin_email || application.applicant_email,
   );
   const [approvalNotes, setApprovalNotes] = useState("");
   const [rejectionNotes, setRejectionNotes] = useState("");

   const startReview = async () => {
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_PARTNERSHIP_APPLICATION_REVIEW", application.id),
         { method: "POST", body: {} },
         "Application review started.",
      );
      if (result.ok) onRefresh();
   };

   const approve = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_PARTNERSHIP_APPLICATION_APPROVE", application.id),
         {
            method: "POST",
            body: {
               approved_admin_email: approvedAdminEmail.trim(),
               decision_notes: approvalNotes.trim(),
            },
         },
         "Application approved for Organization Admin onboarding.",
      );
      if (result.ok) onRefresh();
   };

   const reject = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_PARTNERSHIP_APPLICATION_REJECT", application.id),
         {
            method: "POST",
            body: { decision_notes: rejectionNotes.trim() },
         },
         "Partnership application rejected.",
      );
      if (result.ok) onRefresh();
   };

   if (application.status === "SUBMITTED") {
      return (
         <section className="management-detail-section management-application-decision">
            <h2>Platform review</h2>
            <p className="management-section__description">
               Start review before making an approval or rejection decision. This records who began the platform review.
            </p>
            <Button onClick={startReview} loading={pending} loadingLabel="Starting review…">
               Start review
            </Button>
            {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
         </section>
      );
   }

   if (application.status === "UNDER_REVIEW") {
      return (
         <section className="management-detail-section management-application-decision">
            <div className="management-section__title-row">
               <h2>Partnership decision</h2>
               <ManagementStatus value={application.status} label={application.status_label} />
            </div>
            <p className="management-section__description">
               Approve only after the organization, representative, and supporting information have been reviewed.
            </p>

            <div className="management-application-decision-grid">
               <form onSubmit={approve}>
                  <h3>Approve for onboarding</h3>
                  <p>
                     Approval does not activate the organization immediately. It authorizes an Admin invitation to the
                     exact representative email below.
                  </p>
                  <label className="management-form-field">
                     <span>Approved Organization Admin email</span>
                     <Input
                        type="email"
                        value={approvedAdminEmail}
                        onChange={(event) => {
                           reset();
                           setApprovedAdminEmail(event.target.value);
                        }}
                        invalid={Boolean(error?.fields.approved_admin_email)}
                        required
                     />
                     {error?.fields.approved_admin_email ? (
                        <small className="management-field-error">{error.fields.approved_admin_email}</small>
                     ) : null}
                  </label>
                  <label className="management-form-field">
                     <span>Approval notes</span>
                     <Textarea
                        rows={4}
                        value={approvalNotes}
                        onChange={(event) => {
                           reset();
                           setApprovalNotes(event.target.value);
                        }}
                        placeholder="Optional internal review notes"
                     />
                  </label>
                  <Button type="submit" loading={pending} loadingLabel="Approving…">
                     Approve for onboarding
                  </Button>
               </form>

               <form onSubmit={reject} className="management-application-reject">
                  <h3>Reject application</h3>
                  <p>
                     Rejection closes this onboarding request and marks the provisional organization as Rejected.
                  </p>
                  <label className="management-form-field">
                     <span>Rejection rationale</span>
                     <Textarea
                        rows={5}
                        value={rejectionNotes}
                        onChange={(event) => {
                           reset();
                           setRejectionNotes(event.target.value);
                        }}
                        invalid={Boolean(error?.fields.decision_notes)}
                        required
                     />
                     {error?.fields.decision_notes ? (
                        <small className="management-field-error">{error.fields.decision_notes}</small>
                     ) : null}
                  </label>
                  <Button
                     type="submit"
                     variant="destructive"
                     loading={pending}
                     loadingLabel="Rejecting…"
                     disabled={!rejectionNotes.trim()}
                  >
                     Reject application
                  </Button>
               </form>
            </div>
            {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
            {success ? <ManagementFeedback>{success}</ManagementFeedback> : null}
         </section>
      );
   }

   return (
      <section className="management-detail-section management-application-decision">
         <div className="management-section__title-row">
            <h2>Decision</h2>
            <ManagementStatus value={application.status} label={application.status_label} />
         </div>
         <DetailList items={[
            { label: "Decision time", node: formatManagementDate(application.decided_at) },
            { label: "Decision by", value: application.decided_by_username ? "@" + application.decided_by_username : "Not recorded" },
            { label: "Approved Admin email", value: application.approved_admin_email || "Not applicable" },
            { label: "Onboarding completed", node: application.onboarding_completed_at ? formatManagementDate(application.onboarding_completed_at) : "Not yet" },
            { label: "Decision notes", value: application.decision_notes || "No notes recorded" },
         ]} />
         {application.status === "APPROVED" ? (
            <div className="management-application-next-step">
               <div>
                  <strong>
                     {application.onboarding_completed_at
                        ? "Partner onboarding completed"
                        : "Next: provision the approved Organization Admin"}
                  </strong>
                  <p>
                     {application.onboarding_completed_at
                        ? "The approved representative accepted the secure invitation and TruthLens finalized Verified + Active status."
                        : "Send the secure Admin invitation from the organization record. Only the approved email can be used."}
                  </p>
               </div>
               <Link
                  className="tl-button tl-button--primary tl-button--standard"
                  to={"/management/organizations/" + application.organization.id}
               >
                  Open organization
               </Link>
            </div>
         ) : null}
      </section>
   );
}

export default function ManagementPartnershipApplicationDetailPage() {
   const { applicationId } = useParams();
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_PARTNERSHIP_APPLICATION_DETAIL", applicationId),
   );

   return (
      <div className="management-page">
         <ManagementPageHeader
            title={data?.organization?.name || "Partnership Application"}
            subtitle={data ? data.status_label + " · submitted " + formatManagementDate(data.created_at) : "Institutional partnership review"}
            backTo="/management/partnership-applications"
            backLabel="Partner Applications"
            actions={data ? (
               <Link
                  className="tl-button tl-button--secondary tl-button--compact"
                  to={"/management/organizations/" + data.organization.id}
               >
                  Organization record
               </Link>
            ) : null}
         />

         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            {data ? (
               <div className="management-detail-sections">
                  <section className="management-detail-section management-application-summary">
                     <div className="management-section__title-row">
                        <h2>Application status</h2>
                        <ManagementStatus value={data.status} label={data.status_label} />
                     </div>
                     <DetailList items={[
                        { label: "Organization verification", value: data.organization.verification_status_label },
                        { label: "Partnership status", value: data.organization.partner_status_label },
                        { label: "Review started", node: data.review_started_at ? formatManagementDate(data.review_started_at) : "Not yet" },
                        { label: "Reviewer", value: data.reviewer_username ? "@" + data.reviewer_username : "Not assigned" },
                     ]} />
                  </section>

                  <section className="management-detail-section">
                     <h2>Organization identity</h2>
                     <DetailList items={[
                        { label: "Organization name", value: data.organization.name },
                        { label: "Type", value: data.organization.organization_type_label },
                        {
                           label: "Website",
                           node: data.organization.website ? (
                              <a href={data.organization.website} target="_blank" rel="noreferrer">
                                 {data.organization.website} <ExternalLink size={13} />
                              </a>
                           ) : "Not provided",
                        },
                        { label: "Official contact", value: data.official_contact_email },
                     ]} />
                     <div className="management-application-longform">
                        <strong>Organization description</strong>
                        <p>{data.organization_description}</p>
                     </div>
                  </section>

                  <section className="management-detail-section">
                     <h2>Applicant</h2>
                     <DetailList items={[
                        { label: "Full name", value: data.applicant_full_name },
                        { label: "Position", value: data.applicant_position },
                        { label: "Email", value: data.applicant_email },
                        { label: "Authorized representative", value: data.authorized_to_represent ? "Confirmed" : "Not confirmed" },
                     ]} />
                  </section>

                  <section className="management-detail-section">
                     <h2>Partnership request</h2>
                     <div className="management-application-longform">
                        <strong>Reason for partnership</strong>
                        <p>{data.partnership_reason}</p>
                     </div>
                     <div className="management-application-longform">
                        <strong>Partner responsibilities</strong>
                        <p>{data.agrees_to_partner_responsibilities ? "Applicant acknowledged TruthLens Partner responsibilities." : "Not acknowledged."}</p>
                     </div>
                     <div className="management-application-links">
                        <strong>Supporting links</strong>
                        {data.supporting_links?.length ? (
                           data.supporting_links.map((link) => (
                              <a key={link} href={link} target="_blank" rel="noreferrer">
                                 {link} <ExternalLink size={13} />
                              </a>
                           ))
                        ) : <span>No supporting links provided.</span>}
                     </div>
                  </section>

                  <ReviewActions key={data.id + ":" + data.status} application={data} onRefresh={retry} />
               </div>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}
