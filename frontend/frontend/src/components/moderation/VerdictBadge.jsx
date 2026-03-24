import { VERDICT_CONFIG } from "./moderationUtils";

function VerdictBadge({ verdict }) {
   const config = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNVERIFIED;

   return (
      <span
         className="mod-verdict-badge"
         style={{
            color: config.color,
            backgroundColor: config.bg,
            borderColor: config.border,
         }}>
         {config.label}
      </span>
   );
}

export default VerdictBadge;
