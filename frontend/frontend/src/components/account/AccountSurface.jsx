import "./AccountSurface.css";

function AccountSurface({ className = "", children }) {
   const classes = ["account-surface", className].filter(Boolean).join(" ");

   return <div className={classes}>{children}</div>;
}

export default AccountSurface;
