import { forwardRef } from "react";
import "./actions.css";

const BUTTON_VARIANTS = new Set(["primary", "secondary", "ghost", "destructive"]);
const BUTTON_DENSITIES = new Set(["compact", "standard", "comfortable"]);

const Button = forwardRef(function Button(
   {
      children,
      variant = "primary",
      density = "standard",
      loading = false,
      loadingLabel = "Loading…",
      leadingIcon,
      trailingIcon,
      fullWidth = false,
      className = "",
      disabled = false,
      type = "button",
      "aria-busy": ariaBusy,
      ...buttonProps
   },
   ref,
) {
   const resolvedVariant = BUTTON_VARIANTS.has(variant) ? variant : "primary";
   const resolvedDensity = BUTTON_DENSITIES.has(density) ? density : "standard";
   const resolvedLoadingLabel = loadingLabel || "Loading…";
   const classes = [
      "tl-button",
      `tl-button--${resolvedVariant}`,
      `tl-button--${resolvedDensity}`,
      fullWidth ? "tl-button--full-width" : "",
      loading ? "tl-button--loading" : "",
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
         aria-busy={loading ? "true" : ariaBusy}
      >
         {loading ? (
            <>
               <span className="tl-button__spinner" aria-hidden="true" />
               <span className="tl-button__label">{resolvedLoadingLabel}</span>
            </>
         ) : (
            <>
               {leadingIcon ? (
                  <span className="tl-button__icon" aria-hidden="true">
                     {leadingIcon}
                  </span>
               ) : null}
               <span className="tl-button__label">{children}</span>
               {trailingIcon ? (
                  <span className="tl-button__icon" aria-hidden="true">
                     {trailingIcon}
                  </span>
               ) : null}
            </>
         )}
      </button>
   );
});

export default Button;
