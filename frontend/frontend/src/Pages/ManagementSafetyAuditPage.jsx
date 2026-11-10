import AccountabilityPanel from "../components/workspace/AccountabilityPanel.jsx";
import { ManagementPageHeader } from "../components/management/ManagementUi";
import Icons from "../components/Icons.jsx";

function ManagementSafetyAuditPage() {
   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Safety Action History"
            subtitle="Review past Platform Safety decisions, assignments, and case-state changes."
         />

         <aside className="management-boundary-note" aria-label="Safety history boundary">
            <Icons name="info" size={19} />
            <div>
               <strong>Read-only history</strong>
               <p>
                  These records document actions already taken by Platform Staff. Use Safety Review
                  for active cases; historical records here are retained for accountability.
               </p>
            </div>
         </aside>

         <AccountabilityPanel scope="platform" />
      </div>
   );
}

export default ManagementSafetyAuditPage;
