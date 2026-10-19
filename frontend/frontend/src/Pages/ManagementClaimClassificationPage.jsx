import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
   ManagementFeedback,
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
} from "../components/management/ManagementUi";
import Button from "../components/ui/Button";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import {
   formatManagementClaimType,
   formatManagementDate,
   MANAGEMENT_VERIFICATION_DOMAINS,
} from "../utils/management";

const PAGE_SIZE = 20;

function ManagementClaimClassificationPage() {
   const [page, setPage] = useState(1);
   const [selected, setSelected] = useState(null);
   const [domains, setDomains] = useState([]);
   const [jurisdiction, setJurisdiction] = useState("");
   const [rationale, setRationale] = useState("");
   const [successMessage, setSuccessMessage] = useState("");
   const url = useMemo(() => {
      const endpoint = new URL(resolveApiEndpoint("MANAGEMENT_UNCLASSIFIED_INTAKE"));
      endpoint.searchParams.set("page", String(page));
      return endpoint.toString();
   }, [page]);
   const { data, loading, error, retry } = useManagementRequest(url);
   const { mutate, pending, error: mutationError, reset } = useManagementMutation();

   const selectClaim = (item) => {
      reset();
      setSuccessMessage("");
      setSelected(item);
      setDomains([]);
      setJurisdiction("");
      setRationale("");
   };

   const classify = async (event) => {
      event.preventDefault();
      if (!selected || !domains.length || rationale.trim().length < 12) return;
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_CLASSIFY_CLAIM", selected.claim_id),
         {
            method: "PUT",
            body: {
               domains,
               jurisdiction: jurisdiction.trim().toUpperCase(),
               rationale: rationale.trim(),
            },
         },
      );
      if (!result.ok) return;
      setSelected(null);
      setSuccessMessage("Claim classified and recorded in the platform governance audit.");
      retry();
   };

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Claims Needing Classification"
            subtitle="Platform review is required before any Partner Organization can claim these investigations."
         />
         <div className="management-boundary-note">
            <div>
               <strong>Manual classification, not an AI verdict</strong>
               <p>
                  Review the actual claim and context before assigning subject domains and geographic scope.
                  Do not infer an unsupported location, identity, date, or subject. Leave ambiguous claims unclassified.
                  A partner's own public expertise descriptions never grant verification authority.
               </p>
            </div>
         </div>
         {successMessage ? <ManagementFeedback>{successMessage}</ManagementFeedback> : null}

         <ManagementRequestState
            loading={loading}
            error={error}
            empty={Boolean(data && !data.count)}
            emptyMessage="No unclassified investigations are waiting in the current intake."
            onRetry={retry}
         >
            {data ? (
               <section className="management-section">
                  <h2>Unclassified investigation queue</h2>
                  <div className="management-table-wrap management-section__table">
                     <table className="management-table">
                        <thead>
                           <tr>
                              <th>Claim context</th>
                              <th>Type</th>
                              <th>Created</th>
                              <th>Action</th>
                           </tr>
                        </thead>
                        <tbody>
                           {data.results.map((item) => (
                              <tr key={item.assignment_id}>
                                 <td data-label="Claim">
                                    <strong>{item.claim_text || "No text context available — inspect source first"}</strong>
                                    <div><small>Claim ID: {item.claim_id}</small></div>
                                 </td>
                                 <td data-label="Type">{formatManagementClaimType(item.claim_type)}</td>
                                 <td data-label="Created">{formatManagementDate(item.created_at)}</td>
                                 <td data-label="Action">
                                    <Button variant="secondary" density="compact" onClick={() => selectClaim(item)}>
                                       Review classification
                                    </Button>
                                 </td>
                              </tr>
                           ))}
                        </tbody>
                     </table>
                  </div>
                  <ManagementPagination count={data.count} page={page} pageSize={PAGE_SIZE}
                     onPageChange={(next) => { setPage(next); setSelected(null); }} />
               </section>
            ) : null}
         </ManagementRequestState>

         {selected ? (
            <section className="management-section" aria-label="Claim classification review">
               <h2>Classify claim</h2>
               <p>{selected.claim_text || "Claim text is unavailable. Examine its original source before classification."}</p>
               <p>
                  <Link to={`/analysis/${selected.claim_id}`} target="_blank" rel="noopener noreferrer"
                     className="management-inline-link">
                     Inspect claim analysis in a new tab
                  </Link>
               </p>
               <form className="management-trust-editor" onSubmit={classify}>
                  <fieldset className="management-form-field" disabled={pending}>
                     <legend>Subject domains (select all that are material)</legend>
                     <div className="management-scope-options">
                        {MANAGEMENT_VERIFICATION_DOMAINS.map(([code, label]) => (
                           <label key={code}>
                              <input type="checkbox" checked={domains.includes(code)}
                                 onChange={(event) => {
                                    reset();
                                    setDomains((current) => event.target.checked
                                       ? [...current, code] : current.filter((item) => item !== code));
                                 }}
                              />
                              <span>{label}</span>
                           </label>
                        ))}
                     </div>
                  </fieldset>
                  <label className="management-form-field">
                     <span>Claim jurisdiction</span>
                     <Input value={jurisdiction} placeholder="PH, PH-NCR, or GLOBAL"
                        onChange={(event) => { reset(); setJurisdiction(event.target.value); }}
                        required disabled={pending} />
                     <small>GLOBAL only when the proposition genuinely has worldwide scope.</small>
                  </label>
                  <label className="management-form-field">
                     <span>Classification rationale (required)</span>
                     <textarea rows={3} maxLength={2000} minLength={12} required
                        disabled={pending}
                        placeholder="Explain which asserted facts support the selected domains and jurisdiction"
                        value={rationale}
                        onChange={(event) => { reset(); setRationale(event.target.value); }} />
                  </label>
                  {mutationError ? <ManagementFeedback tone="error">{mutationError.message}</ManagementFeedback> : null}
                  <div className="management-inline-actions">
                     <Button type="button" variant="secondary" disabled={pending}
                        onClick={() => { reset(); setSelected(null); }}>Cancel</Button>
                     <Button type="submit" loading={pending} loadingLabel="Classifying…"
                        disabled={pending || !domains.length || !jurisdiction.trim() || rationale.trim().length < 12}>
                        Approve classification
                     </Button>
                  </div>
               </form>
            </section>
         ) : null}
      </div>
   );
}

export default ManagementClaimClassificationPage;
