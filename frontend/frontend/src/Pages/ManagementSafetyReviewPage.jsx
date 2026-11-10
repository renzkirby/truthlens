import SafetyReviewPanel from "../components/workspace/SafetyReviewPanel.jsx";
import { ManagementPageHeader } from "../components/management/ManagementUi";
import Icons from "../components/Icons.jsx";

import "./ManagementSafetyReviewPage.css";

function ManagementSafetyReviewPage() {
   return (
      <div className="management-page management-safety-page">
         <ManagementPageHeader
            title="Safety Review"
            subtitle="Review reported Community content and decide whether platform action is required."
         />

         <section className="management-safety-boundary" aria-labelledby="management-safety-boundary-title">
            <span className="management-safety-boundary__icon" aria-hidden="true">
               <Icons name="shield-check" size={20} />
            </span>
            <div>
               <h2 id="management-safety-boundary-title">What you review here</h2>
               <p>
                  Review reports about abuse, spam, harassment, and other Community safety concerns.
                  Your decision affects platform safety and content handling; it does not decide whether
                  a factual claim is true or false.
               </p>
            </div>
         </section>

         <SafetyReviewPanel />
      </div>
   );
}

export default ManagementSafetyReviewPage;
