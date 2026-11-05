import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { crx } from "@crxjs/vite-plugin";
import { fileURLToPath } from "node:url";
import manifest from "./manifest.json";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
   const extensionRoot = fileURLToPath(new URL(".", import.meta.url));
   const extensionEnv = loadEnv(mode, extensionRoot, "VITE_");
   const apiBaseUrl = extensionEnv.VITE_EXTENSION_API_BASE_URL?.trim();
   const webAppBaseUrl = extensionEnv.VITE_EXTENSION_WEB_APP_BASE_URL?.trim();
   const isLocalBuild = mode === "development";

   if (!apiBaseUrl || !webAppBaseUrl) {
      throw new Error(
         "VITE_EXTENSION_API_BASE_URL and VITE_EXTENSION_WEB_APP_BASE_URL are required for extension builds.",
      );
   }

   const buildManifest = JSON.parse(JSON.stringify(manifest));
   buildManifest.host_permissions = isLocalBuild
      ? [
           "http://localhost:8000/*",
           "http://127.0.0.1:8000/*",
        ]
      : [
           "https://api.truthlens.social/*",
        ];

   const authBridgeResources = buildManifest.web_accessible_resources?.find(
      (entry) => entry.resources?.includes("auth-bridge.js"),
   );
   if (authBridgeResources) {
      authBridgeResources.matches = isLocalBuild
         ? [
              "http://localhost:5174/*",
              "http://127.0.0.1:5174/*",
           ]
         : [
              "https://truthlens-dev.vercel.app/*",
              "https://truthlens.social/*",
              "https://www.truthlens.social/*",
           ];
   }

   return {
      plugins: [react(), crx({ manifest: buildManifest })],
   };
});
