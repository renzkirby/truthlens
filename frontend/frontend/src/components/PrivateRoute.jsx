import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import AuthRouteLoader from "./AuthRouteLoader";
import { canAccessWorkspace } from "../utils/workspace";

function PrivateRoute({ requireWorkspace = false }) {
   const { token, user, loading, sessionRestoreError, retrySessionRestore } = useAuth();
   const location = useLocation();

   // Session restoration may be waiting for a transient outage to recover.
   if (loading) {
      return <AuthRouteLoader error={sessionRestoreError} onRetry={retrySessionRestore} />;
   }

   // Not authenticated
   if (!token) {
      return <Navigate to="/login" state={{ from: location }} replace />;
   }

   // Operational workspace authorization comes
   // from the backend capability context rather
   // than the legacy user role.
   if (requireWorkspace && !canAccessWorkspace(user)) {
      return <Navigate to="/dashboard" state={{ from: location }} replace />;
   }

   return <Outlet />;
}

export default PrivateRoute;
