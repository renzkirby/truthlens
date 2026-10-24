export const WORKSPACE_SUCCESS_TOAST_DURATION = 5000;
export const WORKSPACE_LONG_TOAST_DURATION = 6000;

export function showWorkspaceSuccess(
   addToast,
   { title, message = "", duration = WORKSPACE_SUCCESS_TOAST_DURATION },
) {
   return addToast({
      type: "success",
      title,
      message,
      duration,
   });
}
