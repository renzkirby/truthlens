import Icons from "../Icons.jsx";
import "./EvidenceSourcePreview.css";

const SAFETY_META = {
   NO_KNOWN_THREATS: {
      label: "No known threats detected",
      tone: "clear",
      icon: "shield-check",
      title: "Reputation check only. This does not guarantee that the website is safe.",
   },
   CHECK_UNAVAILABLE: {
      label: "Safety check unavailable",
      tone: "unavailable",
      icon: "alert-circle",
      title: "TruthLens could not complete the external reputation check.",
   },
   KNOWN_THREAT: {
      label: "Security threat detected",
      tone: "threat",
      icon: "alert-triangle",
      title: "The external reputation provider reported a known threat.",
   },
   NOT_CHECKED: {
      label: "Safety not checked",
      tone: "unchecked",
      icon: "info",
      title: "No persisted reputation result is available for this source.",
   },
};

function safeHttpUrl(value) {
   if (!value) return null;
   try {
      const parsed = new URL(String(value).trim());
      if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
         return null;
      }
      return parsed.href;
   } catch {
      return null;
   }
}

function sourceIdentity(value) {
   const safeUrl = safeHttpUrl(value);
   if (!safeUrl) {
      return { host: "", path: "" };
   }
   const parsed = new URL(safeUrl);
   const path = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "";
   return {
      host: parsed.hostname.replace(/^www\./, ""),
      path,
   };
}

export default function EvidenceSourcePreview({
   url,
   safety,
   preview,
   variant = "community",
}) {
   if (!url) return null;

   const safeUrl = safeHttpUrl(url);
   const identity = sourceIdentity(url);
   const safetyStatus = String(safety?.status || "NOT_CHECKED").toUpperCase();
   const previewStatus = String(preview?.status || "NOT_REQUESTED").toUpperCase();
   const networkPolicyBlocked =
      previewStatus === "BLOCKED" && safetyStatus !== "KNOWN_THREAT";
   const safetyMeta = networkPolicyBlocked
      ? {
           label: "URL blocked by network safety policy",
           tone: "threat",
           icon: "alert-triangle",
           title: "TruthLens blocked this destination because it did not meet public-network URL requirements.",
        }
      : SAFETY_META[safetyStatus] || SAFETY_META.NOT_CHECKED;
   const ready = previewStatus === "READY";
   const pending = previewStatus === "PENDING";
   const blocked = networkPolicyBlocked || previewStatus === "BLOCKED" || safetyStatus === "KNOWN_THREAT";
   const networkCheckPending = previewStatus === "PENDING";
   const openAllowed = Boolean(safeUrl) && !blocked && !networkCheckPending;
   const previewTitle = ready && preview?.title ? preview.title : identity.host || String(url);
   const previewDescription = ready && preview?.description ? preview.description : "";
   const siteName = ready && preview?.site_name ? preview.site_name : identity.host;
   const path = identity.path.length > 70 ? `${identity.path.slice(0, 70)}…` : identity.path;

   return (
      <div className={`evidence-source-preview evidence-source-preview--${variant}`}>
         <div className="evidence-source-preview__header">
            <span className="evidence-source-preview__identity">
               <span className="evidence-source-preview__mark" aria-hidden="true">
                  {(identity.host?.[0] || "?").toUpperCase()}
               </span>
               Evidence source
            </span>
            <span
               className={`evidence-source-preview__safety evidence-source-preview__safety--${safetyMeta.tone}`}
               title={safetyMeta.title}
            >
               <Icons name={safetyMeta.icon} size={13} aria-hidden="true" />
               {safetyMeta.label}
            </span>
         </div>

         <div className="evidence-source-preview__body">
            <strong>{previewTitle}</strong>
            {ready && siteName && siteName !== previewTitle && (
               <span className="evidence-source-preview__site">{siteName}</span>
            )}
            {previewDescription && (
               <p>{previewDescription}</p>
            )}
            {!ready && path && (
               <span className="evidence-source-preview__path">{path}</span>
            )}
            {pending && (
               <span className="evidence-source-preview__state">
                  Checking source details and network safety…
               </span>
            )}
            {previewStatus === "UNAVAILABLE" && (
               <span className="evidence-source-preview__state">Preview unavailable. The source link is still preserved.</span>
            )}
            {blocked && (
               <span className="evidence-source-preview__state evidence-source-preview__state--threat">
                  Preview and direct opening are disabled for this source.
               </span>
            )}
         </div>

         {openAllowed ? (
            <a
               className="evidence-source-preview__open"
               href={safeUrl}
               target="_blank"
               rel="noopener noreferrer"
            >
               Open source
               <Icons name="external-link" size={14} aria-hidden="true" />
            </a>
         ) : !safeUrl ? (
            <span className="evidence-source-preview__state evidence-source-preview__state--invalid">
               This URL cannot be opened because it is not a supported HTTP(S) address.
            </span>
         ) : networkCheckPending ? (
            <span className="evidence-source-preview__state">
               Opening is available after the network safety check completes.
            </span>
         ) : null}
      </div>
   );
}
