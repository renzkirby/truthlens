import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, Building2, CheckCircle2, ShieldCheck } from "lucide-react";

import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import Textarea from "../components/ui/Textarea";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { resolveApiEndpoint } from "../utils/api";
import { MANAGEMENT_ORGANIZATION_TYPES } from "../utils/management";

import "./PartnershipApplicationPage.css";

const INITIAL_FORM = {
   organization_name: "",
   organization_type: "",
   website: "",
   official_contact_email: "",
   applicant_full_name: "",
   applicant_position: "",
   applicant_email: "",
   organization_description: "",
   partnership_reason: "",
   supporting_links: "",
   authorized_to_represent: false,
   agrees_to_partner_responsibilities: false,
};

function fieldMessage(error, key) {
   const value = error?.[key];
   if (Array.isArray(value)) return value[0] || "";
   return typeof value === "string" ? value : "";
}

const PARTNERSHIP_FIELD_ORDER = [
   "organization_name",
   "organization_type",
   "website",
   "official_contact_email",
   "organization_description",
   "applicant_full_name",
   "applicant_position",
   "applicant_email",
   "partnership_reason",
   "supporting_links",
   "authorized_to_represent",
   "agrees_to_partner_responsibilities",
];

function firstFieldError(errors) {
   return PARTNERSHIP_FIELD_ORDER.find((field) => fieldMessage(errors, field));
}

function isValidEmail(value) {
   return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || "").trim());
}

function isValidPublicUrl(value) {
   try {
      const parsed = new URL(String(value || "").trim());
      return parsed.protocol === "http:" || parsed.protocol === "https:";
   } catch {
      return false;
   }
}

export default function PartnershipApplicationPage() {
   useDocumentTitle("Become a TruthLens Partner");
   const [form, setForm] = useState(INITIAL_FORM);
   const [pending, setPending] = useState(false);
   const [error, setError] = useState(null);
   const [submitted, setSubmitted] = useState(false);
   const formRef = useRef(null);

   const supportingLinkCount = useMemo(
      () => form.supporting_links.split("\n").map((value) => value.trim()).filter(Boolean).length,
      [form.supporting_links],
   );

   const update = (field, value) => {
      setForm((current) => ({ ...current, [field]: value }));
      setError(null);
   };

   const scrollToField = (field) => {
      if (!field) return;

      window.requestAnimationFrame(() => {
         const container = formRef.current?.querySelector(
            `[data-partnership-field="${field}"]`,
         );
         if (!container) return;

         container.scrollIntoView({
            behavior: "smooth",
            block: "center",
         });

         const control = container.querySelector("input, select, textarea");
         window.setTimeout(() => {
            control?.focus({ preventScroll: true });
         }, 300);
      });
   };

   const validateBeforeSubmit = () => {
      const nextError = {};
      const requiredTextFields = [
         ["organization_name", "Organization name is required."],
         ["organization_type", "Select an organization type."],
         ["website", "An official website or public social media page is required."],
         ["official_contact_email", "Official contact email is required."],
         ["applicant_full_name", "Applicant full name is required."],
         ["applicant_position", "Applicant position or role is required."],
         ["applicant_email", "Representative email is required."],
      ];

      requiredTextFields.forEach(([field, message]) => {
         if (!String(form[field] || "").trim()) {
            nextError[field] = [message];
         }
      });

      if (form.website.trim() && !isValidPublicUrl(form.website)) {
         nextError.website = ["Enter a valid http:// or https:// web address."];
      }

      if (
         form.official_contact_email.trim()
         && !isValidEmail(form.official_contact_email)
      ) {
         nextError.official_contact_email = ["Enter a valid official contact email address."];
      }

      if (form.applicant_email.trim() && !isValidEmail(form.applicant_email)) {
         nextError.applicant_email = ["Enter a valid representative email address."];
      }

      if (form.organization_description.trim().length < 30) {
         nextError.organization_description = [
            "Provide at least 30 characters describing the organization.",
         ];
      }

      if (form.partnership_reason.trim().length < 30) {
         nextError.partnership_reason = [
            "Provide at least 30 characters explaining the partnership request.",
         ];
      }

      if (supportingLinkCount > 5) {
         nextError.supporting_links = ["Provide no more than 5 supporting links."];
      }

      if (!form.authorized_to_represent) {
         nextError.authorized_to_represent = [
            "Confirm that you are authorized to represent this organization.",
         ];
      }

      if (!form.agrees_to_partner_responsibilities) {
         nextError.agrees_to_partner_responsibilities = [
            "Confirm that you reviewed and acknowledge the Partner Organization Guidelines.",
         ];
      }

      return nextError;
   };

   const submit = async (event) => {
      event.preventDefault();
      if (pending) return;

      const localErrors = validateBeforeSubmit();
      const firstLocalError = firstFieldError(localErrors);

      if (firstLocalError) {
         setError(localErrors);
         scrollToField(firstLocalError);
         return;
      }

      setPending(true);
      setError(null);

      try {
         const response = await fetch(resolveApiEndpoint("PARTNERSHIP_APPLICATION"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               ...form,
               supporting_links: form.supporting_links
                  .split("\n")
                  .map((value) => value.trim())
                  .filter(Boolean)
                  .slice(0, 5),
            }),
         });
         const payload = await response.json().catch(() => ({}));
         if (!response.ok) {
            setError(payload);
            scrollToField(firstFieldError(payload));
            return;
         }
         setSubmitted(true);
      } catch {
         setError({
            detail: "We couldn't submit the partnership application. Check your connection and try again.",
         });
      } finally {
         setPending(false);
      }
   };

   if (submitted) {
      return (
         <main className="partner-application-page">
            <section className="partner-application-success">
               <div className="partner-application-success__icon">
                  <CheckCircle2 size={30} aria-hidden="true" />
               </div>
               <span className="partner-application-eyebrow">Application submitted</span>
               <h1>Thank you for applying to partner with TruthLens.</h1>
               <p>
                  Your organization is now pending platform review. Submission does not grant verification authority.
                  If approved, TruthLens will send the approved representative a secure Organization Admin invitation.
               </p>
               <div className="partner-application-success__next">
                  <strong>What happens next</strong>
                  <ol>
                     <li>TruthLens reviews the organization and submitted information.</li>
                     <li>If approved, an Organization Admin onboarding invitation is issued.</li>
                     <li>The approved representative verifies their account and accepts the invitation.</li>
                     <li>TruthLens then activates the verified Partner Organization.</li>
                  </ol>
               </div>
               <Link className="tl-button tl-button--secondary tl-button--standard" to="/landing">
                  Return to TruthLens
               </Link>
            </section>
         </main>
      );
   }

   return (
      <main className="partner-application-page">
         <div className="partner-application-layout">
            <aside className="partner-application-intro">
               <Link to="/landing" className="partner-application-back">
                  <ArrowLeft size={16} aria-hidden="true" />
                  Back to TruthLens
               </Link>
               <span className="partner-application-eyebrow">TruthLens Partner Network</span>
               <h1>Want to become a TruthLens Partner?</h1>
               <p>
                  Organizations involved in fact-checking, journalism, research, education, public information, or
                  related verification work can apply to join the TruthLens professional verification network.
               </p>

               <div className="partner-application-principles">
                  <article>
                     <Building2 size={19} aria-hidden="true" />
                     <div>
                        <strong>Institutional review</strong>
                        <span>TruthLens reviews the organization before any professional authority is granted.</span>
                     </div>
                  </article>
                  <article>
                     <ShieldCheck size={19} aria-hidden="true" />
                     <div>
                        <strong>Secure representative onboarding</strong>
                        <span>An approved representative must accept a verified-email Admin invitation.</span>
                     </div>
                  </article>
               </div>
            </aside>

            <form ref={formRef} className="partner-application-form" onSubmit={submit} noValidate>
               <header>
                  <span className="partner-application-eyebrow">Partnership application</span>
                  <h2>Tell us about your organization</h2>
                  <p>Fields marked required are used to evaluate institutional legitimacy and partnership suitability.</p>
               </header>

               <section>
                  <h3>Organization identity</h3>
                  <div className="partner-application-grid">
                     <label data-partnership-field="organization_name">
                        <span>Organization name *</span>
                        <Input
                           value={form.organization_name}
                           onChange={(event) => update("organization_name", event.target.value)}
                           invalid={Boolean(fieldMessage(error, "organization_name"))}
                           required
                        />
                        {fieldMessage(error, "organization_name") ? <small className="partner-application-error">{fieldMessage(error, "organization_name")}</small> : null}
                     </label>

                     <label data-partnership-field="organization_type">
                        <span>Organization type *</span>
                        <Select
                           value={form.organization_type}
                           onChange={(event) => update("organization_type", event.target.value)}
                           invalid={Boolean(fieldMessage(error, "organization_type"))}
                           required
                        >
                           <option value="">Select organization type</option>
                           {MANAGEMENT_ORGANIZATION_TYPES.map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                           ))}
                        </Select>
                        {fieldMessage(error, "organization_type") ? <small className="partner-application-error">{fieldMessage(error, "organization_type")}</small> : null}
                     </label>

                     <label data-partnership-field="website">
                        <span>Official website or public social media page *</span>
                        <Input
                           type="url"
                           value={form.website}
                           onChange={(event) => update("website", event.target.value)}
                           placeholder="https://example.org"
                           invalid={Boolean(fieldMessage(error, "website"))}
                           required
                        />
                        {fieldMessage(error, "website") ? (
                           <small className="partner-application-error">{fieldMessage(error, "website")}</small>
                        ) : (
                           <small>
                              Provide the organization’s official website. If it does not maintain one, an official
                              public social media page is acceptable.
                           </small>
                        )}
                     </label>

                     <label data-partnership-field="official_contact_email">
                        <span>Official contact email *</span>
                        <Input
                           type="email"
                           value={form.official_contact_email}
                           onChange={(event) => update("official_contact_email", event.target.value)}
                           placeholder="contact@example.org"
                           invalid={Boolean(fieldMessage(error, "official_contact_email"))}
                           required
                        />
                        {fieldMessage(error, "official_contact_email") ? <small className="partner-application-error">{fieldMessage(error, "official_contact_email")}</small> : null}
                     </label>
                  </div>

                  <label data-partnership-field="organization_description">
                     <span>Organization description *</span>
                     <Textarea
                        rows={4}
                        value={form.organization_description}
                        onChange={(event) => update("organization_description", event.target.value)}
                        placeholder="Describe your organization, its work, and the communities or audiences it serves."
                        invalid={Boolean(fieldMessage(error, "organization_description"))}
                        required
                     />
                     <small className={fieldMessage(error, "organization_description") ? "partner-application-error" : ""}>
                        {fieldMessage(error, "organization_description") || "Minimum 30 characters."}
                     </small>
                  </label>
               </section>

               <section>
                  <h3>Authorized representative</h3>
                  <div className="partner-application-grid">
                     <label data-partnership-field="applicant_full_name">
                        <span>Full name *</span>
                        <Input
                           value={form.applicant_full_name}
                           onChange={(event) => update("applicant_full_name", event.target.value)}
                           invalid={Boolean(fieldMessage(error, "applicant_full_name"))}
                           required
                        />
                        {fieldMessage(error, "applicant_full_name") ? <small className="partner-application-error">{fieldMessage(error, "applicant_full_name")}</small> : null}
                     </label>
                     <label data-partnership-field="applicant_position">
                        <span>Position or role *</span>
                        <Input
                           value={form.applicant_position}
                           onChange={(event) => update("applicant_position", event.target.value)}
                           placeholder="e.g. Executive Director"
                           invalid={Boolean(fieldMessage(error, "applicant_position"))}
                           required
                        />
                        {fieldMessage(error, "applicant_position") ? <small className="partner-application-error">{fieldMessage(error, "applicant_position")}</small> : null}
                     </label>
                     <label className="partner-application-grid__full" data-partnership-field="applicant_email">
                        <span>Representative email *</span>
                        <Input
                           type="email"
                           value={form.applicant_email}
                           onChange={(event) => update("applicant_email", event.target.value)}
                           placeholder="you@example.org"
                           invalid={Boolean(fieldMessage(error, "applicant_email"))}
                           required
                        />
                        {fieldMessage(error, "applicant_email") ? (
                           <small className="partner-application-error">{fieldMessage(error, "applicant_email")}</small>
                        ) : (
                           <small>If approved, TruthLens may use this address for Organization Admin onboarding.</small>
                        )}
                     </label>
                  </div>
               </section>

               <section>
                  <h3>Partnership request</h3>
                  <label data-partnership-field="partnership_reason">
                     <span>Why does your organization want to partner with TruthLens? *</span>
                     <Textarea
                        rows={5}
                        value={form.partnership_reason}
                        onChange={(event) => update("partnership_reason", event.target.value)}
                        placeholder="Explain how your organization would contribute to professional verification on TruthLens."
                        invalid={Boolean(fieldMessage(error, "partnership_reason"))}
                        required
                     />
                     <small className={fieldMessage(error, "partnership_reason") ? "partner-application-error" : ""}>
                        {fieldMessage(error, "partnership_reason") || "Minimum 30 characters."}
                     </small>
                  </label>

                  <label data-partnership-field="supporting_links">
                     <span>Supporting links</span>
                     <Textarea
                        rows={3}
                        value={form.supporting_links}
                        onChange={(event) => update("supporting_links", event.target.value)}
                        placeholder={"https://example.org/about\nhttps://example.org/editorial-policy"}
                        invalid={Boolean(fieldMessage(error, "supporting_links")) || supportingLinkCount > 5}
                     />
                     <small>
                        Optional links that can help TruthLens review your organization, such as an About page,
                        editorial policy, registration or accreditation record, institutional directory, or other
                        public documentation. One URL per line, up to 5 links.
                     </small>
                  </label>
               </section>

               <section className="partner-application-attestations">
                  <h3>Confirmations</h3>
                  <p className="partner-application-guidelines-note">
                     Review the{" "}
                     <Link to="/partner-guidelines" target="_blank" rel="noreferrer">
                        Partner Organization Guidelines
                     </Link>{" "}
                     before submitting this application.
                  </p>
                  <label data-partnership-field="authorized_to_represent">
                     <input
                        type="checkbox"
                        checked={form.authorized_to_represent}
                        onChange={(event) => update("authorized_to_represent", event.target.checked)}
                     />
                     <span>I confirm that I am authorized to submit this partnership application on behalf of the organization.</span>
                  </label>
                  <label data-partnership-field="agrees_to_partner_responsibilities">
                     <input
                        type="checkbox"
                        checked={form.agrees_to_partner_responsibilities}
                        onChange={(event) => update("agrees_to_partner_responsibilities", event.target.checked)}
                     />
                     <span>
                        I have reviewed the Partner Organization Guidelines and acknowledge that approval and continued
                        participation are subject to TruthLens Partner responsibilities and governance requirements.
                     </span>
                  </label>
                  {fieldMessage(error, "authorized_to_represent") ? <small className="partner-application-error">{fieldMessage(error, "authorized_to_represent")}</small> : null}
                  {fieldMessage(error, "agrees_to_partner_responsibilities") ? <small className="partner-application-error">{fieldMessage(error, "agrees_to_partner_responsibilities")}</small> : null}
               </section>

               {error?.detail ? <div className="partner-application-feedback" role="alert">{error.detail}</div> : null}

               <div className="partner-application-actions">
                  <p>
                     Submission creates a private pending organization record for platform review. It does not make the
                     organization a verified or active TruthLens Partner.
                  </p>
                  <Button
                     type="submit"
                     loading={pending}
                     loadingLabel="Submitting application…"
                     trailingIcon={<ArrowRight size={16} />}
                  >
                     Submit partnership application
                  </Button>
               </div>
            </form>
         </div>
      </main>
   );
}
