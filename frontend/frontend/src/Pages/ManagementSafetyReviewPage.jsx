import SafetyReviewPanel from "../components/workspace/SafetyReviewPanel.jsx";
import { ManagementPageHeader } from "../components/management/ManagementUi";

function ManagementSafetyReviewPage() {
   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Safety Review"
            subtitle="Review reported Community content and apply platform-safety actions."
         />

         <section className="management-section" aria-labelledby="management-safety-boundary">
            <div className="management-section__heading">
               <h2 id="management-safety-boundary">Community safety governance</h2>
               <p>
                  Safety actions address platform-policy violations. Factual verification
                  and partner adjudication remain separate in the Verification Workspace.
               </p>
            </div>

            <SafetyReviewPanel />
         </section>
      </div>
   );
}

export default ManagementSafetyReviewPage;
