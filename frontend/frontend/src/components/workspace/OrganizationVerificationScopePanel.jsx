import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import Button from "../ui/Button.jsx";
import Icons from "../Icons.jsx";
import { resolveApiEndpoint } from "../../utils/api";
import {
   MANAGEMENT_VERIFICATION_DOMAINS,
   formatVerificationDomain,
} from "../../utils/management";
import "./OrganizationVerificationScopePanel.css";

function SpecializationsEditor({ scope, onClose, onSaved }) {
   const dialogRef = useRef(null);
   const { authFetch } = useAuth();
   const [domains, setDomains] = useState(scope.specializations || []);
   const [rationale, setRationale] = useState("");
   const [saving, setSaving] = useState(false);
   const [error, setError] = useState("");

   useEffect(() => {
      const dialog = dialogRef.current;
      dialog?.showModal();
      return () => {
         if (dialog?.open) dialog.close();
      };
   }, []);

   const submit = async (event) => {
      event.preventDefault();
      if (saving) return;
      setError("");
      setSaving(true);
      try {
         await authFetch(resolveApiEndpoint("ORGANIZATION_VERIFICATION_SCOPE", scope.organization_id), {
            method: "PATCH",
            body: { domains, rationale: rationale.trim() },
         });
         onSaved();
      } catch (err) {
         setError(err?.detail || err?.message || "Could not save specializations.");
      } finally {
         setSaving(false);
      }
   };

   return (
      <dialog ref={dialogRef} className="org-scope-dialog"
         aria-labelledby="org-scope-dialog-title"
         aria-describedby="org-scope-dialog-description"
         onCancel={(event) => {
            event.preventDefault();
            if (!saving) onClose();
         }}>
         <div className="org-scope-dialog__heading">
            <div>
               <h3 id="org-scope-dialog-title">Manage verification specializations</h3>
               <p id="org-scope-dialog-description">
                  Select the subjects your organization is prepared to investigate. These
                  selections affect new-assignment matching only when TruthLens enables
                  subject-based intake. Existing assigned work is preserved.
               </p>
            </div>
            <button type="button" onClick={onClose} disabled={saving} aria-label="Close specialization editor">
               <Icons name="x" size={20} />
            </button>
         </div>
         <form onSubmit={submit} className="org-scope-dialog__form">
            <fieldset disabled={saving}>
               <legend>Investigation subjects</legend>
               <p>Select the specializations your institution can responsibly investigate.</p>
               <div className="org-scope-domain-grid">
                  {MANAGEMENT_VERIFICATION_DOMAINS.map(([code, label]) => (
                     <label key={code} className={`org-scope-domain ${domains.includes(code) ? "selected" : ""}`}>
                        <input type="checkbox"
                           checked={domains.includes(code)}
                           onChange={(event) => setDomains((current) => event.target.checked
                              ? [...current, code] : current.filter((item) => item !== code))}
                        />
                        <span>{label}</span>
                     </label>
                  ))}
               </div>
            </fieldset>
            <label className="org-scope-input-label">
               Reason for change
               <textarea rows={3} minLength={12} maxLength={2000}
                  required disabled={saving} value={rationale}
                  placeholder="Explain the organization's subject expertise or why scope is changing."
                  onChange={(event) => setRationale(event.target.value)}
               />
               <small>This decision will be recorded in the organization accountability history.</small>
            </label>
            {error ? <div role="alert" className="org-scope-error">{error}</div> : null}
            <div className="org-scope-dialog__actions">
               <Button type="button" variant="secondary" disabled={saving} onClick={onClose}>Cancel</Button>
               <Button type="submit" loading={saving} loadingLabel="Saving…"
                  disabled={saving || rationale.trim().length < 12}>
                  Save specializations
               </Button>
            </div>
         </form>
      </dialog>
   );
}

export default function OrganizationVerificationScopePanel({ organizationId }) {
   const { authFetch } = useAuth();
   const [requestState, setRequestState] = useState({
      key: null, scope: null, error: "",
   });
   const [version, setVersion] = useState(0);
   const [editing, setEditing] = useState(false);
   const requestKey = `${organizationId}:${version}`;
   const loading = requestState.key !== requestKey;
   const scope = loading ? null : requestState.scope;
   const error = loading ? "" : requestState.error;

   useEffect(() => {
      let active = true;
      const currentKey = `${organizationId}:${version}`;
      authFetch(resolveApiEndpoint("ORGANIZATION_VERIFICATION_SCOPE", organizationId))
         .then((payload) => {
            if (active) setRequestState({ key: currentKey, scope: payload, error: "" });
         })
         .catch((err) => {
            if (active) setRequestState({
               key: currentKey, scope: null,
               error: err?.message || "Unable to load verification specializations.",
            });
         });
      return () => { active = false; };
   }, [authFetch, organizationId, version]);

   return (
      <section className="org-scope-panel">
         <div className="org-scope-panel__header">
            <div>
               <h3>Verification specializations</h3>
               <p>The Organization Admin sets your organization's investigation subjects.
                  Partner status is managed separately by the platform.</p>
            </div>
         </div>
         {loading ? <p role="status">Loading verification specializations…</p> : null}
         {error ? <div role="alert" className="org-scope-error">{error}</div> : null}
         {scope ? (
            <>
               <dl className="org-scope-summary">
                  <div>
                     <dt>Selected investigation subjects</dt>
                     <dd>{scope.specializations.length
                        ? scope.specializations.map(formatVerificationDomain).join(", ")
                        : "No specializations selected"}</dd>
                  </div>
                  <div>
                     <dt>Management permission</dt>
                     <dd>{scope.can_manage
                        ? "You can manage verification specializations."
                        : "Only your organization's Organization Admin can edit specializations."}</dd>
                  </div>
               </dl>
               {scope.can_manage ? (
                  <div className="org-scope-panel__actions">
                     <Button type="button" onClick={() => setEditing(true)}>
                        Manage verification specializations
                     </Button>
                  </div>
               ) : null}
            </>
         ) : null}
         {scope && editing ? (
            <SpecializationsEditor scope={scope}
               onClose={() => setEditing(false)}
               onSaved={() => {
                  setEditing(false);
                  setVersion((current) => current + 1);
               }}
            />
         ) : null}
      </section>
   );
}
