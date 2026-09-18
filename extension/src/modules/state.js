const configuredApiBaseUrl = import.meta.env.VITE_EXTENSION_API_BASE_URL?.trim();
const apiBaseUrl = (
   configuredApiBaseUrl || (import.meta.env.DEV ? "http://localhost:8000/api" : "")
).replace(/\/+$/, "");

export const state = {
   API_BASE_URL: apiBaseUrl,
   WEB_APP_ORIGINS: [
      "http://localhost:5174",
      "http://127.0.0.1:5174",
      "https://truthlens-dev.vercel.app",
      "https://truthlens.app",
      "https://www.truthlens.app",
   ],
   isSnipping: false,
   isDrawing: false,
   startX: 0,
   startY: 0,
   selectionBox: null,
   overlay: null,
   isAnalyzing: false,
};
