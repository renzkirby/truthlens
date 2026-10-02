import { Link } from "react-router-dom";

import PartnerLogo from "./PartnerLogo";
import "./PartnerAffiliations.css";

function PartnerAffiliations({ affiliations, compact = false, className = "" }) {
   const safeAffiliations = Array.isArray(affiliations) ? affiliations : [];
   if (safeAffiliations.length === 0) return null;

   return (
      <ul
         className={`partner-affiliations ${compact ? "partner-affiliations--compact" : ""} ${className}`.trim()}
         aria-label="Partner organization affiliations"
      >
         {safeAffiliations.map((organization) => (
            <li key={organization.id || organization.slug}>
               <Link to={`/community/partners/${encodeURIComponent(organization.slug)}`}>
                  {!compact && (
                     <PartnerLogo
                        logoUrl={organization.logo_url}
                        organizationName={organization.name}
                        size="compact"
                     />
                  )}
                  <span>
                     {compact ? (
                        <>
                           <small>Partner</small>
                           <span aria-hidden="true">·</span>
                           <strong>{organization.name}</strong>
                        </>
                     ) : (
                        <>
                           <small>Partner Organization Member</small>
                           <strong>{organization.name}</strong>
                        </>
                     )}
                  </span>
               </Link>
            </li>
         ))}
      </ul>
   );
}

export default PartnerAffiliations;
