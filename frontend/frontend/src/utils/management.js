export function canAccessManagementConsole(user) {
   return user?.management_console?.can_access === true;
}

export function formatManagementDate(value, { dateOnly = false } = {}) {
   if (!value) return "Not recorded";

   const date = new Date(value);
   if (Number.isNaN(date.getTime())) return "Not recorded";

   return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      ...(dateOnly ? {} : { timeStyle: "short" }),
   }).format(date);
}

export function managementStatusTone(status) {
   if (["ACTIVE", "VERIFIED", "ACCEPTED"].includes(status)) return "success";
   if (["PENDING", "UNVERIFIED"].includes(status)) return "warning";
   if (["SUSPENDED", "REJECTED", "CANCELLED", "EXPIRED"].includes(status)) return "critical";
   return "neutral";
}
