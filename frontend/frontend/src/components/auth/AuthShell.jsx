import AccountBrandLink from "../account/AccountBrandLink.jsx";
import AccountSurface from "../account/AccountSurface.jsx";
import Icons from "../Icons.jsx";
import "./AuthShell.css";

function AuthShell({ eyebrow, title, description, highlights = [], children }) {
   return (
      <main className="auth-shell">
         <aside className="auth-brand-panel" aria-label="About TruthLens">
            <AccountBrandLink tone="inverse" />

            <div className="auth-brand-content">
               {eyebrow && <p className="auth-brand-eyebrow">{eyebrow}</p>}

               <p className="auth-brand-title">{title}</p>

               <p className="auth-brand-description">{description}</p>

               {highlights.length > 0 && (
                  <ul className="auth-highlight-list">
                     {highlights.map((highlight) => (
                        <li key={highlight}>
                           <span className="auth-highlight-icon" aria-hidden="true">
                              <Icons name="check-circle" size={18} />
                           </span>

                           <span>{highlight}</span>
                        </li>
                     ))}
                  </ul>
               )}
            </div>

            <div className="auth-decoration auth-decoration-one" aria-hidden="true" />
            <div className="auth-decoration auth-decoration-two" aria-hidden="true" />
         </aside>

         <div className="auth-form-panel">
            <div className="auth-mobile-brand">
               <AccountSurface>
                  <AccountBrandLink />
               </AccountSurface>
            </div>

            <AccountSurface>{children}</AccountSurface>
         </div>
      </main>
   );
}

export default AuthShell;
