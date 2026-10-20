import { useEffect, useId, useRef } from "react";
import { Link } from "react-router-dom";

import { formatManagementDate, managementStatusTone } from "../../utils/management";
import Icons from "../Icons";
import Badge from "../ui/Badge";
import Button from "../ui/Button";

const FOCUSABLE_SELECTOR = [
   "button:not([disabled])",
   "[href]",
   "input:not([disabled])",
   "select:not([disabled])",
   "textarea:not([disabled])",
   '[tabindex]:not([tabindex="-1"])',
].join(",");

export function ManagementPageHeader({ title, subtitle, backTo, backLabel = "Back", actions }) {
   return (
      <header className="management-page-header">
         {backTo ? (
            <Link to={backTo} className="management-back-link">
               <Icons name="arrow-left" size={16} />
               {backLabel}
            </Link>
         ) : null}
         <div className="management-page-header__content">
            <div>
               <h1>{title}</h1>
               {subtitle ? <p>{subtitle}</p> : null}
            </div>
            {actions ? <div className="management-page-header__actions">{actions}</div> : null}
         </div>
      </header>
   );
}

export function ManagementFeedback({ tone = "success", children }) {
   if (!children) return null;
   return (
      <div
         className={`management-feedback management-feedback--${tone}`}
         role={tone === "error" ? "alert" : "status"}
         aria-live="polite"
      >
         <Icons name={tone === "error" ? "alert-circle" : "check-circle"} size={18} />
         <span>{children}</span>
      </div>
   );
}


export function ManagementFormDialog({
   open,
   title,
   description,
   onClose,
   processing = false,
   children,
   returnFocusRef,
}) {
   const id = useId();
   const dialogRef = useRef(null);
   const cancelRef = useRef(onClose);
   const processingRef = useRef(processing);
   const titleId = `${id}-title`;
   const descriptionId = `${id}-description`;

   useEffect(() => {
      cancelRef.current = onClose;
      processingRef.current = processing;
   }, [onClose, processing]);

   useEffect(() => {
      if (!open) return undefined;
      const previousFocus = document.activeElement;
      const explicitReturnTarget = returnFocusRef?.current;
      const previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      const initialFocus = dialogRef.current?.querySelector(FOCUSABLE_SELECTOR);
      initialFocus?.focus();

      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !processingRef.current) {
            event.preventDefault();
            cancelRef.current?.();
            return;
         }
         if (event.key !== "Tab") return;
         const items = Array.from(
            dialogRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) || [],
         ).filter((node) => !node.hidden && node.getClientRects().length > 0);
         if (!items.length) {
            event.preventDefault();
            return;
         }
         const first = items[0];
         const last = items[items.length - 1];
         if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
         } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
         }
      };
      document.addEventListener("keydown", handleKeyDown);
      return () => {
         document.removeEventListener("keydown", handleKeyDown);
         document.body.style.overflow = previousOverflow;
         const target = explicitReturnTarget?.isConnected
            ? explicitReturnTarget : previousFocus;
         if (target?.isConnected) target.focus();
      };
   }, [open, returnFocusRef]);

   if (!open) return null;

   return (
      <div className="management-dialog-backdrop" onMouseDown={(event) => {
         if (event.target === event.currentTarget && !processing) onClose();
      }}>
         <div
            ref={dialogRef}
            className="management-dialog management-dialog--form"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            aria-describedby={descriptionId}
         >
            <div className="management-form-dialog__heading">
               <div>
                  <h2 id={titleId}>{title}</h2>
                  <p id={descriptionId}>{description}</p>
               </div>
               <button type="button" className="management-form-dialog__close"
                  onClick={onClose} disabled={processing} aria-label="Close dialog">
                  <Icons name="x" size={20} />
               </button>
            </div>
            <div className="management-form-dialog__body">{children}</div>
         </div>
      </div>
   );
}

export function ManagementConfirmDialog({
   open,
   title,
   description,
   warning,
   error,
   confirmLabel,
   processing = false,
   confirmVariant = "primary",
   returnFocusRef,
   onConfirm,
   onClose,
}) {
   const dialogRef = useRef(null);
   const cancelRef = useRef(null);
   const onCloseRef = useRef(onClose);
   const processingRef = useRef(processing);

   useEffect(() => {
      onCloseRef.current = onClose;
      processingRef.current = processing;
   }, [onClose, processing]);

   useEffect(() => {
      if (!open) return undefined;

      const previousFocus = document.activeElement;
      const explicitReturnTarget = returnFocusRef?.current;
      cancelRef.current?.focus();

      const handleKeyDown = (event) => {
         if (event.key === "Escape" && !processingRef.current) {
            event.preventDefault();
            onCloseRef.current();
            return;
         }
         if (event.key !== "Tab") return;

         const focusable = Array.from(
            dialogRef.current?.querySelectorAll(FOCUSABLE_SELECTOR) || [],
         ).filter((element) => !element.hidden);
         if (!focusable.length) return;
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
      return () => {
         document.removeEventListener("keydown", handleKeyDown);
         const returnTarget = explicitReturnTarget?.isConnected
            ? explicitReturnTarget
            : previousFocus;
         if (returnTarget?.isConnected) returnTarget.focus();
      };
   }, [open, returnFocusRef]);

   if (!open) return null;

   return (
      <div
         className="management-dialog-backdrop"
         onMouseDown={(event) => {
            if (event.target === event.currentTarget && !processing) onClose();
         }}
      >
         <div
            ref={dialogRef}
            className="management-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="management-confirm-title"
            aria-describedby="management-confirm-description"
         >
            <h2 id="management-confirm-title">{title}</h2>
            <p id="management-confirm-description">{description}</p>
            {warning ? <div className="management-dialog__warning">{warning}</div> : null}
            {error ? <div className="management-dialog__error" role="alert">{error}</div> : null}
            <div className="management-dialog__actions">
               <Button ref={cancelRef} variant="secondary" disabled={processing} onClick={onClose}>
                  Cancel
               </Button>
               <Button
                  variant={confirmVariant}
                  loading={processing}
                  loadingLabel="Working…"
                  onClick={onConfirm}
               >
                  {confirmLabel}
               </Button>
            </div>
         </div>
      </div>
   );
}

export function ManagementStatus({ value, label }) {
   return <Badge tone={managementStatusTone(value)}>{label || value || "Not recorded"}</Badge>;
}

export function ManagementRequestState({ loading, error, empty, emptyMessage, onRetry, children }) {
   if (loading) {
      return (
         <div className="management-state" role="status" aria-live="polite">
            <Icons name="loader" className="management-state__spinner" size={22} />
            <strong>Loading management data</strong>
            <span>Please wait while the latest records are retrieved.</span>
         </div>
      );
   }

   if (error) {
      return (
         <div className="management-state management-state--error" role="alert">
            <Icons name="alert-circle" size={22} />
            <strong>Management data is unavailable</strong>
            <span>{error}</span>
            <Button variant="secondary" density="compact" onClick={onRetry}>
               Try again
            </Button>
         </div>
      );
   }

   if (empty) {
      return (
         <div className="management-state">
            <Icons name="inbox" size={22} />
            <strong>No records found</strong>
            <span>{emptyMessage}</span>
         </div>
      );
   }

   return children;
}

export function ManagementPagination({ count, page, pageSize = 20, onPageChange }) {
   const pageCount = Math.max(1, Math.ceil(count / pageSize));
   if (pageCount <= 1) return null;

   return (
      <nav className="management-pagination" aria-label="Results pages">
         <span>
            Page {page} of {pageCount}
         </span>
         <div>
            <Button
               variant="secondary"
               density="compact"
               disabled={page <= 1}
               onClick={() => onPageChange(page - 1)}
            >
               Previous
            </Button>
            <Button
               variant="secondary"
               density="compact"
               disabled={page >= pageCount}
               onClick={() => onPageChange(page + 1)}
            >
               Next
            </Button>
         </div>
      </nav>
   );
}

export function DetailList({ items }) {
   return (
      <dl className="management-detail-list">
         {items.map(({ label, value, node, dateOnly }) => (
            <div key={label}>
               <dt>{label}</dt>
               <dd>{node || (dateOnly !== undefined ? formatManagementDate(value, { dateOnly }) : value || "Not recorded")}</dd>
            </div>
         ))}
      </dl>
   );
}
