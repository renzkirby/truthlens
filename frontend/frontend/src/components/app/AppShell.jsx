import { Outlet, useLocation } from "react-router-dom";

import NavigationBar from "../NavigationBar.jsx";

import "./AppShell.css";

function AppShell() {
   const location = useLocation();

   return (
      <div className="app-shell">
         <NavigationBar key={location.pathname} />

         <div className="app-shell__content">
            <Outlet />
         </div>
      </div>
   );
}

export default AppShell;
