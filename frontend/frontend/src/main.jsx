import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/mona-sans/wght.css";
import "./index.css";
import App from "./App.jsx";
import { AuthProvider } from "./providers/AuthProvider";
import { NotificationProvider } from "./providers/NotificationProvider";
import { NotificationInboxProvider } from "./providers/NotificationInboxProvider";
import { GoogleOAuthProvider } from "@react-oauth/google";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID;

createRoot(document.getElementById("root")).render(
   <StrictMode>
      <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
         <AuthProvider>
            <NotificationProvider>
               <NotificationInboxProvider>
                  <App />
               </NotificationInboxProvider>
            </NotificationProvider>
         </AuthProvider>
      </GoogleOAuthProvider>
   </StrictMode>,
);
