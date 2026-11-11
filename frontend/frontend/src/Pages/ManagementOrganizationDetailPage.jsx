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
   const [suspensionForm, setSuspensionForm] = useState({
      suspension_type: "",
      factors: [],
      severity: "",
      rationale: "",
      policy_basis: "",
      supporting_basis: "",
      supporting_references: "",
      other_factor_explanation: "",
      remediation_problem: "",
      remediation_required_action: "",
      remediation_evidence_required: "",
      remediation_deadline: "",
      remediation_review_method: "",
      remediation_failure_consequence: "",
      review_date: "",
   });
   const [reinstatementForm, setReinstatementForm] = useState({
      basis: "",
      rationale: "",
      supporting_basis: "",
      supporting_references: "",
      completed_remediation: "",
      continuing_conditions: "",
      monitoring_end_date: "",
      monitoring_success_criteria: "",
      monitoring_recurrence_consequence: "",
   });
   const [endingForm, setEndingForm] = useState({
      ending_type: "",
      ground: "",
      factors: [],
      severity: "",
      rationale: "",
      policy_basis: "",
      supporting_basis: "",
      supporting_references: "",
      other_factor_explanation: "",
   });
   const [validationTouched, setValidationTouched] = useState({
      suspend: {},
      reinstate: {},
      end: {},
   });
   const { mutate, pending, error, reset } = useManagementMutation();

   const markValidationTouched = (form, field) => {
      setValidationTouched((current) => ({
         ...current,
         [form]: {
            ...current[form],
            [field]: true,
         },
      }));
   };

   const resetValidationTouched = (form) => {
      setValidationTouched((current) => ({
         ...current,
         [form]: {},
      }));
   };

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
         description: "Restore active Partner authority after a suspension when continued restriction is no longer justified.",
         warning: "Reinstatement is a new governance decision. The historical suspension remains preserved and existing current memberships remain unchanged.",
         success: "Partnership reinstated.",
         variant: "primary",
      },
   ].filter((action) => action.allowed);

   const selectedAction = governanceActions.find(
      (action) => action.key === confirmationAction,
   );

   const executeGovernanceAction = async () => {
      if (!selectedAction) return;

      const body = selectedAction.key === "suspend"
         ? {
            suspension_type: suspensionForm.suspension_type,
            factors: suspensionForm.factors,
            severity: suspensionForm.severity,
            rationale: suspensionForm.rationale,
            policy_basis: suspensionForm.policy_basis,
            supporting_basis: suspensionForm.supporting_basis,
            supporting_references: parseSupportingReferences(suspensionForm.supporting_references),
            other_factor_explanation: suspensionForm.other_factor_explanation,
            remediation_problem: suspensionForm.remediation_problem,
            remediation_required_action: suspensionForm.remediation_required_action,
            remediation_evidence_required: suspensionForm.remediation_evidence_required,
            remediation_deadline: suspensionForm.remediation_deadline || null,
            remediation_review_method: suspensionForm.remediation_review_method,
            remediation_failure_consequence: suspensionForm.remediation_failure_consequence,
            review_date: suspensionForm.review_date || null,
         }
         : selectedAction.key === "reinstate"
            ? {
               basis: reinstatementForm.basis,
               rationale: reinstatementForm.rationale,
               supporting_basis: reinstatementForm.supporting_basis,
               supporting_references: parseSupportingReferences(reinstatementForm.supporting_references),
               completed_remediation: reinstatementForm.completed_remediation,
               continuing_conditions: reinstatementForm.continuing_conditions,
               monitoring_end_date: reinstatementForm.monitoring_end_date || null,
               monitoring_success_criteria: reinstatementForm.monitoring_success_criteria,
               monitoring_recurrence_consequence: reinstatementForm.monitoring_recurrence_consequence,
            }
            : {};

      const result = await mutate(
         resolveApiEndpoint(selectedAction.endpoint, organization.id),
         { method: "POST", body },
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
         {
            method: "POST",
            body: {
               ending_type: endingForm.ending_type,
               ground: endingForm.ground,
               factors: endingForm.factors,
               severity: endingForm.severity,
               rationale: endingForm.rationale,
               policy_basis: endingForm.policy_basis,
               supporting_basis: endingForm.supporting_basis,
               supporting_references: parseSupportingReferences(endingForm.supporting_references),
               other_factor_explanation: endingForm.other_factor_explanation,
            },
         },
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

   const partnershipFactors = [
      ["VERIFICATION_STANDARDS", "Verification Standards Violation"],
      ["IMPARTIALITY_CONFLICT", "Impartiality or Conflict-of-Interest Violation"],
      ["TRANSPARENCY_MISREPRESENTATION", "Transparency or Misrepresentation Violation"],
      ["CORRECTIONS_ACCOUNTABILITY", "Correction or Accountability Failure"],
      ["PLATFORM_PARTNERSHIP", "Platform or Partnership Policy Violation"],
      ["GOVERNANCE_CAPACITY", "Organizational Governance or Capacity Concern"],
      ["SECURITY_INTEGRITY", "Security, Legal, or Institutional Integrity Risk"],
      ["INACTIVITY_RESPONSIVENESS", "Inactivity or Non-responsiveness"],
      ["OTHER", "Other"],
   ];
   const severityOptions = [
      ["LOW", "Low"],
      ["MODERATE", "Moderate"],
      ["HIGH", "High"],
      ["CRITICAL", "Critical"],
   ];
   const reinstatementBasisOptions = [
      ["REMEDIATION_COMPLETED", "Required Remediation Completed"],
      ["UNDERLYING_RISK_RESOLVED", "Underlying Risk Resolved"],
      ["INVESTIGATION_DID_NOT_JUSTIFY_CONTINUED_SUSPENSION", "Investigation Did Not Justify Continued Suspension"],
      ["OPERATIONAL_REQUIREMENTS_RESTORED", "Operational Requirements Restored"],
      ["CONTINUED_RESTRICTION_NO_LONGER_PROPORTIONATE", "Continued Restriction No Longer Proportionate"],
   ];
   const parseSupportingReferences = (value) => (
      value
         .split("\n")
         .map((reference) => reference.trim())
         .filter(Boolean)
         .slice(0, 10)
   );
   const endingGroundOptions = {
      VOLUNTARY_WITHDRAWAL: [
         ["VOLUNTARY_WITHDRAWAL", "Voluntary Withdrawal"],
      ],
      ADMINISTRATIVE_CONCLUSION: [
         ["PERMANENT_LOSS_ELIGIBILITY", "Permanent Loss of Eligibility or Capacity"],
         ["ORGANIZATION_DISSOLVED", "Organization Dissolved or Ceased Relevant Operations"],
         ["PROLONGED_ABANDONMENT", "Prolonged Inactivity or Partnership Abandonment"],
      ],
      TERMINATION_FOR_CAUSE: [
         ["SEVERE_NON_REMEDIABLE_VIOLATION", "Severe Non-remediable Violation"],
         ["REPEATED_SYSTEMIC_VIOLATIONS", "Repeated or Systemic Serious Violations"],
         ["FAILED_REMEDIATION", "Failed Remediation"],
      ],
   };
   const updateSuspensionForm = (field, value) => {
      setSuspensionForm((current) => {
         if (field === "suspension_type") {
            return {
               ...current,
               suspension_type: value,
               remediation_problem: value === "REMEDIAL" ? current.remediation_problem : "",
               remediation_required_action: value === "REMEDIAL" ? current.remediation_required_action : "",
               remediation_evidence_required: value === "REMEDIAL" ? current.remediation_evidence_required : "",
               remediation_deadline: value === "REMEDIAL" ? current.remediation_deadline : "",
               remediation_review_method: value === "REMEDIAL" ? current.remediation_review_method : "",
               remediation_failure_consequence: value === "REMEDIAL" ? current.remediation_failure_consequence : "",
            };
         }
         return { ...current, [field]: value };
      });
   };
   const updateReinstatementForm = (field, value) => {
      setReinstatementForm((current) => {
         if (field === "basis") {
            return {
               ...current,
               basis: value,
               completed_remediation: value === "REMEDIATION_COMPLETED"
                  ? current.completed_remediation
                  : "",
            };
         }
         if (field === "continuing_conditions" && !value.trim()) {
            return {
               ...current,
               continuing_conditions: value,
               monitoring_end_date: "",
               monitoring_success_criteria: "",
               monitoring_recurrence_consequence: "",
            };
         }
         return { ...current, [field]: value };
      });
   };
   const updateEndingForm = (field, value) => {
      setEndingForm((current) => {
         if (field === "ending_type") {
            return {
               ...current,
               ending_type: value,
               ground: "",
               factors: value === "VOLUNTARY_WITHDRAWAL" ? [] : current.factors,
               severity: value === "TERMINATION_FOR_CAUSE" ? current.severity : "",
            };
         }
         return { ...current, [field]: value };
      });
   };

   const toggleSuspensionFactor = (factor) => {
      setSuspensionForm((current) => {
         const removing = current.factors.includes(factor);
         return {
            ...current,
            factors: removing
               ? current.factors.filter((value) => value !== factor)
               : [...current.factors, factor],
            other_factor_explanation:
               factor === "OTHER" && removing
                  ? ""
                  : current.other_factor_explanation,
         };
      });
   };
   const toggleEndingFactor = (factor) => {
      setEndingForm((current) => {
         const removing = current.factors.includes(factor);
         return {
            ...current,
            factors: removing
               ? current.factors.filter((value) => value !== factor)
               : [...current.factors, factor],
            other_factor_explanation:
               factor === "OTHER" && removing
                  ? ""
                  : current.other_factor_explanation,
         };
      });
   };
   const suspensionHasOther = suspensionForm.factors.includes("OTHER");
   const suspensionRemediationReady = suspensionForm.suspension_type !== "REMEDIAL" || Boolean(
      suspensionForm.remediation_problem.trim()
      && suspensionForm.remediation_required_action.trim()
      && suspensionForm.remediation_evidence_required.trim()
      && suspensionForm.remediation_deadline
      && suspensionForm.remediation_review_method.trim()
      && suspensionForm.remediation_failure_consequence.trim()
   );
   const suspensionReady = Boolean(
      suspensionForm.suspension_type
      && suspensionForm.factors.length
      && suspensionForm.severity
      && suspensionForm.rationale.trim().length >= 20
      && suspensionForm.policy_basis.trim()
      && suspensionForm.supporting_basis.trim()
      && (!suspensionHasOther || suspensionForm.other_factor_explanation.trim())
      && suspensionRemediationReady
      && (suspensionForm.suspension_type !== "PRECAUTIONARY" || suspensionForm.review_date)
   );
   const reinstatementMonitoringReady = !reinstatementForm.continuing_conditions.trim() || Boolean(
      reinstatementForm.monitoring_end_date
      && reinstatementForm.monitoring_success_criteria.trim()
      && reinstatementForm.monitoring_recurrence_consequence.trim()
   );
   const reinstatementReady = Boolean(
      reinstatementForm.basis
      && reinstatementForm.rationale.trim().length >= 20
      && reinstatementForm.supporting_basis.trim()
      && (
         reinstatementForm.basis !== "REMEDIATION_COMPLETED"
         || reinstatementForm.completed_remediation.trim()
      )
      && reinstatementMonitoringReady
   );
   const endingHasOther = endingForm.factors.includes("OTHER");
   const endingReady = Boolean(
      endingForm.ending_type
      && endingForm.ground
      && endingForm.rationale.trim().length >= 20
      && endingForm.policy_basis.trim()
      && endingForm.supporting_basis.trim()
      && (!endingHasOther || endingForm.other_factor_explanation.trim())
      && (
         endingForm.ending_type !== "TERMINATION_FOR_CAUSE"
         || (
            endingForm.factors.length
            && ["HIGH", "CRITICAL"].includes(endingForm.severity)
         )
      )
   );

   const suspensionValidationErrors = {
      suspension_type: suspensionForm.suspension_type ? "" : "Suspension type is required.",
      factors: suspensionForm.factors.length ? "" : "Select at least one suspension factor.",
      severity: suspensionForm.severity ? "" : "Severity is required.",
      rationale: suspensionForm.rationale.trim().length >= 20
         ? ""
         : "Rationale must be at least 20 characters.",
      policy_basis: suspensionForm.policy_basis.trim() ? "" : "Policy basis is required.",
      supporting_basis: suspensionForm.supporting_basis.trim()
         ? ""
         : "Internal supporting basis is required.",
      other_factor_explanation: !suspensionHasOther || suspensionForm.other_factor_explanation.trim()
         ? ""
         : "Explain the underlying standard for the Other factor.",
      remediation_problem: suspensionForm.suspension_type !== "REMEDIAL" || suspensionForm.remediation_problem.trim()
         ? ""
         : "Problem to correct is required for a remedial suspension.",
      remediation_required_action: suspensionForm.suspension_type !== "REMEDIAL" || suspensionForm.remediation_required_action.trim()
         ? ""
         : "Required action is required for a remedial suspension.",
      remediation_evidence_required: suspensionForm.suspension_type !== "REMEDIAL" || suspensionForm.remediation_evidence_required.trim()
         ? ""
         : "Evidence of compliance is required for a remedial suspension.",
      remediation_deadline: suspensionForm.suspension_type !== "REMEDIAL" || suspensionForm.remediation_deadline
         ? ""
         : "Remediation deadline is required for a remedial suspension.",
      remediation_review_method: suspensionForm.suspension_type !== "REMEDIAL" || suspensionForm.remediation_review_method.trim()
         ? ""
         : "Review method is required for a remedial suspension.",
      remediation_failure_consequence: suspensionForm.suspension_type !== "REMEDIAL" || suspensionForm.remediation_failure_consequence.trim()
         ? ""
         : "Consequence if unresolved is required for a remedial suspension.",
      review_date: suspensionForm.suspension_type !== "PRECAUTIONARY" || suspensionForm.review_date
         ? ""
         : "Review date is required for a precautionary suspension.",
   };

   const reinstatementValidationErrors = {
      basis: reinstatementForm.basis ? "" : "Basis for reinstatement is required.",
      rationale: reinstatementForm.rationale.trim().length >= 20
         ? ""
         : "Rationale must be at least 20 characters.",
      supporting_basis: reinstatementForm.supporting_basis.trim()
         ? ""
         : "Internal supporting basis is required.",
      completed_remediation: reinstatementForm.basis !== "REMEDIATION_COMPLETED" || reinstatementForm.completed_remediation.trim()
         ? ""
         : "Completed remediation is required for this reinstatement basis.",
      monitoring_end_date: !reinstatementForm.continuing_conditions.trim() || reinstatementForm.monitoring_end_date
         ? ""
         : "Monitoring end date is required when continuing conditions are set.",
      monitoring_success_criteria: !reinstatementForm.continuing_conditions.trim() || reinstatementForm.monitoring_success_criteria.trim()
         ? ""
         : "Success criteria are required when continuing conditions are set.",
      monitoring_recurrence_consequence: !reinstatementForm.continuing_conditions.trim() || reinstatementForm.monitoring_recurrence_consequence.trim()
         ? ""
         : "A recurrence consequence is required when continuing conditions are set.",
   };

   const endingValidationErrors = {
      ending_type: endingForm.ending_type ? "" : "Ending type is required.",
      ground: endingForm.ground ? "" : "Ground is required.",
      factors: endingForm.ending_type !== "TERMINATION_FOR_CAUSE" || endingForm.factors.length
         ? ""
         : "Select at least one factor for a termination for cause.",
      severity: endingForm.ending_type !== "TERMINATION_FOR_CAUSE" || ["HIGH", "CRITICAL"].includes(endingForm.severity)
         ? ""
         : "Severity must be High or Critical for a termination for cause.",
      rationale: endingForm.rationale.trim().length >= 20
         ? ""
         : "Rationale must be at least 20 characters.",
      policy_basis: endingForm.policy_basis.trim() ? "" : "Policy basis is required.",
      supporting_basis: endingForm.supporting_basis.trim()
         ? ""
         : "Internal supporting basis is required.",
      other_factor_explanation: !endingHasOther || endingForm.other_factor_explanation.trim()
         ? ""
         : "Explain the underlying standard for the Other factor.",
   };

   const visibleValidationErrors = (form, errors) => {
      const touched = validationTouched[form] || {};
      if (!Object.keys(touched).length) return [];
      return [...new Set(Object.values(errors).filter(Boolean))];
   };

   const isTouchedInvalid = (form, field, errors) => Boolean(
      validationTouched[form]?.[field] && errors[field]
   );

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
                           if (action.key === "suspend" || action.key === "reinstate") {
                              resetValidationTouched(action.key);
                           }
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
                     resetValidationTouched("end");
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
            confirmDisabled={
               (selectedAction?.key === "suspend" && !suspensionReady)
               || (selectedAction?.key === "reinstate" && !reinstatementReady)
            }
            processing={pending}
            onConfirm={executeGovernanceAction}
            onClose={() => setConfirmationAction(null)}
         >
            {selectedAction?.key === "suspend" ? (
               <div className="management-governance-form">
                  {visibleValidationErrors("suspend", suspensionValidationErrors).length ? (
                     <ManagementFeedback tone="error">
                        <strong>Complete the required suspension fields.</strong>
                        <ul className="management-validation-summary">
                           {visibleValidationErrors("suspend", suspensionValidationErrors).map((message) => (
                              <li key={message}>{message}</li>
                           ))}
                        </ul>
                     </ManagementFeedback>
                  ) : null}
                  <label className="management-form-field">
                     <span>Suspension type <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <select
                        value={suspensionForm.suspension_type}
                        onChange={(event) => updateSuspensionForm("suspension_type", event.target.value)}
                        disabled={pending}
                        required
                     >
                        <option value="">Select suspension type</option>
                        <option value="REMEDIAL">Remedial Suspension</option>
                        <option value="PRECAUTIONARY">Precautionary Suspension</option>
                        <option value="ADMINISTRATIVE">Administrative Suspension</option>
                     </select>
                  </label>
                  <fieldset className="management-governance-factor-group">
                     <legend>Factor(s) <span className="management-required-indicator" aria-hidden="true">*</span></legend>
                     <p>Select every factor materially relevant to this suspension.</p>
                     <div>
                        {partnershipFactors.map(([value, label]) => (
                           <label key={value}>
                              <input
                                 type="checkbox"
                                 checked={suspensionForm.factors.includes(value)}
                                 onChange={() => toggleSuspensionFactor(value)}
                                 disabled={pending}
                              />
                              <span>{label}</span>
                           </label>
                        ))}
                     </div>
                  </fieldset>
                  {suspensionHasOther ? (
                     <label className="management-form-field">
                        <span>Other factor explanation <span className="management-required-indicator" aria-hidden="true">*</span></span>
                        <textarea
                           value={suspensionForm.other_factor_explanation}
                           onChange={(event) => updateSuspensionForm("other_factor_explanation", event.target.value)}
                           rows={3}
                           disabled={pending}
                           required
                           placeholder="Identify the underlying Partner standard and explain why the established factors do not fit."
                        />
                     </label>
                  ) : null}
                  <label className="management-form-field">
                     <span>Severity <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <select
                        value={suspensionForm.severity}
                        onChange={(event) => updateSuspensionForm("severity", event.target.value)}
                        disabled={pending}
                        required
                     >
                        <option value="">Select severity</option>
                        {severityOptions.map(([value, label]) => (
                           <option key={value} value={value}>{label}</option>
                        ))}
                     </select>
                  </label>
                  <label className={`management-form-field${isTouchedInvalid("suspend", "rationale", suspensionValidationErrors) ? " management-form-field--invalid" : ""}`}>
                     <span>Rationale <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <textarea
                        value={suspensionForm.rationale}
                        onChange={(event) => updateSuspensionForm("rationale", event.target.value)}
                        onBlur={() => markValidationTouched("suspend", "rationale")}
                        rows={4}
                        disabled={pending}
                        required
                        minLength={20}
                        aria-invalid={isTouchedInvalid("suspend", "rationale", suspensionValidationErrors)}
                        aria-describedby={isTouchedInvalid("suspend", "rationale", suspensionValidationErrors) ? "suspension-rationale-error" : undefined}
                        placeholder="Describe the material facts and context supporting this suspension."
                     />
                     <FieldError id="suspension-rationale-error">
                        {isTouchedInvalid("suspend", "rationale", suspensionValidationErrors)
                           ? suspensionValidationErrors.rationale
                           : ""}
                     </FieldError>
                  </label>
                  <label className="management-form-field">
                     <span>Policy basis <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <Input
                        value={suspensionForm.policy_basis}
                        onChange={(event) => updateSuspensionForm("policy_basis", event.target.value)}
                        disabled={pending}
                        required
                        placeholder="e.g. Partnership Enforcement Policy §13.1"
                     />
                  </label>
                  <label className="management-form-field">
                     <span>Internal supporting basis <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <textarea
                        value={suspensionForm.supporting_basis}
                        onChange={(event) => updateSuspensionForm("supporting_basis", event.target.value)}
                        rows={3}
                        disabled={pending}
                        required
                        placeholder="Internal evidence or records supporting the decision. This is not shown to the organization."
                     />
                     <small>Internal Platform Governance only.</small>
                  </label>
                  <label className="management-form-field">
                     <span>Supporting references (optional)</span>
                     <textarea
                        value={suspensionForm.supporting_references}
                        onChange={(event) => updateSuspensionForm("supporting_references", event.target.value)}
                        rows={2}
                        disabled={pending}
                        placeholder="One internal reference per line, up to 10."
                     />
                  </label>
                  {suspensionForm.suspension_type === "REMEDIAL" ? (
                     <div className="management-governance-form">
                        <strong>Remediation plan</strong>
                        <p className="management-section__description">
                           Record a clear path the organization can follow toward compliance and reinstatement review.
                        </p>
                        <label className="management-form-field">
                           <span>Problem to correct <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={suspensionForm.remediation_problem}
                              onChange={(event) => updateSuspensionForm("remediation_problem", event.target.value)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className="management-form-field">
                           <span>Required action <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={suspensionForm.remediation_required_action}
                              onChange={(event) => updateSuspensionForm("remediation_required_action", event.target.value)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className="management-form-field">
                           <span>Evidence of compliance <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={suspensionForm.remediation_evidence_required}
                              onChange={(event) => updateSuspensionForm("remediation_evidence_required", event.target.value)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className="management-form-field">
                           <span>Remediation deadline <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <Input
                              type="date"
                              value={suspensionForm.remediation_deadline}
                              onChange={(event) => updateSuspensionForm("remediation_deadline", event.target.value)}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className="management-form-field">
                           <span>Review method <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={suspensionForm.remediation_review_method}
                              onChange={(event) => updateSuspensionForm("remediation_review_method", event.target.value)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className="management-form-field">
                           <span>Consequence if unresolved <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={suspensionForm.remediation_failure_consequence}
                              onChange={(event) => updateSuspensionForm("remediation_failure_consequence", event.target.value)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                     </div>
                  ) : null}
                  <label className="management-form-field">
                     <span>
                        Review date{suspensionForm.suspension_type === "PRECAUTIONARY" ? (
                           <> <span className="management-required-indicator" aria-hidden="true">*</span></>
                        ) : " (optional)"}
                     </span>
                     <Input
                        type="date"
                        value={suspensionForm.review_date}
                        onChange={(event) => updateSuspensionForm("review_date", event.target.value)}
                        disabled={pending}
                        required={suspensionForm.suspension_type === "PRECAUTIONARY"}
                     />
                  </label>
               </div>
            ) : selectedAction?.key === "reinstate" ? (
               <div className="management-governance-form">
                  {visibleValidationErrors("reinstate", reinstatementValidationErrors).length ? (
                     <ManagementFeedback tone="error">
                        <strong>Complete the required reinstatement fields.</strong>
                        <ul className="management-validation-summary">
                           {visibleValidationErrors("reinstate", reinstatementValidationErrors).map((message) => (
                              <li key={message}>{message}</li>
                           ))}
                        </ul>
                     </ManagementFeedback>
                  ) : null}
                  <label className={`management-form-field${isTouchedInvalid("reinstate", "basis", reinstatementValidationErrors) ? " management-form-field--invalid" : ""}`}>
                     <span>Basis for reinstatement <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <select
                        value={reinstatementForm.basis}
                        onChange={(event) => {
                           updateReinstatementForm("basis", event.target.value);
                           markValidationTouched("reinstate", "basis");
                        }}
                        disabled={pending}
                        required
                        aria-invalid={isTouchedInvalid("reinstate", "basis", reinstatementValidationErrors)}
                     >
                        <option value="">Select reinstatement basis</option>
                        {reinstatementBasisOptions.map(([value, label]) => (
                           <option key={value} value={value}>{label}</option>
                        ))}
                     </select>
                     <FieldError id="reinstatement-basis-error">
                        {isTouchedInvalid("reinstate", "basis", reinstatementValidationErrors)
                           ? reinstatementValidationErrors.basis
                           : ""}
                     </FieldError>
                  </label>
                  <label className={`management-form-field${isTouchedInvalid("reinstate", "rationale", reinstatementValidationErrors) ? " management-form-field--invalid" : ""}`}>
                     <span>Rationale <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <textarea
                        value={reinstatementForm.rationale}
                        onChange={(event) => updateReinstatementForm("rationale", event.target.value)}
                        onBlur={() => markValidationTouched("reinstate", "rationale")}
                        rows={4}
                        disabled={pending}
                        required
                        minLength={20}
                        aria-invalid={isTouchedInvalid("reinstate", "rationale", reinstatementValidationErrors)}
                        aria-describedby={isTouchedInvalid("reinstate", "rationale", reinstatementValidationErrors) ? "reinstatement-rationale-error" : undefined}
                        placeholder="Explain why continued suspension is no longer justified."
                     />
                     <FieldError id="reinstatement-rationale-error">
                        {isTouchedInvalid("reinstate", "rationale", reinstatementValidationErrors)
                           ? reinstatementValidationErrors.rationale
                           : ""}
                     </FieldError>
                  </label>
                  {reinstatementForm.basis === "REMEDIATION_COMPLETED" ? (
                     <label className={`management-form-field${isTouchedInvalid("reinstate", "completed_remediation", reinstatementValidationErrors) ? " management-form-field--invalid" : ""}`}>
                        <span>Completed remediation <span className="management-required-indicator" aria-hidden="true">*</span></span>
                        <textarea
                           value={reinstatementForm.completed_remediation}
                           onChange={(event) => updateReinstatementForm("completed_remediation", event.target.value)}
                           onBlur={() => markValidationTouched("reinstate", "completed_remediation")}
                           rows={3}
                           disabled={pending}
                           required
                           aria-invalid={isTouchedInvalid("reinstate", "completed_remediation", reinstatementValidationErrors)}
                           placeholder="Describe the remediation completed and accepted by TruthLens."
                        />
                     </label>
                  ) : null}
                  <label className={`management-form-field${isTouchedInvalid("reinstate", "supporting_basis", reinstatementValidationErrors) ? " management-form-field--invalid" : ""}`}>
                     <span>Internal supporting basis <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <textarea
                        value={reinstatementForm.supporting_basis}
                        onChange={(event) => updateReinstatementForm("supporting_basis", event.target.value)}
                        onBlur={() => markValidationTouched("reinstate", "supporting_basis")}
                        rows={3}
                        disabled={pending}
                        required
                        aria-invalid={isTouchedInvalid("reinstate", "supporting_basis", reinstatementValidationErrors)}
                        placeholder="Internal evidence supporting reinstatement. This is not shown to the organization."
                     />
                     <small>Internal Platform Governance only.</small>
                  </label>
                  <label className="management-form-field">
                     <span>Supporting references (optional)</span>
                     <textarea
                        value={reinstatementForm.supporting_references}
                        onChange={(event) => updateReinstatementForm("supporting_references", event.target.value)}
                        rows={2}
                        disabled={pending}
                        placeholder="One internal reference per line, up to 10."
                     />
                  </label>
                  <label className="management-form-field">
                     <span>Continuing conditions (optional)</span>
                     <textarea
                        value={reinstatementForm.continuing_conditions}
                        onChange={(event) => updateReinstatementForm("continuing_conditions", event.target.value)}
                        rows={3}
                        disabled={pending}
                        placeholder="Leave blank when no formal monitoring conditions apply."
                     />
                  </label>
                  {reinstatementForm.continuing_conditions.trim() ? (
                     <>
                        <label className="management-form-field">
                           <span>Monitoring end date <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <Input
                              type="date"
                              value={reinstatementForm.monitoring_end_date}
                              onChange={(event) => updateReinstatementForm("monitoring_end_date", event.target.value)}
                              onBlur={() => markValidationTouched("reinstate", "monitoring_end_date")}
                              invalid={isTouchedInvalid("reinstate", "monitoring_end_date", reinstatementValidationErrors)}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className={`management-form-field${isTouchedInvalid("reinstate", "monitoring_success_criteria", reinstatementValidationErrors) ? " management-form-field--invalid" : ""}`}>
                           <span>Success criteria <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={reinstatementForm.monitoring_success_criteria}
                              onChange={(event) => updateReinstatementForm("monitoring_success_criteria", event.target.value)}
                              onBlur={() => markValidationTouched("reinstate", "monitoring_success_criteria")}
                              aria-invalid={isTouchedInvalid("reinstate", "monitoring_success_criteria", reinstatementValidationErrors)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                        <label className={`management-form-field${isTouchedInvalid("reinstate", "monitoring_recurrence_consequence", reinstatementValidationErrors) ? " management-form-field--invalid" : ""}`}>
                           <span>Consequence if the serious issue recurs <span className="management-required-indicator" aria-hidden="true">*</span></span>
                           <textarea
                              value={reinstatementForm.monitoring_recurrence_consequence}
                              onChange={(event) => updateReinstatementForm("monitoring_recurrence_consequence", event.target.value)}
                              onBlur={() => markValidationTouched("reinstate", "monitoring_recurrence_consequence")}
                              aria-invalid={isTouchedInvalid("reinstate", "monitoring_recurrence_consequence", reinstatementValidationErrors)}
                              rows={2}
                              disabled={pending}
                              required
                           />
                        </label>
                     </>
                  ) : null}
               </div>
            ) : null}
         </ManagementConfirmDialog>
         <ManagementConfirmDialog
            open={endConfirmationOpen}
            title="End this Partner Organization’s partnership?"
            description="Historical verification records and published work will not be deleted. Record why the active partnership is ending."
            warning={endImpactSummary}
            error={error?.message}
            confirmLabel="End partnership"
            confirmVariant="destructive"
            confirmDisabled={!endingReady}
            processing={pending}
            onConfirm={endPartnership}
            onClose={() => setEndConfirmationOpen(false)}
         >
            <div className="management-governance-form">
               {visibleValidationErrors("end", endingValidationErrors).length ? (
                  <ManagementFeedback tone="error">
                     <strong>Complete the required partnership-ending fields.</strong>
                     <ul className="management-validation-summary">
                        {visibleValidationErrors("end", endingValidationErrors).map((message) => (
                           <li key={message}>{message}</li>
                        ))}
                     </ul>
                  </ManagementFeedback>
               ) : null}
               <label className="management-form-field">
                  <span>Ending type <span className="management-required-indicator" aria-hidden="true">*</span></span>
                  <select
                     value={endingForm.ending_type}
                     onChange={(event) => updateEndingForm("ending_type", event.target.value)}
                     disabled={pending}
                     required
                  >
                     <option value="">Select ending type</option>
                     <option value="VOLUNTARY_WITHDRAWAL">Voluntary Withdrawal</option>
                     <option value="ADMINISTRATIVE_CONCLUSION">Administrative Conclusion</option>
                     <option value="TERMINATION_FOR_CAUSE">Termination for Cause</option>
                  </select>
               </label>
               <label className="management-form-field">
                  <span>Ground <span className="management-required-indicator" aria-hidden="true">*</span></span>
                  <select
                     value={endingForm.ground}
                     onChange={(event) => updateEndingForm("ground", event.target.value)}
                     disabled={pending || !endingForm.ending_type}
                     required
                  >
                     <option value="">Select ground</option>
                     {(endingGroundOptions[endingForm.ending_type] || []).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                     ))}
                  </select>
               </label>
               {endingForm.ending_type !== "VOLUNTARY_WITHDRAWAL" ? (
                  <fieldset className="management-governance-factor-group">
                     <legend>
                        {endingForm.ending_type === "TERMINATION_FOR_CAUSE" ? (
                           <>Factor(s) <span className="management-required-indicator" aria-hidden="true">*</span></>
                        ) : "Related factor(s) (optional)"}
                     </legend>
                     <p>
                        {endingForm.ending_type === "TERMINATION_FOR_CAUSE"
                           ? "Select every factor materially relevant to this termination."
                           : "Select factors only when they help explain the administrative conclusion."}
                     </p>
                     <div>
                        {partnershipFactors.map(([value, label]) => (
                           <label key={value}>
                              <input
                                 type="checkbox"
                                 checked={endingForm.factors.includes(value)}
                                 onChange={() => toggleEndingFactor(value)}
                                 disabled={pending}
                              />
                              <span>{label}</span>
                           </label>
                        ))}
                     </div>
                  </fieldset>
               ) : null}
               {endingForm.ending_type === "TERMINATION_FOR_CAUSE" ? (
                  <label className="management-form-field">
                     <span>Severity <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <select
                        value={endingForm.severity}
                        onChange={(event) => updateEndingForm("severity", event.target.value)}
                        disabled={pending}
                        required
                     >
                        <option value="">Select severity</option>
                        <option value="HIGH">High</option>
                        <option value="CRITICAL">Critical</option>
                     </select>
                  </label>
               ) : null}
               {endingHasOther ? (
                  <label className="management-form-field">
                     <span>Other factor explanation <span className="management-required-indicator" aria-hidden="true">*</span></span>
                     <textarea
                        value={endingForm.other_factor_explanation}
                        onChange={(event) => updateEndingForm("other_factor_explanation", event.target.value)}
                        rows={3}
                        disabled={pending}
                        required
                        placeholder="Identify the underlying Partner standard and explain why the established factors do not fit."
                     />
                  </label>
               ) : null}
               <label className={`management-form-field${isTouchedInvalid("end", "rationale", endingValidationErrors) ? " management-form-field--invalid" : ""}`}>
                  <span>Rationale <span className="management-required-indicator" aria-hidden="true">*</span></span>
                  <textarea
                     value={endingForm.rationale}
                     onChange={(event) => updateEndingForm("rationale", event.target.value)}
                     onBlur={() => markValidationTouched("end", "rationale")}
                     rows={4}
                     disabled={pending}
                     required
                     minLength={20}
                     aria-invalid={isTouchedInvalid("end", "rationale", endingValidationErrors)}
                     aria-describedby={isTouchedInvalid("end", "rationale", endingValidationErrors) ? "ending-rationale-error" : undefined}
                     placeholder="Describe the material facts supporting the conclusion of this partnership."
                  />
                  <FieldError id="ending-rationale-error">
                     {isTouchedInvalid("end", "rationale", endingValidationErrors)
                        ? endingValidationErrors.rationale
                        : ""}
                  </FieldError>
               </label>
               <label className="management-form-field">
                  <span>Policy basis <span className="management-required-indicator" aria-hidden="true">*</span></span>
                  <Input
                     value={endingForm.policy_basis}
                     onChange={(event) => updateEndingForm("policy_basis", event.target.value)}
                     disabled={pending}
                     required
                     placeholder="e.g. Partnership Enforcement Policy §19.3"
                  />
               </label>
               <label className="management-form-field">
                  <span>Internal supporting basis <span className="management-required-indicator" aria-hidden="true">*</span></span>
                  <textarea
                     value={endingForm.supporting_basis}
                     onChange={(event) => updateEndingForm("supporting_basis", event.target.value)}
                     rows={3}
                     disabled={pending}
                     required
                     placeholder="Internal evidence or records supporting the decision. This is not shown to the organization."
                  />
                  <small>Internal Platform Governance only.</small>
               </label>
               <label className="management-form-field">
                  <span>Supporting references (optional)</span>
                  <textarea
                     value={endingForm.supporting_references}
                     onChange={(event) => updateEndingForm("supporting_references", event.target.value)}
                     rows={2}
                     disabled={pending}
                     placeholder="One internal reference per line, up to 10."
                  />
               </label>
            </div>
         </ManagementConfirmDialog>
      </section>
   );
}



function GovernanceReconsiderationCard({
   organizationId,
   reconsideration,
   onRefresh,
   onFeedback,
}) {
   const [independenceNote, setIndependenceNote] = useState("");
   const [overrideRationale, setOverrideRationale] = useState("");
   const [outcome, setOutcome] = useState("UPHELD");
   const [resolutionRationale, setResolutionRationale] = useState("");
   const [internalBasis, setInternalBasis] = useState("");
   const { mutate, pending, error, reset } = useManagementMutation();

   const startReview = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint(
            "MANAGEMENT_GOVERNANCE_RECONSIDERATION_REVIEW",
            organizationId,
            reconsideration.id,
         ),
         {
            method: "POST",
            body: {
               reviewer_independence_note: independenceNote.trim(),
               independence_override_rationale: overrideRationale.trim(),
            },
         },
      );
      if (!result.ok) return;
      onFeedback("Reconsideration review started.");
      onRefresh();
   };

   const resolveReview = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint(
            "MANAGEMENT_GOVERNANCE_RECONSIDERATION_RESOLVE",
            organizationId,
            reconsideration.id,
         ),
         {
            method: "POST",
            body: {
               outcome,
               resolution_rationale: resolutionRationale.trim(),
               internal_supporting_basis: internalBasis.trim(),
            },
         },
      );
      if (!result.ok) return;
      onFeedback(
         outcome === "REVOKED"
            ? "Reconsideration resolved and the suspension was revoked through governed reinstatement."
            : "Reconsideration resolved and the suspension was upheld.",
      );
      onRefresh();
   };

   return (
      <article className="management-governance-action">
         <div>
            <div className="management-section__title-row">
               <div>
                  <strong>Suspension reconsideration</strong>
                  <p>
                     Target suspension event: {reconsideration.suspension_event_id}
                  </p>
               </div>
               <ManagementStatus value={reconsideration.status} />
            </div>
            <DetailList items={[
               { label: "Requested by", value: reconsideration.requested_by || "Historical user" },
               { label: "Grounds", value: reconsideration.grounds?.join(", ") || "Not recorded" },
               { label: "Organization statement", value: reconsideration.request_statement },
               { label: "Original decision-maker", value: reconsideration.original_decision_maker || "Not recorded" },
               { label: "Reviewer", value: reconsideration.reviewer || "Not assigned" },
               { label: "Outcome", value: reconsideration.outcome || "Pending" },
               reconsideration.resolution_rationale
                  ? { label: "Organization-facing resolution", value: reconsideration.resolution_rationale }
                  : null,
            ].filter(Boolean)} />

            {reconsideration.status === "SUBMITTED" ? (
               <form className="management-governance-form" onSubmit={startReview}>
                  <strong>Begin review</strong>
                  <p className="management-section__description">
                     Use an independent Platform Admin where practicable. If the original decision-maker must self-review, the backend enforces the required independence record.
                  </p>
                  <label className="management-form-field">
                     <span>Reviewer independence note (optional unless required)</span>
                     <textarea
                        rows={3}
                        value={independenceNote}
                        onChange={(event) => {
                           reset();
                           setIndependenceNote(event.target.value);
                        }}
                        disabled={pending}
                        placeholder="Record how reviewer independence is satisfied, or why independent review is unavailable."
                     />
                     <FieldError id={`reconsideration-independence-${reconsideration.id}`}>
                        {error?.fields.reviewer_independence_note}
                     </FieldError>
                  </label>
                  <label className="management-form-field">
                     <span>Self-review override rationale (only when necessary)</span>
                     <textarea
                        rows={3}
                        value={overrideRationale}
                        onChange={(event) => {
                           reset();
                           setOverrideRationale(event.target.value);
                        }}
                        disabled={pending}
                        placeholder="Required only when the original decision-maker reviews despite another active Platform Admin being available."
                     />
                     <FieldError id={`reconsideration-override-${reconsideration.id}`}>
                        {error?.fields.independence_override_rationale}
                     </FieldError>
                  </label>
                  <Button type="submit" loading={pending} loadingLabel="Starting review…">
                     Start review
                  </Button>
               </form>
            ) : null}

            {reconsideration.status === "UNDER_REVIEW" ? (
               <form className="management-governance-form" onSubmit={resolveReview}>
                  <strong>Resolve review</strong>
                  <label className="management-form-field">
                     <span>Outcome</span>
                     <select
                        value={outcome}
                        onChange={(event) => setOutcome(event.target.value)}
                        disabled={pending}
                     >
                        <option value="UPHELD">Upheld</option>
                        <option value="REVOKED">Revoked</option>
                     </select>
                  </label>
                  <label className="management-form-field">
                     <span>Organization-facing resolution rationale</span>
                     <textarea
                        rows={4}
                        value={resolutionRationale}
                        onChange={(event) => {
                           reset();
                           setResolutionRationale(event.target.value);
                        }}
                        disabled={pending}
                        required
                        minLength={20}
                        placeholder="Explain why the suspension is upheld or revoked."
                     />
                  </label>
                  <label className="management-form-field">
                     <span>Internal supporting basis</span>
                     <textarea
                        rows={4}
                        value={internalBasis}
                        onChange={(event) => {
                           reset();
                           setInternalBasis(event.target.value);
                        }}
                        disabled={pending}
                        required
                        minLength={20}
                        placeholder="Internal evidence supporting the reconsideration outcome. This is not shown to the organization."
                     />
                     <small>Internal Platform Governance only.</small>
                  </label>
                  <Button
                     type="submit"
                     variant={outcome === "REVOKED" ? "primary" : "secondary"}
                     loading={pending}
                     loadingLabel="Resolving…"
                     disabled={
                        resolutionRationale.trim().length < 20
                        || internalBasis.trim().length < 20
                     }
                  >
                     Resolve reconsideration
                  </Button>
               </form>
            ) : null}

            {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
         </div>
      </article>
   );
}

function GovernanceReconsiderationSection({
   organization,
   onRefresh,
   onFeedback,
}) {
   const reconsiderations = organization.governance_reconsiderations || [];
   if (!reconsiderations.length) return null;

   return (
      <section className="management-detail-section">
         <h2>Suspension reconsideration</h2>
         <p className="management-section__description">
            Organization-requested review of a suspension. Submission never restores professional authority; only a revoked outcome uses the governed reinstatement transition.
         </p>
         <div className="management-governance-correction-list">
            {reconsiderations.map((reconsideration) => (
               <GovernanceReconsiderationCard
                  key={reconsideration.id}
                  organizationId={organization.id}
                  reconsideration={reconsideration}
                  onRefresh={onRefresh}
                  onFeedback={onFeedback}
               />
            ))}
         </div>
      </section>
   );
}

function GovernanceContactSection({
   organization,
   onRefresh,
   onFeedback,
}) {
   const delivery = organization.governance_notice_delivery || {};
   const fallback = delivery.fallback;
   const [editing, setEditing] = useState(false);
   const [email, setEmail] = useState(organization.governance_contact_email || "");
   const [outOfBandOpen, setOutOfBandOpen] = useState(false);
   const [outOfBandMethod, setOutOfBandMethod] = useState("");
   const [outOfBandDetails, setOutOfBandDetails] = useState("");
   const { mutate, pending, error, reset } = useManagementMutation();

   const saveContact = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATION_GOVERNANCE_CONTACT", organization.id),
         {
            method: "PATCH",
            body: { governance_contact_email: email.trim() },
         },
      );
      if (!result.ok) return;

      setEditing(false);
      onFeedback(
         email.trim()
            ? "Private governance contact updated."
            : "Private governance contact cleared.",
      );
      onRefresh();
   };

   const recordOutOfBand = async (event) => {
      event.preventDefault();
      if (!fallback?.id) return;

      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATION_GOVERNANCE_OUT_OF_BAND", organization.id),
         {
            method: "POST",
            body: {
               fallback_delivery_id: fallback.id,
               method: outOfBandMethod.trim(),
               details: outOfBandDetails.trim(),
            },
         },
      );
      if (!result.ok) return;

      setOutOfBandOpen(false);
      setOutOfBandMethod("");
      setOutOfBandDetails("");
      onFeedback("Out-of-band governance notice recorded.");
      onRefresh();
   };

   const retryDelivery = async () => {
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATION_GOVERNANCE_NOTICE_RETRY", organization.id),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;
      onFeedback(result.data.detail || "Governance notice delivery completed.");
      onRefresh();
   };

   const fallbackStatusLabels = {
      PENDING: "Pending",
      SENT: "Sent",
      FAILED: "Failed",
      NOT_DELIVERABLE: "Not deliverable",
      OUT_OF_BAND_RECORDED: "Out-of-band notice recorded",
   };
   const canRecordOutOfBand = fallback
      && ["NOT_DELIVERABLE", "FAILED"].includes(fallback.status);

   return (
      <section className="management-detail-section">
         <div className="management-section__title-row">
            <div>
               <h2>Governance contact and notice delivery</h2>
               <p className="management-section__description">
                  This private contact is used only when no active Organization Admin can receive a secure governance notice. It is never shown on the public organization profile.
               </p>
            </div>
         </div>

         {delivery.no_active_admin ? (
            <ManagementFeedback tone="error">
               No active Organization Admin is currently available to receive a detailed secure governance notice.
               {organization.governance_contact_email
                  ? " TruthLens will use the private governance contact for a minimal fallback alert."
                  : " Configure a private governance contact or record any out-of-band notice after the governance action."}
            </ManagementFeedback>
         ) : null}

         {!editing ? (
            <>
               <DetailList items={[
                  {
                     label: "Private governance contact",
                     value: organization.governance_contact_email || "Not configured",
                  },
                  {
                     label: "Latest fallback delivery",
                     value: fallback
                        ? (fallbackStatusLabels[fallback.status] || fallback.status)
                        : "Not required",
                  },
                  fallback?.contact_email
                     ? { label: "Fallback address used", value: fallback.contact_email }
                     : null,
                  fallback?.recorded_at
                     ? {
                        label: "Out-of-band notice recorded",
                        node: formatManagementDate(fallback.recorded_at),
                     }
                     : null,
               ].filter(Boolean)} />
               <div className="management-inline-actions">
                  <Button
                     variant="secondary"
                     disabled={pending}
                     onClick={() => {
                        reset();
                        setEmail(organization.governance_contact_email || "");
                        setEditing(true);
                     }}
                  >
                     Edit private governance contact
                  </Button>
                  {delivery.retry_available || fallback?.status === "FAILED" || fallback?.status === "PENDING" ? (
                     <Button
                        variant="secondary"
                        disabled={pending}
                        onClick={retryDelivery}
                     >
                        Retry notice delivery
                     </Button>
                  ) : null}
                  {canRecordOutOfBand ? (
                     <Button
                        variant="secondary"
                        disabled={pending}
                        onClick={() => {
                           reset();
                           setOutOfBandOpen(true);
                        }}
                     >
                        Record out-of-band notice
                     </Button>
                  ) : null}
               </div>
            </>
         ) : (
            <form className="management-provision-form" onSubmit={saveContact}>
               <label className="management-form-field">
                  <span>Private governance contact email</span>
                  <Input
                     type="email"
                     value={email}
                     onChange={(event) => {
                        reset();
                        setEmail(event.target.value);
                     }}
                     invalid={Boolean(error?.fields.governance_contact_email)}
                     disabled={pending}
                     autoComplete="email"
                     placeholder="governance@example.org"
                  />
                  <small>
                     Leave blank only when the organization has no suitable fallback address.
                  </small>
                  <FieldError id="governance-contact-email-error">
                     {error?.fields.governance_contact_email}
                  </FieldError>
               </label>
               <div className="management-inline-actions">
                  <Button
                     variant="secondary"
                     disabled={pending}
                     onClick={() => {
                        reset();
                        setEmail(organization.governance_contact_email || "");
                        setEditing(false);
                     }}
                  >
                     Cancel
                  </Button>
                  <Button type="submit" loading={pending} loadingLabel="Saving…">
                     Save contact
                  </Button>
               </div>
            </form>
         )}

         {outOfBandOpen && fallback ? (
            <form className="management-provision-form" onSubmit={recordOutOfBand}>
               <div className="management-provision-form__intro">
                  <strong>Record out-of-band governance notice</strong>
                  <p>
                     Use this only to document a real communication that occurred outside TruthLens. It does not change the governance decision itself.
                  </p>
               </div>
               <label className="management-form-field">
                  <span>Method</span>
                  <Input
                     value={outOfBandMethod}
                     onChange={(event) => {
                        reset();
                        setOutOfBandMethod(event.target.value);
                     }}
                     disabled={pending}
                     required
                     placeholder="e.g. Official organization email"
                  />
               </label>
               <label className="management-form-field">
                  <span>Details</span>
                  <textarea
                     value={outOfBandDetails}
                     onChange={(event) => {
                        reset();
                        setOutOfBandDetails(event.target.value);
                     }}
                     rows={3}
                     disabled={pending}
                     required
                     placeholder="Record when and how the organization was informed. Do not place confidential supporting evidence here."
                  />
               </label>
               <div className="management-inline-actions">
                  <Button
                     variant="secondary"
                     disabled={pending}
                     onClick={() => {
                        reset();
                        setOutOfBandOpen(false);
                        setOutOfBandMethod("");
                        setOutOfBandDetails("");
                     }}
                  >
                     Cancel
                  </Button>
                  <Button type="submit" loading={pending} loadingLabel="Recording…">
                     Record notice
                  </Button>
               </div>
            </form>
         ) : null}

         {fallback?.last_error ? (
            <ManagementFeedback tone="error">
               {fallback.last_error}
            </ManagementFeedback>
         ) : null}
         {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}
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
                  <GovernanceContactSection
                     organization={data}
                     onRefresh={retry}
                     onFeedback={showFeedback}
                  />
                  <GovernanceReconsiderationSection
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
