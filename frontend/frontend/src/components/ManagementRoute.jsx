import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import {
   canAccessManagementConsole,
   canAccessPlatformSafetyConsole,
} from "../utils/management";

function ManagementRoute() {
   const { user } = useAuth();
   const location = useLocation();
   const isPlatformAdmin = canAccessManagementConsole(user);
   const canAccessSafety = canAccessPlatformSafetyConsole(user);

   if (!canAccessSafety) {
      return <Navigate to="/community" state={{ from: location }} replace />;
   }

   if (!isPlatformAdmin && !location.pathname.startsWith("/management/safety")) {
      return <Navigate to="/management/safety" state={{ from: location }} replace />;
   }

   return <Outlet />;
}

export default ManagementRoute;
