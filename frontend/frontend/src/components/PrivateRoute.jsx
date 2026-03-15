import { useAuth } from "../context/AuthContext";
import { Navigate, Outlet, useLocation } from "react-router-dom";

function PrivateRoute({ children }) {
   const { token } = useAuth();
   const location = useLocation();

   return token ? (
      <Outlet />
   ) : (
      <Navigate
         to="/login"
         state={{ from: location }}
      />
   );
}

export default PrivateRoute;
