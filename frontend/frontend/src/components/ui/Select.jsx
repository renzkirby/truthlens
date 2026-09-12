import { forwardRef } from "react";
import "./fields.css";

const FIELD_DENSITIES = new Set(["compact", "standard", "comfortable"]);
const FIELD_SURFACES = new Set(["surface", "subtle"]);

const Select = forwardRef(function Select(
   {
      children,
      density = "standard",
      invalid = false,
      surface = "surface",
      className = "",
      "aria-invalid": ariaInvalid,
      ...selectProps
   },
   ref,
) {
   const resolvedDensity = FIELD_DENSITIES.has(density) ? density : "standard";
   const resolvedSurface = FIELD_SURFACES.has(surface) ? surface : "surface";
   const resolvedInvalid = invalid || ariaInvalid === true || ariaInvalid === "true";
   const classes = [
      "tl-select",
      `tl-select--${resolvedDensity}`,
      `tl-select--${resolvedSurface}`,
      resolvedInvalid ? "tl-select--invalid" : "",
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <select
         {...selectProps}
         ref={ref}
         className={classes}
         aria-invalid={invalid ? "true" : ariaInvalid}
      >
         {children}
      </select>
   );
});

export default Select;
