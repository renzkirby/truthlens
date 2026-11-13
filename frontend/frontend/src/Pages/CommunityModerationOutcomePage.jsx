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
   const [requestOpen, setRequestOpen] = useState(false);
   const [requestStatement, setRequestStatement] = useState("");
   const [requestError, setRequestError] = useState("");
   const [submittingRequest, setSubmittingRequest] = useState(false);

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
         .catch((requestErrorValue) => {
            if (active) setError(requestErrorValue);
         });

      return () => {
         active = false;
      };
   }, [authFetch, decisionId]);

   const handleRequestSubmit = async (event) => {
      event.preventDefault();
      const statement = requestStatement.trim();

      if (statement.length < 20) {
         setRequestError("Explain why the removal should be reviewed again in at least 20 characters.");
         return;
      }

      setSubmittingRequest(true);
      setRequestError("");

      try {
         const payload = await authFetch(
            resolveApiEndpoint("COMMUNITY_MODERATION_RECONSIDERATION", decisionId),
            {
               method: "POST",
               body: { request_statement: statement },
            },
         );
         setOutcome(payload);
         setRequestOpen(false);
         setRequestStatement("");
      } catch (requestErrorValue) {
         setRequestError(
            userFacingErrorMessage(requestErrorValue, {
               fallback: "We couldn't submit this reconsideration request. Try again.",
               conflictMessage: "This removal can no longer accept a reconsideration request.",
               permissionMessage: "This moderation outcome cannot be reconsidered by this account.",
               serviceMessage: "Reconsideration is temporarily unavailable. Try again shortly.",
            }),
         );
      } finally {
         setSubmittingRequest(false);
      }
   };

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
   const targetType = outcome.target?.type || outcome.content?.target_type || "THREAD";
   const targetLabel = targetType === "COMMENT" ? "comment" : targetType === "EVIDENCE" ? "evidence" : "discussion";
   const targetLabelTitle = targetLabel.charAt(0).toUpperCase() + targetLabel.slice(1);
   const restoredTargetUrl =
      targetType === "COMMENT"
         ? `/thread/detail/${outcome.target?.thread_id || outcome.content?.thread_id}?tab=comments#comment-${outcome.target?.id || outcome.content?.target_id}`
         : targetType === "EVIDENCE"
           ? `/thread/detail/${outcome.target?.thread_id || outcome.content?.thread_id}?tab=evidence`
           : `/thread/detail/${outcome.target?.thread_id || outcome.content?.thread_id}`;
   const report = outcome.report;
   const reconsideration = outcome.reconsideration;
   const reversed = reconsideration?.outcome === "REVERSED";
   const reconsiderationPending = reconsideration?.status === "SUBMITTED";

   const heading = (() => {
      if (reversed) {
         return isAuthor ? `Your ${targetLabel} was restored` : "Moderation decision updated";
      }
      if (isAuthor) {
         return removed ? `Your ${targetLabel} was removed` : "Safety review completed";
      }
      if (report?.outcome === "CONFIRMED") return "Your report was confirmed";
      if (report?.outcome === "NOT_CONFIRMED") return "The content you reported was removed";
      return "Your report was reviewed";
   })();

   return (
      <main className="community-outcome-page">
         <div className="community-outcome-content">
            <Link className="community-outcome-back" to="/notifications">← Notifications</Link>

            <header className="community-outcome-header">
               <span>Platform Safety</span>
               <h1>{heading}</h1>
               <p>Original decision recorded {formatDate(outcome.decided_at)}</p>
            </header>

            <section className="community-outcome-card">
               <div className="community-outcome-heading">
                  <div>
                     <span>Original decision</span>
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

            {reconsideration ? (
               <section className="community-outcome-card community-reconsideration-card">
                  <span className="community-outcome-eyebrow">Reconsideration</span>
                  <div className="community-outcome-heading">
                     <div>
                        <h2>
                           {reconsiderationPending
                              ? "Reconsideration requested"
                              : reconsideration.outcome === "REVERSED"
                                ? "Removal reversed"
                                : "Removal upheld"}
                        </h2>
                     </div>
                     <strong>
                        {reconsiderationPending
                           ? "Under review"
                           : reconsideration.outcome === "REVERSED"
                             ? "Restored"
                             : "Upheld"}
                     </strong>
                  </div>

                  {reconsiderationPending ? (
                     <p>
                        Platform Safety will review the original removal again. The discussion remains removed
                        while the reconsideration is pending.
                     </p>
                  ) : (
                     <>
                        <p>
                           {reconsideration.outcome === "REVERSED"
                              ? "Platform Safety reversed the original removal and restored the content."
                              : "Platform Safety reviewed the request and kept the original removal in place."}
                        </p>
                        <div className="community-outcome-rationale">
                           <h3>Reconsideration explanation</h3>
                           <p>{reconsideration.resolution_rationale}</p>
                        </div>
                     </>
                  )}

                  {isAuthor && reconsideration.request_statement ? (
                     <div className="community-reconsideration-request">
                        <h3>Your request</h3>
                        <p>{reconsideration.request_statement}</p>
                        <small>Submitted {formatDate(reconsideration.submitted_at)}</small>
                     </div>
                  ) : null}
               </section>
            ) : null}

            {isAuthor && outcome.can_request_reconsideration ? (
               <section className="community-outcome-card">
                  <span className="community-outcome-eyebrow">Reconsideration</span>
                  <h2>Think this removal was a mistake?</h2>
                  <p>
                     You can request one reconsideration of this removal. Explain what Platform Safety
                     should review again. The content stays removed while the request is reviewed.
                  </p>

                  {!requestOpen ? (
                     <button
                        type="button"
                        className="community-outcome-primary-action"
                        onClick={() => {
                           setRequestOpen(true);
                           setRequestError("");
                        }}
                     >
                        Request reconsideration
                     </button>
                  ) : (
                     <form className="community-reconsideration-form" onSubmit={handleRequestSubmit}>
                        <label htmlFor="community-reconsideration-statement">
                           Why should this decision be reconsidered?
                        </label>
                        <textarea
                           id="community-reconsideration-statement"
                           value={requestStatement}
                           minLength={20}
                           maxLength={2000}
                           rows={6}
                           required
                           disabled={submittingRequest}
                           onChange={(event) => {
                              setRequestStatement(event.target.value);
                              setRequestError("");
                           }}
                        />
                        <div className="community-reconsideration-form-meta">
                           <span>{requestStatement.length}/2000</span>
                           {requestError ? <strong role="alert">{requestError}</strong> : null}
                        </div>
                        <div className="community-reconsideration-actions">
                           <button
                              type="button"
                              className="community-outcome-secondary-action"
                              disabled={submittingRequest}
                              onClick={() => {
                                 setRequestOpen(false);
                                 setRequestStatement("");
                                 setRequestError("");
                              }}
                           >
                              Cancel
                           </button>
                           <button
                              type="submit"
                              className="community-outcome-primary-action"
                              disabled={submittingRequest}
                           >
                              {submittingRequest ? "Submitting…" : "Submit request"}
                           </button>
                        </div>
                     </form>
                  )}
               </section>
            ) : null}

            {isAuthor && outcome.content ? (
               <section className="community-outcome-card">
                  <span className="community-outcome-eyebrow">Affected {targetLabel}</span>
                  <h2>{targetLabelTitle} reviewed by Platform Safety</h2>
                  <blockquote>{outcome.content.excerpt || "Content excerpt unavailable."}</blockquote>
                  {reversed ? (
                     <div className="community-outcome-restored">
                        <p className="community-outcome-helper">
                           The {targetLabel} was restored after reconsideration.
                        </p>
                        <Link to={restoredTargetUrl}>
                           View restored {targetLabel}
                        </Link>
                     </div>
                  ) : removed ? (
                     <p className="community-outcome-helper">
                        The original {targetLabel} is no longer available in Community circulation.
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
                              : reversed && report.outcome === "CONFIRMED"
                                ? "No longer counts toward reputation"
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
