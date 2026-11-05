const configuredApiBaseUrl = import.meta.env.VITE_EXTENSION_API_BASE_URL?.trim();
const configuredWebAppBaseUrl = import.meta.env.VITE_EXTENSION_WEB_APP_BASE_URL?.trim();

const apiBaseUrl = (configuredApiBaseUrl || (import.meta.env.DEV ? "http://localhost:8000/api" : "")).replace(
   /\/+$/,
   "",
);

const webAppBaseUrl = (configuredWebAppBaseUrl || (import.meta.env.DEV ? "http://localhost:5174" : "")).replace(
   /\/+$/,
   "",
);

const LOCAL_WEB_APP_ORIGINS = [
   "http://localhost:5174",
   "http://127.0.0.1:5174",
];

const DEPLOYED_WEB_APP_ORIGINS = [
   "https://truthlens-dev.vercel.app",
   "https://truthlens.social",
   "https://www.truthlens.social",
];

const isLocalWebApp = LOCAL_WEB_APP_ORIGINS.includes(webAppBaseUrl);

export const state = {
   API_BASE_URL: apiBaseUrl,
   WEB_APP_BASE_URL: webAppBaseUrl,
   WEB_APP_ORIGINS: isLocalWebApp
      ? LOCAL_WEB_APP_ORIGINS
      : DEPLOYED_WEB_APP_ORIGINS,
   isSnipping: false,
   isDrawing: false,
   startX: 0,
   startY: 0,
   selectionBox: null,
   overlay: null,
   isAnalyzing: false,
};
