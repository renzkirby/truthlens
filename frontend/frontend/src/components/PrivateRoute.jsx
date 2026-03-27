import { useAuth } from "../context/AuthContext";
import { Navigate, Outlet, useLocation } from "react-router-dom";

function PrivateRoute({ requiredRole, children }) {
   const { token, user, loading } = useAuth();
   const location = useLocation();

   // Not authenticated - redirect to login
   if (!token) {
      return (
         <Navigate
            to="/login"
            state={{ from: location }}
         />
      );
   }

   // Still loading user data - show loading spinner
   if (loading) {
      return (
         <div
            style={{
               display: "flex",
               alignItems: "center",
               justifyContent: "center",
               width: "100vw",
               height: "100vh",
               background: "#f9fafb",
            }}>
            <div
               style={{
                  textAlign: "center",
               }}>
               <div
                  style={{
                     width: "40px",
                     height: "40px",
                     margin: "0 auto 16px",
                     border: "3px solid #e5e7eb",
                     borderTopColor: "#10b981",
                     borderRadius: "50%",
                     animation: "spin 0.8s linear infinite",
                  }}
               />
               <p style={{ color: "#6b7280", fontSize: "14px" }}>Loading...</p>
               <style>{`
                  @keyframes spin {
                     to { transform: rotate(360deg); }
                  }
               `}</style>
            </div>
         </div>
      );
   }

   // Has required role
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
