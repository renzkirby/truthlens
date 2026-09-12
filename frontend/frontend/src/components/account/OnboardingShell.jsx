import { Outlet } from "react-router-dom";
import AccountBrandLink from "./AccountBrandLink.jsx";
import "./OnboardingShell.css";

function OnboardingShell() {
   return (
      <div className="onboarding-shell">
         <div className="onboarding-shell__frame">
            <header className="onboarding-shell__header">
               <AccountBrandLink />
            </header>

            <main className="onboarding-shell__main">
               <Outlet />
            </main>
         </div>
      </div>
   );
}

export default OnboardingShell;
