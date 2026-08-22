import { Link } from "react-router-dom";
import LogoImage from "../../assets/truthlens_logo.png";
import Icons from "../Icons.jsx";
import "./AuthShell.css";

function AuthShell({ eyebrow, title, description, highlights = [], children }) {
   return (
      <main className="auth-shell">
         <section className="auth-brand-panel" aria-label="TruthLens introduction">
            <Link to="/" className="auth-brand-link" aria-label="Return to TruthLens home">
               <img src={LogoImage} alt="" className="auth-brand-logo" />
               <span>TruthLens</span>
            </Link>

            <div className="auth-brand-content">
               {eyebrow && <p className="auth-brand-eyebrow">{eyebrow}</p>}

               <h1 className="auth-brand-title">{title}</h1>

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
         </section>

         <section className="auth-form-panel">
            <div className="auth-mobile-brand">
               <Link to="/" className="auth-brand-link" aria-label="Return to TruthLens home">
                  <img src={LogoImage} alt="" className="auth-brand-logo" />
                  <span>TruthLens</span>
               </Link>
            </div>

            <div className="auth-form-container">{children}</div>
         </section>
      </main>
   );
}

export default AuthShell;
