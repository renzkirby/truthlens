export const state = {
   API_BASE_URL: "https://truthlens-backend-dev.duckdns.org/api",
   // API_BASE_URL: "http://localhost:8000/api",
   WEB_APP_ORIGINS: [
      "https://truthlens-dev.vercel.app",
      "http://localhost:5174",
      "http://127.0.0.1:5174",
   ],
   isSnipping: false,
   isDrawing: false,
   startX: 0,
   startY: 0,
   selectionBox: null,
   overlay: null,
   isAnalyzing: false,
};
