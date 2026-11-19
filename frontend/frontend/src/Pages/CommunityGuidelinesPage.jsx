import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { resolveApiEndpoint } from "../utils/api";
import "./CommunityGuidelinesPage.css";

function ruleAnchorId(code) {
   return `rule-${String(code || "").toLowerCase().replaceAll("_", "-")}`;
}

function CommunityGuidelinesContent({ requestedVersion, locationHash }) {
   const [policy, setPolicy] = useState(null);
   const [error, setError] = useState(false);

   useEffect(() => {
      let active = true;
      const endpoint = resolveApiEndpoint("COMMUNITY_GUIDELINES");
      const url = requestedVersion
         ? `${endpoint}?${new URLSearchParams({ version: requestedVersion }).toString()}`
         : endpoint;

      fetch(url)
         .then(async (response) => {
            if (!response.ok) throw new Error("Policy unavailable");
            return response.json();
         })
         .then((payload) => {
            if (!active) return;
            setPolicy(payload);
            setError(false);
         })
         .catch(() => {
            if (active) setError(true);
         });

      return () => {
         active = false;
      };
   }, [requestedVersion]);

   useEffect(() => {
      if (!policy) return undefined;

      const frame = window.requestAnimationFrame(() => {
         if (!locationHash) {
            window.scrollTo({ top: 0, left: 0, behavior: "auto" });
            return;
         }

         const targetId = decodeURIComponent(locationHash.slice(1));
         const target = document.getElementById(targetId);
         if (!target) return;

         target.scrollIntoView({ block: "start", behavior: "auto" });
         target.focus({ preventScroll: true });
      });

      return () => window.cancelAnimationFrame(frame);
   }, [locationHash, policy]);

   if (error) {
      return (
         <div className="community-guidelines-page">
            <section className="community-guidelines-state">
               <h1>Community Guidelines version unavailable</h1>
               <p>
                  {requestedVersion
                     ? `TruthLens does not have Community Guidelines version ${requestedVersion}.`
                     : "TruthLens could not load the current Community Guidelines."}
               </p>
               <Link to="/community-guidelines">View current Guidelines</Link>
            </section>
         </div>
      );
   }

   if (!policy) {
      return (
         <div className="community-guidelines-page">
            <section className="community-guidelines-state" role="status">
               <p>Loading Community Guidelines…</p>
            </section>
         </div>
      );
   }

   const enforcement = policy.account_enforcement;
   const explanation = policy.public_explanation;
   const restrictionCapabilities = explanation?.restriction_capabilities;

   return (
      <div className="community-guidelines-page">
         <header className="community-guidelines-hero">
            <span>TruthLens Community</span>
            <h1>{policy.title}</h1>
            <p>
               These rules explain safe Community participation and how Platform Safety reviews Community conduct.
            </p>
            <small>
               Version {policy.version}
               {policy.published_on ? ` · Published ${policy.published_on}` : ""}
            </small>
         </header>

         <div className="community-guidelines-layout">
            <aside className="community-guidelines-toc" aria-label="On this page">
               <strong>On this page</strong>
               <nav>
                  <a href="#how-reporting-works">How reporting works</a>
                  <a href="#verification-boundary">Safety report or Verify?</a>
                  {explanation && <a href="#how-safety-works">How Safety decisions work</a>}
                  <a href="#community-rules">Community safety rules</a>
                  {enforcement && <a href="#account-enforcement">Account actions</a>}
                  {restrictionCapabilities && <a href="#restriction-access">During a restriction</a>}
                  {explanation && <a href="#reviews">Reviews and corrections</a>}
                  {policy.rules.map((rule) => (
                     <a key={rule.code} href={`#${ruleAnchorId(rule.code)}`}>
                        {rule.title}
                     </a>
                  ))}
                  <a href="#version-history">Version history</a>
               </nav>
            </aside>

            <article className="community-guidelines-content">
               <section id="how-reporting-works" tabIndex="-1">
                  <h2>How reporting works</h2>
                  <p>{policy.reporting_note}</p>
                  <p>
                     Reporting sends content to Platform Safety for review. A report does not automatically remove content
                     and does not automatically prove that the selected concern occurred.
                  </p>
               </section>

               <section id="verification-boundary" className="community-guidelines-callout" tabIndex="-1">
                  <h2>Safety report or Verify?</h2>
                  <p>{policy.verification_boundary}</p>
                  <div className="community-guidelines-choice-grid">
                     <div>
                        <strong>Report</strong>
                        <span>Use this when Community content may break a safety rule.</span>
                     </div>
                     <div>
                        <strong>Verify</strong>
                        <span>Use this when you think a factual claim may be wrong or misleading.</span>
                     </div>
                  </div>
               </section>

               {explanation ? (
                  <section id="how-safety-works" tabIndex="-1">
                     <h2>How Safety decisions work</h2>
                     <p>Reports start a review. They do not decide the result.</p>
                     <ol className="community-guidelines-process">
                        {explanation.process_steps.map((step) => (
                           <li key={step.title}>
                              <strong>{step.title}</strong>
                              <span>{step.description}</span>
                           </li>
                        ))}
                     </ol>
                  </section>
               ) : null}

               <section id="community-rules" tabIndex="-1">
                  <h2>Community safety rules</h2>
                  <p>
                     Platform Safety reviews the content and its context before deciding whether one of these rules was broken.
                  </p>
               </section>

               {policy.rules.map((rule) => (
                  <section key={rule.code} id={ruleAnchorId(rule.code)} tabIndex="-1">
                     <h2>{rule.title}</h2>
                     <p>{rule.description}</p>
                     {rule.examples?.length ? (
                        <div className="community-guidelines-rule-extra">
                           <h3>Common examples</h3>
                           <ul>
                              {rule.examples.map((example) => (
                                 <li key={example}>{example}</li>
                              ))}
                           </ul>
                        </div>
                     ) : null}
                     {rule.boundary ? (
                        <div className="community-guidelines-boundary">
                           <strong>Important boundary</strong>
                           <p>{rule.boundary}</p>
                        </div>
                     ) : null}
                  </section>
               ))}

               {enforcement ? (
                  <section id="account-enforcement" className="community-guidelines-enforcement" tabIndex="-1">
                     <h2>Community account actions</h2>
                     <p>{enforcement.overview}</p>

                     <div className="community-guidelines-action-list">
                        {enforcement.actions.map((action) => (
                           <div key={action.code} className="community-guidelines-action">
                              <h3>{action.title}</h3>
                              <p>{action.description}</p>
                           </div>
                        ))}
                     </div>

                     <h3>How Platform Safety decides</h3>
                     <p>{enforcement.decision_factors}</p>
                     <p>{enforcement.automation_boundary}</p>
                  </section>
               ) : null}

               {restrictionCapabilities ? (
                  <section id="restriction-access" tabIndex="-1">
                     <h2>During a Community restriction</h2>
                     <p>
                        A Community restriction limits participation. It does not disable the whole TruthLens account.
                     </p>
                     <div className="community-guidelines-permission-grid">
                        <div>
                           <h3>Still available</h3>
                           <ul>
                              {restrictionCapabilities.available.map((item) => (
                                 <li key={item.code}>{item.label}</li>
                              ))}
                           </ul>
                        </div>
                        <div>
                           <h3>Not available while restricted</h3>
                           <ul>
                              {restrictionCapabilities.unavailable.map((item) => (
                                 <li key={item.code}>{item.label}</li>
                              ))}
                           </ul>
                        </div>
                     </div>
                  </section>
               ) : null}

               {explanation ? (
                  <section id="reviews" tabIndex="-1">
                     <h2>Reviews and corrections</h2>
                     <div className="community-guidelines-review-grid">
                        <div>
                           <h3>Content reconsideration</h3>
                           <p>{explanation.content_reconsideration}</p>
                        </div>
                        <div>
                           <h3>Account-action review</h3>
                           <p>{explanation.account_action_review}</p>
                        </div>
                     </div>
                     <p>
                        If Platform Safety reverses the content decision, any account action that depended on that decision
                        is also corrected.
                     </p>
                     <div className="community-guidelines-safety-note" role="note">
                        <strong>Immediate safety concern?</strong>
                        <p>{explanation.immediate_safety_note}</p>
                     </div>
                  </section>
               ) : enforcement ? (
                  <section id="reviews" tabIndex="-1">
                     <h2>Review and continued access</h2>
                     <p>{enforcement.review_right}</p>
                     <p>{enforcement.reporting_while_restricted}</p>
                     <p>{enforcement.ban_evasion}</p>
                     <p>{enforcement.profile_reporting_limitation}</p>
                  </section>
               ) : null}

               <section id="version-history" tabIndex="-1">
                  <h2>Version history</h2>
                  <p className="community-guidelines-version-note">
                     Older versions stay available so past Safety decisions can be read against the policy version used at the time.
                  </p>
                  <div className="community-guidelines-version-list">
                     {policy.versions.map((version) => (
                        <Link
                           key={version.version}
                           className={`community-guidelines-version ${version.version === policy.version ? "is-viewing" : ""}`}
                           to={
                              version.current
                                 ? "/community-guidelines"
                                 : `/community-guidelines?version=${encodeURIComponent(version.version)}`
                           }
                        >
                           <span>
                              <strong>Version {version.version}</strong>
                              <small>{version.published_on}</small>
                           </span>
                           <p>{version.summary}</p>
                           {version.version === policy.version && <em>Viewing</em>}
                        </Link>
                     ))}
                  </div>
               </section>
            </article>
         </div>
      </div>
   );
}

function CommunityGuidelinesPage() {
   const location = useLocation();
   const searchParams = new URLSearchParams(location.search);
   const requestedVersion = (searchParams.get("version") || "")
      .split("#", 1)[0]
      .trim();

   return (
      <CommunityGuidelinesContent
         key={requestedVersion || "current"}
         requestedVersion={requestedVersion}
         locationHash={location.hash}
      />
   );
}

export default CommunityGuidelinesPage;
