import SafetyReviewPanel from "../components/workspace/SafetyReviewPanel.jsx";
import { ManagementPageHeader } from "../components/management/ManagementUi";
import Icons from "../components/Icons.jsx";

import "./ManagementSafetyReviewPage.css";

function ManagementSafetyReviewPage() {
   return (
      <div className="management-page management-safety-page">
         <ManagementPageHeader
            title="Safety Review"
            subtitle="Review reported Community content and record platform-safety decisions."
         />

         <section className="management-safety-boundary" aria-labelledby="management-safety-boundary-title">
            <span className="management-safety-boundary__icon" aria-hidden="true">
               <Icons name="shield-check" size={20} />
            </span>
            <div>
               <h2 id="management-safety-boundary-title">Platform policy review</h2>
               <p>
                  Review reports for abuse, spam, harassment, and other platform-policy concerns.
                  Safety actions do not determine whether a claim is factually true or false.
               </p>
            </div>
         </section>

         <SafetyReviewPanel />
      </div>
   );
}

export default ManagementSafetyReviewPage;
