import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../hooks/useAuth";
import Button from "../ui/Button.jsx";
import Input from "../ui/Input.jsx";
import Icons from "../Icons.jsx";
import { resolveApiEndpoint } from "../../utils/api";
import {
   MANAGEMENT_VERIFICATION_DOMAINS,
   formatVerificationDomain,
} from "../../utils/management";
import "./OrganizationVerificationScopePanel.css";

function ScopeEditor({ mode, scope, onClose, onSaved }) {
   const dialogRef = useRef(null);
   const { authFetch } = useAuth();
   const isRequest = mode === "REQUEST";
   const initialDomains = isRequest ? scope.requested_domains : scope.active_domains;
   const initialJurisdictions = isRequest ? scope.requested_jurisdictions : scope.active_jurisdictions;
   const [domains, setDomains] = useState(initialDomains || []);
   const [jurisdictions, setJurisdictions] = useState((initialJurisdictions || []).join(", "));
   const [rationale, setRationale] = useState("");
   const [saving, setSaving] = useState(false);
   const [error, setError] = useState("");

   useEffect(() => {
      const dialog = dialogRef.current;
      dialog?.showModal();
      return () => dialog?.close();
   }, []);

   const submit = async (event) => {
      event.preventDefault();
      if (saving) return;
      setError("");
      setSaving(true);
      try {
         await authFetch(resolveApiEndpoint("ORGANIZATION_VERIFICATION_SCOPE", scope.organization_id), {
            method: "PATCH",
            body: {
               action: mode,
               domains,
               jurisdictions: [...new Set(
                  jurisdictions.split(",").map((value) => value.trim().toUpperCase()).filter(Boolean),
               )],
               rationale: rationale.trim(),
            },
         });
         onSaved();
      } catch (err) {
         setError(err?.detail || err?.message || "Could not save verification scope.");
      } finally {
         setSaving(false);
      }
   };
   const approved = new Set(scope.approved_domains || []);
   return (
      <dialog ref={dialogRef} className="org-scope-dialog" aria-labelledby="org-scope-dialog-title"
         aria-describedby="org-scope-dialog-description"
         onCancel={(event) => { if (saving) event.preventDefault(); else onClose(); }}
         onClose={onClose}>
         <div className="org-scope-dialog__heading">
            <div>
               <h3 id="org-scope-dialog-title">
                  {isRequest ? "Request verification specializations" : "Manage active investigation scope"}
               </h3>
               <p id="org-scope-dialog-description">
                  {isRequest
                     ? "Request additional qualifications for independent platform review. Requests do not grant authority."
                     : "Choose which approved specializations your organization currently accepts. You can reduce scope immediately."}
               </p>
            </div>
            <button type="button" onClick={onClose} disabled={saving} aria-label="Close scope editor">
               <Icons name="x" size={20} />
            </button>
         </div>
         <form onSubmit={submit} className="org-scope-dialog__form">
            <fieldset disabled={saving}>
               <legend>Subject-matter specializations</legend>
               <p>{isRequest ? "Select all subjects to request." : "Only previously approved subjects can be activated."}</p>
               <div className="org-scope-domain-grid">
                  {MANAGEMENT_VERIFICATION_DOMAINS.map(([code, label]) => {
                     const unavailable = !isRequest && !approved.has(code);
                     return (
                        <label key={code} className={`org-scope-domain ${domains.includes(code) ? "selected" : ""}`}>
                           <input type="checkbox" checked={domains.includes(code)}
                              disabled={saving || unavailable}
                              onChange={(event) => setDomains((current) => event.target.checked
                                 ? [...current, code] : current.filter((item) => item !== code))}
                           />
                           <span>{label}</span>
                           {unavailable ? <small>Not approved</small> : null}
                        </label>
                     );
                  })}
               </div>
            </fieldset>
            <label className="org-scope-input-label">
               Geographic coverage
               <Input value={jurisdictions} disabled={saving}
                  placeholder="PH, PH-NCR or GLOBAL"
                  onChange={(event) => setJurisdictions(event.target.value)} />
               <small>Comma-separated ISO-style scopes. GLOBAL means worldwide.</small>
            </label>
            {!isRequest ? (
               <p className="org-scope-note">
                  Approved geographic scopes: {scope.approved_jurisdictions.join(", ") || "None"}.
                  Additional coverage requires a new request and platform approval.
               </p>
            ) : null}
            <label className="org-scope-input-label">
               Rationale for the change
               <textarea rows={3} minLength={12} maxLength={2000}
                  required disabled={saving} value={rationale}
                  placeholder={isRequest ? "Explain the organization's qualifications." : "Explain why you are adjusting active investigation coverage."}
                  onChange={(event) => setRationale(event.target.value)}
               />
            </label>
            {error ? <div role="alert" className="org-scope-error">{error}</div> : null}
            <div className="org-scope-dialog__actions">
               <Button type="button" variant="secondary" disabled={saving} onClick={onClose}>Cancel</Button>
               <Button type="submit" loading={saving} loadingLabel="Saving…"
                  disabled={saving || rationale.trim().length < 12 || Boolean(domains.length) !== Boolean(jurisdictions.trim())}>
                  {isRequest ? "Submit for platform review" : "Save active scope"}
               </Button>
            </div>
         </form>
      </dialog>
   );
}

export default function OrganizationVerificationScopePanel({ organizationId }) {
   const { authFetch } = useAuth();
   const [scope, setScope] = useState(null);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState("");
   const [version, setVersion] = useState(0);
   const [editorMode, setEditorMode] = useState(null);

   useEffect(() => {
      let active = true;
      setLoading(true);
      setError("");
      authFetch(resolveApiEndpoint("ORGANIZATION_VERIFICATION_SCOPE", organizationId))
         .then((payload) => { if (active) setScope(payload); })
         .catch((err) => { if (active) setError(err?.message || "Unable to load verification scope."); })
         .finally(() => { if (active) setLoading(false); });
      return () => { active = false; };
   }, [authFetch, organizationId, version]);

   return (
      <section className="org-scope-panel">
         <div className="org-scope-panel__header">
            <div>
               <h3>Verification scope</h3>
               <p>Manage requested and currently active investigation subjects.
                  Platform approval remains independent of organization leadership.</p>
            </div>
         </div>
         {loading ? <p role="status">Loading verification scope…</p> : null}
         {error ? <div role="alert" className="org-scope-error">{error}</div> : null}
         {scope && !loading ? (
            <>
               <dl className="org-scope-summary">
                  <div>
                     <dt>Authorized subjects</dt>
                     <dd>{scope.approved_domains.length
                        ? scope.approved_domains.map(formatVerificationDomain).join(", ") : "None approved"}</dd>
                  </div>
                  <div><dt>Authorized geographic coverage</dt>
                     <dd>{scope.approved_jurisdictions.join(", ") || "None approved"}</dd>
                  </div>
                  <div><dt>Requested subjects</dt>
                     <dd>{scope.requested_domains.length
                        ? scope.requested_domains.map(formatVerificationDomain).join(", ") : "No request yet"}</dd>
                  </div>
                  <div><dt>Active subjects</dt>
                     <dd>{scope.active_domains.length
                        ? scope.active_domains.map(formatVerificationDomain).join(", ") : "No subjects active"}</dd>
                  </div>
                  <div><dt>Active geographic coverage</dt>
                     <dd>{scope.active_jurisdictions.join(", ") || "No coverage active"}</dd>
                  </div>
               </dl>
               <div className="org-scope-panel__actions">
                  <Button type="button" onClick={() => setEditorMode("REQUEST")}>
                     Request specializations
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => setEditorMode("ACTIVATE")}>
                     Manage active scope
                  </Button>
               </div>
            </>
         ) : null}
         {scope && editorMode ? (
            <ScopeEditor key={editorMode} mode={editorMode} scope={scope}
               onClose={() => setEditorMode(null)}
               onSaved={() => { setEditorMode(null); setVersion((current) => current + 1); }} />
         ) : null}
      </section>
   );
}
