import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { resolveApiEndpoint } from "../utils/api";
import "./CommunityGuidelinesPage.css";

function CommunityGuidelinesPage() {
   const [searchParams] = useSearchParams();
   const [policy, setPolicy] = useState(null);
   const [error, setError] = useState(false);
   const requestedVersion = (searchParams.get("version") || "").trim();

   useEffect(() => {
      let active = true;
      const endpoint = resolveApiEndpoint("COMMUNITY_GUIDELINES");
      const url = requestedVersion
         ? `${endpoint}?${new URLSearchParams({ version: requestedVersion }).toString()}`
         : endpoint;

      setPolicy(null);
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

   if (error) {
      return (
         <div className="community-guidelines-page">
            <section className="community-guidelines-state">
               <h1>Community Guidelines unavailable</h1>
               <p>
                  {requestedVersion
                     ? `TruthLens could not load Community Guidelines version ${requestedVersion}.`
                     : "TruthLens could not load the current Community Guidelines."}
               </p>
               <Link to="/community-guidelines">View current guidelines</Link>
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

   return (
      <div className="community-guidelines-page">
         <header className="community-guidelines-hero">
            <span>TruthLens Community</span>
            <h1>{policy.title}</h1>
            <p>
               These rules guide Platform Safety decisions about abuse, spam, privacy,
               threats, and other Community conduct.
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
                  <a href="#verification-boundary">Safety and fact-checking</a>
                  {enforcement && <a href="#account-enforcement">Account enforcement</a>}
                  {policy.rules.map((rule) => (
                     <a key={rule.code} href={`#rule-${rule.code.toLowerCase()}`}>
                        {rule.title}
                     </a>
                  ))}
                  <a href="#version-history">Version history</a>
               </nav>
            </aside>

            <article className="community-guidelines-content">
               <section id="how-reporting-works">
                  <h2>How reporting works</h2>
                  <p>{policy.reporting_note}</p>
                  <p>
                     Reporting sends content to Platform Safety for review. A report does
                     not automatically remove content and does not automatically prove that
                     the selected concern occurred.
                  </p>
               </section>

               <section id="verification-boundary" className="community-guidelines-callout">
                  <h2>Safety and fact-checking are different</h2>
                  <p>{policy.verification_boundary}</p>
               </section>

               {enforcement && (
                  <section id="account-enforcement" className="community-guidelines-enforcement">
                     <h2>Community account enforcement</h2>
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

                     <h3>Review and continued access</h3>
                     <p>{enforcement.review_right}</p>
                     <p>{enforcement.reporting_while_restricted}</p>

                     <h3>Scope and limitations</h3>
                     <p>{enforcement.ban_evasion}</p>
                     <p>{enforcement.profile_reporting_limitation}</p>
                  </section>
               )}

               <section>
                  <h2>Community safety rules</h2>
                  <p>
                     Platform Safety reviews the content and context before deciding whether
                     one of the rules below was violated.
                  </p>
               </section>

               {policy.rules.map((rule) => (
                  <section key={rule.code} id={`rule-${rule.code.toLowerCase()}`}>
                     <h2>{rule.title}</h2>
                     <p>{rule.description}</p>
                  </section>
               ))}

               <section id="version-history">
                  <h2>Version history</h2>
                  <p className="community-guidelines-version-note">
                     Older versions remain available so past Safety decisions can be read
                     against the policy version that applied when they were made.
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

export default CommunityGuidelinesPage;
