import { useCallback, useEffect, useMemo, useState } from "react";

import ThemeContext from "../context/ThemeContext";
import {
   THEME_STORAGE_KEY,
   normalizeThemePreference,
   readStoredThemePreference,
   resolveThemePreference,
   writeStoredThemePreference,
} from "../utils/themePreference";

const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

function readSystemPreference() {
   return (
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia(DARK_MEDIA_QUERY).matches
   );
}

export function ThemeProvider({ children }) {
   const [themePreference, setThemePreferenceState] = useState(() => readStoredThemePreference());
   const [systemPrefersDark, setSystemPrefersDark] = useState(() => readSystemPreference());

   const resolvedTheme = resolveThemePreference(themePreference, systemPrefersDark);

   const setThemePreference = useCallback((nextPreference) => {
      const normalized = normalizeThemePreference(nextPreference);
      setThemePreferenceState(normalized);
      writeStoredThemePreference(normalized);
   }, []);

   const toggleDarkMode = useCallback(() => {
      setThemePreference(resolvedTheme === "dark" ? "light" : "dark");
   }, [resolvedTheme, setThemePreference]);

   useEffect(() => {
      const mediaQuery = window.matchMedia?.(DARK_MEDIA_QUERY);
      if (!mediaQuery) return undefined;

      const handleChange = (event) => setSystemPrefersDark(event.matches);

      if (typeof mediaQuery.addEventListener === "function") {
         mediaQuery.addEventListener("change", handleChange);
         return () => mediaQuery.removeEventListener("change", handleChange);
      }

      mediaQuery.addListener?.(handleChange);
      return () => mediaQuery.removeListener?.(handleChange);
   }, []);

   useEffect(() => {
      document.documentElement.dataset.themePreference = themePreference;
      document.documentElement.dataset.theme = resolvedTheme;
      document.documentElement.style.colorScheme = resolvedTheme;
   }, [resolvedTheme, themePreference]);

   useEffect(() => {
      const handleStorage = (event) => {
         if (event.key !== THEME_STORAGE_KEY) return;
         setThemePreferenceState(normalizeThemePreference(event.newValue));
      };

      window.addEventListener("storage", handleStorage);
      return () => window.removeEventListener("storage", handleStorage);
   }, []);

   const value = useMemo(
      () => ({
         themePreference,
         resolvedTheme,
         systemPrefersDark,
         setThemePreference,
         toggleDarkMode,
      }),
      [resolvedTheme, setThemePreference, systemPrefersDark, themePreference, toggleDarkMode],
   );

   return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export default ThemeProvider;
