import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { Search, SlidersHorizontal } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { resolveApiEndpoint } from "../utils/api";
import PartnerLogo from "../components/partners/PartnerLogo";
import "./PartnersPage.css";

const ORGANIZATION_TYPES = [
   ["", "All organization types"],
   ["FACT_CHECKING", "Fact-Checking Organization"],
   ["NEWS", "News Organization"],
   ["UNIVERSITY", "University"],
   ["RESEARCH", "Research Organization"],
   ["NGO", "Non-Governmental Organization"],
   ["GOVERNMENT", "Government Organization"],
   ["OTHER", "Other"],
];

function PartnerCard({ partner, directorySearch }) {
   const expertise = Array.isArray(partner.expertise_areas) ? partner.expertise_areas : [];
   const visibleExpertise = expertise.slice(0, 3);
   const remainingExpertise = expertise.length - visibleExpertise.length;

   return (
      <Link
         to={`/partners/${encodeURIComponent(partner.slug)}`}
         state={{ fromPartners: directorySearch }}
         className="partner-directory-card"
      >
         <div className="partner-directory-card__topline">
            <PartnerLogo logoUrl={partner.logo_url} organizationName={partner.name} />
            <span className="partner-directory-card__type">{partner.organization_type_label}</span>
         </div>

         <div className="partner-directory-card__body">
            <h3>{partner.name}</h3>
            <p className="partner-directory-card__description">
               {partner.description || "No public description provided."}
            </p>
         </div>

         {visibleExpertise.length > 0 && (
            <ul className="partner-directory-card__expertise" aria-label="Expertise areas">
               {visibleExpertise.map((area, index) => (
                  <li key={`${area}-${index}`}>{area}</li>
               ))}
               {remainingExpertise > 0 && <li>+{remainingExpertise} more</li>}
            </ul>
         )}

         <span className="partner-directory-card__action">View public profile</span>
      </Link>
   );
}

function DirectorySkeleton() {
   return (
      <div className="partner-directory-grid" aria-hidden="true">
         {[0, 1, 2].map((item) => (
            <div className="partner-directory-skeleton" key={item}>
               <div className="skeleton-box partner-directory-skeleton__logo" />
               <div className="skeleton-box partner-directory-skeleton__title" />
               <div className="skeleton-box partner-directory-skeleton__line" />
               <div className="skeleton-box partner-directory-skeleton__line partner-directory-skeleton__line--short" />
            </div>
         ))}
      </div>
   );
}

function PartnersPage() {
   useDocumentTitle("TruthLens Partners");

   const { authFetch } = useAuth();
   const location = useLocation();
   const [searchParams, setSearchParams] = useSearchParams();
   const querySearch = searchParams.get("search") || "";
   const queryType = searchParams.get("type") || "";
   const [searchInput, setSearchInput] = useState(querySearch);
   const [directory, setDirectory] = useState(null);
   const [error, setError] = useState(false);
   const [isLoading, setIsLoading] = useState(true);
   const [retryVersion, setRetryVersion] = useState(0);
   const requestIdRef = useRef(0);

   useEffect(() => {
      setSearchInput(querySearch);
   }, [querySearch]);

   useEffect(() => {
      const timeoutId = window.setTimeout(() => {
         const normalizedSearch = searchInput.trim();
         if (normalizedSearch === querySearch) return;

         const nextParams = new URLSearchParams(searchParams);
         if (normalizedSearch) nextParams.set("search", normalizedSearch);
         else nextParams.delete("search");
         setSearchParams(nextParams, { replace: true });
      }, 300);

      return () => window.clearTimeout(timeoutId);
   }, [querySearch, searchInput, searchParams, setSearchParams]);

   useEffect(() => {
      const requestId = ++requestIdRef.current;
      const endpoint = resolveApiEndpoint("PUBLIC_PARTNERS");
      const requestParams = new URLSearchParams();
      if (querySearch) requestParams.set("search", querySearch);
      if (queryType) requestParams.set("type", queryType);
      const queryString = requestParams.toString();
      const requestUrl = queryString ? `${endpoint}?${queryString}` : endpoint;

      setIsLoading(true);
      setError(false);

      authFetch(requestUrl)
         .then((response) => {
            if (requestId !== requestIdRef.current) return;
            setDirectory({
               count: Number(response?.count) || 0,
               results: Array.isArray(response?.results) ? response.results : [],
            });
         })
         .catch(() => {
            if (requestId === requestIdRef.current) setError(true);
         })
         .finally(() => {
            if (requestId === requestIdRef.current) setIsLoading(false);
         });

      return () => {
         requestIdRef.current += 1;
      };
   }, [authFetch, querySearch, queryType, retryVersion]);

   const updateType = (event) => {
      const nextParams = new URLSearchParams(searchParams);
      if (event.target.value) nextParams.set("type", event.target.value);
      else nextParams.delete("type");
      setSearchParams(nextParams);
   };

   const clearFilters = () => {
      setSearchInput("");
      setSearchParams(new URLSearchParams());
   };

   const hasFilters = Boolean(querySearch || queryType);
   const resultCount = directory?.count ?? 0;
   const resultSummary = hasFilters
      ? `${resultCount} ${resultCount === 1 ? "partner" : "partners"} found`
      : `${resultCount} public ${resultCount === 1 ? "partner" : "partners"}`;

   return (
      <div className="partners-page">
         <section className="partners-hero" aria-labelledby="partners-heading">
               <div className="partners-page__container partners-hero__content">
                  <p className="partners-eyebrow">Public partner directory</p>
                  <h1 id="partners-heading">TruthLens Partners</h1>
                  <p className="partners-hero__lead">
                     Explore organizations that have chosen to maintain a public partner profile on TruthLens.
                  </p>
                  <p className="partners-hero__boundary">
                     Public partner presence does not imply endorsement of every TruthLens analysis or publication.
                  </p>
               </div>
            </section>

            <section className="partners-directory" aria-labelledby="directory-heading">
               <div className="partners-page__container">
                  <div className="partners-directory__heading">
                     <div>
                        <p className="partners-eyebrow">Browse organizations</p>
                        <h2 id="directory-heading">Public partner profiles</h2>
                     </div>
                     {directory && !error && (
                        <p className="partners-directory__count" aria-live="polite" aria-atomic="true">
                           {isLoading ? "Updating results…" : resultSummary}
                        </p>
                     )}
                  </div>

                  <div className="partners-filters" role="search" aria-label="Filter partner directory">
                     <div className="partners-filter-field">
                        <label htmlFor="partner-search">Search</label>
                        <div className="partners-filter-control">
                           <Search aria-hidden="true" />
                           <input
                              id="partner-search"
                              type="search"
                              value={searchInput}
                              onChange={(event) => setSearchInput(event.target.value)}
                              placeholder="Search partner organizations"
                           />
                        </div>
                     </div>

                     <div className="partners-filter-field">
                        <label htmlFor="partner-type">Organization type</label>
                        <div className="partners-filter-control">
                           <SlidersHorizontal aria-hidden="true" />
                           <select id="partner-type" value={queryType} onChange={updateType}>
                              {ORGANIZATION_TYPES.map(([value, label]) => (
                                 <option key={value} value={value}>{label}</option>
                              ))}
                           </select>
                        </div>
                     </div>
                  </div>

                  <div className="partners-results" aria-busy={isLoading}>
                     {!directory && isLoading && (
                        <>
                           <p className="partners-results__status">Loading public partners…</p>
                           <DirectorySkeleton />
                        </>
                     )}

                     {error && (
                        <div className="partners-state" role="alert">
                           <h3>Partner directory unavailable</h3>
                           <p>We could not load public partner profiles. Please try again.</p>
                           <button type="button" onClick={() => setRetryVersion((value) => value + 1)}>
                              Retry
                           </button>
                        </div>
                     )}

                     {!error && directory && directory.results.length === 0 && !isLoading && (
                        <div className="partners-state">
                           <h3>{hasFilters ? "No partners match these filters." : "No public partners are available yet."}</h3>
                           <p>
                              {hasFilters
                                 ? "Try a different search or organization type."
                                 : "Organizations with public partner profiles will appear here."}
                           </p>
                           {hasFilters && (
                              <button type="button" onClick={clearFilters}>Clear filters</button>
                           )}
                        </div>
                     )}

                     {!error && directory && directory.results.length > 0 && (
                        <div className={`partner-directory-grid${isLoading ? " is-updating" : ""}`}>
                           {directory.results.map((partner) => (
                              <PartnerCard
                                 key={partner.id}
                                 partner={partner}
                                 directorySearch={location.search}
                              />
                           ))}
                        </div>
                     )}
                  </div>
               </div>
         </section>
      </div>
   );
}

export default PartnersPage;
