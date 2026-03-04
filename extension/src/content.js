import "./content.css";

console.log("TruthLens content script loaded");

let isSnipping = false;
let isDrawing = false;
let startX, startY;
let selectionBox = null;
let overlay = null;

chrome.runtime.onMessage.addListener(function (request, sender, sendResponse) {
   if (request.type === "ACTIVATE_SNIPPING") {
      console.log("Snipping mode activated!");
      activateSnippingMode();
      sendResponse({ success: true });
   }
});

function activateSnippingMode() {
   isSnipping = true;

   createOverlay();

   document.addEventListener("mousedown", onMouseDown);
   document.addEventListener("mousemove", onMouseMove);
   document.addEventListener("mouseup", onMouseUp);
   document.addEventListener("keydown", onKeyDown);

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

   const width = Math.abs(currentX - startX);
   const height = Math.abs(currentY - startY);

   const left = Math.min(startX, currentX);
   const top = Math.min(startY, currentY);

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

   const left = Math.min(startX, endX);
   const top = Math.min(startY, endY);
   const width = Math.abs(endX - startX);
   const height = Math.abs(endY - startY);

   console.log("Selection complete:", { left, top, width, height });

   if (width < 10 || height < 10) {
      console.log("Selection too small, canceling");
      cleanup();
      return;
   }
   captureScreenshot({ left, top, width, height });
}

function onKeyDown(e) {
   if (e.key === "Escape") {
      console.log("Snipping canceled by user");
      cleanup();
   }
}

function captureScreenshot(coords) {
   console.log("Requesting screenshot with coords:", coords);

   if (selectionBox) selectionBox.style.display = "none";
   if (overlay) overlay.style.display = "none";

   setTimeout(() => {
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
   }, 100);
}

function cropAndSave(fullScreenshot, coords) {
   const img = new Image();
   img.onload = function () {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");

      const dpr = window.devicePixelRatio || 1;

      canvas.width = coords.width * dpr;
      canvas.height = coords.height * dpr;

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

   console.log("Image analysis complete, result received from server");
   console.log("Server response:", data);

   displayResultCard(data);
}

function cleanup() {
   isSnipping = false;
   isDrawing = false;

   if (overlay) {
      overlay.remove();
      overlay = null;
   }

   if (selectionBox) {
      selectionBox.remove();
      selectionBox = null;
   }

   document.body.style.cursor = "";

   document.removeEventListener("mousedown", onMouseDown);
   document.removeEventListener("mousemove", onMouseMove);
   document.removeEventListener("mouseup", onMouseUp);
   document.removeEventListener("keydown", onKeyDown);

   console.log("Snipping mode deactivated");
}

function displayResultCard(data) {
   const { result, source_type, cleaned_text } = data;

   let verdict = "Analyzing...";
   let summary = "No summary available.";
   let confidence_score = "N/A";
   let sourceUrl = "#";
   let badgeColor = "#6b7280";

   if (source_type === "Official Fact Check" && result && result.length > 0) {
      verdict = result.verdict;
      summary = result.summary;
      confidence_score = result.confidence_score;

      const lowerVerdict = verdict.toLowerCase();
      if (lowerVerdict === "fake" || lowerVerdict === "misleading" || lowerVerdict === "false")
         badgeColor = "#e02424";
      else if (lowerVerdict === "fact") badgeColor = "#0e9f6e";
      else if (lowerVerdict === "satire") badgeColor = "#a83bf1";
      else if (lowerVerdict.includes("scope")) badgeColor = "#6b7280";
      else badgeColor = "#ebdc09";

      if (result.sources && result.sources.length > 0) {
         sourceUrl = result.sources[0].url;
      }
   } else if (source_type === "Live Web Search") {
      verdict = result.verdict;
      summary = result.summary;
      confidence_score = result.confidence_score;

      const lowerVerdict = verdict.toLowerCase();
      if (lowerVerdict === "fake" || lowerVerdict === "misleading" || lowerVerdict === "false")
         badgeColor = "#e02424";
      else if (lowerVerdict === "fact") badgeColor = "#0e9f6e";
      else if (lowerVerdict === "satire") badgeColor = "#a83bf1";
      else if (lowerVerdict.includes("scope")) badgeColor = "#6b7280";
      else badgeColor = "#ebdc09";

      if (result.sources && result.sources.length > 0) {
         sourceUrl = result.sources[0].url;
      }
   } else if (source_type === "N/A") {
      verdict = result.verdict;
      summary = result.summary;
      confidence_score = result.confidence_score;
   }

   console.log("Verdict:", verdict);
   console.log("Summary:", summary);
   console.log("Confidence Score:", confidence_score);
   console.log("Source URL:", sourceUrl);

   const card = document.createElement("div");
   card.id = "truthlens-result-card";
   card.className = "truthlens-card";

   let confidence_bar_color = "#6b7280"; // Default gray

   if (confidence_score < 40) confidence_bar_color = "#e02424";
   else if (confidence_score >= 40 && confidence_score < 70) confidence_bar_color = "#ebdc09";
   else if (confidence_score >= 70) confidence_bar_color = "#0e9f6e";

   card.innerHTML = `
      <div class="truthlens-header">
         <strong class="truthlens-title">TruthLens</strong>
         <button id="truthlens-close-btn" class="truthlens-close-btn">&times;</button>
      </div>
      <div class="truthlens-verdict-text">
         This post is <span class="truthlens-verdict" style="background-color: ${badgeColor};">${verdict}</span>
      </div>
      <div class="truthlens-summary-box">
         <div class="truthlens-summary-title">AI Summary</div>
         <div style="font-size: 14px; line-height: 1.4;">${summary}</div>
      </div>
      <div class="truthlens-confidence-score">Confidence Score: ${confidence_score}</div>
      <div class="truthlens-confidence-bar">
         <div class="truthlens-confidence-fill" style="width: ${confidence_score}%; background-color: ${confidence_bar_color};"></div>
      </div>

      ${
         verdict === "UNVERIFIED"
            ? "<a href='#' target='_blank' class='truthlens-source-link'>Want to ask the community?</a>"
            : verdict === "OUT_OF_SCOPE"
              ? ""
              : `<a href="${sourceUrl}" target="_blank" class="truthlens-source-link">View Source</a>`
      }

      <div class="truthlens-footer">Source Type: ${source_type}</div>
      `;

   document.body.appendChild(card);
   document.getElementById("truthlens-close-btn").addEventListener("click", () => {
      card.remove();
   });
}
