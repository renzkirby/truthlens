import test from "node:test";
import assert from "node:assert/strict";

import { shouldSubmitTextVerifyOnKeyDown } from "./textVerifyKeyboard.js";

test("Enter submits a text verification", () => {
   assert.equal(
      shouldSubmitTextVerifyOnKeyDown({
         key: "Enter",
         shiftKey: false,
         isComposing: false,
         nativeEvent: { isComposing: false },
      }),
      true,
   );
});

test("Shift+Enter keeps a newline", () => {
   assert.equal(
      shouldSubmitTextVerifyOnKeyDown({
         key: "Enter",
         shiftKey: true,
         isComposing: false,
         nativeEvent: { isComposing: false },
      }),
      false,
   );
});

test("IME composition Enter does not submit", () => {
   assert.equal(
      shouldSubmitTextVerifyOnKeyDown({
         key: "Enter",
         shiftKey: false,
         isComposing: true,
         nativeEvent: { isComposing: true },
      }),
      false,
   );
});

test("non-Enter keys do not submit", () => {
   assert.equal(
      shouldSubmitTextVerifyOnKeyDown({
         key: "a",
         shiftKey: false,
         isComposing: false,
         nativeEvent: { isComposing: false },
      }),
      false,
   );
});
