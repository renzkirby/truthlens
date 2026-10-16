import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { canAccessManagementConsole } from "../utils/management";

function ManagementRoute() {
   const { user } = useAuth();
   const location = useLocation();

   if (!canAccessManagementConsole(user)) {
      return <Navigate to="/dashboard" state={{ from: location }} replace />;
   }

   return <Outlet />;
}

export default ManagementRoute;
