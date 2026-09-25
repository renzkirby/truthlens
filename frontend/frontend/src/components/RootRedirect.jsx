import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { canAccessWorkspace } from "../utils/workspace";
import AuthRouteLoader from "./AuthRouteLoader";

function RootRedirect() {
   const { token, user, loading, sessionRestoreError, retrySessionRestore } = useAuth();

   if (loading) {
      return <AuthRouteLoader error={sessionRestoreError} onRetry={retrySessionRestore} />;
   }

   if (!token) {
      return <Navigate to="/landing" replace />;
   }

   const destination = canAccessWorkspace(user) ? "/workspace" : "/community";

   return <Navigate to={destination} replace />;
}

export default RootRedirect;
