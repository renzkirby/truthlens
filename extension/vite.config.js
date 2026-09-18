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

   if (mode === "production" && !apiBaseUrl) {
      throw new Error(
         "VITE_EXTENSION_API_BASE_URL is required for production extension builds.",
      );
   }

   return {
      plugins: [react(), crx({ manifest })],
   };
});
