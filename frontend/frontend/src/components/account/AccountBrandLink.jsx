import { Link } from "react-router-dom";
import LogoImage from "../../assets/truthlens_logo.png";
import "./AccountBrandLink.css";

function AccountBrandLink({ tone = "default", className = "" }) {
   const resolvedTone = tone === "inverse" ? "inverse" : "default";
   const classes = [
      "account-brand-link",
      `account-brand-link--${resolvedTone}`,
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <Link to="/landing-page" className={classes} aria-label="Return to TruthLens home">
         <img src={LogoImage} alt="" className="account-brand-link__logo" />
         <span>TruthLens</span>
      </Link>
   );
}

export default AccountBrandLink;
