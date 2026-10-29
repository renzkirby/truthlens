import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "../../hooks/useAuth";
import { useNotification } from "../../hooks/useNotification";
import { resolveApiEndpoint } from "../../utils/api";
import { showWorkspaceSuccess } from "../../utils/workspaceToast";

import Icons from "../Icons.jsx";
import Button from "../ui/Button.jsx";
import Input from "../ui/Input.jsx";
import Select from "../ui/Select.jsx";

import "./OrganizationWorkloadPanel.css";

const PAGE_SIZE = 10;

const CLAIM_TYPE_OPTIONS = [
   { value: "", label: "All claim types" },
   { value: "TEXT", label: "Text" },
   { value: "IMAGE", label: "Image" },
   { value: "URL", label: "URL" },
   { value: "FILE", label: "File" },
];

function formatDateTime(value) {
   if (!value) return "Unknown";

   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Unknown";

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
   }).format(date);
}

function formatLabel(value) {
   if (!value) return "Unknown";

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatConfidence(value) {
   if (value === null || value === undefined || value === "") return null;

   const numeric = Number(value);
   if (!Number.isFinite(numeric)) return null;
   return `${Math.round(numeric)}%`;
}

function OrganizationWorkloadPanel({
   organizationId,
   organizationName,
   canReleaseInvestigation = false,
   onOpenInvestigation,
}) {
   const { authFetch } = useAuth();
   const { addToast } = useNotification();

   const [offset, setOffset] = useState(0);
   const [requestVersion, setRequestVersion] = useState(0);
   const [loadedUrl, setLoadedUrl] = useState(null);

   const [searchInput, setSearchInput] = useState("");
   const [search, setSearch] = useState("");
   const [ownership, setOwnership] = useState("all");
   const [claimType, setClaimType] = useState("");
   const [sortOrder, setSortOrder] = useState("newest");

   const [workload, setWorkload] = useState({
      count: 0,
      results: [],
   });
   const [loading, setLoading] = useState(true);
   const [errorMessage, setErrorMessage] = useState("");
   const [actionError, setActionError] = useState("");
   const [confirmingReleaseId, setConfirmingReleaseId] = useState(null);
   const [releasingId, setReleasingId] = useState(null);
   const releaseCancelRef = useRef(null);
   const releaseTriggerRefs = useRef(new Map());

   useEffect(() => {
      if (!confirmingReleaseId) return undefined;

      const frame = window.requestAnimationFrame(() => {
         releaseCancelRef.current?.focus();
      });

      return () => window.cancelAnimationFrame(frame);
   }, [confirmingReleaseId]);

   useEffect(() => {
      const timer = window.setTimeout(() => {
         const nextSearch = searchInput.trim();
         if (nextSearch === search) return;

         setSearch(nextSearch);
         setOffset(0);
         setLoading(true);
      }, 300);

      return () => window.clearTimeout(timer);
   }, [search, searchInput]);

   const workloadUrl = useMemo(() => {
      if (!organizationId) return null;

      const query = new URLSearchParams({
         organization_id: String(organizationId),
         limit: String(PAGE_SIZE),
         offset: String(offset),
         ownership,
         sort: sortOrder,
      });

      if (search) query.set("search", search);
      if (claimType) query.set("claim_type", claimType);

      return `${resolveApiEndpoint("VERIFICATION_WORKLOAD")}?${query.toString()}`;
   }, [claimType, organizationId, offset, ownership, search, sortOrder]);

   useEffect(() => {
      if (!workloadUrl) return undefined;

      let cancelled = false;

      authFetch(workloadUrl, { method: "GET" })
         .then((data) => {
            if (cancelled) return;

            setWorkload({
               count: Number(data?.count ?? 0),
               results: Array.isArray(data?.results) ? data.results : [],
            });
            setLoadedUrl(workloadUrl);
            setErrorMessage("");
         })
         .catch((error) => {
            if (cancelled) return;
            setErrorMessage(error?.message || "Unable to load organization investigations.");
         })
         .finally(() => {
            if (!cancelled) setLoading(false);
         });

      return () => {
         cancelled = true;
      };
   }, [authFetch, requestVersion, workloadUrl]);

   const resetTransientState = () => {
      setErrorMessage("");
      setActionError("");
      setConfirmingReleaseId(null);
   };

   const refresh = () => {
      setLoading(true);
      resetTransientState();
      setRequestVersion((current) => current + 1);
   };

   const updateOwnership = (value) => {
      setOwnership(value);
      setOffset(0);
      setLoading(true);
      resetTransientState();
   };

   const updateClaimType = (value) => {
      setClaimType(value);
      setOffset(0);
      setLoading(true);
      resetTransientState();
   };

   const updateSortOrder = (value) => {
      setSortOrder(value);
      setOffset(0);
      setLoading(true);
      resetTransientState();
   };

   const clearFilters = () => {
      setSearchInput("");
      setSearch("");
      setOwnership("all");
      setClaimType("");
      setSortOrder("newest");
      setOffset(0);
      setLoading(true);
      resetTransientState();
   };

   const handlePreviousPage = () => {
      setLoading(true);
      resetTransientState();
      setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_SIZE));
   };

   const handleNextPage = () => {
      setLoading(true);
      resetTransientState();
      setOffset((currentOffset) => currentOffset + PAGE_SIZE);
   };

   const hasCurrentWorkload = loadedUrl === workloadUrl;
   const isBlockingLoad = loading && !hasCurrentWorkload;
   const isBackgroundRefresh = loading && hasCurrentWorkload;
   const hasPrevious = offset > 0;
   const hasNext = offset + workload.results.length < workload.count;
   const rangeStart = workload.count === 0 ? 0 : offset + 1;
   const rangeEnd = Math.min(offset + workload.results.length, workload.count);
   const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
   const totalPages = Math.max(1, Math.ceil(workload.count / PAGE_SIZE));
   const hasFilters = Boolean(search || claimType || ownership !== "all" || sortOrder !== "newest");

   const removeReleasedAssignmentFromWorkload = (assignmentId) => {
      const remainingResults = workload.results.filter((assignment) => assignment.id !== assignmentId);

      setWorkload((current) => ({
         ...current,
         count: Math.max(0, Number(current.count ?? 0) - 1),
         results: current.results.filter((assignment) => assignment.id !== assignmentId),
      }));

      if (offset > 0 && remainingResults.length === 0) {
         setLoading(true);
         setOffset((currentOffset) => Math.max(0, currentOffset - PAGE_SIZE));
      }
   };

   const handleRelease = async (assignmentId) => {
      if (!assignmentId || !canReleaseInvestigation) return;

      setReleasingId(assignmentId);
      setActionError("");

      try {
         await authFetch(resolveApiEndpoint("VERIFICATION_ASSIGNMENT_RELEASE", assignmentId), {
            method: "POST",
         });

         setConfirmingReleaseId(null);
         removeReleasedAssignmentFromWorkload(assignmentId);
         showWorkspaceSuccess(addToast, {
            title: "Investigation released",
            message: "It has returned to shared Verification Intake.",
         });
      } catch (error) {
         setConfirmingReleaseId(null);

         if (error?.status === 409) {
            setActionError(error?.message || "This investigation can no longer be released.");
            setRequestVersion((current) => current + 1);
         } else {
            setActionError(error?.message || "Unable to release this investigation.");
         }
      } finally {
         setReleasingId(null);
      }
   };

   const closeReleaseConfirmation = (assignmentId) => {
      setConfirmingReleaseId(null);
      window.requestAnimationFrame(() => {
         releaseTriggerRefs.current.get(assignmentId)?.focus();
      });
   };

   return (
      <div className="organization-workload" aria-busy={loading ? "true" : undefined}>
         <div className="workload-overview">
            <div>
               <strong>
                  {hasCurrentWorkload ? workload.count : "—"} active investigations
               </strong>
               <p>Resume fact-checking work currently owned by {organizationName || "this organization"}.</p>
            </div>

            <Button
               type="button"
               variant="secondary"
               density="compact"
               className="workload-refresh-action"
               leadingIcon={<Icons name="refresh-cw" size={14} />}
               onClick={refresh}
               loading={isBackgroundRefresh}
               loadingLabel="Refreshing…"
               disabled={loading}
            >
               Refresh
            </Button>
         </div>

         <section className="workload-toolbar" aria-label="Investigation filters">
            <div className="workload-view-tabs" aria-label="Investigation ownership">
               <button
                  type="button"
                  className={ownership === "all" ? "active" : ""}
                  aria-pressed={ownership === "all"}
                  onClick={() => updateOwnership("all")}
               >
                  All active
               </button>
               <button
                  type="button"
                  className={ownership === "mine" ? "active" : ""}
                  aria-pressed={ownership === "mine"}
                  onClick={() => updateOwnership("mine")}
               >
                  My work
               </button>
            </div>

            <div className="workload-filter-bar">
               <div className="workload-search">
                  <label htmlFor="investigation-search">Search investigations</label>
                  <Input
                     id="investigation-search"
                     value={searchInput}
                     onChange={(event) => setSearchInput(event.target.value)}
                     placeholder="Search investigations…"
                     leadingIcon={<Icons name="search" size={15} />}
                     density="standard"
                  />
               </div>

               <div className="workload-filter-field">
                  <label htmlFor="investigation-type-filter">Claim type</label>
                  <Select
                     id="investigation-type-filter"
                     value={claimType}
                     onChange={(event) => updateClaimType(event.target.value)}
                     density="standard"
                  >
                     {CLAIM_TYPE_OPTIONS.map((option) => (
                        <option key={option.value || "all"} value={option.value}>
                           {option.label}
                        </option>
                     ))}
                  </Select>
               </div>

               <div className="workload-filter-field">
                  <label htmlFor="investigation-sort">Sort</label>
                  <Select
                     id="investigation-sort"
                     value={sortOrder}
                     onChange={(event) => updateSortOrder(event.target.value)}
                     density="standard"
                  >
                     <option value="newest">Newest investigations</option>
                     <option value="oldest">Oldest investigations</option>
                  </Select>
               </div>

               {hasFilters ? (
                  <Button type="button" variant="ghost" density="compact" onClick={clearFilters}>
                     Clear filters
                  </Button>
               ) : null}
            </div>
         </section>

         {actionError && (
            <div className="workload-action-error" role="alert">
               <Icons name="alert-circle" size={17} />
               <div>
                  <strong>Release unavailable</strong>
                  <span>{actionError}</span>
               </div>
            </div>
         )}

         {errorMessage && (
            <div className="workload-error" role="alert">
               <Icons name="alert-circle" size={18} />
               <div>
                  <strong>Investigations unavailable</strong>
                  <span>{errorMessage}</span>
                  <Button
                     type="button"
                     variant="secondary"
                     density="compact"
                     leadingIcon={<Icons name="refresh-cw" size={14} />}
                     onClick={refresh}
                     disabled={loading}
                  >
                     Try again
                  </Button>
               </div>
            </div>
         )}

         {isBlockingLoad ? (
            <div className="workload-state" role="status" aria-live="polite">
               <Icons name="loader" size={21} className="workload-spinner" />
               <span>Loading investigations…</span>
            </div>
         ) : null}

         {!isBlockingLoad && hasCurrentWorkload && workload.results.length === 0 ? (
            <div className="workload-state">
               <Icons name={hasFilters ? "search" : "inbox"} size={25} />
               <h3>{hasFilters ? "No investigations match these filters" : "No active investigations"}</h3>
               <p>
                  {hasFilters
                     ? "Adjust or clear the filters to see other organization work."
                     : "Claimed investigations will appear here once your organization accepts work from Verification Intake."}
               </p>
               {hasFilters ? (
                  <Button type="button" variant="secondary" density="compact" onClick={clearFilters}>
                     Clear filters
                  </Button>
               ) : null}
            </div>
         ) : null}

         {!isBlockingLoad && hasCurrentWorkload && workload.results.length > 0 ? (
            <>
               <div className="workload-list-heading">
                  <span>
                     Showing {rangeStart}–{rangeEnd} of {workload.count}
                  </span>
                  <span>Open an investigation to continue its guided workflow.</span>
               </div>

               <ul className="workload-list">
                  {workload.results.map((assignment) => {
                     const claim = assignment?.claim ?? {};
                     const isConfirmingRelease = confirmingReleaseId === assignment.id;
                     const isReleasing = releasingId === assignment.id;
                     const confidence = formatConfidence(claim.consensus_score);
                     const claimHeadingId = `investigation-claim-${assignment.id}`;
                     const releaseConfirmationId = `investigation-release-${assignment.id}`;

                     return (
                        <li key={assignment.id} className="workload-list-item">
                           <article className="workload-item" aria-labelledby={claimHeadingId}>
                              <div className="workload-item-main">
                                 <div className="workload-item-kicker">
                                    <span className="workload-status">Active</span>
                                    <span className="workload-type">{formatLabel(claim.claim_type)}</span>
                                 </div>

                                 <h3 id={claimHeadingId} className="workload-claim-text">
                                    {claim.context_text || "Investigation text unavailable"}
                                 </h3>

                                 <dl className="workload-row-meta">
                                    <div>
                                       <dt>Claimed by</dt>
                                       <dd>
                                          {assignment?.claimed_by?.username
                                             ? `@${assignment.claimed_by.username}`
                                             : "Unknown"}
                                       </dd>
                                    </div>
                                    <div className="workload-evidence-meta">
                                       <dt>Evidence</dt>
                                       <dd>
                                          {Number(assignment.evidence_count || 0)}{" "}
                                          {Number(assignment.evidence_count || 0) === 1 ? "item" : "items"}
                                       </dd>
                                    </div>
                                    <div>
                                       <dt>AI assessment</dt>
                                       <dd>{claim.ai_verdict ? formatLabel(claim.ai_verdict) : "No AI assessment"}</dd>
                                    </div>
                                    {confidence ? (
                                       <div>
                                          <dt>AI confidence</dt>
                                          <dd>{confidence}</dd>
                                       </div>
                                    ) : null}
                                    <div>
                                       <dt>Source</dt>
                                       <dd>{claim.source_type || "Not recorded"}</dd>
                                    </div>
                                 </dl>
                              </div>

                              <div className="workload-item-actions">
                                 {claim.last_updated || assignment.updated_at ? (
                                    <time
                                       className="workload-updated-at"
                                       dateTime={claim.last_updated || assignment.updated_at}
                                    >
                                       Updated {formatDateTime(claim.last_updated || assignment.updated_at)}
                                    </time>
                                 ) : (
                                    <span className="workload-updated-at">Updated date unavailable</span>
                                 )}

                                 <div className="workload-action-buttons">
                                    <Button
                                       type="button"
                                       variant="primary"
                                       density="standard"
                                       trailingIcon={<Icons name="arrow-right" size={15} />}
                                       onClick={() => onOpenInvestigation?.(assignment)}
                                    >
                                       Open investigation
                                    </Button>

                                    {canReleaseInvestigation && !isConfirmingRelease ? (
                                       <Button
                                          ref={(node) => {
                                             if (node) releaseTriggerRefs.current.set(assignment.id, node);
                                             else releaseTriggerRefs.current.delete(assignment.id);
                                          }}
                                          type="button"
                                          variant="ghost"
                                          density="compact"
                                          className="workload-release-action"
                                          aria-expanded="false"
                                          aria-controls={releaseConfirmationId}
                                          disabled={Boolean(releasingId)}
                                          onClick={() => setConfirmingReleaseId(assignment.id)}
                                       >
                                          Release
                                       </Button>
                                    ) : null}
                                 </div>
                              </div>

                              {canReleaseInvestigation && isConfirmingRelease ? (
                                 <div
                                    id={releaseConfirmationId}
                                    className="workload-release-confirm"
                                    role="group"
                                    aria-label="Confirm investigation release"
                                 >
                                    <div className="workload-release-warning">
                                       <Icons name="alert-triangle" size={17} />
                                       <span>
                                          Release this investigation back to shared intake? This is only permitted before authoritative review work begins.
                                       </span>
                                    </div>

                                    <div className="workload-release-controls">
                                       <Button
                                          ref={releaseCancelRef}
                                          type="button"
                                          variant="secondary"
                                          density="compact"
                                          disabled={isReleasing}
                                          onClick={() => closeReleaseConfirmation(assignment.id)}
                                       >
                                          Cancel
                                       </Button>
                                       <Button
                                          type="button"
                                          variant="secondary"
                                          density="compact"
                                          className="workload-warning-action"
                                          loading={isReleasing}
                                          loadingLabel="Releasing…"
                                          disabled={isReleasing}
                                          onClick={() => handleRelease(assignment.id)}
                                       >
                                          Confirm release
                                       </Button>
                                    </div>
                                 </div>
                              ) : null}
                           </article>
                        </li>
                     );
                  })}
               </ul>

               <div className="workload-pagination">
                  <span>
                     Page {currentPage} of {totalPages}
                  </span>

                  <div className="workload-pagination-controls">
                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        leadingIcon={<Icons name="chevron-left" size={15} />}
                        disabled={!hasPrevious}
                        onClick={handlePreviousPage}
                     >
                        Previous
                     </Button>

                     <Button
                        type="button"
                        variant="secondary"
                        density="compact"
                        trailingIcon={<Icons name="chevron-right" size={15} />}
                        disabled={!hasNext}
                        onClick={handleNextPage}
                     >
                        Next
                     </Button>
                  </div>
               </div>
            </>
         ) : null}
      </div>
   );
}

export default OrganizationWorkloadPanel;
