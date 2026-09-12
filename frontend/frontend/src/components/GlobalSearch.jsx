import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { resolveApiEndpoint } from "../utils/api";
import Icons from "./Icons.jsx";
import Button from "./ui/Button.jsx";
import IconButton from "./ui/IconButton.jsx";
import Input from "./ui/Input.jsx";

import "./GlobalSearch.css";

const THREADS_ENDPOINT = resolveApiEndpoint("THREADS");
const USERS_SEARCH_ENDPOINT = resolveApiEndpoint("USER_SEARCH");
const MOBILE_DIALOG_ID = "tl-global-search-mobile-dialog";
const FOCUSABLE_SELECTOR = [
   "a[href]",
   "button:not([disabled])",
   "input:not([disabled])",
   "[tabindex]:not([tabindex='-1'])",
].join(",");

const isModeratorRole = (role) => role === "MOD" || role === "MODERATOR";

function normalizeResults(data) {
   if (Array.isArray(data?.results)) return data.results;
   return Array.isArray(data) ? data : [];
}

function getThreadTitle(thread) {
   const caption = thread?.caption?.trim();
   if (caption) return caption;

   const claimText = thread?.claim?.context_text?.trim();
   return claimText || "Untitled thread";
}

function getThreadSubtitle(thread) {
   const authorName = thread?.author?.username ? `@${thread.author.username}` : "Community thread";
   const authoritativeVerdict = thread?.claim?.effective_verdict || thread?.claim?.final_verdict;

   return authoritativeVerdict ? `${authorName} · ${authoritativeVerdict}` : authorName;
}

function SearchResults({ idPrefix, query, loading, error, users, threads, onNavigate }) {
   const hasResults = users.length > 0 || threads.length > 0;
   const statusMessage = loading
      ? "Searching TruthLens…"
      : error || (query && !hasResults ? `No results found for “${query}”.` : "");

   return (
      <section className="tl-global-search__results" aria-labelledby={`${idPrefix}-results-title`} aria-busy={loading}>
         <h2 id={`${idPrefix}-results-title`} className="tl-sr-only">
            Search results
         </h2>

         <div className="tl-global-search__status" role="status" aria-live="polite" aria-atomic="true">
            {loading && (
               <span className="tl-global-search__spinner" aria-hidden="true">
                  <Icons name="loader" size={16} />
               </span>
            )}
            {statusMessage}
         </div>

         {!loading && !error && users.length > 0 && (
            <section className="tl-global-search__section" aria-labelledby={`${idPrefix}-people-title`}>
               <h3 id={`${idPrefix}-people-title`} className="tl-global-search__section-title">
                  People
               </h3>
               <ul className="tl-global-search__list">
                  {users.map((searchUser) => (
                     <li key={searchUser.id ?? searchUser.username}>
                        <Link
                           to={`/user/${searchUser.username}`}
                           className="tl-global-search__result"
                           onClick={onNavigate}
                        >
                           <span className="tl-global-search__avatar" aria-hidden="true">
                              {searchUser.avatar_url ? (
                                 <img src={searchUser.avatar_url} alt="" />
                              ) : (
                                 <Icons name="user" size={14} />
                              )}
                           </span>
                           <span className="tl-global-search__result-copy">
                              <span className="tl-global-search__result-title">@{searchUser.username}</span>
                              <span className="tl-global-search__result-subtitle">
                                 {searchUser.bio || "TruthLens member"}
                              </span>
                           </span>
                           <span className="tl-global-search__user-signals">
                              <span className="tl-global-search__trust">
                                 Trust {Number(searchUser.trust_score || 0).toFixed(1)}
                              </span>
                              {isModeratorRole(searchUser.role) && (
                                 <span className="tl-global-search__platform-role" aria-label="Platform moderator">
                                    MOD
                                 </span>
                              )}
                           </span>
                        </Link>
                     </li>
                  ))}
               </ul>
            </section>
         )}

         {!loading && !error && threads.length > 0 && (
            <section className="tl-global-search__section" aria-labelledby={`${idPrefix}-threads-title`}>
               <h3 id={`${idPrefix}-threads-title`} className="tl-global-search__section-title">
                  Threads
               </h3>
               <ul className="tl-global-search__list">
                  {threads.map((thread) => (
                     <li key={thread.id}>
                        <Link
                           to={`/thread/detail/${thread.id}`}
                           className="tl-global-search__result"
                           onClick={onNavigate}
                        >
                           <span className="tl-global-search__thread-icon" aria-hidden="true">
                              <Icons name="file-text" size={14} />
                           </span>
                           <span className="tl-global-search__result-copy">
                              <span className="tl-global-search__result-title">{getThreadTitle(thread)}</span>
                              <span className="tl-global-search__result-subtitle">{getThreadSubtitle(thread)}</span>
                           </span>
                        </Link>
                     </li>
                  ))}
               </ul>
            </section>
         )}

         {!loading && !error && hasResults && query && (
            <Link
               to={`/community?q=${encodeURIComponent(query)}`}
               className="tl-global-search__community-link"
               onClick={onNavigate}
            >
               View matching threads in Community
            </Link>
         )}
      </section>
   );
}

function GlobalSearch() {
   const { authFetch } = useAuth();
   const navigate = useNavigate();
   const [searchInput, setSearchInput] = useState("");
   const [debouncedSearch, setDebouncedSearch] = useState("");
   const [desktopResultsOpen, setDesktopResultsOpen] = useState(false);
   const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
   const [searchLoading, setSearchLoading] = useState(false);
   const [searchError, setSearchError] = useState("");
   const [searchUsers, setSearchUsers] = useState([]);
   const [searchThreads, setSearchThreads] = useState([]);
   const desktopContainerRef = useRef(null);
   const desktopInputRef = useRef(null);
   const mobileTriggerRef = useRef(null);
   const mobileDialogRef = useRef(null);
   const mobileInputRef = useRef(null);
   const searchRequestIdRef = useRef(0);
   const returnFocusOnCloseRef = useRef(false);

   const clearSearch = useCallback(() => {
      searchRequestIdRef.current += 1;
      setSearchInput("");
      setDebouncedSearch("");
      setDesktopResultsOpen(false);
      setSearchLoading(false);
      setSearchError("");
      setSearchUsers([]);
      setSearchThreads([]);
   }, []);

   const closeMobileSearch = useCallback(
      ({ reset = true, returnFocus = true } = {}) => {
         returnFocusOnCloseRef.current = returnFocus;
         if (reset) clearSearch();
         setMobileSearchOpen(false);
      },
      [clearSearch],
   );

   useEffect(() => {
      const timeoutId = window.setTimeout(() => {
         setDebouncedSearch(searchInput);
      }, 250);

      return () => window.clearTimeout(timeoutId);
   }, [searchInput]);

   useEffect(() => {
      const query = debouncedSearch.trim();
      if (!query) return undefined;

      const requestId = searchRequestIdRef.current + 1;
      searchRequestIdRef.current = requestId;
      let effectIsCurrent = true;
      const encodedQuery = encodeURIComponent(query);
      const threadSearchUrl = `${THREADS_ENDPOINT}?search=${encodedQuery}`;
      const userSearchUrl = `${USERS_SEARCH_ENDPOINT}?search=${encodedQuery}&limit=6`;

      Promise.all([authFetch(threadSearchUrl, { method: "GET" }), authFetch(userSearchUrl, { method: "GET" })])
         .then(([threadData, userData]) => {
            if (!effectIsCurrent || requestId !== searchRequestIdRef.current) return;

            setSearchThreads(normalizeResults(threadData).slice(0, 6));
            setSearchUsers(normalizeResults(userData).slice(0, 6));
            setSearchError("");
         })
         .catch(() => {
            if (!effectIsCurrent || requestId !== searchRequestIdRef.current) return;

            setSearchThreads([]);
            setSearchUsers([]);
            setSearchError("We couldn’t load search results. Try again.");
         })
         .finally(() => {
            if (effectIsCurrent && requestId === searchRequestIdRef.current) {
               setSearchLoading(false);
            }
         });

      return () => {
         effectIsCurrent = false;
      };
   }, [authFetch, debouncedSearch]);

   useEffect(() => {
      if (!desktopResultsOpen) return undefined;

      function handleOutsideInteraction(event) {
         if (desktopContainerRef.current && !desktopContainerRef.current.contains(event.target)) {
            setDesktopResultsOpen(false);
         }
      }

      document.addEventListener("pointerdown", handleOutsideInteraction);
      return () => document.removeEventListener("pointerdown", handleOutsideInteraction);
   }, [desktopResultsOpen]);

   useEffect(() => {
      if (!desktopResultsOpen || mobileSearchOpen) return undefined;

      function handleDesktopEscape(event) {
         if (event.key === "Escape") {
            setDesktopResultsOpen(false);
         }
      }

      document.addEventListener("keydown", handleDesktopEscape);
      return () => document.removeEventListener("keydown", handleDesktopEscape);
   }, [desktopResultsOpen, mobileSearchOpen]);

   useEffect(() => {
      if (!mobileSearchOpen) return undefined;

      const dialog = mobileDialogRef.current;
      const mobileTrigger = mobileTriggerRef.current;
      const bodyOverflow = document.body.style.overflow;
      const mobileMediaQuery = window.matchMedia("(max-width: 768px)");
      const backgroundElements = Array.from(
         document.querySelectorAll(".top-navbar, .app-shell__content, .mobile-bottom-bar"),
      );
      const inertState = backgroundElements.map((element) => [element, element.getAttribute("inert")]);
      const focusFrame = window.requestAnimationFrame(() => mobileInputRef.current?.focus());

      document.body.style.overflow = "hidden";
      backgroundElements.forEach((element) => element.setAttribute("inert", ""));

      function handleBreakpointChange(event) {
         if (!event.matches) {
            closeMobileSearch({ returnFocus: false });
         }
      }

      function handleModalKeydown(event) {
         if (event.key === "Escape") {
            event.preventDefault();
            closeMobileSearch();
            return;
         }

         if (event.key !== "Tab" || !dialog) return;

         const focusableElements = Array.from(dialog.querySelectorAll(FOCUSABLE_SELECTOR));
         if (focusableElements.length === 0) {
            event.preventDefault();
            dialog.focus();
            return;
         }

         const firstElement = focusableElements[0];
         const lastElement = focusableElements[focusableElements.length - 1];

         if (event.shiftKey && document.activeElement === firstElement) {
            event.preventDefault();
            lastElement.focus();
         } else if (!event.shiftKey && document.activeElement === lastElement) {
            event.preventDefault();
            firstElement.focus();
         } else if (!dialog.contains(document.activeElement)) {
            event.preventDefault();
            firstElement.focus();
         }
      }

      document.addEventListener("keydown", handleModalKeydown);
      mobileMediaQuery.addEventListener("change", handleBreakpointChange);

      return () => {
         window.cancelAnimationFrame(focusFrame);
         document.removeEventListener("keydown", handleModalKeydown);
         mobileMediaQuery.removeEventListener("change", handleBreakpointChange);
         document.body.style.overflow = bodyOverflow;
         inertState.forEach(([element, inertAttributeValue]) => {
            if (inertAttributeValue === null) {
               element.removeAttribute("inert");
            } else {
               element.setAttribute("inert", inertAttributeValue);
            }
         });

         if (returnFocusOnCloseRef.current) {
            window.requestAnimationFrame(() => mobileTrigger?.focus());
         }
         returnFocusOnCloseRef.current = false;
      };
   }, [closeMobileSearch, mobileSearchOpen]);

   const handleSearchInputChange = (event, openDesktopResults) => {
      const value = event.target.value;
      const hasQuery = value.trim().length > 0;

      searchRequestIdRef.current += 1;
      setSearchInput(value);
      setSearchError("");

      if (hasQuery) {
         setSearchLoading(true);
         setDesktopResultsOpen(openDesktopResults);
      } else {
         setDebouncedSearch("");
         setDesktopResultsOpen(false);
         setSearchLoading(false);
         setSearchUsers([]);
         setSearchThreads([]);
      }
   };

   const handleSearchSubmit = (event) => {
      event.preventDefault();
      const query = searchInput.trim();
      if (!query) return;

      returnFocusOnCloseRef.current = false;
      setMobileSearchOpen(false);
      clearSearch();
      navigate(`/community?q=${encodeURIComponent(query)}`);
   };

   const handleResultNavigation = () => {
      returnFocusOnCloseRef.current = false;
      setMobileSearchOpen(false);
      clearSearch();
   };

   const handleDesktopClear = () => {
      clearSearch();
      window.requestAnimationFrame(() => desktopInputRef.current?.focus());
   };

   const handleMobileClear = () => {
      clearSearch();
      window.requestAnimationFrame(() => mobileInputRef.current?.focus());
   };

   const openMobileSearch = () => {
      returnFocusOnCloseRef.current = true;
      setDesktopResultsOpen(false);
      setMobileSearchOpen(true);
   };

   const query = debouncedSearch.trim();
   const showDesktopResults = desktopResultsOpen && searchInput.trim().length > 0;

   return (
      <div className="tl-global-search">
         <div className="tl-global-search__desktop" ref={desktopContainerRef}>
            <form
               className="tl-global-search__form"
               role="search"
               aria-label="Global search"
               onSubmit={handleSearchSubmit}
            >
               <Input
                  ref={desktopInputRef}
                  type="search"
                  density="compact"
                  surface="subtle"
                  className="tl-global-search__input"
                  placeholder="Search people and claims..."
                  value={searchInput}
                  onFocus={() => {
                     if (searchInput.trim()) setDesktopResultsOpen(true);
                  }}
                  onChange={(event) => handleSearchInputChange(event, true)}
                  aria-label="Search people and claims"
                  leadingIcon={<Icons name="search" size={16} />}
                  trailingAdornment={
                     searchInput ? (
                        <IconButton
                           variant="ghost"
                           density="compact"
                           className="tl-global-search__clear"
                           icon={<Icons name="x" size={14} />}
                           aria-label="Clear search"
                           onClick={handleDesktopClear}
                        />
                     ) : null
                  }
               />
            </form>

            {showDesktopResults && (
               <div className="tl-global-search__disclosure">
                  <SearchResults
                     idPrefix="tl-global-search-desktop"
                     query={query}
                     loading={searchLoading}
                     error={searchError}
                     users={searchUsers}
                     threads={searchThreads}
                     onNavigate={handleResultNavigation}
                  />
               </div>
            )}
         </div>

         <IconButton
            ref={mobileTriggerRef}
            variant="ghost"
            density="comfortable"
            className="tl-global-search__mobile-trigger"
            icon={<Icons name="search" size={20} />}
            aria-label="Search"
            aria-haspopup="dialog"
            aria-expanded={mobileSearchOpen}
            aria-controls={MOBILE_DIALOG_ID}
            onClick={openMobileSearch}
         />

         {mobileSearchOpen &&
            createPortal(
               <div
                  ref={mobileDialogRef}
                  id={MOBILE_DIALOG_ID}
                  className="tl-global-search__overlay"
                  role="dialog"
                  aria-modal="true"
                  aria-label="Global search"
                  tabIndex={-1}
               >
                  <div className="tl-global-search__mobile-header">
                     <form
                        className="tl-global-search__mobile-form"
                        role="search"
                        aria-label="Global search"
                        onSubmit={handleSearchSubmit}
                     >
                        <Input
                           ref={mobileInputRef}
                           type="search"
                           density="comfortable"
                           surface="surface"
                           className="tl-global-search__mobile-input"
                           placeholder="Search people and claims..."
                           value={searchInput}
                           onChange={(event) => handleSearchInputChange(event, false)}
                           aria-label="Search people and claims"
                           leadingIcon={<Icons name="search" size={18} />}
                           trailingAdornment={
                              searchInput ? (
                                 <IconButton
                                    variant="ghost"
                                    density="compact"
                                    className="tl-global-search__clear"
                                    icon={<Icons name="x" size={16} />}
                                    aria-label="Clear search"
                                    onClick={handleMobileClear}
                                 />
                              ) : null
                           }
                        />
                     </form>
                     <Button
                        variant="ghost"
                        density="comfortable"
                        className="tl-global-search__cancel"
                        onClick={() => closeMobileSearch()}
                     >
                        Cancel
                     </Button>
                  </div>

                  <div className="tl-global-search__mobile-results">
                     <SearchResults
                        idPrefix="tl-global-search-mobile"
                        query={query}
                        loading={searchLoading}
                        error={searchError}
                        users={searchUsers}
                        threads={searchThreads}
                        onNavigate={handleResultNavigation}
                     />
                  </div>
               </div>,
               document.body,
            )}
      </div>
   );
}

export default GlobalSearch;
