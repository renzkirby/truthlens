import { Link } from "react-router-dom";

import { ManagementPageHeader, ManagementRequestState } from "../components/management/ManagementUi";
import Icons from "../components/Icons";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";

const DESTINATIONS = [
   {
      to: "/management/organizations",
      title: "Partner Organizations",
      description: "Inspect institutional identity, platform trust, and Organization Admin state.",
      icon: "landmark",
      primary: true,
   },
   {
      to: "/management/memberships",
      title: "Memberships",
      description: "Review organization roles, status, and admission history.",
      icon: "users",
   },
   {
      to: "/management/invitations",
      title: "Invitations",
      description: "Review membership and Organization Admin onboarding invitations.",
      icon: "mail",
   },
];

function ManagementOverviewPage() {
   const { data, loading, error, retry } = useManagementRequest(
      resolveApiEndpoint("MANAGEMENT_OVERVIEW"),
   );
   const organizations = data?.organizations;

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Platform Overview"
            subtitle="Platform administration and operational governance"
         />

         <ManagementRequestState loading={loading} error={error} onRetry={retry}>
            <section className="management-metrics" aria-label="Organization governance summary">
               <article>
                  <span>Total Organizations</span>
                  <strong>{organizations?.total ?? 0}</strong>
               </article>
               <article>
                  <span>Active Partners</span>
                  <strong>{organizations?.active_partners ?? 0}</strong>
               </article>
               <article>
                  <span>Pending Verification</span>
                  <strong>{organizations?.pending_verification ?? 0}</strong>
               </article>
               <article>
                  <span>Suspended Partners</span>
                  <strong>{organizations?.suspended_partners ?? 0}</strong>
               </article>
            </section>
         </ManagementRequestState>

         <section className="management-section" aria-labelledby="governance-heading">
            <div className="management-section__heading">
               <h2 id="governance-heading">Governance records</h2>
               <p>Read-only access to the institutional records maintained by TruthLens.</p>
            </div>
            <div className="management-destinations">
               {DESTINATIONS.map((destination) => (
                  <Link
                     key={destination.to}
                     to={destination.to}
                     className={`management-destination ${destination.primary ? "management-destination--primary" : ""}`}
                  >
                     <Icons name={destination.icon} size={22} />
                     <span>
                        <strong>{destination.title}</strong>
                        <small>{destination.description}</small>
                     </span>
                     <Icons name="arrow-right" size={18} />
                  </Link>
               ))}
            </div>
         </section>
      </div>
   );
}

export default ManagementOverviewPage;
