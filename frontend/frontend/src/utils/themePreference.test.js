import assert from "node:assert/strict";
import test from "node:test";

import {
   THEME_STORAGE_KEY,
   isThemePreference,
   normalizeThemePreference,
   readStoredThemePreference,
   resolveThemePreference,
   writeStoredThemePreference,
} from "./themePreference.js";

function createStorage(initial = {}) {
   const values = new Map(Object.entries(initial));
   return {
      getItem(key) {
         return values.has(key) ? values.get(key) : null;
      },
      setItem(key, value) {
         values.set(key, String(value));
      },
      value(key) {
         return values.get(key);
      },
   };
}

test("theme preferences accept only system, light, and dark", () => {
   assert.equal(isThemePreference("system"), true);
   assert.equal(isThemePreference("light"), true);
   assert.equal(isThemePreference("dark"), true);
   assert.equal(isThemePreference("sepia"), false);
   assert.equal(normalizeThemePreference("sepia"), "light");
});

test("system resolves from the device preference while fixed themes remain fixed", () => {
   assert.equal(resolveThemePreference("system", true), "dark");
   assert.equal(resolveThemePreference("system", false), "light");
   assert.equal(resolveThemePreference("dark", false), "dark");
   assert.equal(resolveThemePreference("light", true), "light");
});

test("stored theme defaults safely to light and rejects invalid values", () => {
   assert.equal(readStoredThemePreference(createStorage()), "light");
   assert.equal(readStoredThemePreference(createStorage({ [THEME_STORAGE_KEY]: "unknown" })), "light");
   assert.equal(readStoredThemePreference(createStorage({ [THEME_STORAGE_KEY]: "dark" })), "dark");
});

test("missing storage safely falls back without throwing", () => {
   assert.equal(readStoredThemePreference(undefined), "light");
   assert.equal(writeStoredThemePreference("dark", undefined), false);
});

test("storage failures do not break theme initialization", () => {
   const throwingStorage = {
      getItem() {
         throw new Error("blocked");
      },
      setItem() {
         throw new Error("blocked");
      },
   };

   assert.equal(readStoredThemePreference(throwingStorage), "light");
   assert.equal(writeStoredThemePreference("dark", throwingStorage), false);
});

test("writing a theme normalizes the persisted preference", () => {
   const storage = createStorage();
   assert.equal(writeStoredThemePreference("dark", storage), true);
   assert.equal(storage.value(THEME_STORAGE_KEY), "dark");

   assert.equal(writeStoredThemePreference("unsupported", storage), true);
   assert.equal(storage.value(THEME_STORAGE_KEY), "light");
});
