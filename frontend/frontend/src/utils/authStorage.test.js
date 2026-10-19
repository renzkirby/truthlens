import assert from "node:assert/strict";
import test from "node:test";

import {
   applyAuthSnapshot,
   chooseFreshestAuthSnapshot,
   clearAuthTokens,
   getAuthSnapshot,
   shouldApplyAuthClear,
   storeAuthTokens,
   updateAuthTokens,
} from "./authStorage.js";

class MemoryStorage {
   constructor() {
      this.values = new Map();
   }

   getItem(key) {
      return this.values.has(key) ? this.values.get(key) : null;
   }

   setItem(key, value) {
      this.values.set(key, String(value));
   }

   removeItem(key) {
      this.values.delete(key);
   }

   clear() {
      this.values.clear();
   }
}

const resetStorage = () => {
   globalThis.localStorage = new MemoryStorage();
   globalThis.sessionStorage = new MemoryStorage();
};

test("non-remembered sessions remain session scoped", () => {
   resetStorage();

   storeAuthTokens("access-a", "refresh-a", false, { broadcast: false });

   assert.equal(sessionStorage.getItem("access"), "access-a");
   assert.equal(sessionStorage.getItem("refresh"), "refresh-a");
   assert.equal(localStorage.getItem("access"), null);
   assert.equal(getAuthSnapshot()?.rememberMe, false);
});

test("remembered sessions use shared persistent storage", () => {
   resetStorage();

   storeAuthTokens("access-a", "refresh-a", true, { broadcast: false });

   assert.equal(localStorage.getItem("access"), "access-a");
   assert.equal(localStorage.getItem("refresh"), "refresh-a");
   assert.equal(sessionStorage.getItem("access"), null);
   assert.equal(getAuthSnapshot()?.rememberMe, true);
});

test("applying a remote account switch clears the previous storage mode", () => {
   resetStorage();

   storeAuthTokens("remembered-access", "remembered-refresh", true, {
      broadcast: false,
   });

   applyAuthSnapshot(
      {
         access: "session-access",
         refresh: "session-refresh",
         rememberMe: false,
         sessionId: "session-b",
         sessionStartedAt: 200,
         updatedAt: 200,
      },
      { broadcast: false },
   );

   assert.equal(localStorage.getItem("access"), null);
   assert.equal(sessionStorage.getItem("access"), "session-access");
   assert.equal(getAuthSnapshot()?.sessionId, "session-b");
});

test("refresh keeps the current browser-session identity and persistence", () => {
   resetStorage();

   const login = storeAuthTokens("access-a", "refresh-a", false, {
      broadcast: false,
   });
   const refreshed = updateAuthTokens("access-b", "refresh-b", {
      broadcast: false,
   });

   assert.equal(refreshed.sessionId, login.sessionId);
   assert.equal(refreshed.sessionStartedAt, login.sessionStartedAt);
   assert.equal(refreshed.rememberMe, false);
   assert.equal(sessionStorage.getItem("access"), "access-b");
});

test("newer login session wins over a later refresh from an older identity", () => {
   const oldRefresh = {
      access: "old-access-newer-refresh",
      refresh: "old-refresh",
      rememberMe: false,
      sessionId: "old-session",
      sessionStartedAt: 100,
      updatedAt: 500,
   };
   const newLogin = {
      access: "new-access",
      refresh: "new-refresh",
      rememberMe: false,
      sessionId: "new-session",
      sessionStartedAt: 300,
      updatedAt: 300,
   };

   assert.equal(
      chooseFreshestAuthSnapshot(oldRefresh, newLogin)?.sessionId,
      "new-session",
   );
});

test("stale logout from an older session does not clear a newer login", () => {
   const current = {
      access: "new-access",
      refresh: "new-refresh",
      rememberMe: false,
      sessionId: "new-session",
      sessionStartedAt: 300,
      updatedAt: 300,
   };

   assert.equal(
      shouldApplyAuthClear(current, {
         sessionId: "old-session",
         sessionStartedAt: 100,
      }),
      false,
   );
   assert.equal(
      shouldApplyAuthClear(current, {
         sessionId: "new-session",
         sessionStartedAt: 300,
      }),
      true,
   );
});

test("clear removes remembered and session-only material", () => {
   resetStorage();

   localStorage.setItem("access", "stale-local");
   sessionStorage.setItem("refresh", "stale-session");

   clearAuthTokens({ broadcast: false });

   assert.equal(localStorage.getItem("access"), null);
   assert.equal(sessionStorage.getItem("refresh"), null);
   assert.equal(getAuthSnapshot(), null);
});
