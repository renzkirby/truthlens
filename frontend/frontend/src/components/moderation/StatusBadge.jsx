function StatusBadge({ status }) {
   const normalized = status || "OPEN";
   const stateClass = normalized === "CLOSED" ? "closed" : "open";

   return <span className={`mod-status-badge ${stateClass}`}>{normalized}</span>;
}

export default StatusBadge;
