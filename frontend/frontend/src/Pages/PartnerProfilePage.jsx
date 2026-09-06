import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ExternalLink, Info } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import PublicSiteHeader from "../components/public/PublicSiteHeader";
import PartnerLogo from "../components/partners/PartnerLogo";
import "./PartnerProfilePage.css";

function PartnerProfileContent({ slug }) {
   const { authFetch } = useAuth();
   const [partner, setPartner] = useState(null);
   const [isLoading, setIsLoading] = useState(true);
   const [error, setError] = useState(null);
   const [retryVersion, setRetryVersion] = useState(0);
   const requestIdRef = useRef(0);

   useEffect(() => {
      const requestId = ++requestIdRef.current;

      authFetch(resolveApiEndpoint("PUBLIC_PARTNER_DETAIL", slug))
         .then((response) => {
            if (requestId === requestIdRef.current) setPartner(response);
         })
         .catch((requestError) => {
            if (requestId === requestIdRef.current) {
               setError(requestError?.status === 404 ? "unavailable" : "request");
            }
         })
         .finally(() => {
            if (requestId === requestIdRef.current) setIsLoading(false);
         });

      return () => {
         requestIdRef.current += 1;
      };
   }, [authFetch, retryVersion, slug]);

   const retry = () => {
      setPartner(null);
      setError(null);
      setIsLoading(true);
      setRetryVersion((value) => value + 1);
   };

   return (
      <>
            {isLoading && (
               <section className="partner-profile-state" aria-busy="true" aria-live="polite">
                  <div className="skeleton-box partner-profile-state__logo" aria-hidden="true" />
                  <h1>Public partner profile</h1>
                  <p>Loading public partner profile…</p>
               </section>
            )}

            {!isLoading && error && (
               <section className="partner-profile-state" role="alert">
                  <h1>Partner profile unavailable</h1>
                  <p>This public partner profile could not be found or is not currently available.</p>
                  {error === "request" && (
                     <button type="button" onClick={retry}>
                        Retry
                     </button>
                  )}
               </section>
            )}

            {!isLoading && !error && partner && (
               <article className="partner-profile">
                  <header className="partner-profile-hero">
                     <PartnerLogo
                        logoUrl={partner.logo_url}
                        organizationName={partner.name}
                        size="profile"
                     />
                     <div>
                        <p className="partner-profile-eyebrow">Public partner profile</p>
                        <h1>{partner.name}</h1>
                        <p className="partner-profile-type">{partner.organization_type_label}</p>
                     </div>
                  </header>

                  <div className="partner-profile-content">
                     <section aria-labelledby="partner-about-heading">
                        <h2 id="partner-about-heading">About</h2>
                        <p className="partner-profile-description">
                           {partner.description || "This organization has not provided a public description."}
                        </p>
                     </section>

                     {Array.isArray(partner.expertise_areas) && partner.expertise_areas.length > 0 && (
                        <section aria-labelledby="partner-expertise-heading">
                           <h2 id="partner-expertise-heading">Expertise</h2>
                           <ul className="partner-profile-expertise">
                              {partner.expertise_areas.map((area, index) => (
                                 <li key={`${area}-${index}`}>{area}</li>
                              ))}
                           </ul>
                        </section>
                     )}

                     {partner.website && (
                        <section aria-labelledby="partner-website-heading">
                           <h2 id="partner-website-heading">Website</h2>
                           <a
                              className="partner-profile-website"
                              href={partner.website}
                              target="_blank"
                              rel="noopener noreferrer"
                           >
                              Visit organization website
                              <ExternalLink aria-hidden="true" />
                           </a>
                        </section>
                     )}

                     <aside className="partner-profile-context" aria-labelledby="partner-context-heading">
                        <Info aria-hidden="true" />
                        <div>
                           <h2 id="partner-context-heading">Partnership context</h2>
                           <p>
                              This public profile indicates that the organization has chosen to maintain a public
                              presence on TruthLens. Partner participation does not automatically imply endorsement
                              of all TruthLens analyses, verdicts, or content.
                           </p>
                        </div>
                     </aside>
                  </div>
               </article>
            )}
      </>
   );
}

function PartnerProfilePage() {
   const { slug } = useParams();
   const location = useLocation();
   const previousSearch = location.state?.fromPartners;
   const partnersPath =
      typeof previousSearch === "string" && (previousSearch === "" || previousSearch.startsWith("?"))
         ? `/partners${previousSearch}`
         : "/partners";

   return (
      <div className="partner-profile-page">
         <PublicSiteHeader />
         <main className="partner-profile-main">
            <Link to={partnersPath} className="partner-profile-back">
               <ArrowLeft aria-hidden="true" />
               Back to partners
            </Link>

            <PartnerProfileContent key={slug} slug={slug} />
         </main>
      </div>
   );
}

export default PartnerProfilePage;
