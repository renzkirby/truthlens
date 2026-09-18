import { useEffect, useId, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { resolveApiEndpoint } from "../../utils/api";
import { getAuthSessionIdentity } from "../../utils/authIdentity";
import Badge from "../ui/Badge.jsx";
import Button from "../ui/Button.jsx";

import "./VerificationIntelligencePanel.css";

const EVIDENCE_STATES = {
   NO_EVIDENCE: "No persisted evidence",
   AUTOMATED_CONTEXT_ONLY: "System-collected context only",
   HUMAN_REVIEW_PENDING: "Human evidence review pending",
   HUMAN_REVIEW_COMPLETE: "Human evidence review complete",
   HUMAN_REVIEW_COMPLETE_WITH_AUTOMATED_CONTEXT: "Human review complete with system-collected context",
};

const KNOWLEDGE_STATES = {
   NO_PRIOR_INSTITUTIONAL_KNOWLEDGE: "None surfaced for this claim",
   RELATED_CONTEXT_ONLY: "Related institutional context only",
   AUTHORITATIVE_RESOLUTION: "Prior institutional resolution available",
   AUTHORITATIVE_WITH_RELATED_CONTEXT: "Prior resolution with related context",
};

const READINESS_REASONS = {
   NO_HUMAN_EVIDENCE: "No human-submitted evidence is available for review.",
   UNREVIEWED_HUMAN_EVIDENCE: "Human-submitted evidence still requires review.",
   ACTIVE_EVIDENCE_CASES: "Active evidence-review cases remain unresolved.",
};

const BASIS_LABELS = {
   CURRENT_HUMAN_EVIDENCE_REVIEW_STATE: "Current human evidence review state",
   LATEST_VERIFICATION_RUN: "Latest persisted verification run",
   PERSISTED_SOURCE_IDENTITY_GROUPING: "Persisted source identity grouping",
};

const MATCH_METHOD_LABELS = {
   CLAIM_CACHE: "Direct published claim",
   EXACT_CANONICAL: "Exact canonical reference",
   EQUIVALENT_CLAIM: "Previously resolved proposition equivalence",
   EXACT_HEADLINE: "Headline equality",
   SEMANTIC: "Persisted semantic relationship",
   FULL_TEXT: "Persisted full-text relationship",
};

function readableLabel(value, fallback = "Unavailable") {
   return typeof value === "string" && value.trim()
      ? value
           .replaceAll("_", " ")
           .toLowerCase()
           .replace(/^\w/, (letter) => letter.toUpperCase())
      : fallback;
}

function formatCount(value, singular, plural = `${singular}s`) {
   return Number.isInteger(value) && value >= 0 ? `${value} ${value === 1 ? singular : plural}` : null;
}

function RecordedDate({ value }) {
   const date = value ? new Date(value) : null;

   if (!date || Number.isNaN(date.getTime())) {
      return "Publication date not recorded";
   }

   return (
      <time dateTime={date.toISOString()}>
         {new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date)}
      </time>
   );
}

function MetricList({ values }) {
   const usableValues = values.filter(([, value]) => Number.isInteger(value) && value >= 0);

   if (usableValues.length === 0) {
      return null;
   }

   return (
      <dl className="verification-intelligence-metrics">
         {usableValues.map(([label, value]) => (
            <div key={label}>
               <dt>{label}</dt>
               <dd>{value}</dd>
            </div>
         ))}
      </dl>
   );
}

function CountBadges({ values }) {
   const visibleValues = values.filter(([, value]) => Number.isInteger(value) && value > 0);

   if (visibleValues.length === 0) {
      return null;
   }

   return (
      <div className="verification-intelligence-count-badges" aria-label="Evidence review counts">
         {visibleValues.map(([label, value, pluralLabel = label]) => (
            <Badge key={label} tone="neutral">
               {value} {value === 1 ? label : pluralLabel}
            </Badge>
         ))}
      </div>
   );
}

function PublicationContext({ publication, explanation, authoritative = false }) {
   return (
      <article className="verification-intelligence-publication">
         <div className="verification-intelligence-publication-labels">
            <Badge tone="neutral">
               {authoritative ? "Prior institutional resolution" : "Context only · verdict does not transfer"}
            </Badge>
            {authoritative && publication?.verdict ? (
               <Badge tone="neutral">Recorded verdict: {readableLabel(publication.verdict)}</Badge>
            ) : null}
         </div>

         <p className="verification-intelligence-publication-title">
            {publication?.headline || "Publication headline not recorded"}
         </p>
         <p className="verification-intelligence-meta">
            {publication?.organization?.name || "Organization not recorded"}
            {" · "}
            <RecordedDate value={publication?.published_at} />
         </p>
         <p className="verification-intelligence-meta">
            Match: {MATCH_METHOD_LABELS[explanation?.match_method] || "Unsupported match method"}
         </p>
         <p>{explanation?.why_surfaced?.detail || "Surfacing explanation unavailable."}</p>

         {authoritative ? (
            <p className="verification-intelligence-note">
               Durable prior institutional knowledge is shown for context. It does not preselect or replace the current
               human adjudication.
            </p>
         ) : null}
      </article>
   );
}

function HumanEvidenceSummary({ human }) {
   const readiness = human.evidence_side_adjudication_readiness || {};
   const summary = [
      formatCount(human.total, "submission"),
      formatCount(human.reviewed, "reviewed", "reviewed"),
      Number.isInteger(human.unreviewed) && human.unreviewed > 0
         ? formatCount(human.unreviewed, "unreviewed", "unreviewed")
         : null,
   ]
      .filter(Boolean)
      .join(" · ");

   return (
      <section className="verification-intelligence-block" aria-labelledby="verification-intelligence-human-heading">
         <div className="verification-intelligence-block-heading">
            <h6 id="verification-intelligence-human-heading">Human evidence</h6>
            <Badge tone="neutral">
               {readiness.ready === true
                  ? "Evidence review complete"
                  : readiness.ready === false
                    ? "Evidence review incomplete"
                    : "Review status unavailable"}
            </Badge>
         </div>

         <p className="verification-intelligence-summary-line">{summary || "Human evidence counts are unavailable."}</p>

         <CountBadges
            values={[
               ["verified", human.verified],
               ["rejected", human.rejected],
               ["unreviewed", human.unreviewed],
               ["active evidence case", human.active_evidence_cases, "active evidence cases"],
            ]}
         />

         {readiness.ready === false &&
         Array.isArray(readiness.blocking_codes) &&
         readiness.blocking_codes.length > 0 ? (
            <ul className="verification-intelligence-compact-list">
               {readiness.blocking_codes.map((code) => (
                  <li key={code}>{READINESS_REASONS[code] || "An unsupported evidence-review reason was returned."}</li>
               ))}
            </ul>
         ) : null}

         <p className="verification-intelligence-note">
            This is evidence-review status only. Actual decision eligibility is governed by Assignment and readiness in
            the main review surface.
         </p>
      </section>
   );
}

function SystemCollectedEvidenceSummary({ automated }) {
   const assessment = automated.assessment || {};
   const stances = automated.stance_counts || {};
   const sourceIdentity = automated.source_identity || {};
   const total = Number.isInteger(automated.total) && automated.total >= 0 ? automated.total : null;

   return (
      <section className="verification-intelligence-block" aria-labelledby="verification-intelligence-system-heading">
         <div className="verification-intelligence-block-heading">
            <h6 id="verification-intelligence-system-heading">System-collected evidence</h6>
            <Badge tone="neutral">Context only</Badge>
         </div>

         {total === 0 ? (
            <p className="verification-intelligence-empty-copy">
               No persisted system-collected evidence exists in the latest verification run.
            </p>
         ) : (
            <>
               <p className="verification-intelligence-summary-line">
                  {total === null
                     ? "System-collected evidence count unavailable."
                     : `${total} persisted from the latest verification run.`}
               </p>

               <MetricList
                  values={[
                     ["Fully assessed", assessment.fully_assessed],
                     ["Partially assessed", assessment.partially_assessed],
                     ["Unassessed", assessment.unassessed],
                  ]}
               />

               <div className="verification-intelligence-signal-group">
                  <span>Persisted relationship signals</span>
                  <div className="verification-intelligence-count-badges">
                     {[
                        ["Supports", stances.SUPPORTS],
                        ["Refutes", stances.REFUTES],
                        ["Context", stances.CONTEXT],
                        ["Unknown", stances.UNKNOWN],
                     ]
                        .filter(([, value]) => Number.isInteger(value) && value > 0)
                        .map(([label, value]) => (
                           <Badge key={label} tone="neutral">
                              {label} {value}
                           </Badge>
                        ))}
                  </div>
               </div>

               {Number.isInteger(sourceIdentity.group_count) && sourceIdentity.group_count > 0 ? (
                  <div className="verification-intelligence-source-summary">
                     <strong>Source identity</strong>
                     <p>
                        {sourceIdentity.group_count} {sourceIdentity.group_count === 1 ? "group" : "groups"}
                        {Number.isInteger(sourceIdentity.shared_group_count) && sourceIdentity.shared_group_count > 0
                           ? ` · ${sourceIdentity.shared_group_count} shared ${sourceIdentity.shared_group_count === 1 ? "group" : "groups"}`
                           : " · no shared groups"}
                     </p>
                     {Number.isInteger(sourceIdentity.shared_group_count) && sourceIdentity.shared_group_count > 0 ? (
                        <p className="verification-intelligence-note">
                           Shared source identity can make multiple items look more independent than they are.
                        </p>
                     ) : null}
                  </div>
               ) : null}
            </>
         )}

         <p className="verification-intelligence-note">
            These are sources persisted by the automated verification pipeline. Their machine-assessed relationship to
            the claim does not determine the verdict.
         </p>
      </section>
   );
}

function ReviewQuestions({ questions }) {
   return (
      <section
         className="verification-intelligence-block"
         aria-labelledby="verification-intelligence-questions-heading"
      >
         <div className="verification-intelligence-block-heading">
            <h6 id="verification-intelligence-questions-heading">Review questions</h6>
            {Array.isArray(questions) && questions.length > 0 ? <Badge tone="warning">{questions.length}</Badge> : null}
         </div>

         {!Array.isArray(questions) ? (
            <p className="verification-intelligence-empty-copy">Review questions are unavailable in this response.</p>
         ) : questions.length === 0 ? (
            <p className="verification-intelligence-empty-copy">
               No template-based review questions are triggered by the current persisted evidence state.
            </p>
         ) : (
            <ol className="verification-intelligence-questions">
               {questions.map((item, index) => (
                  <li key={`${item.code}:${index}`}>
                     <p>{item.question}</p>
                     <div className="verification-intelligence-question-context">
                        <Badge tone={item.blocking === true ? "warning" : "neutral"}>
                           {item.blocking === true ? "Needs review" : "Review consideration"}
                        </Badge>
                        <span>{BASIS_LABELS[item.basis] || "Review basis unavailable"}</span>
                     </div>
                  </li>
               ))}
            </ol>
         )}
      </section>
   );
}

function PriorKnowledge({ knowledge }) {
   const knowledgeIntelligence = knowledge.intelligence || {};
   const related = Array.isArray(knowledgeIntelligence.related) ? knowledgeIntelligence.related : null;
   const unsupportedAuthorityExplanation = Boolean(
      knowledge.authoritative_resolution && !knowledgeIntelligence.authoritative,
   );

   return (
      <section
         className="verification-intelligence-block"
         aria-labelledby="verification-intelligence-knowledge-heading"
      >
         <div className="verification-intelligence-block-heading">
            <h6 id="verification-intelligence-knowledge-heading">Prior institutional knowledge</h6>
         </div>

         <p className="verification-intelligence-summary-line">
            {unsupportedAuthorityExplanation
               ? "Published record present · authority explanation unsupported"
               : KNOWLEDGE_STATES[knowledgeIntelligence.state] || "Prior knowledge state unavailable"}
         </p>

         {knowledgeIntelligence.authoritative && knowledge.authoritative_resolution ? (
            <PublicationContext
               authoritative
               publication={knowledge.authoritative_resolution}
               explanation={knowledgeIntelligence.authoritative}
            />
         ) : knowledge.authoritative_resolution ? (
            <p className="verification-intelligence-warning">
               A published record is present, but its authority explanation is unsupported in this intelligence
               contract. Do not use it as an authority cue.
            </p>
         ) : null}

         {related === null ? (
            <p className="verification-intelligence-empty-copy">
               Explained related publication context is unavailable.
            </p>
         ) : related.length > 0 ? (
            <details className="verification-intelligence-related-disclosure">
               <summary>Related institutional context ({related.length})</summary>
               <ul className="verification-intelligence-publications">
                  {related.map((item, index) => (
                     <li key={`${item.fact_check_id}:${index}`}>
                        <PublicationContext publication={item} explanation={item} />
                     </li>
                  ))}
               </ul>
            </details>
         ) : null}
      </section>
   );
}

function InterpretationLimitations({ evidenceLimitations, knowledgeLimitations }) {
   const groups = [
      ["Evidence interpretation", evidenceLimitations],
      ["Institutional knowledge", knowledgeLimitations],
   ].filter(([, items]) => Array.isArray(items) && items.length > 0);

   return (
      <details className="verification-intelligence-limitations">
         <summary>Interpretation notes</summary>
         <div className="verification-intelligence-limitations-body">
            {groups.length > 0 ? (
               groups.map(([label, items]) => (
                  <div key={label}>
                     <strong>{label}</strong>
                     <ul>
                        {items.map((item, index) => (
                           <li key={`${item.code}:${index}`}>
                              <span>{readableLabel(item.code)}</span>
                              <p>{item.detail}</p>
                           </li>
                        ))}
                     </ul>
                  </div>
               ))
            ) : (
               <p>No interpretation limitations were returned in these intelligence blocks.</p>
            )}
         </div>
      </details>
   );
}

function IntelligenceContent({ data }) {
   const evidence = data.evidence_intelligence || {};
   const human = evidence.human || {};
   const automated = evidence.automated || {};
   const knowledge = data.institutional_knowledge || {};
   const evidenceLimitations = Array.isArray(evidence.limitations) ? evidence.limitations : [];
   const knowledgeLimitations = Array.isArray(knowledge?.intelligence?.limitations)
      ? knowledge.intelligence.limitations
      : [];

   return (
      <div className="verification-intelligence-content">
         <div className="verification-intelligence-state-card">
            <span>Current evidence state</span>
            <strong>{EVIDENCE_STATES[evidence.state] || "Evidence state unavailable"}</strong>
         </div>

         <HumanEvidenceSummary human={human} />
         <ReviewQuestions questions={evidence.unresolved_questions} />
         <SystemCollectedEvidenceSummary automated={automated} />
         <PriorKnowledge knowledge={knowledge} />
         <InterpretationLimitations
            evidenceLimitations={evidenceLimitations}
            knowledgeLimitations={knowledgeLimitations}
         />
      </div>
   );
}

export default function VerificationIntelligencePanel({ claimId, organizationId }) {
   const { authFetch, user, token } = useAuth();
   const headingId = useId();
   const requestIdRef = useRef(0);
   const [requestVersion, setRequestVersion] = useState(0);
   const [result, setResult] = useState(null);
   const requestedClaimId = String(claimId ?? "").trim();
   const requestedOrganizationId = String(organizationId ?? "").trim();
   const principal = getAuthSessionIdentity(user, token);
   const identity = JSON.stringify([requestedOrganizationId, requestedClaimId, principal, Boolean(token)]);

   useEffect(() => {
      if (!requestedClaimId || !requestedOrganizationId) {
         return undefined;
      }

      let cancelled = false;
      const requestId = ++requestIdRef.current;
      const url = `${resolveApiEndpoint("VERIFICATION_INTELLIGENCE", requestedClaimId)}?${new URLSearchParams({
         organization_id: requestedOrganizationId,
      })}`;
      const isCurrent = () => !cancelled && requestIdRef.current === requestId;

      authFetch(url, { method: "GET" })
         .then((data) => {
            if (!isCurrent()) {
               return;
            }

            if (
               String(data?.claim?.id ?? "") !== requestedClaimId ||
               data?.schema_version !== "1.0" ||
               !data?.evidence_intelligence ||
               !data?.institutional_knowledge?.intelligence
            ) {
               setResult({
                  identity,
                  requestVersion,
                  error: "The intelligence response is incomplete or does not match this claim. Retry intelligence to reload it.",
               });
               return;
            }

            setResult({ identity, requestVersion, data });
         })
         .catch((error) => {
            if (!isCurrent()) {
               return;
            }

            const message =
               error?.status === 401
                  ? "Your session could not access verification intelligence. Restore your session, then retry intelligence."
                  : error?.status === 403
                    ? "You do not have access to verification intelligence for this organization. Retry after your access is restored."
                    : error?.status === 404
                      ? "Intelligence is unavailable for the current active verification work. This does not indicate that no evidence exists."
                      : "Verification intelligence could not be loaded. Retry intelligence to reload this supplementary context.";

            setResult({ identity, requestVersion, error: message });
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, identity, requestVersion, requestedClaimId, requestedOrganizationId]);

   if (!requestedClaimId || !requestedOrganizationId) {
      return null;
   }

   const currentResult = result?.identity === identity && result?.requestVersion === requestVersion ? result : null;
   const loading = currentResult === null;

   return (
      <section className="verification-intelligence-panel" aria-labelledby={headingId}>
         <header className="verification-intelligence-heading">
            <div className="verification-intelligence-heading-row">
               <div>
                  <span className="verification-intelligence-eyebrow">Review support</span>
                  <h5 id={headingId}>Verification intelligence</h5>
               </div>
               <Badge tone="neutral">Non-authoritative</Badge>
            </div>
            <p>Persisted evidence and institutional context only. This panel does not recommend or set a verdict.</p>
         </header>

         {loading ? (
            <p role="status" className="verification-intelligence-loading">
               Loading intelligence… The case and decision workflow remain available.
            </p>
         ) : currentResult.error ? (
            <div className="verification-intelligence-error" role="alert">
               <strong>Verification intelligence unavailable</strong>
               <p>{currentResult.error}</p>
               <p>Case detail and the existing Adjudication workflow remain available.</p>
               <Button
                  type="button"
                  variant="secondary"
                  density="compact"
                  className="verification-intelligence-retry"
                  onClick={() => setRequestVersion((version) => version + 1)}
               >
                  Retry intelligence
               </Button>
            </div>
         ) : (
            <IntelligenceContent data={currentResult.data} />
         )}
      </section>
   );
}
