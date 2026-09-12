import { Outlet } from "react-router-dom";
import AccountBrandLink from "./AccountBrandLink.jsx";
import "./AccountActionShell.css";

function AccountActionShell() {
   return (
      <div className="account-action-shell">
         <div className="account-action-shell__frame">
            <header className="account-action-shell__header">
               <AccountBrandLink />
            </header>

            <main className="account-action-shell__main">
               <Outlet />
            </main>
         </div>
      </div>
   );
}

export default AccountActionShell;
