import { useEffect, useRef, useState } from "react";
import {
   AlertTriangle,
   ArrowRight,
   ExternalLink,
   FileClock,
   History,
   Info,
   RefreshCw,
   ShieldCheck,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import PartnerLogo from "../components/partners/PartnerLogo";
import { useAuth } from "../hooks/useAuth";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { resolveApiEndpoint } from "../utils/api";
import { createPublicReachEventId, recordPublicReach } from "../utils/publicReach";
import "./PublicFactCheckPage.css";

const VERDICT_META = {
   FACT: { label: "Fact", className: "fact", mark: "✓" },
   FAKE: { label: "Fake", className: "fake", mark: "×" },
   MISLEADING: { label: "Misleading", className: "misleading", mark: "!" },
   SATIRE: { label: "Satire", className: "satire", mark: "~" },
   UNVERIFIED: { label: "Unverified", className: "unverified", mark: "?" },
   OUT_OF_SCOPE: { label: "Out of scope", className: "out-of-scope", mark: "—" },
};

const REVISION_LABELS = {
   INITIAL: "Initial publication",
   EDITORIAL_REVISION: "Editorial revision",
   FACTUAL_CORRECTION: "Factual correction",
};

const SOURCE_ORIGIN_LABELS = {
   DECISION_EVIDENCE: "Decision evidence",
   ORGANIZATION_EDITORIAL: "Organization editorial source",
   LEGACY_IMPORT: "Legacy imported source",
   UNKNOWN: "Source origin unavailable",
};

const CITATION_STATE_LABELS = {
   CITED_IN_ARTICLE: "Cited in article",
   NOT_CITED_IN_ARTICLE: "Not cited in article",
   CITATION_HISTORY_UNAVAILABLE: "Citation history unavailable",
};

function formatDateTime(value, fallback = "Publication time unavailable") {
   if (!value) return fallback;

   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return fallback;

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function publicationStateLabel(value) {
   if (value === "CURRENT") return "Current publication";
   if (value === "SUPERSEDED") return "Historical version";
   return "Publication state unavailable";
}

function revisionLabel(value) {
   return REVISION_LABELS[value] || "Revision kind unavailable";
}

function sourceOriginLabel(value) {
   return SOURCE_ORIGIN_LABELS[value] || "Source origin unavailable";
}

function citationStateLabel(value) {
   return CITATION_STATE_LABELS[value] || "Citation history unavailable";
}

function safeSource(value) {
   if (typeof value !== "string" || !value.trim()) return null;

   try {
      const parsed = new URL(value);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
         return null;
      }
      return {
         href: parsed.href,
         hostname: parsed.hostname,
      };
   } catch {
      return null;
   }
}

function routeForVersion(organizationSlug, publicationId) {
   return `/partners/${encodeURIComponent(organizationSlug)}/fact-checks/${encodeURIComponent(publicationId)}`;
}

function Verdict({ value, compact = false }) {
   const meta = VERDICT_META[value] || {
      label: "Unknown verdict",
      className: "unknown",
      mark: "•",
   };

   if (compact) {
      return (
         <span className={`public-fact-check-verdict-compact public-fact-check-verdict-compact--${meta.className}`}>
            <span aria-hidden="true">{meta.mark}</span>
            {meta.label}
         </span>
      );
   }

   return (
      <div className={`public-fact-check-verdict public-fact-check-verdict--${meta.className}`}>
         <span className="public-fact-check-verdict__label">Human factual verdict</span>
         <div className="public-fact-check-verdict__value">
            <span className="public-fact-check-verdict__mark" aria-hidden="true">
               {meta.mark}
            </span>
            <strong>{meta.label}</strong>
         </div>
      </div>
   );
}

function FactualState({ label, item }) {
   if (!item) return null;

   return (
      <div className="public-fact-check-factual-state">
         <p className="public-fact-check-factual-state__label">{label}</p>
         <Verdict value={item.verdict} compact />
         <blockquote>{item.canonical_claim}</blockquote>
      </div>
   );
}

function ArticleBody({ value }) {
   const paragraphs = typeof value === "string" ? value.split(/\n\s*\n/).filter((paragraph) => paragraph.trim()) : [];

   if (paragraphs.length === 0) {
      return <p className="public-fact-check-body-empty">No article body was published.</p>;
   }

   return (
      <div className="public-fact-check-body">
         {paragraphs.map((paragraph, index) => (
            <p key={index}>{paragraph}</p>
         ))}
      </div>
   );
}

function SourceItem({ source }) {
   const safeUrl = safeSource(source?.url);
   const title = typeof source?.title === "string" ? source.title.trim() : "";

   return (
      <li className="public-fact-check-source">
         {title && <h3>{title}</h3>}
         <div className="public-fact-check-source__location">
            {safeUrl ? (
               <a
                  href={safeUrl.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={title ? `Open source: ${title}` : `Open source: ${safeUrl.hostname}`}
               >
                  <span>{safeUrl.hostname}</span>
                  <ExternalLink aria-hidden="true" />
               </a>
            ) : (
               <span>{source?.url || "Source URL unavailable"}</span>
            )}
            {safeUrl && <small>{source.url}</small>}
         </div>
         <ul className="public-fact-check-source__metadata" aria-label="Source provenance">
            <li>{sourceOriginLabel(source?.source_origin)}</li>
            <li>{citationStateLabel(source?.citation_state)}</li>
         </ul>
      </li>
   );
}

function PublicFactCheckPage() {
   const { slug, publicationId } = useParams();
   const { authFetch } = useAuth();
   const [detailState, setDetailState] = useState(null);
   const [errorState, setErrorState] = useState(null);
   const [isLoading, setIsLoading] = useState(true);
   const [retryVersion, setRetryVersion] = useState(0);
   const [focusRouteKey, setFocusRouteKey] = useState(null);
   const requestIdRef = useRef(0);
   const reachAttemptRef = useRef(null);
   const historyFocusTargetRef = useRef(null);
   const headingRef = useRef(null);
   const routeKey = `${slug}/${publicationId}`;
   const detail = detailState?.routeKey === routeKey ? detailState.data : null;
   const error = errorState?.routeKey === routeKey ? errorState.type : null;
   const showLoading = isLoading || (!detail && !error);

   let documentTitle = "Published Fact-Check | TruthLens";
   if (detail?.article?.headline && detail?.organization?.name) {
      documentTitle = `${detail.article.headline} | ${detail.organization.name} | TruthLens`;
   } else if (error) {
      documentTitle = "Published Fact-Check Unavailable | TruthLens";
   }
   useDocumentTitle(documentTitle);

   useEffect(() => {
      const requestId = ++requestIdRef.current;
      if (reachAttemptRef.current?.routeKey !== routeKey) {
         reachAttemptRef.current = { routeKey, eventId: createPublicReachEventId() };
      }
      const reachEventId = reachAttemptRef.current.eventId;

      authFetch(resolveApiEndpoint("PUBLIC_PARTNER_FACT_CHECK_DETAIL", slug, publicationId))
         .then((response) => {
            if (requestId !== requestIdRef.current) return;
            if (!response?.article || response?.organization?.slug !== slug
               || typeof response?.selected_publication_id !== "string"
               || response.selected_publication_id.toLowerCase() !== publicationId.toLowerCase()) {
               throw new Error("The public publication response is incomplete.");
            }

            setDetailState({ routeKey, data: response, reachEventId });
            if (historyFocusTargetRef.current === routeKey) {
               historyFocusTargetRef.current = null;
               setFocusRouteKey(routeKey);
            }
         })
         .catch((requestError) => {
            if (requestId !== requestIdRef.current) return;
            setErrorState({
               routeKey,
               type: requestError?.status === 404 ? "unavailable" : "request",
            });
         })
         .finally(() => {
            if (requestId === requestIdRef.current) setIsLoading(false);
         });

      return () => {
         requestIdRef.current += 1;
      };
   }, [authFetch, publicationId, retryVersion, routeKey, slug]);

   useEffect(() => {
      if (!detail || error || showLoading || reachAttemptRef.current?.routeKey !== routeKey
         || detailState.reachEventId !== reachAttemptRef.current.eventId) return;
      void recordPublicReach({
         clientEventId: detailState.reachEventId,
         eventType: "PUBLICATION_VIEW",
         sourceSurface: "PUBLIC_FACT_CHECK_PAGE",
         organizationSlug: detail.organization.slug,
         publicationId: detail.selected_publication_id,
      });
   }, [detail, detailState, error, routeKey, showLoading]);

   useEffect(() => {
      if (!detail || focusRouteKey !== routeKey) return undefined;

      const frameId = window.requestAnimationFrame(() => {
         headingRef.current?.scrollIntoView({ behavior: "auto", block: "start" });
         headingRef.current?.focus({ preventScroll: true });
         setFocusRouteKey(null);
      });
      return () => window.cancelAnimationFrame(frameId);
   }, [detail, focusRouteKey, routeKey]);

   const retry = () => {
      setDetailState(null);
      setErrorState(null);
      setIsLoading(true);
      setRetryVersion((value) => value + 1);
   };

   if (showLoading) {
      return (
         <div className="public-fact-check-page">
            <section className="public-fact-check-state" aria-busy="true" aria-live="polite">
               <div className="public-fact-check-state__mark" aria-hidden="true">
                  <ShieldCheck />
               </div>
               <h1>Published fact-check</h1>
               <p>Loading institutional publication…</p>
            </section>
         </div>
      );
   }

   if (error) {
      const unavailable = error === "unavailable";
      return (
         <div className="public-fact-check-page">
            <section className="public-fact-check-state" role="alert">
               <div className="public-fact-check-state__mark" aria-hidden="true">
                  <FileClock />
               </div>
               <h1>Published fact-check unavailable</h1>
               <p>
                  {unavailable
                     ? "This publication could not be found or is not currently available publicly."
                     : "We could not load this published fact-check. Please try again."}
               </p>
               <div className="public-fact-check-state__actions">
                  {!unavailable && (
                     <button type="button" onClick={retry}>
                        <RefreshCw aria-hidden="true" />
                        Retry
                     </button>
                  )}
                  <Link to="/partners">Browse public partners</Link>
               </div>
            </section>
         </div>
      );
   }

   const organization = detail.organization;
   const article = detail.article || {};
   const decision = detail.decision || {};
   const lineage = Array.isArray(detail.lineage) ? detail.lineage : [];
   const selectedIndex = lineage.findIndex(
      (item) => String(item?.publication_id) === String(detail.selected_publication_id),
   );
   const currentLineageItem = lineage.find(
      (item) => String(item?.publication_id) === String(detail.current_publication_id),
   );
   const laterFactualCorrection =
      selectedIndex >= 0
         ? lineage.slice(selectedIndex + 1).find((item) => item?.revision_kind === "FACTUAL_CORRECTION")
         : null;
   const selectedPredecessor = selectedIndex > 0 ? lineage[selectedIndex - 1] : null;
   const isCurrent = detail.history_state === "CURRENT";
   const selectedIsCorrection = article.revision_kind === "FACTUAL_CORRECTION";
   const hasCorrectionHistory = lineage.some((item) => item?.revision_kind === "FACTUAL_CORRECTION");
   const sources = Array.isArray(detail.sources) ? detail.sources : [];
   const currentRoute = routeForVersion(organization.slug, detail.current_publication_id);

   const markHistoryNavigation = (item) => {
      if (item?.publication_id) {
         historyFocusTargetRef.current = `${organization.slug}/${item.publication_id}`;
      }
   };

   return (
      <div className="public-fact-check-page">
         <div className="public-fact-check-layout">
            <nav className="public-fact-check-breadcrumb" aria-label="Breadcrumb">
               <ol>
                  <li>
                     <Link to="/partners">Partners</Link>
                  </li>
                  <li aria-hidden="true">/</li>
                  <li>
                     <Link to={`/partners/${encodeURIComponent(organization.slug)}`}>{organization.name}</Link>
                  </li>
               </ol>
            </nav>

            <article className="public-fact-check-document">
               <header className="public-fact-check-header">
                  <div className="public-fact-check-kicker-row">
                     <p className="public-fact-check-kicker">
                        <ShieldCheck aria-hidden="true" />
                        Institutional fact-check
                     </p>
                     <p className="public-fact-check-version-state">
                        Article v{article.version} · {publicationStateLabel(detail.history_state)}
                     </p>
                  </div>

                  <div className="public-fact-check-claim">
                     <p className="public-fact-check-micro-label">Claim</p>
                     <blockquote>“{decision.canonical_claim}”</blockquote>
                  </div>

                  <Verdict value={decision.verdict} />

                  <div className="public-fact-check-attribution">
                     <p className="public-fact-check-micro-label">Published by</p>
                     <div className="public-fact-check-attribution__row">
                        <Link
                           className="public-fact-check-attribution__identity"
                           to={`/partners/${encodeURIComponent(organization.slug)}`}
                        >
                           <PartnerLogo logoUrl={organization.logo_url} organizationName={organization.name} />
                           <span>
                              <strong>{organization.name}</strong>
                              <span>{organization.organization_type_label}</span>
                           </span>
                        </Link>
                        <time dateTime={detail.published_at}>Published {formatDateTime(detail.published_at)}</time>
                     </div>
                  </div>

                  <div className="public-fact-check-article-intro">
                     <h1 ref={headingRef} tabIndex={-1} className="public-fact-check-title">
                        {article.headline}
                     </h1>
                     {article.summary && <p className="public-fact-check-summary">{article.summary}</p>}
                  </div>
               </header>

               {detail.history_state === "SUPERSEDED" && (
                  <aside
                     className={`public-fact-check-notice ${laterFactualCorrection ? "public-fact-check-notice--correction" : "public-fact-check-notice--historical"}`}
                     aria-labelledby="historical-version-heading"
                  >
                     <div className="public-fact-check-notice__heading">
                        {laterFactualCorrection ? (
                           <AlertTriangle aria-hidden="true" />
                        ) : (
                           <FileClock aria-hidden="true" />
                        )}
                        <div>
                           <h2 id="historical-version-heading">
                              {laterFactualCorrection
                                 ? "This factual conclusion was later corrected"
                                 : "You are reading a historical version"}
                           </h2>
                           <p>
                              This version is preserved for transparency and is no longer the current institutional
                              publication.
                           </p>
                        </div>
                     </div>
                     {laterFactualCorrection && currentLineageItem && (
                        <div className="public-fact-check-notice__current-state">
                           <FactualState label="Current factual state" item={currentLineageItem} />
                        </div>
                     )}
                     <Link to={currentRoute} onClick={() => markHistoryNavigation(currentLineageItem)}>
                        Read the current publication
                        <ArrowRight aria-hidden="true" />
                     </Link>
                  </aside>
               )}

               {selectedIsCorrection && selectedPredecessor && (
                  <aside className="public-fact-check-correction" aria-labelledby="factual-correction-heading">
                     <div className="public-fact-check-correction__heading">
                        <AlertTriangle aria-hidden="true" />
                        <div>
                           <h2 id="factual-correction-heading">
                              {isCurrent ? "Factual correction" : "Factual correction in this version"}
                           </h2>
                           {detail.revision?.requested_at && (
                              <p>Correction requested {formatDateTime(detail.revision.requested_at)}</p>
                           )}
                        </div>
                     </div>

                     <p className="public-fact-check-correction__intro">
                        The organization changed its published factual conclusion through an accountable correction.
                     </p>

                     <div className="public-fact-check-transition">
                        <FactualState label="Previous factual state" item={selectedPredecessor} />
                        <ArrowRight className="public-fact-check-transition__arrow" aria-hidden="true" />
                        <FactualState
                           label="Corrected factual state"
                           item={{
                              verdict: decision.verdict,
                              canonical_claim: decision.canonical_claim,
                           }}
                        />
                     </div>

                     {detail.revision?.reason && (
                        <div className="public-fact-check-correction__reason">
                           <h3>Why this changed</h3>
                           <p>{detail.revision.reason}</p>
                        </div>
                     )}
                  </aside>
               )}

               {isCurrent && !selectedIsCorrection && hasCorrectionHistory && (
                  <aside className="public-fact-check-history-note" aria-labelledby="correction-history-heading">
                     <History aria-hidden="true" />
                     <div>
                        <h2 id="correction-history-heading">Factual correction history</h2>
                        <p>
                           This publication lineage includes a factual correction. The exact correction version and
                           reason remain available in the publication record below.
                        </p>
                        <a href="#publication-history">Review publication history</a>
                     </div>
                  </aside>
               )}

               {detail.revision?.kind === "EDITORIAL_REVISION" && (
                  <aside className="public-fact-check-editorial-update" aria-labelledby="editorial-update-heading">
                     <Info aria-hidden="true" />
                     <div>
                        <h2 id="editorial-update-heading">Editorial update</h2>
                        {detail.revision.reason && <p>{detail.revision.reason}</p>}
                        <p className="public-fact-check-editorial-update__metadata">
                           Updated from Article v{detail.revision.predecessor?.version}
                           {detail.revision.requested_at
                              ? ` · Requested ${formatDateTime(detail.revision.requested_at)}`
                              : ""}
                        </p>
                     </div>
                  </aside>
               )}

               <section className="public-fact-check-section" aria-labelledby="article-body-heading">
                  <h2 id="article-body-heading">Full analysis</h2>
                  <ArticleBody value={article.article_body} />
               </section>

               <section className="public-fact-check-section" aria-labelledby="sources-heading">
                  <div className="public-fact-check-section__heading">
                     <h2 id="sources-heading">Sources</h2>
                     <p>Decision evidence and article citation are separate provenance records.</p>
                  </div>
                  {sources.length > 0 ? (
                     <ul className="public-fact-check-sources">
                        {sources.map((source, index) => (
                           <SourceItem key={`${source?.url || "source"}-${index}`} source={source} />
                        ))}
                     </ul>
                  ) : (
                     <p className="public-fact-check-empty">No public sources are listed for this publication.</p>
                  )}
               </section>

               <section className="public-fact-check-section public-fact-check-record" aria-labelledby="record-heading">
                  <div className="public-fact-check-section__heading">
                     <h2 id="record-heading">Publication record</h2>
                     <p>Public publication details and the complete institutionally published lineage.</p>
                  </div>

                  <dl className="public-fact-check-record__summary">
                     <div>
                        <dt>Published by</dt>
                        <dd>
                           <Link to={`/partners/${encodeURIComponent(organization.slug)}`}>{organization.name}</Link>
                        </dd>
                     </div>
                     <div>
                        <dt>Published at</dt>
                        <dd>
                           <time dateTime={detail.published_at}>{formatDateTime(detail.published_at)}</time>
                        </dd>
                     </div>
                     <div>
                        <dt>Article version</dt>
                        <dd>Article v{article.version}</dd>
                     </div>
                     <div>
                        <dt>Revision kind</dt>
                        <dd>{revisionLabel(article.revision_kind)}</dd>
                     </div>
                     <div>
                        <dt>Publication state</dt>
                        <dd>{publicationStateLabel(detail.history_state)}</dd>
                     </div>
                  </dl>

                  <nav id="publication-history" className="public-fact-check-history" aria-labelledby="history-heading">
                     <div className="public-fact-check-history__heading">
                        <h3 id="history-heading">Version history</h3>
                        <p>Only versions that were institutionally published appear here.</p>
                     </div>
                     <ol>
                        {lineage.map((item) => {
                           const selected = String(item?.publication_id) === String(detail.selected_publication_id);
                           return (
                              <li
                                 key={item.publication_id}
                                 className={[
                                    item.revision_kind === "FACTUAL_CORRECTION"
                                       ? "public-fact-check-history__item--correction"
                                       : "",
                                    item.history_state === "CURRENT" ? "public-fact-check-history__item--current" : "",
                                    selected ? "public-fact-check-history__item--selected" : "",
                                 ]
                                    .filter(Boolean)
                                    .join(" ")}
                              >
                                 <span className="public-fact-check-history__marker" aria-hidden="true" />
                                 <Link
                                    to={routeForVersion(organization.slug, item.publication_id)}
                                    aria-current={selected ? "page" : undefined}
                                    onClick={() => {
                                       if (!selected) markHistoryNavigation(item);
                                    }}
                                 >
                                    <div className="public-fact-check-history__title-row">
                                       <strong>Article v{item.version}</strong>
                                       <span>·</span>
                                       <span>{publicationStateLabel(item.history_state)}</span>
                                    </div>
                                    <div className="public-fact-check-history__meta-row">
                                       <span>{revisionLabel(item.revision_kind)}</span>
                                       <span>·</span>
                                       <time dateTime={item.published_at}>{formatDateTime(item.published_at)}</time>
                                    </div>
                                    {item.headline && <h4>{item.headline}</h4>}
                                    <Verdict value={item.verdict} compact />
                                    {item.revision_reason && (
                                       <p>
                                          <strong>
                                             {item.revision_kind === "FACTUAL_CORRECTION"
                                                ? "Correction reason:"
                                                : "Revision reason:"}
                                          </strong>{" "}
                                          {item.revision_reason}
                                       </p>
                                    )}
                                 </Link>
                              </li>
                           );
                        })}
                     </ol>
                  </nav>
               </section>
            </article>
         </div>
      </div>
   );
}

export default PublicFactCheckPage;
