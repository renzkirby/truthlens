import { useEffect } from "react";

import { useAuth } from "./useAuth";

const FULL_ACCESS = {
   status: "FULL_ACCESS",
   can_contribute: true,
   restriction_ends_at: null,
   active_enforcement_id: null,
   has_unseen_action: false,
};

export function useCommunityAccess() {
   const { user, refreshUser } = useAuth();
   const identityEligible = user?.community_identity?.can_participate !== false;
   const access = user?.community_identity?.community_access || FULL_ACCESS;
   const canContribute = identityEligible && access.can_contribute !== false;
   const canReport = identityEligible;
   const accessStatus = access.status || "FULL_ACCESS";
   const restrictionEndsAt = access.restriction_ends_at || null;
   const activeEnforcementId = access.active_enforcement_id || null;
   const hasUnseenAction = access.has_unseen_action === true;

   useEffect(() => {
      if (accessStatus !== "TEMPORARILY_RESTRICTED" || !restrictionEndsAt) {
         return undefined;
      }

      const end = new Date(restrictionEndsAt).getTime();
      if (!Number.isFinite(end)) return undefined;

      const delay = Math.max(1000, end - Date.now() + 2000);
      const timer = window.setTimeout(() => {
         refreshUser().catch(() => null);
      }, Math.min(delay, 2147483000));

      return () => window.clearTimeout(timer);
   }, [accessStatus, refreshUser, restrictionEndsAt]);

   return {
      identityEligible,
      canContribute,
      canReport,
      accessStatus,
      restrictionEndsAt,
      activeEnforcementId,
      hasUnseenAction,
      access,
   };
}

export function communityRestrictionSummary(accessStatus, restrictionEndsAt) {
   if (accessStatus === "TEMPORARILY_RESTRICTED") {
      if (!restrictionEndsAt) {
         return "Your Community contribution access is temporarily restricted.";
      }
      const date = new Date(restrictionEndsAt);
      if (Number.isNaN(date.getTime())) {
         return "Your Community contribution access is temporarily restricted.";
      }
      return `Your Community contribution access is restricted until ${date.toLocaleString()}.`;
   }
   if (accessStatus === "INDEFINITELY_RESTRICTED") {
      return "Your Community contribution access is indefinitely restricted.";
   }
   return "";
}
