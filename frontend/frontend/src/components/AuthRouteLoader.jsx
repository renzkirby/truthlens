import "./AuthRouteLoader.css";

function AuthRouteLoader({ error = null, onRetry = null }) {
   return (
      <div className="auth-route-loader">
         {!error && <div className="auth-route-loader__spinner" aria-hidden="true" />}

         <p className="auth-route-loader__text" role="status" aria-live="polite">
            {error?.message || "Loading your session…"}
         </p>

         {error && onRetry && (
            <button className="auth-route-loader__retry" type="button" onClick={onRetry}>
               Try again
            </button>
         )}
      </div>
   );
}

export default AuthRouteLoader;
