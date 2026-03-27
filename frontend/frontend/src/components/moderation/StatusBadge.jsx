function StatusBadge({ status }) {
   const normalized = status || "OPEN";
   const stateClass = normalized === "CLOSED" ? "closed" : "open";

   return (
      <div>
         <span className={`mod-status-badge ${stateClass}`}>{normalized}</span>
      </div>
   );
}

export default StatusBadge;
