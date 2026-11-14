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
   const [accountReviewOpen, setAccountReviewOpen] = useState(false);
   const [accountReviewStatement, setAccountReviewStatement] = useState("");
   const [accountReviewError, setAccountReviewError] = useState("");
   const [submittingAccountReview, setSubmittingAccountReview] = useState(false);

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

   const handleAccountReviewSubmit = async (event) => {
      event.preventDefault();
      const enforcement = outcome?.account_enforcement;
      const statement = accountReviewStatement.trim();

      if (!enforcement?.id) return;
      if (statement.length < 20) {
         setAccountReviewError(
            "Explain why the account action should be reviewed in at least 20 characters.",
         );
         return;
      }

      setSubmittingAccountReview(true);
      setAccountReviewError("");

      try {
         const updatedEnforcement = await authFetch(
            resolveApiEndpoint(
               "COMMUNITY_ACCOUNT_ENFORCEMENT_REVIEW",
               enforcement.id,
            ),
            {
               method: "POST",
               body: { request_statement: statement },
            },
         );
         setOutcome((current) => ({
            ...current,
            account_enforcement: updatedEnforcement,
         }));
         setAccountReviewOpen(false);
         setAccountReviewStatement("");
      } catch (reviewError) {
         setAccountReviewError(
            userFacingErrorMessage(reviewError, {
               fallback: "We couldn't submit this account-action review. Try again.",
               conflictMessage: "This account action can no longer accept a review request.",
               permissionMessage: "This account action cannot be reviewed by this account.",
               serviceMessage: "Account-action review is temporarily unavailable. Try again shortly.",
            }),
         );
      } finally {
         setSubmittingAccountReview(false);
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
   const accountEnforcement = outcome.account_enforcement || null;
   const accountActionLabel = accountEnforcement
      ? ({
           WARNING: "Community warning",
           TEMPORARY_RESTRICTION: "Temporary Community restriction",
           INDEFINITE_RESTRICTION: "Indefinite Community restriction",
        }[accountEnforcement.action] || accountEnforcement.action)
      : null;
   const accountReview = accountEnforcement?.review || null;

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

            {isAuthor && accountEnforcement ? (
               <section className="community-outcome-card community-account-action-card">
                  <span className="community-outcome-eyebrow">Community access action</span>
                  <div className="community-outcome-heading">
                     <div>
                        <h2>{accountActionLabel}</h2>
                        <p>
                           This account-level action is separate from the content-removal decision above.
                        </p>
                     </div>
                     <strong>
                        {accountEnforcement.state === "ACTIVE"
                           ? "Active"
                           : accountEnforcement.state === "EXPIRED"
                             ? "Expired"
                             : accountEnforcement.state === "REVOKED"
                               ? "No longer active"
                               : "Recorded"}
                     </strong>
                  </div>

                  <dl className="community-outcome-details">
                     <div>
                        <dt>Community Guidelines finding</dt>
                        <dd>{accountEnforcement.violation?.title || "Community Guidelines"}</dd>
                     </div>
                     <div>
                        <dt>Policy</dt>
                        <dd>
                           {accountEnforcement.policy?.title} · Version {accountEnforcement.policy?.version}
                        </dd>
                     </div>
                     {accountEnforcement.restriction_ends_at ? (
                        <div>
                           <dt>Restriction ends</dt>
                           <dd>{formatDate(accountEnforcement.restriction_ends_at)}</dd>
                        </div>
                     ) : null}
                  </dl>

                  <div className="community-outcome-rationale">
                     <h3>Why this account action was issued</h3>
                     <p>{accountEnforcement.user_rationale}</p>
                  </div>

                  {accountEnforcement.revoked_at ? (
                     <div className="community-account-action-update">
                        <h3>Account action updated</h3>
                        <p>{accountEnforcement.revocation_rationale}</p>
                        <small>Updated {formatDate(accountEnforcement.revoked_at)}</small>
                     </div>
                  ) : null}

                  {accountReview ? (
                     <div className="community-account-review-summary">
                        <h3>Account-action review</h3>
                        <p>
                           {accountReview.outcome
                              ? accountReview.outcome === "REVERSED"
                                 ? "Platform Safety reversed the account action."
                                 : "Platform Safety upheld the account action."
                              : "Your account-action review is pending Platform Safety review."}
                        </p>
                        {accountReview.resolution_rationale ? (
                           <div className="community-outcome-rationale">
                              <h3>Review explanation</h3>
                              <p>{accountReview.resolution_rationale}</p>
                           </div>
                        ) : null}
                        <div className="community-reconsideration-request">
                           <h3>Your request</h3>
                           <p>{accountReview.request_statement}</p>
                           <small>Submitted {formatDate(accountReview.submitted_at)}</small>
                        </div>
                     </div>
                  ) : null}

                  {accountEnforcement.can_request_review ? (
                     <>
                        <p className="community-outcome-helper">
                           You can request one review of this account action. This is separate
                           from asking Platform Safety to reconsider the content removal.
                        </p>
                        {!accountReviewOpen ? (
                           <button
                              type="button"
                              className="community-outcome-primary-action"
                              onClick={() => {
                                 setAccountReviewOpen(true);
                                 setAccountReviewError("");
                              }}
                           >
                              Request account-action review
                           </button>
                        ) : (
                           <form
                              className="community-reconsideration-form"
                              onSubmit={handleAccountReviewSubmit}
                           >
                              <label htmlFor="community-account-review-statement">
                                 Why should this account action be reviewed?
                              </label>
                              <textarea
                                 id="community-account-review-statement"
                                 value={accountReviewStatement}
                                 minLength={20}
                                 maxLength={3000}
                                 rows={6}
                                 required
                                 disabled={submittingAccountReview}
                                 onChange={(event) => {
                                    setAccountReviewStatement(event.target.value);
                                    setAccountReviewError("");
                                 }}
                              />
                              <div className="community-reconsideration-form-meta">
                                 <span>{accountReviewStatement.length}/3000</span>
                                 {accountReviewError ? (
                                    <strong role="alert">{accountReviewError}</strong>
                                 ) : null}
                              </div>
                              <div className="community-reconsideration-actions">
                                 <button
                                    type="button"
                                    className="community-outcome-secondary-action"
                                    disabled={submittingAccountReview}
                                    onClick={() => {
                                       setAccountReviewOpen(false);
                                       setAccountReviewStatement("");
                                       setAccountReviewError("");
                                    }}
                                 >
                                    Cancel
                                 </button>
                                 <button
                                    type="submit"
                                    className="community-outcome-primary-action"
                                    disabled={submittingAccountReview}
                                 >
                                    {submittingAccountReview ? "Submitting…" : "Submit review request"}
                                 </button>
                              </div>
                           </form>
                        )}
                     </>
                  ) : null}

                  <Link
                     to={`/community-guidelines?version=${encodeURIComponent(
                        accountEnforcement.policy?.version || outcome.policy?.version || "",
                     )}`}
                  >
                     Read the policy version used for this action
                  </Link>
               </section>
            ) : null}

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
                        Platform Safety will review the original removal again. The {targetLabel} remains removed
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
