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

export function readStoredThemePreference(storage = globalThis?.localStorage) {
   try {
      if (!storage?.getItem) return "light";
      return normalizeThemePreference(storage.getItem(THEME_STORAGE_KEY));
   } catch {
      return "light";
   }
}

export function writeStoredThemePreference(preference, storage = globalThis?.localStorage) {
   const normalized = normalizeThemePreference(preference);
   try {
      storage?.setItem?.(THEME_STORAGE_KEY, normalized);
      return true;
   } catch {
      return false;
   }
}
