import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import Button from "../components/ui/Button";
import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import { userFacingErrorMessage } from "../utils/userFacingError";
import "./GovernanceNoticePage.css";

const dateFormatter = new Intl.DateTimeFormat(undefined, {
   dateStyle: "medium",
   timeStyle: "short",
});

const groundOptions = [
   ["MATERIAL_FACTS_INCORRECT", "Material facts are incorrect"],
   ["RELEVANT_EVIDENCE_OVERLOOKED", "Relevant evidence was overlooked"],
   ["POLICY_MISAPPLIED", "Policy was incorrectly applied"],
   ["SIGNIFICANT_PROCEDURAL_ERROR", "A significant procedural error occurred"],
];

function formatDate(value) {
   if (!value) return "Not recorded";
   const date = new Date(value);
   return Number.isNaN(date.getTime()) ? "Not recorded" : dateFormatter.format(date);
}

function formatValue(value) {
   if (value === null || value === undefined || value === "") return "Not recorded";
   if (Array.isArray(value)) return value.length ? value.join(", ") : "Not recorded";
   if (typeof value === "object") return JSON.stringify(value);
   return String(value);
}

function ReconsiderationSummary({ reconsideration }) {
   if (!reconsideration) return null;

   return (
      <section className="tl-governance-card">
         <div className="tl-governance-card__heading">
            <div>
               <span className="tl-governance-eyebrow">Reconsideration</span>
               <h2>Suspension review request</h2>
            </div>
            <span className="tl-governance-status">{reconsideration.status.replaceAll("_", " ")}</span>
         </div>
         <dl className="tl-governance-detail-list">
            <div>
               <dt>Grounds</dt>
               <dd>{formatValue(reconsideration.grounds)}</dd>
            </div>
            <div>
               <dt>Submitted</dt>
               <dd>{formatDate(reconsideration.submitted_at)}</dd>
            </div>
            <div>
               <dt>Organization statement</dt>
               <dd>{reconsideration.request_statement}</dd>
            </div>
            {reconsideration.supporting_references?.length ? (
               <div>
                  <dt>Supporting references</dt>
                  <dd>{reconsideration.supporting_references.join(", ")}</dd>
               </div>
            ) : null}
            {reconsideration.outcome ? (
               <div>
                  <dt>Outcome</dt>
                  <dd>{reconsideration.outcome}</dd>
               </div>
            ) : null}
            {reconsideration.resolution_rationale ? (
               <div>
                  <dt>Resolution</dt>
                  <dd>{reconsideration.resolution_rationale}</dd>
               </div>
            ) : null}
         </dl>
      </section>
   );
}

function GovernanceNoticePage() {
   const { noticeId } = useParams();
   const { authFetch } = useAuth();
   const [notice, setNotice] = useState(null);
   const [loadError, setLoadError] = useState(null);
   const [submissionError, setSubmissionError] = useState(null);
   const [submitting, setSubmitting] = useState(false);
   const [grounds, setGrounds] = useState([]);
   const [statement, setStatement] = useState("");
   const [references, setReferences] = useState("");

   useEffect(() => {
      let active = true;
      const detailUrl = resolveApiEndpoint("GOVERNANCE_NOTICE_DETAIL", noticeId);

      authFetch(detailUrl, { method: "GET" })
         .then((payload) => {
            if (!active) return null;
            setNotice(payload);
            setLoadError(null);
            return authFetch(
               resolveApiEndpoint("GOVERNANCE_NOTICE_VIEWED", noticeId),
               { method: "PATCH" },
            ).catch(() => null);
         })
         .catch((error) => {
            if (active) setLoadError(error);
         });

      return () => {
         active = false;
      };
   }, [authFetch, noticeId]);

   const governanceEntries = useMemo(
      () => Object.entries(notice?.governance || {}).filter(([, value]) => (
         value !== null && value !== "" && (!Array.isArray(value) || value.length)
      )),
      [notice],
   );

   const toggleGround = (ground) => {
      setGrounds((current) => (
         current.includes(ground)
            ? current.filter((value) => value !== ground)
            : [...current, ground]
      ));
   };

   const submitReconsideration = async (event) => {
      event.preventDefault();
      setSubmitting(true);
      setSubmissionError(null);
      try {
         const reconsideration = await authFetch(
            resolveApiEndpoint("GOVERNANCE_NOTICE_RECONSIDERATION", noticeId),
            {
               method: "POST",
               body: {
                  grounds,
                  request_statement: statement.trim(),
                  supporting_references: references
                     .split("\n")
                     .map((value) => value.trim())
                     .filter(Boolean)
                     .slice(0, 10),
               },
            },
         );
         setNotice((current) => ({
            ...current,
            reconsideration,
            can_request_reconsideration: false,
         }));
         setGrounds([]);
         setStatement("");
         setReferences("");
      } catch (error) {
         setSubmissionError(error);
      } finally {
         setSubmitting(false);
      }
   };

   if (loadError) {
      return (
         <main className="tl-governance-page">
            <section className="tl-governance-state">
               <h1>Governance notice unavailable</h1>
               <p>
                  {userFacingErrorMessage(loadError, {
                     fallback: "We couldn't load this governance notice.",
                     notFoundMessage: "This governance notice is not available to this account.",
                  })}
               </p>
               <Link to="/notifications">Return to notifications</Link>
            </section>
         </main>
      );
   }

   if (!notice) {
      return (
         <main className="tl-governance-page">
            <section className="tl-governance-state">
               <p>Loading governance notice…</p>
            </section>
         </main>
      );
   }

   const isAdminNotice = notice.audience === "ADMIN";

   return (
      <main className="tl-governance-page">
         <div className="tl-governance-page__content">
            <Link className="tl-governance-back" to="/notifications">← Notifications</Link>

            <header className="tl-governance-header">
               <span className="tl-governance-eyebrow">Partner Organization Governance</span>
               <h1>{notice.action?.label || "Governance notice"}</h1>
               <p>
                  {notice.organization?.name || "Organization"} · Effective {formatDate(notice.effective_at)}
               </p>
            </header>

            <section className="tl-governance-card">
               <div className="tl-governance-card__heading">
                  <div>
                     <span className="tl-governance-eyebrow">Current effect</span>
                     <h2>Partner status</h2>
                  </div>
                  <span className="tl-governance-status">{notice.partner_status || "Not recorded"}</span>
               </div>

               {isAdminNotice ? (
                  <>
                     <div className="tl-governance-rationale">
                        <h3>Organization-facing rationale</h3>
                        <p>{notice.rationale || "No additional rationale was recorded."}</p>
                     </div>
                     {governanceEntries.length ? (
                        <dl className="tl-governance-detail-list">
                           {governanceEntries.map(([key, value]) => (
                              <div key={key}>
                                 <dt>{key.replaceAll("_", " ")}</dt>
                                 <dd>{formatValue(value)}</dd>
                              </div>
                           ))}
                        </dl>
                     ) : null}
                  </>
               ) : (
                  <p className="tl-governance-member-message">{notice.message}</p>
               )}
            </section>

            <ReconsiderationSummary reconsideration={notice.reconsideration} />

            {isAdminNotice && notice.can_request_reconsideration ? (
               <section className="tl-governance-card">
                  <div className="tl-governance-card__heading">
                     <div>
                        <span className="tl-governance-eyebrow">Available next step</span>
                        <h2>Request reconsideration</h2>
                     </div>
                  </div>
                  <p className="tl-governance-helper">
                     A reconsideration request does not restore Partner authority while review is pending.
                     Use only the policy-defined grounds below and identify the material issue for review.
                  </p>
                  <form className="tl-governance-form" onSubmit={submitReconsideration}>
                     <fieldset>
                        <legend>Grounds</legend>
                        {groundOptions.map(([value, label]) => (
                           <label key={value}>
                              <input
                                 type="checkbox"
                                 checked={grounds.includes(value)}
                                 onChange={() => toggleGround(value)}
                                 disabled={submitting}
                              />
                              <span>{label}</span>
                           </label>
                        ))}
                     </fieldset>
                     <label>
                        <span>Organization statement</span>
                        <textarea
                           rows={5}
                           value={statement}
                           onChange={(event) => setStatement(event.target.value)}
                           disabled={submitting}
                           required
                           minLength={20}
                           placeholder="Explain the material facts, overlooked evidence, policy issue, or procedural error that should be reviewed."
                        />
                     </label>
                     <label>
                        <span>Supporting references (optional)</span>
                        <textarea
                           rows={3}
                           value={references}
                           onChange={(event) => setReferences(event.target.value)}
                           disabled={submitting}
                           placeholder="One reference per line. Do not upload confidential documents here."
                        />
                     </label>
                     {submissionError ? (
                        <div className="tl-governance-error" role="alert">
                           {userFacingErrorMessage(submissionError, {
                              fallback: "We couldn't submit the reconsideration request.",
                              conflictMessage: "A reconsideration is already open or this suspension is no longer eligible for review.",
                           })}
                        </div>
                     ) : null}
                     <Button
                        type="submit"
                        loading={submitting}
                        loadingLabel="Submitting…"
                        disabled={!grounds.length || statement.trim().length < 20}
                     >
                        Submit reconsideration
                     </Button>
                  </form>
               </section>
            ) : null}

            {isAdminNotice && notice.action?.code === "PARTNERSHIP_ENDED" ? (
               <section className="tl-governance-card tl-governance-card--quiet">
                  <h2>Review of a partnership ending</h2>
                  <p>
                     This notice does not provide a self-service termination appeal portal.
                     Contact TruthLens through the established organization channel if a serious
                     dispute requires administrative review.
                  </p>
               </section>
            ) : null}
         </div>
      </main>
   );
}

export default GovernanceNoticePage;
