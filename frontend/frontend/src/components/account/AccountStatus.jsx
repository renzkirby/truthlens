import "./AccountStatus.css";

const ACCOUNT_STATUS_TONES = new Set(["neutral", "info", "success", "warning", "critical"]);

function AccountStatus({
   tone = "neutral",
   icon,
   eyebrow,
   title,
   description,
   actions,
   live,
   busy = false,
   loading = false,
   className = "",
}) {
   const resolvedTone = ACCOUNT_STATUS_TONES.has(tone) ? tone : "neutral";
   const isBusy = loading || busy;
   const classes = ["account-status", `account-status--${resolvedTone}`, className]
      .filter(Boolean)
      .join(" ");

   return (
      <div className={classes} aria-live={live} aria-busy={isBusy ? "true" : undefined}>
         {loading || icon ? (
            <div className="account-status__icon" aria-hidden="true">
               {loading ? <span className="account-status__spinner" aria-hidden="true" /> : icon}
            </div>
         ) : null}

         {eyebrow ? <p className="account-status__eyebrow">{eyebrow}</p> : null}

         <h1 className="account-status__title">{title}</h1>

         {description ? <p className="account-status__description">{description}</p> : null}

         {actions ? <div className="account-status__actions">{actions}</div> : null}
      </div>
   );
}

export default AccountStatus;
