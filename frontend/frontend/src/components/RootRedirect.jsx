import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import AuthRouteLoader from "./AuthRouteLoader";

function RootRedirect() {
   const { token, user, loading } = useAuth();

   if (loading) {
      return <AuthRouteLoader />;
   }

   if (!token) {
      return <Navigate to="/login" replace />;
   }

   const isModerator = user?.role === "MOD" || user?.role === "MODERATOR";

   return <Navigate to={isModerator ? "/moderation" : "/community"} replace />;
}

export default RootRedirect;
