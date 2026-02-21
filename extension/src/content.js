// content.js - Snipping tool implementation

console.log("TruthLens content script loaded");

let isSnipping = false;
let isDrawing = false;
let startX, startY;
let selectionBox = null;
let overlay = null;

// Listen for activation from popup
chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "ACTIVATE_SNIPPING") {
      console.log("Snipping mode activated!");
      activateSnippingMode();
      sendResponse({ success: true });
   }
});

function activateSnippingMode() {
   isSnipping = true;

   // Create overlay
   createOverlay();

   // Add event listeners
   document.addEventListener("mousedown", onMouseDown);
   document.addEventListener("mousemove", onMouseMove);
   document.addEventListener("mouseup", onMouseUp);
   document.addEventListener("keydown", onKeyDown);

   // Change cursor
   document.body.style.cursor = "crosshair";
}

function createOverlay() {
   overlay = document.createElement("div");
   overlay.style.position = "fixed";
   overlay.style.top = "0";
   overlay.style.left = "0";
   overlay.style.width = "100%";
   overlay.style.height = "100%";
   overlay.style.background = "rgba(0, 0, 0, 0.3)";
   overlay.style.zIndex = "999999";
   overlay.style.cursor = "crosshair";
   document.body.appendChild(overlay);

   console.log("Overlay created");
}

function onMouseDown(e) {
   if (!isSnipping) return;

   isDrawing = true;
   startX = e.clientX;
   startY = e.clientY;

   console.log("Mouse down at:", startX, startY);

   // Create selection box
   selectionBox = document.createElement("div");
   selectionBox.style.position = "fixed";
   selectionBox.style.border = "2px solid #2196F3";
   selectionBox.style.background = "rgba(33, 150, 243, 0.1)";
   selectionBox.style.zIndex = "1000000";
   selectionBox.style.left = startX + "px";
   selectionBox.style.top = startY + "px";
   selectionBox.style.width = "0px";
   selectionBox.style.height = "0px";
   document.body.appendChild(selectionBox);
}

function onMouseMove(e) {
   if (!isSnipping || !isDrawing) return;

   const currentX = e.clientX;
   const currentY = e.clientY;

   // Calculate width and height (handle all drag directions)
   const width = Math.abs(currentX - startX);
   const height = Math.abs(currentY - startY);

   // Calculate top-left corner (handle dragging in any direction)
   const left = Math.min(startX, currentX);
   const top = Math.min(startY, currentY);

   // Update selection box
   selectionBox.style.left = left + "px";
   selectionBox.style.top = top + "px";
   selectionBox.style.width = width + "px";
   selectionBox.style.height = height + "px";
}

function onMouseUp(e) {
   if (!isSnipping || !isDrawing) return;

   isDrawing = false;

   const endX = e.clientX;
   const endY = e.clientY;

   // Calculate final coordinates
   const left = Math.min(startX, endX);
   const top = Math.min(startY, endY);
   const width = Math.abs(endX - startX);
   const height = Math.abs(endY - startY);

   console.log("Selection complete:", { left, top, width, height });

   // Check if selection is too small
   if (width < 10 || height < 10) {
      console.log("Selection too small, canceling");
      cleanup();
      return;
   }

   // Capture screenshot
   captureScreenshot({ left, top, width, height });
}

function onKeyDown(e) {
   // ESC to cancel
   if (e.key === "Escape") {
      console.log("Snipping canceled by user");
      cleanup();
   }
}

function captureScreenshot(coords) {
   console.log("Requesting screenshot with coords:", coords);

   // 1. Hide the UI elements so they aren't included in the screenshot
   if (selectionBox) selectionBox.style.display = "none";
   if (overlay) overlay.style.display = "none";

   // 2. Wait a brief moment (100ms) for the browser to repaint the DOM without your UI
   setTimeout(() => {
      // 3. Send to background script for capture AFTER the UI is hidden
      chrome.runtime.sendMessage(
         {
            type: "CAPTURE_SCREENSHOT",
            coords: coords,
         },
         function (response) {
            if (response && response.screenshot) {
               console.log("Screenshot received, cropping...");
               cropAndSave(response.screenshot, coords);
            } else {
               console.error("Screenshot capture failed");
               cleanup();
            }
         },
      );
   }, 100); // 100ms is a safe delay to guarantee the blue box and dark tint are gone
}

function cropAndSave(fullScreenshot, coords) {
   const img = new Image();
   img.onload = function () {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");

      // 1. Get the device pixel ratio (e.g., 2 for Retina screens, 1.25 for 125% Windows scaling)
      const dpr = window.devicePixelRatio || 1;

      // 2. Scale the canvas dimensions to match the physical pixels for high-quality output (Best for OCR)
      canvas.width = coords.width * dpr;
      canvas.height = coords.height * dpr;

      // 3. Crop the image using the scaled coordinates
      ctx.drawImage(
         img,
         coords.left * dpr, // Source X (Physical)
         coords.top * dpr, // Source Y (Physical)
         coords.width * dpr, // Source Width (Physical)
         coords.height * dpr, // Source Height (Physical)
         0, // Destination X
         0, // Destination Y
         canvas.width, // Destination Width
         canvas.height, // Destination Height
      );

      const croppedScreenshot = canvas.toDataURL("image/png");
      console.log("Screenshot cropped successfully");

      // Store in chrome.storage or send to Django
      console.log("Cropped screenshot ready:", croppedScreenshot.substring(0, 50) + "...");
      console.log(croppedScreenshot);
      // TODO: Send to Django backend here
      const payload = {
         image_data: croppedScreenshot,
      };
      sendImageToServer(payload);

      cleanup();
   };

   img.src = fullScreenshot;
}

async function sendImageToServer(image) {
   const response = await fetch("http://localhost:8000/api/analyze/", {
      method: "POST",
      headers: {
         "content-type": "application/json",
      },
      body: JSON.stringify(image),
   });

   const data = await response.json();

   console.log(data.message);
   console.log(data.extracted_text);
   console.log(data.result);
}

function cleanup() {
   isSnipping = false;
   isDrawing = false;

   // Remove overlay
   if (overlay) {
      overlay.remove();
      overlay = null;
   }

   // Remove selection box
   if (selectionBox) {
      selectionBox.remove();
      selectionBox = null;
   }

   // Reset cursor
   document.body.style.cursor = "";

   // Remove event listeners
   document.removeEventListener("mousedown", onMouseDown);
   document.removeEventListener("mousemove", onMouseMove);
   document.removeEventListener("mouseup", onMouseUp);
   document.removeEventListener("keydown", onKeyDown);

   console.log("Snipping mode deactivated");
}
