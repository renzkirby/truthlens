import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import Icons from "../Icons.jsx";

import { resolveApiEndpoint } from "../../utils/api";

import "./OrganizationWorkloadPanel.css";

const PAGE_SIZE = 10;

function formatDateTime(value) {
   if (!value) {
      return "Unknown";
   }

   const date = new Date(value);

   if (Number.isNaN(date.getTime())) {
      return "Unknown";
   }

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function formatLabel(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function OrganizationWorkloadPanel({ organizationId, organizationName }) {
   const { authFetch } = useAuth();

   const [offset, setOffset] = useState(0);

   const [requestVersion, setRequestVersion] = useState(0);

   const [workload, setWorkload] = useState({
      count: 0,
      results: [],
   });

   const [loading, setLoading] = useState(true);

   const [errorMessage, setErrorMessage] = useState("");

   const workloadUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      const query = new URLSearchParams({
         organization_id: String(organizationId),
         limit: String(PAGE_SIZE),
         offset: String(offset),
      });

      return `${resolveApiEndpoint("VERIFICATION_WORKLOAD")}?${query.toString()}`;
   }, [organizationId, offset]);

   useEffect(() => {
      if (!workloadUrl) {
         return undefined;
      }

      let cancelled = false;

      authFetch(workloadUrl, {
         method: "GET",
      })
         .then((data) => {
            if (cancelled) {
               return;
            }

            setWorkload({
               count: Number(data?.count ?? 0),
               results: Array.isArray(data?.results) ? data.results : [],
            });

            setErrorMessage("");
         })
         .catch((error) => {
            if (cancelled) {
               return;
            }

            setErrorMessage(error?.message || "Unable to load organization workload.");

            setWorkload({
               count: 0,
               results: [],
            });
         })
         .finally(() => {
            if (!cancelled) {
               setLoading(false);
            }
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, workloadUrl, requestVersion]);

   const refresh = () => {
      setLoading(true);
      setErrorMessage("");

      setRequestVersion((current) => current + 1);
   };

   const handlePreviousPage = () => {
      setLoading(true);
      setErrorMessage("");

      setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_SIZE));
   };

   const handleNextPage = () => {
      setLoading(true);
      setErrorMessage("");

      setOffset((currentOffset) => currentOffset + PAGE_SIZE);
   };

   if (loading) {
      return (
         <div className="workload-state">
            <Icons name="loader" size={21} className="workload-spinner" />

            <span>Loading organization workload...</span>
         </div>
      );
   }

   if (errorMessage) {
      return (
         <div className="workload-error" role="alert">
            <Icons name="alert-circle" size={18} />

            <div>
               <strong>Workload unavailable</strong>

               <span>{errorMessage}</span>
            </div>
         </div>
      );
   }

   const hasPrevious = offset > 0;

   const hasNext = offset + workload.results.length < workload.count;

   const rangeStart = workload.count === 0 ? 0 : offset + 1;

   const rangeEnd = Math.min(offset + workload.results.length, workload.count);

   return (
      <div className="organization-workload">
         <div className="workload-toolbar">
            <div>
               <strong>Active investigations</strong>

               <span>
                  {workload.count} currently owned by {organizationName || "this organization"}
               </span>
            </div>

            <button type="button" onClick={refresh}>
               <Icons name="refresh-cw" size={15} />
               Refresh
            </button>
         </div>

         {workload.results.length === 0 ? (
            <div className="workload-state">
               <Icons name="inbox" size={25} />

               <h3>No active investigations</h3>

               <p>
                  Claimed investigations will appear here once your organization accepts work from Verification Intake.
               </p>
            </div>
         ) : (
            <>
               <div className="workload-list">
                  {workload.results.map((assignment) => {
                     const claim = assignment?.claim ?? {};

                     return (
                        <article key={assignment.id} className="workload-card">
                           <div className="workload-card-header">
                              <div>
                                 <span className="workload-status">Active</span>

                                 <span className="workload-type">{formatLabel(claim.claim_type)}</span>
                              </div>

                              <span>Claimed {formatDateTime(assignment.claimed_at)}</span>
                           </div>

                           <h3>{claim.context_text || "Claim text unavailable"}</h3>

                           <div className="workload-meta">
                              <div>
                                 <span>Claimed by</span>

                                 <strong>
                                    {assignment?.claimed_by?.username
                                       ? `@${assignment.claimed_by.username}`
                                       : "Unknown"}
                                 </strong>
                              </div>

                              <div>
                                 <span>AI assessment</span>

                                 <strong>{formatLabel(claim.ai_verdict || "UNVERIFIED")}</strong>
                              </div>

                              <div>
                                 <span>Last updated</span>

                                 <strong>{formatDateTime(claim.last_updated)}</strong>
                              </div>
                           </div>
                        </article>
                     );
                  })}
               </div>

               <div className="workload-pagination">
                  <span>
                     Showing {rangeStart}–{rangeEnd} of {workload.count}
                  </span>

                  <div>
                     <button type="button" disabled={!hasPrevious} onClick={handlePreviousPage}>
                        <Icons name="chevron-left" size={15} />
                        Previous
                     </button>

                     <button type="button" disabled={!hasNext} onClick={handleNextPage}>
                        Next
                        <Icons name="chevron-right" size={15} />
                     </button>
                  </div>
               </div>
            </>
         )}
      </div>
   );
}

export default OrganizationWorkloadPanel;
