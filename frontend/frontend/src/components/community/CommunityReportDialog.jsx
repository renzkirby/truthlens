import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";

import "./CommunityReportDialog.css";

import { COMMUNITY_REPORT_REASONS } from "./communityReportReasons.js";


function focusableElements(root) {
   return Array.from(
      root?.querySelectorAll(
         'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      ) || [],
   );
}

export default function CommunityReportDialog({
   open,
   busy = false,
   targetLabel = "content",
   onClose,
   onSubmit,
   fallbackFocusRef = null,
   returnFocusRef = null,
}) {
   const [reason, setReason] = useState("");
   const [notes, setNotes] = useState("");
   const [error, setError] = useState("");
   const dialogRef = useRef(null);
   const firstReasonRef = useRef(null);
   const previousFocusRef = useRef(null);
   const wasOpenRef = useRef(false);
   const titleId = useId();
   const descriptionId = useId();
   const reasonLegendId = useId();
   const notesId = useId();
   const errorId = useId();

   const selectedReason = COMMUNITY_REPORT_REASONS.find((item) => item.value === reason);
   const otherSelected = reason === "OTHER";
   const trimmedNotes = notes.trim();

   useEffect(() => {
      if (!open) return undefined;

      previousFocusRef.current =
         returnFocusRef?.current ||
         (document.activeElement instanceof HTMLElement ? document.activeElement : null);

      const focusFrame = window.requestAnimationFrame(() => firstReasonRef.current?.focus());
      return () => window.cancelAnimationFrame(focusFrame);
   }, [open, returnFocusRef]);

   useEffect(() => {
      if (!open) return undefined;

      const handleKeyDown = (event) => {
         if (event.key === "Escape") {
            if (busy) return;
            event.preventDefault();
            onClose?.();
            return;
         }
         if (event.key !== "Tab") return;

         const focusable = focusableElements(dialogRef.current);
         if (!focusable.length) {
            event.preventDefault();
            dialogRef.current?.focus();
            return;
         }

         const first = focusable[0];
         const last = focusable[focusable.length - 1];
         if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
         } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
         }
      };

      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
   }, [busy, onClose, open]);

   useEffect(() => {
      if (wasOpenRef.current && !open) {
         window.setTimeout(() => {
            const preferred = returnFocusRef?.current;
            if (preferred?.isConnected) preferred.focus();
            else if (previousFocusRef.current?.isConnected) previousFocusRef.current.focus();
            else fallbackFocusRef?.current?.focus();
         }, 0);
      }
      wasOpenRef.current = open;
   }, [fallbackFocusRef, open, returnFocusRef]);

   if (!open) return null;

   const submit = async () => {
      if (busy) return;

      if (!reason) {
         setError("Choose a reason before submitting the report.");
         firstReasonRef.current?.focus();
         return;
      }
      if (trimmedNotes.length > 1000) {
         setError("Report details must be 1000 characters or fewer.");
         return;
      }
      if (otherSelected && trimmedNotes.length < 10) {
         setError("Please explain your concern in at least 10 characters when selecting Others.");
         return;
      }

      setError("");
      await onSubmit?.({ reason, notes: trimmedNotes });
   };

   return (
      <div
         className="community-report-dialog-overlay"
         onMouseDown={(event) => {
            if (!busy && event.target === event.currentTarget) onClose?.();
         }}
      >
         <div
            ref={dialogRef}
            className="community-report-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
            tabIndex="-1"
         >
            <p className="community-report-dialog-kicker">Platform safety</p>
            <h2 id={titleId}>Report this {targetLabel}</h2>
            <p id={descriptionId} className="community-report-dialog-intro">
               Tell Platform Safety what seems wrong with this {targetLabel}.
            </p>

            <fieldset className="community-report-dialog-reasons" aria-describedby={error ? errorId : undefined}>
               <legend id={reasonLegendId}>Why are you reporting this?</legend>
               <div className="community-report-dialog-reason-list">
                  {COMMUNITY_REPORT_REASONS.map((item, index) => {
                     const descriptionOptionId = `${reasonLegendId}-${item.value.toLowerCase()}`;
                     return (
                        <label
                           key={item.value}
                           className={`community-report-dialog-reason ${reason === item.value ? "is-selected" : ""}`}
                        >
                           <input
                              ref={index === 0 ? firstReasonRef : null}
                              type="radio"
                              name="community-report-reason"
                              value={item.value}
                              checked={reason === item.value}
                              onChange={() => {
                                 setReason(item.value);
                                 setError("");
                              }}
                              aria-describedby={descriptionOptionId}
                              disabled={busy}
                           />
                           <span>
                              <strong>{item.label}</strong>
                              <small id={descriptionOptionId}>{item.description}</small>
                           </span>
                        </label>
                     );
                  })}
               </div>
            </fieldset>

            <p className="community-report-dialog-policy-note">
               Your selection helps Platform Safety understand the report. It does not automatically determine whether a Community Guidelines violation occurred.{" "}
               <Link to="/community-guidelines" target="_blank" rel="noopener noreferrer">
                  Read Community Guidelines
               </Link>
            </p>

            <p className="community-report-dialog-verify-note">
               Think a factual claim is wrong? <Link to="/verify">Use Verify</Link> or submit evidence instead of reporting it as a Safety violation.
            </p>

            {selectedReason?.sensitive && (
               <div className="community-report-dialog-safety-note" role="note">
                  <strong>Immediate safety concern?</strong>
                  <span>
                     If someone is in immediate danger, contact local emergency services or appropriate authorities. TruthLens is not an emergency service.
                  </span>
               </div>
            )}

            <div className="community-report-dialog-details">
               <label htmlFor={notesId}>
                  {otherSelected ? "Please explain your concern *" : "Additional details (optional)"}
               </label>
               <textarea
                  id={notesId}
                  rows={4}
                  value={notes}
                  onChange={(event) => {
                     setNotes(event.target.value);
                     setError("");
                  }}
                  minLength={otherSelected ? 10 : undefined}
                  maxLength={1000}
                  required={otherSelected}
                  disabled={busy}
                  aria-invalid={Boolean(error)}
                  aria-describedby={error ? errorId : undefined}
                  placeholder={
                     otherSelected
                        ? "Describe why this content should be reviewed."
                        : "Add context that may help Platform Safety review this report."
                  }
               />
               <span className="community-report-dialog-count">
                  {otherSelected ? "10–1000 characters required" : "Up to 1000 characters"}
               </span>
               {error && (
                  <p id={errorId} className="community-report-dialog-error" role="alert">
                     {error}
                  </p>
               )}
            </div>

            <div className="community-report-dialog-actions">
               <button type="button" className="community-report-dialog-secondary" onClick={onClose} disabled={busy}>
                  Cancel
               </button>
               <button type="button" className="community-report-dialog-primary" onClick={submit} disabled={busy}>
                  {busy ? "Submitting…" : "Submit report"}
               </button>
            </div>
         </div>
      </div>
   );
}
