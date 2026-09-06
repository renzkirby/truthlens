import { useState } from "react";
import { Building2 } from "lucide-react";
import "./PartnerLogo.css";

function PartnerLogo({ logoUrl, organizationName, size = "card" }) {
   const [failedLogoUrl, setFailedLogoUrl] = useState(null);
   const showImage = Boolean(logoUrl) && failedLogoUrl !== logoUrl;

   return (
      <div className={`partner-logo partner-logo--${size}`}>
         {showImage ? (
            <img src={logoUrl} alt={`${organizationName} logo`} onError={() => setFailedLogoUrl(logoUrl)} />
         ) : (
            <Building2 aria-hidden="true" />
         )}
      </div>
   );
}

export default PartnerLogo;
