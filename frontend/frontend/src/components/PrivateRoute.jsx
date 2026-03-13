import { useAuth } from "../context/AuthContext";
import { Navigate, Outlet } from "react-router-dom";

function PrivateRoute({ children }) {
   const { token } = useAuth();

   return token ? <Outlet /> : <Navigate to="/login" />;
}

export default PrivateRoute;
