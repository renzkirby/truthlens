import { forwardRef } from "react";
import "./Badge.css";

const BADGE_TONES = new Set(["neutral", "info", "success", "warning", "critical"]);

const Badge = forwardRef(function Badge(
   { children, tone = "neutral", icon, className = "", ...spanProps },
   ref,
) {
   if (children === undefined || children === null || children === false) {
      throw new Error("Badge requires text content in addition to any icon or color treatment.");
   }

   const resolvedTone = BADGE_TONES.has(tone) ? tone : "neutral";
   const classes = ["tl-badge", `tl-badge--${resolvedTone}`, className].filter(Boolean).join(" ");

   return (
      <span {...spanProps} ref={ref} className={classes}>
         {icon ? (
            <span className="tl-badge__icon" aria-hidden="true">
               {icon}
            </span>
         ) : null}
         <span className="tl-badge__label">{children}</span>
      </span>
   );
});

export default Badge;
