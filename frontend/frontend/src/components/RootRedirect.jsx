import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { getDefaultAuthenticatedDestination } from "../utils/authNavigation";
import AuthRouteLoader from "./AuthRouteLoader";

function RootRedirect() {
   const { token, user, loading, sessionRestoreError, retrySessionRestore } = useAuth();

   if (loading) {
      return <AuthRouteLoader error={sessionRestoreError} onRetry={retrySessionRestore} />;
   }

   if (!token) {
      return <Navigate to="/landing" replace />;
   }

   const destination = getDefaultAuthenticatedDestination(user);

   return <Navigate to={destination} replace />;
}

export default RootRedirect;
