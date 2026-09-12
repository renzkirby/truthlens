import { Outlet } from "react-router-dom";

import "./WorkspaceShell.css";

function WorkspaceShell() {
   return (
      <div className="workspace-shell">
         <main className="workspace-shell__main">
            <Outlet />
         </main>
      </div>
   );
}

export default WorkspaceShell;
