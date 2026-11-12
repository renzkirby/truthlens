import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import { userFacingErrorMessage } from "../utils/userFacingError";
import "./CommunityModerationOutcomePage.css";

const formatter = new Intl.DateTimeFormat(undefined, {
   dateStyle: "medium",
   timeStyle: "short",
});

function formatDate(value) {
   if (!value) return "Not recorded";
   const date = new Date(value);
   return Number.isNaN(date.getTime()) ? "Not recorded" : formatter.format(date);
}

function CommunityModerationOutcomePage() {
   const { decisionId } = useParams();
   const { authFetch } = useAuth();
   const [outcome, setOutcome] = useState(null);
   const [error, setError] = useState(null);

   useEffect(() => {
      let active = true;
      authFetch(resolveApiEndpoint("COMMUNITY_MODERATION_OUTCOME", decisionId), {
         method: "GET",
      })
         .then((payload) => {
            if (!active) return;
            setOutcome(payload);
            setError(null);
         })
         .catch((requestError) => {
            if (active) setError(requestError);
         });

      return () => {
         active = false;
      };
   }, [authFetch, decisionId]);

   if (error) {
      return (
         <main className="community-outcome-page">
            <section className="community-outcome-state">
               <h1>Moderation outcome unavailable</h1>
               <p>
                  {userFacingErrorMessage(error, {
                     fallback: "We couldn't load this moderation outcome.",
                     notFoundMessage: "This moderation outcome is not available to this account.",
                  })}
               </p>
               <Link to="/notifications">Return to notifications</Link>
            </section>
         </main>
      );
   }

   if (!outcome) {
      return (
         <main className="community-outcome-page">
            <section className="community-outcome-state" role="status">
               <p>Loading moderation outcome…</p>
            </section>
         </main>
      );
   }

   const removed = outcome.action === "REMOVE";
   const isAuthor = outcome.role === "AUTHOR";
   const report = outcome.report;

   return (
      <main className="community-outcome-page">
         <div className="community-outcome-content">
            <Link className="community-outcome-back" to="/notifications">← Notifications</Link>

            <header className="community-outcome-header">
               <span>Platform Safety</span>
               <h1>
                  {isAuthor
                     ? removed ? "Your discussion was removed" : "Safety review completed"
                     : report?.outcome === "CONFIRMED"
                       ? "Your report was confirmed"
                       : "Your report was reviewed"}
               </h1>
               <p>Decision recorded {formatDate(outcome.decided_at)}</p>
            </header>

            <section className="community-outcome-card">
               <div className="community-outcome-heading">
                  <div>
                     <span>Decision</span>
                     <h2>{removed ? "Content removed" : "No violation found"}</h2>
                  </div>
                  <strong>{removed ? "Removed" : "Dismissed"}</strong>
               </div>

               {removed && outcome.policy?.violation_title ? (
                  <dl className="community-outcome-details">
                     <div>
                        <dt>Community Guidelines finding</dt>
                        <dd>{outcome.policy.violation_title}</dd>
                     </div>
                     <div>
                        <dt>Policy</dt>
                        <dd>{outcome.policy.title} · Version {outcome.policy.version}</dd>
                     </div>
                  </dl>
               ) : null}

               <div className="community-outcome-rationale">
                  <h3>Review reason</h3>
                  <p>{outcome.rationale}</p>
               </div>

               <Link to="/community-guidelines">Read the Community Guidelines</Link>
            </section>

            {isAuthor && outcome.content ? (
               <section className="community-outcome-card">
                  <span className="community-outcome-eyebrow">Affected discussion</span>
                  <h2>Content reviewed by Platform Safety</h2>
                  <blockquote>{outcome.content.excerpt || "Content excerpt unavailable."}</blockquote>
                  {removed ? (
                     <p className="community-outcome-helper">
                        The original discussion is no longer available in the Community feed.
                     </p>
                  ) : null}
               </section>
            ) : null}

            {!isAuthor && report ? (
               <section className="community-outcome-card">
                  <span className="community-outcome-eyebrow">Your report</span>
                  <h2>{report.reason_label}</h2>
                  {report.notes ? <p>{report.notes}</p> : <p>No additional notes were submitted.</p>}
                  <dl className="community-outcome-details">
                     <div>
                        <dt>Report outcome</dt>
                        <dd>{report.outcome_label}</dd>
                     </div>
                     <div>
                        <dt>Community reputation</dt>
                        <dd>
                           {report.counts_toward_reputation
                              ? "Counts as a confirmed report"
                              : "No reputation change"}
                        </dd>
                     </div>
                  </dl>
               </section>
            ) : null}
         </div>
      </main>
   );
}

export default CommunityModerationOutcomePage;
