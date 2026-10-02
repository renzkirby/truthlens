import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, Info } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useNotification } from "../hooks/useNotification";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { resolveApiEndpoint } from "../utils/api";
import { createPublicReachEventId, recordPublicReach } from "../utils/publicReach";
import PartnerLogo from "../components/partners/PartnerLogo";
import Icons from "../components/Icons.jsx";
import "./UserProfile.css";
import "./PartnerProfilePage.css";

const PUBLICATION_PAGE_SIZE = 6;
const PARTNER_PROFILE_TABS = ["published", "about"];

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

function factCheckRoute(slug, publicationId, isCommunity) {
   const prefix = isCommunity ? "/community/partners" : "/partners";
   return `${prefix}/${encodeURIComponent(slug)}/fact-checks/${encodeURIComponent(publicationId)}`;
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


function PublishedFactCheckCard({ slug, publication, isCommunity }) {
   const decision = publication?.decision || {};
   const article = publication?.article || {};
   const history = publication?.history || {};
   const verdict = verdictMeta(decision.verdict);
   const publicationPath = factCheckRoute(slug, publication.publication_id, isCommunity);
   const headline = article.headline || "Published fact-check";
   const previousVersions = Number.isInteger(history.previous_versions_count)
      ? history.previous_versions_count
      : 0;

   return (
      <article
         className={`user-profile__activity-item partner-publication-card partner-publication-card--${verdict.className}`}
      >
         <div className="user-profile__activity-item-topline">
            <span
               className={`user-profile__status partner-publication-verdict partner-publication-verdict--${verdict.className}`}
            >
               {verdict.label}
            </span>
            <time dateTime={publication.published_at}>{formatPublishedDate(publication.published_at)}</time>
         </div>

         <div className="user-profile__activity-copy">
            <h3>{headline}</h3>
            <p className="partner-publication-claim">
               <span>Claim: </span>
               {decision.canonical_claim || "Claim text unavailable for this publication."}
            </p>
            {article.summary && <p>{article.summary}</p>}
         </div>

         <div className="user-profile__activity-footer">
            <div className="user-profile__activity-metrics">
               {article.version != null && <span>Article v{article.version}</span>}
               <span>{revisionLabel(article.revision_kind)}</span>
               {previousVersions > 0 && (
                  <span>
                     {previousVersions} previous published {previousVersions === 1 ? "version" : "versions"}
                  </span>
               )}
               {history.has_factual_correction && (
                  <span className="partner-publication-card__correction">Correction history</span>
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

function PartnerPublishedFactChecks({ slug, isCommunity, onCountChange }) {
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
            onCountChange?.(page.count);
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
   }, [authFetch, onCountChange, retryVersion, slug]);

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
            onCountChange?.(page.count);
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
         <div className="user-profile__loading-block" role="status" aria-live="polite">
            <span className="user-profile__sr-only">Loading published fact-checks.</span>
            <div className="user-profile__skeleton-list" aria-hidden="true">
               {Array.from({ length: 3 }).map((_, index) => (
                  <div className="user-profile__skeleton-item" key={`partner-publication-skeleton-${index}`}>
                     <span className="user-profile__skeleton-line is-short" />
                     <span className="user-profile__skeleton-line" />
                     <span className="user-profile__skeleton-line is-medium" />
                  </div>
               ))}
            </div>
         </div>
      );
   }

   if (initialError) {
      return (
         <div className="user-profile__inline-state is-error" role="alert">
            <Icons name="alert-circle" size={20} aria-hidden="true" />
            <div>
               <h3>Published fact-checks could not load</h3>
               <p>The organization profile is still available. You can retry this section.</p>
            </div>
            <button type="button" onClick={retryInitialLoad}>
               Try again
            </button>
         </div>
      );
   }

   if (factChecks.length === 0) {
      return (
         <div className="user-profile__empty-state">
            <Icons name="file-text" size={22} aria-hidden="true" />
            <h3>No published fact-checks yet</h3>
            <p>This organization has no public fact-check publications available right now.</p>
         </div>
      );
   }

   const hasMore = nextOffset < count;

   return (
      <>
         <ul className="user-profile__activity-list partner-publications-list">
            {factChecks.map((publication) => (
               <li key={publication.publication_id}>
                  <PublishedFactCheckCard
                     slug={slug}
                     publication={publication}
                     isCommunity={isCommunity}
                  />
               </li>
            ))}
         </ul>

         {(hasMore || loadMoreError) && (
            <div className="user-profile__pagination partner-publications-pagination">
               <div>
                  <span>
                     Showing {factChecks.length.toLocaleString()} of {count.toLocaleString()}
                  </span>
                  {loadMoreError && (
                     <span className="partner-publications-pagination__error" role="status">
                        More publications could not be loaded.
                     </span>
                  )}
               </div>

               {hasMore && (
                  <button
                     type="button"
                     className="user-profile__secondary-button"
                     onClick={loadMore}
                     disabled={isLoadingMore}
                  >
                     {isLoadingMore ? "Loading…" : loadMoreError ? "Try again" : "Load more"}
                  </button>
               )}
            </div>
         )}
      </>
   );
}

function PartnerProfileContent({ slug, isCommunity }) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();
   const [partner, setPartner] = useState(null);
   const [isLoading, setIsLoading] = useState(true);
   const [error, setError] = useState(null);
   const [retryVersion, setRetryVersion] = useState(0);
   const [isFollowPending, setIsFollowPending] = useState(false);
   const [activeTab, setActiveTab] = useState("published");
   const [publicationCount, setPublicationCount] = useState(null);
   const requestIdRef = useRef(0);
   const reachEventIdRef = useRef(null);
   let documentTitle = isCommunity ? "Partner Organization | TruthLens Community" : "Partner Profile | TruthLens";
   if (partner?.name) documentTitle = `${partner.name} | TruthLens Partners`;
   if (error) documentTitle = "Partner Profile Unavailable | TruthLens";

   useDocumentTitle(documentTitle);

   useEffect(() => {
      const requestId = ++requestIdRef.current;

      if (!isCommunity && !reachEventIdRef.current) {
         reachEventIdRef.current = createPublicReachEventId();
      }

      authFetch(resolveApiEndpoint("PUBLIC_PARTNER_DETAIL", slug))
         .then((response) => {
            if (requestId !== requestIdRef.current) return;
            if (!response?.name || response?.slug !== slug) {
               throw new Error("The public partner response is incomplete.");
            }
            setPartner(response);
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
   }, [authFetch, isCommunity, retryVersion, slug]);

   useEffect(() => {
      if (isCommunity || isLoading || error || !partner) return;
      void recordPublicReach({
         clientEventId: reachEventIdRef.current,
         eventType: "PARTNER_PROFILE_VIEW",
         sourceSurface: "PUBLIC_PARTNER_PROFILE",
         organizationSlug: partner.slug,
      });
   }, [error, isCommunity, isLoading, partner]);

   const retry = () => {
      setPartner(null);
      setError(null);
      setIsLoading(true);
      setRetryVersion((value) => value + 1);
   };

   const toggleFollow = async () => {
      if (!partner || isFollowPending) return;

      setIsFollowPending(true);
      try {
         const response = await authFetch(
            resolveApiEndpoint("PUBLIC_PARTNER_FOLLOW", partner.slug),
            { method: "POST" },
         );
         setPartner((current) =>
            current
               ? {
                    ...current,
                    is_following: Boolean(response.is_following),
                    followers_count: Number(response.followers_count) || 0,
                 }
               : current,
         );
      } catch {
         addToast({
            type: "error",
            message: `We couldn't ${partner.is_following ? "unfollow" : "follow"} this organization. Please try again.`,
         });
      } finally {
         setIsFollowPending(false);
      }
   };

   const selectTab = (tab) => setActiveTab(tab);

   const handleTabKeyDown = (event) => {
      const currentIndex = PARTNER_PROFILE_TABS.indexOf(activeTab);
      let nextIndex = null;

      if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % PARTNER_PROFILE_TABS.length;
      if (event.key === "ArrowLeft") {
         nextIndex = (currentIndex - 1 + PARTNER_PROFILE_TABS.length) % PARTNER_PROFILE_TABS.length;
      }
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = PARTNER_PROFILE_TABS.length - 1;
      if (nextIndex === null) return;

      event.preventDefault();
      const nextTab = PARTNER_PROFILE_TABS[nextIndex];
      selectTab(nextTab);
      document.getElementById(`partner-profile-tab-${nextTab}`)?.focus();
   };

   if (isLoading) {
      return (
         <div className="partner-profile-state-shell" aria-busy="true">
            <div className="user-profile__page-state" role="status" aria-live="polite">
               <span className="user-profile__state-icon partner-profile__state-logo" aria-hidden="true">
                  <Icons name="loader" size={24} />
               </span>
               <h1>Loading partner profile</h1>
               <p>Gathering this organization&apos;s public identity and publications.</p>
            </div>
         </div>
      );
   }

   if (error || !partner) {
      return (
         <div className="partner-profile-state-shell">
            <div className="user-profile__page-state" role="alert">
               <span className="user-profile__state-icon user-profile__state-icon--error" aria-hidden="true">
                  <Icons name="alert-circle" size={24} />
               </span>
               <h1>Partner profile unavailable</h1>
               <p>This public partner profile could not be found or is not currently available.</p>
               {error === "request" && (
                  <button type="button" className="user-profile__primary-button" onClick={retry}>
                     Try again
                  </button>
               )}
            </div>
         </div>
      );
   }

   const followerCount = Number(partner.followers_count || 0);
   const expertiseAreas = Array.isArray(partner.expertise_areas) ? partner.expertise_areas : [];
   const currentTabDescription =
      activeTab === "published"
         ? `Institutionally published fact-checks from ${partner.name}.`
         : `Public information about ${partner.name}.`;

   return (
      <section className="user-profile__profile-card partner-profile" aria-labelledby="partner-profile-heading">
         <div className="user-profile__identity">
            <div className="user-profile__identity-top">
               <PartnerLogo
                  logoUrl={partner.logo_url}
                  organizationName={partner.name}
                  size="profile"
               />

               <div className="user-profile__name-group">
                  <h1 id="partner-profile-heading">{partner.name}</h1>
                  <p className="user-profile__handle">
                     {partner.organization_type_label || "Partner Organization"}
                  </p>
               </div>

            </div>

            <div className="user-profile__identity-details">
               <p className="user-profile__role partner-profile__role">
                  <span className="partner-profile__role-mark" aria-hidden="true" />
                  Partner Organization
               </p>

               <p className={`user-profile__bio ${partner.description ? "" : "is-empty"}`.trim()}>
                  {partner.description || "This organization has not provided a public description."}
               </p>

               {partner.website && (
                  <a
                     className="user-profile__joined partner-profile__website-inline"
                     href={partner.website}
                     target="_blank"
                     rel="noopener noreferrer"
                  >
                     <ExternalLink aria-hidden="true" />
                     Visit organization website
                  </a>
               )}

               <div className="user-profile__profile-footer">
                  <div className="user-profile__connections">
                     <span
                        className="partner-profile__connection-stat"
                        aria-label={`${followerCount.toLocaleString()} ${followerCount === 1 ? "follower" : "followers"}`}
                     >
                        <strong>{followerCount.toLocaleString()}</strong>{" "}
                        {followerCount === 1 ? "Follower" : "Followers"}
                     </span>
                  </div>

                  {isCommunity && (
                     <button
                        type="button"
                        className={`user-profile__primary-button user-profile__profile-action ${
                           partner.is_following ? "is-following" : ""
                        }`}
                        onClick={toggleFollow}
                        disabled={isFollowPending}
                        aria-pressed={Boolean(partner.is_following)}
                     >
                        <Icons
                           name={partner.is_following ? "user-check" : "user-plus"}
                           size={16}
                           aria-hidden="true"
                        />
                        {isFollowPending ? "Updating…" : partner.is_following ? "Following" : "Follow"}
                     </button>
                  )}
               </div>
            </div>
         </div>

         <section
            className="user-profile__activity partner-profile__activity"
            aria-labelledby="partner-profile-activity-heading"
            aria-describedby="partner-profile-activity-description"
         >
            <h2 id="partner-profile-activity-heading" className="user-profile__sr-only">
               Partner organization profile content
            </h2>
            <p id="partner-profile-activity-description" className="user-profile__sr-only">
               {currentTabDescription}
            </p>

            <div className="user-profile__activity-nav">
               <div
                  className="user-profile__tabs"
                  role="tablist"
                  aria-label="Partner organization profile"
                  onKeyDown={handleTabKeyDown}
               >
                  {PARTNER_PROFILE_TABS.map((tab) => (
                     <button
                        key={tab}
                        id={`partner-profile-tab-${tab}`}
                        type="button"
                        role="tab"
                        aria-selected={activeTab === tab}
                        aria-controls={`partner-profile-panel-${tab}`}
                        tabIndex={activeTab === tab ? 0 : -1}
                        onClick={() => selectTab(tab)}
                     >
                        {tab === "published" ? "Fact-Checks" : "About"}
                     </button>
                  ))}
               </div>

               {activeTab === "published" && Number.isInteger(publicationCount) && publicationCount >= 0 && (
                  <span className="user-profile__activity-count">
                     {publicationCount.toLocaleString()} {publicationCount === 1 ? "publication" : "publications"}
                  </span>
               )}
            </div>

            <div
               id="partner-profile-panel-published"
               className="user-profile__tab-panel"
               role="tabpanel"
               aria-labelledby="partner-profile-tab-published"
               hidden={activeTab !== "published"}
               tabIndex={activeTab === "published" ? 0 : -1}
            >
               <PartnerPublishedFactChecks
                  slug={slug}
                  isCommunity={isCommunity}
                  onCountChange={setPublicationCount}
               />
            </div>

            <div
               id="partner-profile-panel-about"
               className="user-profile__tab-panel"
               role="tabpanel"
               aria-labelledby="partner-profile-tab-about"
               hidden={activeTab !== "about"}
               tabIndex={activeTab === "about" ? 0 : -1}
            >
               {activeTab === "about" && (
                  <div className="user-profile__activity-list partner-profile__about-list">
                     <section className="user-profile__activity-item partner-profile__about-section">
                        <div className="user-profile__activity-copy">
                           <h3>About</h3>
                           <p>
                              {partner.description || "This organization has not provided a public description."}
                           </p>
                        </div>
                     </section>

                     <section className="user-profile__activity-item partner-profile__about-section">
                        <div className="user-profile__activity-copy">
                           <h3>Expertise</h3>
                           {expertiseAreas.length > 0 ? (
                              <ul className="partner-profile-expertise">
                                 {expertiseAreas.map((area, index) => (
                                    <li key={`${area}-${index}`}>{area}</li>
                                 ))}
                              </ul>
                           ) : (
                              <p>No public expertise areas have been listed.</p>
                           )}
                        </div>
                     </section>

                     {partner.website && (
                        <section className="user-profile__activity-item partner-profile__about-section">
                           <div className="user-profile__activity-copy">
                              <h3>Website</h3>
                              <a
                                 className="partner-profile-website"
                                 href={partner.website}
                                 target="_blank"
                                 rel="noopener noreferrer"
                              >
                                 Visit organization website
                                 <ExternalLink aria-hidden="true" />
                              </a>
                           </div>
                        </section>
                     )}

                     <aside className="user-profile__activity-item partner-profile-context">
                        <Info aria-hidden="true" />
                        <div>
                           <h3>Partnership context</h3>
                           <p>
                              This public profile indicates that the organization has chosen to maintain a public
                              presence on TruthLens. Partner participation does not automatically imply endorsement
                              of all TruthLens analyses, verdicts, or content.
                           </p>
                        </div>
                     </aside>
                  </div>
               )}
            </div>
         </section>
      </section>
   );
}

function PartnerProfilePage() {
   const { slug } = useParams();
   const location = useLocation();
   const previousSearch = location.state?.fromPartners;
   const isCommunity = location.pathname.startsWith("/community/partners/");
   const partnersPath =
      typeof previousSearch === "string" &&
      (previousSearch === "" || previousSearch.startsWith("?"))
         ? `/partners${previousSearch}`
         : "/partners";

   return (
      <div className={`partner-profile-page ${isCommunity ? "partner-profile-page--community" : ""}`}>
         <main className="user-profile partner-profile-main">
            {!isCommunity && (
               <Link to={partnersPath} className="partner-profile-back">
                  <ArrowLeft aria-hidden="true" />
                  Back to partners
               </Link>
            )}

            <PartnerProfileContent
               key={`${isCommunity ? "community" : "public"}-${slug}`}
               slug={slug}
               isCommunity={isCommunity}
            />
         </main>
      </div>
   );
}

export default PartnerProfilePage;
