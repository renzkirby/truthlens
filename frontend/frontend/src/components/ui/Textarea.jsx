import { forwardRef } from "react";
import "./fields.css";

const FIELD_DENSITIES = new Set(["compact", "standard", "comfortable"]);
const FIELD_SURFACES = new Set(["surface", "subtle"]);

const Textarea = forwardRef(function Textarea(
   {
      density = "standard",
      invalid = false,
      surface = "surface",
      className = "",
      "aria-invalid": ariaInvalid,
      ...textareaProps
   },
   ref,
) {
   const resolvedDensity = FIELD_DENSITIES.has(density) ? density : "standard";
   const resolvedSurface = FIELD_SURFACES.has(surface) ? surface : "surface";
   const resolvedInvalid = invalid || ariaInvalid === true || ariaInvalid === "true";
   const classes = [
      "tl-textarea",
      `tl-textarea--${resolvedDensity}`,
      `tl-textarea--${resolvedSurface}`,
      resolvedInvalid ? "tl-textarea--invalid" : "",
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <textarea
         {...textareaProps}
         ref={ref}
         className={classes}
         aria-invalid={invalid ? "true" : ariaInvalid}
      />
   );
});

export default Textarea;
