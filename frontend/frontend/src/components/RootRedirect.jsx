import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { canAccessWorkspace } from "../utils/workspace";
import {
   canAccessManagementConsole,
   isPlatformSafetyModerator,
} from "../utils/management";
import AuthRouteLoader from "./AuthRouteLoader";

function RootRedirect() {
   const { token, user, loading, sessionRestoreError, retrySessionRestore } = useAuth();

   if (loading) {
      return <AuthRouteLoader error={sessionRestoreError} onRetry={retrySessionRestore} />;
   }

   if (!token) {
      return <Navigate to="/landing" replace />;
   }

   const destination = canAccessManagementConsole(user)
      ? "/management"
      : isPlatformSafetyModerator(user)
        ? "/management/safety"
        : canAccessWorkspace(user)
          ? "/workspace"
          : "/community";

   return <Navigate to={destination} replace />;
}

export default RootRedirect;
