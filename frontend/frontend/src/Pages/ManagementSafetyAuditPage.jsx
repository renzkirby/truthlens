import AccountabilityPanel from "../components/workspace/AccountabilityPanel.jsx";
import { ManagementPageHeader } from "../components/management/ManagementUi";

function ManagementSafetyAuditPage() {
   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Safety Action History"
            subtitle="Review past Platform Safety decisions, assignments, and case-state changes."
         />

         <AccountabilityPanel scope="platform" />
      </div>
   );
}

export default ManagementSafetyAuditPage;
