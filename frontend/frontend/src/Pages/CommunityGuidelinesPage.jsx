import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { resolveApiEndpoint } from "../utils/api";
import "./CommunityGuidelinesPage.css";

function CommunityGuidelinesPage() {
   const [policy, setPolicy] = useState(null);
   const [error, setError] = useState(false);

   useEffect(() => {
      let active = true;
      fetch(resolveApiEndpoint("COMMUNITY_GUIDELINES"))
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
   }, []);

   if (error) {
      return (
         <div className="community-guidelines-page">
            <section className="community-guidelines-state">
               <h1>Community Guidelines unavailable</h1>
               <p>TruthLens could not load the current Community Guidelines.</p>
               <Link to="/landing">Return to TruthLens</Link>
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

   return (
      <div className="community-guidelines-page">
         <header className="community-guidelines-hero">
            <span>TruthLens Community</span>
            <h1>{policy.title}</h1>
            <p>
               These rules guide Platform Safety decisions about abuse, spam, privacy,
               threats, and other Community conduct.
            </p>
            <small>Version {policy.version}</small>
         </header>

         <div className="community-guidelines-layout">
            <aside className="community-guidelines-toc" aria-label="On this page">
               <strong>On this page</strong>
               <nav>
                  <a href="#how-reporting-works">How reporting works</a>
                  <a href="#verification-boundary">Safety and fact-checking</a>
                  {policy.rules.map((rule) => (
                     <a key={rule.code} href={`#rule-${rule.code.toLowerCase()}`}>
                        {rule.title}
                     </a>
                  ))}
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
            </article>
         </div>
      </div>
   );
}

export default CommunityGuidelinesPage;
