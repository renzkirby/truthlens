import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import { resolveApiEndpoint } from "../../utils/api";
import { userFacingErrorMessage } from "../../utils/userFacingError";
import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";
import Select from "../ui/Select.jsx";
import Textarea from "../ui/Textarea.jsx";

const ACTION_LABELS = {
   WARNING: "Warning",
   TEMPORARY_RESTRICTION: "Temporary Community restriction",
   INDEFINITE_RESTRICTION: "Indefinite Community restriction",
};

const STATE_LABELS = {
   ACTIVE: "Active",
   EXPIRED: "Expired",
   REVOKED: "No longer active",
   WARNING: "Recorded",
};

function formatDateTime(value) {
   if (!value) return "";
   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "";
   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function accountActionError(error, fallback) {
   return userFacingErrorMessage(error, {
      fallback,
      authMessage: "Your session expired. Sign in again to continue Platform Safety review.",
      permissionMessage: "Your account does not have permission to manage Community account actions.",
      conflictMessage: "This account action changed before your request completed. Refresh and review the latest state.",
      serviceMessage: "Community account enforcement is temporarily unavailable. Try again shortly.",
   });
}

export function SafetyAccountActionForm({
   detail,
   safetyFetch,
   onUpdated,
}) {
   const { addToast } = useNotification();
   const [action, setAction] = useState("");
   const [durationCode, setDurationCode] = useState("24_HOURS");
   const [userRationale, setUserRationale] = useState("");
   const [internalNote, setInternalNote] = useState("");
   const [confirmIndefinite, setConfirmIndefinite] = useState(false);
   const [submitting, setSubmitting] = useState(false);
   const [error, setError] = useState("");

   const decision = detail?.safety_decision;
   const enforcement = detail?.account_enforcement;
   const reconsiderationPending =
      Boolean(detail?.reconsideration) && !detail?.reconsideration?.outcome;
   const reversedContent = detail?.reconsideration?.outcome === "REVERSED";
   const eligible =
      decision?.action === "REMOVE" &&
      !reversedContent;

   useEffect(() => {
      setAction("");
      setDurationCode("24_HOURS");
      setUserRationale("");
      setInternalNote("");
      setConfirmIndefinite(false);
      setError("");
   }, [detail?.id, enforcement?.id]);

   if (!eligible) return null;

   if (enforcement) {
      return (
         <section className="safety-account-action-card">
            <div className="safety-subheading-row">
               <div>
                  <h4>Community access action</h4>
                  <p>Account enforcement is separate from the content-removal decision.</p>
               </div>
               <span className="safety-account-action-status">
                  {STATE_LABELS[enforcement.state] || enforcement.state}
               </span>
            </div>

            <dl className="safety-thread-provenance">
               <div>
                  <dt>Action</dt>
                  <dd>{ACTION_LABELS[enforcement.action] || enforcement.action}</dd>
               </div>
               <div>
                  <dt>Affected account</dt>
                  <dd>{enforcement.user?.username ? `@${enforcement.user.username}` : "Account unavailable"}</dd>
               </div>
               <div>
                  <dt>Policy finding</dt>
                  <dd>{enforcement.violation?.title || decision.violation_title}</dd>
               </div>
               {enforcement.restriction_ends_at ? (
                  <div>
                     <dt>Restriction ends</dt>
                     <dd>{formatDateTime(enforcement.restriction_ends_at)}</dd>
                  </div>
               ) : null}
            </dl>

            <div className="safety-account-action-reason">
               <strong>Reason shown to the user</strong>
               <p>{enforcement.user_rationale}</p>
            </div>
         </section>
      );
   }

   if (detail?.account_enforcement_available === false) {
      return (
         <section className="safety-account-action-card is-disabled">
            <div className="safety-subheading-row">
               <div>
                  <h4>Community access action</h4>
                  <p>Account enforcement is separate from the content-removal decision.</p>
               </div>
            </div>
            <div className="safety-account-action-disabled">
               <Icons name="info" size={16} />
               <span>
                  {reconsiderationPending
                     ? "Resolve the content reconsideration before deciding any account-level action."
                     : "This historical removal predates the Community account-enforcement policy and cannot be used to issue a new warning or restriction."}
               </span>
            </div>
         </section>
      );
   }

   if (!detail?.account_enforcement_issuance_enabled) {
      return (
         <section className="safety-account-action-card is-disabled">
            <div className="safety-subheading-row">
               <div>
                  <h4>Community access action</h4>
                  <p>Account enforcement is separate from the content-removal decision.</p>
               </div>
            </div>
            <div className="safety-account-action-disabled">
               <Icons name="lock" size={16} />
               <span>
                  New account actions are disabled by the deployment safeguard.
                  Standing, reviews, reversals, and existing restrictions remain operational.
               </span>
            </div>
         </section>
      );
   }

   const submit = async (event) => {
      event.preventDefault();
      if (!action) {
         setError("Choose an account action or leave this content removal without one.");
         return;
      }
      if (userRationale.trim().length < 20) {
         setError("Write a clear user-facing reason of at least 20 characters.");
         return;
      }
      if (action === "INDEFINITE_RESTRICTION" && !confirmIndefinite) {
         setError("Confirm that the indefinite restriction has no automatic end date.");
         return;
      }

      setSubmitting(true);
      setError("");

      try {
         const body = {
            action,
            user_rationale: userRationale.trim(),
            internal_note: internalNote.trim(),
         };
         if (action === "TEMPORARY_RESTRICTION") {
            body.duration_code = durationCode;
         }
         if (action === "INDEFINITE_RESTRICTION") {
            body.confirm_indefinite = true;
         }

         const updated = await safetyFetch(
            resolveApiEndpoint("SAFETY_ACCOUNT_ENFORCEMENT", detail.id),
            { method: "POST", body },
         );

         onUpdated?.(updated);
         addToast({
            type: "success",
            message:
               action === "WARNING"
                  ? "Community warning recorded."
                  : "Community contribution restriction issued.",
         });
      } catch (requestError) {
         setError(
            accountActionError(
               requestError,
               "We couldn't record this Community account action. Review the fields and try again.",
            ),
         );
      } finally {
         setSubmitting(false);
      }
   };

   return (
      <section className="safety-account-action-card">
         <div className="safety-subheading-row">
            <div>
               <h4>Community access action</h4>
               <p>
                  Optional. A content removal does not automatically require an account action.
               </p>
            </div>
         </div>

         <form className="safety-account-action-form" onSubmit={submit}>
            <label>
               <span>Account action</span>
               <Select
                  density="standard"
                  value={action}
                  disabled={submitting}
                  onChange={(event) => {
                     setAction(event.target.value);
                     setConfirmIndefinite(false);
                     setError("");
                  }}
               >
                  <option value="">No account action</option>
                  <option value="WARNING">Warning</option>
                  <option value="TEMPORARY_RESTRICTION">Temporary Community restriction</option>
                  <option value="INDEFINITE_RESTRICTION">Indefinite Community restriction</option>
               </Select>
            </label>

            {action === "TEMPORARY_RESTRICTION" ? (
               <label>
                  <span>Duration</span>
                  <Select
                     density="standard"
                     value={durationCode}
                     disabled={submitting}
                     onChange={(event) => setDurationCode(event.target.value)}
                  >
                     <option value="24_HOURS">24 hours</option>
                     <option value="7_DAYS">7 days</option>
                     <option value="30_DAYS">30 days</option>
                  </Select>
               </label>
            ) : null}

            {action ? (
               <>
                  <label>
                     <span>Reason shown to the user *</span>
                     <small>
                        Explain why this account action is proportionate. Do not include
                        reporter identity or private information.
                     </small>
                     <Textarea
                        density="standard"
                        rows={4}
                        maxLength={3000}
                        value={userRationale}
                        disabled={submitting}
                        onChange={(event) => setUserRationale(event.target.value)}
                     />
                  </label>

                  <label>
                     <span>Internal Safety note</span>
                     <small>Visible only to Platform Safety.</small>
                     <Textarea
                        density="standard"
                        rows={3}
                        maxLength={5000}
                        value={internalNote}
                        disabled={submitting}
                        onChange={(event) => setInternalNote(event.target.value)}
                     />
                  </label>
               </>
            ) : null}

            {action === "INDEFINITE_RESTRICTION" ? (
               <label className="safety-account-confirmation">
                  <input
                     type="checkbox"
                     checked={confirmIndefinite}
                     disabled={submitting}
                     onChange={(event) => setConfirmIndefinite(event.target.checked)}
                  />
                  <span>
                     I understand that this Community restriction has no automatic
                     end date. Verification, reading, reporting, and separately
                     authorized Partner Workspace access remain available.
                  </span>
               </label>
            ) : null}

            {error ? (
               <p className="safety-account-form-error" role="alert">{error}</p>
            ) : null}

            {action ? (
               <div className="safety-decision-controls">
                  <Button
                     type="button"
                     variant="secondary"
                     density="standard"
                     disabled={submitting}
                     onClick={() => {
                        setAction("");
                        setUserRationale("");
                        setInternalNote("");
                        setConfirmIndefinite(false);
                        setError("");
                     }}
                  >
                     No account action
                  </Button>
                  <Button
                     type="submit"
                     variant={action === "INDEFINITE_RESTRICTION" ? "destructive" : "primary"}
                     density="comfortable"
                     disabled={submitting}
                     loading={submitting}
                     loadingLabel="Recording…"
                  >
                     {action === "WARNING" ? "Issue warning" : "Issue restriction"}
                  </Button>
               </div>
            ) : (
               <p className="safety-policy-helper">
                  No account action is the default. Use account enforcement only when
                  the confirmed violation and context justify a separate consequence.
               </p>
            )}
         </form>
      </section>
   );
}

function ReviewStartForm({ enforcement, onStart, busy }) {
   const requirement = enforcement.review_internal?.independence_requirement;
   const [independenceNote, setIndependenceNote] = useState("");
   const [overrideRationale, setOverrideRationale] = useState("");

   return (
      <form
         className="safety-access-inline-form"
         onSubmit={(event) => {
            event.preventDefault();
            onStart({
               reviewer_independence_note: independenceNote.trim(),
               independence_override_rationale: overrideRationale.trim(),
            });
         }}
      >
         {requirement === "OVERRIDE_RATIONALE" ? (
            <label>
               <span>Self-review override rationale *</span>
               <Textarea
                  density="standard"
                  rows={3}
                  value={overrideRationale}
                  disabled={busy}
                  onChange={(event) => setOverrideRationale(event.target.value)}
               />
               <small>
                  Another qualified Safety reviewer is available. Explain why you are
                  reviewing your own original account action.
               </small>
            </label>
         ) : requirement === "UNAVAILABLE_NOTE" ? (
            <label>
               <span>Reviewer independence note *</span>
               <Textarea
                  density="standard"
                  rows={3}
                  value={independenceNote}
                  disabled={busy}
                  onChange={(event) => setIndependenceNote(event.target.value)}
               />
               <small>Record why independent review is not available.</small>
            </label>
         ) : (
            <p className="safety-policy-helper">
               You did not issue the original account action, so this review is independent.
            </p>
         )}

         <Button type="submit" variant="primary" density="standard" disabled={busy}>
            Start review
         </Button>
      </form>
   );
}

function ReviewResolveForm({ onResolve, busy }) {
   const [outcome, setOutcome] = useState("UPHELD");
   const [rationale, setRationale] = useState("");
   const [internalNote, setInternalNote] = useState("");

   return (
      <form
         className="safety-access-inline-form"
         onSubmit={(event) => {
            event.preventDefault();
            onResolve({
               outcome,
               resolution_rationale: rationale.trim(),
               internal_note: internalNote.trim(),
            });
         }}
      >
         <label>
            <span>Review outcome</span>
            <Select
               density="standard"
               value={outcome}
               disabled={busy}
               onChange={(event) => setOutcome(event.target.value)}
            >
               <option value="UPHELD">Uphold account action</option>
               <option value="REVERSED">Reverse account action</option>
            </Select>
         </label>
         <label>
            <span>Explanation shown to the user *</span>
            <Textarea
               density="standard"
               rows={3}
               value={rationale}
               disabled={busy}
               maxLength={3000}
               onChange={(event) => setRationale(event.target.value)}
            />
         </label>
         <label>
            <span>Internal Safety note</span>
            <Textarea
               density="standard"
               rows={2}
               value={internalNote}
               disabled={busy}
               maxLength={5000}
               onChange={(event) => setInternalNote(event.target.value)}
            />
         </label>
         <Button
            type="submit"
            variant={outcome === "REVERSED" ? "primary" : "secondary"}
            density="standard"
            disabled={busy || rationale.trim().length < 20}
         >
            Resolve review
         </Button>
      </form>
   );
}

function LiftForm({ onLift, busy }) {
   const [rationale, setRationale] = useState("");

   return (
      <form
         className="safety-access-inline-form"
         onSubmit={(event) => {
            event.preventDefault();
            onLift(rationale.trim());
         }}
      >
         <label>
            <span>Why should this restriction end early? *</span>
            <Textarea
               density="standard"
               rows={3}
               value={rationale}
               disabled={busy}
               maxLength={3000}
               onChange={(event) => setRationale(event.target.value)}
            />
         </label>
         <Button
            type="submit"
            variant="secondary"
            density="standard"
            disabled={busy || rationale.trim().length < 20}
         >
            Lift restriction early
         </Button>
      </form>
   );
}

export default function CommunityAccountEnforcementPanel({ safetyFetch }) {
   const { user } = useAuth();
   const { addToast } = useNotification();
   const [open, setOpen] = useState(false);
   const [filter, setFilter] = useState("");
   const [data, setData] = useState({ count: 0, results: [] });
   const [loading, setLoading] = useState(false);
   const [error, setError] = useState("");
   const [busyId, setBusyId] = useState(null);
   const [expandedId, setExpandedId] = useState(null);
   const [refreshVersion, setRefreshVersion] = useState(0);

   const endpoint = useMemo(() => {
      const query = new URLSearchParams();
      if (filter) query.set("status", filter);
      query.set("limit", "50");
      const base = resolveApiEndpoint("SAFETY_ACCOUNT_ENFORCEMENTS");
      return `${base}?${query.toString()}`;
   }, [filter]);

   const reload = useCallback(() => {
      setRefreshVersion((value) => value + 1);
   }, []);

   useEffect(() => {
      if (!open) return undefined;
      let cancelled = false;
      setLoading(true);
      setError("");

      safetyFetch(endpoint, { method: "GET" })
         .then((response) => {
            if (cancelled) return;
            setData({
               count: Number(response?.count || 0),
               results: Array.isArray(response?.results) ? response.results : [],
            });
         })
         .catch((requestError) => {
            if (!cancelled) {
               setError(
                  accountActionError(
                     requestError,
                     "We couldn't load Community account actions. Try again.",
                  ),
               );
            }
         })
         .finally(() => {
            if (!cancelled) setLoading(false);
         });

      return () => {
         cancelled = true;
      };
   }, [endpoint, open, refreshVersion, safetyFetch]);

   const mutate = async (enforcement, endpointKey, endpointId, body, successMessage) => {
      setBusyId(enforcement.id);
      setError("");
      try {
         await safetyFetch(resolveApiEndpoint(endpointKey, endpointId), {
            method: "POST",
            body,
         });
         addToast({ type: "success", message: successMessage });
         reload();
      } catch (requestError) {
         setError(
            accountActionError(
               requestError,
               "We couldn't update this Community account action. Review the fields and try again.",
            ),
         );
      } finally {
         setBusyId(null);
      }
   };

   return (
      <section className="safety-access-panel">
         <div className="safety-access-panel-header">
            <div>
               <span className="safety-toolbar-kicker">Community access</span>
               <strong>Warnings, restrictions, and account-action reviews</strong>
               <p>Account actions remain separate from content-removal decisions.</p>
            </div>
            <Button
               type="button"
               variant="secondary"
               density="standard"
               onClick={() => setOpen((value) => !value)}
            >
               {open ? "Hide Community access" : "Open Community access"}
            </Button>
         </div>

         {open ? (
            <div className="safety-access-panel-body">
               <div className="safety-access-controls">
                  <label>
                     <span>Show</span>
                     <Select
                        density="standard"
                        value={filter}
                        disabled={loading}
                        onChange={(event) => setFilter(event.target.value)}
                     >
                        <option value="">Recent account actions</option>
                        <option value="ACTIVE">Active restrictions</option>
                        <option value="PENDING_REVIEW">Pending reviews</option>
                        <option value="WARNING">Warnings</option>
                     </Select>
                  </label>
                  <Button
                     type="button"
                     variant="secondary"
                     density="standard"
                     disabled={loading}
                     onClick={reload}
                  >
                     Refresh
                  </Button>
               </div>

               {error ? <p className="safety-account-form-error" role="alert">{error}</p> : null}

               {loading ? (
                  <div className="safety-state" role="status">
                     <Icons name="loader" size={18} className="safety-spinner" />
                     <span>Loading Community account actions…</span>
                  </div>
               ) : data.results.length === 0 ? (
                  <div className="safety-inline-empty">No account actions match this view.</div>
               ) : (
                  <div className="safety-access-list">
                     {data.results.map((enforcement) => {
                        const expanded = expandedId === enforcement.id;
                        const busy = busyId === enforcement.id;
                        const review = enforcement.review;
                        const reviewInternal = enforcement.review_internal;
                        const currentReviewer =
                           reviewInternal?.reviewer &&
                           String(reviewInternal.reviewer.id) === String(user?.id);
                        const canLift =
                           enforcement.state === "ACTIVE" &&
                           enforcement.action !== "WARNING";

                        return (
                           <article key={enforcement.id} className="safety-access-item">
                              <button
                                 type="button"
                                 className="safety-access-item-summary"
                                 onClick={() => setExpandedId(expanded ? null : enforcement.id)}
                                 aria-expanded={expanded}
                              >
                                 <span>
                                    <strong>
                                       {enforcement.user?.username
                                          ? `@${enforcement.user.username}`
                                          : enforcement.user?.username_snapshot || "Account unavailable"}
                                    </strong>
                                    <small>{ACTION_LABELS[enforcement.action] || enforcement.action}</small>
                                 </span>
                                 <span>
                                    <small>{STATE_LABELS[enforcement.state] || enforcement.state}</small>
                                    <Icons name={expanded ? "chevron-up" : "chevron-down"} size={15} />
                                 </span>
                              </button>

                              {expanded ? (
                                 <div className="safety-access-item-detail">
                                    <dl className="safety-thread-provenance">
                                       <div>
                                          <dt>Finding</dt>
                                          <dd>{enforcement.violation?.title || "Community Guidelines"}</dd>
                                       </div>
                                       <div>
                                          <dt>Issued</dt>
                                          <dd>{formatDateTime(enforcement.issued_at)}</dd>
                                       </div>
                                       <div>
                                          <dt>Issued by</dt>
                                          <dd>{enforcement.issued_by?.username ? `@${enforcement.issued_by.username}` : "Reviewer unavailable"}</dd>
                                       </div>
                                       {enforcement.restriction_ends_at ? (
                                          <div>
                                             <dt>Ends</dt>
                                             <dd>{formatDateTime(enforcement.restriction_ends_at)}</dd>
                                          </div>
                                       ) : null}
                                    </dl>

                                    <div className="safety-account-action-reason">
                                       <strong>User-facing reason</strong>
                                       <p>{enforcement.user_rationale}</p>
                                    </div>

                                    {enforcement.internal_note ? (
                                       <div className="safety-account-internal-note">
                                          <strong>Internal Safety note</strong>
                                          <p>{enforcement.internal_note}</p>
                                       </div>
                                    ) : null}

                                    {review?.status === "SUBMITTED" ? (
                                       <div className="safety-access-review-block">
                                          <h5>Pending account-action review</h5>
                                          <blockquote>{review.request_statement}</blockquote>
                                          <ReviewStartForm
                                             enforcement={enforcement}
                                             busy={busy}
                                             onStart={(body) =>
                                                mutate(
                                                   enforcement,
                                                   "SAFETY_ACCOUNT_ENFORCEMENT_REVIEW_START",
                                                   review.id,
                                                   body,
                                                   "Account-action review started.",
                                                )
                                             }
                                          />
                                       </div>
                                    ) : review?.status === "UNDER_REVIEW" ? (
                                       <div className="safety-access-review-block">
                                          <h5>Account-action review in progress</h5>
                                          <blockquote>{review.request_statement}</blockquote>
                                          {currentReviewer ? (
                                             <ReviewResolveForm
                                                busy={busy}
                                                onResolve={(body) =>
                                                   mutate(
                                                      enforcement,
                                                      "SAFETY_ACCOUNT_ENFORCEMENT_REVIEW_RESOLVE",
                                                      review.id,
                                                      body,
                                                      "Account-action review resolved.",
                                                   )
                                                }
                                             />
                                          ) : (
                                             <p className="safety-policy-helper">
                                                Assigned to {reviewInternal?.reviewer?.username ? `@${reviewInternal.reviewer.username}` : "another Safety reviewer"}.
                                             </p>
                                          )}
                                       </div>
                                    ) : review ? (
                                       <div className="safety-access-review-block">
                                          <h5>Account-action review</h5>
                                          <p>
                                             {review.status === "MOOT"
                                                ? "Moot because the underlying content-removal basis no longer applies."
                                                : review.outcome === "REVERSED"
                                                  ? "Account action reversed."
                                                  : "Account action upheld."}
                                          </p>
                                          {review.resolution_rationale ? <p>{review.resolution_rationale}</p> : null}
                                       </div>
                                    ) : null}

                                    {canLift ? (
                                       <details className="safety-access-lift">
                                          <summary>Lift restriction early</summary>
                                          <LiftForm
                                             busy={busy}
                                             onLift={(rationale) =>
                                                mutate(
                                                   enforcement,
                                                   "SAFETY_ACCOUNT_ENFORCEMENT_LIFT",
                                                   enforcement.id,
                                                   { rationale },
                                                   "Community restriction lifted.",
                                                )
                                             }
                                          />
                                       </details>
                                    ) : null}
                                 </div>
                              ) : null}
                           </article>
                        );
                     })}
                  </div>
               )}
            </div>
         ) : null}
      </section>
   );
}
