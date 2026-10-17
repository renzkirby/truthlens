import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
   ManagementFeedback,
   ManagementPageHeader,
} from "../components/management/ManagementUi";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { resolveApiEndpoint } from "../utils/api";
import {
   MANAGEMENT_ORGANIZATION_TYPES,
   MANAGEMENT_PARTNER_STATUSES,
   MANAGEMENT_VERIFICATION_STATUSES,
} from "../utils/management";

const INITIAL_FORM = {
   name: "",
   slug: "",
   organization_type: "",
   verification_status: "UNVERIFIED",
   partner_status: "NONE",
};

function FieldError({ id, children }) {
   if (!children) return null;
   return <span id={id} className="management-field-error">{children}</span>;
}

function ManagementOrganizationCreatePage() {
   const navigate = useNavigate();
   const [form, setForm] = useState(INITIAL_FORM);
   const { mutate, pending, error, reset } = useManagementMutation();

   const updateField = (field, value) => {
      setForm((current) => ({ ...current, [field]: value }));
      reset();
   };

   const submit = async (event) => {
      event.preventDefault();
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_ORGANIZATIONS"),
         { method: "POST", body: form },
      );
      if (result.ok) navigate(`/management/organizations/${result.data.id}`);
   };

   return (
      <div className="management-page management-page--form">
         <ManagementPageHeader
            title="Add Partner Organization"
            subtitle="Create the institutional identity and initial platform trust record. The organization will manage its own public profile after a Primary Admin is invited separately."
            backTo="/management/organizations"
            backLabel="Partner Organizations"
         />

         <form className="management-create-form" onSubmit={submit} noValidate>
            <section className="management-form-section" aria-labelledby="identity-section-title">
               <div className="management-form-section__heading">
                  <h2 id="identity-section-title">Institutional Identity</h2>
                  <p>Use the organization’s formal name and a stable URL-friendly slug.</p>
               </div>
               <div className="management-form-grid">
                  <label className="management-form-field management-form-field--wide">
                     <span>Organization name</span>
                     <Input
                        value={form.name}
                        onChange={(event) => updateField("name", event.target.value)}
                        invalid={Boolean(error?.fields.name)}
                        aria-describedby={error?.fields.name ? "organization-name-error" : undefined}
                        autoComplete="organization"
                        required
                        disabled={pending}
                     />
                     <FieldError id="organization-name-error">{error?.fields.name}</FieldError>
                  </label>
                  <label className="management-form-field">
                     <span>Slug</span>
                     <Input
                        value={form.slug}
                        onChange={(event) => updateField("slug", event.target.value)}
                        invalid={Boolean(error?.fields.slug)}
                        aria-describedby={error?.fields.slug ? "organization-slug-error" : "organization-slug-help"}
                        placeholder="example-organization"
                        required
                        disabled={pending}
                     />
                     <small id="organization-slug-help">Lowercase letters, numbers, hyphens, and underscores.</small>
                     <FieldError id="organization-slug-error">{error?.fields.slug}</FieldError>
                  </label>
                  <label className="management-form-field">
                     <span>Organization type</span>
                     <Select
                        value={form.organization_type}
                        onChange={(event) => updateField("organization_type", event.target.value)}
                        invalid={Boolean(error?.fields.organization_type)}
                        aria-describedby={error?.fields.organization_type ? "organization-type-error" : undefined}
                        required
                        disabled={pending}
                     >
                        <option value="">Select an organization type</option>
                        {MANAGEMENT_ORGANIZATION_TYPES.map(([value, label]) => (
                           <option key={value} value={value}>{label}</option>
                        ))}
                     </Select>
                     <FieldError id="organization-type-error">{error?.fields.organization_type}</FieldError>
                  </label>
               </div>
            </section>

            <section className="management-form-section" aria-labelledby="trust-section-title">
               <div className="management-form-section__heading">
                  <h2 id="trust-section-title">Initial Platform Trust</h2>
                  <p>These platform-governed values are independent. Creating the organization does not invite or assign a Primary Admin.</p>
               </div>
               <div className="management-form-grid">
                  <label className="management-form-field">
                     <span>Verification status</span>
                     <Select
                        value={form.verification_status}
                        onChange={(event) => updateField("verification_status", event.target.value)}
                        invalid={Boolean(error?.fields.verification_status)}
                        aria-describedby={error?.fields.verification_status ? "verification-status-error" : undefined}
                        disabled={pending}
                     >
                        {MANAGEMENT_VERIFICATION_STATUSES.map(([value, label]) => (
                           <option key={value} value={value}>{label}</option>
                        ))}
                     </Select>
                     <FieldError id="verification-status-error">{error?.fields.verification_status}</FieldError>
                  </label>
                  <label className="management-form-field">
                     <span>Partner status</span>
                     <Select
                        value={form.partner_status}
                        onChange={(event) => updateField("partner_status", event.target.value)}
                        invalid={Boolean(error?.fields.partner_status)}
                        aria-describedby={error?.fields.partner_status ? "partner-status-error" : undefined}
                        disabled={pending}
                     >
                        {MANAGEMENT_PARTNER_STATUSES.map(([value, label]) => (
                           <option key={value} value={value}>{label}</option>
                        ))}
                     </Select>
                     <FieldError id="partner-status-error">{error?.fields.partner_status}</FieldError>
                  </label>
               </div>
            </section>

            {error ? <ManagementFeedback tone="error">{error.message}</ManagementFeedback> : null}

            <div className="management-form-actions">
               <Button variant="secondary" disabled={pending} onClick={() => navigate("/management/organizations")}>
                  Cancel
               </Button>
               <Button type="submit" loading={pending} loadingLabel="Adding organization…">
                  Add organization
               </Button>
            </div>
         </form>
      </div>
   );
}

export default ManagementOrganizationCreatePage;

