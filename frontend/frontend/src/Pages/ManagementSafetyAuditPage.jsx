import AccountabilityPanel from "../components/workspace/AccountabilityPanel.jsx";
import { ManagementPageHeader } from "../components/management/ManagementUi";

function ManagementSafetyAuditPage() {
   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Safety Audit"
            subtitle="Review the append-only record of Platform Safety actions and case state changes."
         />

         <AccountabilityPanel scope="platform" />
      </div>
   );
}

export default ManagementSafetyAuditPage;
