import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import {
   canAccessManagementConsole,
   canAccessPlatformSafetyConsole,
} from "../utils/management";
import { canAccessWorkspace } from "../utils/workspace";

function CommunityParticipantRoute() {
   const { user } = useAuth();
   const location = useLocation();

   if (user?.community_identity?.can_participate !== false) {
      return <Outlet />;
   }

   const destination = canAccessManagementConsole(user)
      ? "/management"
      : canAccessPlatformSafetyConsole(user)
        ? "/management/safety"
        : canAccessWorkspace(user)
          ? "/workspace"
          : "/community";

   return <Navigate to={destination} state={{ from: location }} replace />;
}

export default CommunityParticipantRoute;
