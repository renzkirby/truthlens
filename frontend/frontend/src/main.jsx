import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";
import { AuthProvider } from "./providers/AuthProvider";
import { NotificationProvider } from "./providers/NotificationProvider";
import { GoogleOAuthProvider } from "@react-oauth/google";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID;

createRoot(document.getElementById("root")).render(
   <StrictMode>
      <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
         <AuthProvider>
            <NotificationProvider>
               <App />
            </NotificationProvider>
         </AuthProvider>
      </GoogleOAuthProvider>
   </StrictMode>,
);
