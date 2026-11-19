import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import Icons from "../components/Icons.jsx";
import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import { userFacingErrorMessage } from "../utils/userFacingError";
import "./CommunityStandingPage.css";

const dateFormatter = new Intl.DateTimeFormat(undefined, {
   year: "numeric",
   month: "short",
   day: "numeric",
   hour: "numeric",
   minute: "2-digit",
   timeZoneName: "short",
});

function formatDateTime(value) {
   if (!value) return "Not recorded";
   const date = new Date(value);
   return Number.isNaN(date.getTime()) ? "Not recorded" : dateFormatter.format(date);
}

function accessDescription(access) {
   if (access?.status === "TEMPORARILY_RESTRICTED") {
      return `You can still read Community content, use Verify, and report unsafe content. New or edited Community contributions are restricted until ${formatDateTime(access.restriction_ends_at)}.`;
   }
   if (access?.status === "INDEFINITELY_RESTRICTED") {
      return "You can still read Community content, use Verify, and report unsafe content. New or edited Community contributions are restricted with no automatic end date.";
   }
   return "You can currently take part in the TruthLens Community normally.";
}

function reviewSummary(review) {
   if (!review) return null;
   if (review.outcome_label) return review.outcome_label;
   return review.status_label || "Review requested";
}

function policyRuleHref(item) {
   const version = String(item?.policy?.version || "").trim();
   const code = String(item?.violation?.code || "").trim();
   const query = version ? `?version=${encodeURIComponent(version)}` : "";
   const anchor = code
      ? `#rule-${code.toLowerCase().replaceAll("_", "-")}`
      : "";
   return `/community-guidelines${query}${anchor}`;
}

function CommunityStandingPage() {
   const { authFetch } = useAuth();
   const [standing, setStanding] = useState(null);
   const [error, setError] = useState(null);

   useEffect(() => {
      let active = true;
      authFetch(resolveApiEndpoint("COMMUNITY_STANDING"), { method: "GET" })
         .then((payload) => {
            if (!active) return;
            setStanding(payload);
            setError(null);
         })
         .catch((requestError) => {
            if (!active) return;
            setError(requestError);
         });
      return () => {
         active = false;
      };
   }, [authFetch]);

   const activeAction = useMemo(
      () => standing?.history?.find((item) => item.state === "ACTIVE") || null,
      [standing],
   );

   if (error) {
      return (
         <main className="community-standing-page">
            <section className="community-standing-state">
               <h1>Community Standing unavailable</h1>
               <p>
                  {userFacingErrorMessage(error, {
                     fallback: "We couldn't load your Community Standing.",
                     permissionMessage: "Community Standing is available to Community participants.",
                  })}
               </p>
               <Link to="/dashboard">Return to Dashboard</Link>
            </section>
         </main>
      );
   }

   if (!standing) {
      return (
         <main className="community-standing-page">
            <section className="community-standing-state" role="status">
               <p>Loading Community Standing…</p>
            </section>
         </main>
      );
   }

   const access = standing.access || {};
   const history = standing.history || [];
   const capabilities = standing.restriction_capabilities || {
      available: [],
      unavailable: [],
   };
   const restricted = access.status !== "FULL_ACCESS";

   return (
      <main className="community-standing-page">
         <div className="community-standing-content">
            <Link className="community-standing-back" to="/dashboard">
               ← Dashboard
            </Link>

            <header className="community-standing-header">
               <span>TruthLens Community</span>
               <h1>Community Standing</h1>
               <p>Your current Community access and account-level Safety actions.</p>
            </header>

            <section className="community-standing-access" aria-labelledby="community-standing-access-title">
               <div className="community-standing-access-icon" aria-hidden="true">
                  <Icons name={restricted ? "shield" : "shield-check"} size={22} />
               </div>
               <div>
                  <span>Current access</span>
                  <h2 id="community-standing-access-title">{access.label || "Full access"}</h2>
                  <p>{accessDescription(access)}</p>
                  {activeAction?.safety_decision_id ? (
                     <Link to={`/community/moderation/outcomes/${activeAction.safety_decision_id}`}>
                        View related decision
                     </Link>
                  ) : null}
               </div>
            </section>

            {restricted ? (
               <section className="community-standing-capabilities" aria-labelledby="community-standing-capabilities-title">
                  <div className="community-standing-section-heading">
                     <span>While restricted</span>
                     <h2 id="community-standing-capabilities-title">What you can still do</h2>
                     <p>The restriction applies to Community participation, not your whole TruthLens account.</p>
                  </div>

                  <div className="community-standing-capability-grid">
                     <div>
                        <h3>Still available</h3>
                        <ul>
                           {capabilities.available.map((item) => (
                              <li key={item.code}>
                                 <Icons name="check-circle" size={16} aria-hidden="true" />
                                 <span>{item.label}</span>
                              </li>
                           ))}
                        </ul>
                     </div>
                     <div>
                        <h3>Not available while restricted</h3>
                        <ul>
                           {capabilities.unavailable.map((item) => (
                              <li key={item.code}>
                                 <Icons name="x-circle" size={16} aria-hidden="true" />
                                 <span>{item.label}</span>
                              </li>
                           ))}
                        </ul>
                     </div>
                  </div>
               </section>
            ) : null}

            <section className="community-standing-history" aria-labelledby="community-standing-history-title">
               <div className="community-standing-section-heading community-standing-history-heading">
                  <div>
                     <span>Account actions</span>
                     <h2 id="community-standing-history-title">History</h2>
                     <p>Warnings and Community restrictions recorded for your account.</p>
                  </div>
                  <Link to="/community-guidelines">Read Community Guidelines</Link>
               </div>

               {history.length === 0 ? (
                  <div className="community-standing-empty">
                     <Icons name="shield-check" size={20} aria-hidden="true" />
                     <div>
                        <strong>No account-level Safety actions</strong>
                        <p>You have no warning or Community restriction history.</p>
                     </div>
                  </div>
               ) : (
                  <div className="community-standing-action-list">
                     {history.map((item) => {
                        const reviewText = reviewSummary(item.review);
                        return (
                           <article key={item.id} className="community-standing-action">
                              <div className="community-standing-action-heading">
                                 <div>
                                    <h3>{item.action_label || item.action}</h3>
                                    <span>{item.state_label || item.state}</span>
                                 </div>
                                 <time dateTime={item.issued_at}>{formatDateTime(item.issued_at)}</time>
                              </div>

                              <dl className="community-standing-action-details">
                                 <div>
                                    <dt>Guidelines finding</dt>
                                    <dd>{item.violation?.title || "Community Guidelines"}</dd>
                                 </div>
                                 <div>
                                    <dt>Policy</dt>
                                    <dd>Version {item.policy?.version || "Not recorded"}</dd>
                                 </div>
                                 {item.restriction_ends_at ? (
                                    <div>
                                       <dt>Restriction ends</dt>
                                       <dd>{formatDateTime(item.restriction_ends_at)}</dd>
                                    </div>
                                 ) : null}
                                 {item.state_reason_label ? (
                                    <div>
                                       <dt>Why it ended</dt>
                                       <dd>{item.state_reason_label}</dd>
                                    </div>
                                 ) : null}
                                 {reviewText ? (
                                    <div>
                                       <dt>Account-action review</dt>
                                       <dd>{reviewText}</dd>
                                    </div>
                                 ) : null}
                              </dl>

                              <div className="community-standing-rationale">
                                 <h4>Why this action was issued</h4>
                                 <p>{item.user_rationale}</p>
                              </div>

                              {item.action === "WARNING" ? (
                                 <p className="community-standing-note">
                                    A warning does not restrict your access now. It stays in your Safety history and may be considered by a human reviewer if a later confirmed violation needs an account-level decision.
                                 </p>
                              ) : null}

                              {item.revocation_rationale ? (
                                 <div className="community-standing-update">
                                    <strong>Action update</strong>
                                    <p>{item.revocation_rationale}</p>
                                 </div>
                              ) : null}

                              <div className="community-standing-action-links">
                                 {item.safety_decision_id ? (
                                    <Link to={`/community/moderation/outcomes/${item.safety_decision_id}`}>
                                       View decision
                                    </Link>
                                 ) : null}
                                 <Link to={policyRuleHref(item)}>
                                    View policy rule
                                 </Link>
                              </div>
                           </article>
                        );
                     })}
                  </div>
               )}
            </section>
         </div>
      </main>
   );
}

export default CommunityStandingPage;
