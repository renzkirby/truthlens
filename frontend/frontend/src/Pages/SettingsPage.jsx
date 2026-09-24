import { useEffect, useRef, useState } from "react";

import Icons from "../components/Icons";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Textarea from "../components/ui/Textarea";
import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";

import "./SettingsPage.css";

const MAX_AVATAR_SIZE = 2 * 1024 * 1024;
const ACCEPTED_AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/gif"]);
const MAX_SETTINGS_ERROR_LENGTH = 200;
const UNSAFE_SETTINGS_ERROR_PATTERNS = [
   /<!doctype|<\/?[a-z][^>]*>/i,
   /traceback|stack trace|django|internal server error|technical 500 response|request failed|failed to fetch/i,
   /\b(?:syntax|type|reference|value|key|operational|programming)error\b|unexpected token|status code \d{3}/i,
   /\bat\s+\S+\s+\([^)]*:\d+:\d+\)/i,
];

const profileFromUser = (user) => ({
   username: user?.username || "",
   bio: user?.bio || "",
});

const firstError = (value) => {
   if (Array.isArray(value)) return value[0] || "";
   return typeof value === "string" ? value : "";
};

const settingsErrorMessage = (error, fallback) => {
   const status = Number(error?.status);

   // Never expose server, network, parser, or unknown runtime failures.
   // Product-safe fallbacks are the authoritative copy for those cases.
   if (!Number.isInteger(status) || status < 400 || status >= 500) {
      return fallback;
   }

   const candidates = [error?.detail, error?.message];

   for (const candidate of candidates) {
      if (typeof candidate !== "string") continue;

      const message = candidate.replace(/\s+/g, " ").trim();
      if (!message || message.length > MAX_SETTINGS_ERROR_LENGTH) continue;
      if (UNSAFE_SETTINGS_ERROR_PATTERNS.some((pattern) => pattern.test(message))) continue;

      return message;
   }

   return fallback;
};

const authMethodLabel = (method) => {
   if (method === "password") return "Password";
   if (method === "google") return "Google";
   return method;
};

function SettingsPage() {
   const { user, authFetch, refreshUser, logout } = useAuth();
   const [activeSection, setActiveSection] = useState("profile");
   const [formData, setFormData] = useState(() => profileFromUser(user));
   const [savedProfile, setSavedProfile] = useState(() => profileFromUser(user));
   const [avatarBase64, setAvatarBase64] = useState("");
   const [previewAvatar, setPreviewAvatar] = useState(user?.avatar_url || null);
   const [avatarFailed, setAvatarFailed] = useState(false);
   const [fieldErrors, setFieldErrors] = useState({});
   const [profileMessage, setProfileMessage] = useState({ text: "", type: "" });
   const [isSaving, setIsSaving] = useState(false);
   const [isSendingVerification, setIsSendingVerification] = useState(false);
   const [isSendingReset, setIsSendingReset] = useState(false);
   const [verificationMessage, setVerificationMessage] = useState({ text: "", type: "" });
   const [passwordMessage, setPasswordMessage] = useState({ text: "", type: "" });
   const fileInputRef = useRef(null);

   useEffect(() => {
      if (!user) return;

      const nextProfile = profileFromUser(user);
      setFormData(nextProfile);
      setSavedProfile(nextProfile);
      setAvatarBase64("");
      setPreviewAvatar(user.avatar_url || null);
      setAvatarFailed(false);
   }, [user]);

   const isDirty =
      formData.username !== savedProfile.username || formData.bio !== savedProfile.bio || Boolean(avatarBase64);

   const clearFieldFeedback = (fieldName) => {
      setFieldErrors((current) => ({ ...current, [fieldName]: "" }));
      setProfileMessage({ text: "", type: "" });
   };

   const handleInputChange = (event) => {
      const { name, value } = event.target;
      setFormData((current) => ({ ...current, [name]: value }));
      clearFieldFeedback(name);
   };

   const handleFileChange = (event) => {
      const file = event.target.files?.[0];
      if (!file) return;

      clearFieldFeedback("avatar_base64");

      if (!ACCEPTED_AVATAR_TYPES.has(file.type)) {
         setFieldErrors((current) => ({
            ...current,
            avatar_base64: "Choose a JPG, PNG, or GIF image.",
         }));
         event.target.value = "";
         return;
      }

      if (file.size > MAX_AVATAR_SIZE) {
         setFieldErrors((current) => ({
            ...current,
            avatar_base64: "Choose an image that is 2 MB or smaller.",
         }));
         event.target.value = "";
         return;
      }

      const reader = new FileReader();
      reader.onload = () => {
         if (typeof reader.result !== "string") {
            setFieldErrors((current) => ({
               ...current,
               avatar_base64: "We could not read that image. Choose another file.",
            }));
            return;
         }

         setAvatarBase64(reader.result);
         setPreviewAvatar(reader.result);
         setAvatarFailed(false);
      };
      reader.onerror = () => {
         setFieldErrors((current) => ({
            ...current,
            avatar_base64: "We could not read that image. Choose another file.",
         }));
      };
      reader.readAsDataURL(file);
   };

   const handleSaveProfile = async (event) => {
      event.preventDefault();
      if (isSaving || !isDirty) return;

      const trimmedUsername = formData.username.trim();
      if (!trimmedUsername) {
         setFieldErrors((current) => ({ ...current, username: "Enter a username." }));
         return;
      }
      if (trimmedUsername.length > 150) {
         setFieldErrors((current) => ({
            ...current,
            username: "Use 150 characters or fewer.",
         }));
         return;
      }

      setIsSaving(true);
      setFieldErrors({});
      setProfileMessage({ text: "", type: "" });

      const payload = {
         username: formData.username,
         bio: formData.bio,
      };
      if (avatarBase64) payload.avatar_base64 = avatarBase64;

      try {
         const savedUser = await authFetch(resolveApiEndpoint("PROFILE_UPDATE"), {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: payload,
         });
         const refreshedUser = await refreshUser?.();
         const authoritativeUser = refreshedUser || savedUser;
         const nextProfile = profileFromUser(authoritativeUser);

         setFormData(nextProfile);
         setSavedProfile(nextProfile);
         setAvatarBase64("");
         setPreviewAvatar(authoritativeUser?.avatar_url || previewAvatar);
         setAvatarFailed(false);
         if (fileInputRef.current) fileInputRef.current.value = "";
         setProfileMessage({ text: "Your profile has been saved.", type: "success" });
      } catch (error) {
         const nextErrors = {
            username: firstError(error?.username),
            bio: firstError(error?.bio),
            avatar_base64: firstError(error?.avatar_base64),
         };
         setFieldErrors(nextErrors);
         const fallbackMessage = Object.values(nextErrors).some(Boolean)
            ? "Review the highlighted fields and try again."
            : "We could not save your profile. Try again.";

         setProfileMessage({
            text: settingsErrorMessage(error, fallbackMessage),
            type: "error",
         });
      } finally {
         setIsSaving(false);
      }
   };

   const handleResendVerification = async () => {
      if (isSendingVerification || user?.is_email_verified) return;

      setIsSendingVerification(true);
      setVerificationMessage({ text: "", type: "" });

      try {
         const data = await authFetch(resolveApiEndpoint("SEND_VERIFICATION"), {
            method: "POST",
         });
         setVerificationMessage({
            text: data?.detail || "Verification email sent. Check your inbox.",
            type: "success",
         });
      } catch (error) {
         setVerificationMessage({
            text:
               error?.status === 429
                  ? "You have requested several verification emails. Try again later."
                  : settingsErrorMessage(error, "We could not send the verification email. Try again."),
            type: "error",
         });
      } finally {
         setIsSendingVerification(false);
      }
   };

   const authMethods = Array.isArray(user?.auth_methods) ? user.auth_methods : [];
   const isGoogleOnlyAccount = authMethods.includes("google") && !authMethods.includes("password");
   const passwordAction = isGoogleOnlyAccount
      ? {
           title: "Add a password",
           description:
              "This account currently signs in with Google. We will email a secure, single-use link that lets you add a TruthLens password.",
           button: "Send password setup link",
           loading: "Sending setup link…",
           success: "Password setup instructions have been sent.",
           rateError: "You have requested several password setup emails. Try again later.",
           error: "We could not send password setup instructions. Try again.",
        }
      : {
           title: "Password security",
           description: "We will email a secure, single-use link to reset your password.",
           button: "Send password reset link",
           loading: "Sending reset link…",
           success: "Password reset instructions have been sent.",
           rateError: "You have requested several reset emails. Try again later.",
           error: "We could not send password reset instructions. Try again.",
        };

   const handlePasswordReset = async () => {
      if (isSendingReset || !user?.email) return;

      setIsSendingReset(true);
      setPasswordMessage({ text: "", type: "" });

      try {
         const data = await authFetch(resolveApiEndpoint("PASSWORD_RESET"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: { email: user.email },
         });
         setPasswordMessage({
            text: isGoogleOnlyAccount ? passwordAction.success : data?.detail || passwordAction.success,
            type: "success",
         });
      } catch (error) {
         setPasswordMessage({
            text: error?.status === 429 ? passwordAction.rateError : settingsErrorMessage(error, passwordAction.error),
            type: "error",
         });
      } finally {
         setIsSendingReset(false);
      }
   };

   const avatarFallback = formData.username.trim().charAt(0).toUpperCase() || "?";

   return (
      <main className="settings-page">
         <div className="settings-page__container">
            <header className="settings-page__header">
               <h1>Settings</h1>
               <p>Manage your public profile and the security details tied to your account.</p>
            </header>

            <div className="settings-page__layout">
               <nav className="settings-nav" aria-label="Settings sections">
                  <button
                     type="button"
                     className={`settings-nav__item ${activeSection === "profile" ? "is-active" : ""}`}
                     onClick={() => setActiveSection("profile")}
                     aria-current={activeSection === "profile" ? "page" : undefined}
                  >
                     <Icons name="user" size={18} aria-hidden="true" />
                     <span>Profile</span>
                  </button>
                  <button
                     type="button"
                     className={`settings-nav__item ${activeSection === "security" ? "is-active" : ""}`}
                     onClick={() => setActiveSection("security")}
                     aria-current={activeSection === "security" ? "page" : undefined}
                  >
                     <Icons name="lock" size={18} aria-hidden="true" />
                     <span>Account &amp; security</span>
                  </button>
               </nav>

               <div className="settings-content">
                  {activeSection === "profile" ? (
                     <section aria-labelledby="profile-settings-title">
                        <div className="settings-section__header">
                           <h2 id="profile-settings-title">Profile</h2>
                           <p>Control how you appear to other people across TruthLens.</p>
                        </div>

                        <form className="settings-form" onSubmit={handleSaveProfile} noValidate>
                           <div className="settings-avatar-field">
                              <div className="settings-avatar" aria-hidden="true">
                                 {previewAvatar && !avatarFailed ? (
                                    <img src={previewAvatar} alt="" onError={() => setAvatarFailed(true)} />
                                 ) : (
                                    <span>{avatarFallback}</span>
                                 )}
                              </div>
                              <div className="settings-avatar-field__body">
                                 <label className="settings-field__label" htmlFor="settings-avatar">
                                    Profile picture
                                 </label>
                                 <input
                                    id="settings-avatar"
                                    ref={fileInputRef}
                                    className="settings-avatar-input"
                                    type="file"
                                    accept="image/jpeg,image/png,image/gif"
                                    onChange={handleFileChange}
                                    aria-describedby={`avatar-hint${fieldErrors.avatar_base64 ? " avatar-error" : ""}`}
                                    aria-invalid={fieldErrors.avatar_base64 ? "true" : undefined}
                                 />
                                 <Button
                                    type="button"
                                    variant="secondary"
                                    density="standard"
                                    leadingIcon={<Icons name="upload" size={17} />}
                                    onClick={() => fileInputRef.current?.click()}
                                    disabled={isSaving}
                                 >
                                    Choose profile picture
                                 </Button>
                                 <p id="avatar-hint" className="settings-field__hint">
                                    JPG, PNG, or GIF. Maximum 2 MB.
                                 </p>
                                 {fieldErrors.avatar_base64 ? (
                                    <p id="avatar-error" className="settings-field__error">
                                       {fieldErrors.avatar_base64}
                                    </p>
                                 ) : null}
                              </div>
                           </div>

                           <div className="settings-field">
                              <label className="settings-field__label" htmlFor="settings-username">
                                 Username
                              </label>
                              <Input
                                 id="settings-username"
                                 name="username"
                                 value={formData.username}
                                 onChange={handleInputChange}
                                 autoComplete="username"
                                 maxLength={150}
                                 density="comfortable"
                                 invalid={Boolean(fieldErrors.username)}
                                 aria-describedby={`username-hint${fieldErrors.username ? " username-error" : ""}`}
                                 disabled={isSaving}
                                 required
                              />
                              <p id="username-hint" className="settings-field__hint">
                                 This is the name shown on your profile and contributions.
                              </p>
                              {fieldErrors.username ? (
                                 <p id="username-error" className="settings-field__error">
                                    {fieldErrors.username}
                                 </p>
                              ) : null}
                           </div>

                           <div className="settings-field">
                              <label className="settings-field__label" htmlFor="settings-bio">
                                 Bio
                              </label>
                              <Textarea
                                 id="settings-bio"
                                 name="bio"
                                 value={formData.bio}
                                 onChange={handleInputChange}
                                 density="comfortable"
                                 rows={5}
                                 invalid={Boolean(fieldErrors.bio)}
                                 aria-describedby={`bio-hint${fieldErrors.bio ? " bio-error" : ""}`}
                                 disabled={isSaving}
                              />
                              <p id="bio-hint" className="settings-field__hint">
                                 Share a short introduction for people viewing your public profile.
                              </p>
                              {fieldErrors.bio ? (
                                 <p id="bio-error" className="settings-field__error">
                                    {fieldErrors.bio}
                                 </p>
                              ) : null}
                           </div>

                           <div className="settings-form__footer">
                              <Button
                                 type="submit"
                                 variant="primary"
                                 density="comfortable"
                                 loading={isSaving}
                                 loadingLabel="Saving profile…"
                                 disabled={!isDirty}
                              >
                                 Save profile
                              </Button>
                              <p className="settings-form__save-hint">
                                 {isDirty ? "You have unsaved changes." : "Your profile is up to date."}
                              </p>
                           </div>

                           {profileMessage.text ? (
                              <div
                                 className={`settings-feedback settings-feedback--${profileMessage.type}`}
                                 role={profileMessage.type === "error" ? "alert" : "status"}
                                 aria-live={profileMessage.type === "error" ? "assertive" : "polite"}
                              >
                                 <Icons
                                    name={profileMessage.type === "error" ? "alert-circle" : "check-circle"}
                                    size={18}
                                    aria-hidden="true"
                                 />
                                 <span>{profileMessage.text}</span>
                              </div>
                           ) : null}
                        </form>
                     </section>
                  ) : (
                     <section aria-labelledby="security-settings-title">
                        <div className="settings-section__header">
                           <h2 id="security-settings-title">Account &amp; security</h2>
                           <p>Review your sign-in details and recover access when you need to.</p>
                        </div>

                        <div className="settings-account-list">
                           <section className="settings-account-row" aria-labelledby="account-email-title">
                              <div className="settings-account-row__icon" aria-hidden="true">
                                 <Icons name="mail" size={19} />
                              </div>
                              <div className="settings-account-row__content">
                                 <div className="settings-account-row__heading">
                                    <h3 id="account-email-title">Email address</h3>
                                    <span
                                       className={`settings-status settings-status--${
                                          user?.is_email_verified ? "verified" : "pending"
                                       }`}
                                    >
                                       <Icons
                                          name={user?.is_email_verified ? "check-circle" : "alert-circle"}
                                          size={14}
                                          aria-hidden="true"
                                       />
                                       {user?.is_email_verified ? "Verified" : "Not verified"}
                                    </span>
                                 </div>
                                 <p className="settings-account-row__value">{user?.email || "No email on file"}</p>
                                 <p className="settings-account-row__description">
                                    This email is tied to your TruthLens account and is used for verification and
                                    account recovery.
                                 </p>
                                 {!user?.is_email_verified ? (
                                    <div className="settings-account-row__actions">
                                       <Button
                                          type="button"
                                          variant="secondary"
                                          density="standard"
                                          loading={isSendingVerification}
                                          loadingLabel="Sending verification…"
                                          onClick={handleResendVerification}
                                          disabled={!user?.email}
                                       >
                                          Resend verification email
                                       </Button>
                                    </div>
                                 ) : null}
                                 {verificationMessage.text ? (
                                    <p
                                       className={`settings-inline-message settings-inline-message--${verificationMessage.type}`}
                                       role={verificationMessage.type === "error" ? "alert" : "status"}
                                    >
                                       {verificationMessage.text}
                                    </p>
                                 ) : null}
                              </div>
                           </section>

                           <section className="settings-account-row" aria-labelledby="sign-in-methods-title">
                              <div className="settings-account-row__icon" aria-hidden="true">
                                 <Icons name="shield-check" size={19} />
                              </div>
                              <div className="settings-account-row__content">
                                 <h3 id="sign-in-methods-title">Sign-in methods</h3>
                                 {authMethods.length ? (
                                    <ul className="settings-auth-methods">
                                       {authMethods.map((method) => (
                                          <li key={method}>
                                             <Icons
                                                name={method === "password" ? "lock" : "user-check"}
                                                size={16}
                                                aria-hidden="true"
                                             />
                                             <span>{authMethodLabel(method)}</span>
                                          </li>
                                       ))}
                                    </ul>
                                 ) : (
                                    <p className="settings-account-row__description">
                                       Sign-in method information is unavailable.
                                    </p>
                                 )}
                              </div>
                           </section>

                           <section className="settings-account-row" aria-labelledby="password-title">
                              <div className="settings-account-row__icon" aria-hidden="true">
                                 <Icons name="lock" size={19} />
                              </div>
                              <div className="settings-account-row__content">
                                 <h3 id="password-title">{passwordAction.title}</h3>
                                 <p className="settings-account-row__description">{passwordAction.description}</p>
                                 <div className="settings-account-row__actions">
                                    <Button
                                       type="button"
                                       variant="secondary"
                                       density="standard"
                                       loading={isSendingReset}
                                       loadingLabel={passwordAction.loading}
                                       onClick={handlePasswordReset}
                                       disabled={!user?.email}
                                    >
                                       {passwordAction.button}
                                    </Button>
                                 </div>
                                 {passwordMessage.text ? (
                                    <p
                                       className={`settings-inline-message settings-inline-message--${passwordMessage.type}`}
                                       role={passwordMessage.type === "error" ? "alert" : "status"}
                                    >
                                       {passwordMessage.text}
                                    </p>
                                 ) : null}
                              </div>
                           </section>

                           <section className="settings-account-row" aria-labelledby="session-title">
                              <div className="settings-account-row__icon" aria-hidden="true">
                                 <Icons name="logout" size={19} />
                              </div>
                              <div className="settings-account-row__content">
                                 <h3 id="session-title">Current session</h3>
                                 <p className="settings-account-row__description">
                                    You&apos;re signed in on this browser. Log out when you&apos;re finished, especially
                                    on a shared device.
                                 </p>
                                 <div className="settings-account-row__actions">
                                    <Button
                                       type="button"
                                       variant="secondary"
                                       density="standard"
                                       leadingIcon={<Icons name="logout" size={17} />}
                                       onClick={logout}
                                    >
                                       Log out of TruthLens
                                    </Button>
                                 </div>
                              </div>
                           </section>
                        </div>
                     </section>
                  )}
               </div>
            </div>
         </div>
      </main>
   );
}

export default SettingsPage;
