import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, Info, RefreshCw } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { resolveApiEndpoint } from "../utils/api";
import PartnerLogo from "../components/partners/PartnerLogo";
import "./PartnerProfilePage.css";

const PUBLICATION_PAGE_SIZE = 6;

const VERDICT_META = {
   FACT: { label: "Fact", className: "fact" },
   FAKE: { label: "Fake", className: "fake" },
   MISLEADING: { label: "Misleading", className: "misleading" },
   SATIRE: { label: "Satire", className: "satire" },
   UNVERIFIED: { label: "Unverified", className: "unverified" },
   OUT_OF_SCOPE: { label: "Out of scope", className: "out-of-scope" },
};

const REVISION_LABELS = {
   INITIAL: "Initial publication",
   EDITORIAL_REVISION: "Editorial revision",
   FACTUAL_CORRECTION: "Factual correction",
};

function formatPublishedDate(value) {
   if (!value) return "Publication date unavailable";

   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Publication date unavailable";

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
   }).format(date);
}

function revisionLabel(value) {
   return REVISION_LABELS[value] || "Revision kind unavailable";
}

function verdictMeta(value) {
   return (
      VERDICT_META[value] || {
         label: "Unknown verdict",
         className: "unknown",
      }
   );
}

function factCheckRoute(slug, publicationId) {
   return `/partners/${encodeURIComponent(slug)}/fact-checks/${encodeURIComponent(publicationId)}`;
}

function factChecksEndpoint(slug, offset) {
   const endpoint = resolveApiEndpoint("PUBLIC_PARTNER_FACT_CHECKS", slug);
   const query = new URLSearchParams({
      limit: String(PUBLICATION_PAGE_SIZE),
      offset: String(offset),
   });

   return `${endpoint}?${query.toString()}`;
}

function validateFactCheckPage(response) {
   if (
      !response ||
      !Array.isArray(response.results) ||
      typeof response.count !== "number" ||
      typeof response.offset !== "number"
   ) {
      throw new Error("The public fact-check collection response is incomplete.");
   }

   return response;
}

function dedupePublications(items) {
   const seen = new Set();

   return items.filter((item) => {
      const publicationId = String(item?.publication_id || "");
      if (!publicationId || seen.has(publicationId)) return false;

      seen.add(publicationId);
      return true;
   });
}

function mergePublications(current, incoming) {
   return dedupePublications([...current, ...incoming]);
}

function PublishedFactCheckCard({ slug, publication }) {
   const decision = publication?.decision || {};
   const article = publication?.article || {};
   const history = publication?.history || {};
   const verdict = verdictMeta(decision.verdict);
   const publicationPath = factCheckRoute(slug, publication.publication_id);
   const headline = article.headline || "Published fact-check";
   const previousVersions = Number.isInteger(history.previous_versions_count)
      ? history.previous_versions_count
      : 0;

   return (
      <article
         className={`partner-publication-card partner-publication-card--${verdict.className}`}
      >
         <div className="partner-publication-card__topline">
            <div className="partner-publication-verdict">
               <span>Human factual verdict</span>
               <strong>{verdict.label}</strong>
            </div>

            <div className="partner-publication-card__version">
               <span>Article v{article.version}</span>
               <span aria-hidden="true">·</span>
               <span>{revisionLabel(article.revision_kind)}</span>
            </div>
         </div>

         <h3>{headline}</h3>

         <div className="partner-publication-claim">
            <span>Claim</span>
            <blockquote>
               {decision.canonical_claim || "Claim text unavailable for this publication."}
            </blockquote>
         </div>

         {article.summary && <p className="partner-publication-summary">{article.summary}</p>}

         <div className="partner-publication-card__footer">
            <div className="partner-publication-card__metadata">
               <time dateTime={publication.published_at}>
                  {formatPublishedDate(publication.published_at)}
               </time>

               {previousVersions > 0 && (
                  <span>
                     {previousVersions} previous published{" "}
                     {previousVersions === 1 ? "version" : "versions"}
                  </span>
               )}

               {history.has_factual_correction && (
                  <span className="partner-publication-card__correction">
                     Includes factual correction history
                  </span>
               )}
            </div>

            <Link
               className="partner-publication-read"
               to={publicationPath}
               aria-label={`Read fact-check: ${headline}`}
            >
               Read fact-check
               <ArrowRight aria-hidden="true" />
            </Link>
         </div>
      </article>
   );
}

function PartnerPublishedFactChecks({ slug }) {
   const { authFetch } = useAuth();
   const [factChecks, setFactChecks] = useState([]);
   const [count, setCount] = useState(0);
   const [nextOffset, setNextOffset] = useState(0);
   const [isInitialLoading, setIsInitialLoading] = useState(true);
   const [isLoadingMore, setIsLoadingMore] = useState(false);
   const [initialError, setInitialError] = useState(false);
   const [loadMoreError, setLoadMoreError] = useState(false);
   const [retryVersion, setRetryVersion] = useState(0);
   const initialRequestIdRef = useRef(0);
   const loadMoreRequestIdRef = useRef(0);

   useEffect(() => {
      const requestId = ++initialRequestIdRef.current;

      authFetch(factChecksEndpoint(slug, 0))
         .then((response) => {
            if (requestId !== initialRequestIdRef.current) return;

            const page = validateFactCheckPage(response);
            setFactChecks(dedupePublications(page.results));
            setCount(page.count);
            setNextOffset(page.offset + page.results.length);
            setInitialError(false);
         })
         .catch(() => {
            if (requestId === initialRequestIdRef.current) {
               setInitialError(true);
            }
         })
         .finally(() => {
            if (requestId === initialRequestIdRef.current) {
               setIsInitialLoading(false);
            }
         });

      return () => {
         initialRequestIdRef.current += 1;
         loadMoreRequestIdRef.current += 1;
      };
   }, [authFetch, retryVersion, slug]);

   const retryInitialLoad = () => {
      setInitialError(false);
      setIsInitialLoading(true);
      setRetryVersion((value) => value + 1);
   };

   const loadMore = () => {
      if (isLoadingMore || nextOffset >= count) return;

      const requestId = ++loadMoreRequestIdRef.current;
      const requestedOffset = nextOffset;

      setIsLoadingMore(true);
      setLoadMoreError(false);

      authFetch(factChecksEndpoint(slug, requestedOffset))
         .then((response) => {
            if (requestId !== loadMoreRequestIdRef.current) return;

            const page = validateFactCheckPage(response);
            setFactChecks((current) => mergePublications(current, page.results));
            setCount(page.count);
            setNextOffset(page.offset + page.results.length);
         })
         .catch(() => {
            if (requestId === loadMoreRequestIdRef.current) {
               setLoadMoreError(true);
            }
         })
         .finally(() => {
            if (requestId === loadMoreRequestIdRef.current) {
               setIsLoadingMore(false);
            }
         });
   };

   if (isInitialLoading) {
      return (
         <div
            className="partner-publications-state partner-publications-state--loading"
            aria-busy="true"
            aria-live="polite"
         >
            <div className="partner-publications-skeleton" aria-hidden="true">
               <span />
               <span />
               <span />
            </div>
            <p>Loading published fact-checks…</p>
         </div>
      );
   }

   if (initialError) {
      return (
         <div className="partner-publications-state" role="status">
            <strong>Published fact-checks could not be loaded.</strong>
            <p>The organization profile is still available. You can retry this section.</p>
            <button type="button" onClick={retryInitialLoad}>
               <RefreshCw aria-hidden="true" />
               Retry published fact-checks
            </button>
         </div>
      );
   }

   if (factChecks.length === 0) {
      return (
         <div className="partner-publications-state">
            <strong>No published fact-checks are currently available from this organization.</strong>
         </div>
      );
   }

   const hasMore = nextOffset < count;

   return (
      <>
         <div className="partner-publications-summary" aria-live="polite">
            Showing {factChecks.length} of {count} published fact-check{count === 1 ? "" : "s"}.
         </div>

         <ul className="partner-publications-list">
            {factChecks.map((publication) => (
               <li key={publication.publication_id}>
                  <PublishedFactCheckCard slug={slug} publication={publication} />
               </li>
            ))}
         </ul>

         {(hasMore || loadMoreError) && (
            <div className="partner-publications-more">
               {loadMoreError && (
                  <p role="status">
                     More published fact-checks could not be loaded. Already loaded publications
                     remain available.
                  </p>
               )}

               {hasMore && (
                  <button type="button" onClick={loadMore} disabled={isLoadingMore}>
                     {isLoadingMore ? "Loading more…" : loadMoreError ? "Try again" : "Load more"}
                  </button>
               )}
            </div>
         )}
      </>
   );
}

function PartnerProfileContent({ slug }) {
   const { authFetch } = useAuth();
   const [partner, setPartner] = useState(null);
   const [isLoading, setIsLoading] = useState(true);
   const [error, setError] = useState(null);
   const [retryVersion, setRetryVersion] = useState(0);
   const requestIdRef = useRef(0);
   let documentTitle = "Partner Profile | TruthLens";
   if (partner?.name) documentTitle = `${partner.name} | TruthLens Partners`;
   if (error) documentTitle = "Partner Profile Unavailable | TruthLens";

   useDocumentTitle(documentTitle);

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

                  <section
                     className="partner-profile-publications"
                     aria-labelledby="partner-publications-heading"
                  >
                     <div className="partner-profile-publications__heading">
                        <div>
                           <h2 id="partner-publications-heading">Published fact-checks</h2>
                           <p>Fact-checks institutionally published by this organization.</p>
                        </div>
                     </div>

                     <PartnerPublishedFactChecks slug={slug} />
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
         <div className="partner-profile-main">
            <Link to={partnersPath} className="partner-profile-back">
               <ArrowLeft aria-hidden="true" />
               Back to partners
            </Link>

            <PartnerProfileContent key={slug} slug={slug} />
         </div>
      </div>
   );
}

export default PartnerProfilePage;
