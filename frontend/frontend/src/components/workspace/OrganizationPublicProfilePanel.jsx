import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import { resolveApiEndpoint } from "../../utils/api";
import Icons from "../Icons.jsx";

import "./OrganizationPublicProfilePanel.css";

const EMPTY_DRAFT = {
   description: "",
   website: "",
   logo_url: "",
   expertise_areas: "",
   public_profile_enabled: false,
   public_logo_enabled: false,
};

const EDITABLE_FIELDS = [
   "description",
   "website",
   "logo_url",
   "expertise_areas",
   "public_profile_enabled",
   "public_logo_enabled",
];

function formatStatus(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function profileToDraft(profile) {
   return {
      description: profile?.description ?? "",
      website: profile?.website ?? "",
      logo_url: profile?.logo_url ?? "",
      expertise_areas: Array.isArray(profile?.expertise_areas) ? profile.expertise_areas.join("\n") : "",
      public_profile_enabled: profile?.public_profile_enabled === true,
      public_logo_enabled: profile?.public_logo_enabled === true,
   };
}

function normalizeExpertiseAreas(value) {
   const entries = [];
   const seen = new Set();

   for (const line of value.split("\n")) {
      const entry = line.trim();

      if (!entry) {
         continue;
      }

      if (entry.length > 100) {
         return {
            error: `“${entry.slice(0, 32)}${entry.length > 32 ? "…" : ""}” exceeds 100 characters.`,
            value: [],
         };
      }

      const comparisonKey = entry.toLowerCase();

      if (!seen.has(comparisonKey)) {
         seen.add(comparisonKey);
         entries.push(entry);
      }
   }

   if (entries.length > 20) {
      return {
         error: "Enter no more than 20 expertise areas.",
         value: [],
      };
   }

   return {
      error: "",
      value: entries,
   };
}

function validateOptionalHttpUrl(value, label) {
   const trimmedValue = value.trim();

   if (!trimmedValue) {
      return "";
   }

   try {
      const parsedUrl = new URL(trimmedValue);

      if (!["http:", "https:"].includes(parsedUrl.protocol)) {
         return `${label} must use http:// or https://.`;
      }
   } catch {
      return `Enter a valid ${label.toLowerCase()} URL, including http:// or https://.`;
   }

   return "";
}

function normalizeProfileValues(draft) {
   const expertise = normalizeExpertiseAreas(draft.expertise_areas);

   return {
      values: {
         description: draft.description.trim(),
         website: draft.website.trim() || null,
         logo_url: draft.logo_url.trim() || null,
         expertise_areas: expertise.value,
         public_profile_enabled: draft.public_profile_enabled,
         public_logo_enabled: draft.public_logo_enabled,
      },
      expertiseError: expertise.error,
   };
}

function normalizeSavedValues(profile) {
   return {
      description: profile?.description ?? "",
      website: profile?.website || null,
      logo_url: profile?.logo_url || null,
      expertise_areas: Array.isArray(profile?.expertise_areas) ? profile.expertise_areas : [],
      public_profile_enabled: profile?.public_profile_enabled === true,
      public_logo_enabled: profile?.public_logo_enabled === true,
   };
}

function valuesMatch(left, right) {
   return JSON.stringify(left) === JSON.stringify(right);
}

function getVisibilityState(profile) {
   if (profile.publicly_visible === true) {
      return {
         className: "visible",
         icon: "check-circle",
         label: "Visible publicly",
         description:
            "This organization currently satisfies the public partner eligibility rules and has public presence enabled.",
      };
   }

   if (profile.public_profile_enabled !== true) {
      return {
         className: "disabled",
         icon: "eye-off",
         label: "Public profile disabled",
         description: "TruthLens will not list this organization publicly while public profile consent is disabled.",
      };
   }

   return {
      className: "unavailable",
      icon: "alert-circle",
      label: "Enabled, not currently public",
      description:
         "The profile preference is enabled, but TruthLens verification or partner status currently prevents public listing.",
   };
}

function getServerFieldErrors(error) {
   return EDITABLE_FIELDS.reduce((errors, field) => {
      const detail = error?.[field];

      if (detail) {
         errors[field] = Array.isArray(detail) ? detail.join(" ") : String(detail);
      }

      return errors;
   }, {});
}

function OrganizationPublicProfilePanel({ organizationId, requestVersion = 0 }) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();

   const [loading, setLoading] = useState(true);
   const [loadError, setLoadError] = useState("");
   const [savedProfile, setSavedProfile] = useState(null);
   const [draft, setDraft] = useState(EMPTY_DRAFT);
   const [saving, setSaving] = useState(false);
   const [saveError, setSaveError] = useState("");
   const [fieldErrors, setFieldErrors] = useState({});
   const [retryVersion, setRetryVersion] = useState(0);
   const profileRequestIdRef = useRef(0);

   const endpoint = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      return resolveApiEndpoint("ORGANIZATION_PUBLIC_PROFILE", organizationId);
   }, [organizationId]);

   useEffect(
      () => () => {
         profileRequestIdRef.current += 1;
      },
      [],
   );

   useEffect(() => {
      let cancelled = false;
      const requestId = profileRequestIdRef.current + 1;

      profileRequestIdRef.current = requestId;

      setSavedProfile(null);
      setDraft(EMPTY_DRAFT);
      setLoadError("");
      setSaveError("");
      setFieldErrors({});
      setSaving(false);

      if (!endpoint) {
         setLoading(false);
         return undefined;
      }

      setLoading(true);

      authFetch(endpoint, {
         method: "GET",
      })
         .then((profile) => {
            if (cancelled || profileRequestIdRef.current !== requestId) {
               return;
            }

            setSavedProfile(profile);
            setDraft(profileToDraft(profile));
         })
         .catch((error) => {
            if (cancelled || profileRequestIdRef.current !== requestId) {
               return;
            }

            setLoadError(error?.message || "Unable to load the organization's public profile settings.");
         })
         .finally(() => {
            if (!cancelled && profileRequestIdRef.current === requestId) {
               setLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, endpoint, requestVersion, retryVersion]);

   const dirty = useMemo(() => {
      if (!savedProfile) {
         return false;
      }

      return !valuesMatch(draft, profileToDraft(savedProfile));
   }, [draft, savedProfile]);

   const updateDraft = (field, value) => {
      setDraft((current) => ({
         ...current,
         [field]: value,
      }));
      setSaveError("");
      setFieldErrors((current) => {
         if (!current[field]) {
            return current;
         }

         const nextErrors = {
            ...current,
         };
         delete nextErrors[field];
         return nextErrors;
      });
   };

   const resetChanges = () => {
      setDraft(profileToDraft(savedProfile));
      setSaveError("");
      setFieldErrors({});
   };

   const handleSubmit = async (event) => {
      event.preventDefault();

      if (!savedProfile || !endpoint || saving) {
         return;
      }

      const { values, expertiseError } = normalizeProfileValues(draft);
      const nextFieldErrors = {
         website: validateOptionalHttpUrl(draft.website, "Website"),
         logo_url: validateOptionalHttpUrl(draft.logo_url, "Logo URL"),
         expertise_areas: expertiseError,
      };

      Object.keys(nextFieldErrors).forEach((field) => {
         if (!nextFieldErrors[field]) {
            delete nextFieldErrors[field];
         }
      });

      if (Object.keys(nextFieldErrors).length > 0) {
         setFieldErrors(nextFieldErrors);
         setSaveError("Review the highlighted fields before saving.");
         return;
      }

      const savedValues = normalizeSavedValues(savedProfile);
      const changes = EDITABLE_FIELDS.reduce((payload, field) => {
         if (!valuesMatch(values[field], savedValues[field])) {
            payload[field] = values[field];
         }

         return payload;
      }, {});

      if (Object.keys(changes).length === 0) {
         setDraft(profileToDraft(savedProfile));
         setSaveError("");
         setFieldErrors({});
         return;
      }

      setSaving(true);
      setSaveError("");
      setFieldErrors({});

      const requestId = profileRequestIdRef.current + 1;
      profileRequestIdRef.current = requestId;

      try {
         const profile = await authFetch(endpoint, {
            method: "PATCH",
            body: changes,
         });

         if (profileRequestIdRef.current !== requestId) {
            return;
         }

         setSavedProfile(profile);
         setDraft(profileToDraft(profile));
         setSaveError("");
         setFieldErrors({});

         addToast({
            type: "success",
            title: "Public profile updated",
            message: "The organization's public presence settings were saved.",
         });
      } catch (error) {
         if (profileRequestIdRef.current !== requestId) {
            return;
         }

         const serverFieldErrors = getServerFieldErrors(error);
         const firstFieldError = Object.values(serverFieldErrors)[0];
         const message =
            error?.detail ||
            firstFieldError ||
            error?.message ||
            "Unable to save the organization's public profile settings.";

         setFieldErrors(serverFieldErrors);
         setSaveError(message);

         addToast({
            type: "error",
            title: "Public profile not updated",
            message,
         });
      } finally {
         if (profileRequestIdRef.current === requestId) {
            setSaving(false);
         }
      }
   };

   return (
      <section className="org-public-profile-panel" aria-labelledby="org-public-profile-heading">
         <div className="org-public-profile-heading">
            <div>
               <span className="org-public-profile-eyebrow">Organization presentation</span>
               <h3 id="org-public-profile-heading">Public partner presence</h3>
               <p>Control what TruthLens may show publicly about this organization.</p>
            </div>
         </div>

         {loading ? (
            <div className="org-public-profile-state" aria-live="polite" aria-busy="true">
               <Icons name="loader" size={20} className="org-admin-spinner" />
               <span>Loading public profile settings…</span>
            </div>
         ) : loadError ? (
            <div className="org-public-profile-error" role="alert">
               <Icons name="alert-circle" size={18} />
               <div>
                  <strong>Public profile settings unavailable</strong>
                  <span>{loadError}</span>
                  <button type="button" onClick={() => setRetryVersion((current) => current + 1)}>
                     <Icons name="refresh-cw" size={14} />
                     Retry
                  </button>
               </div>
            </div>
         ) : savedProfile ? (
            <>
               <div className="org-public-profile-overview">
                  <div className="org-public-profile-identity">
                     <div className="org-public-profile-identity-icon" aria-hidden="true">
                        <Icons name="landmark" size={20} />
                     </div>
                     <div>
                        <strong>{savedProfile.name}</strong>
                        <span>{savedProfile.organization_type_label || formatStatus(savedProfile.organization_type)}</span>
                        {savedProfile.slug && <code>{savedProfile.slug}</code>}
                     </div>
                  </div>

                  <dl className="org-public-profile-statuses">
                     <div>
                        <dt>Verification</dt>
                        <dd>{formatStatus(savedProfile.verification_status)}</dd>
                     </div>
                     <div>
                        <dt>Partnership</dt>
                        <dd>{formatStatus(savedProfile.partner_status)}</dd>
                     </div>
                  </dl>

                  {(() => {
                     const visibility = getVisibilityState(savedProfile);

                     return (
                        <div className={`org-public-visibility ${visibility.className}`}>
                           <div>
                              <span aria-hidden="true">
                                 <Icons name={visibility.icon} size={16} />
                              </span>
                              <strong>{visibility.label}</strong>
                           </div>
                           <p>{visibility.description}</p>
                        </div>
                     );
                  })()}
               </div>

               <form className="org-public-profile-form" onSubmit={handleSubmit} aria-busy={saving ? "true" : undefined}>
                  <div className="org-public-profile-fields">
                     <div className="org-public-profile-field org-public-profile-field-wide">
                        <label htmlFor="org-public-profile-description">Public description</label>
                        <textarea
                           id="org-public-profile-description"
                           value={draft.description}
                           onChange={(event) => updateDraft("description", event.target.value)}
                           aria-describedby="org-public-profile-description-help"
                           rows={5}
                           disabled={saving}
                        />
                        <span id="org-public-profile-description-help" className="org-public-profile-help">
                           Describe the organization for its public TruthLens partner profile. Blank is allowed.
                        </span>
                     </div>

                     <div className="org-public-profile-field">
                        <label htmlFor="org-public-profile-website">Website</label>
                        <input
                           id="org-public-profile-website"
                           type="url"
                           value={draft.website}
                           onChange={(event) => updateDraft("website", event.target.value)}
                           aria-describedby={`org-public-profile-website-help${fieldErrors.website ? " org-public-profile-website-error" : ""}`}
                           aria-invalid={fieldErrors.website ? "true" : undefined}
                           maxLength={2000}
                           placeholder="https://example.org"
                           disabled={saving}
                        />
                        <span id="org-public-profile-website-help" className="org-public-profile-help">
                           Optional public organization website. Include http:// or https://.
                        </span>
                        {fieldErrors.website && (
                           <span id="org-public-profile-website-error" className="org-public-profile-field-error" role="alert">
                              {fieldErrors.website}
                           </span>
                        )}
                     </div>

                     <div className="org-public-profile-field">
                        <label htmlFor="org-public-profile-logo-url">Logo URL</label>
                        <input
                           id="org-public-profile-logo-url"
                           type="url"
                           value={draft.logo_url}
                           onChange={(event) => updateDraft("logo_url", event.target.value)}
                           aria-describedby={`org-public-profile-logo-help${fieldErrors.logo_url ? " org-public-profile-logo-error" : ""}`}
                           aria-invalid={fieldErrors.logo_url ? "true" : undefined}
                           maxLength={2000}
                           placeholder="https://example.org/logo.png"
                           disabled={saving}
                        />
                        <span id="org-public-profile-logo-help" className="org-public-profile-help">
                           Saving a logo URL does not make it public. Display also requires separate logo consent and
                           public eligibility.
                        </span>
                        {fieldErrors.logo_url && (
                           <span id="org-public-profile-logo-error" className="org-public-profile-field-error" role="alert">
                              {fieldErrors.logo_url}
                           </span>
                        )}
                     </div>

                     <div className="org-public-profile-field org-public-profile-field-wide">
                        <label htmlFor="org-public-profile-expertise">Expertise areas</label>
                        <textarea
                           id="org-public-profile-expertise"
                           value={draft.expertise_areas}
                           onChange={(event) => updateDraft("expertise_areas", event.target.value)}
                           aria-describedby={`org-public-profile-expertise-help${fieldErrors.expertise_areas ? " org-public-profile-expertise-error" : ""}`}
                           aria-invalid={fieldErrors.expertise_areas ? "true" : undefined}
                           rows={5}
                           placeholder={"Election verification\nMedia literacy\nPublic policy"}
                           disabled={saving}
                        />
                        <span id="org-public-profile-expertise-help" className="org-public-profile-help">
                           One area per line. Up to 20 areas and 100 characters per area; duplicates are removed when
                           saved.
                        </span>
                        {fieldErrors.expertise_areas && (
                           <span
                              id="org-public-profile-expertise-error"
                              className="org-public-profile-field-error"
                              role="alert"
                           >
                              {fieldErrors.expertise_areas}
                           </span>
                        )}
                     </div>
                  </div>

                  <fieldset className="org-public-profile-consent" disabled={saving}>
                     <legend>Public presence consent</legend>

                     <label className="org-public-profile-consent-option">
                        <input
                           type="checkbox"
                           checked={draft.public_profile_enabled}
                           onChange={(event) => updateDraft("public_profile_enabled", event.target.checked)}
                           aria-describedby="org-public-profile-enabled-help"
                        />
                        <span>
                           <strong>Enable public partner profile</strong>
                           <small id="org-public-profile-enabled-help">
                              Consent to show the approved profile publicly when TruthLens eligibility requirements are
                              also satisfied. This does not change verification, partnership, or publication authority.
                           </small>
                        </span>
                     </label>

                     <label className="org-public-profile-consent-option">
                        <input
                           type="checkbox"
                           checked={draft.public_logo_enabled}
                           onChange={(event) => updateDraft("public_logo_enabled", event.target.checked)}
                           aria-describedby="org-public-profile-logo-enabled-help"
                        />
                        <span>
                           <strong>Allow public logo display</strong>
                           <small id="org-public-profile-logo-enabled-help">
                              Separate consent for public branding. It remains independent of public profile enablement
                              and does not authorize institutional fact-check publication or attribution.
                           </small>
                        </span>
                     </label>
                  </fieldset>

                  {dirty && <p className="org-public-profile-unsaved">You have unsaved changes.</p>}

                  {saveError && (
                     <div className="org-public-profile-error org-public-profile-save-error" role="alert">
                        <Icons name="alert-circle" size={17} />
                        <span>{saveError}</span>
                     </div>
                  )}

                  <div className="org-public-profile-actions">
                     <button type="button" onClick={resetChanges} disabled={!dirty || saving}>
                        Reset changes
                     </button>
                     <button type="submit" className="primary" disabled={!dirty || saving}>
                        {saving ? (
                           <>
                              <Icons name="loader" size={14} className="org-admin-spinner" />
                              Saving…
                           </>
                        ) : (
                           "Save public profile"
                        )}
                     </button>
                  </div>
               </form>
            </>
         ) : null}
      </section>
   );
}

export default OrganizationPublicProfilePanel;
