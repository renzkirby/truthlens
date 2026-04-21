// App.jsx
import { useState, useEffect } from "react";
import "./App.css";
import truthlensIcon from "./assets/truthlens-icon.png";
import NavigationBar from "./components/NavigationBar";
import FileUpload from "./pages/FileUpload";
import SnippingTool from "./pages/SnippingTool";
import UrlUpload from "./pages/UrlUpload";
import DetectDeepfake from "./pages/DetectDeepfake";
import { AUTH_STORAGE_KEYS, getAuthSession } from "./modules/auth.js";
import { state } from "./modules/state.js";

const GUEST_SCANS_STORAGE_KEY = "guest_scans";
const GUEST_SCANS_CAP = 3;
const GUEST_SCAN_SYNC_STATUS_STORAGE_KEY = "guest_scan_sync_status";
const WEB_APP_BASE_URL = state.WEB_APP_ORIGINS?.[0] || "http://localhost:5174";
const GUEST_SYNC_STATUS_AUTO_DISMISS_MS = 7000;

function normalizeGuestScans(rawGuestScans) {
   if (!Array.isArray(rawGuestScans)) {
      return [];
   }

   return rawGuestScans
      .filter((scan) => scan && typeof scan === "object")
      .sort((left, right) => {
         const leftTime = new Date(left.scanned_at || 0).getTime();
         const rightTime = new Date(right.scanned_at || 0).getTime();
         return rightTime - leftTime;
      });
}

function normalizeGuestSyncStatus(rawStatus) {
   if (!rawStatus || typeof rawStatus !== "object") {
      return null;
   }

   const status = String(rawStatus.status || "").toLowerCase();
   if (!status) {
      return null;
   }

   const syncedCount = Number(rawStatus.synced_count ?? rawStatus.syncedCount ?? 0);

   return {
      status,
      syncedCount: Number.isFinite(syncedCount) ? Math.max(0, syncedCount) : 0,
      updatedAt: rawStatus.updated_at || rawStatus.updatedAt || null,
      error: typeof rawStatus.error === "string" ? rawStatus.error : null,
   };
}

function formatGuestTimestamp(timestamp) {
   if (!timestamp) {
      return "Just now";
   }

   const parsed = new Date(timestamp);
   if (Number.isNaN(parsed.getTime())) {
      return "Just now";
   }

   return parsed.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
   });
}

function getVerdictToneClass(verdict) {
   switch (String(verdict || "").toUpperCase()) {
      case "FACT":
         return "fact";
      case "FAKE":
         return "fake";
      case "MISLEADING":
         return "misleading";
      case "SATIRE":
         return "satire";
      default:
         return "unverified";
   }
}

function App() {
   const [isSnipping, setIsSnipping] = useState(false);
   const [activeLink, setActiveLink] = useState("snipping");
   const [checkDeepfake, setCheckDeepfake] = useState(false);
   const [isGuestMode, setIsGuestMode] = useState(true);
   const [ghostScans, setGhostScans] = useState([]);
   const [loggedInUsername, setLoggedInUsername] = useState(null);
   const [guestSyncStatus, setGuestSyncStatus] = useState(null);

   const dismissGuestSyncStatus = () => {
      setGuestSyncStatus(null);

      if (typeof chrome !== "undefined" && chrome.storage?.local) {
         chrome.storage.local.remove([GUEST_SCAN_SYNC_STATUS_STORAGE_KEY]);
      }
   };

   // load checkDeepfake choice from switch
   useEffect(() => {
      if (typeof chrome !== "undefined" && chrome.storage) {
         chrome.storage.local.get(["checkDeepfake"], (result) => {
            if (result.checkDeepfake !== undefined) {
               setCheckDeepfake(result.checkDeepfake);
            }
         });
      }
   }, []);

   useEffect(() => {
      if (typeof chrome === "undefined" || !chrome.storage?.local) {
         return;
      }

      let isDisposed = false;

      const requestGuestSyncRetryIfNeeded = () => {
         if (
            typeof chrome === "undefined" ||
            !chrome.runtime?.sendMessage ||
            !chrome.storage?.local
         ) {
            return;
         }

         chrome.storage.local.get([GUEST_SCANS_STORAGE_KEY], (result) => {
            if (isDisposed) {
               return;
            }

            const pendingGuestScans = Array.isArray(result?.[GUEST_SCANS_STORAGE_KEY])
               ? result[GUEST_SCANS_STORAGE_KEY]
               : [];
            if (!pendingGuestScans.length) {
               return;
            }

            chrome.runtime.sendMessage({ type: "SYNC_GUEST_SCANS_NOW" }, () => {
               // No-op: status updates are reflected through storage listeners.
            });
         });
      };

      const requestAuthContext = () =>
         new Promise((resolve) => {
            if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) {
               resolve(null);
               return;
            }

            chrome.runtime.sendMessage({ type: "GET_AUTH_CONTEXT" }, (response) => {
               if (chrome.runtime.lastError) {
                  resolve(null);
                  return;
               }
               resolve(response || null);
            });
         });

      const hydratePopupSession = async () => {
         const session = await getAuthSession();
         if (isDisposed) {
            return;
         }

         const guestMode = !session?.accessToken;
         setIsGuestMode(guestMode);

         if (!guestMode) {
            setGhostScans([]);

            const authContext = await requestAuthContext();
            if (isDisposed) {
               return;
            }

            const normalizedUsername =
               authContext?.accepted && typeof authContext.username === "string"
                  ? authContext.username.trim()
                  : "";
            setLoggedInUsername(normalizedUsername || null);

            requestGuestSyncRetryIfNeeded();

            chrome.storage.local.get([GUEST_SCAN_SYNC_STATUS_STORAGE_KEY], (result) => {
               if (isDisposed) {
                  return;
               }

               setGuestSyncStatus(
                  normalizeGuestSyncStatus(result?.[GUEST_SCAN_SYNC_STATUS_STORAGE_KEY]),
               );
            });
            return;
         }

         setLoggedInUsername(null);
         setGuestSyncStatus(null);

         chrome.storage.local.get([GUEST_SCANS_STORAGE_KEY], (result) => {
            if (isDisposed) {
               return;
            }
            setGhostScans(normalizeGuestScans(result?.[GUEST_SCANS_STORAGE_KEY]));
         });
      };

      hydratePopupSession();

      const handleStorageChange = (changes, areaName) => {
         if (areaName !== "local") {
            return;
         }

         if (changes[AUTH_STORAGE_KEYS.ACCESS_TOKEN] || changes[AUTH_STORAGE_KEYS.REFRESH_TOKEN]) {
            hydratePopupSession();
            return;
         }

         if (changes[GUEST_SCANS_STORAGE_KEY]) {
            setGhostScans(normalizeGuestScans(changes[GUEST_SCANS_STORAGE_KEY].newValue));
         }

         if (changes[GUEST_SCAN_SYNC_STATUS_STORAGE_KEY]) {
            setGuestSyncStatus(
               normalizeGuestSyncStatus(changes[GUEST_SCAN_SYNC_STATUS_STORAGE_KEY].newValue),
            );
         }
      };

      chrome.storage.onChanged.addListener(handleStorageChange);

      return () => {
         isDisposed = true;
         chrome.storage.onChanged.removeListener(handleStorageChange);
      };
   }, []);

   useEffect(() => {
      if (isGuestMode || !guestSyncStatus) {
         return;
      }

      const dismissTimer = window.setTimeout(() => {
         dismissGuestSyncStatus();
      }, GUEST_SYNC_STATUS_AUTO_DISMISS_MS);

      return () => {
         window.clearTimeout(dismissTimer);
      };
   }, [guestSyncStatus?.updatedAt, guestSyncStatus?.status, isGuestMode]);

   const handleOpenCommunityPlatform = () => {
      const communityUrl = `${WEB_APP_BASE_URL}/community`;
      if (typeof chrome !== "undefined" && chrome.tabs?.create) {
         chrome.tabs.create({ url: communityUrl });
         return;
      }

      window.open(communityUrl, "_blank", "noopener,noreferrer");
   };

   const handleToggleDeepfake = (checked) => {
      setCheckDeepfake(checked);
      if (typeof chrome !== "undefined" && chrome.storage) {
         chrome.storage.local.set({ checkDeepfake: checked });
      }
   };

   const handleSnipClick = async () => {
      setIsSnipping(true);
      if (typeof chrome === "undefined" || !chrome.tabs) return setIsSnipping(false);
      try {
         const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
         chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_SNIPPING", intent: "factcheck" }, () => {
            if (chrome.runtime.lastError) setIsSnipping(false);
         });
         // Close the extension popup so we can see the CropStudio on the page
         window.close();
      } catch (error) {
         setIsSnipping(false);
      }
   };

   const handleDeepfakeSnipClick = async () => {
      setIsSnipping(true);
      if (typeof chrome === "undefined" || !chrome.tabs) return setIsSnipping(false);
      try {
         const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
         chrome.tabs.sendMessage(tab.id, { type: "ACTIVATE_SNIPPING", intent: "deepfake" }, () => {
            if (chrome.runtime.lastError) setIsSnipping(false);
         });
         // Close the extension popup so we can see the CropStudio on the page
         window.close();
      } catch (error) {
         setIsSnipping(false);
      }
   };

   const renderContent = () => {
      switch (activeLink) {
         case "snipping":
            return (
               <SnippingTool
                  handleSnipClick={handleSnipClick}
                  isSnipping={isSnipping}
               />
            );
         case "detect-deepfake":
            return (
               <DetectDeepfake
                  handleDeepfakeSnipClick={handleDeepfakeSnipClick}
                  isSnipping={isSnipping}
               />
            );
         case "file-upload":
            return <FileUpload />;
         case "url-upload":
            return <UrlUpload />;
         default:
            return null;
      }
   };

   return (
      <div className="card">
         <div className="header-row">
            <div className="logo-container">
               <div className="logo-box">
                  <img
                     src={truthlensIcon}
                     alt="TruthLens"
                     style={{ width: "25px", height: "25px", objectFit: "contain" }}
                  />
               </div>
               <h2>TruthLens</h2>
            </div>
            <span className="version-badge">v1.1</span>
         </div>

         <NavigationBar
            activeLink={activeLink}
            setActiveLink={setActiveLink}
         />

         <div className="content-area">{renderContent()}</div>

         {!isGuestMode &&
            guestSyncStatus?.status === "success" &&
            guestSyncStatus.syncedCount > 0 && (
               <section
                  className="guest-sync-status success"
                  role="status">
                  <div className="guest-sync-status-headline">
                     <strong>
                        Synced {guestSyncStatus.syncedCount} ghost scan
                        {guestSyncStatus.syncedCount === 1 ? "" : "s"} after login.
                     </strong>
                     <button
                        type="button"
                        className="guest-sync-dismiss-btn"
                        onClick={dismissGuestSyncStatus}
                        aria-label="Dismiss sync status">
                        ×
                     </button>
                  </div>
                  <span>
                     Added to your private library
                     {guestSyncStatus.updatedAt
                        ? ` • ${formatGuestTimestamp(guestSyncStatus.updatedAt)}`
                        : "."}
                  </span>
               </section>
            )}

         {!isGuestMode && guestSyncStatus?.status === "error" && (
            <section
               className="guest-sync-status error"
               role="status">
               <div className="guest-sync-status-headline">
                  <strong>We could not sync your unsaved scans automatically.</strong>
                  <button
                     type="button"
                     className="guest-sync-dismiss-btn"
                     onClick={dismissGuestSyncStatus}
                     aria-label="Dismiss sync status">
                     ×
                  </button>
               </div>
               <span>
                  {guestSyncStatus.error ||
                     "Your local ghost scans remain on this device and will retry on your next login."}
               </span>
            </section>
         )}

         {isGuestMode && (
            <section className="guest-mode-panel">
               <div className="guest-mode-header">
                  <span className="guest-mode-badge">Guest Mode</span>
                  <span className="guest-mode-cap">
                     {ghostScans.length}/{GUEST_SCANS_CAP} cached locally
                  </span>
               </div>

               <div className="guest-history-list">
                  {ghostScans.length === 0 ? (
                     <p className="guest-history-empty">
                        No ghost scans yet. Run a scan and your latest 3 verdicts will appear here.
                     </p>
                  ) : (
                     ghostScans.map((scan, index) => {
                        const verdict = String(scan?.verdict || "UNVERIFIED").toUpperCase();
                        const confidenceScore = Number(scan?.confidence_score || 0);

                        return (
                           <article
                              key={`${scan?.scanned_at || "ghost-scan"}-${index}`}
                              className="guest-history-item">
                              <div className="guest-history-item-top">
                                 <span className="guest-history-item-type">
                                    {scan?.scan_type || "SCAN"}
                                 </span>
                                 <span
                                    className={`guest-history-verdict ${getVerdictToneClass(verdict)}`}>
                                    {verdict}
                                 </span>
                              </div>

                              <p className="guest-history-summary">
                                 {scan?.summary || "No summary available."}
                              </p>

                              <div className="guest-history-meta">
                                 <span>{confidenceScore}% confidence</span>
                                 <span>{formatGuestTimestamp(scan?.scanned_at)}</span>
                              </div>
                           </article>
                        );
                     })
                  )}
               </div>

               <div className="guest-upsell-cta">
                  <p>
                     You have unsaved scans. Log in or create a TruthLens account to save them to
                     your permanent Private Library and earn Trust Points!
                  </p>
                  <div className="guest-upsell-actions">
                     <a
                        href={`${WEB_APP_BASE_URL}/login`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="guest-upsell-link login">
                        Log In
                     </a>
                     <a
                        href={`${WEB_APP_BASE_URL}/register`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="guest-upsell-link register">
                        Create Account
                     </a>
                  </div>
               </div>
            </section>
         )}

         <div className="app-footer">
            <span className="footer-user">
               {isGuestMode ? (
                  "Browsing as guest"
               ) : loggedInUsername ? (
                  <>
                     Signed in as <strong>@{loggedInUsername}</strong>
                  </>
               ) : (
                  "Signed in to TruthLens"
               )}
            </span>
            <button
               type="button"
               className="footer-link footer-link-button"
               onClick={handleOpenCommunityPlatform}>
               Open Community Platform →
            </button>
         </div>
      </div>
   );
}

export default App;
