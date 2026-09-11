import { Outlet } from "react-router-dom";
import PublicSiteHeader from "./PublicSiteHeader.jsx";
import PublicSiteFooter from "./PublicSiteFooter.jsx";
import "./PublicShell.css";

function PublicShell() {
   return (
      <div className="public-shell">
         <PublicSiteHeader />

         <main id="main-content" className="public-shell__main" tabIndex={-1}>
            <Outlet />
         </main>

         <PublicSiteFooter />
      </div>
   );
}

export default PublicShell;
