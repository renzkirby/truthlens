import { forwardRef } from "react";
import "./actions.css";

const ICON_BUTTON_VARIANTS = new Set(["ghost", "secondary", "destructive"]);
const ICON_BUTTON_DENSITIES = new Set(["compact", "standard", "comfortable"]);

const IconButton = forwardRef(function IconButton(
   {
      children,
      icon,
      variant = "ghost",
      density = "standard",
      loading = false,
      className = "",
      disabled = false,
      type = "button",
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledBy,
      "aria-busy": ariaBusy,
      ...buttonProps
   },
   ref,
) {
   if (!ariaLabel && !ariaLabelledBy) {
      throw new Error("IconButton requires an aria-label or aria-labelledby.");
   }

   const resolvedVariant = ICON_BUTTON_VARIANTS.has(variant) ? variant : "ghost";
   const resolvedDensity = ICON_BUTTON_DENSITIES.has(density) ? density : "standard";
   const resolvedIcon = icon ?? children;
   const classes = [
      "tl-icon-button",
      `tl-icon-button--${resolvedVariant}`,
      `tl-icon-button--${resolvedDensity}`,
      loading ? "tl-icon-button--loading" : "",
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <button
         {...buttonProps}
         ref={ref}
         type={type}
         className={classes}
         disabled={disabled || loading}
         aria-label={ariaLabel}
         aria-labelledby={ariaLabelledBy}
         aria-busy={loading ? "true" : ariaBusy}
      >
         {loading ? (
            <span className="tl-button__spinner" aria-hidden="true" />
         ) : (
            <span className="tl-icon-button__icon" aria-hidden="true">
               {resolvedIcon}
            </span>
         )}
      </button>
   );
});

export default IconButton;
