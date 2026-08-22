import "./AuthRouteLoader.css";

function AuthRouteLoader() {
   return (
      <div className="auth-route-loader" role="status" aria-live="polite" aria-label="Loading your TruthLens session">
         <div className="auth-route-loader__spinner" aria-hidden="true" />

         <p className="auth-route-loader__text">Loading your session…</p>
      </div>
   );
}

export default AuthRouteLoader;
