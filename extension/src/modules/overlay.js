import { state } from "./state.js";
import { captureScreenshot } from "./screenshot.js";

export function createOverlay() {
   state.overlay = document.createElement("div");
   state.overlay.style.position = "fixed";
   state.overlay.style.top = "0";
   state.overlay.style.left = "0";
   state.overlay.style.width = "100%";
   state.overlay.style.height = "100%";
   state.overlay.style.background = "rgba(0, 0, 0, 0.3)";
   state.overlay.style.zIndex = "999999";
   state.overlay.style.cursor = "crosshair";
   document.body.appendChild(state.overlay);

   console.log("Overlay created");
}

export function onMouseDown(e) {
   if (!state.isSnipping) return;

   state.isDrawing = true;
   state.startX = e.clientX;
   state.startY = e.clientY;

   console.log("Mouse down at:", state.startX, state.startY);

   state.selectionBox = document.createElement("div");
   state.selectionBox.style.position = "fixed";
   state.selectionBox.style.border = "2px solid #2196F3";
   state.selectionBox.style.background = "rgba(33, 150, 243, 0.1)";
   state.selectionBox.style.zIndex = "1000000";
   state.selectionBox.style.left = state.startX + "px";
   state.selectionBox.style.top = state.startY + "px";
   state.selectionBox.style.width = "0px";
   state.selectionBox.style.height = "0px";
   document.body.appendChild(state.selectionBox);
}

export function onMouseMove(e) {
   if (!state.isSnipping || !state.isDrawing) return;

   const currentX = e.clientX;
   const currentY = e.clientY;

   const width = Math.abs(currentX - state.startX);
   const height = Math.abs(currentY - state.startY);

   const left = Math.min(state.startX, currentX);
   const top = Math.min(state.startY, currentY);

   state.selectionBox.style.left = left + "px";
   state.selectionBox.style.top = top + "px";
   state.selectionBox.style.width = width + "px";
   state.selectionBox.style.height = height + "px";
}

export function onMouseUp(e) {
   if (!state.isSnipping || !state.isDrawing) return;

   state.isDrawing = false;

   const endX = e.clientX;
   const endY = e.clientY;

   const left = Math.min(state.startX, endX);
   const top = Math.min(state.startY, endY);
   const width = Math.abs(endX - state.startX);
   const height = Math.abs(endY - state.startY);

   console.log("Selection complete:", { left, top, width, height });

   if (width < 10 || height < 10) {
      console.log("Selection too small, canceling");
      cleanup();
      return;
   }
   captureScreenshot({ left, top, width, height });
}

export function cleanup() {
   state.isSnipping = false;
   state.isDrawing = false;

   if (state.overlay) {
      state.overlay.remove();
      state.overlay = null;
   }

   if (state.selectionBox) {
      state.selectionBox.remove();
      state.selectionBox = null;
   }

   document.body.style.cursor = "";

   document.removeEventListener("mousedown", onMouseDown);
   document.removeEventListener("mousemove", onMouseMove);
   document.removeEventListener("mouseup", onMouseUp);

   console.log("Snipping mode deactivated");
}
