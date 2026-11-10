export const THEME_STORAGE_KEY = "truthlens.theme";
export const THEME_PREFERENCES = Object.freeze(["system", "light", "dark"]);

export function isThemePreference(value) {
   return THEME_PREFERENCES.includes(value);
}

export function normalizeThemePreference(value) {
   return isThemePreference(value) ? value : "light";
}

export function resolveThemePreference(preference, systemPrefersDark = false) {
   const normalized = normalizeThemePreference(preference);
   if (normalized === "system") return systemPrefersDark ? "dark" : "light";
   return normalized;
}

function getBrowserStorage() {
   try {
      return typeof globalThis === "undefined" ? null : globalThis.localStorage;
   } catch {
      return null;
   }
}

export function readStoredThemePreference(storage) {
   const target = arguments.length ? storage : getBrowserStorage();
   try {
      if (!target?.getItem) return "light";
      return normalizeThemePreference(target.getItem(THEME_STORAGE_KEY));
   } catch {
      return "light";
   }
}

export function writeStoredThemePreference(preference, storage) {
   const normalized = normalizeThemePreference(preference);
   const target = arguments.length > 1 ? storage : getBrowserStorage();
   try {
      target?.setItem?.(THEME_STORAGE_KEY, normalized);
      return Boolean(target?.setItem);
   } catch {
      return false;
   }
}
