import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
   ManagementFeedback,
   ManagementPageHeader,
   ManagementPagination,
   ManagementRequestState,
} from "../components/management/ManagementUi";
import Button from "../components/ui/Button";
import { useManagementMutation } from "../hooks/useManagementMutation";
import { useManagementRequest } from "../hooks/useManagementRequest";
import { resolveApiEndpoint } from "../utils/api";
import { formatManagementClaimType, formatManagementDate } from "../utils/management";

const PAGE_SIZE = 20;

const CLASSIFICATION_STATUSES = {
   NOT_ATTEMPTED: "Not attempted",
   SUGGESTED: "Shadow suggestion — not authorized",
   ABSTAINED: "Classification abstained",
   FAILED: "Classification failed",
};

function ManagementClaimClassificationPage() {
   const [page, setPage] = useState(1);
   const [notice, setNotice] = useState("");
   const url = useMemo(() => {
      const endpoint = new URL(resolveApiEndpoint("MANAGEMENT_UNCLASSIFIED_INTAKE"));
      endpoint.searchParams.set("page", String(page));
      return endpoint.toString();
   }, [page]);
   const { data, loading, error, retry } = useManagementRequest(url);
   const { mutate, pending, error: mutationError } = useManagementMutation();

   const retryClassification = async (claimId) => {
      const result = await mutate(
         resolveApiEndpoint("MANAGEMENT_CLASSIFICATION_RETRY", claimId),
         { method: "POST", body: {} },
      );
      if (!result.ok) return;
      setNotice("A new automatic classification attempt was queued. Refresh to check its status.");
      retry();
   };

   return (
      <div className="management-page">
         <ManagementPageHeader
            title="Classification Exceptions"
            subtitle="Investigations without a validated automatic subject and geographic classification."
         />
         <div className="management-boundary-note">
            <div>
               <strong>Automatic classification is distinct from factual verification</strong>
               <p>
                  Claims are classified asynchronously. Unsupported, ambiguous, and failed outcomes
                  stay unclaimable, without assigning them an invented topic or jurisdiction.
                  This page is for inspecting exceptions and retrying the classifier, not
                  manually approving its suggestions.
               </p>
            </div>
         </div>
         {notice ? <ManagementFeedback>{notice}</ManagementFeedback> : null}
         {mutationError ? <ManagementFeedback tone="error">{mutationError.message}</ManagementFeedback> : null}
         <ManagementRequestState loading={loading} error={error}
            empty={Boolean(data && !data.count)}
            emptyMessage="No unclassified investigations are awaiting resolution."
            onRetry={retry}>
            {data ? (
               <section className="management-section">
                  <div className="management-section__title-row">
                     <h2>Unclassified investigation queue</h2>
                     <Button type="button" variant="secondary" onClick={retry} disabled={loading}>Refresh</Button>
                  </div>
                  <div className="management-table-wrap management-section__table">
                     <table className="management-table">
                        <thead>
                           <tr><th>Claim context</th><th>Type</th><th>Created</th><th>Status</th><th>Action</th></tr>
                        </thead>
                        <tbody>
                           {data.results.map((item) => (
                              <tr key={item.assignment_id}>
                                 <td data-label="Claim context">
                                    <strong>{item.claim_text || "No readable text context"}</strong>
                                    <small>Claim ID: {item.claim_id}</small>
                                 </td>
                                 <td data-label="Type">{formatManagementClaimType(item.claim_type)}</td>
                                 <td data-label="Created">{formatManagementDate(item.created_at)}</td>
                                 <td data-label="Status">
                                    <strong>{CLASSIFICATION_STATUSES[item.classification_status] || item.classification_status}</strong>
                                    {item.classification_reason ? <small>{item.classification_reason.replaceAll("_", " ")}</small> : null}
                                 </td>
                                 <td data-label="Action">
                                    <div className="management-inline-actions">
                                       <Link className="management-inline-link"
                                          to={`/analysis/${item.claim_id}`}
                                          target="_blank" rel="noopener noreferrer">Inspect claim</Link>
                                       <Button variant="secondary" density="compact" disabled={pending}
                                          onClick={() => retryClassification(item.claim_id)}>
                                          Retry automatic classification
                                       </Button>
                                    </div>
                                 </td>
                              </tr>
                           ))}
                        </tbody>
                     </table>
                  </div>
                  <ManagementPagination count={data.count} page={page}
                     pageSize={PAGE_SIZE}
                     onPageChange={setPage} />
               </section>
            ) : null}
         </ManagementRequestState>
      </div>
   );
}

export default ManagementClaimClassificationPage;
