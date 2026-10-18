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
];

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
   if (!notes && !contextEntries.length) return null;

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
         </dl>
      </details>
   );
}
