import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import Icons from "../Icons.jsx";

import { resolveApiEndpoint } from "../../utils/api";

import "./OrganizationAdminPanel.css";

function formatLabel(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDate(value) {
   if (!value) {
      return "Not recorded";
   }

   const date = new Date(value);

   if (Number.isNaN(date.getTime())) {
      return "Not recorded";
   }

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
   }).format(date);
}

function getStatusIcon(status) {
   switch (status) {
      case "ACTIVE":
         return "user-check";

      case "PENDING":
         return "clock";

      case "SUSPENDED":
         return "alert-circle";

      default:
         return "user";
   }
}

function OrganizationAdminPanel({ organizationId, organizationName }) {
   const { authFetch } = useAuth();

   const [requestVersion, setRequestVersion] = useState(0);

   const [roster, setRoster] = useState({
      organization: null,
      count: 0,
      summary: {
         active: 0,
         pending: 0,
         suspended: 0,
      },
      results: [],
   });

   const [loading, setLoading] = useState(true);

   const [errorMessage, setErrorMessage] = useState("");

   const membersUrl = useMemo(() => {
      if (!organizationId) {
         return null;
      }

      return resolveApiEndpoint("ORGANIZATION_MEMBERS", organizationId);
   }, [organizationId]);

   useEffect(() => {
      if (!membersUrl) {
         return undefined;
      }

      let cancelled = false;

      authFetch(membersUrl, {
         method: "GET",
      })
         .then((data) => {
            if (cancelled) {
               return;
            }

            setRoster({
               organization: data?.organization ?? null,
               count: Number(data?.count ?? 0),
               summary: {
                  active: Number(data?.summary?.active ?? 0),
                  pending: Number(data?.summary?.pending ?? 0),
                  suspended: Number(data?.summary?.suspended ?? 0),
               },
               results: Array.isArray(data?.results) ? data.results : [],
            });

            setErrorMessage("");
         })
         .catch((error) => {
            if (cancelled) {
               return;
            }

            setErrorMessage(error?.message || "Unable to load organization members.");

            setRoster({
               organization: null,
               count: 0,
               summary: {
                  active: 0,
                  pending: 0,
                  suspended: 0,
               },
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
   }, [authFetch, membersUrl, requestVersion]);

   const refresh = () => {
      setLoading(true);
      setErrorMessage("");

      setRequestVersion((current) => current + 1);
   };

   if (!organizationId) {
      return (
         <div className="org-admin-state">
            <Icons name="users" size={25} />

            <h3>No organization selected</h3>

            <p>Select an organization before viewing its member roster.</p>
         </div>
      );
   }

   if (loading) {
      return (
         <div className="org-admin-state" aria-live="polite">
            <Icons name="loader" size={21} className="org-admin-spinner" />

            <span>Loading organization members...</span>
         </div>
      );
   }

   if (errorMessage) {
      return (
         <div className="org-admin-error" role="alert">
            <Icons name="alert-circle" size={18} />

            <div>
               <strong>Member roster unavailable</strong>

               <span>{errorMessage}</span>

               <button type="button" onClick={refresh}>
                  <Icons name="refresh-cw" size={14} />
                  Try again
               </button>
            </div>
         </div>
      );
   }

   return (
      <div className="organization-admin-panel">
         <div className="org-admin-toolbar">
            <div>
               <strong>Organization members</strong>

               <span>
                  {roster.count} current membership
                  {roster.count === 1 ? "" : "s"} at{" "}
                  {organizationName || roster.organization?.name || "this organization"}
               </span>
            </div>

            <button type="button" onClick={refresh}>
               <Icons name="refresh-cw" size={15} />
               Refresh
            </button>
         </div>

         <div className="org-admin-summary" aria-label="Membership summary">
            <div>
               <span>Total</span>

               <strong>{roster.count}</strong>
            </div>

            <div>
               <span>Active</span>

               <strong>{roster.summary.active}</strong>
            </div>

            <div>
               <span>Pending</span>

               <strong>{roster.summary.pending}</strong>
            </div>

            <div>
               <span>Suspended</span>

               <strong>{roster.summary.suspended}</strong>
            </div>
         </div>

         {roster.results.length === 0 ? (
            <div className="org-admin-state">
               <Icons name="users" size={25} />

               <h3>No current members</h3>

               <p>Current organization memberships will appear here.</p>
            </div>
         ) : (
            <div className="org-member-list">
               {roster.results.map((membership) => {
                  const user = membership?.user ?? {};

                  return (
                     <article key={membership.id} className="org-member-card">
                        <div className="org-member-identity">
                           <div className="org-member-avatar">
                              <Icons name="user" size={18} />
                           </div>

                           <div>
                              <strong>@{user.username || "unknown"}</strong>

                              <span>{user.email || "No email available"}</span>
                           </div>
                        </div>

                        <div className="org-member-details">
                           <div>
                              <span>Role</span>

                              <strong>{formatLabel(membership.role)}</strong>
                           </div>

                           <div>
                              <span>Status</span>

                              <span
                                 className={`org-member-status ${String(membership.status || "UNKNOWN").toLowerCase()}`}
                              >
                                 <Icons name={getStatusIcon(membership.status)} size={13} />

                                 {formatLabel(membership.status)}
                              </span>
                           </div>

                           <div>
                              <span>Joined</span>

                              <strong>{formatDate(membership.joined_at)}</strong>
                           </div>

                           <div>
                              <span>Approved by</span>

                              <strong>
                                 {membership?.approved_by?.username
                                    ? `@${membership.approved_by.username}`
                                    : "Not recorded"}
                              </strong>
                           </div>
                        </div>
                     </article>
                  );
               })}
            </div>
         )}
      </div>
   );
}

export default OrganizationAdminPanel;
