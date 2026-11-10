import { formatManagementAuditValue } from "../../utils/management";

const STATE_FIELDS = [
   ["name", "Organization name"],
   ["slug", "Slug"],
   ["organization_type", "Organization type"],
   ["verification_status", "Verification status"],
   ["partner_status", "Partner status"],
   ["status", "Invitation status"],
   ["invitation_purpose", "Invitation purpose"],
   ["invited_role", "Invited role"],
   ["send_count", "Delivery count"],
];

const CONTEXT_FIELDS = [
   ["source", "Source"],
   ["request_source", "Request source"],
   ["operation", "Operation"],
   ["delivery_status", "Delivery status"],
   ["transition", "Lifecycle transition"],
];

const GOVERNANCE_FIELD_LABELS = {
   suspension_type: "Suspension type",
   ending_type: "Ending type",
   ground: "Ending ground",
   factors: "Factor(s)",
   severity: "Severity",
   policy_basis: "Policy basis",
   required_remediation: "Required remediation",
   review_date: "Review date",
};

const GOVERNANCE_VALUE_LABELS = {
   REMEDIAL: "Remedial Suspension",
   PRECAUTIONARY: "Precautionary Suspension",
   ADMINISTRATIVE: "Administrative Suspension",
   VOLUNTARY_WITHDRAWAL: "Voluntary Withdrawal",
   ADMINISTRATIVE_CONCLUSION: "Administrative Conclusion",
   TERMINATION_FOR_CAUSE: "Termination for Cause",
   PERMANENT_LOSS_ELIGIBILITY: "Permanent Loss of Eligibility or Capacity",
   ORGANIZATION_DISSOLVED: "Organization Dissolved or Ceased Relevant Operations",
   PROLONGED_ABANDONMENT: "Prolonged Inactivity or Partnership Abandonment",
   SEVERE_NON_REMEDIABLE_VIOLATION: "Severe Non-remediable Violation",
   REPEATED_SYSTEMIC_VIOLATIONS: "Repeated or Systemic Serious Violations",
   FAILED_REMEDIATION: "Failed Remediation",
   VERIFICATION_STANDARDS: "Verification Standards Violation",
   IMPARTIALITY_CONFLICT: "Impartiality or Conflict-of-Interest Violation",
   TRANSPARENCY_MISREPRESENTATION: "Transparency or Misrepresentation Violation",
   CORRECTIONS_ACCOUNTABILITY: "Correction or Accountability Failure",
   PLATFORM_PARTNERSHIP: "Platform or Partnership Policy Violation",
   GOVERNANCE_CAPACITY: "Organizational Governance or Capacity Concern",
   SECURITY_INTEGRITY: "Security, Legal, or Institutional Integrity Risk",
   INACTIVITY_RESPONSIVENESS: "Inactivity or Non-responsiveness",
   OTHER: "Other",
   LOW: "Low",
   MODERATE: "Moderate",
   HIGH: "High",
   CRITICAL: "Critical",
};

function formatGovernanceValue(value) {
   if (Array.isArray(value)) {
      return value.length
         ? value.map((entry) => GOVERNANCE_VALUE_LABELS[entry] || entry).join(", ")
         : "None";
   }
   if (value === null || value === undefined || value === "") return "Not set";
   return GOVERNANCE_VALUE_LABELS[value] || String(value);
}

const CREATION_ACTIONS = new Set([
   "ORGANIZATION_CREATED",
   "ORGANIZATION_INVITATION_CREATED",
]);

const UPDATE_ACTIONS = new Set([
   "ORGANIZATION_PLATFORM_TRUST_UPDATED",
   "ORGANIZATION_INVITATION_RESENT",
   "ORGANIZATION_INVITATION_CANCELLED",
]);

function valuesMatch(previousValue, newValue) {
   return JSON.stringify(previousValue) === JSON.stringify(newValue);
}

export function ManagementAuditStateTransition({
   actionType,
   previousState = {},
   newState = {},
}) {
   const fields = STATE_FIELDS.filter(([key]) => {
      const hasPreviousValue = Object.hasOwn(previousState, key);
      const hasNewValue = Object.hasOwn(newState, key);

      if (CREATION_ACTIONS.has(actionType)) {
         return hasNewValue && !valuesMatch(previousState[key], newState[key]);
      }

      if (UPDATE_ACTIONS.has(actionType)) {
         return hasPreviousValue
            && hasNewValue
            && !valuesMatch(previousState[key], newState[key]);
      }

      return (hasPreviousValue || hasNewValue)
         && !valuesMatch(previousState[key], newState[key]);
   });

   if (!fields.length) {
      return (
         <p className="management-empty-value">
            This event does not contain a displayable state change.
         </p>
      );
   }

   return (
      <div className="management-audit-transition" role="table" aria-label="State changes">
         <div className="management-audit-transition__header" role="row">
            <span role="columnheader">Field</span>
            <span role="columnheader">Before</span>
            <span role="columnheader">After</span>
         </div>
         {fields.map(([key, label]) => (
            <div className="management-audit-transition__row" role="row" key={key}>
               <strong role="rowheader">{label}</strong>
               <div role="cell">
                  <span>Before</span>
                  {formatManagementAuditValue(previousState[key])}
               </div>
               <div role="cell">
                  <span>After</span>
                  {formatManagementAuditValue(newState[key])}
               </div>
            </div>
         ))}
      </div>
   );
}

export function ManagementAuditSecondaryContext({ notes, context = {} }) {
   const contextEntries = CONTEXT_FIELDS.filter(([key]) => Object.hasOwn(context, key));
   const governance = (
      context.governance
      && typeof context.governance === "object"
      && !Array.isArray(context.governance)
   ) ? context.governance : null;
   const governanceEntries = governance
      ? Object.entries(GOVERNANCE_FIELD_LABELS)
         .filter(([key]) => Object.hasOwn(governance, key))
      : [];
   if (!notes && !contextEntries.length && !governanceEntries.length) return null;

   return (
      <details className="management-audit-context">
         <summary>Additional context</summary>
         <dl>
            {notes ? (
               <div>
                  <dt>Notes</dt>
                  <dd>{notes}</dd>
               </div>
            ) : null}
            {contextEntries.map(([key, label]) => (
               <div key={key}>
                  <dt>{label}</dt>
                  <dd>{formatManagementAuditValue(context[key])}</dd>
               </div>
            ))}
            {governanceEntries.map(([key, label]) => (
               <div key={key}>
                  <dt>{label}</dt>
                  <dd>{formatGovernanceValue(governance[key])}</dd>
               </div>
            ))}
         </dl>
      </details>
   );
}
