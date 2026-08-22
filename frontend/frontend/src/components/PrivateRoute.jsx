import { useAuth } from "../hooks/useAuth";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import AuthRouteLoader from "./AuthRouteLoader";

function PrivateRoute({ requiredRole }) {
   const { token, user, loading } = useAuth();
   const location = useLocation();
   const normalizedUserRole = user?.role === "MODERATOR" ? "MOD" : user?.role;
   const normalizedRequiredRole = requiredRole === "MODERATOR" ? "MOD" : requiredRole;

   // Not authenticated - redirect to login
   if (!token) {
      return <Navigate to="/login" state={{ from: location }} />;
   }

   // Still loading user data - show loading spinner
   if (loading) {
      return <AuthRouteLoader />;
   }

   // Has required role
   if (normalizedRequiredRole && normalizedUserRole !== normalizedRequiredRole) {
      return <Navigate to="/dashboard" state={{ from: location }} />;
   }

   return <Outlet />;
}

export default PrivateRoute;
