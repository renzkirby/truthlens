export function shouldSubmitTextVerifyOnKeyDown(event) {
   if (!event || event.key !== "Enter") return false;
   if (event.shiftKey) return false;
   if (event.isComposing || event.nativeEvent?.isComposing) return false;
   return true;
}
