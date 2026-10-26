import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { getDefaultAuthenticatedDestination } from "../utils/authNavigation";

function CommunityParticipantRoute() {
   const { user } = useAuth();
   const location = useLocation();

   if (user?.community_identity?.can_participate !== false) {
      return <Outlet />;
   }

   const destination = getDefaultAuthenticatedDestination(user);

   return <Navigate to={destination} state={{ from: location }} replace />;
}

export default CommunityParticipantRoute;
