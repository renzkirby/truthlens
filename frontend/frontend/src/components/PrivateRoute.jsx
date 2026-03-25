import { useAuth } from "../context/AuthContext";
import { Navigate, Outlet, useLocation } from "react-router-dom";

function PrivateRoute({ requiredRole, children }) {
   const { token, user } = useAuth();
   const location = useLocation();

   if (!token) {
      return (
         <Navigate
            to="/login"
            state={{ from: location }}
         />
      );
   }

   if (requiredRole && user?.role !== requiredRole) {
      return (
         <Navigate
            to="/dashboard"
            state={{ from: location }}
         />
      );
   }

   return <Outlet />;
}

export default PrivateRoute;
