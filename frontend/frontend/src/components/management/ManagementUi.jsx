import { Link } from "react-router-dom";

import { formatManagementDate, managementStatusTone } from "../../utils/management";
import Icons from "../Icons";
import Badge from "../ui/Badge";
import Button from "../ui/Button";

export function ManagementPageHeader({ title, subtitle, backTo, backLabel = "Back" }) {
   return (
      <header className="management-page-header">
         {backTo ? (
            <Link to={backTo} className="management-back-link">
               <Icons name="arrow-left" size={16} />
               {backLabel}
            </Link>
         ) : null}
         <h1>{title}</h1>
         {subtitle ? <p>{subtitle}</p> : null}
      </header>
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
            <span>Please wait while the latest governance records are retrieved.</span>
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
