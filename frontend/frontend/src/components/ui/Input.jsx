import { forwardRef } from "react";
import "./fields.css";

const FIELD_DENSITIES = new Set(["compact", "standard", "comfortable"]);
const FIELD_SURFACES = new Set(["surface", "subtle"]);
const UNSUPPORTED_INPUT_TYPES = new Set(["checkbox", "radio", "file"]);

const Input = forwardRef(function Input(
   {
      density = "standard",
      invalid = false,
      surface = "surface",
      leadingIcon,
      trailingAdornment,
      className = "",
      type = "text",
      "aria-invalid": ariaInvalid,
      ...inputProps
   },
   ref,
) {
   if (UNSUPPORTED_INPUT_TYPES.has(type)) {
      throw new Error(`Input does not support type="${type}".`);
   }

   const resolvedDensity = FIELD_DENSITIES.has(density) ? density : "standard";
   const resolvedSurface = FIELD_SURFACES.has(surface) ? surface : "surface";
   const resolvedInvalid = invalid || ariaInvalid === true || ariaInvalid === "true";
   const wrapperClasses = [
      "tl-field",
      leadingIcon ? "tl-field--has-leading" : "",
      trailingAdornment ? "tl-field--has-trailing" : "",
   ]
      .filter(Boolean)
      .join(" ");
   const inputClasses = [
      "tl-input",
      `tl-input--${resolvedDensity}`,
      `tl-input--${resolvedSurface}`,
      resolvedInvalid ? "tl-input--invalid" : "",
      className,
   ]
      .filter(Boolean)
      .join(" ");

   return (
      <span className={wrapperClasses}>
         {leadingIcon ? (
            <span className="tl-field__leading" aria-hidden="true">
               {leadingIcon}
            </span>
         ) : null}
         <input
            {...inputProps}
            ref={ref}
            type={type}
            className={inputClasses}
            aria-invalid={invalid ? "true" : ariaInvalid}
         />
         {trailingAdornment ? <span className="tl-field__trailing">{trailingAdornment}</span> : null}
      </span>
   );
});

export default Input;
