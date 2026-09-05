import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { canAccessWorkspace } from "../utils/workspace";
import AuthRouteLoader from "./AuthRouteLoader";

function RootRedirect() {
   const { token, user, loading } = useAuth();

   if (loading) {
      return <AuthRouteLoader />;
   }

   if (!token) {
      return <Navigate to="/login" replace />;
   }

   const destination = canAccessWorkspace(user) ? "/workspace" : "/community";

   return <Navigate to={destination} replace />;
}

export default RootRedirect;
