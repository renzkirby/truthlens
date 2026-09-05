import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import AuthRouteLoader from "./AuthRouteLoader";
import { canAccessWorkspace } from "../utils/workspace";

function PrivateRoute({ requiredRole, requireWorkspace = false }) {
   const { token, user, loading } = useAuth();
   const location = useLocation();

   const normalizedUserRole = user?.role === "MODERATOR" ? "MOD" : user?.role;

   const normalizedRequiredRole = requiredRole === "MODERATOR" ? "MOD" : requiredRole;

   // Not authenticated
   if (!token) {
      return <Navigate to="/login" state={{ from: location }} replace />;
   }

   // Authentication context is still loading.
   if (loading) {
      return <AuthRouteLoader />;
   }

   // Operational workspace authorization comes
   // from the backend capability context rather
   // than the legacy user role.
   if (requireWorkspace && !canAccessWorkspace(user)) {
      return <Navigate to="/dashboard" state={{ from: location }} replace />;
   }

   // Keep legacy role protection available for
   // routes that have not yet migrated.
   if (normalizedRequiredRole && normalizedUserRole !== normalizedRequiredRole) {
      return <Navigate to="/dashboard" state={{ from: location }} replace />;
   }

   return <Outlet />;
}

export default PrivateRoute;
